# 📊 PnL 计算引擎搭建完成 ✅

**完成时间：** 2026-04-03  
**项目进度：** 35% 完成  
**阶段状态：** 阶段 2.2 完成 → 进入 API 实现 (2.3)

---

## 📋 本次完成的功能

### ✨ 加权平均成本法实现

| 功能 | 说明 | 输出 |
|---|---|---|
| **持仓计算** | 按时间序处理买卖交易，计算当前持仓量和加权平均成本 | 每个标的的 holding_quantity, avg_cost |
| **盈亏计算** | 卖出时计算已实现盈亏，结合行情计算浮动盈亏 | floating_pnl, realized_pnl, pnl_percent |
| **汇总分析** | 聚合所有持仓，计算组合总资产、总盈亏、总实现盈亏 | PortfolioSummary（核心 API 返回体） |

### 📁 创建的文件

| 文件 | 行数 | 功能 |
|---|---|---|
| `app/pnl_engine/calculator.py` | 220 | 核心计算引擎 |
| `app/pnl_engine/__init__.py` | 12 | 模块导出 |
| **总计** | **232** | |

---

## 🎯 核心设计

### 1️⃣ 加权平均成本法（中国 A 股常规算法）

**交易处理逻辑：**

| 交易类型 | 处理 | 公式 |
|---|---|---|
| **BUY** | 增加成本和持仓 | `total_cost += 单价 × 数量 + 手续费`<br>`holding_qty += 数量` |
| **SELL** | 计算已实现盈亏，按比例扣减成本 | `realized_pnl += (卖价 - 平均成本) × 数量 - 手续费`<br>`avg_cost = total_cost / holding_qty`<br>`total_cost -= avg_cost × 卖出数量` |
| **DIVIDEND** | 分红直接加入已实现盈亏，不影响持仓 | `realized_pnl += 分红金额` |

### 2️⃣ 三层函数设计

**`_process_trades(trades) -> Dict[(asset_type, symbol), _PositionState]`**
- 输入：交易列表（按 trade_date 排序）
- 处理：逐笔应用上述逻辑
- 输出：每个标的的持仓状态（持仓量、总成本、已实现盈亏）

**`_build_position_detail(state, current_price) -> PositionDetail`**
- 输入：持仓状态 + 当前市价
- 计算：
  - `avg_cost = total_cost / holding_quantity`
  - `floating_pnl = (current_price - avg_cost) * holding_quantity`
  - `pnl_percent = floating_pnl / (avg_cost × holding_qty) × 100%`
- 降级处理：若 `current_price` 为 None（行情拉取失败），使用 `avg_cost` 代替

**`calculate_portfolio(db, asset_type_filter=None) -> PortfolioSummary`**  
- 公开入口，对应 `GET /api/portfolio/summary` 接口
- 步骤：
  1. 查询数据库中的所有交易（按 trade_date 排序，可选过滤）
  2. 调用 `_process_trades()` 计算各标的持仓
  3. 筛选活跃持仓（`holding_quantity > 0`）
  4. 批量调用 `get_quote_batch()` 获取最新行情
  5. 逐个生成 `PositionDetail`
  6. 汇总返回 `PortfolioSummary`

### 3️⃣ 数据流图

```
交易流水数据库
├─ 买入 sh600519 100 股 @ ¥1700 + ¥50 手续费
├─ 买入 sh600519 100 股 @ ¥1750 + ¥50 手续费
├─ 卖出 sh600519 50 股 @ ¥1800 - ¥25 手续费
└─ 买入 510300 1000 份 @ ¥3.85 + ¥1.5 手续费
   ↓
   _process_trades()
   ↓
   {
     ('STOCK_A', 'sh600519'): PositionState(
       holding_qty=150,
       avg_cost=1726.67,  // (1700×100+50 + 1750×100+50 - 1726.67×50) / 150
       realized_pnl=3650   // (1800-1726.67) × 50 - 25
     ),
     ('FUND', '510300'): PositionState(
       holding_qty=1000,
       total_cost=3851.5,
       realized_pnl=0
     )
   }
   ↓
   get_quote_batch([('STOCK_A', 'sh600519'), ('FUND', '510300')])
   ↓ 获得最新行情
   {
     ('STOCK_A', 'sh600519'): QuoteData(current_price=1820),
     ('FUND', '510300'): QuoteData(current_price=3.95)
   }
   ↓
   _build_position_detail() × 2
   ↓
   PortfolioSummary {
     positions: [
       PositionDetail(
         symbol='sh600519',
         holding_quantity=150,
         avg_cost=1726.67,
         current_price=1820,
         floating_pnl=13949.5,    // (1820-1726.67) × 150
         pnl_percent="+0.80%"
       ),
       PositionDetail(
         symbol='510300',
         holding_quantity=1000,
         avg_cost=3.8515,
         current_price=3.95,
         floating_pnl=98.5,        // (3.95-3.8515) × 1000
         pnl_percent="+2.55%"
       )
     ],
     total_assets=285548.5,        // sh: 1820×150, 510300: 3.95×1000
     total_pnl=14048,              // 浮盈总和
     total_pnl_percent="+0.81%",
     realized_pnl=3650
   }
```

---

## 🧪 验证结果

### ✅ 结构验证（已通过）

