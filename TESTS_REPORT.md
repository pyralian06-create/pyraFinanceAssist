# 🧪 PnL 计算引擎单元测试报告

**测试时间：** 2026-04-03  
**测试框架：** pytest  
**覆盖率：** 12 个测试用例，100% 通过  

---

## 📋 测试概览

| 测试类别 | 用例数 | 状态 | 说明 |
|---|---|---|---|
| **基础交易** | 4 | ✅ 全通过 | 空持仓、单买、买卖、分红 |
| **加权平均成本** | 2 | ✅ 全通过 | 成本计算、多资产组合 |
| **行情降级处理** | 2 | ✅ 全通过 | 完全失败、部分失败 |
| **资产类型过滤** | 1 | ✅ 全通过 | 按资产类型筛选持仓 |
| **边界情况** | 3 | ✅ 全通过 | 零手续费、小数份额、大数字 |
| **总计** | **12** | **✅ 全通过** | 无失败，无跳过 |

---

## ✅ 测试用例详解

### 基础交易（TestBasicTrades）

#### 1. `test_empty_portfolio` — 空持仓
**目的：** 验证数据库中无交易时的行为  
**场景：** 无任何交易记录  
**预期：** 返回全零的 PortfolioSummary  
**结果：** ✅ PASS

```
输入：空交易列表
输出：
  - total_assets: 0
  - total_pnl: 0
  - realized_pnl: 0
  - positions: []
```

#### 2. `test_single_buy` — 单个买入
**目的：** 验证买入交易和加权平均成本计算  
**场景：**
```
交易：买入 100 股 @ ¥100 + ¥50 手续费
行情：当前价 ¥110
```
**验证点：**
- 持仓数量：100 股 ✓
- 平均成本：(100×100 + 50) / 100 = ¥100.5 ✓
- 浮动盈亏：(110 - 100.5) × 100 = ¥950 ✓
- 盈亏比例：950 / 10050 × 100% = +9.45% ✓

**结果：** ✅ PASS

#### 3. `test_buy_and_sell` — 买入+卖出
**目的：** 验证已实现盈亏的计算  
**场景：**
```
交易 1：买入 100 股 @ ¥100 + ¥50 手续费
交易 2：卖出 50 股 @ ¥120 - ¥25 手续费
行情：当前价 ¥125
```
**验证点：**
- 剩余持仓：50 股 ✓
- 已实现盈亏：(120 - 100.5) × 50 - 25 = ¥950 ✓
- 平均成本：仍为 ¥100.5 ✓
- 浮动盈亏：(125 - 100.5) × 50 = ¥1225 ✓

**结果：** ✅ PASS

#### 4. `test_dividend` — 分红处理
**目的：** 验证分红不影响持仓，直接计入已实现盈亏  
**场景：**
```
交易 1：买入 100 股 @ ¥100
交易 2：分红 ¥2/股 × 100 = ¥200
行情：当前价 ¥100
```
**验证点：**
- 持仓数量不变：100 股 ✓
- 已实现盈亏：¥200（分红金额） ✓
- 浮动盈亏：0（价格未变） ✓

**结果：** ✅ PASS

---

### 加权平均成本法（TestWeightedAverageCost）

#### 5. `test_weighted_average_cost_calculation` — 多次买入的成本计算
**目的：** 验证加权平均成本法的核心逻辑  
**场景：**
```
交易 1：买入 100 股 @ ¥100
交易 2：买入 100 股 @ ¥110
行情：当前价 ¥120
```
**预期：** avg_cost = (100×100 + 110×100) / 200 = ¥105  
**验证点：**
- 持仓数量：200 股 ✓
- 平均成本：¥105 ✓
- 浮动盈亏：(120 - 105) × 200 = ¥3000 ✓

**结果：** ✅ PASS

#### 6. `test_multiple_assets` — 多资产组合
**目的：** 验证多个资产（A股、基金）的独立计算和聚合  
**场景：**
```
持仓 1（A股）：100 股 sh600519 @ ¥100 → 当前 ¥110
持仓 2（基金）：1000 份 510300 @ ¥3.5 → 当前 ¥3.7
```
**验证点：**
- 返回两个独立的 PositionDetail ✓
- 总资产：100×110 + 1000×3.7 = ¥14700 ✓
- 总浮盈：(110-100)×100 + (3.7-3.5)×1000 = ¥1200 ✓

**结果：** ✅ PASS

---

### 行情降级处理（TestQuoteFallback）

#### 7. `test_quote_failure_fallback` — 行情拉取完全失败
**目的：** 验证行情失败时自动降级为平均成本  
**场景：**
```
持仓：100 股 @ ¥100
行情：返回 None（拉取失败）
```
**预期：** 使用平均成本 ¥100 作为当前价  
**验证点：**
- current_price = avg_cost = ¥100 ✓
- floating_pnl = 0 ✓

**结果：** ✅ PASS

#### 8. `test_partial_quote_failure` — 行情部分失败
**目的：** 验证部分标的行情失败时的混合处理  
**场景：**
```
持仓 1（sh600519）：100 股 @ ¥100 → 行情成功 ¥120
持仓 2（sh000001）：200 股 @ ¥50 → 行情失败
```
**验证点：**
- sh600519：使用 ¥120，浮盈 = ¥2000 ✓
- sh000001：使用平均成本 ¥50，浮盈 = 0 ✓

