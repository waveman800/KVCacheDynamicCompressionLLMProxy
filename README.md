# KVCache+动态压缩大模型代理服务

> LLM 文本压缩代理服务 - 降低 Token 成本 40-85%

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🎯 项目简介

KVCache+动态压缩大模型代理服务是一个透明的 LLM 请求代理服务，通过智能压缩算法自动减少请求中的 Token 数量，从而大幅降低 API 调用成本，同时支持 KV Cache 优化以加速推理。

### 核心特性

- 🔌 **透明代理**：完全兼容 OpenAI API 格式，客户端无需修改
- 🗜️ **智能压缩**：基于 TF-IDF、关键词匹配和位置权重的动态压缩
- 📏 **细粒度压缩**：支持段落级、句子级压缩，精准保留重要内容
- 🚀 **高性能**：异步处理，支持流式响应，延迟 < 10ms
- 📊 **可观测**：内置 Prometheus 指标和详细统计
- 🔥 **KV Cache**：智能缓存，加速多轮对话
- 🐳 **Docker 部署**：完整的环境变量配置，一键启动

---

## 📊 效果对比

| 场景 | 原始 Token | 压缩后 | 节省 | 月成本(10k请求) |
|------|-----------|--------|------|-----------------|
| 长对话(30轮) | 8,964 | 2,497 | **72%** | $749 (省 $1,940) |
| 文档问答 | 5,500 | 2,200 | **60%** | $660 (省 $990) |
| 客服机器人 | 4,200 | 1,260 | **70%** | $378 (省 $882) |

---

## 🚀 快速开始

### Docker 部署（推荐）

```bash
# 1. 复制环境变量模板
cp .env.example .env

# 2. 编辑 .env 文件，设置 API_KEY 和 TARGET_URL
vim .env

# 3. 启动服务
docker-compose up -d
```

### 安装

```bash
pip install kvcache-dynamic-compression-llm-proxy
```

### 启动服务

```bash
# 设置环境变量
export API_KEY="your-openai-api-key"
export TARGET_URL="https://api.openai.com/v1"

# 启动
kvcache-proxy
```

### 客户端使用

只需修改 `base_url`，其他代码完全不变：

```python
import openai

client = openai.OpenAI(
    api_key="your-api-key",
    base_url="http://localhost:8000/v1"  # 指向代理
)

# 正常使用
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "你好"}]
)

# 查看压缩效果
if hasattr(response, 'compression'):
    print(f"节省了 {response.compression.savings_percentage}% tokens")
```

---

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                        客户端                                    │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│        KVCache+动态压缩大模型代理服务                             │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │  请求接收    │───▶│  智能压缩    │───▶│  转发后端    │         │
│  │  (FastAPI)  │    │(段落/句子)  │    │  (HTTP)     │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│                            │                                     │
│                            ▼                                     │
│         ┌──────────────────────────────────────┐                │
│         │         智能 KV Cache                 │                │
│         │  ├─ 内存压缩（节省50-70%）            │                │
│         │  ├─ 热点常驻（命中率+15-30%）         │                │
│         │  └─ 自适应 TTL（智能过期）            │                │
│         └──────────────────────────────────────┘                │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│              任意 OpenAI 兼容的后端服务                           │
│         (OpenAI / vLLM / SGLang / LMDeploy / 等)                │
└─────────────────────────────────────────────────────────────────┘
```

---

## ⚙️ 配置选项

### 环境变量

#### OpenAI 协议三要素（必填）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `API_KEY` | 大模型 API 密钥 | 必填 |
| `TARGET_URL` / `BASE_URL` | 目标服务地址 | `https://api.openai.com/v1` |
| `MODEL` | 默认模型名称 | `gpt-4o-mini` |

#### 压缩配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ENABLE_COMPRESSION` | 启用压缩 | `true` |
| `MEMORIES_TARGET` | 记忆压缩目标 tokens | `1500` |
| `HISTORY_TARGET` | 历史压缩目标 tokens | `1000` |
| `HISTORY_KEEP_LAST_N` | 历史对话保留轮数 | `4` |

#### 细粒度压缩参数

