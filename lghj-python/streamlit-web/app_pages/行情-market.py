# -*- coding: utf-8 -*-
"""行情页 —— 指数看板 + 股票搜索 + 自选速览（参考同花顺首页）"""

import pandas as pd
import streamlit as st

import api
import components as ui

st.header("行情中心", icon=":material/monitoring:")


@st.fragment(run_every="5s")
def live_indices() -> None:
    """三大指数，5 秒自刷新。"""
    ui.index_metrics()


live_indices()

# ---------------- 每日 / 每周精选（基金 + 个股） ----------------

st.subheader("每日 · 每周精选", divider=True)
st.caption("覆盖全市场基金与 A 股个股，按收益率排行，附净值 / 收益 / 成交额等详细信息")

@st.fragment()
def picks_board() -> None:
    tab_daily, tab_weekly = st.tabs(["每日精选", "每周精选"], on_change="rerun")

    if tab_daily.open:
        left, right = st.columns(2)
        with left:
            st.markdown("**精选基金**")
            funds = api.fund_picks("daily", n=6)
            if funds and funds.get("items"):
                ui.fund_metric_row(funds["items"][:6], "每日基金")
                st.page_link("app_pages/基金-fund.py", label="查看基金排行 →",
                             icon=":material/arrow_forward:")
            else:
                st.caption("基金数据暂不可用")
        with right:
            st.markdown("**精选个股**")
            stocks = api.stock_rank_daily(n=6)
            if stocks:
                ui.stock_pick_row(stocks[:6], "每日个股")
                st.page_link("app_pages/个股-stock.py", label="查看个股详情 →",
                             icon=":material/arrow_forward:")
            else:
                st.caption("个股数据暂不可用")

    if tab_weekly.open:
        left, right = st.columns(2)
        with left:
            st.markdown("**精选基金（近1周）**")
            funds = api.fund_picks("weekly", n=6)
            if funds and funds.get("items"):
                ui.fund_metric_row(funds["items"][:6], "每周基金")
                st.page_link("app_pages/基金-fund.py", label="查看基金排行 →",
                             icon=":material/arrow_forward:")
            else:
                st.caption("基金数据暂不可用")
        with right:
            st.markdown("**精选个股（近5日）**")
            stocks = api.stock_rank_weekly(n=6, pool=120)
            if stocks:
                ui.stock_pick_row(stocks[:6], "每周个股", period_key="weekPct")
                st.page_link("app_pages/个股-stock.py", label="查看个股详情 →",
                             icon=":material/arrow_forward:")
            elif stocks == []:
                st.caption("个股周榜计算中或暂不可用（首次约需 1~2 分钟）")


picks_board()

# ---------------- 股票搜索 ----------------

st.subheader("股票搜索", divider=True)

with st.container(horizontal=True, horizontal_alignment="left"):
    @st.fragment()
    def search_box() -> None:
        kw = st.text_input(
            "关键词",
            value=st.session_state.get("market_kw", ""),
            placeholder="代码 / 名称 / 行业，如 600519、银行",
            label_visibility="collapsed",
            key="market_search",
        )
        if kw != st.session_state.get("market_kw"):
            st.session_state.market_kw = kw
        results = api.search_stocks(kw) if kw else []
        if kw and not results:
            st.caption("未找到匹配股票")
        elif results:
            df = pd.DataFrame(
                [
                    {
                        "symbol": r.get("symbol", ""),
                        "name": r.get("name", ""),
                        "industry": r.get("industry", "") or "-",
                    }
                    for r in results[:20]
                ]
            )
            event = st.dataframe(
                df,
                hide_index=True,
                width="stretch",
                on_select="rerun",
                selection_mode="single-row",
                key="market_search_result",
                column_config={
                    "symbol": st.column_config.TextColumn("代码", width="small"),
                    "name": st.column_config.TextColumn("名称"),
                    "industry": st.column_config.TextColumn("行业"),
                },
            )
            rows = event.selection.rows
            if rows:
                st.session_state.current_symbol = df.iloc[rows[0]]["symbol"]
                st.switch_page("app_pages/个股-stock.py")


search_box()

# ---------------- 自选速览 ----------------

if st.session_state.get("token"):
    st.subheader("自选速览", divider=True)
    try:
        watch = api.optional_list()
    except Exception:  # noqa: BLE001
        watch = []
    if not watch:
        st.caption("暂无自选股，可到「个股」页面添加")
    else:
        df = pd.DataFrame(
            [
                {
                    "symbol": w.get("symbol", ""),
                    "name": w.get("name", ""),
                    "price": w.get("price"),
                    "changePercent": w.get("changePercent"),
                }
                for w in watch
            ]
        )
        styled = ui.colorize_cells(
            df.style.format({"price": "{:.2f}", "changePercent": "{:+.2f}%"}),
            ["price", "changePercent"],
        )
        event = st.dataframe(
            styled,
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            key="market_watch_rows",
            column_config={
                "symbol": st.column_config.TextColumn("代码", width="small"),
                "name": st.column_config.TextColumn("名称"),
                "price": st.column_config.NumberColumn("现价", format="%.2f"),
                "changePercent": st.column_config.NumberColumn("涨跌幅", format="%+.2f%%"),
            },
        )
        rows = event.selection.rows
        if rows:
            st.session_state.current_symbol = df.iloc[rows[0]]["symbol"]
            st.switch_page("app_pages/个股-stock.py")

st.caption("提示：点击列表行进入个股详情（分时 / K线 / 预测 / 新闻）")
