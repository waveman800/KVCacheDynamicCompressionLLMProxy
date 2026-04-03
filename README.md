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
- 🚀 **高性能**：异步处理，支持流式响应，延迟 < 10ms
- 🏢 **多租户**：支持多个应用的独立配置
- 📊 **可观测**：内置 Prometheus 指标和详细统计
- 🔥 **KV Cache**：静态前缀缓存，加速多轮对话

---

## 📊 效果对比

| 场景 | 原始 Token | 压缩后 | 节省 | 月成本(10k请求) |
|------|-----------|--------|------|-----------------|
| 长对话(30轮) | 8,964 | 2,497 | **72%** | $749 (省 $1,940) |
| 文档问答 | 5,500 | 2,200 | **60%** | $660 (省 $990) |
| 客服机器人 | 4,200 | 1,260 | **70%** | $378 (省 $882) |

---

## 🚀 快速开始

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

或使用 Python：

```python
from compress_text_proxy import CompressionProxy, ProxyConfig

config = ProxyConfig(
    target_url="https://api.openai.com/v1",
    api_key="your-api-key"
)

proxy = CompressionProxy(config)
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
│  │  请求接收    │───▶│  智能压缩    │───▶│  适配后端    │         │
│  │  (FastAPI)  │    │  (TF-IDF)   │    │  (HTTP)     │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│                            │                                     │
│                            ▼                                     │
│         ┌──────────────────────────────────────┐                │
│         │         多后端 KV Cache               │                │
│         ├──────────┬──────────┬──────────┬─────┤                │
│         │  OpenAI  │   vLLM   │  SGLang  │ LMDeploy            │
│         │ (客户端) │ (Prefix) │ (Radix)  │ (Session)           │
│         └──────────┴──────────┴──────────┴─────┘                │
└────────────────────┬────────────────────────────────────────────┘
                     │
         ┌───────────┼───────────┬───────────┐
         ▼           ▼           ▼           ▼
┌────────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐
│   OpenAI   │ │  vLLM   │ │  SGLang  │ │ LMDeploy │
│    API     │ │ Server  │ │  Server  │ │  Server  │
└────────────┘ └─────────┘ └──────────┘ └──────────┘
```

---

## ⚙️ 配置选项

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `API_KEY` | OpenAI API Key | 必填 |
| `TARGET_URL` | 目标服务地址 | `https://api.openai.com/v1` |
| `BACKEND_TYPE` | 后端类型: `openai`/`vllm`/`sglang`/`lmdeploy` | `openai` |
| `ENABLE_COMPRESSION` | 启用压缩 | `true` |
| `MEMORIES_TARGET` | 记忆压缩目标 tokens | `1500` |
| `HISTORY_TARGET` | 历史压缩目标 tokens | `1000` |
| `HISTORY_KEEP_LAST_N` | 历史对话保留轮数 | `4` |
| `ENABLE_KV_CACHE` | 启用 KV Cache | `true` |
| `KV_CACHE_SIZE` | KV Cache 大小 | `2000` |
| `HOST` | 服务监听地址 | `0.0.0.0` |
| `PORT` | 服务端口 | `8000` |

### Python 配置

```python
from compress_text_proxy import ProxyConfig

config = ProxyConfig(
    target_url="https://api.openai.com/v1",
    backend_type="openai",  # openai | vllm | sglang | lmdeploy
    api_key="your-api-key",
    enable_compression=True,
    memories_target_tokens=1500,
    history_target_tokens=1000,
    history_keep_last_n=4,
    similarity_threshold=0.55,
    enable_kv_cache=True,
    kv_cache_size=2000,
    kv_cache_enable_compression=True,
    kv_cache_hot_ratio=0.2,
    # 后端特定配置
    vllm_prefix_caching=True,
    sglang_radix_cache=True,
)
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

## 🐳 Docker 部署

### 快速启动

```bash
# 1. 复制环境变量模板
cp .env.example .env

# 2. 编辑 .env 文件，设置你的 API_KEY
vim .env

# 3. 使用脚本启动
./start.sh start

# 或使用 Docker Compose 直接启动
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
  -e HISTORY_KEEP_LAST_N="4" \
  -e ENABLE_KV_CACHE="true" \
  kvcache-proxy
```

### 环境变量配置

#### OpenAI 协议三要素

| 变量名 | 说明 | 默认值 | 必填 |
|--------|------|--------|------|
| `API_KEY` | 大模型 API 密钥 | - | ✅ |
| `TARGET_URL` / `BASE_URL` | 目标服务地址 | `https://api.openai.com/v1` | ✅ |
| `MODEL` | 默认模型名称 | `gpt-4o-mini` | ❌ |

#### 压缩系数配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `ENABLE_COMPRESSION` | 是否启用动态压缩 | `true` |
| `MEMORIES_TARGET` | Memories 压缩目标 Token 数 | `1500` |
| `HISTORY_TARGET` | History 压缩目标 Token 数 | `1000` |
| `HISTORY_KEEP_LAST_N` | 历史对话保留轮数 | `4` |

#### 动态压缩算法参数

| 变量名 | 说明 | 默认值 | 范围 |
|--------|------|--------|------|
| `SIMILARITY_THRESHOLD` | 相似度阈值（值越高压缩越严格） | `0.55` | 0.0-1.0 |
| `SESSION_LEN` | 会话长度限制 | `8192` | - |
| `USE_FAST_MODE` | 快速压缩模式（牺牲压缩率换速度） | `false` | true/false |