**结果：** ✅ PASS

---

### 资产类型过滤（TestAssetTypeFilter）

#### 9. `test_filter_by_asset_type` — 按资产类型过滤
**目的：** 验证 `asset_type_filter` 参数的正确工作  
**场景：**
```
持仓 1：A股 sh600519
持仓 2：基金 510300
过滤条件：仅查询 STOCK_A
```
**验证点：**
- 仅返回 A股 持仓 ✓
- 总资产计算正确 ✓

**结果：** ✅ PASS

---

### 边界情况（TestEdgeCases）

#### 10. `test_zero_commission` — 零手续费
**目的：** 验证无手续费时的简化计算  
**场景：**
```
交易：买入 100 股 @ ¥100，无手续费
行情：¥110
```
**预期：** avg_cost = 100（无手续费）  
**验证点：**
- avg_cost = ¥100 ✓
- floating_pnl = ¥1000 ✓

**结果：** ✅ PASS

#### 11. `test_fractional_quantity` — 小数份额
**目的：** 验证基金、黄金等小数份额的支持  
**场景：**
```
交易：买入 1030.21 份基金 @ ¥1.456 + ¥1.5 手续费
行情：¥1.5
```
**预期：** 正确计算小数精度  
**验证点：**
- 持仓数量：1030.21 ✓
- 平均成本：精度正确 ✓

**结果：** ✅ PASS

#### 12. `test_large_numbers` — 大数字精度
**目的：** 验证大金额交易的精度处理  
**场景：**
```
交易：买入 1000 股 @ ¥50000 + ¥100000 手续费 = ¥50100000
行情：¥55000
```
**验证点：**
- avg_cost = ¥50100 ✓
- floating_pnl = ¥4900000 ✓
- total_assets = ¥55000000 ✓

**结果：** ✅ PASS

---

## 🎯 测试覆盖范围

### 算法正确性
- ✅ 加权平均成本法的买入成本计算
- ✅ 卖出时的已实现盈亏计算
- ✅ 分红处理（不影响持仓）
- ✅ 多次买入的成本合并
- ✅ 浮动盈亏的正确计算

### 数据处理
- ✅ 空持仓处理
- ✅ 单个资产处理
- ✅ 多资产聚合
- ✅ 小数精度（基金、黄金）
- ✅ 大数字精度

### 错误处理
- ✅ 行情拉取失败的降级
- ✅ 部分行情失败的混合处理
- ✅ 零手续费边界
- ✅ 资产类型过滤

---

## 📊 测试执行结果

```
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2

collected 12 items

tests/test_pnl_engine.py::TestBasicTrades::test_empty_portfolio PASSED
tests/test_pnl_engine.py::TestBasicTrades::test_single_buy PASSED
tests/test_pnl_engine.py::TestBasicTrades::test_buy_and_sell PASSED
tests/test_pnl_engine.py::TestBasicTrades::test_dividend PASSED
tests/test_pnl_engine.py::TestWeightedAverageCost::test_weighted_average_cost_calculation PASSED
tests/test_pnl_engine.py::TestWeightedAverageCost::test_multiple_assets PASSED
tests/test_pnl_engine.py::TestQuoteFallback::test_quote_failure_fallback PASSED
tests/test_pnl_engine.py::TestQuoteFallback::test_partial_quote_failure PASSED
tests/test_pnl_engine.py::TestAssetTypeFilter::test_filter_by_asset_type PASSED
tests/test_pnl_engine.py::TestEdgeCases::test_zero_commission PASSED
tests/test_pnl_engine.py::TestEdgeCases::test_fractional_quantity PASSED
tests/test_pnl_engine.py::TestEdgeCases::test_large_numbers PASSED

======================== 12 passed in 1.00s ========================
```

---

## ✨ 测试特点

✅ **完整的场景覆盖** — 从基础交易到复杂边界  
✅ **隔离的测试环境** — 使用内存数据库，无外部依赖  
✅ **Mock 行情数据** — 无需真实 API 调用  
✅ **明确的验证点** — 每个测试验证 3-5 个关键指标  
✅ **可读的注释** — 清晰标注预期值和计算公式  

---

## 🚀 运行测试

```bash
# 运行所有测试
python3 -m pytest tests/test_pnl_engine.py -v

# 运行特定测试类
python3 -m pytest tests/test_pnl_engine.py::TestBasicTrades -v

# 运行特定测试
python3 -m pytest tests/test_pnl_engine.py::TestBasicTrades::test_single_buy -v

# 显示详细输出
python3 -m pytest tests/test_pnl_engine.py -vv --tb=short
```

---

## 📝 结论

✅ **PnL 计算引擎已验证无误**

- 加权平均成本法实现正确
- 所有交易类型（BUY/SELL/DIVIDEND）处理正确
- 多资产组合支持
- 行情失败时优雅降级
- 边界情况妥善处理

**下一步：** 实现 `/api/portfolio/summary` API 端点
