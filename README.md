# 个人金融助手分析工具 (V1.0)

轻量级的金融持仓分析与实时盯盘工具。采用"本地存储+内存计算"的极简架构，无需昂贵云服务，完全掌握数据隐私。

## 核心功能

✅ **交易流水记录**：支持多资产（A股、基金、黄金、美股）  
✅ **动态盈亏分析**：实时 PnL 计算、持仓成本核算  
✅ **实时盯盘**：自定义监控规则、微信告警推送  
✅ **可视化看板**：持仓分布、盈亏详情、交易管理  

## 项目结构

```
finance_tool/
├── CLAUDE.md              # 项目设计文档
├── README.md              # 本文件
├── requirements.txt       # 依赖列表
├── .env.example          # 环境变量模板
├── .env                  # 环境变量（本地，不提交git）
│
├── finance_data.db       # SQLite 数据库（自动创建）
│
├── app/                  # 后端主包
│   ├── config.py         # 全局配置管理
│   ├── main.py           # FastAPI 启动入口（待编写）
│   │
│   ├── models/           # 数据库 ORM 模型层
│   │   ├── database.py   # SQLAlchemy 初始化
│   │   ├── trade.py      # Trade 交易流水表
│   │   └── alert_rule.py # AlertRule 告警规则表
│   │
│   ├── schemas/          # Pydantic 数据验证层
│   │   ├── trade.py      # Trade 请求/响应模式
│   │   ├── portfolio.py  # Portfolio 模式
│   │   └── alert.py      # Alert 模式
│   │
│   ├── data_fetcher/     # 数据接入模块（待编写）
│   │   ├── router.py     # 多源行情路由
│   │   ├── stock_a.py    # A股接入
│   │   ├── fund.py       # 基金接入
│   │   ├── gold.py       # 黄金接入
│   │   └── us_stock.py   # 美股接入
│   │
│   ├── ledger/           # 交易流水管理（待编写）
│   │   └── service.py    # CRUD 业务逻辑
│   │
│   ├── pnl_engine/       # 持仓&盈亏计算（待编写）
│   │   └── calculator.py # 核心算法
│   │
│   ├── monitor/          # 盯盘守护进程（待编写）
│   │   ├── daemon.py     # asyncio 轮询
│   │   ├── rule_engine.py # 规则判定
│   │   └── notifier.py   # 消息推送
│   │
│   └── api/              # FastAPI 路由层（待编写）
│       ├── trades.py     # /api/trades
│       ├── portfolio.py  # /api/portfolio
│       └── alerts.py     # /api/alerts
│
└── dashboard/            # Streamlit 前端（待编写）
    ├── app.py            # 主入口
    └── pages/
        ├── 01_portfolio.py    # 持仓大屏
        ├── 02_trade_entry.py  # 交易录入
        └── 03_alert_config.py # 告警配置
```

## 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip install -r requirements.txt

# 创建 .env 文件（复制自 .env.example）
cp .env.example .env
```

### 2. 启动后端

```bash
# 启动 FastAPI 服务（http://localhost:8000）
python -m uvicorn app.main:app --reload
```

### 3. 启动前端

```bash
# 另开一个终端，启动 Streamlit（http://localhost:8501）
streamlit run dashboard/app.py
```

## 开发进度

- [x] 阶段 1：打地基
  - [x] 项目结构初始化
  - [x] requirements.txt
  - [x] config.py 配置管理
  - [x] models/ ORM 层 (Trade, AlertRule)
  - [x] schemas/ Pydantic 验证层
  
- [ ] 阶段 2：算明白
  - [ ] data_fetcher/ 行情接入
  - [ ] ledger/ CRUD 业务逻辑
  - [ ] pnl_engine/ 盈亏计算
  - [ ] api/ FastAPI 路由
  
- [ ] 阶段 3：动起来
  - [ ] monitor/ 盯盘守护进程
  - [ ] notifier/ 微信推送
  - [ ] Server酱 集成
  
- [ ] 阶段 4：看得到
  - [ ] Streamlit 前端
  - [ ] 可视化图表

## 核心概念

### 数据流向

```
用户界面 (Streamlit)
    ↓↑
FastAPI HTTP 接口 (/api/trades, /api/portfolio, /api/alerts)
    ↓
业务逻辑层 (ledger, pnl_engine, monitor)
    ↓
ORM 层 (models/Trade, AlertRule)
    ↓
SQLite 本地数据库 (finance_data.db)

后台独立：
盯盘守护进程 (asyncio daemon) → 数据接入器 (AkShare) → Server酱推送
```

### 关键设计决策

1. **Decimal 精度**：quantity 和 price 使用 `Numeric(18,6)` 支持基金份额和黄金克重
2. **异步守护进程**：在 FastAPI lifespan 中启动 asyncio 任务，和 API 服务共用事件循环
3. **前后端解耦**：Streamlit 通过 HTTP 调用 FastAPI，未来可独立部署

## 外部依赖

| 依赖 | 用途 | 注册 |
|-----|------|------|
| AkShare | 行情数据 | `pip install akshare`（无需凭证） |
| Server酱 | 微信推送 | https://sct.ftqq.com（微信扫码，获取 SendKey） |
| SQLite | 本地数据库 | Python 内置 |

## 贡献指南

- 按照 requirements.txt 安装依赖
- 修改代码时 respect 现有的模块划分
- 新增功能前先更新 CLAUDE.md 设计文档
- 提交代码前运行 tests（待实现）

## License

MIT
