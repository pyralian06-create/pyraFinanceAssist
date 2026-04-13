#!/bin/bash
# 以普通模式启动 FastAPI 后端（不等待调试器）

cd "$(dirname "$0")/.."

echo "🚀 启动 FastAPI 后端"
echo "   API 地址:    http://localhost:8000"
echo "   API 文档:    http://localhost:8000/docs"
echo ""

.venv/bin/python -m uvicorn app.main:app \
  --reload \
  --host 0.0.0.0 \
  --port 8000 \
  --log-level info
