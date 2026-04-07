# 个人金融助手分析工具

轻量级**持仓分析与盈亏**工具。采用「本地存储 + 内存计算」，无需云服务，数据留在本机。

## 核心功能

- **交易流水**：多资产（A 股、港股、美股、基金、现货黄金等）
- **动态盈亏**：加权平均成本、浮动/已实现盈亏、持仓汇总 API
- **行情接入**：AkShare 统一路由（`app/data_fetcher`）
- **可视化看板**：Streamlit（持仓、流水、交易录入）

## 项目结构（摘要）

```
├── app/
│   ├── main.py           # FastAPI 入口
│   ├── config.py
│   ├── models/           # Trade, MarketSymbol
│   ├── schemas/
│   ├── data_fetcher/     # 多资产行情
│   ├── pnl_engine/       # 盈亏计算
│   ├── services/         # 市场标的同步
│   └── api/              # trades, portfolio, market
├── dashboard/
│   ├── app.py
│   └── pages/01_trade_entry.py
├── finance_data.db       # SQLite（运行后生成）
├── CLAUDE.md             # 面向开发者的实现说明
└── requirements.txt
```

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env   # 按需编辑

# 终端 1：API
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 终端 2：看板
streamlit run dashboard/app.py
```

- API 文档：<http://localhost:8000/docs>
- 看板默认：<http://localhost:8501>（默认请求本机 `8000` 端口 API）

## 数据流

```
Streamlit  ──HTTP──►  FastAPI (/api/trades, /api/portfolio, /api/market)
                          │
                          ▼
                    ORM + SQLite (finance_data.db)
                          │
                    data_fetcher (AkShare) ← 持仓汇总取价
```

## 外部依赖

| 依赖 | 用途 |
|-----|------|
| AkShare | 行情与标的名录 |
| SQLite | 本地数据库（Python 内置） |

## 贡献与测试

- 修改代码时保持现有模块划分；重大行为变更请同步 `CLAUDE.md`。
- `pytest tests/`

## License

MIT
