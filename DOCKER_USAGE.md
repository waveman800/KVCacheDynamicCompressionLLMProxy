# Docker 部署使用指南

## 快速开始

### 1. 使用启动脚本（推荐）

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，设置 API_KEY
vim .env

# 启动服务
./start.sh start

# 查看状态
./start.sh status

# 查看日志
./start.sh logs

# 停止服务
./start.sh stop
```

### 2. 使用 Docker Compose

```bash
# 启动
docker-compose up -d

# 停止
docker-compose down
```

### 3. 使用 Docker 命令

```bash
# 构建
docker build -t kvcache-proxy .

# 运行
docker run -d \
  --name kvcache-proxy \
  -p 8000:8000 \
  -e API_KEY="sk-xxx" \
  -e TARGET_URL="https://api.openai.com/v1" \
  -e MODEL="gpt-4o-mini" \
  kvcache-proxy
```

## 环境变量清单

### OpenAI 协议三要素（必填）

| 变量 | 说明 | 示例 |
|------|------|------|
| `API_KEY` | API 密钥 | `sk-abc123...` |
| `TARGET_URL` / `BASE_URL` | 服务地址 | `https://api.openai.com/v1` |
| `MODEL` | 默认模型 | `gpt-4o-mini` |

### 压缩系数（可选）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ENABLE_COMPRESSION` | 启用压缩 | `true` |
| `MEMORIES_TARGET` | 记忆压缩目标 | `1500` |
| `HISTORY_TARGET` | 历史压缩目标 | `1000` |
| `HISTORY_KEEP_LAST_N` | 保留最近 N 轮 | `4` |

### 动态压缩算法参数（可选）

| 变量 | 说明 | 默认值 | 范围 |
|------|------|--------|------|
| `SIMILARITY_THRESHOLD` | 相似度阈值 | `0.55` | 0.0-1.0 |
| `SESSION_LEN` | 会话长度限制 | `8192` | - |
| `USE_FAST_MODE` | 快速压缩模式 | `false` | true/false |

### KV Cache 基础配置（可选）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ENABLE_KV_CACHE` | 启用缓存 | `true` |
| `KV_CACHE_SIZE` | 缓存条目数 | `2000` |
| `KV_CACHE_TTL` | 过期时间(秒) | `3600` |

### KV Cache 高性价比优化（可选）

| 变量 | 说明 | 默认值 | 推荐值 |
|------|------|--------|--------|
| `KV_CACHE_COMPRESSION` | 内存压缩 | `true` | ✅ 开启 |
| `KV_CACHE_COMPRESSION_THRESHOLD` | 压缩阈值(字节) | `1024` | 512-2048 |
| `KV_CACHE_HOT_RATIO` | 热点数据比例 | `0.2` | 0.1-0.3 |
| `KV_CACHE_ADAPTIVE_TTL` | 自适应TTL | `true` | ✅ 开启 |
| `KV_CACHE_MIN_TTL` | 最小TTL(秒) | `300` | 60-600 |
| `KV_CACHE_MAX_TTL` | 最大TTL(秒) | `7200` | 1800-86400 |

**性价比说明：**
- 开启压缩可节省 **50-70%** 内存，CPU 开销 < 5%
- 热点常驻可提升 **15-30%** 命中率
- 自适应 TTL 自动平衡内存占用和命中率

## API 端点

| 端点 | 说明 |
|------|------|
| `POST /v1/chat/completions` | 聊天补全（OpenAI 兼容） |
| `GET /v1/models` | 列出模型 |
| `GET /health` | 健康检查 |
| `GET /metrics` | 性能指标 |

## 客户端使用示例

```python
import openai

client = openai.OpenAI(
    api_key="your-api-key",
    base_url="http://localhost:8000/v1"
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "你好"}]
)

print(response.choices[0].message.content)
# 查看压缩效果
if hasattr(response, 'compression'):
    print(f"节省了 {response.compression['total_savings_percentage']:.1f}% tokens")
```
