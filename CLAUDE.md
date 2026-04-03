# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Contents

个人金融辅助分析工具 (V1.0) - 系统设计与实施文档

1. 项目概述

本项目旨在为个人开发者构建一个轻量级的金融持仓分析与实时盯盘工具。系统采用“本地存储+内存计算”的极简架构，无需购买昂贵的云服务和重型数据库，完全掌握数据隐私。
核心功能：交易流水记录（支持多资产）、动态盈亏分析（PnL）、持仓成本核算、自定义指标盯盘与微信告警。

2. 核心系统模块划分与功能说明

为了实现高内聚低耦合的开发，整个系统划分为以下五个核心模块：

2.1 数据接入模块 (Data Fetcher)

功能： 系统的“数据泵”，负责与外部数据源打交道。

具体职责：

多源路由 (Router)： 根据资产类型（如 A股、基金、黄金）将请求路由到不同的 AkShare 底层接口。

抓取个股/资产的实时行情（最新价、成交量等），供盯盘模块和持仓分析模块使用。

拉取历史日线/分钟线级别 K 线数据，用于后续可能的技术指标计算与复盘。

屏蔽外部 API 差异，向内部提供统一的数据结构。

2.2 交易流水管理模块 (Trade Ledger)

功能： 系统的“底层账本”，负责所有原始交易行为的持久化记录。

具体职责：

提供交易记录的增删改查（CRUD）功能。

记录每一次买入、卖出、分红的详细信息（时间、资产大类、标的、价格、数量、手续费）。

确保本地 SQLite 数据库中流水数据的完整性与一致性。

2.3 持仓与盈亏分析模块 (PnL & Position Engine)

功能： 系统的“计算大脑”，负责基于历史流水和当前行情推算账户状态。

具体职责：

提取流水数据，动态计算每只资产的当前持仓量和加权平均成本。

结合数据接入模块提供的最新价，实时计算各个标的的浮动盈亏 (Floating PnL) 和盈亏比例。

汇总计算整体账户的总资产规模和历史实现盈亏，支持按资产大类（如只看基金盈亏）进行过滤。

2.4 实时盯盘与告警模块 (Monitor & Alert Daemon)

功能： 系统的“后台哨兵”，持续监控市场异动并通知用户。

具体职责：

维护和管理用户设定的盯盘规则（如：价格突破、跌破均线、异常放量等）。

开启独立的异步任务持续轮询行情数据。

当市场数据触及设定规则的阈值时，触发告警逻辑，调用外部推送 API（如 Server酱）将消息发送至微信。

处理告警冷却机制，防止短时间内消息轰炸。

2.5 前端可视化看板 (Dashboard UI)

功能： 系统的“人机交互窗口”，提供直观的数据展示与操作界面。

具体职责：

持仓大屏： 以饼图展示跨资产（股票/基金/黄金）配置比例，以表格展示各资产的实时盈亏状况。

操作台： 提供表单界面供用户手动录入最新的买卖交易流水（通过下拉框切换资产类型）。

盯盘配置： 提供界面让用户随时添加、开启、关闭或修改盯盘告警规则。

3. 资源准备与外部依赖

在敲下第一行代码前，你需要准备好以下环境和外部账号（均可免费获取）：

3.1 本地开发环境

语言环境： Python 3.10+

开发工具： VS Code (建议安装 Python、SQLite Viewer 扩展)

数据库： SQLite3 (Python 内置，无需额外安装服务端)

3.2 外部数据源 API

历史与日级行情： AkShare (Python 库，开源免费，涵盖了 A股、美股、公募基金、现货黄金等绝大多数品种)。

实时行情订阅： 针对 A 股/美股/黄金，使用新浪/腾讯财经的公开 API 或 WebSocket 接口（集成在 AkShare 内部或使用极简 requests 轮询）。

3.3 消息推送 API (用于盯盘告警)

微信推送： Server酱 (Turbo 版) 或 PushPlus。

操作： 去官网用微信扫码登录，获取一个 SendKey (一个字符串凭证)。调用时只需发一个 HTTP 请求，你的微信就会收到告警信息。

4. 核心业务数据库设计

系统采用 SQLite，所有的表都保存在本地的 finance_data.db 文件中。针对多资产兼容，结构设计如下：

表 1：trades (交易流水表 - 手动录入)

