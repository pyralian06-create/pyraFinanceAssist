# 数据获取模块 - 完整规格说明

**更新时间：** 2026-04-03  
**模块位置：** `app/data_fetcher/`  
**状态：** ✅ 已实现  

---

## 概述

数据获取模块是系统的"数据泵"，负责从 AkShare 获取多资产实时行情和历史数据。

### 核心职责

1. **多源路由**：根据 asset_type 自动路由到不同的 AkShare 接口
2. **实时行情**：获取当前价格、涨跌幅、成交量等
3. **历史 K线**：拉取日线数据供图表展示和技术分析
4. **缓存优化**：大量操作一次 API 调用，减少网络延迟
5. **统一接口**：屏蔽各资产类型的 API 差异

### 数据流向

```
FastAPI 路由层
    ↓
app/api/portfolio.py (持仓汇总)
    ↓
app/pnl_engine/calculator.py (P&L 计算)
    ↓
app/data_fetcher/router.py ← 入口
    ↓
┌─────────────────────────┐
│  stock_a.py    fund.py  │  gold.py
│  (A股)    (ETF/LOF/开放) │  (黄金)
└─────────────────────────┘
    ↓
AkShare API → 上交所/深交所/基金公司/SGE
```

---

## 统一输出格式：QuoteData

所有资产类型返回统一的 `QuoteData` 结构，供上层模块使用：

```python
@dataclass
class QuoteData:
    symbol: str              # 资产代码
    name: str                # 资产名称
    current_price: Decimal   # 当前价格 ✅
    previous_close: Decimal  # 昨日收盘价（用于验证涨跌幅计算）
    change_amount: Decimal   # 涨跌额
    change_pct: float        # 涨跌幅 %（如 2.35 = +2.35%）
    volume: Optional[float]  # 成交量（黄金为 None）
    timestamp: datetime      # 数据时间戳
    asset_type: str          # STOCK_A / FUND / GOLD_SPOT
```

### 用途映射

| QuoteData 字段 | 持仓 PnL 计算 | 实时告警 |
|---|---|---|
| `current_price` | ✅ 持仓价值 = 持仓量 × current_price | ✅ PRICE 告警 |
| `change_pct` | ✅ 浮动收益率 | ✅ CHANGE_PCT 告警 |
| `volume` | ❌ 无 | ✅ VOLUME 告警 |

---

## 第一部分：A股 (asset_type = "STOCK_A")

### 需要获取的数据

| 数据项 | 来源 API | 字段名 | 说明 |
|---|---|---|---|
| 当前价格 | `stock_zh_a_spot_em()` | `最新价` | ✅ 用于持仓价值计算 |
| 昨日收盘 | `stock_zh_a_spot_em()` | `昨收` | 用于涨跌幅计算 |
| 涨跌幅 | `stock_zh_a_spot_em()` | `涨跌幅` | ✅ 用于 CHANGE_PCT 告警 |
| 涨跌额 | `stock_zh_a_spot_em()` | `涨跌额` | 展示用 |
| 成交量 | `stock_zh_a_spot_em()` | `成交量` | ✅ 用于 VOLUME 告警 |
| 股票名称 | `stock_zh_a_spot_em()` | `名称` | 展示用 |

### API 使用

#### 实时行情（优化版：批量拉取全市场）

```python
# 一次 API 调用，获取 ~5000 只股票
df = ak.stock_zh_a_spot_em()

# 在内存中缓存 60 秒，多次查询直接过滤：
df[df['代码'] == '600519']
```

**关键信息：**
- 拉取全市场 (~5000 只) 可能需要 1-3 分钟
- **我们缓存 60 秒**，同时期间多个 get_quote() 调用只执行一次 API
- 列名注意：项目用 `sh600519`（带前缀），AkShare 用 `600519`（无前缀）→ 代码需要去前缀

#### 历史 K线（按单个股票查询，不慢）

```python
# 单个股票查询，无需缓存
df = ak.stock_zh_a_hist(
    symbol='600519',              # 不带前缀
    period='daily',
    start_date='20250101',        # YYYYMMDD 格式
    end_date='20251231',
    adjust=''                     # '' 原始价格，与成本计算一致
)
```

**关键信息：**
- 返回该股票的所有历史日线
- `adjust=''` 建议用于成本计算（保持原始价格）
- 不需要缓存（单股票查询快速）

---

## 第二部分：基金 (asset_type = "FUND")

基金类型复杂，需要自动识别三个子类型：

### 基金类型识别规则

```python
def _detect_fund_type(symbol: str) -> str:
    """
    根据 6 位代码识别基金类型
    """
    if symbol.startswith('159'):          # 深交所 QDII/ETF
        return "ETF"
    elif symbol.startswith('5') and 500 < int(symbol[:3]) < 520:
        return "ETF"                      # 上交所 ETF (501-519)
    elif symbol.startswith(('1', '5')):
        return "LOF"                      # 其他交易所基金
    else:
        return "OPEN"                     # 开放式基金 (0xxxxx, 2xxxxx 等)
```

### 子类型 1：ETF（交易所交易基金）

