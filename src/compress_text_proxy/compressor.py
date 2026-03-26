"""
动态文本压缩器

基于 TF-IDF、关键词匹配和位置权重的智能压缩算法
"""

import re
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import Counter


@dataclass
class CompressionResult:
    """压缩结果"""
    content: Any
    original_tokens: int
    compressed_tokens: int
    was_compressed: bool
    processing_time_ms: float
    compression_ratio: float
    savings_percentage: float


class TokenCounter:
    """简单的 Token 计数器（不依赖 tiktoken）"""
    
    def count_tokens(self, text: str) -> int:
        """
        估算 token 数
        中文：1 字符 ≈ 1 token
        英文：1 单词 ≈ 1.3 tokens
        """
        if not text:
            return 0
        
        # 中文字符
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        # 英文单词
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        # 其他字符
        other_chars = len(text) - chinese_chars - sum(len(w) for w in re.findall(r'[a-zA-Z]+', text))
        
        # 估算：中文 1:1，英文 1:1.3，其他 1:0.5
        estimated = int(chinese_chars + english_words * 1.3 + other_chars * 0.5)
        return max(estimated, len(text) // 4)  # 保底计算
    
    def count_tokens_messages(self, messages: List[Dict[str, str]]) -> int:
        """计算消息列表的 token 数"""
        total = 0
        for msg in messages:
            total += self.count_tokens(msg.get("content", ""))
            total += 4  # 角色和格式的开销
        return total


class DynamicCompressor:
    """
    动态上下文压缩器
    
    核心算法：
    1. TF-IDF 重要性评分
    2. 关键词匹配
    3. 位置权重
    4. 相似度去重
    """
    
    def __init__(
        self,
        session_len: int = 8192,
        similarity_threshold: float = 0.55,
        use_fast_mode: bool = False
    ):
        self.session_len = session_len
        self.similarity_threshold = similarity_threshold
        self.use_fast_mode = use_fast_mode
        self.token_counter = TokenCounter()
        
        # 关键词列表
        self.keywords = [
            "结论", "总结", "因此", "所以", "重要", "关键", "注意",
            "必须", "需要", "建议", "方案", "解决", "结果", "发现",
            "问题", "原因", "措施", "目标", "计划", "步骤", "实现",
            "important", "key", "note", "must", "need", "should", "suggest",
            "result", "find", "problem", "reason", "solution", "goal", "plan"
        ]
    
    def compress_memories(
        self,
        memories: List[str],
        max_tokens: int = 1500,
        query: str = ""
    ) -> CompressionResult:
        """
        压缩记忆列表
        
        Args:
            memories: 记忆列表
            max_tokens: 最大 token 数
            query: 当前查询（用于相关性排序）
            
        Returns:
            CompressionResult: 压缩结果
        """
        start_time = time.time()
        
        if not memories:
            return CompressionResult([], 0, 0, False, 0.0, 1.0, 0.0)
        
        # 计算原始 token
        original_text = "\n\n".join(memories)
        original_tokens = self.token_counter.count_tokens(original_text)
        
        # 如果不需要压缩
        if original_tokens <= max_tokens or len(memories) <= 3:
            return CompressionResult(
                memories, original_tokens, original_tokens, False, 0.0, 1.0, 0.0
            )
        
        # 计算每个记忆的重要性
        scored_memories = []
        for i, mem in enumerate(memories):
            score = self._calculate_importance(mem, i, len(memories), query)
            scored_memories.append((score, mem))
        
        # 按重要性排序
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        
        # 选择最重要的记忆，直到达到 token 限制
        selected = []
        current_tokens = 0
        
        # 首先保留最重要的 min_keep 个
        min_keep = min(3, len(scored_memories))
        for i in range(min_keep):
            mem = scored_memories[i][1]
            mem_tokens = self.token_counter.count_tokens(mem)
            selected.append(mem)
            current_tokens += mem_tokens
        
        # 然后按重要性添加其他记忆
        for score, mem in scored_memories[min_keep:]:
            mem_tokens = self.token_counter.count_tokens(mem)
            if current_tokens + mem_tokens <= max_tokens:
                selected.append(mem)
                current_tokens += mem_tokens
            else:
                # 尝试截断
                remaining = max_tokens - current_tokens
                if remaining > 50:  # 至少还能加 50 tokens
                    truncated = self._truncate_text(mem, remaining)
                    if truncated:
                        selected.append(truncated + "...")
                        current_tokens += self.token_counter.count_tokens(truncated)
                break
        
        # 恢复原始顺序
        selected_set = set(selected)
        result = [m for m in memories if m in selected_set]
        
        compressed_tokens = self.token_counter.count_tokens("\n\n".join(result))
        processing_time = (time.time() - start_time) * 1000
        
        ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0
        savings = (1 - ratio) * 100
        
        return CompressionResult(
            content=result,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            was_compressed=len(result) < len(memories) or compressed_tokens < original_tokens,
            processing_time_ms=processing_time,
            compression_ratio=ratio,
            savings_percentage=savings
        )
    
    def compress_chat_history(
        self,
        chat_history: List[Dict[str, str]],
        max_tokens: int = 1500,
        keep_last_n: int = 4
    ) -> CompressionResult:
        """
        压缩聊天历史
        
        策略：
        1. 保留最近 N 轮完整对话
        2. 更早的对话进行摘要
        """
        start_time = time.time()
        
        if not chat_history:
            return CompressionResult([], 0, 0, False, 0.0, 1.0, 0.0)
        
        # 计算原始 token
        original_tokens = self.token_counter.count_tokens_messages(chat_history)
        
        if original_tokens <= max_tokens:
            return CompressionResult(
                chat_history, original_tokens, original_tokens, False, 0.0, 1.0, 0.0
            )
        
        # 保留最近 N 轮
        total_turns = len(chat_history) // 2
        keep_messages = min(keep_last_n * 2, len(chat_history))
        recent = chat_history[-keep_messages:]
        
        # 对更早的对话进行摘要
        if len(chat_history) > keep_messages:
            older = chat_history[:-keep_messages]
            summary = self._summarize_history(older)
            
            if summary:
                result = [{"role": "system", "content": f"[历史对话摘要] {summary}"}] + recent
            else:
                result = recent
        else:
            result = recent
        
        compressed_tokens = self.token_counter.count_tokens_messages(result)
        processing_time = (time.time() - start_time) * 1000
        
        ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0
        savings = (1 - ratio) * 100
        
        return CompressionResult(
            content=result,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            was_compressed=len(result) < len(chat_history),
            processing_time_ms=processing_time,
            compression_ratio=ratio,
            savings_percentage=savings
        )
    
    def _calculate_importance(
        self,
        text: str,
        position: int,
        total: int,
        query: str
    ) -> float:
        """计算文本重要性分数"""
        text_lower = text.lower()
        words = re.findall(r'\w+', text_lower)
        
        if not words:
            return 0.0
        
        # 1. 关键词匹配分数 (40%)
        keyword_matches = sum(1 for kw in self.keywords if kw.lower() in text_lower)
        keyword_score = min(keyword_matches / 3, 1.0) * 0.4
        
        # 2. TF-IDF 分数 (30%)
        word_count = Counter(words)
        if word_count:
            max_tf = max(word_count.values())
            tf_score = (max_tf / len(words)) * 0.5 * 0.3
        else:
            tf_score = 0
        
        # 3. 位置权重 (20%)
        # 开头和结尾更重要
        normalized_pos = position / max(total - 1, 1)
        position_weight = 0.7 + 0.3 * (1 - abs(normalized_pos - 0.5) * 2)
        position_score = position_weight * 0.2
        
        # 4. 查询相关性 (10%)
        if query:
            query_words = set(re.findall(r'\w+', query.lower()))
            text_word_set = set(words)
            overlap = len(query_words & text_word_set)
            query_score = (overlap / max(len(query_words), 1)) * 0.1
        else:
            query_score = 0.05
        
        return keyword_score + tf_score + position_score + query_score
    
    def _truncate_text(self, text: str, max_tokens: int) -> str:
        """截断文本到指定 token 数"""
        # 简单估算：1 token ≈ 4 字符（中文）或 1 单词（英文）
        max_chars = max_tokens * 3
        
        if len(text) <= max_chars:
            return text
        
        # 在句子边界截断
        truncated = text[:max_chars]
        last_period = truncated.rfind('。')
        last_newline = truncated.rfind('\n')
        
        cut_point = max(last_period, last_newline)
        if cut_point > max_chars * 0.7:
            return truncated[:cut_point + 1]
        
        return truncated
    
    def _summarize_history(self, history: List[Dict[str, str]]) -> str:
        """摘要历史对话"""
        # 提取关键信息
        topics = []
        user_queries = [msg["content"] for msg in history if msg["role"] == "user"]
        
        if user_queries:
            # 简单摘要：主题 + 轮数
            total_turns = len(history) // 2
            first_topic = user_queries[0][:30] if user_queries[0] else ""
            return f"之前讨论了 {total_turns} 轮，涉及: {first_topic}...等话题"
        
        return ""
