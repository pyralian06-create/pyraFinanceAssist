#!/bin/bash
# 以调试模式启动 FastAPI 后端
# debugpy 监听 5678，uvicorn 监听 8000
# 使用 --wait-for-client 让服务等待调试器连接后再执行（去掉该参数可直接启动不等待）

cd "$(dirname "$0")/.."

echo "🚀 启动 FastAPI 后端 (调试模式)"
echo "   API 地址:    http://localhost:8000"
echo "   API 文档:    http://localhost:8000/docs"
echo "   调试端口:    5678 (等待调试器连接...)"
echo ""

.venv/bin/python -m debugpy \
  --listen 0.0.0.0:5678 \
  --wait-for-client \
  -m uvicorn app.main:app \
  --reload \
  --host 0.0.0.0 \
  --port 8000 \
  --log-level debug
