# -*- coding: utf-8 -*-
"""
data/collector.py —— akshare 行情数据采集与本地缓存模块

职责：
1. symbol 解析：兼容前端/主服务的"交易所前缀 + 6位代码"格式
   （sh600519 / sz000001 / bj870357，大小写均可），也兼容裸 6 位代码（自动推断市场）；
   内部转换为 akshare 需要的纯数字代码。识别股票与指数（sh000xxx / sz399xxx 为指数）。
2. 分时数据：GET /minute/{symbol} 使用的当日 1 分钟分时（时间、价格、成交量、均价）。
   akshare 主接口 stock_zh_a_hist_min_em（东财），失败时回退 stock_zh_a_minute（新浪）；
   指数使用 index_zh_a_hist_min_em。
3. 日线数据：/predict 与模型训练使用的近 2~3 年日 K。
   股票主接口 stock_zh_a_hist（前复权），回退 stock_zh_a_daily（新浪）；
   指数使用 index_zh_a_hist。
4. 本地缓存：所有采集结果落盘 data/cache/*.csv，按"数据日期"命名/标记，
   当日（同一交易会话）首次采集后复用；网络失败时自动降级读取最近缓存。
5. 交易日历：tool_trade_date_hist_sina 获取交易日列表（缓存 30 天），
   用于推算未来 30 个交易日的预测日期；失败时退化为"跳过周末"推算。

本模块只返回 Python 原生类型（dict/list/float/int/str），不向上层泄漏 pandas/numpy 类型。
"""
from __future__ import annotations

import re
import time
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger("prediction-server.collector")

# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent      # prediction-server/
CACHE_DIR = BASE_DIR / "data" / "cache"                # 代码按路径引用的缓存目录，保留英文名
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 北京时间（东八区）
_BJ_TZ = timezone(timedelta(hours=8))

# 分时数据：同一数据日期在进程内 5 分钟内不重复发起网络采集
_MINUTE_MEMO_TTL = 300
# 交易日历缓存有效期（天）
_TRADE_CAL_TTL_DAYS = 30

_SYMBOL_FULL = re.compile(r"^(sh|sz|bj)(\d{6})$")      # 带交易所前缀
_SYMBOL_BARE = re.compile(r"^(\d{6})$")                # 裸 6 位代码


class CollectorError(Exception):
    """采集失败（网络不可用且无可用缓存）时抛出。"""


class InvalidSymbolError(CollectorError):
    """symbol 格式非法。"""


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def now_bj() -> datetime:
    """当前北京时间。"""
    return datetime.now(_BJ_TZ)


def parse_symbol(symbol: str) -> dict:
    """
    解析股票代码。

    返回 {"symbol": "sh600519", "market": "sh", "code": "600519", "kind": "stock"|"index"}
    规则：
      - sh/sz/bj + 6 位数字：直接使用前缀；
      - 裸 6 位数字：按代码段推断市场（60/68→sh，00/30→sz，399→sz 指数，43/83/87/92→bj）；
      - 指数识别：sh000xxx（如 sh000001 上证指数）、sz399xxx（如 sz399001 深证成指）。
    """
    if symbol is None:
        raise InvalidSymbolError("symbol 不能为空")
    s = str(symbol).strip().lower()
    m = _SYMBOL_FULL.match(s)
    if m:
        market, code = m.group(1), m.group(2)
    else:
        m = _SYMBOL_BARE.match(s)
        if not m:
            raise InvalidSymbolError(
                f"非法的股票代码: {symbol!r}，期望形如 sh600519 / sz000001 / bj870357 或 6 位纯数字")
        code = m.group(1)
        if code.startswith(("60", "68")):
            market = "sh"
        elif code.startswith(("399", "00", "30")):
            market = "sz"
        elif code.startswith(("43", "83", "87", "88", "92")):
            market = "bj"
        else:
            market = "sz"
    kind = "index" if (market == "sh" and code.startswith("000")) or \
                      (market == "sz" and code.startswith("399")) else "stock"
    return {"symbol": market + code, "market": market, "code": code, "kind": kind}


