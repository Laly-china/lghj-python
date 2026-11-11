# -*- coding: utf-8 -*-
"""
data/fund_flow.py —— A 股个股资金流向采集模块（资金流向 Agent 的数据源，立项扩展）

数据源选型（先探测过的可用性结论，见 data/stock_rank.py 同款口径）：
- 主源：新浪历史资金流 MoneyFlow.ssl_qsfx_lscjfb（多日、特大/大/中/小单分级净额，
  本机与常规机房网络均可达）；
- 回退：东财 akshare stock_individual_fund_flow（东财 push2 系在部分网络被代理拦截，
  仅作回退，服务器部署后通常可用）；
- 两源统一归一化为同一字段口径；当日数据按日期覆盖判断缓存新鲜度，
  在线失败时降级读最近缓存（照 collector.get_daily_data 模式）。

归一化字段（每行一个交易日，金额单位：元）：
    date / close / changePct / turnover / mainNetInflow / mainNetPct /
    superNetInflow / bigNetInflow / midNetInflow / smallNetInflow
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import httpx
import pandas as pd

from data.collector import (
    BASE_DIR,
    CollectorError,
    InvalidSymbolError,
    now_bj,
    parse_symbol,
)

logger = logging.getLogger("prediction-server.fund_flow")

CACHE_DIR = BASE_DIR / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

#: 新浪接口一次最多取 60 日（留余量），对上层 days 截断
_SINA_NUM = 30
#: 统一输出列
_COLUMNS = [
    "date", "close", "changePct", "turnover",
    "mainNetInflow", "mainNetPct",
    "superNetInflow", "bigNetInflow", "midNetInflow", "smallNetInflow",
]

_SINA_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "MoneyFlow.ssl_qsfx_lscjfb"
)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://finance.sina.com.cn",
}


def _cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"fundflow_{symbol}.csv"


def _f(v: Any) -> Optional[float]:
    """安全转 float（None/NaN 保持 None）。"""
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def _cache_is_fresh(symbol: str) -> bool:
    """缓存含「最新交易日」即视为新鲜（收盘后当日行出现；盘中当日行实时更新）。"""
    path = _cache_path(symbol)
    if not path.exists():
        return False
    try:
        df = pd.read_csv(path, dtype={"date": str})
    except Exception:  # noqa: BLE001 缓存损坏视为失效
        return False
    if df.empty or "date" not in df.columns:
        return False
    today = now_bj().strftime("%Y-%m-%d")
    return str(df.iloc[0]["date"]) == today


def _load_cache(symbol: str) -> list[dict]:
    df = pd.read_csv(_cache_path(symbol), dtype={"date": str})
    return df[_COLUMNS].to_dict(orient="records")


def _save_cache(symbol: str, items: list[dict]) -> None:
    try:
        pd.DataFrame(items, columns=_COLUMNS).to_csv(
            _cache_path(symbol), index=False, encoding="utf-8"
        )
    except Exception:  # noqa: BLE001 缓存写失败不影响返回
        logger.warning("资金流缓存写入失败 symbol=%s", symbol, exc_info=True)


# ------------------------------------------------------------------
# 主源：新浪历史资金流
# ------------------------------------------------------------------

def _fetch_sina(full_symbol: str) -> list[dict]:
    resp = httpx.get(
        _SINA_URL,
        params={
            "page": 1,
            "num": _SINA_NUM,
            "sort": "opendate",
            "asc": 0,
            "daima": full_symbol,
        },
        headers=_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    resp.encoding = "gbk"
    rows = json.loads(resp.text or "[]")
    if not isinstance(rows, list) or not rows:
        raise CollectorError(f"新浪资金流无数据: {full_symbol}")
    items: list[dict] = []
    for r in rows:
        change_ratio = _f(r.get("changeratio"))
        turnover_bp = _f(r.get("turnover"))
        main_ratio = _f(r.get("ratioamount"))
        items.append(
            {
                "date": str(r.get("opendate", "")),
                "close": _f(r.get("trade")),
                # 新浪口径换算为百分比：changeratio 为小数，turnover 为万分比
                "changePct": round(change_ratio * 100, 4) if change_ratio is not None else None,
                "turnover": round(turnover_bp / 100, 4) if turnover_bp is not None else None,
                # netamount=主力净流入(元)，ratioamount=主力净流入占比(小数)
                "mainNetInflow": _f(r.get("netamount")),
                "mainNetPct": round(main_ratio * 100, 4) if main_ratio is not None else None,
                "superNetInflow": _f(r.get("r0_net")),
                "bigNetInflow": _f(r.get("r1_net")),
                "midNetInflow": _f(r.get("r2_net")),
                "smallNetInflow": _f(r.get("r3_net")),
            }
        )
    return items


# ------------------------------------------------------------------
# 回退源：东财 akshare（部分网络被拦截；服务器机房通常可用）
# ------------------------------------------------------------------

_EM_COL_MAP = {
    "日期": "date",
    "收盘价": "close",
    "涨跌幅": "changePct",
    "换手率": "turnover",
    "主力净流入-净额": "mainNetInflow",
    "主力净流入-净占比": "mainNetPct",
    "超大单净流入-净额": "superNetInflow",
    "超大单净流入-净占比": None,
    "大单净流入-净额": "bigNetInflow",
    "大单净流入-净占比": None,
    "中单净流入-净额": "midNetInflow",
    "中单净流入-净占比": None,
    "小单净流入-净额": "smallNetInflow",
    "小单净流入-净占比": None,
}


def _fetch_eastmoney(full_symbol: str) -> list[dict]:
    import akshare as ak

    market = "sh" if full_symbol.startswith("sh") else ("bj" if full_symbol.startswith("bj") else "sz")
    df = ak.stock_individual_fund_flow(stock=full_symbol[2:], market=market)
    if df is None or df.empty:
        raise CollectorError(f"东财资金流无数据: {full_symbol}")
    df = df.rename(columns={k: v for k, v in _EM_COL_MAP.items() if v})
    df["date"] = df["date"].astype(str)
    items: list[dict] = []
    for _, row in df.iterrows():
        item = {c: _f(row.get(c)) for c in _COLUMNS}
        item["date"] = str(row.get("date", ""))
        items.append(item)
    # 东财为正序，统一倒序（最新在前）对齐新浪
    return items[::-1]


# ------------------------------------------------------------------
# 对外入口
# ------------------------------------------------------------------

def get_fund_flow(symbol: str, days: int = 5) -> dict:
    """查询个股近 N 日资金流向（含当日盘中实时）。

    返回 {"symbol": "sh600519", "items": [最新在前, ...]}（最多 days 行）；
    symbol 非法抛 InvalidSymbolError；两源皆失败且无缓存抛 CollectorError。
    """
    info = parse_symbol(symbol)
    full_symbol = info["symbol"]

    days = max(1, min(int(days), 20))

    # 1. 新鲜缓存直接用
    if _cache_is_fresh(full_symbol):
        items = _load_cache(full_symbol)[:days]
        return {"symbol": full_symbol, "items": items}

    # 2. 主源（新浪）→ 回退（东财）
    items: Optional[list[dict]] = None
    try:
        items = _fetch_sina(full_symbol)
    except Exception as e:  # noqa: BLE001 主源失败转回退
        logger.warning("新浪资金流失败 symbol=%s: %s", full_symbol, e)
    if items is None:
        try:
            items = _fetch_eastmoney(full_symbol)
        except Exception as e:  # noqa: BLE001 回退也失败走缓存降级
            logger.warning("东财资金流回退失败 symbol=%s: %s", full_symbol, e)

    # 3. 降级：读最近缓存
    if items is None:
        if _cache_path(full_symbol).exists():
            logger.warning("资金流两源皆失败，降级读缓存 symbol=%s", full_symbol)
            items = _load_cache(full_symbol)
        else:
            raise CollectorError(f"资金流数据不可用（新浪/东财均失败且无缓存）: {full_symbol}")

    _save_cache(full_symbol, items)
    return {"symbol": full_symbol, "items": items[:days]}
