# 多后端部署指南

KVCache+动态压缩大模型代理服务支持多种 LLM 推理后端，自动适配各后端的 KV Cache 特性。

---

## 📋 后端对比

| 后端 | KV Cache 特性 | 适用场景 | GPU 需求 |
|------|---------------|----------|----------|
| **OpenAI** | 客户端缓存 | 快速开始，无运维 | ❌ |
| **vLLM** | Prefix Caching | 高吞吐，多并发 | ✅ |
| **SGLang** | RadixAttention | 多轮对话优化 | ✅ |
| **LMDeploy** | Session Cache | 企业部署 | ✅ |

---

## 🔧 配置方式

### 环境变量配置

```bash
# 基础配置
export TARGET_URL="http://localhost:8000/v1"
export BACKEND_TYPE="vllm"  # openai | vllm | sglang | lmdeploy
export API_KEY="your-key"

# 后端特定配置
export VLLM_PREFIX_CACHING=true
export SGLANG_RADIX_CACHE=true
export LMDEPLOY_CACHE_ENTRIES=1000
```

### Python 配置

```python
from compress_text_proxy import ProxyConfig

config = ProxyConfig(
    target_url="http://localhost:8000/v1",
    backend_type="vllm",
    api_key="your-key",
    vllm_prefix_caching=True,
)
```

---

## 🚀 vLLM 部署

### 启动 vLLM 服务

```bash
docker run -d \
  --name vllm-server \
  --gpus all \
  -p 8001:8000 \
  -v /path/to/models:/models \
  vllm/vllm-openai:latest \
  --model /models/llama-2-7b \
  --enable-prefix-caching \
  --max-num-seqs 256 \
  --tensor-parallel-size 1
```

### 配置代理

```bash
# .env 文件
TARGET_URL=http://localhost:8001/v1
BACKEND_TYPE=vllm
VLLM_PREFIX_CACHING=true
```

```bash
docker-compose up -d kvcache-dynamic-proxy
```

### 使用 Docker Compose Profile

```bash
export MODEL_PATH=/path/to/models
export VLLM_MODEL=llama-2-7b

docker-compose --profile vllm up -d
```

---

## 🚀 SGLang 部署

### 启动 SGLang 服务

```bash
docker run -d \
  --name sglang-server \
  --gpus all \
  -p 8002:30000 \
  -v /path/to/models:/models \
  lmsysorg/sglang:latest \
  python -m sglang.launch_server \
  --model-path /models/llama-2-7b \
  --port 30000 \
  --enable-radix-cache
```

### 配置代理

```bash
# .env 文件
TARGET_URL=http://localhost:8002/v1
BACKEND_TYPE=sglang
SGLANG_RADIX_CACHE=true
```

### 使用 Docker Compose Profile

```bash
export MODEL_PATH=/path/to/models
export SGLANG_MODEL=llama-2-7b

docker-compose --profile sglang up -d
```

---

## 🚀 LMDeploy 部署

### 启动 LMDeploy 服务

```bash
docker run -d \
  --name lmdeploy-server \
  --gpus all \
  -p 8003:23333 \
  -v /path/to/models:/models \
  openmmlab/lmdeploy:latest \
  lmdeploy serve api_server \
  /models/llama-2-7b \
  --server-port 23333 \
  --tp 1 \
  --cache-max-entry-count 0.8
```

### 配置代理

```bash
# .env 文件
TARGET_URL=http://localhost:8003/v1
BACKEND_TYPE=lmdeploy
LMDEPLOY_CACHE_ENTRIES=1000
```

### 使用 Docker Compose Profile

```bash
export MODEL_PATH=/path/to/models
export LMDEPLOY_MODEL=llama-2-7b

docker-compose --profile lmdeploy up -d
```

---

## 📊 各后端 KV Cache 特性详解

### vLLM Prefix Caching

- **原理**: 缓存相同前缀的 attention KV
- **效果**: 相同系统提示复用，首 token 延迟降低 50-80%
- **配置**: `--enable-prefix-caching`

### SGLang RadixAttention

- **原理**: 树形结构缓存，支持部分匹配
- **效果**: 多轮对话场景效果最佳，缓存命中率 70-90%
- **配置**: 自动启用，无需额外配置

### LMDeploy Session Cache

- **原理**: 基于 session_id 管理对话状态
- **效果**: 长对话保持上下文，减少重复计算
- **配置**: `--cache-max-entry-count 0.8`

---

## 🧪 验证部署

### 测试连通性

```bash
# 健康检查
curl http://localhost:8000/health

# 查看指标
curl http://localhost:8000/metrics
```

### 测试压缩效果

```python
import openai

client = openai.OpenAI(
    api_key="your-key",
    base_url="http://localhost:8000/v1"
)

response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "你好"}
    ],
    extra_body={"memories": ["用户喜欢Python"] * 50}  # 大量记忆测试压缩
)

print(response.compression)
```

---

## 🔍 故障排查

### vLLM 无法连接

```bash
# 检查 vLLM 服务状态
curl http://localhost:8001/v1/models

# 查看日志
docker logs vllm-server
```

### SGLang 端口问题

```bash
# SGLang 默认使用 30000 端口
# 确保代理指向正确端口
export TARGET_URL="http://localhost:8002/v1"
```

### LMDeploy 缓存未命中

```bash
# 增加缓存条目数
export LMDEPLOY_CACHE_ENTRIES=2000

# 重启服务
docker-compose restart kvcache-dynamic-proxy
```

---

## 💡 最佳实践

1. **OpenAI API**: 适合快速验证，无需 GPU
2. **vLLM**: 适合高吞吐场景，启用 prefix caching
3. **SGLang**: 适合多轮对话，RadixAttention 自动优化
4. **LMDeploy**: 适合企业级部署，灵活可控

---

## 📚 参考链接

- [vLLM 文档](https://docs.vllm.ai/)
- [SGLang 文档](https://github.com/sgl-project/sglang)
- [LMDeploy 文档](https://lmdeploy.readthedocs.io/)