#### 代码示例
- `510300` - 上交所 ETF（沪深 300）
- `159915` - 深交所 ETF（创业板 50）

#### 需要获取的数据

| 数据项 | 来源 API | 字段名 |
|---|---|---|
| 当前市价 | `fund_etf_spot_em()` | `最新价` | ✅ 实时市价（非净值）
| 昨日收盘 | `fund_etf_spot_em()` | `昨收` |
| 涨跌幅 | `fund_etf_spot_em()` | `涨跌幅` | ✅
| 成交量 | `fund_etf_spot_em()` | `成交量` | ✅

#### API 使用

```python
# 实时行情：一次拉取全市场 ETF，缓存 60s
df = ak.fund_etf_spot_em()
df[df['代码'] == '510300']

# 历史 K线：按单个 ETF 查询
df = ak.fund_etf_hist_em(
    symbol='510300',
    period='daily',
    start_date='20250101',
    end_date='20251231'
)
```

### 子类型 2：LOF（上市开放式基金）

#### 代码示例
- `166009` - 上交所 LOF
- `164821` - 深交所 LOF

#### API 使用

```python
# 实时行情
df = ak.fund_lof_spot_em()        # 全市场 LOF
df[df['代码'] == '166009']

# 历史 K线
df = ak.fund_lof_hist_em(
    symbol='166009',
    period='daily',
    start_date='20250101',
    end_date='20251231'
)
```

### 子类型 3：开放式基金（T+1 净值）

#### 代码示例
- `005827` - 南方养老 2035（6 位数，0 开头）

#### 需要获取的数据

| 数据项 | 来源 API | 说明 |
|---|---|---|
| 当前净值 | `fund_open_fund_daily_em()` | **T+1 净值** ⚠️ 不是实时市价 |
| 日增长率 | `fund_open_fund_daily_em()` | 昨日净值 vs 前日净值 |

#### 关键限制

- **无实时市价**：开放式基金仅提供 T+1 净值（每天更新一次）
- **无成交量**：开放式基金无二级市场成交量
- **动态列名**：当日净值列名为 `"YYYY-MM-DD-单位净值"`，需要动态解析

#### API 使用

```python
# 当前净值（T+1）
df = ak.fund_open_fund_daily_em()
# 列名示例：基金代码, 基金简称, 2026-04-03-单位净值, 日增长率, ...
row = df[df['基金代码'] == '005827']
nav_col = [col for col in row.columns if col.endswith('-单位净值')][0]
current_nav = row[nav_col].values[0]

# 历史净值（全部历史）
df = ak.fund_open_fund_info_em(
    symbol='005827',
    indicator='单位净值走势',
    period='成立来'  # 获取全部历史
)
```

---

## 第三部分：黄金 (asset_type = "GOLD_SPOT")

### 需要获取的数据

| 数据项 | 来源 API | 说明 |
|---|---|---|
| 实时现价 | `spot_quotations_sge()` | 上海黄金交易所 |
| 历史收盘价 | `spot_hist_sge()` | 全部历史 K 线 |

### 关键限制

⚠️ **SGE 不提供成交量** → **VOLUME 告警对黄金不可用**

### 支持的品种

```python
symbol = 'Au99.99'      # ✅ 最常用（上海黄金基础交易品种）
symbol = 'Au99.95'      # 高纯度
symbol = 'Au(T+D)'      # 黄金延期（类似期货）
```

### API 使用

#### 实时行情（with fallback）

```python
# 尝试实时 tick（交易时间才有）
df = ak.spot_quotations_sge(symbol='Au99.99')

# 如果为空（非交易时间），fallback 到历史最后一行
if df.empty:
    df = ak.spot_hist_sge('Au99.99')
    current_price = df.iloc[-1]['close']
```

#### 历史数据（全量，无日期过滤）

```python
# 注意：无 start_date / end_date 参数
df = ak.spot_hist_sge(symbol='Au99.99')
# 返回该品种全部历史（通常 2000+ 条）

# 列名：date, open, close, high, low（无 volume）
```

---

## 公开 API 使用示例

### 导入

```python
from app.data_fetcher import get_quote, get_quote_batch, get_history
from app.data_fetcher.schemas import QuoteData, HistoricalBar
```

### 单个查询

```python
# A股
quote = get_quote('STOCK_A', 'sh600519')
print(f"{quote.name}: ¥{quote.current_price}, 涨跌{quote.change_pct}%")

# 基金 ETF
quote = get_quote('FUND', '510300')

# 基金 开放式
quote = get_quote('FUND', '005827')

# 黄金
quote = get_quote('GOLD_SPOT', 'Au99.99')
print(f"黄金: ¥{quote.current_price}/克")
```

### 批量查询（推荐用于持仓汇总）

```python
# 一次性获取多个持仓的最新价格
positions = [
    ('STOCK_A', 'sh600519'),
    ('STOCK_A', 'sh000001'),
    ('FUND', '510300'),
    ('FUND', '005827'),
    ('GOLD_SPOT', 'Au99.99'),
]

quotes = get_quote_batch(positions)

# quotes = {
#     ('STOCK_A', 'sh600519'): QuoteData(...),
#     ('STOCK_A', 'sh000001'): QuoteData(...),
#     ('FUND', '510300'): QuoteData(...),
#     ...
# }

total_value = sum(
    q.current_price * position.quantity
    for (asset_type, symbol), q in quotes.items()
    for position in get_positions_by_symbol(asset_type, symbol)
)
```

