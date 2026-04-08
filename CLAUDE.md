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
| **每日持仓收益**（leg 持久化 + 组合曲线 + 今日盈亏） | 已实现：`/api/portfolio/daily-pnl`、`/api/portfolio/today-pnl` |
| Streamlit 看板 | 已实现：主页持仓+流水；「交易录入」；「每日收益看板」 |

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
├── models/              # ORM：Trade, MarketSymbol, PositionDailyMark
├── schemas/             # Pydantic：请求/响应模型（含 daily_pnl.py）
├── data_fetcher/        # 行情：router, stock_a, stock_hk, stock_us, fund, gold, schemas
├── pnl_engine/          # 盈亏引擎：calculator, position_state, daily_pnl
├── services/            # market_info（标的同步）、fx（汇率）
├── api/                 # trades, portfolio, market
├── ledger/              # 仅占位 __init__.py（业务在 api 层直接调 ORM）

dashboard/
├── app.py               # 持仓看板 + 交易流水列表
└── pages/
    ├── 01_trade_entry.py  # 交易录入（含市场搜索）
    └── 02_daily_pnl.py    # 每日持仓收益看板
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
| price, quantity, commission | Numeric(18,6)，**港美股 price 已折算为人民币** |
| notes | 备注 |
| created_at | 记录创建时间 |

### 表 `market_symbols`（市场标的缓存）

用于搜索与校验：symbol、name、asset_type、pinyin、is_active、updated_at 等（见 `app/models/market_symbol.py`）。

### 表 `position_daily_marks`（日度持仓估值明细）

每行存某自然日、某标的的日终快照，**全部以人民币（CNY）计价**：

| 字段 | 说明 |
| :--- | :--- |
| mark_date | 估值日期（DATE） |
| asset_type, symbol | 资产标识 |
| quantity_eod | 日终持仓数量 |
| close_price_cny | 收盘价（CNY，港美股已乘汇率） |
| fx_rate | 汇率快照（A 股 / 基金 / 黄金为 1.0） |
| market_value_cny | 日终市值（CNY） |
| daily_pnl_cny | 当日 leg 盈亏（相对上一有效日同标的市值） |
| daily_pnl_percent | 当日 leg 收益率（%），分母为上一有效日市值，可为 null |
| created_at / updated_at | 系统字段 |

唯一约束：`(mark_date, asset_type, symbol)`，支持 upsert 刷新。

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

- `GET /api/portfolio/summary` — 实时持仓汇总（加权成本+浮盈）；查询参数：`asset_type`（可选）
- `GET /api/portfolio/today-pnl` — 今日盈亏（相对上一交易日收盘，金额+百分比）
- `GET /api/portfolio/daily-pnl?start=&end=` — 历史区间组合日曲线（从 `position_daily_marks` 聚合）
- `GET /api/portfolio/daily-pnl/legs?start=&end=&symbol=&asset_type=` — leg 明细
- `POST /api/portfolio/daily-pnl/refresh?start=&end=` — 重算并写入指定区间 leg 数据

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

### 实时快照（`calculator.py`）

按时间排序流水，加权平均成本；卖出时计入已实现盈亏；结合行情计算浮动盈亏与汇总字段。

### 核心持仓状态（`position_state.py`）

- `PositionState`：持仓快照数据类
- `process_trades(trades)` — 处理全量交易
- `process_trades_up_to(trades, cutoff_date)` — 截止某日快照（用于历史回放）

### 每日收益计算（`daily_pnl.py`）

**口径**：收盘价市值变动（D 日相对 D-1 日），缺交易日前向填充。

- `rebuild_daily_marks(db, start, end)` — 重算区间，upsert `position_daily_marks`
- `query_portfolio_daily_series(db, start, end)` — GROUP BY 聚合，返回组合日曲线（含累计盈亏）
- `query_leg_daily_series(db, start, end, symbol?, asset_type?)` — 查 leg 明细
- `get_today_pnl(db)` — 今日盈亏（优先读库，无数据则实时估算）

### 汇率（`app/services/fx.py`）

- 数据源：AkShare `currency_boc_safe` 中间价（100 外币 → CNY）
- 缺某日汇率时前向填充；AkShare 不可用时使用静态兜底值
- `get_fx_rate_for_asset(asset_type, date)` — 统一入口
- `preload_fx_rates(start, end)` — 批量预加载（减少 rebuild 中的重复请求）

---

## 7. 前端看板（Streamlit）

- **`dashboard/app.py`**：指标卡片、资产筛选、饼图、持仓表、交易流水与删除。
- **`dashboard/pages/01_trade_entry.py`**：交易录入与市场搜索。
- **`dashboard/pages/02_daily_pnl.py`**：每日收益看板
  - 今日盈亏 4 格指标（市值、金额、百分比、数据来源）
  - 历史日曲线 3 个 tab（日盈亏柱状图、累计盈亏折线、持仓市值折线）
  - 各标的贡献堆叠柱状图 + leg 明细数据表
  - 左侧侧边栏：日期区间快选、金额/百分比切换、重算触发按钮

默认 `API_BASE = http://localhost:8000/api`。

---

## 8. 币种说明（多市场）

- **统一本币**：组合内所有估值均以 **人民币（CNY）** 展示。
- `STOCK_HK`（港股）：price 字段已折算 CNY；历史 K 线用 HKD/CNY 中间价换算。
- `STOCK_US`（美股）：price 字段已折算 CNY；历史 K 线用 USD/CNY 中间价换算。
- 汇率来源：AkShare 外汇局中间价，缺失时前向填充。多市场交易日不同，按日历日循环分标的前向填充，存在小量汇兑噪声。

---

## 9. 可选后续

- **`app/ledger` 独立服务层**：当前 CRUD 在 `app/api/trades.py` 内直接操作 ORM。

---

## 10. 文档与测试

- 测试：`pytest tests/`（含 `test_pnl_engine.py` 与 `test_daily_pnl.py`）。
