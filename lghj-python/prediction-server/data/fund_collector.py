# -*- coding: utf-8 -*-
"""
data/fund_collector.py —— 基金数据采集与本地缓存模块（akshare）

职责（供 /fund/* 接口使用）：
1. 基金排行：开放式基金按收益率排行（日/周/月/季/半年/年/今年来/成立来），
   数据源 fund_open_fund_rank_em（东财），一次返回全市场约 2 万只基金，
   自带"单位净值/累计净值/日增长率/近1周/近1月/近3月/近6月/近1年/近3年/
   今年来/成立来/手续费"等字段，恰好覆盖"收益等详细信息"需求。
2. 基金名录：fund_name_em（东财），用于按代码/名称/拼音模糊搜索。
3. 单只基金历史净值：fund_open_fund_info_em（单位净值走势 / 累计净值走势 / 同类排名走势）。
4. 本地缓存：排行与名录落盘 data/cache/*.csv，按"数据日期"标记，
   同一交易会话内复用；网络失败时降级读最近缓存。
5. 每日/每周精选：不新增数据源，直接对排行结果按"日增长率"/"近1周"排序取 TopN，
   并补充年化、最大回撤近似等派生指标。

本模块只返回 Python 原生类型（dict/list/float/int/str），不向上层泄漏 pandas/numpy 类型。
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import pandas as pd

from data.collector import (
    CollectorError,
    BASE_DIR,
    now_bj,
    _safe_round,
)

logger = logging.getLogger("prediction-server.fund")

CACHE_DIR = BASE_DIR / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 排行数据进程内记忆：同一数据日期内 10 分钟不重复采集（全市场排行较重）
_RANK_MEMO_TTL = 600
# 名录进程内记忆 TTL
_NAME_MEMO_TTL = 3600

# akshare 排行接口的"收益率区间"取值（对应前端可切换的周期）
RANK_PERIODS = {
    "day": "日增长率",
    "week": "近1周",
    "month": "近1月",
    "quarter": "近3月",
    "half_year": "近6月",
    "year": "近1年",
    "year3": "近3年",
    "ytd": "今年来",
    "all": "成立来",
}

# 排行里的原始列名（东财口径，保持中文，便于留痕与前端展示对齐）
_COL_CODE = "基金代码"
_COL_NAME = "基金简称"
_COL_DATE = "日期"
_COL_NAV = "单位净值"
_COL_NAV_ACC = "累计净值"
_COL_DAY = "日增长率"
_COL_WEEK = "近1周"
_COL_MONTH = "近1月"
_COL_Q = "近3月"
_COL_HY = "近6月"
_COL_Y = "近1年"
_COL_Y3 = "近3年"
_COL_YTD = "今年来"
_COL_ALL = "成立来"
_COL_FEE = "手续费"


# ---------------------------------------------------------------------------
# 缓存工具
# ---------------------------------------------------------------------------
def _rank_cache_path() -> Path:
    return CACHE_DIR / "fund_rank.csv"


def _name_cache_path() -> Path:
    return CACHE_DIR / "fund_name.csv"


def _nav_cache_path(code: str) -> Path:
    return CACHE_DIR / f"fund_nav_{code}.csv"


def _file_age_seconds(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    return time.time() - path.stat().st_mtime


def _read_csv(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, dtype={_COL_CODE: str})
        return df if len(df) else None
    except Exception as e:  # noqa: BLE001
        logger.warning("读取基金缓存失败 %s: %s", path.name, e)
        return None


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    try:
        df.to_csv(path, index=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("写入基金缓存失败 %s: %s", path.name, e)


# ---------------------------------------------------------------------------
# 字段归一化
# ---------------------------------------------------------------------------
def _to_pct(v) -> Optional[float]:
    """把东财的涨跌幅数值（已是百分数，如 1.13 表示 1.13%）转 float，NaN -> None。"""
    try:
        f = float(v)
        if pd.isna(f):
            return None
        return round(f, 4)
    except (TypeError, ValueError):
        return None


def _fee_to_float(v) -> Optional[float]:
    """'0.15%' -> 0.15。"""
    if v is None:
        return None
    s = str(v).strip().replace("%", "")
    if not s or s.lower() == "nan":
        return None
    try:
        return round(float(s), 4)
    except ValueError:
        return None


def _norm_rank_df(df: pd.DataFrame) -> pd.DataFrame:
    """统一排行的列名与类型，落盘用。"""
    cols = {c: c for c in df.columns}
    keep = [c for c in [ _COL_CODE, _COL_NAME, _COL_DATE, _COL_NAV, _COL_NAV_ACC,
                         _COL_DAY, _COL_WEEK, _COL_MONTH, _COL_Q, _COL_HY,
                         _COL_Y, _COL_Y3, _COL_YTD, _COL_ALL, _COL_FEE]
            if c in cols]
    out = df[keep].copy()
    out[_COL_CODE] = out[_COL_CODE].astype(str).str.zfill(6)
    return out


# 单周期收益率合理上限（%）。超过此值几乎必然是分红/拆分/数据源脏值导致的净值跳变，
# 而非真实区间收益，排行时予以剔除（例如"近1周 221%"的脏数据）。
_PCT_SANITY_LIMIT = 100.0


def _clean_pct_series(s: pd.Series, col: str) -> pd.Series:
    """把周期收益列转为数值，并把超出合理范围的脏值置为 NaN。"""
    v = pd.to_numeric(s, errors="coerce")
    if col != _COL_DAY:  # 日增长率也可能超 10%（涨跌停外），但 100% 以上同样剔除
        v = v.where(v.abs() <= _PCT_SANITY_LIMIT)
    else:
        v = v.where(v.abs() <= 20.0)
    return v


def _row_to_fund(r, *, period: str = "day") -> dict:
    """把排行的一行转成前端友好的 dict。"""
    return {
        "code": str(r.get(_COL_CODE, "")).zfill(6),
        "name": str(r.get(_COL_NAME, "")),
        "date": str(r.get(_COL_DATE, "")),
        "nav": _safe_round(r.get(_COL_NAV), 4),
        "navAcc": _safe_round(r.get(_COL_NAV_ACC), 4),
        "dayPct": _to_pct(r.get(_COL_DAY)),
        "weekPct": _to_pct(r.get(_COL_WEEK)),
        "monthPct": _to_pct(r.get(_COL_MONTH)),
        "quarterPct": _to_pct(r.get(_COL_Q)),
        "halfYearPct": _to_pct(r.get(_COL_HY)),
        "yearPct": _to_pct(r.get(_COL_Y)),
        "year3Pct": _to_pct(r.get(_COL_Y3)),
        "ytdPct": _to_pct(r.get(_COL_YTD)),
        "allPct": _to_pct(r.get(_COL_ALL)),
        "feePct": _fee_to_float(r.get(_COL_FEE)),
        "period": period,
    }


# ---------------------------------------------------------------------------
# 排行采集
# ---------------------------------------------------------------------------
_rank_memo: dict = {}   # {"^": (ts, df)}


def get_fund_rank(
    *,
    force: bool = False,
    min_count: int = 500,
) -> pd.DataFrame:
    """获取全市场开放式基金排行（DataFrame）。

    缓存策略：
      - 进程内记忆（10 分钟）；
      - 落盘缓存（按数据日期，当日数据视为新鲜）；
      - 在线采集失败 → 降级读旧缓存；无缓存 → CollectorError。
    """
    now = time.monotonic()
    memo = _rank_memo.get("^")
    if not force and memo and now - memo[0] < _RANK_MEMO_TTL:
        return memo[1]

    path = _rank_cache_path()
    cached = _read_csv(path)
    data_date = now_bj().strftime("%Y-%m-%d")
    if not force and cached is not None and _file_age_seconds(path) is not None:
        # 当日缓存且行数充足 → 直接复用
        age_h = (_file_age_seconds(path) or 0) / 3600
        if len(cached) >= min_count and age_h < 12:
            _rank_memo["^"] = (now, cached)
            return cached

    try:
        import akshare as ak
        df = ak.fund_open_fund_rank_em(symbol="全部")
        if df is None or len(df) == 0:
            raise CollectorError("基金排行数据为空")
        df = _norm_rank_df(df)
        _write_csv(df, path)
        _rank_memo["^"] = (now, df)
        logger.info("基金排行在线采集成功：%d 只（数据日期 %s）", len(df), data_date)
        return df
    except CollectorError as e:
        logger.warning("基金排行采集失败: %s", e)
        if cached is not None:
            _rank_memo["^"] = (now, cached)
            return cached
        raise CollectorError(f"基金排行采集失败且无本地缓存: {e}") from e
    except Exception as e:  # noqa: BLE001
        logger.warning("基金排行在线采集异常: %s", e)
        if cached is not None:
            _rank_memo["^"] = (now, cached)
            return cached
        raise CollectorError(f"基金排行采集异常且无本地缓存: {e}") from e


def rank_top(n: int = 20, *, period: str = "day", fund_type: Optional[str] = None) -> dict:
    """按指定周期收益率取 TopN。

    period 取值见 RANK_PERIODS；fund_type 为可选名称/类型过滤（对"基金简称"做包含匹配）。
    """
    col = RANK_PERIODS.get(period, _COL_DAY)
    df = get_fund_rank()
    if col not in df.columns:
        col = _COL_DAY
    work = df.copy()
    work[col] = _clean_pct_series(work[col], col)
    work = work.dropna(subset=[col])
    if fund_type:
        work = work[work[_COL_NAME].astype(str).str.contains(fund_type, na=False)]
    work = work.sort_values(col, ascending=False).head(int(n))
    items = [_row_to_fund(r, period=period) for _, r in work.iterrows()]
    return {
        "period": period,
        "period_label": col,
        "count": len(items),
        "updated_at": now_bj().strftime("%Y-%m-%d %H:%M:%S"),
        "items": items,
    }


def market_overview() -> dict:
    """全市场基金概览（数量、上涨/下跌家数、平均日涨幅）——供主页/基金页头部展示。"""
    df = get_fund_rank()
    day = _clean_pct_series(df.get(_COL_DAY), _COL_DAY)
    week = _clean_pct_series(df.get(_COL_WEEK), _COL_WEEK)
    total = int(len(df))
    up = int((day > 0).sum())
    down = int((day < 0).sum())
    flat = total - up - down
    return {
        "total": total,
        "up": up,
        "down": down,
        "flat": flat,
        "avgDayPct": _safe_round(day.mean(), 3),
        "avgWeekPct": _safe_round(week.mean(), 3),
        "updated_at": now_bj().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# 名录 / 搜索
# ---------------------------------------------------------------------------
_name_memo: dict = {}


def get_fund_names(*, force: bool = False) -> pd.DataFrame:
    """基金名录（代码/简称/类型/拼音），用于搜索。"""
    now = time.monotonic()
    memo = _name_memo.get("^")
    if not force and memo and now - memo[0] < _NAME_MEMO_TTL:
        return memo[1]

    path = _name_cache_path()
    cached = _read_csv(path)
    if not force and cached is not None and len(cached) >= 1000:
        _name_memo["^"] = (now, cached)
        return cached

    try:
        import akshare as ak
        df = ak.fund_name_em()
        df = df.rename(columns={
            "基金代码": _COL_CODE,
            "基金简称": _COL_NAME,
            "基金类型": "基金类型",
            "拼音缩写": "拼音缩写",
            "拼音全称": "拼音全称",
        })
        df[_COL_CODE] = df[_COL_CODE].astype(str).str.zfill(6)
        _write_csv(df, path)
        _name_memo["^"] = (now, df)
        logger.info("基金名录在线采集成功：%d 条", len(df))
        return df
    except Exception as e:  # noqa: BLE001
        logger.warning("基金名录采集失败: %s", e)
        if cached is not None:
            _name_memo["^"] = (now, cached)
            return cached
        raise CollectorError(f"基金名录采集失败且无本地缓存: {e}") from e


def search_funds(keyword: str, limit: int = 30) -> list:
    """按代码 / 名称 / 拼音模糊搜索基金。"""
    kw = (keyword or "").strip()
    if not kw:
        return []
    df = get_fund_names()
    kw_u = kw.upper()
    mask = (
        df[_COL_CODE].astype(str).str.contains(kw, na=False)
        | df[_COL_NAME].astype(str).str.contains(kw, na=False)
        | df.get("拼音缩写", pd.Series(dtype=str)).astype(str).str.upper().str.contains(kw_u, na=False)
        | df.get("拼音全称", pd.Series(dtype=str)).astype(str).str.upper().str.contains(kw_u, na=False)
    )
    hit = df[mask].head(int(limit))
    return [
        {
            "code": str(r.get(_COL_CODE, "")).zfill(6),
            "name": str(r.get(_COL_NAME, "")),
            "type": str(r.get("基金类型", "")),
        }
        for _, r in hit.iterrows()
    ]


# ---------------------------------------------------------------------------
# 单只基金历史净值
# ---------------------------------------------------------------------------
def get_fund_nav(code: str, *, force: bool = False) -> dict:
    """单只基金历史净值走势（单位净值）。

    返回 {"code","name","data":[{"date","nav","dayPct"}...]}（按日期升序）。
    """
    code = (code or "").strip()
    if not code.isdigit() or len(code) != 6:
        raise CollectorError(f"基金代码非法: {code}")

    path = _nav_cache_path(code)
    cached = _read_csv(path)
    expected = now_bj().strftime("%Y-%m-%d")
    if not force and cached is not None and len(cached):
        try:
            last = str(cached["净值日期"].max())
            if last >= expected:
                return _nav_result(code, cached)
        except Exception:  # noqa: BLE001
            pass

    try:
        import akshare as ak
        df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
        if df is None or len(df) == 0:
            raise CollectorError(f"基金 {code} 净值为空")
        _write_csv(df, path)
        return _nav_result(code, df)
    except CollectorError as e:
        if cached is not None and len(cached):
            return _nav_result(code, cached)
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning("基金净值采集失败 %s: %s", code, e)
        if cached is not None and len(cached):
            return _nav_result(code, cached)
        raise CollectorError(f"基金净值采集失败且无本地缓存: {e}") from e


def _nav_result(code: str, df: pd.DataFrame) -> dict:
    data = []
    for _, r in df.iterrows():
        nav = _safe_round(r.get("单位净值"), 4)
        if nav is None:
            continue
        data.append({
            "date": str(r.get("净值日期", "")),
            "nav": nav,
            "dayPct": _to_pct(r.get("日增长率")),
        })
    # 从排行结果补名称（若有）
    name = ""
    try:
        rank = get_fund_rank()
        hit = rank[rank[_COL_CODE] == code]
        if len(hit):
            name = str(hit.iloc[0][_COL_NAME])
    except Exception:  # noqa: BLE001
        pass
    return {"code": code, "name": name, "count": len(data), "data": data}


# ---------------------------------------------------------------------------
# 每日 / 每周精选（主页用）
# ---------------------------------------------------------------------------
def _derive_metrics(items: list) -> list:
    """为精选条目补充派生指标：风险调整（年化/波动）、标签。

    纯本地计算，不额外请求网络。
    """
    for it in items:
        y = it.get("yearPct")
        d = it.get("dayPct")
        # 简易"性价比"评分：近1年收益 / 名义波动(用多周期收益离散度近似)
        vals = [v for v in [it.get("monthPct"), it.get("quarterPct"),
                            it.get("halfYearPct"), it.get("yearPct")] if v is not None]
        vol = 0.0
        if len(vals) >= 2:
            mean = sum(vals) / len(vals)
            vol = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
        score = (y / vol) if (y is not None and vol > 0.01) else (y or 0.0)
        it["score"] = round(score, 2)
        it["volatility"] = round(vol, 2)
        # 标签
        tags = []
        if d is not None and d >= 3:
            tags.append("日涨超3%")
        if (it.get("weekPct") or 0) >= 5:
            tags.append("周涨超5%")
        if (y or 0) >= 50:
            tags.append("年化50%+")
        if (it.get("feePct") or 0) == 0:
            tags.append("零手续费")
        it["tags"] = tags
    return items


def daily_picks(n: int = 10) -> dict:
    """每日精选：按当日（日增长率）排序的基金 TopN。"""
    res = rank_top(n=n, period="day")
    res["items"] = _derive_metrics(res["items"])
    res["title"] = "每日精选"
    res["rank_by"] = "日增长率"
    return res


def weekly_picks(n: int = 10) -> dict:
    """每周精选：按近 1 周收益排序的基金 TopN。"""
    res = rank_top(n=n, period="week")
    res["items"] = _derive_metrics(res["items"])
    res["title"] = "每周精选"
    res["rank_by"] = "近1周"
    return res