这是整个系统的基石，记录跨市场资产的每一次买卖行为。
| 字段名 | 数据类型 | 说明 / 示例 |
| :--- | :--- | :--- |
| id | INTEGER | 主键，自增 |
| asset_type | VARCHAR(20) | 资产大类 (枚举: STOCK_A, FUND, GOLD_SPOT, US_STOCK) |
| symbol | VARCHAR(20) | 资产代码 (如: sh600519, 005827, AU9999) |
| trade_date | DATETIME | 交易发生的时间 |
| trade_type | VARCHAR(10) | 交易类型 (枚举：BUY, SELL, DIVIDEND) |
| price | DECIMAL | 交易单价 (黄金为 元/克，基金为 净值) |
| quantity | DECIMAL | 交易数量 (使用小数，兼容基金份额和黄金克数) |
| commission | DECIMAL | 交易手续费及税费总和 |
| notes | VARCHAR(255)| 备注 |

表 2：alert_rules (盯盘告警规则表)

字段名

数据类型

说明 / 示例

id

INTEGER

主键，自增

asset_type

VARCHAR(20)

资产大类 (方便路由取价接口)

symbol

VARCHAR(20)

资产代码

metric

VARCHAR(20)

监控指标 (枚举: PRICE, VOLUME, CHANGE_PCT)

operator

VARCHAR(5)

比较运算符 (如: >, <, >=, <=)

threshold

DECIMAL

触发阈值

is_active

BOOLEAN

是否启用 (1=启用, 0=暂停)

5. 后端 API 接口设计

建议使用 FastAPI 框架。前端 Streamlit 通过这些接口与数据交互。

5.1 交易流水模块

$$POST$$

 /api/trades

功能： 录入一条新的交易记录。

请求体示例 1 (A股)： {"asset_type": "STOCK_A", "symbol": "sh600519", "trade_type": "BUY", "price": 1700.0, "quantity": 100, "commission": 5.0, "trade_date": "..."}

请求体示例 2 (基金)： {"asset_type": "FUND", "symbol": "005827", "trade_type": "BUY", "price": 1.456, "quantity": 1030.21, "commission": 1.5, "trade_date": "..."}

请求体示例 3 (黄金)： {"asset_type": "GOLD_SPOT", "symbol": "AU9999", "trade_type": "BUY", "price": 480.5, "quantity": 50.5, "commission": 0, "trade_date": "..."}

$$GET$$

 /api/trades

功能： 获取交易流水列表，支持按 asset_type 或 symbol 过滤。

5.2 持仓与盈亏分析模块

$$GET$$

 /api/portfolio/summary

功能： 核心接口。聚合计算当前的持仓总览。

响应结构 (JSON)：

{
  "total_assets": 150000.00,
  "total_pnl": 5000.00,
  "positions": [
    {
      "asset_type": "STOCK_A",
      "symbol": "sh600519",
      "holding_quantity": 100,
      "avg_cost": 1680.0,
      "current_price": 1700.0,
      "floating_pnl": 2000.0,
      "pnl_percent": "1.19%"
    },
    {
      "asset_type": "FUND",
      "symbol": "005827",
      "holding_quantity": 1030.21,
      "avg_cost": 1.456,
      "current_price": 1.480,
      "floating_pnl": 24.72,
      "pnl_percent": "1.65%"
    }
  ]
}


5.3 盯盘告警模块

$$POST$$

 /api/alerts

功能： 添加一条新的盯盘规则。

$$GET$$

 /api/alerts

功能： 获取当前所有设定的规则。

6. 后台盯盘守护进程机制

此模块不提供接口，而是一个独立的 Python 异步脚本（可以使用 asyncio），伴随 FastAPI 一同启动：

路由与批量查询： 按 asset_type 将需要盯盘的资产分组，调用相应的 AkShare 接口获取最新价。

规则判定： 将最新价与 threshold 对比。

触发展流： 若判定为 True，向 Server酱发送 HTTP POST 请求。

防轰炸控制： 内存中记录已触发的规则 ID 和时间，同一规则设定冷却期（如：触发后 30 分钟内不再重复发微信）。

7. 实施路径 (Action Plan)

建议将项目分为四个阶段，循序渐进：

阶段 1：打地基 (预计 1-2 天)

安装 Python 和必要库 (pip install fastapi uvicorn sqlalchemy pandas akshare).

编写 models.py，使用 SQLAlchemy 初始化 SQLite 数据库，注意 quantity 设置为 Float/Decimal 类型。

阶段 2：算明白 (预计 2 天)

编写 data_fetcher.py 封装不同 asset_type 对应的 AkShare 获取最新价逻辑。

实现核心算法：根据 trades 表计算当前成本和数量，产出 /api/portfolio/summary 数据。

阶段 3：动起来 (预计 2 天)

注册 Server酱并获取 SendKey。

编写后台盯盘脚本 monitor.py，实现多资产微信推送告警。

阶段 4：看得到 (预计 2-3 天)

安装 UI 库 (pip install streamlit plotly).

编写 app.py（Streamlit 页面）。

录入表单中增加一个“资产大类”的下拉选择框，根据选择的类型改变后面的输入提示（如选择基金，提示输入净值和份额）。
