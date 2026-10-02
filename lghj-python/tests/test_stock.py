"""契约自测：stock.js（搜索/行情/K线/新闻/自选股）。

对应前端 lghj_web/src/api/stock.js 的消费点（Simulation/Watchlist/Dashboard/Market 视图）。
"""

from __future__ import annotations

import httpx

from conftest import MAIN, assert_result_ok


# ====================== 股票搜索 ======================

def test_search_by_symbol_prefix(client: httpx.Client):
    """代码前缀搜索 600519 → 命中贵州茅台，StockDoc 字段齐全。"""
    r = client.get(f"{MAIN}/api/user/stock/search", params={"keyword": "600519"})
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    items = body["data"]
    assert isinstance(items, list) and items, "600519 应命中至少一只股票"
    hit = next((i for i in items if i["symbol"] == "600519"), None)
    assert hit is not None, "600519 前缀应命中 600519"
    for field in ("id", "symbol", "name", "industry", "marketType"):
        assert field in hit, f"StockDoc 缺字段 {field}: {hit}"
    assert hit["name"] == "贵州茅台"
    assert hit["marketType"] in ("1", "2", 1, 2)


def test_search_by_name_fuzzy(client: httpx.Client):
    """名称/行业模糊搜索 银行 → 命中银行类股票。"""
    r = client.get(f"{MAIN}/api/user/stock/search", params={"keyword": "银行"})
    assert r.status_code == 200
    items = r.json()["data"]
    assert isinstance(items, list) and len(items) > 1, "银行 模糊搜索应命中多只"
    matched = [i for i in items if "银行" in (i.get("name") or "") or "银行" in (i.get("industry") or "")]
    assert matched, "命中的股票名称或行业应包含 银行"


# ====================== 实时行情 ======================

def test_realtime_quote(client: httpx.Client):
    """实时行情（腾讯 ~ 分割，字段 1/2/3/4/5/6/31/32）。"""
    r = client.get(f"{MAIN}/api/user/realtime/quote", params={"market": "sh", "code": "600519"})
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    quote = body["data"]
    assert quote is not None, "行情不应为空（外网腾讯接口可用）"
    for field in ("code", "name", "price", "prevClose", "open", "volume", "change", "changePercent"):
        assert field in quote, f"行情缺字段 {field}: {quote}"
    assert quote["code"] == "600519"
    assert float(quote["price"]) > 0, "收盘后腾讯仍返回最近价格，price 应 > 0"


# ====================== K线三周期 ======================

def test_kline_day_week_month(client: httpx.Client):
    """K线三周期 D/W/M：[{date,open,close,high,low,volume}]，Dashboard 按此画图。"""
    for period in ("D", "W", "M"):
        r = client.get(f"{MAIN}/api/user/stock/data", params={"symbol": "600519", "period": period})
        assert r.status_code == 200, f"period={period} HTTP 失败"
        body = r.json()
        assert_result_ok(body)
        data = body["data"]
        assert isinstance(data, list) and len(data) > 10, f"period={period} K线数据过少"
        item = data[-1]
        for field in ("date", "open", "close", "high", "low"):
            assert field in item, f"period={period} K线缺字段 {field}: {item}"
        assert float(item["close"]) > 0
        # D 周期日期为 yyyy-MM-dd
        if period == "D":
            assert len(str(item["date"]).split("-")) == 3


# ====================== 新闻 ======================

def test_realtime_news(client: httpx.Client):
    """新闻：StockNewsVO 字段 + recentN 生效。"""
    r = client.get(f"{MAIN}/api/user/realtime/news", params={"symbol": "600519", "recentN": 3})
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    news = body["data"]
    assert isinstance(news, list), "新闻应为数组"
    assert len(news) <= 3, f"recentN=3 应截断，实际 {len(news)}"
    if news:
        for field in ("keyword", "title", "content", "publishTime", "source", "url"):
            assert field in news[0], f"新闻条目缺字段 {field}: {news[0]}"


# ====================== 自选股（增/查/删，query string 传参） ======================

def test_watchlist_add_list_remove(client: httpx.Client, user_a: dict, suffix: str):
    """自选股全流程：add（query 传 symbol）→ list（StockFollowVO 字段）→ remove。"""
    headers = user_a["headers"]
    # 添加（query string 传参，前端 addWatchlist 即 params）
    r = client.post(f"{MAIN}/api/user/optional/add", params={"symbol": "600519"}, headers=headers)
    assert r.status_code == 200
    assert_result_ok(r.json())

    # 列表：字段名契约 {stockId,symbol,name,price,changePercent,volume}
    # （前端 Watchlist.vue 还消费 followTime，但原 Java VO 无该字段，前端固有差异，忠实保留）
    r = client.get(f"{MAIN}/api/user/optional/list", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    items = body["data"]
    assert isinstance(items, list)
    hit = next((i for i in items if i.get("symbol") == "600519"), None)
    assert hit is not None, "600519 应出现在自选股列表"
    for field in ("stockId", "symbol", "name", "price", "changePercent", "volume"):
        assert field in hit, f"StockFollowVO 缺字段 {field}: {hit}"
    assert float(hit["price"]) > 0

    # 删除（query string 传参）
    r = client.post(f"{MAIN}/api/user/optional/remove", params={"symbol": "600519"}, headers=headers)
    assert r.status_code == 200
    assert_result_ok(r.json())

    # 列表不再包含
    r = client.get(f"{MAIN}/api/user/optional/list", headers=headers)
    items = r.json()["data"] or []
    assert all(i.get("symbol") != "600519" for i in items), "删除后自选股不应再包含 600519"


def test_watchlist_requires_token(client: httpx.Client):
    """自选股接口不在放行清单：无 token → 401。"""
    r = client.get(f"{MAIN}/api/user/optional/list")
    assert r.status_code == 401
