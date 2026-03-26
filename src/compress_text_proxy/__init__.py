"""
KVCache+动态压缩大模型代理服务 - LLM 文本压缩代理服务

通过智能压缩算法降低 LLM 调用的 Token 成本 40-85%，
同时支持 KV Cache 优化以加速推理。

Usage:
    from compress_text_proxy import CompressionProxy, ProxyConfig
    
    config = ProxyConfig(
        target_url="https://api.openai.com/v1",
        api_key="your-api-key"
    )
    
    proxy = CompressionProxy(config)
    result = await proxy.process_request(messages, memories)
"""

__version__ = "1.0.0"
__author__ = "MemOS Team"

from .proxy import CompressionProxy, ProxyConfig, ProxyResult
from .compressor import DynamicCompressor, CompressionResult
from .cache import KVCacheManager, BackendType
from .metrics import MetricsCollector

__all__ = [
    "CompressionProxy",
    "ProxyConfig",
    "ProxyResult",
    "DynamicCompressor",
    "CompressionResult",
    "KVCacheManager",
    "BackendType",
    "MetricsCollector",
]
