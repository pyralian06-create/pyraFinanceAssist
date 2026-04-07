# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Contents

个人金融辅助分析工具 — **当前实现说明**（后端 FastAPI `v0.1.0` + Streamlit 看板）。架构为「本地 SQLite + 内存计算」，数据不出本机。**不包含**盯盘、告警规则、微信推送等功能。

### 已实现能力概览

| 能力 | 状态 |
| :--- | :--- |
| 交易流水 CRUD（SQLite） | 已实现：`/api/trades` |
| 持仓与盈亏（加权平均成本、已实现/浮动盈亏） | 已实现：`/api/portfolio/summary` |
| 多资产行情接入（AkShare + 统一路由） | 已实现：`app/data_fetcher/`（A 股 / 港股 / 美股 / 基金 / 现货黄金） |
| 市场标的搜索与校验（录入辅助） | 已实现：`/api/market/search`、`/api/market/validate/{symbol}` |
| Streamlit 看板 | 已实现：主页持仓+流水；子页「交易录入」 |

---

## 1. 技术栈与运行方式

- **语言**：Python 3.10+
- **后端**：FastAPI、Uvicorn、SQLAlchemy 2.x、Pydantic v2
- **数据**：SQLite（默认 `./finance_data.db`，见 `app/config.py` 的 `database_url`）
- **行情**：AkShare（`app/data_fetcher/` 按资产类型路由）
- **前端**：Streamlit + Plotly + httpx 调用后端 API
- **配置**：`.env`（`pydantic-settings` 读取数据库与日志等）

启动示例：

```bash
pip install -r requirements.txt
# 终端 1
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# 终端 2
streamlit run dashboard/app.py
```

应用启动时会执行：`init_db()`；并触发 `app/services/market_info.sync_market_symbols()` 在后台线程同步全市场标的名录到 `market_symbols` 表。

---

## 2. 代码布局

```
app/
├── main.py              # FastAPI 入口、路由挂载、生命周期
├── config.py            # 全局配置
├── models/              # ORM：Trade, MarketSymbol
├── schemas/             # Pydantic：请求/响应模型
├── data_fetcher/        # 行情：router, stock_a, stock_hk, stock_us, fund, gold, schemas
├── pnl_engine/          # calculate_portfolio() 盈亏引擎
├── services/            # market_info（标的同步）
├── api/                 # trades, portfolio, market
├── ledger/              # 仅占位 __init__.py（业务在 api 层直接调 ORM）

dashboard/
├── app.py               # 持仓看板 + 交易流水列表
└── pages/
    └── 01_trade_entry.py  # 交易录入（含市场搜索）
```

---

## 3. 数据库（SQLite）

库文件默认：`finance_data.db`。

### 表 `trades`（交易流水）

| 字段 | 说明 |
| :--- | :--- |
| id | 主键 |
| asset_type, symbol | 资产大类与代码（如 `STOCK_A`、`STOCK_HK`、`STOCK_US`、`FUND`、`GOLD_SPOT` 等） |
| trade_date, trade_type | 时间与类型（BUY / SELL / DIVIDEND） |
| price, quantity, commission | Numeric(18,6) |
| notes | 备注 |
| created_at | 记录创建时间 |

### 表 `market_symbols`（市场标的缓存）

用于搜索与校验：symbol、name、asset_type、pinyin、is_active、updated_at 等（见 `app/models/market_symbol.py`）。

若本地数据库是旧版本且仍含已废弃的 `alert_rules` 表，可忽略或自行用 SQLite 工具删除，不影响当前代码。

---

## 4. HTTP API（当前实现）

前缀均为相对 `http://localhost:8000`（开发默认）。

**系统**

- `GET /` — API 信息
- `GET /health` — 健康检查

**交易**

- `POST /api/trades` — 创建
- `GET /api/trades` — 列表，查询参数：`asset_type`、`symbol`
- `GET /api/trades/{trade_id}` — 单条
- `PATCH /api/trades/{trade_id}` — 部分更新
- `DELETE /api/trades/{trade_id}` — 删除

**持仓**

- `GET /api/portfolio/summary` — 持仓汇总；查询参数：`asset_type`（可选）

**市场**

- `GET /api/market/search?q=...&limit=...` — 模糊搜索标的
- `GET /api/market/validate/{symbol}` — 校验代码是否存在

Swagger：`/docs`。

---

## 5. 数据接入模块（`app/data_fetcher`）

- **统一入口**：`get_quote` / `get_quote_batch_direct`、`get_history`（见 `router.py`）。
- **支持资产类型**：`STOCK_A`、`STOCK_HK`、`STOCK_US`、`FUND`、`GOLD_SPOT`。
- **持仓汇总取价**：`pnl_engine` 通过 `get_quote_batch_direct` 并发拉取最新价。

---

## 6. 盈亏引擎（`app/pnl_engine`）

- 按时间排序流水，加权平均成本；卖出时计入已实现盈亏；再结合行情计算浮动盈亏与汇总字段。
- 单元测试见 `tests/test_pnl_engine.py`。

---

## 7. 前端看板（Streamlit）

- **`dashboard/app.py`**：指标卡片、资产筛选、饼图、持仓表、交易流水与删除。
- **`dashboard/pages/01_trade_entry.py`**：交易录入与市场搜索。

默认 `API_BASE = http://localhost:8000/api`。

---

## 8. 可选后续

- **`app/ledger` 独立服务层**：当前 CRUD 在 `app/api/trades.py` 内直接操作 ORM。

---

## 9. 文档与测试

- 专项说明可参考仓库内 `DATA_FETCHER_COMPLETE.md`、`PNL_ENGINE_COMPLETE.md` 等（以代码为准）。
- 测试：`pytest tests/`。
