"""
金融助手分析工具 - 后端包

核心模块：
- models: ORM 数据库模型 (Trade, AlertRule)
- schemas: Pydantic 数据验证 (TradeCreate, PortfolioSummary 等)
- data_fetcher: 多资产行情接入 (AkShare)
- ledger: 交易流水管理 CRUD
- pnl_engine: 持仓成本与盈亏计算
- monitor: 盯盘守护进程与告警推送
- api: FastAPI 路由层
"""

__version__ = "0.1.0"
