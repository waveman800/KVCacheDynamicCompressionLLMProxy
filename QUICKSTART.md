# KVCache+动态压缩大模型代理服务 快速开始

## 5 分钟快速体验

### 1. 安装

```bash
git clone <repository-url>
cd KVCacheDynamicCompressionLLMProxy
pip install -e .
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env，设置 API_KEY 和 TARGET_URL
```

### 3. 启动

```bash
kvcache-proxy
```

或使用 Python：

```bash
python -m compress_text_proxy.server
```

### 4. 测试

```bash
# 健康检查
curl http://localhost:8000/health

# 查看指标
curl http://localhost:8000/metrics
```

### 5. 使用

```python
import openai

client = openai.OpenAI(
    api_key="your-api-key",
    base_url="http://localhost:8000/v1"
)

response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "你好"}]
)

print(response.choices[0].message.content)
```

---

## 多后端快速配置

### OpenAI (默认)

```bash
export API_KEY="sk-..."
export TARGET_URL="https://api.openai.com/v1"
export BACKEND_TYPE="openai"
```

### vLLM

```bash
# 1. 启动 vLLM
docker run -d --gpus all -p 8001:8000 \
  -v /path/to/models:/models \
  vllm/vllm-openai:latest \
  --model /models/llama-2-7b \
  --enable-prefix-caching

# 2. 配置代理
export TARGET_URL="http://localhost:8001/v1"
export BACKEND_TYPE="vllm"
export VLLM_PREFIX_CACHING="true"
```

### SGLang

```bash
# 1. 启动 SGLang
docker run -d --gpus all -p 8002:30000 \
  -v /path/to/models:/models \
  lmsysorg/sglang:latest \
  python -m sglang.launch_server \
  --model-path /models/llama-2-7b

# 2. 配置代理
export TARGET_URL="http://localhost:8002/v1"
export BACKEND_TYPE="sglang"
export SGLANG_RADIX_CACHE="true"
```

### LMDeploy

```bash
# 1. 启动 LMDeploy
docker run -d --gpus all -p 8003:23333 \
  -v /path/to/models:/models \
  openmmlab/lmdeploy:latest \
  lmdeploy serve api_server /models/llama-2-7b

# 2. 配置代理
export TARGET_URL="http://localhost:8003/v1"
export BACKEND_TYPE="lmdeploy"
```

---

## Docker 部署

### OpenAI 模式

```bash
docker-compose up -d
```

### vLLM 模式

```bash
export MODEL_PATH=/path/to/models
docker-compose --profile vllm up -d
```

### SGLang 模式

```bash
export MODEL_PATH=/path/to/models
docker-compose --profile sglang up -d
```

### LMDeploy 模式

```bash
export MODEL_PATH=/path/to/models
docker-compose --profile lmdeploy up -d
```

---

## 预期效果

```
原始请求: 9,000 tokens
压缩后:   2,500 tokens (-72%)

月成本(10k请求):
  无压缩: $2,700
  有压缩: $750 (节省 $1,950)
```

---

## 下一步

- 查看 [README.md](README.md) 获取完整文档
- 查看 [docs/BACKENDS.md](docs/BACKENDS.md) 获取多后端部署指南
- 查看 [examples/](examples/) 获取更多示例
