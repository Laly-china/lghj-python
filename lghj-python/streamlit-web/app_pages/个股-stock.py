# -*- coding: utf-8 -*-
"""个股页 —— 分时 / K线 / LSTM 预测 / 新闻（参考同花顺个股详情布局）"""

import pandas as pd
import streamlit as st

import api
import components as ui

st.header("个股详情", icon=":material/candlestick_chart:")

# ---------------- 代码选择 ----------------

symbol = st.session_state.get("current_symbol", "sh600519")
with st.container(horizontal=True, horizontal_alignment="left"):
    sym_input = st.text_input(
        "代码",
        value=symbol,
        label_visibility="collapsed",
        key="stock_symbol_input",
    )
    if st.button("查看", icon=":material/search:", type="primary"):
        st.session_state.current_symbol = sym_input.strip()
        st.rerun()

symbol = st.session_state.get("current_symbol", "sh600519").strip() or "sh600519"
market, code = api.split_symbol(symbol)

# ---------------- 实时行情头部（5 秒自刷新） ----------------


@st.fragment(run_every="5s")
def live_quote() -> None:
    ui.quote_header(api.get_quote(market, code), symbol)


live_quote()

# 加/移自选
if st.session_state.get("token"):
    watch_symbols = {w.get("symbol") for w in api.optional_list()}
    in_watch = symbol in watch_symbols
    col_a, col_b = st.columns([1, 6])
    with col_a:
        if in_watch:
            if st.button("移除自选", icon=":material/star:"):
                ok, msg = api.optional_remove(symbol)
                st.toast(msg, icon=":material/check_circle:" if ok else ":material/error:")
                st.rerun()
        else:
            if st.button("加自选", icon=":material/star_border:"):
                ok, msg = api.optional_add(symbol)
                st.toast(msg, icon=":material/check_circle:" if ok else ":material/error:")
                st.rerun()

# ---------------- 四个标签页（懒加载：仅激活标签计算） ----------------

tab_min, tab_k, tab_p, tab_n = st.tabs(
    ["分时", "K线", "AI 预测", "新闻"], on_change="rerun"
)

if tab_min.open:
    minute = api.get_minute(symbol)
    if minute:
        st.echarts_chart(ui.minute_option(minute), height=430)
    else:
        st.info("暂无分时数据（非交易时段或该代码不支持）")

if tab_k.open:
    period = st.segmented_control(
        "周期", ["D", "W", "M"], default="D",
        format_func={"D": "日线", "W": "周线", "M": "月线"}.get,
        key="stock_kline_period",
    )
    df = api.get_kline(symbol, period or "D")
    if df.empty:
        st.info("暂无 K 线数据")
    else:
        st.echarts_chart(ui.kline_option(df), height=430)

if tab_p.open:
    pred = api.get_predict(symbol)
    if pred and pred.get("predictions"):
        hist = api.get_kline(symbol, "D")
        st.echarts_chart(ui.predict_option(hist, pred["predictions"]), height=430)
        p = pred["predictions"]
        st.caption(
            f"模型：LSTM(2×64) · 预测区间 {p[0]['date']} ~ {p[-1]['date']} · "
            f"现价参考 {float(p[0]['price']):.2f} → 30 日 {float(p[-1]['price']):.2f}"
        )
    else:
        st.info("该代码暂无预测数据（支持 A 股个股与指数）")

if tab_n.open:
    news = api.get_news(symbol, recent_n=20)
    if not news:
        st.info("暂无相关新闻")
    for n in news:
        with st.container(border=True):
            st.markdown(
                f"**{n.get('title', '')}**　"
                f"<span style='color:#8B949E;font-size:12px'>"
                f"{n.get('source', '')} · {n.get('publishTime', '')}</span>",
                unsafe_allow_html=True,
            )
            content = n.get("content") or ""
            if content:
                st.caption(content[:120] + ("…" if len(content) > 120 else ""))
            if n.get("url"):
                st.page_link(n["url"], label="阅读原文", icon=":material/open_in_new:")