def _expected_latest_session(now: Optional[datetime] = None) -> str:
    """
    推断"最近一个应有行情的交易日"（YYYY-MM-DD）。
    简化处理：只按周末回退，不考虑法定节假日（节假日多打一次网络请求即可，
    采集结果的数据日期会与缓存对齐，不会产生脏数据）。
    """
    d = (now or now_bj()).date()
    # 收盘 15:00 前，"最新会话"按前一个工作日算
    if (now or now_bj()).hour < 15:
        d = d - timedelta(days=1)
    while d.weekday() >= 5:  # 5=周六 6=周日
        d = d - timedelta(days=1)
    return d.isoformat()


def _pick_col(df: pd.DataFrame, candidates: list) -> Optional[str]:
    """在 DataFrame 中按候选名顺序查找第一个存在的列名。"""
    cols = {str(c).strip(): c for c in df.columns}
    for name in candidates:
        if name in cols:
            return cols[name]
    return None


def _to_float(v) -> float:
    return float(v)


def _to_int(v) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# 分时数据
# ---------------------------------------------------------------------------
def _minute_cache_path(symbol: str, data_date: str) -> Path:
    return CACHE_DIR / f"minute_{symbol}_{data_date.replace('-', '')}.csv"


def _newest_minute_cache(symbol: str) -> Optional[tuple]:
    """返回 (data_date, DataFrame) 或 None。文件名形如 minute_sh600519_20260930.csv。"""
    files = sorted(CACHE_DIR.glob(f"minute_{symbol}_*.csv"), reverse=True)
    for f in files:
        m = re.search(r"_(\d{8})\.csv$", f.name)
        if not m:
            continue
        try:
            df = pd.read_csv(f, dtype={"time": str})
            if len(df) > 0:
                data_date = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}"
                return data_date, df
        except Exception as e:  # 缓存文件损坏则跳过
            logger.warning("读取分时缓存失败 %s: %s", f.name, e)
    return None


def _write_minute_cache(symbol: str, data_date: str, items: list) -> None:
    path = _minute_cache_path(symbol, data_date)
    try:
        pd.DataFrame(items).to_csv(path, index=False, encoding="utf-8")
    except Exception as e:
        logger.warning("写入分时缓存失败: %s", e)


def _normalize_minute_df(df: pd.DataFrame) -> tuple:
    """
    将 akshare 分时 DataFrame 归一化为 (data_date, items)。
    items: [{"time": "0930", "price": 1800.0, "volume": 10000, "avg_price": 1800.0}, ...]
    字段契约来自 Java 主服务文档（API_Documentation_Detailed.md 2.1.3）：
    time 为 HHmm 字符串，price/volume/avg_price 为数值。
    """
    tcol = _pick_col(df, ["时间", "day", "time", "date"])
    if tcol is None:
        raise CollectorError(f"分时数据缺少时间列，实际列: {list(df.columns)}")
    pcol = _pick_col(df, ["收盘", "最新价", "close", "price"])
    vcol = _pick_col(df, ["成交量", "volume"])
    acol = _pick_col(df, ["均价", "avg_price"])
    amount_col = _pick_col(df, ["成交额", "amount"])

    df = df.copy()
    ts = df[tcol].astype(str).str.strip()
    date_part = ts.str.slice(0, 10)
    hhmm = ts.str.slice(11, 16).str.replace(":", "", regex=False)
    # 兼容时间列不带日期的情况（如 "0930"/"09:30"）
    bad = hhmm.isna() | (hhmm == "")
    if bad.any():
        hhmm = ts.str.replace(":", "", regex=False).str.slice(0, 4)
        date_part = date_part.where(~bad, other=_expected_latest_session())

    df["_date"] = date_part
    df["_hhmm"] = hhmm
    df["_price"] = pd.to_numeric(df[pcol], errors="coerce") if pcol else float("nan")
    if vcol:
        df["_volume"] = pd.to_numeric(df[vcol], errors="coerce")
    else:
        df["_volume"] = 0.0

    # 均价：优先用接口自带列；否则用累计成交额/累计成交量近似（VWAP）。
    # 守卫：部分数据源（如新浪指数分时）的 amount/volume 语义是"市场平均股价"
    # 而非本标的均价，若 VWAP 与价格偏离中位数超过 50%，退化为价格累计均值。
    if acol:
        df["_avg"] = pd.to_numeric(df[acol], errors="coerce")
    else:
        if amount_col:
            amt = pd.to_numeric(df[amount_col], errors="coerce").fillna(0.0).cumsum()
            vol = df["_volume"].fillna(0.0).cumsum()
            vwap = (amt / vol.replace(0.0, float("nan"))).ffill()
            ratio = (vwap / df["_price"]).dropna()
            skewed = ratio.median() > 1.5 or ratio.median() < 0.5 if len(ratio) else True
            df["_avg"] = df["_price"].expanding().mean() if skewed else vwap
        else:
            df["_avg"] = df["_price"].expanding().mean()

    # 只保留最近一个交易会话的数据
    latest_date = df["_date"].dropna().max()
    df = df[df["_date"] == latest_date]
    df = df.dropna(subset=["_price"])

    items = []
    for _, r in df.iterrows():
        avg = r["_avg"]
        items.append({
            "time": str(r["_hhmm"]).zfill(4),
            "price": round(_to_float(r["_price"]), 3),
            "volume": _to_int(r["_volume"]),
            "avg_price": round(_to_float(avg) if pd.notna(avg) else r["_price"], 3),
        })
    return str(latest_date), items


