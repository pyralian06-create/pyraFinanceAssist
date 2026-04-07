# 快速启动指南

## 环境准备

### 1. 安装依赖
```bash
pip3 install -r requirements.txt
```

### 2. 验证安装
```bash
python3 -c "import fastapi; import sqlalchemy; print('✅ 核心依赖安装成功')"
```

## 启动应用

### 启动 FastAPI 后端服务

```bash
# 方法 1：直接运行
python3 app/main.py

# 方法 2：使用 uvicorn（生产推荐）
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**服务信息：**
- 主页：http://localhost:8000
- API 文档：http://localhost:8000/docs （Swagger UI）
- ReDoc 文档：http://localhost:8000/redoc
- 健康检查：http://localhost:8000/health

### 启动 Streamlit 前端

```bash
streamlit run dashboard/app.py
# 前端地址：http://localhost:8501
```

## 项目架构

```
FastAPI (后端)
├── /api/trades      ← 交易流水 CRUD
├── /api/portfolio   ← 持仓汇总
└── /api/market      ← 市场标的搜索与校验

Streamlit (前端)
├── 持仓看板与流水（app.py）
└── 交易录入（pages/01_trade_entry.py）
```

## 数据库

SQLite 数据库文件自动创建于：
```
./finance_data.db
```

### 查看数据库

**VS Code SQLite 扩展：**
1. 安装 "SQLite" 扩展（作者：alexcvzz）
2. 在文件浏览器中右键 `finance_data.db` → "Open Database"
3. 查看表结构和数据

## 开发工作流

### 调试 SQL 语句
在 `.env` 中设置：
```
ECHO_SQL=True
```

重启应用后，所有 SQL 语句将打印到控制台。

### 测试 API 接口

使用 Swagger UI（http://localhost:8000/docs）直接测试：
1. 点击需要测试的端点
2. 点击 "Try it out"
3. 输入请求参数
4. 点击 "Execute" 查看响应

## 常见问题

### Q: 启动时报错 "No module named 'fastapi'"
A: 需要安装依赖
```bash
pip3 install -r requirements.txt
```

### Q: 数据库无法初始化
A: 检查 `.env` 中的 `DATABASE_URL` 路径权限

### Q: 想修改数据库路径
A: 编辑 `.env` 中的 `DATABASE_URL`
```
DATABASE_URL=sqlite:////path/to/finance_data.db
```

## 下一步（可选）

- 完善 `app/ledger/` 独立服务层（当前 CRUD 在 `app/api/trades`）
- 扩展看板或报表需求见 `CLAUDE.md`
