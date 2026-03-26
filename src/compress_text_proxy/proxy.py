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
    # 目标后端配置（支持环境变量覆盖）
    target_url: str = Field(
        default="https://api.openai.com/v1",
        description="目标模型服务地址 (env: TARGET_URL)"
    )
    backend_type: str = Field(
        default="openai",
        description="后端类型: openai|vllm|sglang|lmdeploy (env: BACKEND_TYPE)"
    )
    api_key: Optional[str] = Field(default=None, description="API Key (env: API_KEY)")
    
    # 压缩配置
    enable_compression: bool = Field(default=True, description="env: ENABLE_COMPRESSION")
    memories_target_tokens: int = Field(default=1500, description="env: MEMORIES_TARGET")
    history_target_tokens: int = Field(default=1000, description="env: HISTORY_TARGET")
    history_keep_last_n: int = Field(default=4, description="历史对话保留轮数 (env: HISTORY_KEEP_LAST_N)")
    similarity_threshold: float = Field(default=0.55)
    
    # KV Cache 配置
    enable_kv_cache: bool = Field(default=True, description="env: ENABLE_KV_CACHE")
    kv_cache_size: int = Field(default=1000, description="env: KV_CACHE_SIZE")
    kv_cache_ttl: int = Field(default=3600, description="env: KV_CACHE_TTL")
    
    # 后端特定 KV Cache 配置
    vllm_prefix_caching: bool = Field(default=True, description="vLLM 前缀缓存 (env: VLLM_PREFIX_CACHING)")
    sglang_radix_cache: bool = Field(default=True, description="SGLang RadixAttention (env: SGLANG_RADIX_CACHE)")
    lmdeploy_cache_max_entries: int = Field(default=1000, description="LMDeploy 缓存条目 (env: LMDEPLOY_CACHE_ENTRIES)")
    
    # 请求配置
    timeout: float = Field(default=60.0)
    max_retries: int = Field(default=3)
    enable_streaming: bool = Field(default=True)
    
    @classmethod
    def from_env(cls) -> "ProxyConfig":
        """从环境变量创建配置"""
        import os
        
        return cls(
            target_url=os.getenv("TARGET_URL", "https://api.openai.com/v1"),
            backend_type=os.getenv("BACKEND_TYPE", "openai"),
            api_key=os.getenv("API_KEY"),
            enable_compression=os.getenv("ENABLE_COMPRESSION", "true").lower() == "true",
            memories_target_tokens=int(os.getenv("MEMORIES_TARGET", "1500")),
            history_target_tokens=int(os.getenv("HISTORY_TARGET", "1000")),
            enable_kv_cache=os.getenv("ENABLE_KV_CACHE", "true").lower() == "true",
            kv_cache_size=int(os.getenv("KV_CACHE_SIZE", "1000")),
            kv_cache_ttl=int(os.getenv("KV_CACHE_TTL", "3600")),
            vllm_prefix_caching=os.getenv("VLLM_PREFIX_CACHING", "true").lower() == "true",
            sglang_radix_cache=os.getenv("SGLANG_RADIX_CACHE", "true").lower() == "true",
            lmdeploy_cache_max_entries=int(os.getenv("LMDEPLOY_CACHE_ENTRIES", "1000")),
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
            similarity_threshold=config.similarity_threshold
        )
        self.cache_manager = KVCacheManager(
            backend_type=config.backend_type,
            max_size=config.kv_cache_size,
            ttl_seconds=config.kv_cache_ttl,
            vllm_prefix_caching=config.vllm_prefix_caching,
            sglang_radix_cache=config.sglang_radix_cache,
            lmdeploy_max_entries=config.lmdeploy_cache_max_entries
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
