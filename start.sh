#!/bin/bash
# ==========================================
# KVCache+动态压缩大模型代理服务 - 快速启动脚本
# ==========================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的信息
info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# 显示帮助信息
show_help() {
    cat << EOF
KVCache+动态压缩大模型代理服务 - 启动脚本

用法: $0 [选项] [命令]

命令:
    start           启动服务（默认）
    stop            停止服务
    restart         重启服务
    build           重新构建镜像
    logs            查看日志
    status          查看服务状态
    config          显示当前配置

选项:
    -h, --help      显示帮助信息
    -p, --profile   指定 docker-compose profile (vllm|sglang|lmdeploy|monitoring)

示例:
    # 使用 OpenAI API 启动（默认）
    $0 start

    # 使用 vLLM 后端启动
    $0 --profile vllm start

    # 查看日志
    $0 logs

    # 查看当前配置
    $0 config

环境变量:
    请确保 .env 文件已正确配置，或设置以下环境变量：
    - API_KEY: 大模型 API 密钥
    - TARGET_URL: 目标服务地址
    - MODEL: 默认模型名称
EOF
}

# 检查 .env 文件
check_env() {
    if [ ! -f ".env" ]; then
        warn ".env 文件不存在，使用 .env.example 作为模板"
        if [ -f ".env.example" ]; then
            cp .env.example .env
            warn "请编辑 .env 文件，设置你的 API_KEY 和其他配置"
        else
            error ".env.example 文件也不存在！"
            exit 1
        fi
    fi

    # 检查关键环境变量
    if [ -z "$API_KEY" ] && ! grep -q "^API_KEY=your-api-key" .env 2>/dev/null; then
        info "API_KEY 已配置"
    else
        warn "请确保 API_KEY 已正确配置在 .env 文件中"
    fi
}

# 显示当前配置
show_config() {
    info "当前配置:"
    echo "----------------------------------------"
    if [ -f ".env" ]; then
        grep -v "^#" .env | grep -v "^$" | while read line; do
            key=$(echo "$line" | cut -d'=' -f1)
            value=$(echo "$line" | cut -d'=' -f2-)
            # 隐藏 API_KEY 的值
            if [ "$key" = "API_KEY" ]; then
                echo "  $key=***hidden***"
            else
                echo "  $key=$value"
            fi
        done
    else
        warn ".env 文件不存在"
    fi
    echo "----------------------------------------"
}

# 启动服务
start_service() {
    check_env
    info "启动 KVCache+动态压缩大模型代理服务..."

    if [ -n "$PROFILE" ]; then
        info "使用 profile: $PROFILE"
        docker-compose --profile "$PROFILE" up -d
    else
        docker-compose up -d
    fi

    success "服务已启动！"
    info "API 地址: http://localhost:8000"
    info "健康检查: http://localhost:8000/health"
    info "指标监控: http://localhost:8000/metrics"
}

# 停止服务
stop_service() {
    info "停止服务..."
    docker-compose down
    success "服务已停止"
}

# 重启服务
restart_service() {
    stop_service
    start_service
}

# 重新构建
build_service() {
    info "重新构建镜像..."
    docker-compose build --no-cache
    success "镜像构建完成"
}

# 查看日志
show_logs() {
    docker-compose logs -f
}

# 查看状态
show_status() {
    docker-compose ps
}

# 解析参数
PROFILE=""
COMMAND="start"

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -p|--profile)
            PROFILE="$2"
            shift 2
            ;;
        start|stop|restart|build|logs|status|config)
            COMMAND="$1"
            shift
            ;;
        *)
            error "未知参数: $1"
            show_help
            exit 1
            ;;
    esac
done

# 执行命令
case $COMMAND in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    build)
        build_service
        ;;
    logs)
        show_logs
        ;;
    status)
        show_status
        ;;
    config)
        show_config
        ;;
    *)
        error "未知命令: $COMMAND"
        show_help
        exit 1
        ;;
esac
