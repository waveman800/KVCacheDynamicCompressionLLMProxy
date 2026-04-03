"""
压缩代理核心

提供透明的 LLM 请求代理，自动压缩上下文
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any, AsyncGenerator, Union
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

import httpx
from pydantic import BaseModel, Field

from .compressor import DynamicCompressor, CompressionResult
from .cache import KVCacheManager
from .metrics import MetricsCollector


class ProxyConfig(BaseModel):
    """代理配置"""
    # 目标服务配置（支持环境变量覆盖）
    target_url: str = Field(
        default="https://api.openai.com/v1",
        description="目标模型服务地址 (env: TARGET_URL / BASE_URL)"
    )
    api_key: Optional[str] = Field(default=None, description="API Key (env: API_KEY)")
    
    # 压缩配置
    enable_compression: bool = Field(default=True, description="env: ENABLE_COMPRESSION")
    memories_target_tokens: int = Field(default=1500, description="env: MEMORIES_TARGET")
    history_target_tokens: int = Field(default=1000, description="env: HISTORY_TARGET")
    history_keep_last_n: int = Field(default=4, description="历史对话保留轮数 (env: HISTORY_KEEP_LAST_N)")
    
    # 动态压缩算法参数
    similarity_threshold: float = Field(default=0.55, description="相似度阈值 (env: SIMILARITY_THRESHOLD)")
    session_len: int = Field(default=8192, description="会话长度限制 (env: SESSION_LEN)")
    use_fast_mode: bool = Field(default=False, description="快速压缩模式 (env: USE_FAST_MODE)")
    
    # 细粒度压缩参数
    compression_granularity: str = Field(default="paragraph", description="压缩粒度: full/paragraph/sentence (env: COMPRESSION_GRANULARITY)")
    min_keep_segments: int = Field(default=1, description="每个记忆最少保留的片段数 (env: MIN_KEEP_SEGMENTS)")
    
    # 重要性评分权重（总和应为1.0）
    content_importance_weight: float = Field(default=0.7, description="内容重要性权重 0-1，内部:关键词60%+TF-IDF40% (env: CONTENT_IMPORTANCE_WEIGHT)")
    position_weight: float = Field(default=0.2, description="位置权重 0-1 (env: POSITION_WEIGHT)")
    query_weight: float = Field(default=0.1, description="查询相关性权重 0-1 (env: QUERY_WEIGHT)")
    
    # KV Cache 基础配置
    enable_kv_cache: bool = Field(default=True, description="env: ENABLE_KV_CACHE")
    kv_cache_size: int = Field(default=2000, description="env: KV_CACHE_SIZE (默认2000，配合压缩实际内存占用≈1000)")
    kv_cache_ttl: int = Field(default=3600, description="env: KV_CACHE_TTL")
    
    # 高性价比 KV Cache 优化参数
    kv_cache_enable_compression: bool = Field(default=True, description="启用内存压缩 (env: KV_CACHE_COMPRESSION)")
    kv_cache_compression_threshold: int = Field(default=1024, description="压缩阈值字节 (env: KV_CACHE_COMPRESSION_THRESHOLD)")
    kv_cache_hot_ratio: float = Field(default=0.2, description="热点数据比例 0-1 (env: KV_CACHE_HOT_RATIO)")
    kv_cache_adaptive_ttl: bool = Field(default=True, description="自适应TTL (env: KV_CACHE_ADAPTIVE_TTL)")
    kv_cache_min_ttl: int = Field(default=300, description="最小TTL秒 (env: KV_CACHE_MIN_TTL)")
    kv_cache_max_ttl: int = Field(default=7200, description="最大TTL秒 (env: KV_CACHE_MAX_TTL)")
    
    # 请求配置
    timeout: float = Field(default=60.0)
    max_retries: int = Field(default=3)
    enable_streaming: bool = Field(default=True)
    
    @classmethod
    def from_env(cls) -> "ProxyConfig":
        """从环境变量创建配置"""
        import os
        
        return cls(
            target_url=os.getenv("TARGET_URL", os.getenv("BASE_URL", "https://api.openai.com/v1")),
            api_key=os.getenv("API_KEY"),
            enable_compression=os.getenv("ENABLE_COMPRESSION", "true").lower() == "true",
            memories_target_tokens=int(os.getenv("MEMORIES_TARGET", "1500")),
            history_target_tokens=int(os.getenv("HISTORY_TARGET", "1000")),
            history_keep_last_n=int(os.getenv("HISTORY_KEEP_LAST_N", "4")),
            similarity_threshold=float(os.getenv("SIMILARITY_THRESHOLD", "0.55")),
            session_len=int(os.getenv("SESSION_LEN", "8192")),
            use_fast_mode=os.getenv("USE_FAST_MODE", "false").lower() == "true",
            compression_granularity=os.getenv("COMPRESSION_GRANULARITY", "paragraph"),
            min_keep_segments=int(os.getenv("MIN_KEEP_SEGMENTS", "1")),
            content_importance_weight=float(os.getenv("CONTENT_IMPORTANCE_WEIGHT", "0.7")),
            position_weight=float(os.getenv("POSITION_WEIGHT", "0.2")),
            query_weight=float(os.getenv("QUERY_WEIGHT", "0.1")),
            enable_kv_cache=os.getenv("ENABLE_KV_CACHE", "true").lower() == "true",
            kv_cache_size=int(os.getenv("KV_CACHE_SIZE", "2000")),
            kv_cache_ttl=int(os.getenv("KV_CACHE_TTL", "3600")),
            kv_cache_enable_compression=os.getenv("KV_CACHE_COMPRESSION", "true").lower() == "true",
            kv_cache_compression_threshold=int(os.getenv("KV_CACHE_COMPRESSION_THRESHOLD", "1024")),
            kv_cache_hot_ratio=float(os.getenv("KV_CACHE_HOT_RATIO", "0.2")),
            kv_cache_adaptive_ttl=os.getenv("KV_CACHE_ADAPTIVE_TTL", "true").lower() == "true",
            kv_cache_min_ttl=int(os.getenv("KV_CACHE_MIN_TTL", "300")),
            kv_cache_max_ttl=int(os.getenv("KV_CACHE_MAX_TTL", "7200")),
        )


@dataclass
class ProxyResult:
    """代理处理结果"""
    success: bool
    backend_request: Dict[str, Any]
    backend_response: Optional[str] = None
    compression_info: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time_ms: float = 0.0


class CompressionProxy:
    """
    压缩代理
    
    核心功能：
    1. 接收 OpenAI 兼容格式的请求
    2. 自动识别并压缩 memories/history
    3. 转发到后端模型服务
    4. 返回响应（带压缩统计）
    """
    
    def __init__(self, config: ProxyConfig):
        self.config = config
        self.compressor = DynamicCompressor(
            similarity_threshold=config.similarity_threshold,
            session_len=config.session_len,
            use_fast_mode=config.use_fast_mode,
            granularity=config.compression_granularity,
            min_keep_segments=config.min_keep_segments,
            keyword_weight=config.content_importance_weight * 0.6,
            tfidf_weight=config.content_importance_weight * 0.4,
            position_weight=config.position_weight,
            query_weight=config.query_weight
        )
        self.cache_manager = KVCacheManager(
            max_size=config.kv_cache_size,
            ttl_seconds=config.kv_cache_ttl,
            enable_compression=config.kv_cache_enable_compression,
            compression_threshold=config.kv_cache_compression_threshold,
            hot_data_ratio=config.kv_cache_hot_ratio,
            adaptive_ttl=config.kv_cache_adaptive_ttl,
            min_ttl=config.kv_cache_min_ttl,
            max_ttl=config.kv_cache_max_ttl
        ) if config.enable_kv_cache else None
        self.metrics = MetricsCollector()
        
        # HTTP 客户端
        headers = {}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        
        self.http_client = httpx.AsyncClient(
            timeout=config.timeout,
            headers=headers
        )
    
    async def process_request(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4",
        memories: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs
    ) -> ProxyResult:
        """
        处理请求（压缩 + 转发）
        
        Args:
            messages: OpenAI 格式的消息列表
            model: 模型名称
            memories: 记忆列表（可选）
            user_id: 用户标识
            session_id: 会话标识
            
        Returns:
            ProxyResult: 处理结果
        """
        start_time = time.time()
        
        try:
            # 1. 解析消息
            system_prompt = ""
            chat_history = []
            current_query = ""
            
            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                
                if role == "system":
                    system_prompt = content
                elif role == "user":
                    if not current_query:
                        current_query = content
                    else:
                        chat_history.append({"role": "user", "content": content})
                elif role == "assistant":
                    chat_history.append({"role": "assistant", "content": content})
            
            # 2. 执行压缩
            compression_info = None
            compressed_messages = messages.copy()
            
            if self.config.enable_compression:
                comp_result = await self._compress_context(
                    system_prompt=system_prompt,
                    memories=memories or [],
                    chat_history=chat_history,
                    query=current_query,
                    user_id=user_id,
                    session_id=session_id
                )
                
                compressed_messages = comp_result["messages"]
                compression_info = comp_result["info"]
                
                # 更新指标
                if compression_info:
                    self.metrics.record_compression(compression_info)
            
            # 3. 构建后端请求
            backend_request = {
                "model": model,
                "messages": [
                    {"role": m["role"], "content": m["content"]} 
                    for m in compressed_messages
                ],
                **kwargs
            }
            
            processing_time = (time.time() - start_time) * 1000
            
            return ProxyResult(
                success=True,
                backend_request=backend_request,
                compression_info=compression_info,
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            return ProxyResult(
                success=False,
                backend_request={},
                error=str(e),
                processing_time_ms=(time.time() - start_time) * 1000
            )
    
    async def forward_to_backend(
        self,
        backend_request: Dict[str, Any],
        stream: bool = False
    ) -> AsyncGenerator[str, None]:
        """
        转发请求到后端
        
        Args:
            backend_request: 后端请求体
            stream: 是否流式响应
            
        Yields:
            响应内容
        """
        url = f"{self.config.target_url}/chat/completions"
        
        for attempt in range(self.config.max_retries):
            try:
                if stream:
                    async with self.http_client.stream(
                        "POST", url, json=backend_request
                    ) as response:
                        async for chunk in response.aiter_text():
                            yield chunk
                else:
                    response = await self.http_client.post(url, json=backend_request)
                    yield response.text
                
                return
                
            except Exception as e:
                if attempt == self.config.max_retries - 1:
                    yield json.dumps({"error": str(e)})
                else:
                    await asyncio.sleep(0.5 * (attempt + 1))
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4",
        stream: bool = False,
        memories: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> Union[Dict[str, Any], AsyncGenerator[str, None]]:
        """
        完整的聊天补全接口
        
        Args:
            messages: 消息列表
            model: 模型名称
            stream: 是否流式
            memories: 记忆列表
            user_id: 用户标识
            
        Returns:
            非流式：完整响应字典
            流式：异步生成器
        """
        # 处理请求
        result = await self.process_request(
            messages=messages,
            model=model,
            memories=memories,
            user_id=user_id,
            **kwargs
        )
        
        if not result.success:
            if stream:
                async def error_gen():
                    yield json.dumps({"error": result.error})
                return error_gen()
            else:
                return {"error": result.error}
        
        # 转发到后端
        if stream:
            return self.forward_to_backend(result.backend_request, stream=True)
        else:
            async for response_text in self.forward_to_backend(result.backend_request, stream=False):
                try:
                    response_data = json.loads(response_text)
                    
                    # 添加压缩信息
                    if result.compression_info:
                        response_data["compression"] = result.compression_info
                    
                    return response_data
                except json.JSONDecodeError:
                    return {"error": "Invalid response from backend", "raw": response_text}
            
            return {"error": "No response from backend"}
    
    async def _compress_context(
        self,
        system_prompt: str,
        memories: List[str],
        chat_history: List[Dict[str, str]],
        query: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        压缩上下文
        
        Returns:
            {"messages": [...], "info": {...}}
        """
        info = {
            "original_memories_count": len(memories),
            "original_history_turns": len(chat_history) // 2,
            "cache_hit": False
        }
        
        # 检查 KV Cache
        cache_key = None
        if self.cache_manager and user_id:
            cache_key = f"{user_id}:{session_id or 'default'}:{hash(system_prompt) % 10000}"
            cached = self.cache_manager.get(cache_key)
            if cached:
                info["cache_hit"] = True
                info["cache_key"] = cache_key
        
        # 压缩 memories
        mem_result = self.compressor.compress_memories(
            memories=memories,
            max_tokens=self.config.memories_target_tokens,
            query=query
        )
        
        # 压缩 chat history
        hist_result = self.compressor.compress_chat_history(
            chat_history=chat_history,
            max_tokens=self.config.history_target_tokens,
            keep_last_n=self.config.history_keep_last_n
        )
        
        # 更新 info
        info.update({
            "memories_original_tokens": mem_result.original_tokens,
            "memories_compressed_tokens": mem_result.compressed_tokens,
            "memories_savings_percentage": mem_result.savings_percentage,
            "history_original_tokens": hist_result.original_tokens,
            "history_compressed_tokens": hist_result.compressed_tokens,
            "history_savings_percentage": hist_result.savings_percentage,
            "total_original_tokens": mem_result.original_tokens + hist_result.original_tokens,
            "total_compressed_tokens": mem_result.compressed_tokens + hist_result.compressed_tokens,
            "total_savings_percentage": (
                (mem_result.original_tokens + hist_result.original_tokens -
                 mem_result.compressed_tokens - hist_result.compressed_tokens) /
                max(mem_result.original_tokens + hist_result.original_tokens, 1) * 100
            )
        })
        
        # 构建压缩后的消息列表
        compressed_messages = []
        
        # System prompt
        if system_prompt:
            # 添加压缩后的 memories 到 system prompt
            if mem_result.content:
                mem_text = "\n".join([f"- {m}" for m in mem_result.content])
                system_prompt += f"\n\n[相关记忆]\n{mem_text}"
            compressed_messages.append({"role": "system", "content": system_prompt})
        
        # Chat history
        compressed_messages.extend(hist_result.content)
        
        # Current query
        if query:
            compressed_messages.append({"role": "user", "content": query})
        
        # 存储到 KV Cache
        if self.cache_manager and cache_key and not info["cache_hit"]:
            self.cache_manager.set(cache_key, {
                "system_prompt": system_prompt,
                "timestamp": time.time()
            })
        
        return {
            "messages": compressed_messages,
            "info": info
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取指标"""
        return self.metrics.get_summary()
    
    async def close(self):
        """关闭代理"""
        await self.http_client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