| 变量 | 说明 | 默认值 | 可选值 |
|------|------|--------|--------|
| `COMPRESSION_GRANULARITY` | 压缩粒度 | `paragraph` | `full`/`paragraph`/`sentence` |
| `MIN_KEEP_SEGMENTS` | 最少保留片段数 | `1` | ≥1 |
| `CONTENT_IMPORTANCE_WEIGHT` | 内容重要性权重 | `0.7` | 0.0-1.0 |
| `POSITION_WEIGHT` | 位置权重 | `0.2` | 0.0-1.0 |
| `QUERY_WEIGHT` | 查询相关性权重 | `0.1` | 0.0-1.0 |

**压缩粒度说明：**
- `full`：整个记忆项级别压缩（最快，压缩率较低）
- `paragraph`：按段落压缩（推荐，平衡速度和质量）
- `sentence`：按句子压缩（最慢，压缩率最高）

**重要性评分权重公式：**
```
总重要性 = 内容重要性×0.7 + 位置×0.2 + 查询×0.1

内容重要性内部：
├── 关键词匹配: 0.7 × 0.6 = 0.42 (42%)
└── TF-IDF统计: 0.7 × 0.4 = 0.28 (28%)
```

#### 动态压缩算法参数

| 变量 | 说明 | 默认值 | 范围 |
|------|------|--------|------|
| `SIMILARITY_THRESHOLD` | 相似度阈值（值越高压缩越严格） | `0.55` | 0.0-1.0 |
| `SESSION_LEN` | 会话长度限制 | `8192` | - |
| `USE_FAST_MODE` | 快速压缩模式（牺牲压缩率换速度） | `false` | true/false |

#### KV Cache 配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ENABLE_KV_CACHE` | 启用 KV Cache | `true` |
| `KV_CACHE_SIZE` | 缓存最大条目数 | `2000` |
| `KV_CACHE_TTL` | 缓存过期时间（秒） | `3600` |
| `KV_CACHE_COMPRESSION` | 启用内存压缩 | `true` |
| `KV_CACHE_COMPRESSION_THRESHOLD` | 压缩阈值（字节） | `1024` |
| `KV_CACHE_HOT_RATIO` | 热点数据常驻比例 | `0.2` |
| `KV_CACHE_ADAPTIVE_TTL` | 自适应 TTL | `true` |
| `KV_CACHE_MIN_TTL` | 最小 TTL（秒） | `300` |
| `KV_CACHE_MAX_TTL` | 最大 TTL（秒） | `7200` |

**优化策略说明：**
1. **内存压缩**：对冷数据启用 gzip 压缩，内存占用降低 50-70%
2. **热点常驻**：高频访问数据（20%）保留在内存，命中率提升 15-30%
3. **自适应 TTL**：根据命中率动态调整过期时间

#### 服务配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HOST` | 监听地址 | `0.0.0.0` |
| `PORT` | 监听端口 | `8000` |

---

## 🐳 Docker 部署

### 快速启动

```bash
# 1. 复制环境变量模板
cp .env.example .env

# 2. 编辑 .env 文件，设置你的 API_KEY
vim .env

# 3. 启动服务
docker-compose up -d
```

### Docker 命令行部署

```bash
# 构建镜像
docker build -t kvcache-proxy .

# 运行（带完整环境变量）
docker run -d \
  --name kvcache-proxy \
  -p 8000:8000 \
  -e API_KEY="your-api-key" \
  -e TARGET_URL="https://api.openai.com/v1" \
  -e MODEL="gpt-4o-mini" \
  -e ENABLE_COMPRESSION="true" \
  -e MEMORIES_TARGET="1500" \
  -e HISTORY_TARGET="1000" \
  -e COMPRESSION_GRANULARITY="paragraph" \
  -e CONTENT_IMPORTANCE_WEIGHT="0.7" \
  -e ENABLE_KV_CACHE="true" \
  -e KV_CACHE_COMPRESSION="true" \
  kvcache-proxy
```

### Docker Compose

