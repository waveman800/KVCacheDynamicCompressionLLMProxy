"""
基础使用示例
"""

import asyncio
from compress_text_proxy import CompressionProxy, ProxyConfig


async def basic_example():
    """基础示例"""
    print("=" * 60)
    print("基础使用示例")
    print("=" * 60)
    
    # 创建配置
    config = ProxyConfig(
        target_url="https://api.openai.com/v1",
        api_key="your-api-key-here",  # 替换为你的 API Key
        enable_compression=True,
        memories_target_tokens=1500,
        history_target_tokens=1000,
    )
    
    # 创建代理
    async with CompressionProxy(config) as proxy:
        # 准备消息
        messages = [
            {"role": "system", "content": "你是一个有帮助的助手"},
            {"role": "user", "content": "你好，请介绍一下自己"}
        ]
        
        # 处理请求
        result = await proxy.process_request(messages)
        
        if result.success:
            print(f"✅ 请求处理成功")
            print(f"处理时间: {result.processing_time_ms:.2f}ms")
            
            if result.compression_info:
                info = result.compression_info
                print(f"\n压缩统计:")
                print(f"  原始 tokens: {info.get('total_original_tokens', 0)}")
                print(f"  压缩后: {info.get('total_compressed_tokens', 0)}")
                print(f"  节省: {info.get('total_savings_percentage', 0):.1f}%")
        else:
            print(f"❌ 处理失败: {result.error}")


async def compression_example():
    """压缩效果示例"""
    print("\n" + "=" * 60)
    print("压缩效果示例")
    print("=" * 60)
    
    config = ProxyConfig(
        target_url="https://api.openai.com/v1",
        enable_compression=True
    )
    
    async with CompressionProxy(config) as proxy:
        # 生成大量测试数据
        memories = [
            f"记忆{i}: 用户的项目使用 Python 开发，基于 FastAPI 框架，"
            f"数据库使用 PostgreSQL，部署在 AWS 上..."
            for i in range(30)
        ]
        
        chat_history = []
        for i in range(20):
            chat_history.append({"role": "user", "content": f"问题{i}: 如何优化性能？"})
            chat_history.append({"role": "assistant", "content": f"回答{i}: 建议从以下几个方面优化..."})
        
        messages = [
            {"role": "system", "content": "基于用户的历史记录回答问题"},
            *chat_history,
            {"role": "user", "content": "总结一下之前的建议"}
        ]
        
        # 处理请求
        result = await proxy.process_request(
            messages=messages,
            memories=memories,
            user_id="user_123"
        )
        
        if result.compression_info:
            info = result.compression_info
            print(f"\n压缩效果:")
            print(f"  Memories: {info['original_memories_count']} → "
                  f"{len(result.compression_info.get('compressed_memories', memories))} 条")
            print(f"  History: {info['original_history_turns']} → "
                  f"{len(result.compression_info.get('compressed_history', chat_history))//2} 轮")
            print(f"  Tokens: {info['total_original_tokens']} → {info['total_compressed_tokens']}")
            print(f"  节省: {info['total_savings_percentage']:.1f}%")
            print(f"  处理时间: {result.processing_time_ms:.2f}ms")


async def metrics_example():
    """指标查看示例"""
    print("\n" + "=" * 60)
    print("指标查看示例")
    print("=" * 60)
    
    config = ProxyConfig(
        target_url="https://api.openai.com/v1",
        enable_compression=True
    )
    
    async with CompressionProxy(config) as proxy:
        # 模拟多个请求
        for i in range(10):
            await proxy.process_request([
                {"role": "user", "content": f"测试消息{i}"}
            ])
        
        # 获取指标
        metrics = proxy.get_metrics()
        
        print(f"\n统计指标:")
        print(f"  总请求: {metrics['total_requests']}")
        print(f"  节省 tokens: {metrics['total_tokens_saved']:,}")
        print(f"  平均节省: {metrics['avg_savings_percentage']:.1f}%")
        print(f"  平均处理时间: {metrics['avg_processing_time_ms']:.2f}ms")
        print(f"  运行时间: {metrics['uptime_seconds']:.0f}秒")


async def main():
    """主函数"""
    try:
        await basic_example()
        await compression_example()
        await metrics_example()
    except Exception as e:
        print(f"\n错误: {e}")
        print("提示: 请确保设置了正确的 API_KEY")


if __name__ == "__main__":
    asyncio.run(main())
