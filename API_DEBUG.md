# API 调试指南

本文档包含所有常用的 curl 命令，用于测试和调试 API 端点。

## 前置要求

```bash
# 启动 API 服务
python3 -m uvicorn app.main:app --reload --log-level info
```

API 会在 `http://localhost:8000` 启动

---

## 系统检查

### 健康检查
```bash
curl -X GET http://localhost:8000/health
```

**预期响应**:
```json
{
  "status": "healthy",
  "service": "Personal Finance Assistant",
  "version": "0.1.0"
}
```

### 根路由
```bash
curl -X GET http://localhost:8000/
```

---

## 数据缓存查询

### 查询全市场行情缓存（第一页，50条）
```bash
curl -X GET "http://localhost:8000/api/portfolio/market-cache"
```

### 查询全市场行情缓存（指定分页）
```bash
# 跳过前100条，返回下一个50条
curl -X GET "http://localhost:8000/api/portfolio/market-cache?skip=100&limit=50"

# 返回100条记录
curl -X GET "http://localhost:8000/api/portfolio/market-cache?limit=100"

# 返回所有记录（最多500条）
curl -X GET "http://localhost:8000/api/portfolio/market-cache?limit=500"
```

**预期响应**（缓存加载完后）:
```json
{
  "total": 5835,
  "skip": 0,
  "limit": 50,
  "returned": 50,
  "data": [
    {
      "代码": "600519",
      "名称": "贵州茅台",
      "最新价": "1460.0",
      "昨收": "1465.0",
      "涨跌额": "-5.0",
      "涨跌幅": "-0.34",
      "成交量": "12345678.0"
    }
    // ... 更多记录
  ]
}
```

**预期响应**（缓存还在加载）:
```json
{
  "detail": "系统正在初始化行情数据，请稍候几分钟后重试"
}
```
HTTP Status: 202 Accepted

---

## 缓存管理

### 查询缓存刷新状态
```bash
curl -X GET http://localhost:8000/api/portfolio/cache-status
```

**预期响应** (缓存正在刷新):
```json
{
  "stock_a": {
    "name": "A股全市场行情",
    "is_refreshing": true,
    "last_update_time": "2026-04-04T11:00:00.123456",
    "is_ready": true,
    "elapsed_seconds": 45.3,
    "progress": "正在处理第 1234 条记录..."
  },
  "etf": {
    "name": "ETF全市场行情",
    "is_refreshing": false,
    "last_update_time": "2026-04-04T11:00:10.654321",
    "is_ready": true,
    "elapsed_seconds": null,
    "progress": ""
  },
  "lof": {
    "name": "LOF全市场行情",
    "is_refreshing": false,
    "last_update_time": "2026-04-04T11:00:15.987654",
    "is_ready": true,
    "elapsed_seconds": null,
    "progress": ""
  }
}
```

**字段说明**:
- `is_refreshing`: 是否正在刷新（用于判断是否可以手动触发）
- `is_ready`: 缓存是否已加载可用（若为 false，查询会返回 202）
- `last_update_time`: 最后更新的时间戳
- `elapsed_seconds`: 当前刷新已耗时（仅在 `is_refreshing=true` 时有值）
- `progress`: tqdm 进度条信息（如：`95%|█████████▍| 55/58 [05:57<00:19,  6.64s/it]`）

**进度隔离说明**：
- 三个数据源（A股、ETF、LOF）**并发刷新**时，各自的进度条**分线程隔离**
- 使用 `threading.local` 存储，不会互相覆盖
- 每个缓存各自维护独立的进度信息

**前端应用示例**：
```javascript
// 定期轮询缓存状态，实时显示各数据源进度
setInterval(() => {
  fetch('/api/portfolio/cache-status')
    .then(r => r.json())
    .then(data => {
      // A股进度（如果正在刷新）
      if (data.stock_a.is_refreshing) {
        console.log('A股:', data.stock_a.progress);
        // 95%|█████████▍| 55/58 [05:57<00:19,  6.64s/it]
      }
      // ETF 进度（独立显示）
      if (data.etf.is_refreshing) {
        console.log('ETF:', data.etf.progress);
      }
      // LOF 进度（独立显示）
      if (data.lof.is_refreshing) {
        console.log('LOF:', data.lof.progress);
      }
    });
}, 1000);
```

