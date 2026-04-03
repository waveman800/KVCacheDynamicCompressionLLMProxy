FROM python:3.10-slim
# ccr.ccs.tencentyun.com/waveman/python:3.12-slim

# 镜像元数据
LABEL maintainer="Brain Team"
LABEL description="KV Cache + 动态压缩的大模型代理服务 - 降低 Token 成本 40-85%"
LABEL version="1.0.0"

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY pyproject.toml README.md ./
COPY src/ ./src/

# 安装 Python 依赖
RUN pip install --no-cache-dir -e "."

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# ==========================================
# 环境变量配置说明
# ==========================================
# 以下变量必须在宿主机环境变量中设置（通过 -e 或 --env-file 传入）：
#
# 【OpenAI 协议三要素 - 必填】
#   API_KEY      - 大模型 API 密钥
#   TARGET_URL   - 目标服务地址 (如 https://api.openai.com/v1)
#   MODEL        - 默认模型名称 (如 gpt-4o-mini)
#
# 示例：
#   docker run -e API_KEY=xxx -e TARGET_URL=https://api.openai.com/v1 -e MODEL=gpt-4o-mini ...
# ==========================================

# 压缩配置（可选，有默认值）
ENV ENABLE_COMPRESSION="true"
ENV MEMORIES_TARGET="1500"
ENV HISTORY_TARGET="1000"
ENV HISTORY_KEEP_LAST_N="4"

# 动态压缩算法参数（可选，有默认值）
ENV SIMILARITY_THRESHOLD="0.55"
ENV SESSION_LEN="8192"
ENV USE_FAST_MODE="false"

# 细粒度压缩参数（可选，有默认值）
ENV COMPRESSION_GRANULARITY="paragraph"
ENV MIN_KEEP_SEGMENTS="1"

# 重要性评分权重（总和应为1.0）
ENV CONTENT_IMPORTANCE_WEIGHT="0.7"
ENV POSITION_WEIGHT="0.2"
ENV QUERY_WEIGHT="0.1"

# KV Cache 基础配置（可选，有默认值）
ENV ENABLE_KV_CACHE="true"
ENV KV_CACHE_SIZE="2000"
ENV KV_CACHE_TTL="3600"

# KV Cache 高性价比优化参数（可选，有默认值）
ENV KV_CACHE_COMPRESSION="true"
ENV KV_CACHE_COMPRESSION_THRESHOLD="1024"
ENV KV_CACHE_HOT_RATIO="0.2"
ENV KV_CACHE_ADAPTIVE_TTL="true"
ENV KV_CACHE_MIN_TTL="300"
ENV KV_CACHE_MAX_TTL="7200"

# 服务配置（可选，有默认值）
ENV HOST="0.0.0.0"
ENV PORT="8000"

# 启动命令
CMD ["kvcache-proxy"]
