# -*- coding: utf-8 -*-
"""
data/stock_rank.py —— A 股个股排行模块（每日 / 每周精选用）

数据源选型（与 lghj-server 保持一致的可用性口径）：
- 优先 akshare stock_zh_a_spot（新浪，全市场约 5500 只，一次请求，
  字段：代码/名称/最新价/涨跌额/涨跌幅/昨收/今开/最高/最低/成交量/成交额）；
- 东财 push2 系列（stock_zh_a_spot_em）在部分网络下被代理拦截，故不作首选；
- 腾讯批量接口（qt.gtimg.cn，lghj-server 同款）作为回退，支持一次多只，适合补齐少量个股。

排序口径：
- 每日榜：当日涨跌幅（涨跌幅字段）
- 每周榜：近 5 个交易日累计涨幅（用日 K 由"昨收→最新价"扩展；数据缺失时退化为当日涨幅）

输出统一为 Python 原生类型；涨红跌绿的着色交由前端处理。
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import pandas as pd

from data.collector import CollectorError, BASE_DIR, now_bj, _safe_round

logger = logging.getLogger("prediction-server.stock_rank")

CACHE_DIR = BASE_DIR / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_SPOT_MEMO_TTL = 120          # 全市场实时快照进程内记忆（2 分钟）
_WEEK_CACHE_TTL = 3600        # 周涨幅缓存（1 小时）


def _spot_cache_path() -> Path:
    return CACHE_DIR / "stock_spot.csv"


def _to_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 全市场快照
# ---------------------------------------------------------------------------
_spot_memo: dict = {}


def get_spot(*, force: bool = False) -> pd.DataFrame:
    """获取 A 股全市场实时快照（含涨跌幅）。

    缓存：进程内 2 分钟；落盘按小时降级。
    """
    now = time.monotonic()
    memo = _spot_memo.get("^")
    if not force and memo and now - memo[0] < _SPOT_MEMO_TTL:
        return memo[1]

    path = _spot_cache_path()
    cached = None
    if path.exists():
        try:
            cached = pd.read_csv(path, dtype={"代码": str})
        except Exception:  # noqa: BLE001
            cached = None

    try:
        import akshare as ak
        df = ak.stock_zh_a_spot()
        if df is None or len(df) == 0:
            raise CollectorError("A股实时快照为空")
        try:
            df.to_csv(path, index=False)
        except Exception:  # noqa: BLE001
            pass
        _spot_memo["^"] = (now, df)
        logger.info("A股快照采集成功：%d 只", len(df))
        return df
    except Exception as e:  # noqa: BLE001
        logger.warning("A股快照采集失败: %s", e)
        if cached is not None and len(cached):
            _spot_memo["^"] = (now, cached)
            return cached
        raise CollectorError(f"A股快照采集失败且无缓存: {e}") from e


def _norm_code(raw: str) -> dict:
    """'sh600519' -> {"symbol","market","code"}；裸 6 位自动推断市场。"""
    s = str(raw).strip().lower()
    if len(s) >= 8 and s[:2] in ("sh", "sz", "bj"):
        return {"symbol": s, "market": s[:2], "code": s[2:]}
    code = s
    if code.startswith(("60", "68", "90")):
        m = "sh"
    elif code.startswith(("00", "30", "20")):
        m = "sz"
    elif code.startswith(("8", "4", "92")):
        m = "bj"
    else:
        m = "sh"
    return {"symbol": m + code, "market": m, "code": code}


def _row_to_stock(r, *, period: str) -> dict:
    raw_code = str(r.get("代码", ""))
    meta = _norm_code(raw_code)
    price = _to_float(r.get("最新价"))
    return {
        "symbol": meta["symbol"],
        "code": meta["code"],
        "name": str(r.get("名称", "")),
        "price": round(price, 2) if price is not None else None,
        "change": _safe_round(r.get("涨跌额"), 2),
        "changePct": _safe_round(r.get("涨跌幅"), 2),
        "prevClose": _safe_round(r.get("昨收"), 2),
        "open": _safe_round(r.get("今开"), 2),
        "high": _safe_round(r.get("最高"), 2),
        "low": _safe_round(r.get("最低"), 2),
        "volume": _safe_round(r.get("成交量"), 0),
        "amount": _safe_round(r.get("成交额"), 0),
        "period": period,
    }


# ---------------------------------------------------------------------------
# 每日 / 每周榜
# ---------------------------------------------------------------------------
def daily_rank_stocks(n: int = 10, *, exclude_st: bool = True,
                      min_amount: float = 0.0) -> dict:
    """每日个股榜：按当日涨跌幅排序。

    exclude_st: 过滤 ST/*ST/退市股（名称含 ST/退）
    min_amount: 最小成交额（元）门槛，过滤僵尸股
    """
    df = get_spot()
    work = df.copy()
    work["涨跌幅"] = pd.to_numeric(work["涨跌幅"], errors="coerce")
    work = work.dropna(subset=["涨跌幅"])
    if exclude_st:
        work = work[~work["名称"].astype(str).str.contains("ST|退", na=False)]
    if min_amount > 0:
        amt = pd.to_numeric(work.get("成交额"), errors="coerce")
        work = work[amt.fillna(0) >= min_amount]
    work = work.sort_values("涨跌幅", ascending=False).head(int(n))
    items = [_row_to_stock(r, period="day") for _, r in work.iterrows()]
    return {
        "period": "day",
        "period_label": "当日涨跌幅",
        "count": len(items),
        "updated_at": now_bj().strftime("%Y-%m-%d %H:%M:%S"),
        "items": items,
    }


def weekly_rank_stocks(n: int = 10, *, top_pool: int = 120) -> dict:
    """每周个股榜：近 5 个交易日累计涨幅。

    实现：先取当日涨幅池（top_pool 只）缩小候选，再对候选用日 K 计算近 5 日累计涨幅。
    日 K 源按 新浪 -> 腾讯 顺序尝试；若全部不可用，则降级为"按当日涨幅近似"，
    并在返回体的 degraded / note 字段中明确标注（绝不静默返回空列表）。
    """
    pool = daily_rank_stocks(top_pool, exclude_st=True)
    cands = pool["items"]
    if not cands:
        return {"period": "week", "period_label": "近5日涨幅", "count": 0,
                "updated_at": now_bj().strftime("%Y-%m-%d %H:%M:%S"),
                "items": [], "degraded": True, "note": "当日行情源不可用，无法构造候选池"}

    symbols = [c["symbol"] for c in cands]
    week_pct, source = _batch_week_change(symbols)

    degraded = False
    note = ""
    if not week_pct:
        # 全部日 K 源不可用 -> 降级：用当日涨幅近似周涨幅，保证榜单可用
        degraded = True
        note = "日K数据源不可用，已降级为按当日涨幅近似（区间收益不精确）"
        for c in cands:
            c["weekPct"] = c.get("changePct")
        source = "degraded_day_change"

    for c in cands:
        if c.get("weekPct") is None:
            c["weekPct"] = week_pct.get(c["symbol"])
    cands = [c for c in cands if c.get("weekPct") is not None]
    for c in cands:
        c["weekPct"] = round(float(c["weekPct"]), 2)
    cands.sort(key=lambda x: x["weekPct"], reverse=True)
    items = cands[:int(n)]
    for c in items:
        c["period"] = "week"
    return {
        "period": "week",
        "period_label": "近5日涨幅",
        "count": len(items),
        "updated_at": now_bj().strftime("%Y-%m-%d %H:%M:%S"),
        "items": items,
        "dataSource": source,
        "degraded": degraded,
        "note": note,
    }


# ---------------------------------------------------------------------------
# 日 K 获取：新浪（主）-> 腾讯（备）
# ---------------------------------------------------------------------------
def _fetch_sina_daily(sym: str, datalen: int = 12) -> list:
    """新浪日K（quotes.sina.cn，直连可用），返回 [close, ...]（升序）。"""
    import urllib.request
    import json as _json
    url = ("https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
           f"?symbol={sym}&scale=240&ma=no&datalen={datalen}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=6).read().decode("utf-8", "ignore")
    rows = _json.loads(raw)
    closes = []
    for r in rows if isinstance(rows, list) else []:
        try:
            closes.append(float(r.get("close")))
        except (TypeError, ValueError):
            continue
    return closes


def _fetch_tencent_daily_single(sym: str, datalen: int = 12) -> list:
    """腾讯日K（备源），返回 [close, ...]（升序）。"""
    import urllib.request
    import json as _json
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={sym},day,,,{datalen},qfq")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=6).read().decode("utf-8", "ignore")
    data = _json.loads(raw)
    node = data.get("data", {}).get(sym, {})
    klines = node.get("qfqday") or node.get("day") or []
    return [float(k[2]) for k in klines if len(k) > 2]


_week_memo: dict = {}


def _batch_week_change(symbols: list) -> tuple[dict, str]:
    """近 5 日累计涨幅：返回 ({symbol: pct}, 数据源标识)。

    先整体用新浪，失败者再用腾讯补；两源均失败则该 symbol 缺失（由调用方降级处理）。
    """
    now = time.monotonic()
    memo = _week_memo.get("^")
    if memo and now - memo[0] < _WEEK_CACHE_TTL and memo[1].get("__symbols__") == symbols:
        return ({k: v for k, v in memo[1].items() if k != "__symbols__"},
                memo[1].get("__source__", "sina"))

    closes_map: dict[str, list] = {}
    sina_hit = 0
    for sym in symbols:
        try:
            closes = _fetch_sina_daily(sym)
            if len(closes) >= 2:
                closes_map[sym] = closes
                sina_hit += 1
        except Exception:  # noqa: BLE001
            continue

    # 新浪未命中的用腾讯补
    tencent_hit = 0
    for sym in symbols:
        if sym in closes_map:
            continue
        try:
            closes = _fetch_tencent_daily_single(sym)
            if len(closes) >= 2:
                closes_map[sym] = closes
                tencent_hit += 1
        except Exception:  # noqa: BLE001
            continue

    res = {}
    for sym, closes in closes_map.items():
        if len(closes) >= 6:
            base, last = closes[-6], closes[-1]
        else:
            base, last = closes[0], closes[-1]
        if base > 0:
            res[sym] = (last / base - 1) * 100

    source = "sina" if sina_hit >= tencent_hit else "tencent"
    if sina_hit and tencent_hit:
        source = f"sina({sina_hit})+tencent({tencent_hit})"
    res["__symbols__"] = symbols
    res["__source__"] = source
    _week_memo["^"] = (now, res)
    return ({k: v for k, v in res.items() if not k.startswith("__")}, source)
