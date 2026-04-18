"""
pyraFinanceAssist 前端看板 - 主入口

页面说明：
- 主页 (app.py): 持仓看板 + 交易流水
- 子页 (pages/01_trade_entry.py): 交易录入
"""

import os
import streamlit as st
import httpx
import json
from datetime import datetime
import plotly.express as px
import pandas as pd

# 页面配置
st.set_page_config(
    page_title="持仓看板",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 后端 API：默认 127.0.0.1（避免 localhost 走系统代理导致 502）；可用环境变量覆盖
API_BASE = os.environ.get("PYRA_API_BASE", "http://127.0.0.1:8000/api")

# 持仓汇总会并发拉多路行情，易超过 30s；502 多为代理/网关对慢请求或 localhost 处理异常
_HTTPX_TIMEOUT = httpx.Timeout(connect=15.0, read=180.0, write=60.0, pool=60.0)
_HTTPX_SHORT = httpx.Timeout(connect=15.0, read=30.0, write=30.0, pool=30.0)

# ────────────────────────────────────────────────────────────────
# 工具函数
# ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def get_portfolio_data(asset_type_filter=None):
    """获取持仓汇总数据（30秒缓存）"""
    params = {}
    if asset_type_filter:
        params["asset_type"] = asset_type_filter

    try:
        r = httpx.get(
            f"{API_BASE}/portfolio/summary",
            params=params,
            timeout=_HTTPX_TIMEOUT,
            trust_env=False,
        )
    except httpx.RequestError as e:
        st.error(f"获取持仓数据失败（网络）: {e}")
        return None
    if r.status_code != 200:
        hint = ""
        if r.status_code in (502, 504):
            hint = " 若出现 502/504，请确认本机已启动后端，并尝试设置 PYRA_API_BASE=http://127.0.0.1:8000/api、关闭对 localhost 的全局代理。"
        st.error(f"获取持仓数据失败: HTTP {r.status_code}.{hint}")
        return None
    return r.json()


def get_trades_data():
    """获取交易流水（不缓存，实时刷新）"""
    try:
        r = httpx.get(
            f"{API_BASE}/trades",
            timeout=_HTTPX_SHORT,
            trust_env=False,
        )
    except httpx.RequestError as e:
        st.error(f"获取交易流水失败（网络）: {e}")
        return []
    if r.status_code != 200:
        st.error(f"获取交易流水失败: {r.status_code}")
        return []
    return r.json()


def delete_trade(trade_id):
    """删除交易记录"""
    r = httpx.delete(
        f"{API_BASE}/trades/{trade_id}",
        timeout=_HTTPX_SHORT,
        trust_env=False,
    )
    if r.status_code == 204:
        st.success(f"✅ 删除成功")
        st.rerun()
    else:
        st.error(f"❌ 删除失败: {r.text}")


def format_pnl_color(pnl_str):
    """根据盈亏值返回颜色（用于表格显示）"""
    if pnl_str.startswith('+'):
        return '🟢 ' + pnl_str
    else:
        return '🔴 ' + pnl_str


# ────────────────────────────────────────────────────────────────
# 页面标题与导航
# ────────────────────────────────────────────────────────────────

st.title("📊 持仓看板")
col1, col2 = st.columns([0.8, 0.2])
with col1:
    st.markdown("实时持仓汇总 · PnL 分析")
with col2:
    if st.button("🔄 刷新数据", key="main_refresh"):
        st.cache_data.clear()
        st.rerun()

st.divider()

# ────────────────────────────────────────────────────────────────
# 汇总指标卡片
# ────────────────────────────────────────────────────────────────

portfolio = get_portfolio_data()
if portfolio:
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "💰 总资产",
            f"¥{float(portfolio['total_assets']):,.2f}",
            delta=None
        )

    with col2:
        total_pnl = float(portfolio['total_pnl'])
        st.metric(
            "📈 浮动盈亏",
            f"¥{total_pnl:+,.2f}",
            delta=portfolio['total_pnl_percent'],
            delta_color="inverse"
        )

    with col3:
        realized = float(portfolio['realized_pnl'])
        st.metric(
            "✅ 已实现盈亏",
            f"¥{realized:+,.2f}",
            delta=None
        )

    with col4:
        today_pnl = portfolio.get("today_pnl_cny")
        today_pct = portfolio.get("today_pnl_percent")
        if today_pnl is not None:
            pct_str = f"{today_pct:+.2f}%" if today_pct is not None else None
            st.metric(
                "📅 今日盈亏",
                f"¥{float(today_pnl):+,.2f}",
                delta=pct_str,
                delta_color="inverse"
            )
        else:
            st.metric("📅 今日盈亏", "无基准数据", help="需先在「每日收益看板」执行一次历史数据重算")

st.divider()

# ────────────────────────────────────────────────────────────────
# 资产类型筛选与分栏布局
# ────────────────────────────────────────────────────────────────

asset_filter = st.selectbox(
    "资产类型筛选",
    options=[None, "STOCK_A", "STOCK_HK", "STOCK_US", "FUND", "GOLD_SPOT"],
    format_func=lambda x: {
        None: "全部资产",
        "STOCK_A": "A 股",
        "STOCK_HK": "港股",
        "STOCK_US": "美股",
        "FUND": "基金（ETF/LOF）",
        "GOLD_SPOT": "现货黄金"
    }[x],
    key="asset_filter"
)

