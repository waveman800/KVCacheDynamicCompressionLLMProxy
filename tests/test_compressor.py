"""
测试压缩器
"""

import pytest
from compress_text_proxy.compressor import DynamicCompressor, CompressionResult


class TestDynamicCompressor:
    """测试动态压缩器"""
    
    @pytest.fixture
    def compressor(self):
        return DynamicCompressor()
    
    def test_compress_memories_empty(self, compressor):
        """测试空记忆列表"""
        result = compressor.compress_memories([], max_tokens=1000)
        assert result.content == []
        assert result.original_tokens == 0
        assert result.was_compressed == False
    
    def test_compress_memories_no_need(self, compressor):
        """测试不需要压缩的情况"""
        memories = ["短记忆1", "短记忆2"]
        result = compressor.compress_memories(memories, max_tokens=10000)
        assert result.was_compressed == False
        assert len(result.content) == 2
    
    def test_compress_memories_with_trimming(self, compressor):
        """测试需要压缩的情况"""
        # 生成大量记忆
        memories = [
            f"这是第{i}条记忆的详细内容，包含了很多用户信息和历史记录..."
            for i in range(50)
        ]
        
        result = compressor.compress_memories(memories, max_tokens=500)
        
        assert result.was_compressed == True
        assert result.compressed_tokens < result.original_tokens
        assert result.savings_percentage > 0
        assert len(result.content) < len(memories)
    
    def test_compress_chat_history(self, compressor):
        """测试压缩聊天历史"""
        history = []
        for i in range(20):
            history.append({"role": "user", "content": f"问题{i}" * 50})
            history.append({"role": "assistant", "content": f"回答{i}" * 50})
        
        result = compressor.compress_chat_history(history, max_tokens=1000)
        
        assert result.was_compressed == True
        assert len(result.content) < len(history)
    
    def test_importance_calculation(self, compressor):
        """测试重要性计算"""
        text = "这是重要结论，必须注意关键问题"
        score = compressor._calculate_importance(text, 0, 10, "")
        
        # 包含关键词的文本应该有更高分数
        assert score > 0.1
    
    def test_token_counter(self, compressor):
        """测试 Token 计数器"""
        text = "Hello world 你好世界"
        tokens = compressor.token_counter.count_tokens(text)
        
        # 应该有合理的估算
        assert tokens > 0
        assert tokens < len(text) * 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
