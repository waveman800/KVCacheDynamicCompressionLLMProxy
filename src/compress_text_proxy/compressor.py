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


class GranularityLevel:
    """压缩粒度级别"""
    FULL = "full"       # 整个记忆项
    PARAGRAPH = "paragraph"  # 按段落
    SENTENCE = "sentence"    # 按句子


class DynamicCompressor:
    """
    动态上下文压缩器
    
    核心算法：
    1. TF-IDF 重要性评分
    2. 关键词匹配
    3. 位置权重
    4. 相似度去重
    5. 细粒度段落/句子压缩
    """
    
    def __init__(
        self,
        session_len: int = 8192,
        similarity_threshold: float = 0.55,
        use_fast_mode: bool = False,
        granularity: str = "paragraph",
        min_keep_segments: int = 1,
        keyword_weight: float = 0.4,
        tfidf_weight: float = 0.3,
        position_weight: float = 0.2,
        query_weight: float = 0.1
    ):
        self.session_len = session_len
        self.similarity_threshold = similarity_threshold
        self.use_fast_mode = use_fast_mode
        self.granularity = granularity
        self.min_keep_segments = min_keep_segments
        self.token_counter = TokenCounter()
        
        # 权重配置（合并后：内容重要性 + 位置 + 查询）
        self.content_importance_weight = keyword_weight + tfidf_weight  # 兼容旧配置
        self.position_weight = position_weight
        self.query_weight = query_weight
        
        # 内容重要性内部比例：关键词 60% + TF-IDF 40%
        self._keyword_internal_ratio = 0.6
        self._tfidf_internal_ratio = 0.4
        
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
        压缩记忆列表（支持细粒度段落/句子压缩）
        
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
        
        # 细粒度模式：对每个记忆项内部进行段落/句子压缩
        if self.granularity in (GranularityLevel.PARAGRAPH, GranularityLevel.SENTENCE):
            return self._compress_memories_granular(memories, max_tokens, query, original_tokens, start_time)
        
        # 粗粒度模式：整个记忆项级别压缩
        return self._compress_memories_full(memories, max_tokens, query, original_tokens, start_time)
    
    def _compress_memories_full(
        self,
        memories: List[str],
        max_tokens: int,
        query: str,
        original_tokens: int,
        start_time: float
    ) -> CompressionResult:
        """完整记忆项级别压缩"""
        scored_memories = []
        for i, mem in enumerate(memories):
            score = self._calculate_importance(mem, i, len(memories), query)
            scored_memories.append((score, mem))
        
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        
        selected = []
        current_tokens = 0
        min_keep = min(3, len(scored_memories))
        
        for i in range(min_keep):
            mem = scored_memories[i][1]
            mem_tokens = self.token_counter.count_tokens(mem)
            selected.append(mem)
            current_tokens += mem_tokens
        
        for score, mem in scored_memories[min_keep:]:
            mem_tokens = self.token_counter.count_tokens(mem)
            if current_tokens + mem_tokens <= max_tokens:
                selected.append(mem)
                current_tokens += mem_tokens
            else:
                remaining = max_tokens - current_tokens
                if remaining > 50:
                    truncated = self._truncate_text_to_tokens(mem, remaining)
                    if truncated:
                        selected.append(truncated + "...")
                        current_tokens += self.token_counter.count_tokens(truncated)
                break
        
        selected_set = set(selected)
        result = [m for m in memories if m in selected_set]
        compressed_tokens = self.token_counter.count_tokens("\n\n".join(result))
        processing_time = (time.time() - start_time) * 1000
        ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0
        
        return CompressionResult(
            content=result,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            was_compressed=len(result) < len(memories) or compressed_tokens < original_tokens,
            processing_time_ms=processing_time,
            compression_ratio=ratio,
            savings_percentage=(1 - ratio) * 100
        )
    
    def _compress_memories_granular(
        self,
        memories: List[str],
        max_tokens: int,
        query: str,
        original_tokens: int,
        start_time: float
    ) -> CompressionResult:
        """细粒度段落/句子级别压缩"""
        memory_scores = []
        for i, mem in enumerate(memories):
            score = self._calculate_importance(mem, i, len(memories), query)
            mem_tokens = self.token_counter.count_tokens(mem)
            memory_scores.append({'text': mem, 'score': score, 'tokens': mem_tokens, 'index': i})
        
        memory_scores.sort(key=lambda x: x['score'], reverse=True)
        
        selected_memories = []
        current_tokens = 0
        total_segments_kept = 0
        
        for mem_info in memory_scores:
            if current_tokens >= max_tokens:
                break
            
            remaining_budget = max_tokens - current_tokens
            
            if mem_info['tokens'] <= remaining_budget:
                selected_memories.append(mem_info)
                current_tokens += mem_info['tokens']
            else:
                compressed_text, orig_tokens, comp_tokens = self._compress_text_granular(
                    mem_info['text'], remaining_budget, query
                )
                if comp_tokens > 0:
                    selected_memories.append({
                        'text': compressed_text,
                        'score': mem_info['score'],
                        'tokens': comp_tokens,
                        'index': mem_info['index'],
                        'compressed': True
                    })
                    current_tokens += comp_tokens
                    total_segments_kept += 1
        
        selected_memories.sort(key=lambda x: x['index'])
        result = [m['text'] for m in selected_memories]
        compressed_tokens = self.token_counter.count_tokens("\n\n".join(result))
        processing_time = (time.time() - start_time) * 1000
        ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0
        
        return CompressionResult(
            content=result,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            was_compressed=True,
            processing_time_ms=processing_time,
            compression_ratio=ratio,
            savings_percentage=(1 - ratio) * 100
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
    
    def _split_text(self, text: str) -> List[Tuple[str, int, int]]:
        """
        按粒度切分文本
        
        Returns:
            [(片段内容, 起始位置, 结束位置), ...]
        """
        if self.granularity == GranularityLevel.SENTENCE:
            # 按句子切分（支持中英文标点）
            pattern = r'[^。！？.!?]+[。！？.!?]*'
            matches = list(re.finditer(pattern, text))
            return [(m.group().strip(), m.start(), m.end()) for m in matches if m.group().strip()]
        
        elif self.granularity == GranularityLevel.PARAGRAPH:
            # 按段落切分（双换行或单换行）
            paragraphs = re.split(r'\n\n|\n', text)
            result = []
            pos = 0
            for para in paragraphs:
                para = para.strip()
                if para:
                    result.append((para, pos, pos + len(para)))
                    pos += len(para) + 2  # +2 for separator
            return result
        
        else:  # FULL
            return [(text, 0, len(text))]
    
    def _calculate_importance(
        self,
        text: str,
        position: int,
        total: int,
        query: str
    ) -> float:
        """
        计算文本重要性分数
        
        权重分配：
        - 内容重要性: CONTENT_IMPORTANCE_WEIGHT (默认0.7)
          └─ 内部: 关键词匹配 60% + TF-IDF 40%
        - 位置权重: POSITION_WEIGHT (默认0.2)
        - 查询相关性: QUERY_WEIGHT (默认0.1)
        """
        text_lower = text.lower()
        words = re.findall(r'\w+', text_lower)
        
        if not words:
            return 0.0
        
        # 1. 内容重要性评分 (合并关键词 + TF-IDF)
        # 1.1 关键词匹配分数 (内部占60%)
        keyword_matches = sum(1 for kw in self.keywords if kw.lower() in text_lower)
        keyword_score = min(keyword_matches / 3, 1.0) * self._keyword_internal_ratio
        
        # 1.2 TF-IDF 分数 (内部占40%)
        word_count = Counter(words)
        if word_count:
            max_tf = max(word_count.values())
            tfidf_score = (max_tf / len(words)) * 0.5 * self._tfidf_internal_ratio
        else:
            tfidf_score = 0
        
        # 合并内容重要性
        content_score = (keyword_score + tfidf_score) * self.content_importance_weight
        
        # 2. 位置权重（开头和结尾更重要）
        normalized_pos = position / max(total - 1, 1)
        position_factor = 0.7 + 0.3 * (1 - abs(normalized_pos - 0.5) * 2)
        position_score = position_factor * self.position_weight
        
        # 3. 查询相关性
        if query:
            query_words = set(re.findall(r'\w+', query.lower()))
            text_word_set = set(words)
            overlap = len(query_words & text_word_set)
            query_score = (overlap / max(len(query_words), 1)) * self.query_weight
        else:
            query_score = self.query_weight * 0.5  # 无查询时给一半基础分
        
        return content_score + position_score + query_score
    
    def _compress_text_granular(
        self,
        text: str,
        max_tokens: int,
        query: str
    ) -> Tuple[str, int, int]:
        """
        细粒度压缩文本
        
        Returns:
            (压缩后文本, 原始tokens, 压缩后tokens)
        """
        original_tokens = self.token_counter.count_tokens(text)
        
        if original_tokens <= max_tokens:
            return text, original_tokens, original_tokens
        
        # 切分文本
        segments = self._split_text(text)
        if len(segments) <= self.min_keep_segments:
            # 片段太少，直接截断
            return self._truncate_text_to_tokens(text, max_tokens), original_tokens, max_tokens
        
        # 计算每个片段的重要性
        scored_segments = []
        for i, (seg_text, start, end) in enumerate(segments):
            score = self._calculate_importance(seg_text, i, len(segments), query)
            seg_tokens = self.token_counter.count_tokens(seg_text)
            scored_segments.append({
                'text': seg_text,
                'score': score,
                'tokens': seg_tokens,
                'position': i
            })
        
        # 按重要性排序
        scored_segments.sort(key=lambda x: x['score'], reverse=True)
        
        # 优先保留最重要的 min_keep_segments 个
        selected = scored_segments[:self.min_keep_segments]
        current_tokens = sum(s['tokens'] for s in selected)
        
        # 继续添加其他高分片段
        remaining_budget = max_tokens - current_tokens
        for seg in scored_segments[self.min_keep_segments:]:
            if remaining_budget <= 0:
                break
            
            if seg['tokens'] <= remaining_budget:
                selected.append(seg)
                remaining_budget -= seg['tokens']
            else:
                # 尝试部分保留（仅句子粒度）
                if self.granularity == GranularityLevel.SENTENCE and remaining_budget > 20:
                    truncated = self._truncate_text_to_tokens(seg['text'], remaining_budget)
                    if truncated:
                        selected.append({
                            'text': truncated,
                            'score': seg['score'],
                            'tokens': self.token_counter.count_tokens(truncated),
                            'position': seg['position']
                        })
                break
        
        # 按原始位置排序，恢复文本顺序
        selected.sort(key=lambda x: x['position'])
        
        # 组合结果
        result_text = ' '.join(s['text'] for s in selected)
        compressed_tokens = self.token_counter.count_tokens(result_text)
        
        return result_text, original_tokens, compressed_tokens
    
    def _truncate_text_to_tokens(self, text: str, max_tokens: int) -> str:
        """将文本截断到指定token数"""
        max_chars = int(max_tokens * 3)  # 粗略估算
        
        if len(text) <= max_chars:
            return text
        
        truncated = text[:max_chars]
        # 在句子边界截断
        for punct in ['。', '！', '？', '.', '!', '?', '\n']:
            idx = truncated.rfind(punct)
            if idx > max_chars * 0.6:  # 至少保留60%
                return truncated[:idx + 1]
        
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
