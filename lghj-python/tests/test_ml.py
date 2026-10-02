"""契约自测：test_ml.py — 预测服务（8001，裸 JSON）+ 跨服务分时链路（8080 → 8001）。

前端 stock.js：getRealtimeMinute → 8001 /minute/{symbol}（裸数组 4 字段）；
getPrediction → 8001 /predict/{symbol}（{symbol, predictions×30}）。
跨服务：8080 /api/user/realtime/minute?market=&code= 内部调 8001 取分时。
"""

from __future__ import annotations

import httpx

from conftest import MAIN, PRED, assert_result_ok


# ====================== 预测服务直连（8001） ======================

def test_minute_bare_array_four_fields(client: httpx.Client):
    """/minute/sh600519：HTTP 200 裸数组，元素恰为 time/price/volume/avg_price 四字段。"""
    r = client.get(f"{PRED}/minute/sh600519")
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list), f"分时应为裸数组: {type(data)}"
    assert data, "分时数组不应为空"
    first = data[0]
    assert set(first.keys()) == {"time", "price", "volume", "avg_price"}, \
        f"分时元素应恰为 4 字段 time/price/volume/avg_price: {first}"
    # time 为 HHMM 字符串，price/avg_price 数值
    assert str(first["time"]).isdigit() and len(str(first["time"])) == 4
    assert float(first["price"]) >= 0
    assert isinstance(first["volume"], int) or float(first["volume"]) >= 0


def test_predict_30_items(client: httpx.Client):
    """/predict/sh600519：裸对象 {symbol, predictions×30}，元素 {date, price}。"""
    r = client.get(f"{PRED}/predict/sh600519")
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, dict) and data.get("symbol") == "sh600519"
    preds = data["predictions"]
    assert isinstance(preds, list) and len(preds) == 30, f"predictions 应为 30 项: {len(preds)}"
    for p in preds[:3]:
        assert "date" in p and "price" in p, f"预测项缺 date/price: {p}"
        assert float(p["price"]) > 0
    # 日期升序
    dates = [p["date"] for p in preds]
    assert dates == sorted(dates), "预测日期应升序"


def test_predict_bare_code_accepted(client: httpx.Client):
    """裸 6 位代码兼容（自动推断市场）。"""
    r = client.get(f"{PRED}/predict/600519")
    assert r.status_code == 200
    assert r.json()["symbol"] == "sh600519"


def test_invalid_symbol_400(client: httpx.Client):
    """非法 symbol：400 {"error":"invalid_symbol","msg":...}。"""
    r = client.get(f"{PRED}/minute/abc")
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "invalid_symbol"
    assert isinstance(body.get("msg"), str)


# ====================== 跨服务：8080 分时取自 8001 ======================

def test_8080_minute_data_from_8001(client: httpx.Client):
    """8080 /api/user/realtime/minute（放行）内部调 8001：返回分时数组（Result 包装）。"""
    r = client.get(f"{MAIN}/api/user/realtime/minute", params={"market": "sh", "code": "600519"})
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    data = body["data"]
    assert isinstance(data, list) and data, "8080 分时数据不应为空（应来自 8001）"
    first = data[0]
    assert {"time", "price", "volume", "avg_price"} <= set(first.keys()), \
        f"8080 透传的 8001 分时字段不符: {first}"

    # 与 8001 直连结果同构（8080 可能有 Redis 缓存，条数不强制相等）
    direct = client.get(f"{PRED}/minute/sh600519").json()
    assert isinstance(direct, list) and direct, "8001 直连分时不应为空"
    assert set(data[0].keys()) == set(direct[0].keys()), "8080 与 8001 分时字段结构应一致"


def test_8080_minute_index_symbol(client: httpx.Client):
    """指数分时（sh000001 上证指数，Dashboard 默认标的）经 8080 → 8001 链路可用。"""
    r = client.get(f"{MAIN}/api/user/realtime/minute", params={"market": "sh", "code": "000001"})
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    assert isinstance(body["data"], list) and body["data"], "指数分时数据不应为空"