def _fetch_minute_online(sym: dict) -> tuple:
    """在线采集分时数据，多接口依次回退。返回 (data_date, items)。"""
    code, market, kind = sym["code"], sym["market"], sym["kind"]
    errors = []

    # 1) 东财接口（股票 / 指数各有一个）
    try:
        import akshare as ak
        if kind == "index":
            df = ak.index_zh_a_hist_min_em(symbol=code, period="1")
        else:
            df = ak.stock_zh_a_hist_min_em(symbol=code, period="1", adjust="")
        if df is not None and len(df) > 0:
            return _normalize_minute_df(df)
        errors.append("stock/index_zh_a_hist_min_em 返回空")
    except Exception as e:
        errors.append(f"em 1分钟接口失败: {e}")

    # 2) 新浪 1 分钟接口（股票与指数均支持，symbol 需带前缀，如 sh000001）
    try:
        import akshare as ak
        df = ak.stock_zh_a_minute(symbol=market + code, period="1")
        if df is not None and len(df) > 0:
            return _normalize_minute_df(df)
        errors.append("stock_zh_a_minute 返回空")
    except Exception as e:
        errors.append(f"新浪 1分钟接口失败: {e}")

    raise CollectorError("；".join(errors))


# 进程内备忘：{symbol: (monotonic_ts, data_date)}，避免同一会话反复请求网络
_minute_memo: dict = {}


def get_minute_data(symbol: str) -> dict:
    """
    获取分时数据（供 /minute/{symbol} 使用）。

    缓存策略（带日期失效）：
      1. 已有缓存的数据日期 >= 最近应有一个会话日期 → 直接返回缓存，不发网络请求；
      2. 否则发起在线采集；采集到的数据日期与最新缓存相同且市场未开市 → 复用缓存；
      3. 同一 symbol 在 5 分钟内已采集过相同数据日期 → 直接复用；
      4. 在线采集失败 → 降级返回最近一次缓存（任何日期）；
      5. 无任何数据 → 抛 CollectorError。

    返回 {"symbol", "data_date", "items": [...]}，items 即裸 JSON 数组内容。
    """
    sym = parse_symbol(symbol)
    s = sym["symbol"]
    expected = _expected_latest_session()

    # 1) 缓存已覆盖最新会话 → 直接复用（"当日首次采集后复用"）
    newest = _newest_minute_cache(s)
    if newest and newest[0] >= expected:
        return {"symbol": s, "data_date": newest[0], "items": _df_to_items(newest[1])}

    # 2) 进程内备忘 TTL 内复用
    memo = _minute_memo.get(s)
    if memo and (time.monotonic() - memo[0]) < _MINUTE_MEMO_TTL:
        if newest and newest[0] == memo[1]:
            return {"symbol": s, "data_date": newest[0], "items": _df_to_items(newest[1])}

    # 3) 在线采集
    try:
        data_date, items = _fetch_minute_online(sym)
        _minute_memo[s] = (time.monotonic(), data_date)
        if not newest or data_date > newest[0]:
            _write_minute_cache(s, data_date, items)  # 新会话数据才落盘
        return {"symbol": s, "data_date": data_date, "items": items}
    except CollectorError as e:
        logger.warning("分时在线采集失败 %s: %s", s, e)
        # 4) 降级：返回最近的缓存
        if newest:
            return {"symbol": s, "data_date": newest[0], "items": _df_to_items(newest[1])}
        raise CollectorError(f"分时数据采集失败且无本地缓存: {e}") from e


