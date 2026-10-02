# -*- coding: utf-8 -*-
"""自选股页 —— 列表 + 现价/涨跌幅（涨红跌绿），点击行进个股"""

import pandas as pd
import streamlit as st

import api
import components as ui

st.header("自选股", icon=":material/star:")

ui.require_login()

watch = api.optional_list()
if not watch:
    st.caption("暂无自选股：到「行情」搜索股票，或在「个股」页面点击「加自选」")
    st.stop()

df = pd.DataFrame(
    [
        {
            "symbol": w.get("symbol", ""),
            "name": w.get("name", ""),
            "price": w.get("price"),
            "changePercent": w.get("changePercent"),
            "volume": w.get("volume"),
            "followTime": w.get("followTime"),
        }
        for w in watch
    ]
)
styled = ui.colorize_cells(
    df.style.format(
        {"price": "{:.2f}", "changePercent": "{:+.2f}%"}, na_rep="-"
    ),
    ["price", "changePercent"],
)
event = st.dataframe(
    styled,
    hide_index=True,
    width="stretch",
    on_select="rerun",
    selection_mode="single-row",
    key="watch_rows",
    column_config={
        "symbol": st.column_config.TextColumn("代码", width="small"),
        "name": st.column_config.TextColumn("名称"),
        "price": st.column_config.NumberColumn("现价", format="%.2f"),
        "changePercent": st.column_config.NumberColumn("涨跌幅", format="%+.2f%%"),
        "volume": st.column_config.NumberColumn("成交量"),
        "followTime": st.column_config.TextColumn("添加时间"),
    },
)

rows = event.selection.rows
if rows:
    sel = df.iloc[rows[0]]
    symbol = sel["symbol"]
    st.session_state.current_symbol = symbol
    left, right = st.columns([1, 1])
    with left:
        if st.button("查看行情 →", icon=":material/candlestick_chart:", type="primary"):
            st.switch_page("app_pages/个股-stock.py")
    with right:
        if st.button("移除自选", icon=":material/delete:"):
            ok, msg = api.optional_remove(symbol)
            st.toast(msg, icon=":material/check_circle:" if ok else ":material/error:")
            st.rerun()
