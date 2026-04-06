"""
交易录入页面

功能：
- 搜索/输入资产代码（A股、基金、黄金）
- 录入交易信息（类型、价格、数量、手续费、备注）
- 批量导入持仓信息（总金额 + 份数，自动计算成本价）
- 提交至后端 API
"""

import streamlit as st
import httpx
import json
from datetime import datetime, timedelta
import pandas as pd

# 页面配置
st.set_page_config(
    page_title="交易录入",
    page_icon="📝",
    layout="wide"
)

# 后端 API 基础 URL
API_BASE = "http://localhost:8000/api"

# ────────────────────────────────────────────────────────────────
# 工具函数
# ────────────────────────────────────────────────────────────────

def search_symbols(query, asset_type=None):
    """搜索标的代码"""
    try:
        r = httpx.get(
            f"{API_BASE}/market/search",
            params={"q": query, "limit": 20},
            timeout=5
        )
        if r.status_code == 200:
            results = r.json()
            # 如果指定了 asset_type，进行过滤
            if asset_type:
                results = [r for r in results if r.get("asset_type") == asset_type]
            return results
        else:
            st.error(f"搜索失败: {r.status_code}")
            return []
    except Exception as e:
        st.error(f"搜索出错: {str(e)}")
        return []


def add_stock_prefix(code):
    """为 A 股代码添加交易所前缀"""
    code = str(code).strip()
    # 如果已有前缀，直接返回
    if code.startswith('sh') or code.startswith('sz'):
        return code
    # 根据代码首位判断交易所
    if code.startswith('6'):
        return f"sh{code}"
    else:  # 0 或 3
        return f"sz{code}"


def submit_trade(payload):
    """提交交易记录"""
    try:
        r = httpx.post(f"{API_BASE}/trades", json=payload, timeout=10)
        if r.status_code == 201:
            return True, "✅ 录入成功"
        else:
            return False, f"❌ 录入失败 ({r.status_code}): {r.text}"
    except Exception as e:
        return False, f"❌ 提交出错: {str(e)}"


# ────────────────────────────────────────────────────────────────
# 页面标题
# ────────────────────────────────────────────────────────────────

st.title("📝 交易录入")
st.markdown("记录每一笔买卖交易、分红派息")

st.divider()

# ────────────────────────────────────────────────────────────────
# 初始化会话状态
# ────────────────────────────────────────────────────────────────

if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = ""
if "selected_fund_type" not in st.session_state:
    st.session_state.selected_fund_type = None


# ────────────────────────────────────────────────────────────────
# 单笔 vs 批量导入切换
# ────────────────────────────────────────────────────────────────

tab1, tab2 = st.tabs(["📋 单笔录入", "📊 批量导入"])

# ════════════════════════════════════════════════════════════════
# TAB 1：单笔录入
# ════════════════════════════════════════════════════════════════

