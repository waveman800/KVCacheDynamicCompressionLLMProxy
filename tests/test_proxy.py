"""
测试代理
"""

import pytest
from compress_text_proxy.proxy import CompressionProxy, ProxyConfig


class TestCompressionProxy:
    """测试压缩代理"""
    
    @pytest.fixture
    async def proxy(self):
        config = ProxyConfig(
            target_url="https://api.openai.com/v1",
            api_key="test-key",
            enable_compression=True
        )
        proxy = CompressionProxy(config)
        yield proxy
        await proxy.close()
    
    @pytest.mark.asyncio
    async def test_process_request_basic(self, proxy):
        """测试基本请求处理"""
        messages = [
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "你好"}
        ]
        
        result = await proxy.process_request(messages)
        
        assert result.success == True
        assert result.backend_request is not None
        assert "messages" in result.backend_request
    
    @pytest.mark.asyncio
    async def test_process_request_with_memories(self, proxy):
        """测试带记忆的请求"""
        messages = [
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "你好"}
        ]
        memories = [f"记忆{i}的内容" for i in range(20)]
        
        result = await proxy.process_request(
            messages=messages,
            memories=memories
        )
        
        assert result.success == True
        assert result.compression_info is not None
        assert result.compression_info["original_memories_count"] == 20
    
    @pytest.mark.asyncio
    async def test_metrics_collection(self, proxy):
        """测试指标收集"""
        # 处理几个请求
        for i in range(5):
            await proxy.process_request([
                {"role": "user", "content": f"测试{i}"}
            ])
        
        metrics = proxy.get_metrics()
        
        assert metrics["total_requests"] == 5
        assert "avg_savings_percentage" in metrics
    
    @pytest.mark.asyncio
    async def test_disabled_compression(self):
        """测试禁用压缩"""
        config = ProxyConfig(
            target_url="https://api.openai.com/v1",
            enable_compression=False
        )
        proxy = CompressionProxy(config)
        
        messages = [{"role": "user", "content": "你好"}]
        result = await proxy.process_request(messages)
        
        assert result.compression_info is None
        
        await proxy.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