if asset_filter:
    # 重新加载过滤后的数据
    st.cache_data.clear()
    portfolio = get_portfolio_data(asset_filter)

if not portfolio or not portfolio.get('positions'):
    st.info("暂无持仓数据")
else:
    col_pie, col_table = st.columns([1, 1.5])

    # ─── 左栏：资产配置饼图 ───
    with col_pie:
        st.subheader("资产配置")

        # 按 asset_type 聚合市值
        positions = portfolio['positions']
        asset_values = {}
        for pos in positions:
            asset_type = pos['asset_type']
            market_value = float(pos['current_price']) * float(pos['holding_quantity'])
            asset_values[asset_type] = asset_values.get(asset_type, 0) + market_value

        if asset_values:
            fig = px.pie(
                values=list(asset_values.values()),
                names=list(asset_values.keys()),
                title="按资产类型分配"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.text("无数据")

    # ─── 右栏：持仓明细表格 ───
    with col_table:
        st.subheader("持仓明细")

        # 构建表格数据
        table_data = []
        for pos in positions:
            table_data.append({
                "资产类型": {
                    "STOCK_A": "A股",
                    "STOCK_HK": "港股",
                    "STOCK_US": "美股",
                    "FUND": "基金",
                    "GOLD_SPOT": "黄金"
                }.get(pos['asset_type'], pos['asset_type']),
                "代码": pos['symbol'],
                "名称": pos['name'] if pos['name'] else "-", # Add name here, default to "-" if empty
                "持仓量": f"{float(pos['holding_quantity']):,.2f}",
                "均价 (元)": f"{float(pos['avg_cost']):,.2f}",
                "现价 (元)": f"{float(pos['current_price']):,.2f}",
                "浮盈 (元)": f"{float(pos['floating_pnl']):+,.2f}",
                "盈亏%": pos['pnl_percent']
            })

        df_table = pd.DataFrame(table_data)

        # 定义样式函数
        def style_pnl(val):
            if isinstance(val, str):
                if val.startswith('+'):
                    return 'background-color: #d4edda; color: #155724'
                elif val.startswith('-'):
                    return 'background-color: #f8d7da; color: #721c24'
            return ''

        # 应用样式
        styled_df = df_table.style.applymap(style_pnl, subset=['盈亏%'])
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

st.divider()

# ────────────────────────────────────────────────────────────────
# 交易流水管理
# ────────────────────────────────────────────────────────────────

st.subheader("📋 交易流水")

trades = get_trades_data()
if not trades:
    st.info("暂无交易记录")
else:
    # 按日期倒序排序
    trades.sort(key=lambda x: x.get('trade_date', ''), reverse=True)

    # 构建表格
    col_search, col_count = st.columns([0.7, 0.3])
    with col_search:
        search_symbol = st.text_input("搜索代码", placeholder="输入代码或资产类型过滤", key="trade_search")
    with col_count:
        st.metric("总交易数", len(trades))

    # 过滤
    if search_symbol:
        trades = [
            t for t in trades
            if search_symbol.lower() in t.get('symbol', '').lower()
            or search_symbol.lower() in t.get('asset_type', '').lower()
        ]

    # 显示交易表格
    table_trades = []
    for trade in trades:
        trade_date = trade.get('trade_date', '')
        if trade_date:
            # 解析 ISO 格式的日期时间
            try:
                dt = datetime.fromisoformat(trade_date.replace('Z', '+00:00'))
                date_str = dt.strftime('%Y-%m-%d')
            except:
                date_str = trade_date[:10]
        else:
            date_str = '-'

        table_trades.append({
            "ID": trade.get('id', '-'),
            "日期": date_str,
            "资产类型": {
                "STOCK_A": "A股",
                "STOCK_HK": "港股",
                "STOCK_US": "美股",
                "FUND": "基金",
                "GOLD_SPOT": "黄金"
            }.get(trade.get('asset_type', ''), trade.get('asset_type', '-')),
            "代码": trade.get('symbol', '-'),
            "交易类型": {
                "BUY": "买入",
                "SELL": "卖出",
                "DIVIDEND": "分红"
            }.get(trade.get('trade_type', ''), trade.get('trade_type', '-')),
            "单价": f"{float(trade.get('price', 0)):,.2f}",
            "数量": f"{float(trade.get('quantity', 0)):,.2f}",
            "手续费": f"{float(trade.get('commission', 0)):,.2f}",
            "备注": trade.get('notes', '') or '-'
        })

    df_trades = pd.DataFrame(table_trades)
    st.dataframe(df_trades, use_container_width=True, hide_index=True)

    # 删除按钮
    st.write("**删除交易：**")
    col_delete = st.columns(5)
    for i, trade in enumerate(trades[:5]):  # 仅显示前5个
        with col_delete[i % 5]:
            if st.button(f"删除 #{trade['id']}", key=f"del_{trade['id']}"):
                delete_trade(trade['id'])

st.divider()

# ────────────────────────────────────────────────────────────────
# 页脚与导航
# ────────────────────────────────────────────────────────────────

st.markdown("""
---
**快速导航：** 点击侧边栏 "交易录入" 页面录入新交易。

💡 **提示：**
- 持仓数据约每 30 秒缓存刷新；拉行情较慢时单次请求最长约 3 分钟
- 点击 🔄 按钮立即刷新所有数据
- 若 HTTP 502：确认后端已启动，可用环境变量 `PYRA_API_BASE=http://127.0.0.1:8000/api`
- 交易流水可搜索过滤
""")

