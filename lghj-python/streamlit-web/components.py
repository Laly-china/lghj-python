# -*- coding: utf-8 -*-
"""components.py —— 共享 UI 组件（同花顺风格）

- 颜色体系：中国证券惯例「涨红跌绿」，深色终端底
- 图表：Apache ECharts（st.echarts_chart 原生渲染），K线/分时/预测三类 option 构造
- 表格：pandas Styler 仅用于着色（格式化交给 column_config）
"""

from __future__ import annotations

import html as html_lib
import json

import pandas as pd
import streamlit as st

# 涨红跌绿（浅色主题：白底上取加深变体保证对比度）
UP = "#E64545"        # 涨（同花顺红）
DOWN = "#00A67D"      # 跌
FLAT = "#6B7280"      # 平
AVG_LINE = "#D48806"  # 分时均价线（THS 黄·加深）
TEXT = "#1F2328"
GRID = "#E2E5E9"
AXIS_LABEL = "#6B7280"


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
        "axisLine": {"lineStyle": {"color": "#D0D4D9"}},
        "axisLabel": {"color": AXIS_LABEL, "fontSize": 11},
        "splitLine": {"lineStyle": {"color": "#ECEDEF"}},
    }
    if extra:
        axis.update(extra)
    return axis


def _tooltip() -> dict:
    return {
        "trigger": "axis",
        "axisPointer": {"type": "cross", "label": {"backgroundColor": "#EEF0F2"}},
        "backgroundColor": "#FFFFFF",
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
            {"name": "MA5", "type": "line", "data": ma5, "showSymbol": False, "lineStyle": {"width": 1, "color": "#D48806"}},
            {"name": "MA10", "type": "line", "data": ma10, "showSymbol": False, "lineStyle": {"width": 1, "color": "#2563EB"}},
            {"name": "MA20", "type": "line", "data": ma20, "showSymbol": False, "lineStyle": {"width": 1, "color": "#7C3AED"}},
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


# ====================== Agent 管家团队可视化（管家命名 + 运行状态推导） ======================

# agent 英文名 -> (卡片名, 图标, 一句话职能)；
# 命名参考腾讯 Marvis「职能+管家」四字风格，职能与装配 yml 的专家分工一一对应
AGENT_CARDS: dict[str, tuple[str, str, str]] = {
    "InvestmentAdvisorSupervisor": ("队长", "👑", "拆解问题、分派专家、汇总结论"),
    "MarketAnalysisAgent": ("行情管家", "🌐", "宏观·行业·基本面与消息面"),
    "QuantTechnicalAgent": ("技术管家", "📈", "量价趋势·支撑阻力·波动分析"),
    "PersonalTradeProfileAgent": ("持仓管家", "💼", "我的持仓与交易画像"),
    "RiskAssessmentAgent": ("风控管家", "🛡️", "风险识别与仓位风控边界"),
    "PortfolioAdviceAgent": ("组合管家", "🧩", "配置建议·仓位纪律·观察清单"),
    "ComplianceDisclosureAgent": ("合规管家", "⚖️", "合规审查与免责声明"),
}


def agent_card_name(agent_name: str) -> str:
    """agent 英文名 -> 管家卡片名（未登记的 agent 原样返回）。"""
    return AGENT_CARDS.get(agent_name, (agent_name, "🤖", ""))[0]


def agent_card(agent_id: str) -> tuple[str, str, str]:
    """agentId 或英文名 -> (卡片名, 图标, 职能)；investment-advisor 映射为「队长」。"""
    if agent_id == "investment-advisor":
        agent_id = "InvestmentAdvisorSupervisor"
    return AGENT_CARDS.get(agent_id, (agent_id, "🤖", ""))


# ====================== Agent 思考芯片流（ZCode 式：实时流出 / 回放共用） ======================

def render_thinking_chips(events: list[dict]) -> None:
    """把轨迹事件渲染为纵向决策芯片：🧠决策 / 🔧工具(可展开看入参结果) / ➡️转交 / 📤输出。

    run_start 不渲染；生成中与完成后的回放使用同一渲染，保证视觉一致。
    """
    for e in events:
        etype = e.get("type")
        if etype == "run_start":
            continue
        dur = f" · {e.get('durationMs')}ms" if e.get("durationMs") is not None else ""
        who = agent_card(str(e.get("agent") or ""))[0]
        if etype == "llm_call":
            st.markdown(
                f"<span style='color:#2563EB;font-size:12px'>🧠 {html_lib.escape(who)} 决策{dur} · "
                f"{html_lib.escape(str(e.get('result') or ''))}</span>",
                unsafe_allow_html=True,
            )
        elif etype == "transfer":
            target = agent_card(str(e.get("name") or ""))[0]
            st.markdown(
                f"<span style='color:#D97706;font-size:12px'>➡️ 转交 {html_lib.escape(target)}</span>",
                unsafe_allow_html=True,
            )
        elif etype == "tool":
            args_text = json.dumps(e.get("args") or {}, ensure_ascii=False)
            result_text = str(e.get("result") or "")
            with st.expander(f"🔧 {html_lib.escape(str(e.get('name') or ''))} · {html_lib.escape(who)}{dur}", expanded=False):
                st.markdown(
                    f"<div style='color:#57606A;font-size:11px;line-height:1.7'>入参　"
                    f"<code style='color:#6B7280;word-break:break-all'>{html_lib.escape(args_text)}</code><br>"
                    f"结果　{html_lib.escape(result_text[:300])}</div>",
                    unsafe_allow_html=True,
                )
        elif etype == "agent_text":
            st.markdown(
                f"<span style='color:#00A67D;font-size:12px'>📤 {html_lib.escape(who)} 输出结论</span>",
                unsafe_allow_html=True,
            )


def agent_thinking_stream(events: list[dict], live: bool = False) -> None:
    """思考过程折叠块：live=生成中（默认展开 + 尾部进行中提示），否则收起态回放。"""
    steps = [e for e in events if e.get("type") != "run_start"]
    if live:
        with st.expander(f"深度思考中… · 已 {len(steps)} 步", expanded=True):
            render_thinking_chips(events)
            st.markdown(
                "<span style='color:#D97706;font-size:12px'>● 思考继续中…</span>",
                unsafe_allow_html=True,
            )
    else:
        with st.expander(f"已深度思考 · {len(steps)} 步", expanded=False):
            render_thinking_chips(events)


def slice_current_run(events: list[dict]) -> list[dict]:
    """切出最后一个 run_start 之后的轨迹片段（即最近一次提问的执行过程）。"""
    last = -1
    for i, e in enumerate(events):
        if e.get("type") == "run_start":
            last = i
    return events[last:] if last >= 0 else list(events)


def agent_team_status(events: list[dict], running: bool) -> dict[str, str]:
    """由轨迹片段推导各 agent 状态。

    有事件的 agent = done；对话仍在进行时，最后一条事件的 agent = running（正在打点者）。
    """
    status: dict[str, str] = {}
    for e in events:
        if e.get("type") != "run_start" and e.get("agent"):
            status[e["agent"]] = "done"
    if running and events:
        last_agent = events[-1].get("agent")
        if last_agent:
            status[last_agent] = "running"
    return status