def _df_to_items(df: pd.DataFrame) -> list:
    """把缓存 CSV 读出的 DataFrame 还原为分时 item 列表。"""
    items = []
    for _, r in df.iterrows():
        try:
            items.append({
                "time": str(r["time"]).strip().zfill(4),
                "price": round(float(r["price"]), 3),
                "volume": _to_int(r["volume"]),
                "avg_price": round(float(r["avg_price"]), 3),
            })
        except (KeyError, ValueError, TypeError):
            continue
    return items


# ---------------------------------------------------------------------------
# 日线数据
# ---------------------------------------------------------------------------
def _daily_cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"daily_{symbol}.csv"


def _read_daily_cache(symbol: str) -> Optional[pd.DataFrame]:
    path = _daily_cache_path(symbol)
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, dtype={"date": str})
        if len(df) == 0:
            return None
        return df
    except Exception as e:
        logger.warning("读取日线缓存失败 %s: %s", path.name, e)
        return None


def _write_daily_cache(symbol: str, df: pd.DataFrame) -> None:
    try:
        df.to_csv(_daily_cache_path(symbol), index=False, encoding="utf-8")
    except Exception as e:
        logger.warning("写入日线缓存失败: %s", e)


def _normalize_daily_df(df: pd.DataFrame) -> pd.DataFrame:
    """归一化日线 DataFrame 为列: date, open, high, low, close, volume（按日期升序）。"""
    dcol = _pick_col(df, ["日期", "date", "day"])
    ocol = _pick_col(df, ["开盘", "open"])
    ccol = _pick_col(df, ["收盘", "close"])
    hcol = _pick_col(df, ["最高", "high"])
    lcol = _pick_col(df, ["最低", "low"])
    vcol = _pick_col(df, ["成交量", "volume"])
    if dcol is None or ccol is None:
        raise CollectorError(f"日线数据缺少日期/收盘列，实际列: {list(df.columns)}")
    out = pd.DataFrame({
        "date": df[dcol].astype(str).str.slice(0, 10),
        "open": pd.to_numeric(df[ocol], errors="coerce") if ocol else float("nan"),
        "high": pd.to_numeric(df[hcol], errors="coerce") if hcol else float("nan"),
        "low": pd.to_numeric(df[lcol], errors="coerce") if lcol else float("nan"),
        "close": pd.to_numeric(df[ccol], errors="coerce"),
        "volume": pd.to_numeric(df[vcol], errors="coerce") if vcol else 0.0,
    })
    out = out.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    return out


def _fetch_daily_online(sym: dict, start_date: str, end_date: str) -> pd.DataFrame:
    """在线采集日线，多接口依次回退。"""
    code, market, kind = sym["code"], sym["market"], sym["kind"]
    errors = []

    # 1) 东财日线（股票前复权 / 指数）
    try:
        import akshare as ak
        if kind == "index":
            df = ak.index_zh_a_hist(symbol=code, period="daily",
                                    start_date=start_date, end_date=end_date)
        else:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date,
                                    end_date=end_date, adjust="qfq")
        if df is not None and len(df) > 0:
            return _normalize_daily_df(df)
        errors.append("stock/index_zh_a_hist 返回空")
    except Exception as e:
        errors.append(f"em 日线接口失败: {e}")

    # 2) 新浪日线（symbol 需带前缀；无起止参数，自行截断）
    #    股票用 stock_zh_a_daily（前复权）；指数用 stock_zh_index_daily（不复权）
    try:
        import akshare as ak
        if kind == "index":
            df = ak.stock_zh_index_daily(symbol=market + code)
        else:
            df = ak.stock_zh_a_daily(symbol=market + code, adjust="qfq")
        if df is not None and len(df) > 0:
            ndf = _normalize_daily_df(df)
            return ndf[ndf["date"] >= start_date]
        errors.append("新浪日线接口返回空")
    except Exception as e:
        errors.append(f"新浪日线接口失败: {e}")

    raise CollectorError("；".join(errors))


