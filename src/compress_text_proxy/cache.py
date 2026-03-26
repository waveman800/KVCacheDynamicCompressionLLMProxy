"""
KV Cache 管理器

兼容多种后端：vLLM、SGLang、LMDeploy
"""

import time
from typing import Dict, Any, Optional, List
from collections import OrderedDict
from enum import Enum


class BackendType(Enum):
    """支持的推理后端类型"""
    OPENAI = "openai"
    VLLM = "vllm"
    SGLANG = "sglang"
    LMDEPLOY = "lmdeploy"
    HUGGINGFACE = "huggingface"


class KVCacheManager:
    """
    统一的 KV Cache 管理器
    
    根据后端类型自动选择合适的缓存策略：
    - vLLM: 利用 prefix_caching 特性
    - SGLang: 利用 RadixAttention 特性  
    - LMDeploy: 手动管理 past_key_values
    - OpenAI: 客户端缓存（仅减少传输）
    - HuggingFace: 手动管理 past_key_values
    """
    
    def __init__(
        self, 
        backend_type: str = "openai",
        max_size: int = 1000, 
        ttl_seconds: int = 3600,
        vllm_prefix_caching: bool = True,
        sglang_radix_cache: bool = True,
        lmdeploy_max_entries: int = 1000
    ):
        self.backend_type = BackendType(backend_type.lower())
        self.max_size = max_size
        self.ttl = ttl_seconds
        self.vllm_prefix_caching = vllm_prefix_caching
        self.sglang_radix_cache = sglang_radix_cache
        self.lmdeploy_max_entries = lmdeploy_max_entries
        
        # 本地 LRU 缓存
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0
        
        # 统计信息
        self._backend_stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "tokens_saved": 0
        }
    
    def get_cache_key(
        self,
        prefix: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> str:
        """生成缓存键"""
        components = []
        if user_id:
            components.append(f"u:{user_id}")
        if session_id:
            components.append(f"s:{session_id}")
        components.append(f"p:{hash(prefix) % 10000}")
        return ":".join(components)
    
    def build_prefill_request(
        self,
        system_prompt: str,
        static_messages: List[Dict[str, str]],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        构建预填充请求（用于 vLLM/SGLang/LMDeploy）
        
        对于支持前缀缓存的后端，返回预填充请求
        对于不支持的后端，返回 None
        """
        if self.backend_type in [BackendType.OPENAI, BackendType.HUGGINGFACE]:
            return None
        
        # 构建前缀键
        prefix = f"{system_prompt}\n".join([f"{m['role']}:{m['content'][:50]}" for m in static_messages])
        cache_key = self.get_cache_key(prefix, user_id, session_id)
        
        # 检查本地缓存状态
        cached = self.get(cache_key)
        
        if self.backend_type == BackendType.VLLM:
            # vLLM: 使用 prefix_caching，只需发送相同前缀即可命中
            if self.vllm_prefix_caching:
                return {
                    "cache_key": cache_key,
                    "prefix": prefix,
                    "type": "vllm_prefix",
                    "hit": cached is not None
                }
        
        elif self.backend_type == BackendType.SGLANG:
            # SGLang: RadixAttention 自动缓存
            if self.sglang_radix_cache:
                return {
                    "cache_key": cache_key,
                    "prefix": prefix,
                    "type": "sglang_radix",
                    "hit": cached is not None
                }
        
        elif self.backend_type == BackendType.LMDEPLOY:
            # LMDeploy: 需要手动管理 session_id
            return {
                "cache_key": cache_key,
                "prefix": prefix,
                "type": "lmdeploy_session",
                "session_id": cache_key,
                "hit": cached is not None
            }
        
        return None
    
    def adapt_messages_for_backend(
        self,
        messages: List[Dict[str, str]],
        cache_hint: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, str]]:
        """
        根据后端类型调整消息格式
        
        Args:
            messages: 原始消息列表
            cache_hint: 缓存提示信息
            
        Returns:
            适配后的消息列表
        """
        if not cache_hint:
            return messages
        
        if self.backend_type == BackendType.LMDEPLOY:
            # LMDeploy 需要特殊处理：移除已缓存的前缀消息
            # 实际应用中应该根据 session 状态调整
            return messages
        
        # vLLM/SGLang/OpenAI 保持标准格式
        return messages
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if key not in self._cache:
            self._misses += 1
            return None
        
        entry = self._cache[key]
        
        # 检查过期
        if time.time() - entry["timestamp"] > self.ttl:
            del self._cache[key]
            self._misses += 1
            return None
        
        # 移动到最近使用
        self._cache.move_to_end(key)
        self._hits += 1
        
        return entry["value"]
    
    def set(self, key: str, value: Any):
        """设置缓存值"""
        # 如果已满，淘汰最旧的
        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)
        
        self._cache[key] = {
            "value": value,
            "timestamp": time.time()
        }
        self._cache.move_to_end(key)
    
    def delete(self, key: str):
        """删除缓存"""
        if key in self._cache:
            del self._cache[key]
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        self._backend_stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "tokens_saved": 0
        }
    
    def record_backend_cache_hit(self, tokens_saved: int = 0):
        """记录后端缓存命中"""
        self._backend_stats["cache_hits"] += 1
        self._backend_stats["tokens_saved"] += tokens_saved
    
    def record_backend_cache_miss(self):
        """记录后端缓存未命中"""
        self._backend_stats["cache_misses"] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0
        
        backend_total = self._backend_stats["cache_hits"] + self._backend_stats["cache_misses"]
        backend_hit_rate = self._backend_stats["cache_hits"] / backend_total if backend_total > 0 else 0
        
        return {
            "backend_type": self.backend_type.value,
            "local_cache": {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 3),
                "size": len(self._cache),
                "max_size": self.max_size,
                "ttl": self.ttl
            },
            "backend_cache": {
                "hits": self._backend_stats["cache_hits"],
                "misses": self._backend_stats["cache_misses"],
                "hit_rate": round(backend_hit_rate, 3),
                "tokens_saved": self._backend_stats["tokens_saved"]
            },
            "features": {
                "vllm_prefix_caching": self.vllm_prefix_caching if self.backend_type == BackendType.VLLM else None,
                "sglang_radix_cache": self.sglang_radix_cache if self.backend_type == BackendType.SGLANG else None,
                "lmdeploy_max_entries": self.lmdeploy_max_entries if self.backend_type == BackendType.LMDEPLOY else None
            }
        }
