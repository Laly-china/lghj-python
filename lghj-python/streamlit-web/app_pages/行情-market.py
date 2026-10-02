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
