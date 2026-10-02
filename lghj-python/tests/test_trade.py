"""契约自测：trade.js（模拟交易全链路）+ 账户 totalAsset 字段 + 管理端交易分页数据源。

链路：建户 → 买入（买价≥现价，≤4 秒撮合）→ 持仓/委托/成交查询 → 卖出 → 撤单 → 资金对账。
下单/撤单均走 query string 传参（前端 placeOrder/cancelOrder 即 params）。
"""

from __future__ import annotations

import time

import httpx
import pytest

from conftest import MAIN, assert_result_ok

QUOTE_PARAMS = {"market": "sh", "code": "600519"}


def _get_quote(client: httpx.Client) -> dict:
    r = client.get(f"{MAIN}/api/user/realtime/quote", params=QUOTE_PARAMS)
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    quote = body["data"]
    assert quote and float(quote["price"]) > 0, "现价获取失败，交易链路无法验证"
    return quote


@pytest.fixture(scope="module")
def trader(client: httpx.Client, make_user) -> dict:
    """交易链路专用用户：建户 + 取现价。"""
    user = make_user("trader")
    quote = _get_quote(client)
    return {**user, "quote": quote}


def _place(client: httpx.Client, user: dict, direction: int, price: float, quantity: int) -> dict:
    r = client.post(f"{MAIN}/api/user/trade/order",
                    params={"symbol": "600519", "direction": direction,
                            "price": price, "quantity": quantity},
                    headers=user["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def _wait_order_status(client: httpx.Client, user: dict, order_id: int,
                       status: int, max_wait: float = 10.0) -> tuple[bool, float, dict]:
    """轮询委托单状态直至目标状态；返回 (是否达成, 耗时秒, 订单数据)。"""
    start = time.monotonic()
    last = {}
    while time.monotonic() - start < max_wait:
        r = client.get(f"{MAIN}/api/user/trade/query_orders", headers=user["headers"])
        orders = r.json()["data"] or []
        last = next((o for o in orders if o["id"] == order_id), {})
        if last.get("status") == status:
            return True, time.monotonic() - start, last
        time.sleep(0.5)
    return False, time.monotonic() - start, last


# ====================== 建户与账户查询 ======================

def test_01_create_account(client: httpx.Client, trader: dict):
    """建户：初始 20 万，totalCash/availableCash/frozenCash/totalAsset 全字段。"""
    r = client.post(f"{MAIN}/api/user/account/create", headers=trader["headers"])
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    account = body["data"]
    assert account is not None
    for field in ("userId", "totalCash", "availableCash", "frozenCash", "totalAsset"):
        assert field in account, f"账户缺字段 {field}: {account}"
    assert account["userId"] == trader["id"]
    assert float(account["totalCash"]) == 200000.00
    assert float(account["availableCash"]) == 200000.00
    assert float(account["frozenCash"]) == 0.00
    assert float(account["totalAsset"]) == 200000.00


def test_02_query_info_total_asset_field(client: httpx.Client, trader: dict):
    """query_info：Simulation.vue 直接渲染 account.totalAsset/availableCash/frozenCash（驼峰）。"""
    r = client.get(f"{MAIN}/api/user/account/query_info", headers=trader["headers"])
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    account = body["data"]
    assert "totalAsset" in account, "前端硬性依赖 totalAsset 字段"
    assert "availableCash" in account and "frozenCash" in account
    assert float(account["totalAsset"]) == 200000.00


def test_03_query_info_no_account_error(client: httpx.Client, make_user):
    """无账户 query_info：code=500 msg=账户不存在（前端视为未开户）。"""
    user = make_user("noacc")
    r = client.get(f"{MAIN}/api/user/account/query_info", headers=user["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 500
    assert "账户不存在" in body["msg"]


# ====================== 买入全链路 ======================

def test_04_buy_immediate_deal(client: httpx.Client, trader: dict):
    """买价 ≥ 现价 → 立即成交（状态 3），≤4 秒量级完成，产生成交记录与持仓。"""
    quote = trader["quote"]
    price = round(float(quote["price"]) * 1.05, 2)  # 高于现价 → 立即成交
    body = _place(client, trader, direction=1, price=price, quantity=1)  # 1手=100股
    assert_result_ok(body)
    order = body["data"]
    assert order["id"] and order["orderNo"]
    # trade_order.quantity 单位为手（原 Java LOT_SIZE=100，下单 1 手原样回显）
    assert order["direction"] == 1 and order["quantity"] == 1
    trader["buy_order_id"] = order["id"]
    trader["buy_price"] = price

    filled, elapsed, last = _wait_order_status(client, trader, order["id"], status=3, max_wait=12.0)
    assert filled, f"买单价 {price} ≥ 现价应立即成交，实际状态 {last.get('status')}"
    assert elapsed <= 10.0, f"成交耗时 {elapsed:.1f}s，超出 4 秒撮合预期过多"
    # 原 Java execute(order, currentPrice, order.getQuantity())：tradedQuantity 与
    # quantity 同单位（手）；持仓/资金结算时才 ×100 转股（LOT_SIZE=100）
    assert int(last["tradedQuantity"]) == 1

    # 成交记录：dealNo/orderId/dealDirection/price/quantity（quantity 单位为手，同原 Java）
    r = client.get(f"{MAIN}/api/user/trade/query_deals", headers=trader["headers"])
    deals = r.json()["data"] or []
    deal = next((d for d in deals if d["orderId"] == order["id"]), None)
    assert deal is not None, "买入应产生成交记录"
    for field in ("dealNo", "orderId", "dealDirection", "price", "quantity"):
        assert field in deal, f"成交记录缺字段 {field}: {deal}"
    assert deal["dealDirection"] == 1 and int(deal["quantity"]) == 1
    assert float(deal["price"]) <= price, "应按现价（≤委托价）成交"


def test_05_position_after_buy(client: httpx.Client, trader: dict):
    """买入后：持仓 100 股 + costPrice/profitLoss 字段 + 资金减少。"""
    r = client.get(f"{MAIN}/api/user/account/query_position",
                   params={"symbol": "600519"}, headers=trader["headers"])
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    pos = body["data"]
    assert pos is not None, "买入后应有持仓"
    assert int(pos["totalQuantity"]) == 100
    assert int(pos["availableQuantity"]) == 100
    for field in ("costPrice", "profitLoss", "frozenQuantity"):
        assert field in pos, f"持仓缺字段 {field}: {pos}"
    assert float(pos["costPrice"]) > 0

    # 持仓列表
    r = client.get(f"{MAIN}/api/user/account/query_positions", headers=trader["headers"])
    positions = r.json()["data"] or []
    assert any(p["symbol"] == "600519" for p in positions), "持仓列表应含 600519"

    # 资金：可用减少、冻结归零
    account = client.get(f"{MAIN}/api/user/account/query_info", headers=trader["headers"]).json()["data"]
    assert float(account["availableCash"]) < 200000.00
    assert float(account["frozenCash"]) == 0.00, "成交后冻结资金应解冻归零"


# ====================== 卖出全链路 ======================

def test_06_sell_after_buy(client: httpx.Client, trader: dict):
    """卖价 ≤ 现价 → 立即成交；持仓清空（逻辑删除）；资金回款增加。"""
    quote = trader["quote"]
    price = round(float(quote["price"]) * 0.95, 2)  # 低于现价 → 立即成交
    before = client.get(f"{MAIN}/api/user/account/query_info", headers=trader["headers"]).json()["data"]
    body = _place(client, trader, direction=2, price=price, quantity=1)
    assert_result_ok(body)
    order = body["data"]
    trader["sell_order_id"] = order["id"]

    filled, elapsed, last = _wait_order_status(client, trader, order["id"], status=3, max_wait=12.0)
    assert filled, f"卖单价 {price} ≤ 现价应立即成交，实际状态 {last.get('status')}"

    # 持仓清空
    r = client.get(f"{MAIN}/api/user/account/query_position",
                   params={"symbol": "600519"}, headers=trader["headers"])
    body = r.json()
    assert body["code"] == 500 and "持仓不存在" in body["msg"], f"清仓后持仓应不存在: {body}"

    # 资金对账：回款后可用资金应增加
    after = client.get(f"{MAIN}/api/user/account/query_info", headers=trader["headers"]).json()["data"]
    assert float(after["availableCash"]) > float(before["availableCash"]), \
        f"卖出回款后可用资金应增加: {before['availableCash']} → {after['availableCash']}"
    assert float(after["frozenCash"]) == 0.00


# ====================== 撤单 ======================

def test_07_cancel_unfilled_order(client: httpx.Client, trader: dict):
    """低价买单（远低于现价）不会成交 → 撤单成功：状态 4 + 冻结资金解冻。"""
    quote = trader["quote"]
    price = round(float(quote["price"]) * 0.5, 2)  # 远低于现价，挂在订单簿
    before = client.get(f"{MAIN}/api/user/account/query_info", headers=trader["headers"]).json()["data"]
    body = _place(client, trader, direction=1, price=price, quantity=1)
    assert_result_ok(body)
    order = body["data"]
    order_id = order["id"]
    trader["cancel_order_id"] = order_id

    # 等待一个调度周期确认未成交（状态 1）
    time.sleep(4)
    r = client.get(f"{MAIN}/api/user/trade/query_orders", headers=trader["headers"])
    last = next((o for o in (r.json()["data"] or []) if o["id"] == order_id), {})
    assert last.get("status") in (1, 2), f"低价单不应成交: {last}"

    # 撤单（query 参数 orderId）
    r = client.post(f"{MAIN}/api/user/trade/cancel", params={"orderId": order_id},
                    headers=trader["headers"])
    assert r.status_code == 200
    assert_result_ok(r.json())

    # 状态 4 已撤销 + cancelTime
    r = client.get(f"{MAIN}/api/user/trade/query_orders", headers=trader["headers"])
    last = next((o for o in (r.json()["data"] or []) if o["id"] == order_id), {})
    assert last.get("status") == 4, f"撤单后状态应为 4: {last}"
    assert last.get("cancelTime"), "撤单后应记录 cancelTime"

    # 冻结资金解冻
    after = client.get(f"{MAIN}/api/user/account/query_info", headers=trader["headers"]).json()["data"]
    assert float(after["frozenCash"]) == 0.00
    assert float(after["availableCash"]) == float(before["availableCash"]), \
        "撤单后可用资金应恢复至下单前"


def test_08_cancel_nonexistent_order(client: httpx.Client, trader: dict):
    """撤销不存在的订单：code=500 msg=撤销失败（原契约文案）。"""
    r = client.post(f"{MAIN}/api/user/trade/cancel", params={"orderId": 999999999},
                    headers=trader["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 500
    assert "撤销失败" in body["msg"]


def test_09_cancel_other_users_order(client: httpx.Client, trader: dict, make_user):
    """撤销他人订单：code=500 msg=撤销失败（归属校验）。"""
    other = make_user("other")
    r = client.post(f"{MAIN}/api/user/trade/cancel",
                    params={"orderId": trader["buy_order_id"]}, headers=other["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 500 and "撤销失败" in body["msg"]


# ====================== 异常与对账 ======================

def test_10_insufficient_funds(client: httpx.Client, trader: dict):
    """资金不足下单：code=50001（账户可用资金不足），可用资金不变。"""
    quote = trader["quote"]
    price = round(float(quote["price"]), 2)
    before = client.get(f"{MAIN}/api/user/account/query_info", headers=trader["headers"]).json()["data"]
    body = _place(client, trader, direction=1, price=price, quantity=1000)  # 1000手=10万股
    assert body["code"] == 50001, f"应返回 50001 资金不足: {body}"
    assert "资金不足" in body["msg"]
    after = client.get(f"{MAIN}/api/user/account/query_info", headers=trader["headers"]).json()["data"]
    assert float(after["availableCash"]) == float(before["availableCash"])


def test_11_total_asset_reconciliation(client: httpx.Client, trader: dict):
    """资金对账：一轮买卖后总资产 ≈ 初始 20 万（按现价全额成交、无手续费）。"""
    account = client.get(f"{MAIN}/api/user/account/query_info", headers=trader["headers"]).json()["data"]
    total = float(account["totalAsset"])
    assert abs(total - 200000.00) < 2000.00, f"一买一卖后总资产应≈20万，实际 {total}"


def test_12_query_orders_deals_field_contract(client: httpx.Client, trader: dict):
    """委托/成交列表字段契约（Simulation.vue 与 TradeManage.vue 的消费基础）。"""
    r = client.get(f"{MAIN}/api/user/trade/query_orders", headers=trader["headers"])
    orders = r.json()["data"] or []
    assert orders, "交易链路应产生委托单"
    for field in ("id", "orderNo", "userId", "symbol", "direction", "price",
                  "quantity", "tradedQuantity", "status", "createTime"):
        assert field in orders[0], f"委托单缺字段 {field}: {orders[0]}"
    assert orders[0]["userId"] == trader["id"]

    r = client.get(f"{MAIN}/api/user/trade/query_deals", headers=trader["headers"])
    deals = r.json()["data"] or []
    assert deals, "交易链路应产生成交记录"
    for field in ("id", "dealNo", "orderId", "userId", "symbol", "dealDirection",
                  "price", "quantity", "createTime"):
        assert field in deals[0], f"成交记录缺字段 {field}: {deals[0]}"