with tab1:
    st.subheader("📋 录入新交易")

    # 第一行：资产类型
    col_asset, col_trade_type = st.columns([0.5, 0.5])

    with col_asset:
        asset_type = st.selectbox(
            "资产类型 *",
            options=["STOCK_A", "FUND", "GOLD_SPOT"],
            format_func=lambda x: {
                "STOCK_A": "A 股",
                "FUND": "基金（ETF/LOF）",
                "GOLD_SPOT": "现货黄金"
            }[x],
            key="asset_type"
        )

    with col_trade_type:
        trade_type = st.selectbox(
            "交易类型 *",
            options=["BUY", "SELL", "DIVIDEND"],
            format_func=lambda x: {
                "BUY": "买入",
                "SELL": "卖出",
                "DIVIDEND": "分红派息"
            }[x],
            key="trade_type"
        )

    st.divider()

    # ─── 代码输入与搜索 ───
    if asset_type == "GOLD_SPOT":
        # 黄金：固定选项
        symbol = st.selectbox(
            "品种 *",
            options=["Au9999", "Au99.99", "Au(T+D)"],
            key="gold_symbol"
        )

    else:
        # A股/基金：搜索 + 代码输入
        st.markdown("**代码搜索与选择：**")

        col_search_input, col_search_btn = st.columns([0.8, 0.2])

        with col_search_input:
            search_query = st.text_input(
                "搜索代码或名称",
                placeholder="输入股票代码、股票名称或基金代码",
                key="search_input"
            )

        with col_search_btn:
            if st.button("🔍 搜索", key="search_btn"):
                if search_query:
                    st.session_state.search_results = search_symbols(search_query, asset_type)
                    st.rerun()

        # 显示搜索结果
        if st.session_state.search_results:
            st.markdown("**搜索结果：**")
            result_options = [
                f"{r['symbol']} - {r['name']} ({r['asset_type']})"
                for r in st.session_state.search_results
            ]
            selected_result = st.selectbox(
                "选择标的",
                options=range(len(result_options)),
                format_func=lambda i: result_options[i],
                key="search_select"
            )

            if selected_result is not None:
                selected_item = st.session_state.search_results[selected_result]
                st.session_state.selected_symbol = selected_item['symbol']
                st.session_state.selected_fund_type = selected_item.get('asset_type')
                st.success(f"✅ 已选择：{selected_item['symbol']} {selected_item['name']}")

        # 代码输入框（允许用户直接输入）
        symbol = st.text_input(
            "或直接输入代码",
            value=st.session_state.selected_symbol,
            placeholder="例：600519 或 510300 或 Au9999",
            key="symbol_direct"
        )
        symbol = symbol.strip() if symbol else ""

    st.divider()

    # 第二行：价格、数量、手续费
    col_price, col_qty, col_comm = st.columns(3)

    with col_price:
        price = st.number_input(
            "单价（元）*",
            min_value=0.0,
            step=0.01,
            value=0.0,
            key="price"
        )

    with col_qty:
        quantity = st.number_input(
            "数量 *",
            min_value=0.0,
            step=0.01,
            value=0.0,
            key="quantity"
        )

    with col_comm:
        commission = st.number_input(
            "手续费（元）",
            min_value=0.0,
            step=0.01,
            value=0.0,
            key="commission"
        )

    # 第三行：交易日期
    col_date, col_empty = st.columns([0.5, 0.5])

    with col_date:
        trade_date = st.date_input(
            "交易日期 *",
            value=datetime.now().date(),
            key="trade_date"
        )

    # 第四行：备注
    notes = st.text_area(
        "备注（说明交易原因等）",
        placeholder="例：加仓消费龙头，看好长期前景",
        height=80,
        key="notes"
    )

    st.divider()

    # ────────────────────────────────────────────────────────────────
    # 提交按钮
    # ────────────────────────────────────────────────────────────────

    col_submit, col_reset = st.columns([0.3, 0.3])

    with col_submit:
        if st.button("✅ 提交交易", key="submit_btn", type="primary"):
            # 验证必填项
            errors = []
            if not symbol:
                errors.append("❌ 代码不能为空")
            if price <= 0:
                errors.append("❌ 单价必须 > 0")
            if quantity <= 0:
                errors.append("❌ 数量必须 > 0")

            if errors:
                st.error("\n".join(errors))
            else:
                # 处理 A 股代码前缀
                submit_symbol = symbol
                if asset_type == "STOCK_A":
                    submit_symbol = add_stock_prefix(symbol)

                # 构建提交数据
                payload = {
                    "asset_type": asset_type,
                    "symbol": submit_symbol,
                    "trade_date": trade_date.isoformat(),
                    "trade_type": trade_type,
                    "price": float(price),
                    "quantity": float(quantity),
                    "commission": float(commission),
                    "notes": notes if notes else None
                }

                # 提交
                with st.spinner("提交中..."):
                    success, message = submit_trade(payload)

                if success:
                    st.success(message)
                    # 清空表单
                    st.session_state.selected_symbol = ""
                    st.session_state.search_results = []
                    st.session_state.selected_fund_type = None
                    st.balloons()
                    # 延迟后跳转
                    import time
                    time.sleep(1)
                    st.info("将在 2 秒后跳转到持仓看板...")
                    time.sleep(1)
                    st.switch_page("app.py")
                else:
                    st.error(message)

    with col_reset:
        if st.button("🔄 清空表单", key="reset_btn"):
            st.session_state.selected_symbol = ""
            st.session_state.search_results = []
            st.session_state.selected_fund_type = None
            st.rerun()

    st.divider()

    # ────────────────────────────────────────────────────────────────
    # 提示信息
    # ────────────────────────────────────────────────────────────────

    st.markdown("""
    ### 📌 操作指南

    **代码格式：**
    - **A 股**：输入 6 位数字代码（如 600519），系统自动添加 sh/sz 前缀
    - **ETF/LOF**：输入 6 位数字代码（如 510300 或 159915）
    - **黄金**：从下拉菜单选择

    **交易类型：**
    - **买入 (BUY)**：购入持仓
    - **卖出 (SELL)**：减少持仓
    - **分红派息 (DIVIDEND)**：分红收入

    **手续费：**
    - 包括佣金、印花税、过户费等所有费用
    - 黄金通常为 0

    **提示：**
    - 如果搜索未显示结果，说明缓存还在加载，可直接输入代码
    - 交易日期默认为今天，可自行修改
    - 所有必填项（带 * 符号）必须填写
    """)


