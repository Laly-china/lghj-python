# -*- coding: utf-8 -*-
"""模拟交易页 —— 账户总览 / 买卖下单 / 持仓 / 委托 / 成交（参考同花顺交易界面）"""

import pandas as pd
import streamlit as st

import api
import components as ui

st.header("模拟交易", icon=":material/swap_horiz:")

ui.require_login()

# ---------------- 账户 ----------------

account = api.account_info()
if account is None:
    st.warning("还没有模拟账户（初始资金 20 万）")
    if st.button("立即开户", type="primary", icon=":material/account_balance_wallet:"):
        ok, msg = api.account_create()
        (st.toast if ok else st.error)(msg, icon=":material/check_circle:" if ok else None)
        st.rerun()
    st.stop()


@st.fragment(run_every="5s")
def account_metrics() -> None:
    acc = api.account_info()
    if not acc:
        return
    a, b, c, d = st.columns(4)
    a.metric("总资产", f"{float(acc.get('totalAsset') or 0):,.2f}")
    b.metric("可用资金", f"{float(acc.get('availableCash') or 0):,.2f}")
    c.metric("冻结资金", f"{float(acc.get('frozenCash') or 0):,.2f}")
    d.metric("持仓市值", f"{_position_value():,.2f}")


def _position_value() -> float:
    total = 0.0
    for p in api.positions():
        market = "sh" if str(p.get("symbol", "")).startswith("6") else "sz"
        q = api.get_quote(market, p.get("symbol", ""))
        if q:
            total += float(q.get("price") or 0) * float(p.get("totalQuantity") or 0)
    return total


left, right = st.columns([1, 1.6], gap="large")

# ---------------- 左：下单 ----------------

with left:
    st.subheader("买卖委托", divider=True)
    with st.form("order_form", border=True):
        symbol = st.text_input(
            "股票代码", value=st.session_state.get("current_symbol", ""), placeholder="600519（6 位裸代码）",
            key="order_symbol",
        )
        direction = st.segmented_control(
            "方向", ["买入", "卖出"], default="买入", key="order_direction",
            selection_mode="single",
        )
        price = st.number_input("委托价格（元）", min_value=0.01, step=0.01, format="%.2f", key="order_price")
        quantity = st.number_input(
            "数量（手，1 手 = 100 股）", min_value=1, step=1, format="%d", key="order_qty"
        )
        est = price * quantity * 100
        st.caption(f"预估金额：{est:,.2f} 元")
        submit = st.form_submit_button(
            "提交委托", type="primary", use_container_width=True, icon=":material/send:",
        )
    if submit:
        if not symbol.strip():
            st.error("请输入股票代码")
        else:
            ok, msg = api.place_order(
                symbol.strip(), 1 if direction == "买入" else 2, float(price), int(quantity)
            )
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    st.subheader("撤单", divider=True)
    pending = [o for o in api.query_orders() if o.get("status") in (1, 2)]
    if not pending:
        st.caption("暂无待成交委托（买价 ≥ 现价或卖价 ≤ 现价即时成交）")
    else:
        options = {
            f"{o.get('symbol')} {'买' if o.get('direction') == 1 else '卖'} "
            f"{o.get('price')}×{o.get('quantity')}手 [{o.get('orderNo', '')[-6:]}]": o.get("id")
            for o in pending
        }
        sel = st.selectbox("待撤委托", list(options.keys()), key="cancel_sel", label_visibility="collapsed")
        if st.button("撤销选中委托", icon=":material/cancel:", use_container_width=True):
            ok, msg = api.cancel_order(options[sel])
            (st.toast if ok else st.error)(msg, icon=":material/check_circle:" if ok else None)
            st.rerun()

# ---------------- 右：持仓 / 委托 / 成交 ----------------

STATUS = {1: "待成交", 2: "部分成交", 3: "已完成", 4: "已撤销"}