### 手动触发缓存刷新
```bash
# 立即刷新所有缓存（A股 + ETF + LOF）
curl -X POST http://localhost:8000/api/portfolio/refresh-cache
```

**预期响应**（刷新成功）:
```json
{
  "message": "缓存刷新完成",
  "elapsed_seconds": 382.5,
  "data_update_time": "2026-04-04T11:09:19.123456"
}
```
HTTP Status: 200 OK

**预期响应**（刷新已在进行中）:
```json
{
  "detail": "缓存刷新已在进行中"
}
```
HTTP Status: 409 Conflict

**说明**：
- 手动刷新和定时刷新互斥，同时只允许一个运行
- 此端点会同步等待刷新完成（可能需要 5-10 分钟）
- 返回值中的 `data_update_time` 是最新的行情数据时间戳

---

## 持仓汇总查询

### 查看全部持仓
```bash
curl -X GET http://localhost:8000/api/portfolio/summary
```

### 只查看 A 股持仓
```bash
curl -X GET "http://localhost:8000/api/portfolio/summary?asset_type=STOCK_A"
```

### 只查看基金持仓
```bash
curl -X GET "http://localhost:8000/api/portfolio/summary?asset_type=FUND"
```

### 只查看黄金持仓
```bash
curl -X GET "http://localhost:8000/api/portfolio/summary?asset_type=GOLD_SPOT"
```

**预期响应**（缓存就绪）:
```json
{
  "total_assets": 177086.49,
  "total_pnl": -23747.50,
  "total_pnl_percent": "-11.82%",
  "realized_pnl": 0,
  "positions": [
    {
      "asset_type": "STOCK_A",
      "symbol": "sh600519",
      "holding_quantity": "100.0",
      "avg_cost": "1700.55",
      "current_price": "1460.0",
      "floating_pnl": -24055.0,
      "pnl_percent": "-14.15%"
    }
    // ... 更多持仓
  ]
}
```

---

## 交易流水管理

### 录入新交易

#### A 股交易
```bash
curl -X POST http://localhost:8000/api/trades \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "STOCK_A",
    "symbol": "sh600519",
    "trade_date": "2024-01-15T10:30:00",
    "trade_type": "BUY",
    "price": 1700.0,
    "quantity": 100,
    "commission": 5.0,
    "notes": "买入茅台"
  }'
```

#### 基金交易
```bash
curl -X POST http://localhost:8000/api/trades \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "FUND",
    "symbol": "005827",
    "trade_date": "2024-01-15T15:00:00",
    "trade_type": "BUY",
    "price": 1.456,
    "quantity": 1000.0,
    "commission": 1.5,
    "notes": "定投基金"
  }'
```

#### 黄金交易
```bash
curl -X POST http://localhost:8000/api/trades \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "GOLD_SPOT",
    "symbol": "AU9999",
    "trade_date": "2024-01-15T09:00:00",
    "trade_type": "BUY",
    "price": 480.5,
    "quantity": 50.0,
    "commission": 0,
    "notes": "购买黄金"
  }'
```

#### 分红交易
```bash
curl -X POST http://localhost:8000/api/trades \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "STOCK_A",
    "symbol": "sh600519",
    "trade_date": "2024-01-20T00:00:00",
    "trade_type": "DIVIDEND",
    "price": 5.0,
    "quantity": 100,
    "commission": 0,
    "notes": "现金分红"
  }'
```

**预期响应**:
```json
{
  "id": 1,
  "asset_type": "STOCK_A",
  "symbol": "sh600519",
  "trade_date": "2024-01-15T10:30:00",
  "trade_type": "BUY",
  "price": 1700.0,
  "quantity": 100,
  "commission": 5.0,
  "notes": "买入茅台"
}
```