# ════════════════════════════════════════════════════════════════
# TAB 2：批量导入
# ════════════════════════════════════════════════════════════════

with tab2:
    st.subheader("📊 批量导入持仓")
    st.markdown("输入总金额和份数，系统自动计算成本价 (成本价 = 总金额 ÷ 份数)")

    st.divider()

    # 初始化默认数据
    if "batch_import_data" not in st.session_state:
        st.session_state.batch_import_data = pd.DataFrame({
            "资产类型": ["STOCK_A", "FUND"],
            "代码": ["", ""],
            "名称": ["", ""],
            "份数": [0.0, 0.0],
            "总金额(元)": [0.0, 0.0],
            "交易日期": [datetime.now().date(), datetime.now().date()],
            "备注": ["", ""]
        })

    # 可编辑表格
    st.markdown("**持仓数据编辑：**")
    edited_df = st.data_editor(
        st.session_state.batch_import_data,
        use_container_width=True,
        num_rows="dynamic",
        key="batch_editor",
        column_config={
            "资产类型": st.column_config.SelectboxColumn(
                "资产类型 *",
                options=["STOCK_A", "FUND", "GOLD_SPOT"],
                required=True,
            ),
            "代码": st.column_config.TextColumn(
                "代码 * (输入后点搜索)",
                required=True,
            ),
            "名称": st.column_config.TextColumn(
                "名称（自动填充）",
                disabled=True,
            ),
            "份数": st.column_config.NumberColumn(
                "份数 *",
                min_value=0.0,
                step=0.01,
                required=True,
            ),
            "总金额(元)": st.column_config.NumberColumn(
                "总金额(元) *",
                min_value=0.0,
                step=0.01,
                required=True,
            ),
            "交易日期": st.column_config.DateColumn(
                "交易日期 *",
                format="YYYY-MM-DD",
            ),
            "备注": st.column_config.TextColumn(
                "备注",
            ),
        }
    )

    st.divider()

    # 搜索并填充名称功能
    col_search, col_clear_names = st.columns([0.3, 0.3])

    with col_search:
        if st.button("🔍 搜索代码并填充名称", key="search_symbols_btn"):
            with st.spinner("搜索中..."):
                for idx, row in edited_df.iterrows():
                    code = str(row["代码"]).strip()
                    if not code:
                        continue

                    try:
                        # 调用搜索 API
                        r = httpx.get(
                            f"{API_BASE}/market/search",
                            params={"q": code, "limit": 1},
                            timeout=5
                        )
                        if r.status_code == 200:
                            results = r.json()
                            if results:
                                # 取第一个结果的名称
                                edited_df.at[idx, "名称"] = results[0]["name"]
                        else:
                            st.warning(f"⚠️ 代码 {code} 搜索失败 (HTTP {r.status_code})")
                    except Exception as e:
                        st.warning(f"⚠️ 代码 {code} 搜索异常: {str(e)}")

                st.session_state.batch_import_data = edited_df
                st.success("✅ 搜索完成！")
                st.rerun()

    st.divider()

    # 预览和计算成本价
    st.markdown("**成本价预览：**")

    preview_data = []
    for idx, row in edited_df.iterrows():
        if row["份数"] > 0 and row["总金额(元)"] > 0:
            # 四舍五入到4位小数，避免浮点数精度问题
            cost_price = round(row["总金额(元)"] / row["份数"], 4)
            preview_data.append({
                "资产类型": row["资产类型"],
                "代码": row["代码"],
                "名称": row["名称"],
                "份数": f"{row['份数']:.2f}",
                "总金额": f"¥{row['总金额(元)']:.2f}",
                "成本价": f"¥{cost_price:.4f}",
                "交易日期": row["交易日期"],
            })

    if preview_data:
        preview_df = pd.DataFrame(preview_data)
        st.dataframe(preview_df, use_container_width=True, hide_index=True)
    else:
        st.info("请填写至少一条持仓记录（份数 > 0，总金额 > 0）")

    st.divider()

    # 批量提交
    col_import, col_clear = st.columns([0.3, 0.3])

    with col_import:
        if st.button("✅ 批量导入", key="batch_import_btn", type="primary"):
            errors = []
            success_count = 0
            failed_trades = []

            for idx, row in edited_df.iterrows():
                # 验证必填项
                code = str(row["代码"]).strip() if pd.notna(row["代码"]) else ""
                if not code or code.lower() == "nan":
                    errors.append(f"第 {idx + 1} 行：代码不能为空")
                    continue
                if pd.isna(row["份数"]) or row["份数"] <= 0:
                    errors.append(f"第 {idx + 1} 行：份数必须 > 0")
                    continue
                if pd.isna(row["总金额(元)"]) or row["总金额(元)"] <= 0:
                    errors.append(f"第 {idx + 1} 行：总金额必须 > 0")
                    continue

                # 计算成本价（四舍五入到4位小数，避免浮点数精度问题）
                cost_price = round(row["总金额(元)"] / row["份数"], 4)

                # 处理 A 股代码前缀
                submit_symbol = code
                if row["资产类型"] == "STOCK_A":
                    submit_symbol = add_stock_prefix(submit_symbol)

                # 构建提交数据
                payload = {
                    "asset_type": row["资产类型"],
                    "symbol": submit_symbol,
                    "trade_date": row["交易日期"].isoformat(),
                    "trade_type": "BUY",  # 批量导入默认为买入
                    "price": float(cost_price),
                    "quantity": float(row["份数"]),
                    "commission": 0.0,  # 批量导入时佣金设为 0
                    "notes": f"批量导入:{row['备注']}" if row["备注"] else "批量导入"
                }

                # 提交
                success, message = submit_trade(payload)
                if success:
                    success_count += 1
                else:
                    failed_trades.append({
                        "代码": row["代码"],
                        "错误": message
                    })

            # 显示结果
            if errors:
                st.error("**验证错误：**\n" + "\n".join(errors))

            if success_count > 0:
                st.success(f"✅ 成功导入 {success_count} 条持仓记录")
                st.balloons()

            if failed_trades:
                st.error("**导入失败的记录：**")
                for failed in failed_trades:
                    st.error(f"❌ {failed['代码']}: {failed['错误']}")

            if not errors and success_count > 0 and not failed_trades:
                import time
                time.sleep(1)
                st.info("将在 2 秒后跳转到持仓看板...")
                time.sleep(1)
                st.switch_page("app.py")

    with col_clear:
        if st.button("🔄 清空数据", key="batch_clear_btn"):
            st.session_state.batch_import_data = pd.DataFrame({
                "资产类型": ["STOCK_A"],
                "代码": [""],
                "名称": [""],
                "份数": [0.0],
                "总金额(元)": [0.0],
                "交易日期": [datetime.now().date()],
                "备注": [""]
            })
            st.rerun()

    st.divider()

    st.markdown("""
    ### 📌 批量导入指南

    **工作原理：**
    - 输入持仓的总金额和份数
    - 系统自动计算成本价：`成本价 = 总金额 ÷ 份数`
    - 所有记录按 **买入 (BUY)** 处理，交易日期可自定义

    **代码格式：**
    - **A 股**：输入 6 位数字（如 600519），系统自动添加 sh/sz 前缀
    - **基金**：输入 6 位数字（如 510300）
    - **黄金**：输入 Au9999 或 Au99.99 等

    **示例：**
    | 资产类型 | 代码 | 份数 | 总金额 | 成本价计算 |
    |--------|------|------|--------|----------|
    | STOCK_A | 600519 | 10 | 15000 | 15000÷10=1500元 |
    | FUND | 510300 | 500 | 2400 | 2400÷500=4.8元 |
    | GOLD_SPOT | Au9999 | 50 | 24000 | 24000÷50=480元 |

    **提示：**
    - 表格支持动态添加行（点击下方 + 号）
    - 可随时修改已填数据，实时计算成本价
    - 交易日期默认为今天，可根据实际买入日期调整
    """)
