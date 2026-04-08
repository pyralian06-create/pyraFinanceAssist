"""
每日持仓收益看板

功能：
- 今日盈亏（金额 + 百分比）指标卡
- 历史组合日曲线：日盈亏金额 / 日收益率 / 累计盈亏（可切换）
- 各标的当日贡献堆叠柱状图
- 日度 leg 明细数据表

数据来源：后端 /api/portfolio/daily-pnl 及相关接口
"""

import streamlit as st
import httpx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta

st.set_page_config(
    page_title="每日收益看板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_BASE = "http://localhost:8000/api"

# ────────────────────────────────────────────────────────────
# 工具函数
# ────────────────────────────────────────────────────────────

def api_get(path: str, params: dict = None, timeout: int = 30):
    try:
        r = httpx.get(f"{API_BASE}{path}", params=params or {}, timeout=timeout)
        if r.status_code == 200:
            return r.json(), None
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return None, str(e)


def api_post(path: str, params: dict = None, timeout: int = 120):
    try:
        r = httpx.post(f"{API_BASE}{path}", params=params or {}, timeout=timeout)
        if r.status_code == 200:
            return r.json(), None
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return None, str(e)


def fmt_cny(val: float, sign: bool = False) -> str:
    if sign:
        return f"{'+'if val >= 0 else ''}¥{val:,.2f}"
    return f"¥{val:,.2f}"


def fmt_pct(val: float) -> str:
    if val is None:
        return "—"
    return f"{'+'if val >= 0 else ''}{val:.2f}%"


# ────────────────────────────────────────────────────────────
# 侧边栏
# ────────────────────────────────────────────────────────────

st.sidebar.title("设置")

preset = st.sidebar.selectbox(
    "快速日期区间",
    options=["最近 30 天", "最近 90 天", "最近 180 天", "今年至今", "自定义"],
)

today = date.today()
if preset == "最近 30 天":
    default_start, default_end = today - timedelta(days=30), today
elif preset == "最近 90 天":
    default_start, default_end = today - timedelta(days=90), today
elif preset == "最近 180 天":
    default_start, default_end = today - timedelta(days=180), today
elif preset == "今年至今":
    default_start, default_end = date(today.year, 1, 1), today
else:
    default_start, default_end = today - timedelta(days=90), today

if preset == "自定义":
    start_date = st.sidebar.date_input("开始日期", value=default_start)
    end_date = st.sidebar.date_input("结束日期", value=default_end)
else:
    start_date, end_date = default_start, default_end

metric_mode = st.sidebar.radio(
    "收益展示维度",
    options=["金额（CNY）", "百分比（%）"],
    index=0,
)

st.sidebar.divider()
st.sidebar.subheader("数据刷新")
refresh_start = st.sidebar.date_input("刷新起始日", value=today - timedelta(days=90))
refresh_end = st.sidebar.date_input("刷新截止日", value=today)
if st.sidebar.button("🔄 重算历史数据", help="拉取 K 线、港美换汇，写入数据库"):
    with st.spinner("正在重算，首次运行较慢（需拉取历史行情）..."):
        result, err = api_post(
            "/portfolio/daily-pnl/refresh",
            params={"start": str(refresh_start), "end": str(refresh_end)},
            timeout=300,
        )
    if err:
        st.sidebar.error(f"❌ {err}")
    else:
        st.sidebar.success(
            f"✅ 完成！写入 {result.get('rows_upserted', 0)} 行，"
            f"耗时 {result.get('elapsed_seconds', 0):.1f}s"
        )
        st.cache_data.clear()
        st.rerun()

# ────────────────────────────────────────────────────────────
# 主体
# ────────────────────────────────────────────────────────────

st.title("📈 每日持仓收益看板")
st.caption(f"展示区间：{start_date} → {end_date} · 所有金额单位：人民币（CNY）")

# ── 1. 今日盈亏指标 ──────────────────────────────────────────

today_data, today_err = api_get("/portfolio/today-pnl")

col1, col2, col3, col4 = st.columns(4)
if today_data and not today_err:
    mv = float(today_data["market_value"])
    pnl = float(today_data["daily_pnl"])
    pct = today_data.get("daily_pnl_percent")
    src = today_data.get("source", "?")
    pct_str = fmt_pct(pct) if pct is not None else "—"
    col1.metric("💰 今日持仓市值", fmt_cny(mv))
    col2.metric("📊 今日盈亏（金额）", fmt_cny(pnl, sign=True))
    col3.metric("📊 今日盈亏（%）", pct_str)
    col4.metric("数据来源", "实时估算" if src == "realtime" else "历史库")
else:
    for c in [col1, col2, col3, col4]:
        c.metric("—", "无数据")

st.divider()

# ── 2. 历史日曲线 ─────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_daily_series(s: str, e: str):
    data, err = api_get("/portfolio/daily-pnl", params={"start": s, "end": e})
    return data, err

series_data, series_err = load_daily_series(str(start_date), str(end_date))

if series_err:
    st.error(f"❌ 获取日曲线失败: {series_err}")
elif not series_data or not series_data.get("has_data"):
    st.info("📭 所选区间暂无历史数据。请在左侧「重算历史数据」后刷新。")
else:
    rows = series_data["series"]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["daily_pnl"] = df["daily_pnl"].astype(float)
    df["market_value"] = df["market_value"].astype(float)
    df["cumulative_pnl"] = df["cumulative_pnl"].astype(float)
    df["daily_pnl_percent"] = df["daily_pnl_percent"].astype(float, errors="ignore")

    use_pct = metric_mode == "百分比（%）"

    tab1, tab2, tab3 = st.tabs(["📊 日盈亏", "📈 累计盈亏", "💰 持仓市值"])

    with tab1:
        st.subheader("日度盈亏（相对前一日收盘）")
        y_col = "daily_pnl_percent" if use_pct else "daily_pnl"
        y_label = "当日收益率 (%)" if use_pct else "当日盈亏 (CNY)"
        colors = ["#ef5350" if v < 0 else "#26a69a" for v in df[y_col]]
        fig = go.Figure(
            go.Bar(
                x=df["date"],
                y=df[y_col],
                marker_color=colors,
                name=y_label,
                hovertemplate=(
                    "%{x|%Y-%m-%d}<br>" +
                    (f"收益率: %{{y:+.2f}}%<extra></extra>" if use_pct
                     else "盈亏: ¥%{y:,.2f}<extra></extra>")
                ),
            )
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
        fig.update_layout(
            yaxis_title=y_label,
            xaxis_title="日期",
            height=380,
            margin=dict(t=20, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("累计盈亏（从区间首日起）")
        fig2 = go.Figure(
            go.Scatter(
                x=df["date"],
                y=df["cumulative_pnl"],
                mode="lines+markers",
                line=dict(width=2),
                marker=dict(size=4),
                fill="tozeroy",
                fillcolor="rgba(38,166,154,0.15)",
                name="累计盈亏",
                hovertemplate="%{x|%Y-%m-%d}<br>累计: ¥%{y:,.2f}<extra></extra>",
            )
        )
        fig2.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
        fig2.update_layout(
            yaxis_title="累计盈亏 (CNY)",
            xaxis_title="日期",
            height=380,
            margin=dict(t=20, b=20),
        )
        st.plotly_chart(fig2, use_container_width=True)

    with tab3:
        st.subheader("每日总持仓市值（CNY）")
        fig3 = go.Figure(
            go.Scatter(
                x=df["date"],
                y=df["market_value"],
                mode="lines",
                line=dict(width=2),
                name="组合市值",
                hovertemplate="%{x|%Y-%m-%d}<br>市值: ¥%{y:,.2f}<extra></extra>",
            )
        )
        fig3.update_layout(
            yaxis_title="市值 (CNY)",
            xaxis_title="日期",
            height=380,
            margin=dict(t=20, b=20),
        )
        st.plotly_chart(fig3, use_container_width=True)

st.divider()

# ── 3. 各标的贡献堆叠图 ───────────────────────────────────────

st.subheader("📊 各标的当日盈亏贡献")

@st.cache_data(ttl=60)
def load_legs(s: str, e: str):
    data, err = api_get("/portfolio/daily-pnl/legs", params={"start": s, "end": e})
    return data, err

legs_data, legs_err = load_legs(str(start_date), str(end_date))

if legs_err:
    st.warning(f"⚠️ 获取 leg 明细失败: {legs_err}")
elif legs_data and len(legs_data) > 0:
    df_legs = pd.DataFrame(legs_data)
    df_legs["mark_date"] = pd.to_datetime(df_legs["mark_date"])
    df_legs["daily_pnl_cny"] = df_legs["daily_pnl_cny"].astype(float)
    df_legs["daily_pnl_percent"] = pd.to_numeric(df_legs["daily_pnl_percent"], errors="coerce")

    y_col_leg = "daily_pnl_percent" if use_pct else "daily_pnl_cny"
    y_label_leg = "当日收益率 (%)" if use_pct else "当日盈亏 (CNY)"

    fig4 = px.bar(
        df_legs,
        x="mark_date",
        y=y_col_leg,
        color="symbol",
        barmode="relative",
        labels={"mark_date": "日期", y_col_leg: y_label_leg, "symbol": "标的"},
        hover_data=["asset_type", "quantity_eod", "market_value_cny"],
        height=400,
    )
    fig4.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
    fig4.update_layout(margin=dict(t=20, b=20))
    st.plotly_chart(fig4, use_container_width=True)

    # Leg 明细数据表
    with st.expander("📋 查看 leg 明细数据"):
        display_cols = ["mark_date", "symbol", "asset_type", "quantity_eod",
                        "close_price_cny", "market_value_cny", "daily_pnl_cny", "daily_pnl_percent"]
        df_display = df_legs[[c for c in display_cols if c in df_legs.columns]].copy()
        df_display["mark_date"] = df_display["mark_date"].dt.strftime("%Y-%m-%d")
        df_display = df_display.rename(columns={
            "mark_date": "日期",
            "symbol": "代码",
            "asset_type": "资产类型",
            "quantity_eod": "日终持仓",
            "close_price_cny": "收盘价(CNY)",
            "market_value_cny": "市值(CNY)",
            "daily_pnl_cny": "当日盈亏(CNY)",
            "daily_pnl_percent": "当日收益率%",
        })
        st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.info("📭 leg 明细暂无数据。")

st.divider()
st.caption("💡 提示：历史数据需先通过左侧「重算历史数据」生成；今日数据每次打开页面自动实时估算。")
