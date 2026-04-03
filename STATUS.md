# 项目开发状态报告

**更新时间：** 2026-04-03  
**当前阶段：** 阶段 2 - 算明白（进行中）

## ✅ 已完成

### 阶段 1：打地基
- [x] 项目结构初始化
- [x] `app/config.py` - 全局配置管理
- [x] `app/models/database.py` - SQLAlchemy 初始化
- [x] `app/models/trade.py` - Trade ORM 模型
- [x] `app/models/alert_rule.py` - AlertRule ORM 模型
- [x] `app/schemas/trade.py` - Trade Pydantic Schema
- [x] `app/schemas/portfolio.py` - Portfolio Schema
- [x] `app/schemas/alert.py` - Alert Schema
- [x] `requirements.txt` - 依赖列表（已更新）
- [x] `.env` 配置文件

### 阶段 2：算明白 - 进行中
- [x] **`app/main.py`** ✨ 新增
  - FastAPI 应用初始化
  - 生命周期管理（启动、关闭）
  - 中间件配置（CORS、异常处理）
  - 基础路由（/health, /）
  - 数据库自动初始化

## 🚧 进行中

### 阶段 2：算明白（剩余）
- [ ] `app/data_fetcher/` - 行情数据接入
  - [ ] `router.py` - 多源路由
  - [ ] `stock_a.py` - A股接入
  - [ ] `fund.py` - 基金接入
  - [ ] `gold.py` - 黄金接入
  - [ ] `us_stock.py` - 美股接入
- [ ] `app/ledger/service.py` - CRUD 业务逻辑
- [ ] `app/pnl_engine/calculator.py` - 持仓与盈亏计算
- [ ] `app/api/` - FastAPI 路由层
  - [ ] `trades.py` - /api/trades
  - [ ] `portfolio.py` - /api/portfolio
  - [ ] `alerts.py` - /api/alerts

## 📋 待实现

### 阶段 3：动起来（预计 2-3 天）
- [ ] `app/monitor/daemon.py` - asyncio 守护进程
- [ ] `app/monitor/rule_engine.py` - 规则判定
- [ ] `app/monitor/notifier.py` - Server酱 推送

### 阶段 4：看得到（预计 2-3 天）
- [ ] `dashboard/app.py` - Streamlit 入口
- [ ] `dashboard/pages/01_portfolio.py` - 持仓大屏
- [ ] `dashboard/pages/02_trade_entry.py` - 交易录入
- [ ] `dashboard/pages/03_alert_config.py` - 告警配置

## 🎯 下一步

**建议优先级：**

1. **实现 `app/data_fetcher/`** （1-2 天）
   - 用 AkShare 获取实时行情
   - 支持多资产类型路由
   - 提供统一的数据接口

2. **实现 `app/pnl_engine/calculator.py`** （1 天）
   - 成本计算算法
   - 盈亏计算逻辑
   - 汇总分析函数

3. **实现 `app/ledger/service.py`** （0.5 天）
   - CRUD 操作
   - 数据验证

4. **实现 `app/api/` 路由层** （1 天）
   - 暴露业务逻辑为 HTTP API
   - 集成 Swagger 文档

## 🚀 快速启动

```bash
# 安装依赖（已完成）
pip3 install -r requirements.txt

# 启动后端 API 服务
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 访问 API 文档
# http://localhost:8000/docs
```

## 📊 当前 API 状态

已实现的端点：
- `GET /` - API 根信息
- `GET /health` - 健康检查

待实现的端点：
- `GET|POST /api/trades` - 交易管理
- `GET /api/portfolio/summary` - 持仓汇总
- `GET|POST /api/alerts` - 告警规则

## 📝 配置信息

- **数据库**：SQLite (./finance_data.db)
- **后端框架**：FastAPI
- **前端框架**：Streamlit
- **行情数据**：AkShare
- **微信推送**：Server酱 (待配置)

## 📌 设计笔记

### FastAPI 应用架构
```
FastAPI app
├── lifespan (生命周期管理)
│   ├── startup: 初始化数据库
│   └── shutdown: 清理资源
├── middleware (中间件)
│   └── CORSMiddleware (跨域支持)
├── routes (路由)
│   ├── /health (系统)
│   ├── /api/trades (待挂载)
│   ├── /api/portfolio (待挂载)
│   └── /api/alerts (待挂载)
└── exception_handler (异常处理)
```

### 数据库初始化流程
1. 应用启动时调用 `init_db()`
2. SQLAlchemy 读取所有 ORM 模型
3. 自动创建或更新数据库表
4. 数据持久化到 `finance_data.db`

---

**项目进度：** 18% 完成 (3/4 阶段)