### 查看所有交易
```bash
curl -X GET http://localhost:8000/api/trades
```

### 查看所有 A 股交易
```bash
curl -X GET "http://localhost:8000/api/trades?asset_type=STOCK_A"
```

### 查看指定持仓的交易记录
```bash
curl -X GET "http://localhost:8000/api/trades?symbol=sh600519"
```

### 查看指定交易
```bash
curl -X GET http://localhost:8000/api/trades/1
```

### 修改交易（部分更新）
```bash
curl -X PATCH http://localhost:8000/api/trades/1 \
  -H "Content-Type: application/json" \
  -d '{
    "price": 1705.0,
    "notes": "更新买入价格"
  }'
```

### 删除交易
```bash
curl -X DELETE http://localhost:8000/api/trades/1
```

**预期响应**: HTTP Status 204 No Content

---

## 告警规则管理

### 创建告警规则

#### 价格告警（股票突破 2000 元）
```bash
curl -X POST http://localhost:8000/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "STOCK_A",
    "symbol": "sh600519",
    "metric": "PRICE",
    "operator": ">",
    "threshold": 2000.0,
    "notes": "茅台价格突破2000元"
  }'
```

#### 涨跌幅告警（跌超 5%）
```bash
curl -X POST http://localhost:8000/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "STOCK_A",
    "symbol": "sh600519",
    "metric": "CHANGE_PCT",
    "operator": "<",
    "threshold": -5.0,
    "notes": "茅台跌超5%"
  }'
```

#### 成交量告警（异常放量）
```bash
curl -X POST http://localhost:8000/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "STOCK_A",
    "symbol": "sh600519",
    "metric": "VOLUME",
    "operator": ">",
    "threshold": 100000000.0,
    "notes": "茅台成交量超过1亿"
  }'
```

**预期响应**:
```json
{
  "id": 1,
  "asset_type": "STOCK_A",
  "symbol": "sh600519",
  "metric": "PRICE",
  "operator": ">",
  "threshold": 2000.0,
  "is_active": true,
  "notes": "茅台价格突破2000元"
}
```

### 查看所有告警规则
```bash
curl -X GET http://localhost:8000/api/alerts
```

### 查看启用的告警规则
```bash
curl -X GET "http://localhost:8000/api/alerts?is_active=true"
```

### 查看禁用的告警规则
```bash
curl -X GET "http://localhost:8000/api/alerts?is_active=false"
```

### 查看指定告警规则
```bash
curl -X GET http://localhost:8000/api/alerts/1
```

### 修改告警规则
```bash
curl -X PATCH http://localhost:8000/api/alerts/1 \
  -H "Content-Type: application/json" \
  -d '{
    "threshold": 2100.0,
    "notes": "更新突破价格为2100元"
  }'
```

### 切换告警规则的启用/禁用状态
```bash
curl -X PATCH http://localhost:8000/api/alerts/1/toggle \
  -H "Content-Type: application/json" \
  -d '{
    "is_active": false
  }'
```

### 删除告警规则
```bash
curl -X DELETE http://localhost:8000/api/alerts/1
```

**预期响应**: HTTP Status 204 No Content

---

## 常用调试技巧

### 1. 格式化 JSON 响应
```bash
# 使用 jq 格式化
curl -s http://localhost:8000/api/portfolio/summary | jq .

# 只显示特定字段
curl -s http://localhost:8000/api/portfolio/summary | jq '.total_assets, .total_pnl'
```

### 2. 保存响应到文件
```bash
curl -s http://localhost:8000/api/portfolio/summary > portfolio.json
```

### 3. 显示响应头信息
```bash
curl -i http://localhost:8000/api/portfolio/summary
```

### 4. 显示详细请求/响应信息
```bash
curl -v http://localhost:8000/api/portfolio/summary
```

### 5. 统计响应时间
```bash
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8000/api/portfolio/summary
```