### 历史数据

```python
# A股 历史数据
bars = get_history('STOCK_A', 'sh600519', start_date='20250101', end_date='20251231')
for bar in bars:
    print(f"{bar.date}: open={bar.open}, close={bar.close}, vol={bar.volume}")

# 基金历史净值
bars = get_history('FUND', '005827')

# 黄金历史（无日期过滤）
bars = get_history('GOLD_SPOT', 'Au99.99')
```

---

## 缓存策略

### 为什么需要缓存？

- **A股全市场**：一次 API 调用返回 ~5000 只股票，耗时 1-3 分钟
- **基金全市场**：ETF/LOF/开放式基金的 bulk API 也很慢
- **批量持仓查询**：通常需要查询 5-20 个持仓，缓存避免重复调用

### 缓存配置

| 来源 | 缓存 TTL | 原因 |
|---|---|---|
| `stock_zh_a_spot_em()` | 60 秒 | A股实时行情，60s 内变化不大 |
| `fund_etf_spot_em()` | 60 秒 | ETF 实时行情 |
| `fund_lof_spot_em()` | 60 秒 | LOF 实时行情 |
| `fund_open_fund_daily_em()` | 60 秒 | 开放式基金 T+1 净值 |
| `spot_hist_sge()` | 300 秒 | 黄金历史数据，变化不频繁 |

### 使用示例

```python
# 第一次查询：执行 API 调用 + 缓存
quote1 = get_quote('STOCK_A', 'sh600519')  # 慢 (~1-3 分钟)

# 第二次查询（同一秒内）：直接从缓存读取
quote2 = get_quote('STOCK_A', 'sh000001')  # 快 (~1 ms)

# 60 秒后：缓存过期，重新执行 API 调用
quote3 = get_quote('STOCK_A', 'sh600519')  # 慢
```

---

## 性能预期

### 首次运行

- **A股全市场拉取**：1-3 分钟（AkShare 从多个数据源聚合）
- **基金全市场拉取**：30-60 秒
- **黄金实时报价**：2-5 秒

### 缓存命中

- **单个查询**：< 10 ms
- **批量查询 (10 个持仓)**：< 100 ms

---

## 已知限制 & 处理方案

### 限制 1：黄金无成交量

```
问题：VOLUME 告警对黄金无效（SGE 不公布成交量）
方案：
  a) 前端禁止为 GOLD_SPOT 创建 VOLUME 告警
  b) 后端在 monitor 规则引擎检查时跳过
  c) AlertRule 模型添加 supported_metrics 字段
```

### 限制 2：开放式基金无实时市价

```
问题：fund_open_fund_daily_em() 仅返回 T+1 净值，不是实时市价
方案：
  • PnL 计算使用 T+1 净值（合理，基金本身无实时买卖价格）
  • 实时监控基金价格的用户应该改用 ETF
```

### 限制 3：第一次 API 调用很慢

```
问题：stock_zh_a_spot_em() 一次拉取全市场，可能 1-3 分钟
方案：
  a) 应用启动时预加载缓存（lifespan 中调用一次）
  b) 或第一次 /api/portfolio 请求时，用户等待 1-3 分钟
  c) 后台使用 asyncio 异步加载（Phase 3）
```

---

## 下一步工作

1. **在 `app/main.py` 的 lifespan 中预加载缓存**
   ```python
   @asynccontextmanager
   async def lifespan(app: FastAPI):
       # ... 现有初始化代码
       
       # 预加载数据获取缓存（避免首次查询等待）
       try:
           stock_a._get_spot_data_cached()
       except:
           pass
   ```

2. **实现 `app/api/portfolio.py`** 利用 `get_quote_batch()` 汇总持仓

3. **实现 `app/pnl_engine/calculator.py`** 利用 QuoteData 计算盈亏

4. **实现告警规则验证** 跳过黄金的 VOLUME 告警

---

## 文件清单

| 文件 | 职责 | 行数 |
|---|---|---|
| `schemas.py` | QuoteData / HistoricalBar 数据类 | 50 |
| `stock_a.py` | A股 实时 + 历史 | 160 |
| `fund.py` | 基金 (ETF/LOF/开放) 实时 + 历史 | 360 |
| `gold.py` | 黄金 实时 + 历史 + fallback | 180 |
| `router.py` | 统一路由 + 批量查询 | 160 |
| `__init__.py` | 模块导出 | 30 |
| **总计** | | **940** |

---

## 验证清单

- ✅ 所有模块导入成功
- ✅ 数据类实例化成功
- ✅ 函数签名完整
- ✅ 缓存机制就位
- ✅ 基金类型自动识别正确
- ✅ 异常处理覆盖主要路径
- ⏳ 待测：实际 API 调用（取决于网络和 AkShare 服务可用性）

---

**项目进度：阶段 2.1 完成 (完整的数据获取基础设施)**
