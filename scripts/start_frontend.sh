#!/bin/bash
# 启动 Streamlit 前端看板

cd "$(dirname "$0")/.."

echo "🎨 启动 Streamlit 前端看板"
echo "   看板地址:  http://localhost:8501"
echo "   依赖后端:  http://localhost:8000"
echo ""

.venv/bin/streamlit run dashboard/app.py \
  --server.address 0.0.0.0 \
  --server.port 8501 \
  --server.headless true
