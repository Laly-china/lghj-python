# -*- coding: utf-8 -*-
"""components.py —— 共享 UI 组件（同花顺风格）

- 颜色体系：中国证券惯例「涨红跌绿」，深色终端底
- 图表：Apache ECharts（st.echarts_chart 原生渲染），K线/分时/预测三类 option 构造
- 表格：pandas Styler 仅用于着色（格式化交给 column_config）
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

# 涨红跌绿（深色背景下的高可读色）
UP = "#FF5B5B"        # 涨
DOWN = "#00C08B"      # 跌
FLAT = "#8B949E"      # 平
AVG_LINE = "#F0B90B"  # 分时均价线（THS 黄）
TEXT = "#E8EAED"
GRID = "#2A3138"
AXIS_LABEL = "#8B949E"


def require_login() -> None:
    """未登录则跳转独立登录页（登录/注册已移出侧栏）。"""
    if not st.session_state.get("token"):
        st.info("该功能需要登录，正在前往登录页…")
        st.switch_page("app_pages/登录-login.py")
        st.stop()


def up_down_color(v: float) -> str:
    """按数值符号取色。"""
    if v is None or pd.isna(v):
        return FLAT
    return UP if v > 0 else (DOWN if v < 0 else FLAT)


def fmt_signed(v: float, fmt: str = "{:+.2f}") -> str:
    try:
        return fmt.format(float(v))
    except (TypeError, ValueError):
        return "-"


def colorize_cells(styler: pd.io.formats.style.Styler, columns: list[str]) -> pd.io.formats.style.Styler:
    """对指定数值列按符号着字色（涨红跌绿）。"""
    for col in columns:
        if col in styler.data.columns:
            styler = styler.map(
                lambda v, c=col: f"color: {up_down_color(v)}" if pd.notna(v) else None,
                subset=[col],
            )
    return styler


def quote_header(quote: dict | None, symbol: str) -> None:
    """个股行情头部：名称/现价/涨跌额/涨跌幅/今开/昨收/成交量（同花顺样式）。"""
    if not quote:
        st.caption(f"{symbol} · 暂无行情（非交易时段或代码不支持）")
        return
    change = float(quote.get("change") or 0)
    pct = float(quote.get("changePercent") or 0)
    c = up_down_color(change)
    arrow = "▲" if change > 0 else ("▼" if change < 0 else "—")
    title = st.container(horizontal=True, horizontal_alignment="left")
    st.markdown(
        f"<span style='font-size:15px;color:{TEXT}'>{quote.get('name', symbol)}　"
        f"<span style='font-size:12px;color:{AXIS_LABEL}'>{symbol}</span></span>",
        unsafe_allow_html=True,
    )
    price_col, chg_col, open_col, prev_col, vol_col = st.columns([1.2, 1, 0.8, 0.8, 1])
    with price_col:
        st.markdown(
            f"<span style='font-size:34px;font-weight:700;color:{c}'>"
            f"{float(quote.get('price') or 0):.2f}</span>",
            unsafe_allow_html=True,
        )
    with chg_col:
        st.markdown(
            f"<span style='font-size:18px;color:{c}'>{arrow} {fmt_signed(change)}　"
            f"{fmt_signed(pct, '{:+.2f}%')}</span>",
            unsafe_allow_html=True,
        )
    with open_col:
        st.markdown(f"今开 <span style='color:{TEXT}'>{_f(quote.get('open'))}</span>", unsafe_allow_html=True)
    with prev_col:
        st.markdown(f"昨收 <span style='color:{TEXT}'>{_f(quote.get('prevClose'))}</span>", unsafe_allow_html=True)
    with vol_col:
        st.markdown(f"成交量 <span style='color:{TEXT}'>{_vol(quote.get('volume'))}</span>", unsafe_allow_html=True)


def _f(v) -> str:
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return "-"


def _vol(v) -> str:
    try:
        n = float(v)
        return f"{n / 1e6:.2f}万手" if n >= 1e4 else f"{n:.0f}"
    except (TypeError, ValueError):
        return "-"


def _ma(series: pd.Series, n: int) -> list[float | None]:
    return [None if pd.isna(v) else round(float(v), 2) for v in series.rolling(n).mean()]


def _base_axis(extra: dict | None = None) -> dict:
    axis = {
        "axisLine": {"lineStyle": {"color": GRID}},
        "axisLabel": {"color": AXIS_LABEL, "fontSize": 11},
        "splitLine": {"lineStyle": {"color": "#1C2228"}},
    }
    if extra:
        axis.update(extra)
    return axis


def _tooltip() -> dict:
    return {
        "trigger": "axis",
        "axisPointer": {"type": "cross", "label": {"backgroundColor": "#1A2026"}},
        "backgroundColor": "#171C21",
        "borderColor": GRID,
        "textStyle": {"color": TEXT, "fontSize": 12},
    }


def kline_option(df: pd.DataFrame) -> dict:
    """日/周/月 K 线：蜡烛图 + MA5/10/20 + 成交量（THS 配色：红涨绿跌）。"""
    if df.empty:
        return {}
    dates = df["date"].tolist()
    kdata = df[["open", "close", "low", "high"]].values.tolist()
    ma5, ma10, ma20 = _ma(df["close"], 5), _ma(df["close"], 10), _ma(df["close"], 20)
    vols = df.get("volume", pd.Series([0] * len(df))).tolist() if "volume" in df else [0] * len(df)
    vol_colors = [
        {"value": v, "itemStyle": {"color": UP if c >= o else DOWN}}
        for v, c, o in zip(vols, df["close"], df["open"])
    ]
    return {
        "backgroundColor": "transparent",
        "animation": False,
        "tooltip": _tooltip(),
        "legend": {
            "data": ["MA5", "MA10", "MA20"],
            "textStyle": {"color": AXIS_LABEL},
            "top": 0,
        },
        "grid": [
            {"left": 60, "right": 20, "top": 28, "height": "58%"},
            {"left": 60, "right": 20, "top": "76%", "height": "16%"},
        ],
        "xAxis": [
            {"type": "category", "data": dates, "gridIndex": 0, **_base_axis({"boundaryGap": True})},
            {"type": "category", "data": dates, "gridIndex": 1, **_base_axis({"axisLabel": {"show": False}})},
        ],
        "yAxis": [
            {"type": "value", "scale": True, "gridIndex": 0, **_base_axis()},
            {"type": "value", "gridIndex": 1, **_base_axis({"axisLabel": {"show": False}, "splitLine": {"show": False}})},
        ],
        "dataZoom": [
            {"type": "inside", "xAxisIndex": [0, 1], "start": 60, "end": 100},
            {"type": "slider", "xAxisIndex": [0, 1], "start": 60, "end": 100,
             "bottom": 2, "height": 16, "borderColor": GRID, "fillerColor": "rgba(230,69,69,0.15)",
             "handleStyle": {"color": "#E64545"}, "textStyle": {"color": AXIS_LABEL}},
        ],
        "series": [
            {
                "name": "K线",
                "type": "candlestick",
                "data": kdata,
                "xAxisIndex": 0,
                "yAxisIndex": 0,
                "itemStyle": {"color": UP, "color0": DOWN, "borderColor": UP, "borderColor0": DOWN},
            },
            {"name": "MA5", "type": "line", "data": ma5, "showSymbol": False, "lineStyle": {"width": 1, "color": "#F0B90B"}},
            {"name": "MA10", "type": "line", "data": ma10, "showSymbol": False, "lineStyle": {"width": 1, "color": "#4A9EFF"}},
            {"name": "MA20", "type": "line", "data": ma20, "showSymbol": False, "lineStyle": {"width": 1, "color": "#B48CFF"}},
            {"name": "成交量", "type": "bar", "data": vol_colors, "xAxisIndex": 1, "yAxisIndex": 1},
        ],
    }


def minute_option(minute: list[dict]) -> dict:
    """当日分时：价格线 + 均价线（THS：白价黄均）+ 量柱。"""
    if not minute:
        return {}
    times = [str(m.get("time", "")) for m in minute]
    times = [f"{t[:2]}:{t[2:]}" if len(t) == 4 else t for t in times]
    prices = [m.get("price") for m in minute]
    avgs = [m.get("avg_price") for m in minute]
    vols = [m.get("volume") or 0 for m in minute]
    vol_colors = [
        {"value": v, "itemStyle": {"color": UP if (i > 0 and prices[i] >= prices[i - 1]) else DOWN}}
        for i, v in enumerate(vols)
    ]
    return {
        "backgroundColor": "transparent",
        "animation": False,
        "tooltip": _tooltip(),
        "legend": {"data": ["价格", "均价"], "textStyle": {"color": AXIS_LABEL}, "top": 0},
        "grid": [
            {"left": 60, "right": 20, "top": 28, "height": "58%"},
            {"left": 60, "right": 20, "top": "76%", "height": "16%"},
        ],
        "xAxis": [
            {"type": "category", "data": times, "gridIndex": 0, **_base_axis({"boundaryGap": False})},
            {"type": "category", "data": times, "gridIndex": 1, **_base_axis({"axisLabel": {"show": False}})},
        ],
        "yAxis": [
            {"type": "value", "scale": True, "gridIndex": 0, **_base_axis()},
            {"type": "value", "gridIndex": 1, **_base_axis({"axisLabel": {"show": False}, "splitLine": {"show": False}})},
        ],
        "series": [
            {"name": "价格", "type": "line", "data": prices, "showSymbol": False,
             "lineStyle": {"width": 1.4, "color": TEXT}, "color": TEXT},
            {"name": "均价", "type": "line", "data": avgs, "showSymbol": False,
             "lineStyle": {"width": 1.2, "color": AVG_LINE}, "color": AVG_LINE},
            {"name": "成交量", "type": "bar", "data": vol_colors, "xAxisIndex": 1, "yAxisIndex": 1},
        ],
    }


def predict_option(hist: pd.DataFrame, pred: list[dict]) -> dict:
    """预测图：历史收盘（实线）+ LSTM 未来 30 天（红色虚线）。"""
    hist_dates = hist["date"].tolist()[-90:] if not hist.empty else []
    hist_close = hist["close"].tolist()[-90:] if not hist.empty else []
    pred_dates = [p["date"] for p in pred]
    pred_prices = [round(float(p["price"]), 2) for p in pred]
    # 首个预测点接到最后历史点，曲线连续
    if hist_dates:
        pred_dates = [hist_dates[-1]] + pred_dates
        pred_prices = [hist_close[-1]] + pred_prices
    return {
        "backgroundColor": "transparent",
        "animation": False,
        "tooltip": _tooltip(),
        "legend": {"data": ["历史收盘", "LSTM 预测"], "textStyle": {"color": AXIS_LABEL}, "top": 0},
        "grid": {"left": 60, "right": 20, "top": 32, "bottom": 40},
        "xAxis": {"type": "category", "data": hist_dates + pred_dates, **_base_axis({"boundaryGap": False})},
        "yAxis": {"type": "value", "scale": True, **_base_axis()},
        "series": [
            {"name": "历史收盘", "type": "line", "data": hist_close, "showSymbol": False,
             "lineStyle": {"width": 1.4, "color": TEXT}, "color": TEXT},
            {"name": "LSTM 预测", "type": "line", "data": [None] * len(hist_close) + pred_prices,
             "showSymbol": False, "connectNulls": False,
             "lineStyle": {"width": 1.6, "color": "#E64545", "type": "dashed"}, "color": "#E64545"},
        ],
    }


def index_metrics() -> None:
    """三大指数横排（上证/深证成指/创业板指），5 秒自刷新。"""
    cols = st.columns(3)
    specs = [("sh", "000001", "上证指数"), ("sz", "399001", "深证成指"), ("sz", "399006", "创业板指")]
    for col, (mkt, code, name) in zip(cols, specs):
        with col:
            q = api_get_quote_cached(mkt, code)
            if not q:
                st.caption(f"{name} 暂无数据")
                continue
            chg = float(q.get("change") or 0)
            pct = float(q.get("changePercent") or 0)
            st.metric(
                name,
                _f(q.get("price")),
                delta=f"{fmt_signed(chg)}  {fmt_signed(pct, '{:+.2f}%')}",
                delta_color="inverse",  # 涨红跌绿（反色：正=红）
            )


def api_get_quote_cached(market: str, code: str) -> dict | None:
    """绕过 api.py 依赖的轻量引用（避免循环导入）。"""
    from api import get_quote

    return get_quote(market, code)
