# -*- coding: utf-8 -*-
"""基金页 —— 概览 / 排行榜 / 精选 / 搜索 / 单只基金净值详情

数据源：8001 prediction-server 的 /fund/** 接口（akshare 东财口径）
- 排行字段含：单位净值、累计净值、日增长率、近1周/1月/3月/6月/1年/3年、今年来、成立来、手续费
- 涨红跌绿（中国证券惯例）
"""

import pandas as pd
import streamlit as st

import api
import components as ui

st.header("基金中心", icon=":material/savings:")

# ---------------- 市场概览 ----------------

@st.fragment(run_every="60s")
def overview() -> None:
    ov = api.fund_overview()
    if not ov:
        st.warning("基金概览暂时不可用（8001 服务未就绪或数据源不可达）")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("基金总数", f"{ov.get('total', 0):,}")
    c2.metric("今日上涨", f"{ov.get('up', 0):,}", delta=f"+{ov.get('up', 0)}", delta_color="off")
    c3.metric("今日下跌", f"{ov.get('down', 0):,}", delta=f"-{ov.get('down', 0)}", delta_color="off")
    c4.metric("平均日涨幅", f"{float(ov.get('avgDayPct') or 0):+.3f}%",
              delta=f"周 {float(ov.get('avgWeekPct') or 0):+.2f}%", delta_color="off")
    st.caption(f"数据更新时间：{ov.get('updated_at', '')}　（全市场约 2 万只公募基金）")


overview()

# ---------------- 精选（每日 / 每周） ----------------

st.subheader("精选基金", divider=True)
pick_tab_d, pick_tab_w = st.tabs(["每日精选", "每周精选"], on_change="rerun")

if pick_tab_d.open:
    picks = api.fund_picks("daily", n=8)
    if picks and picks.get("items"):
        st.caption(f"按{picks.get('rank_by', '当日收益率')}排序 · 更新于 {picks.get('updated_at', '')}")
        ui.fund_metric_row(picks["items"], "每日精选")
    else:
        st.info("每日精选暂不可用")

if pick_tab_w.open:
    picks = api.fund_picks("weekly", n=8)
    if picks and picks.get("items"):
        st.caption(f"按{picks.get('rank_by', '近1周')}排序 · 更新于 {picks.get('updated_at', '')}")
        ui.fund_metric_row(picks["items"], "每周精选")
    else:
        st.info("每周精选暂不可用")

# ---------------- 排行榜 ----------------

st.subheader("收益排行榜", divider=True)

with st.container(horizontal=True, horizontal_alignment="left"):
    period = st.segmented_control(
        "周期",
        list(api.FUND_PERIODS.keys()),
        default="day",
        format_func=lambda k: api.FUND_PERIODS.get(k, k),
        key="fund_rank_period",
        label_visibility="collapsed",
    )
    type_kw = st.text_input(
        "类型过滤",
        value="",
        placeholder="基金名称包含，如 债券 / 指数 / 医药 / 消费",
        key="fund_type_filter",
        label_visibility="collapsed",
    )
    topn = st.selectbox("条数", [20, 50, 100], index=1, key="fund_rank_topn",
                        label_visibility="collapsed")

period = period or "day"
items = api.fund_rank(period, n=int(topn), fund_type=type_kw.strip())
if not items:
    st.info("该条件下暂无排行数据（可尝试更换周期或清空类型过滤）")
else:
    df = pd.DataFrame(
        [
            {
                "code": it.get("code", ""),
                "name": it.get("name", ""),
                "nav": it.get("nav"),
                "navAcc": it.get("navAcc"),
                "dayPct": it.get("dayPct"),
                "weekPct": it.get("weekPct"),
                "monthPct": it.get("monthPct"),
                "yearPct": it.get("yearPct"),
                "ytdPct": it.get("ytdPct"),
                "feePct": it.get("feePct"),
            }
            for it in items
        ]
    )
    styled = ui.colorize_cells(
        df.style.format(
            {
                "nav": "{:.4f}",
                "navAcc": "{:.4f}",
                "dayPct": "{:+.2f}%",
                "weekPct": "{:+.2f}%",
                "monthPct": "{:+.2f}%",
                "yearPct": "{:+.2f}%",
                "ytdPct": "{:+.2f}%",
                "feePct": "{:.2f}%",
            },
            na_rep="-",
        ),
        ["dayPct", "weekPct", "monthPct", "yearPct", "ytdPct"],
    )
    event = st.dataframe(
        styled,
        hide_index=True,
        width="stretch",
        height=560,
        on_select="rerun",
        selection_mode="single-row",
        key="fund_rank_table",
        column_config={
            "code": st.column_config.TextColumn("代码", width="small"),
            "name": st.column_config.TextColumn("基金名称", width="medium"),
            "nav": st.column_config.NumberColumn("单位净值", format="%.4f"),
            "navAcc": st.column_config.NumberColumn("累计净值", format="%.4f"),
            "dayPct": st.column_config.NumberColumn("日", format="%+.2f%%"),
            "weekPct": st.column_config.NumberColumn("近1周", format="%+.2f%%"),
            "monthPct": st.column_config.NumberColumn("近1月", format="%+.2f%%"),
            "yearPct": st.column_config.NumberColumn("近1年", format="%+.2f%%"),
            "ytdPct": st.column_config.NumberColumn("今年来", format="%+.2f%%"),
            "feePct": st.column_config.NumberColumn("手续费", format="%.2f%%"),
        },
    )
    rows = event.selection.rows
    if rows:
        st.session_state.current_fund = df.iloc[rows[0]]["code"]
        st.rerun()
    st.caption("点击任意行查看该基金净值走势详情")