```yaml
version: '3.8'
services:
  proxy:
    build: .
    ports:
      - "8000:8000"
    environment:
      # OpenAI 协议三要素
      - API_KEY=${API_KEY}
      - TARGET_URL=${TARGET_URL:-https://api.openai.com/v1}
      - MODEL=${MODEL:-gpt-4o-mini}
      
      # 压缩配置
      - ENABLE_COMPRESSION=${ENABLE_COMPRESSION:-true}
      - MEMORIES_TARGET=${MEMORIES_TARGET:-1500}
      - HISTORY_TARGET=${HISTORY_TARGET:-1000}
      - HISTORY_KEEP_LAST_N=${HISTORY_KEEP_LAST_N:-4}
      
      # 细粒度压缩
      - COMPRESSION_GRANULARITY=${COMPRESSION_GRANULARITY:-paragraph}
      - CONTENT_IMPORTANCE_WEIGHT=${CONTENT_IMPORTANCE_WEIGHT:-0.7}
      - POSITION_WEIGHT=${POSITION_WEIGHT:-0.2}
      - QUERY_WEIGHT=${QUERY_WEIGHT:-0.1}
      
      # KV Cache 配置
      - ENABLE_KV_CACHE=${ENABLE_KV_CACHE:-true}
      - KV_CACHE_SIZE=${KV_CACHE_SIZE:-2000}
      - KV_CACHE_COMPRESSION=${KV_CACHE_COMPRESSION:-true}
      - KV_CACHE_HOT_RATIO=${KV_CACHE_HOT_RATIO:-0.2}
```

---

## 📡 API 接口

### 聊天补全

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "system", "content": "你是助手"},
      {"role": "user", "content": "你好"}
    ],
    "memories": ["用户喜欢Python", "用户是开发者"]
  }'
```

### 健康检查

```bash
curl http://localhost:8000/health
```

### 查看指标

```bash
curl http://localhost:8000/metrics
```

**响应示例**：

```json
{
  "total_requests": 1000,
  "total_tokens_saved": 450000,
  "avg_savings_percentage": 68.5,
  "avg_processing_time_ms": 8.2,
  "cache_hit_rate": 0.72,
  "uptime_seconds": 3600
}
```

---

## 📈 监控

### Prometheus 指标

服务暴露以下指标：

- `compression_requests_total` - 总请求数
- `compression_ratio` - 平均压缩比
- `tokens_saved_total` - 累计节省 tokens
- `cache_hit_rate` - KV Cache 命中率
- `processing_time_ms` - 处理延迟

---

## 🧪 测试

```bash
# 运行测试
pytest tests/

# 测试覆盖率
pytest --cov=compress_text_proxy tests/
```

---

## 📝 使用示例

### 基础示例

```python
import asyncio
from compress_text_proxy import CompressionProxy, ProxyConfig

async def main():
    config = ProxyConfig(
        target_url="https://api.openai.com/v1",
        api_key="your-api-key"
    )
    
    async with CompressionProxy(config) as proxy:
        messages = [
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "你好"}
        ]
        
        memories = ["用户喜欢Python", "用户是开发者"]
        
        result = await proxy.process_request(
            messages=messages,
            memories=memories
        )
        
        print(f"压缩节省: {result.compression_info['total_savings_percentage']:.1f}%")

asyncio.run(main())
```

### LangChain 集成

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4",
    openai_api_key="your-api-key",
    openai_api_base="http://localhost:8000/v1"
)

response = llm.invoke("你好")
```

---

## 📁 项目结构

```
KVCacheDynamicCompressionLLMProxy/
├── src/compress_text_proxy/       # 核心代码
│   ├── __init__.py
│   ├── proxy.py                   # 代理核心
│   ├── compressor.py              # 压缩算法
│   ├── cache.py                   # KV Cache
│   ├── metrics.py                 # 指标收集
│   └── server.py                  # FastAPI 服务
│
├── tests/                         # 测试
├── deploy/                        # 部署配置
├── examples/                      # 使用示例
├── docs/                          # 文档
├── README.md                      # 本文件
├── pyproject.toml                 # 项目配置
├── Dockerfile                     # Docker 构建
├── docker-compose.yml             # Docker Compose
└── .env.example                   # 环境变量示例
```

---

## 🤝 贡献

欢迎提交 Issue 和 PR！

---

## 📄 License

MIT License

---

**通过 KVCache+动态压缩大模型代理服务，无需修改现有代码即可享受 40-85% 的 Token 成本节省！**