with right:
    tab_pos, tab_ord, tab_deal = st.tabs(["持仓", "委托", "成交"], on_change="rerun")

    if tab_pos.open:
        pos = api.positions()
        if not pos:
            st.caption("暂无持仓")
        else:
            rows = []
            for p in pos:
                sym = str(p.get("symbol", ""))
                market = "sh" if sym.startswith("6") else "sz"
                q = api.get_quote(market, sym)
                price = float(q.get("price") or 0) if q else None
                qty = float(p.get("totalQuantity") or 0)
                cost = float(p.get("costPrice") or 0)
                mval = price * qty if price else None
                profit = (price - cost) * qty if price else None
                rows.append(
                    {
                        "symbol": sym,
                        "name": (q or {}).get("name", ""),
                        "quantity": qty,
                        "available": p.get("availableQuantity"),
                        "costPrice": cost,
                        "price": price,
                        "marketValue": mval,
                        "profitLoss": profit,
                    }
                )
            df = pd.DataFrame(rows)
            styled = ui.colorize_cells(
                df.style.format(
                    {
                        "quantity": "{:.0f}", "available": "{:.0f}", "costPrice": "{:.2f}",
                        "price": "{:.2f}", "marketValue": "{:,.2f}", "profitLoss": "{:+,.2f}",
                    },
                    na_rep="-",
                ),
                ["price", "profitLoss"],
            )
            st.dataframe(
                styled, hide_index=True, width="stretch", key="trade_pos_rows",
                on_select="rerun", selection_mode="single-row",
                column_config={
                    "symbol": st.column_config.TextColumn("代码", width="small"),
                    "name": st.column_config.TextColumn("名称"),
                    "quantity": st.column_config.NumberColumn("持仓(股)"),
                    "available": st.column_config.NumberColumn("可卖(股)"),
                    "costPrice": st.column_config.NumberColumn("成本", format="%.2f"),
                    "price": st.column_config.NumberColumn("现价", format="%.2f"),
                    "marketValue": st.column_config.NumberColumn("市值"),
                    "profitLoss": st.column_config.NumberColumn("浮动盈亏"),
                },
            )
            sel_rows = st.session_state.get("trade_pos_rows", {}).get("selection", {}).get("rows", []) if isinstance(st.session_state.get("trade_pos_rows"), dict) else []
            if sel_rows:
                sym = df.iloc[sel_rows[0]]["symbol"]
                st.session_state.current_symbol = ("sh" if sym.startswith("6") else "sz") + sym
                st.page_link("app_pages/个股-stock.py", label=f"查看 {sym} 行情 →", icon=":material/candlestick_chart:")

    if tab_ord.open:
        orders = api.query_orders()
        if not orders:
            st.caption("暂无委托记录")
        else:
            df = pd.DataFrame(
                [
                    {
                        "createTime": o.get("createTime"),
                        "symbol": o.get("symbol"),
                        "direction": "买入" if o.get("direction") == 1 else "卖出",
                        "price": o.get("price"),
                        "quantity": o.get("quantity"),
                        "tradedQuantity": o.get("tradedQuantity"),
                        "status": STATUS.get(o.get("status"), str(o.get("status"))),
                    }
                    for o in reversed(orders)
                ]
            )
            styled = df.style.map(
                lambda v: f"color: {ui.UP if v == '买入' else ui.DOWN}",
                subset=["direction"],
            )
            st.dataframe(
                styled, hide_index=True, width="stretch",
                column_config={
                    "createTime": st.column_config.TextColumn("委托时间"),
                    "symbol": st.column_config.TextColumn("代码", width="small"),
                    "direction": st.column_config.TextColumn("方向"),
                    "price": st.column_config.NumberColumn("价格", format="%.2f"),
                    "quantity": st.column_config.NumberColumn("数量(手)"),
                    "tradedQuantity": st.column_config.NumberColumn("已成交(手)"),
                    "status": st.column_config.TextColumn("状态"),
                },
            )

    if tab_deal.open:
        deals = api.query_deals()
        if not deals:
            st.caption("暂无成交记录")
        else:
            df = pd.DataFrame(
                [
                    {
                        "createTime": d.get("createTime"),
                        "symbol": d.get("symbol"),
                        "dealDirection": "买入" if d.get("dealDirection") == 1 else "卖出",
                        "price": d.get("price"),
                        "quantity": d.get("quantity"),
                        "dealNo": d.get("dealNo"),
                    }
                    for d in reversed(deals)
                ]
            )
            styled = df.style.map(
                lambda v: f"color: {ui.UP if v == '买入' else ui.DOWN}",
                subset=["dealDirection"],
            )
            st.dataframe(
                styled, hide_index=True, width="stretch",
                column_config={
                    "createTime": st.column_config.TextColumn("成交时间"),
                    "symbol": st.column_config.TextColumn("代码", width="small"),
                    "dealDirection": st.column_config.TextColumn("方向"),
                    "price": st.column_config.NumberColumn("成交价", format="%.2f"),
                    "quantity": st.column_config.NumberColumn("数量(手)"),
                    "dealNo": st.column_config.TextColumn("成交编号"),
                },
            )
