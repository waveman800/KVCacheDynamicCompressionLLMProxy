"""
指标收集器

收集和统计压缩相关的性能指标
"""

import time
from typing import Dict, Any, List
from dataclasses import dataclass, field
from collections import deque


@dataclass
class CompressionMetrics:
    """单次压缩指标"""
    timestamp: float
    original_tokens: int
    compressed_tokens: int
    savings_percentage: float
    processing_time_ms: float
    cache_hit: bool = False


class MetricsCollector:
    """
    指标收集器
    
    收集压缩相关的统计数据
    """
    
    def __init__(self, max_history: int = 10000):
        self.max_history = max_history
        self._history: deque = deque(maxlen=max_history)
        self._total_requests = 0
        self._total_tokens_saved = 0
        self._start_time = time.time()
    
    def record_compression(self, info: Dict[str, Any]):
        """记录压缩事件"""
        self._total_requests += 1
        
        original = info.get("total_original_tokens", 0)
        compressed = info.get("total_compressed_tokens", 0)
        saved = original - compressed
        
        self._total_tokens_saved += saved
        
        metric = CompressionMetrics(
            timestamp=time.time(),
            original_tokens=original,
            compressed_tokens=compressed,
            savings_percentage=info.get("total_savings_percentage", 0),
            processing_time_ms=info.get("processing_time_ms", 0),
            cache_hit=info.get("cache_hit", False)
        )
        
        self._history.append(metric)
    
    def get_summary(self) -> Dict[str, Any]:
        """获取统计摘要"""
        if not self._history:
            return {
                "total_requests": 0,
                "total_tokens_saved": 0,
                "avg_savings_percentage": 0,
                "avg_processing_time_ms": 0,
                "cache_hit_rate": 0,
                "uptime_seconds": time.time() - self._start_time
            }
        
        recent = list(self._history)
        
        total_savings = sum(m.savings_percentage for m in recent)
        total_time = sum(m.processing_time_ms for m in recent)
        cache_hits = sum(1 for m in recent if m.cache_hit)
        
        return {
            "total_requests": self._total_requests,
            "total_tokens_saved": self._total_tokens_saved,
            "avg_savings_percentage": round(total_savings / len(recent), 2),
            "avg_processing_time_ms": round(total_time / len(recent), 2),
            "cache_hit_rate": round(cache_hits / len(recent), 3),
            "uptime_seconds": round(time.time() - self._start_time, 0),
            "recent_requests": len(recent)
        }
    
    def get_recent(self, n: int = 100) -> List[Dict[str, Any]]:
        """获取最近的指标"""
        recent = list(self._history)[-n:]
        return [
            {
                "timestamp": m.timestamp,
                "original_tokens": m.original_tokens,
                "compressed_tokens": m.compressed_tokens,
                "savings_percentage": m.savings_percentage,
                "processing_time_ms": m.processing_time_ms,
                "cache_hit": m.cache_hit
            }
            for m in recent
        ]
    
    def reset(self):
        """重置统计"""
        self._history.clear()
        self._total_requests = 0
        self._total_tokens_saved = 0
        self._start_time = time.time()