# ---------------- 基金搜索 ----------------

st.subheader("基金搜索", divider=True)

with st.container(horizontal=True, horizontal_alignment="left"):
    kw = st.text_input(
        "关键词",
        value="",
        placeholder="基金代码 / 名称 / 拼音缩写，如 000001、华夏、HXCZHH",
        key="fund_search_kw",
        label_visibility="collapsed",
    )

if kw.strip():
    hits = api.fund_search(kw.strip(), limit=30)
    if not hits:
        st.caption("未找到匹配基金")
    else:
        sdf = pd.DataFrame(
            [{"code": h.get("code", ""), "name": h.get("name", ""), "type": h.get("type", "")}
             for h in hits]
        )
        ev = st.dataframe(
            sdf,
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            key="fund_search_table",
            column_config={
                "code": st.column_config.TextColumn("代码", width="small"),
                "name": st.column_config.TextColumn("基金名称"),
                "type": st.column_config.TextColumn("类型"),
            },
        )
        srows = ev.selection.rows
        if srows:
            st.session_state.current_fund = sdf.iloc[srows[0]]["code"]
            st.rerun()

# ---------------- 单只基金净值详情 ----------------

st.subheader("基金净值详情", divider=True)

default_fund = st.session_state.get("current_fund", "")
fund_code = st.text_input(
    "基金代码",
    value=default_fund,
    placeholder="6 位基金代码，如 000001",
    key="fund_nav_code_input",
)

if fund_code.strip():
    code = fund_code.strip()
    if not (code.isdigit() and len(code) == 6):
        st.warning("请输入 6 位数字基金代码")
    else:
        nav = api.fund_nav(code)
        if not nav or not nav.get("data"):
            st.info(f"基金 {code} 暂无净值数据")
        else:
            data = nav["data"]
            name = nav.get("name") or f"基金 {code}"
            latest = data[-1]
            prev = data[-2] if len(data) >= 2 else None
            nav_val = latest.get("nav")
            day_pct = latest.get("dayPct")
            c = ui.up_down_color(day_pct or 0)

            st.markdown(
                f"<span style='font-size:15px;color:{ui.TEXT}'>{name}　"
                f"<span style='font-size:12px;color:{ui.AXIS_LABEL}'>{code}</span></span>",
                unsafe_allow_html=True,
            )
            m1, m2, m3, m4 = st.columns(4)
            m1.markdown(
                f"<span style='font-size:30px;font-weight:700;color:{c}'>{nav_val:.4f}</span><br>"
                f"<span style='font-size:11px;color:{ui.AXIS_LABEL}'>单位净值</span>",
                unsafe_allow_html=True,
            )
            m2.markdown(
                f"<span style='font-size:22px;color:{c}'>"
                f"{ui.fmt_signed(day_pct, '{:+.2f}%')}</span><br>"
                f"<span style='font-size:11px;color:{ui.AXIS_LABEL}'>日增长率</span>",
                unsafe_allow_html=True,
            )
            m3.metric("净值日期", latest.get("date", "-"))
            # 区间收益（从最近 250 个净值点算近 1 年）
            if len(data) > 250:
                base = data[-251].get("nav")
                if base:
                    yr = (nav_val / base - 1) * 100
                    m4.metric("近1年收益", f"{yr:+.2f}%")
            else:
                m4.metric("数据点", f"{len(data)}")

            st.echarts_chart(ui.fund_nav_option(data[-500:], name), height=420)
            st.caption(
                f"净值走势区间：{data[-500]['date']} ~ {latest['date']}　"
                f"（单位净值 + 日增长率双轴，涨红跌绿）"
            )