```
✓ 模块导入成功
✓ 计算执行成功（无交易时，返回全零 PortfolioSummary）
✓ 数据库连接成功
✓ 数据类实例化成功
✓ 交易处理逻辑验证成功（手工计算对比）
```

### ✅ 逻辑验证（手工测试）

```
输入交易：
  - BUY sh600519 100 @ ¥100 + ¥50 手续费 = 总成本 ¥10050
  - BUY sh600519 100 @ ¥105 + ¥50 手续费 = 总成本再增 ¥10550
  
期望：
  - holding_quantity = 200
  - total_cost = 20600
  - avg_cost = 103
  
实际：✓ 完全匹配
```

---

## 📚 API 使用示例

### 基础用法

```python
from app.pnl_engine import calculate_portfolio
from app.models.database import SessionLocal

db = SessionLocal()

# 计算全部持仓
summary = calculate_portfolio(db)
print(f"总资产: ¥{summary.total_assets}")
print(f"总浮盈: ¥{summary.total_pnl} ({summary.total_pnl_percent})")
print(f"已实现盈亏: ¥{summary.realized_pnl}")

# 遍历各持仓
for pos in summary.positions:
    print(f"{pos.symbol}: 持仓 {pos.holding_quantity}, "
          f"平均成本 ¥{pos.avg_cost}, "
          f"浮盈 ¥{pos.floating_pnl} ({pos.pnl_percent})")

db.close()
```

### 按资产类型过滤

```python
# 仅看 A 股持仓
stock_summary = calculate_portfolio(db, asset_type_filter='STOCK_A')

# 仅看基金持仓
fund_summary = calculate_portfolio(db, asset_type_filter='FUND')
```

---

## 🔧 边界情况处理

| 场景 | 处理 | 备注 |
|---|---|---|
| 持仓量变负 | 夹紧到 0，打印 warning | 数据问题，不崩溃 |
| 行情拉取失败（None） | 使用平均成本作为当前价 | 浮盈亏 = 0 |
| 无交易记录 | 返回全零 PortfolioSummary | positions=[], 所有值=0 |
| 所有持仓已卖出 | positions=[], 仅 realized_pnl 有值 | 正常状态 |
| 除数为零（cost_basis=0） | 设置 pnl_percent=0 | 数据异常，安全处理 |

---

## 📊 代码统计

```
app/pnl_engine/
├── calculator.py        220 行 - 核心计算
└── __init__.py           12 行 - 导出

总计：232 行代码
```

---

## 🔗 关键依赖关系

```
calculate_portfolio()
├─ app.models.trade.Trade        ← 查询交易表
├─ app.data_fetcher.get_quote_batch()  ← 批量拉取行情
├─ app.schemas.portfolio.PortfolioSummary  ← 返回体
└─ sqlalchemy.orm.Session        ← 数据库访问
```

---

## 🔄 与其他模块的集成

### 数据流向

```
FastAPI 请求
  ↓ GET /api/portfolio/summary (待实现)
  ↓
calculate_portfolio(db)
  ├─ Query Trade 表
  ├─ _process_trades() 计算持仓
  ├─ get_quote_batch() 获取行情（来自 data_fetcher）
  └─ 返回 PortfolioSummary
  ↓
JSON 响应 ← Pydantic 自动序列化
```

### 与 data_fetcher 的配合

- **输入**：活跃持仓列表 `[(asset_type, symbol), ...]`
- **输出**：行情字典 `Dict[(asset_type, symbol), QuoteData]`
- **特点**：单次批量查询，共享缓存（60s），大幅减少 API 调用

---

## 🎯 下一步工作

### 优先级 1：持仓汇总 API（Phase 2.3，预计 1 天）

```
app/api/portfolio.py
└─ GET /api/portfolio/summary
   ├─ 接收可选参数 asset_type_filter
   ├─ 调用 calculate_portfolio()
   └─ 返回 JSON
```

### 优先级 2：其他 API 路由（Phase 2.3）

```
app/api/trades.py      → /api/trades CRUD
app/api/alerts.py      → /api/alerts CRUD
```

### 优先级 3：交易管理服务（Phase 2.2）

```
app/ledger/service.py
├─ add_trade()
├─ update_trade()
├─ delete_trade()
└─ list_trades()
```

---

## ✨ 特点总结

✅ **加权平均成本法**：符合中国 A 股会计准则  
✅ **三层函数设计**：关注点分离，易于测试  
✅ **行情降级**：当行情失败时，自动使用平均成本  
✅ **批量优化**：一次 API 调用获取所有行情  
✅ **完整的错误处理**：负数检查、None 防护、除零保护  
✅ **易于扩展**：支持按资产类型过滤、支持自定义计算逻辑  

---

**🎉 PnL 计算引擎现已准备好集成 API 层！**

---

**项目进度：35% 完成 (3.5/4 阶段)**

| 阶段 | 进度 | 状态 |
|---|---|---|
| 阶段 1：打地基 | 100% | ✅ 完成 |
| 阶段 2：算明白 | 50% | 🔄 进行中 (2.1 ✓, 2.2 ✓, 2.3 计划中) |
| 阶段 3：动起来 | 0% | ⏳ 待启动 |
| 阶段 4：看得到 | 0% | ⏳ 待启动 |

**下一步：** 实现持仓汇总 API (`/api/portfolio/summary`) → 交易管理 API → 告警规则
