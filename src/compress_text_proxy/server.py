"""
FastAPI 服务器

提供 HTTP API 接口
"""

import json
import os
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from .proxy import CompressionProxy, ProxyConfig


class ChatMessage(BaseModel):
    """聊天消息"""
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """聊天补全请求"""
    model: str = Field(default="gpt-4")
    messages: List[ChatMessage]
    temperature: Optional[float] = Field(default=0.7)
    max_tokens: Optional[int] = Field(default=None)
    stream: Optional[bool] = Field(default=False)
    
    # 扩展字段
    memories: Optional[List[str]] = Field(default=None)
    user_id: Optional[str] = Field(default=None)
    session_id: Optional[str] = Field(default=None)


# 全局代理实例
proxy: Optional[CompressionProxy] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """生命周期管理"""
    global proxy
    
    # 从环境变量加载完整配置
    config = ProxyConfig.from_env()
    
    proxy = CompressionProxy(config)
    print(f"🚀 KVCache+动态压缩大模型代理服务 started")
    print(f"   Target: {config.target_url}")
    print(f"   Backend: {config.backend_type}")
    print(f"   Compression: {config.enable_compression}")
    print(f"   KV Cache: {config.enable_kv_cache}")
    if config.enable_kv_cache:
        print(f"   KV Cache Features: vLLM_prefix={config.vllm_prefix_caching}, SGLang_radix={config.sglang_radix_cache}")
    
    yield
    
    # 关闭
    await proxy.close()


app = FastAPI(
    title="KVCache+动态压缩大模型代理服务",
    description="KV Cache + 动态压缩的大模型代理服务 - 降低 Token 成本 40-85%",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """OpenAI 兼容的聊天补全接口"""
    global proxy
    
    if not proxy:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    
    result = await proxy.process_request(
        messages=messages,
        model=request.model,
        memories=request.memories,
        user_id=request.user_id,
        session_id=request.session_id,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        stream=request.stream
    )
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    # 转发到后端
    if request.stream:
        async def generate():
            async for chunk in proxy.forward_to_backend(result.backend_request, stream=True):
                yield chunk
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"X-Compression-Info": json.dumps(result.compression_info) if result.compression_info else ""}
        )
    else:
        async for response_text in proxy.forward_to_backend(result.backend_request, stream=False):
            try:
                response_data = json.loads(response_text)
                if result.compression_info:
                    response_data["compression"] = result.compression_info
                return JSONResponse(content=response_data)
            except json.JSONDecodeError:
                return JSONResponse(
                    content={"error": "Invalid response", "raw": response_text},
                    status_code=502
                )
        
        raise HTTPException(status_code=502, detail="No response from backend")


@app.get("/v1/models")
async def list_models():
    """列出可用模型"""
    return {
        "object": "list",
        "data": [
            {"id": "gpt-4", "object": "model"},
            {"id": "gpt-4o", "object": "model"},
            {"id": "gpt-4o-mini", "object": "model"},
        ]
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "service": "KVCache+动态压缩大模型代理服务",
        "version": "1.0.0"
    }


@app.get("/metrics")
async def get_metrics():
    """获取指标"""
    global proxy
    if not proxy:
        return {"error": "Service not ready"}
    
    return proxy.get_metrics()


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "KVCache+动态压缩大模型代理服务",
        "version": "1.0.0",
        "description": "KV Cache + 动态压缩的大模型代理服务",
        "endpoints": {
            "chat": "/v1/chat/completions",
            "models": "/v1/models",
            "health": "/health",
            "metrics": "/metrics"
        }
    }


def main():
    """启动服务器"""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