def get_daily_data(symbol: str, years: int = 3) -> dict:
    """
    获取近 N 年日线（供 /predict 与训练脚本使用）。

    缓存策略（带日期失效）：
      - 缓存最新日期已覆盖最近应有会话 → 直接复用；
      - 否则在线刷新并落盘；失败时降级返回旧缓存；
      - 无任何数据 → 抛 CollectorError。

    返回 {"symbol", "data": [{"date","open","high","low","close","volume"}, ...]}
    """
    sym = parse_symbol(symbol)
    s = sym["symbol"]
    end = now_bj().date()
    start = end - timedelta(days=int(years * 365.25))
    expected = _expected_latest_session()

    cached = _read_daily_cache(s)
    if cached is not None and str(cached["date"].max()) >= expected:
        return {"symbol": s, "data": _df_to_daily_items(cached)}

    try:
        df = _fetch_daily_online(sym, start.isoformat(), end.isoformat())
        if len(df) == 0:
            raise CollectorError("日线数据为空")
        _write_daily_cache(s, df)
        return {"symbol": s, "data": _df_to_daily_items(df)}
    except CollectorError as e:
        logger.warning("日线在线采集失败 %s: %s", s, e)
        if cached is not None:
            return {"symbol": s, "data": _df_to_daily_items(cached)}
        raise CollectorError(f"日线数据采集失败且无本地缓存: {e}") from e


def _df_to_daily_items(df: pd.DataFrame) -> list:
    items = []
    for _, r in df.iterrows():
        try:
            items.append({
                "date": str(r["date"]),
                "open": _safe_round(r.get("open")),
                "high": _safe_round(r.get("high")),
                "low": _safe_round(r.get("low")),
                "close": round(float(r["close"]), 4),
                "volume": _to_int(r.get("volume", 0)),
            })
        except (TypeError, ValueError):
            continue
    return items


def _safe_round(v, nd=4) -> Optional[float]:
    try:
        f = float(v)
        return round(f, nd) if pd.notna(f) else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 交易日历
# ---------------------------------------------------------------------------
def get_trade_dates() -> list:
    """
    获取交易日列表（升序，元素为 "YYYY-MM-DD" 字符串）。
    优先读缓存（30 天有效），失败时在线采集，再失败返回空列表（由调用方退化处理）。
    """
    cal_path = CACHE_DIR / "trade_dates.csv"
    today = now_bj().date()
    if cal_path.exists():
        age_days = (today - datetime.fromtimestamp(cal_path.stat().st_mtime, _BJ_TZ).date()).days
        if age_days <= _TRADE_CAL_TTL_DAYS:
            try:
                df = pd.read_csv(cal_path, dtype=str)
                if len(df) > 0:
                    return sorted(df.iloc[:, 0].astype(str).tolist())
            except Exception as e:
                logger.warning("交易日历缓存损坏: %s", e)
    try:
        import akshare as ak
        df = ak.tool_trade_date_hist_sina()
        col = df.columns[0]
        dates = sorted(pd.to_datetime(df[col]).dt.strftime("%Y-%m-%d").tolist())
        pd.DataFrame({"trade_date": dates}).to_csv(cal_path, index=False)
        return dates
    except Exception as e:
        logger.warning("交易日历采集失败（将退化为跳过周末推算）: %s", e)
        # 用周末规则生成一个覆盖前后若干年的近似日历，保证功能可用
        dates = []
        d = date(today.year - 3, 1, 1)
        end = date(today.year + 2, 12, 31)
        while d <= end:
            if d.weekday() < 5:
                dates.append(d.isoformat())
            d += timedelta(days=1)
        return dates


def next_trade_dates(after_date: str, n: int) -> list:
    """推算 after_date 之后（不含）的 n 个交易日，返回 "YYYY-MM-DD" 列表。"""
    cal = get_trade_dates()
    if after_date in cal:
        idx = cal.index(after_date)
        result = cal[idx + 1: idx + 1 + n]
    else:
        future = [d for d in cal if d > after_date]
        result = future[:n]
    # 日历不够长（退化日历止于未来 2 年内足够，一般不会发生）→ 用周末规则补齐
    while len(result) < n:
        last = result[-1] if result else after_date
        d = datetime.strptime(last, "%Y-%m-%d").date() + timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        if d.isoformat() not in result:
            result.append(d.isoformat())
    return result[:n]