#### KV Cache 基础配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `ENABLE_KV_CACHE` | 是否启用 KV Cache | `true` |
| `KV_CACHE_SIZE` | 缓存最大条目数 | `2000` |
| `KV_CACHE_TTL` | 缓存过期时间（秒） | `3600` |
| `VLLM_PREFIX_CACHING` | vLLM 前缀缓存 | `true` |
| `SGLANG_RADIX_CACHE` | SGLang RadixAttention | `true` |
| `LMDEPLOY_CACHE_ENTRIES` | LMDeploy 缓存条目 | `1000` |

#### KV Cache 高性价比优化参数

| 变量名 | 说明 | 默认值 | 效果 |
|--------|------|--------|------|
| `KV_CACHE_COMPRESSION` | 启用内存压缩 | `true` | 节省 50-70% 内存 |
| `KV_CACHE_COMPRESSION_THRESHOLD` | 压缩阈值（字节） | `1024` | >1KB 才压缩 |
| `KV_CACHE_HOT_RATIO` | 热点数据常驻比例 | `0.2` | 20% 数据常驻 |
| `KV_CACHE_ADAPTIVE_TTL` | 自适应 TTL | `true` | 动态调整过期时间 |
| `KV_CACHE_MIN_TTL` | 最小 TTL（秒） | `300` | 不低于 5 分钟 |
| `KV_CACHE_MAX_TTL` | 最大 TTL（秒） | `7200` | 不超过 2 小时 |

**优化策略说明：**
1. **内存压缩**：对冷数据启用 gzip 压缩，内存占用降低 50-70%，CPU 开销 < 5%
2. **热点常驻**：高频访问数据（20%）保留在内存，不被淘汰，命中率提升 15-30%
3. **自适应 TTL**：根据命中率动态调整过期时间，平衡内存和命中率
4. **分层缓存**：L1（热点，未压缩）+ L2（普通，可能压缩）

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
      
      # KV Cache 基础配置
      - ENABLE_KV_CACHE=${ENABLE_KV_CACHE:-true}
      - KV_CACHE_SIZE=${KV_CACHE_SIZE:-2000}
      - KV_CACHE_TTL=${KV_CACHE_TTL:-3600}
      
      # KV Cache 高性价比优化
      - KV_CACHE_COMPRESSION=${KV_CACHE_COMPRESSION:-true}
      - KV_CACHE_HOT_RATIO=${KV_CACHE_HOT_RATIO:-0.2}
      - KV_CACHE_ADAPTIVE_TTL=${KV_CACHE_ADAPTIVE_TTL:-true}
```

---

## 🔌 多后端支持

KVCache+动态压缩大模型代理服务支持多种推理后端，自动适配各后端的 KV Cache 特性：

### 支持的后端

| 后端 | 地址格式 | KV Cache 特性 | 配置 |
|------|----------|---------------|------|
| **OpenAI** | `https://api.openai.com/v1` | 客户端缓存 | `BACKEND_TYPE=openai` |
| **vLLM** | `http://localhost:8000/v1` | Prefix Caching | `BACKEND_TYPE=vllm` |
| **SGLang** | `http://localhost:30000/v1` | RadixAttention | `BACKEND_TYPE=sglang` |
| **LMDeploy** | `http://localhost:23333/v1` | Session Cache | `BACKEND_TYPE=lmdeploy` |

### vLLM 部署示例

```bash
# 启动 vLLM 服务 (带 prefix caching)
docker run -d \
  --gpus all \
  -p 8001:8000 \
  -v /path/to/models:/models \
  vllm/vllm-openai:latest \
  --model /models/llama-2-7b \
  --enable-prefix-caching

# 配置代理指向 vLLM
export TARGET_URL="http://localhost:8001/v1"
export BACKEND_TYPE="vllm"
export VLLM_PREFIX_CACHING="true"

# 启动代理
docker-compose up -d
```

### SGLang 部署示例

```bash
# 启动 SGLang 服务 (RadixAttention 自动启用)
docker run -d \
  --gpus all \
  -p 8002:30000 \
  -v /path/to/models:/models \
  lmsysorg/sglang:latest \
  python -m sglang.launch_server \
  --model-path /models/llama-2-7b \
  --port 30000

# 配置代理
export TARGET_URL="http://localhost:8002/v1"
export BACKEND_TYPE="sglang"
export SGLANG_RADIX_CACHE="true"

docker-compose up -d
```

### LMDeploy 部署示例

```bash
# 启动 LMDeploy 服务
docker run -d \
  --gpus all \
  -p 8003:23333 \
  -v /path/to/models:/models \
  openmmlab/lmdeploy:latest \
  lmdeploy serve api_server /models/llama-2-7b \
  --server-port 23333

# 配置代理
export TARGET_URL="http://localhost:8003/v1"
export BACKEND_TYPE="lmdeploy"
export LMDEPLOY_CACHE_ENTRIES=1000

docker-compose up -d
```

### Docker Compose Profiles

项目预定义了多种部署 Profile：

```bash
# 使用 vLLM
docker-compose --profile vllm up -d

# 使用 SGLang  
docker-compose --profile sglang up -d

# 使用 LMDeploy
docker-compose --profile lmdeploy up -d

# 完整监控
docker-compose --profile monitoring up -d
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

### Grafana 面板

见 `deploy/grafana/dashboard.json`

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
│   ├── docker-compose.yml
│   ├── k8s-deployment.yaml
│   └── grafana/
│
├── examples/                      # 使用示例
├── docs/                          # 文档
├── README.md                      # 本文件
├── pyproject.toml                 # 项目配置
└── Dockerfile                     # Docker 构建
```

---

## 🤝 贡献

欢迎提交 Issue 和 PR！

---

## 📄 License

MIT License

---

**通过 KVCache+动态压缩大模型代理服务，无需修改现有代码即可享受 40-85% 的 Token 成本节省！**