curl-format.txt 内容：
```
    time_namelookup:  %{time_namelookup}\n
       time_connect:  %{time_connect}\n
    time_appconnect:  %{time_appconnect}\n
   time_pretransfer:  %{time_pretransfer}\n
      time_redirect:  %{time_redirect}\n
 time_starttransfer:  %{time_starttransfer}\n
                    ----------\n
         time_total:  %{time_total}\n
```

### 6. 批量测试
```bash
# 创建多个交易记录进行测试
for i in {1..5}; do
  curl -X POST http://localhost:8000/api/trades \
    -H "Content-Type: application/json" \
    -d "{
      \"asset_type\": \"STOCK_A\",
      \"symbol\": \"sh600519\",
      \"trade_date\": \"2024-01-$(printf '%02d' $i)T10:00:00\",
      \"trade_type\": \"BUY\",
      \"price\": $((1700 + i * 10)),
      \"quantity\": 10,
      \"commission\": 1.0
    }"
done
```

---

## 监控缓存加载进度

### 监控日志（在另一个终端）
```bash
# 实时查看日志
tail -f /tmp/api.log | grep -E "后台|缓存|加载"

# 或者查看完整日志
tail -100 /tmp/api.log
```

### 预期日志输出
```
2026-04-04 10:53:37,181 - app.data_fetcher.stock_a - INFO - 🔄 [后台] 开始加载 A股全市场行情...
2026-04-04 10:53:37,181 - app.main - INFO - ✅ A股行情缓存后台加载已启动
2026-04-04 11:00:03,569 - app.data_fetcher.stock_a - INFO - ✅ [后台] A股行情缓存加载完成: 5835 只股票, 耗时 326.4s, 有效期 300s
```

---

## 性能测试

### 测试缓存未加载时的响应
```bash
# 缓存加载期间，应返回 202 Accepted
curl -i http://localhost:8000/api/portfolio/summary
```

### 测试缓存加载后的响应时间
```bash
# 缓存加载完后，应该秒级响应
time curl -s http://localhost:8000/api/portfolio/summary | jq '.total_assets'

# 结果应该 < 1 秒
```

### 压力测试（缓存就绪后）
```bash
# 使用 Apache Bench 进行并发测试
ab -n 100 -c 10 http://localhost:8000/api/portfolio/summary

# 或使用 wrk
wrk -t4 -c100 -d30s http://localhost:8000/api/portfolio/summary
```

---

## 故障排查

### 如果 API 无法启动

检查日志中的错误信息：
```bash
grep ERROR /tmp/api.log
```

常见问题：
- 端口被占用：`lsof -i :8000`
- 数据库连接失败：检查 `finance_data.db` 文件权限
- 模块导入失败：运行 `pip install -r requirements.txt`

### 如果缓存加载失败

检查日志：
```bash
grep "❌\|失败" /tmp/api.log
```

常见问题：
- 网络问题：检查 AkShare API 连接
- 内存不足：需要约 500MB 内存加载全市场数据
- AkShare 版本问题：运行 `pip install --upgrade akshare`

### 清空缓存重新加载

重启 API 会自动清空内存缓存：
```bash
# 关闭 API
pkill -f uvicorn

# 重新启动
python3 -m uvicorn app.main:app --reload
```

---

## 快速命令总结

```bash
# 检查健康状态
curl http://localhost:8000/health

# 查看持仓汇总
curl http://localhost:8000/api/portfolio/summary

# 查看全市场缓存
curl http://localhost:8000/api/portfolio/market-cache

# 查看所有交易
curl http://localhost:8000/api/trades

# 查看所有告警
curl http://localhost:8000/api/alerts

# 添加新交易
curl -X POST http://localhost:8000/api/trades \
  -H "Content-Type: application/json" \
  -d '{"asset_type":"STOCK_A","symbol":"sh600519","trade_date":"2024-01-15T10:00:00","trade_type":"BUY","price":1700,"quantity":100,"commission":5}'

# 添加告警规则
curl -X POST http://localhost:8000/api/alerts \
  -H "Content-Type: application/json" \
  -d '{"asset_type":"STOCK_A","symbol":"sh600519","metric":"PRICE","operator":">","threshold":2000}'
```
