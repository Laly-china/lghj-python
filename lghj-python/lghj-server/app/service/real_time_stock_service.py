"""实时行情/资讯/K线/分时业务。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/IRealTimeStockService.java
- feng-lghj/lghj-server/src/main/java/com/lghj/service/impl/RealTimeStockServiceImpl.java

外部数据源与解析逻辑逐行照抄：
- 实时行情：腾讯 qt.gtimg.cn，响应按引号截取后以 ~ 分割，字段索引
  1=名称 2=代码 3=最新价 4=昨收 5=今开 6=成交量 31=涨跌额 32=涨跌幅
- 历史K线：新浪 scale=240(日)/1200(周)/7200(月)，失败降级腾讯 kline（day/week/month）
- 实时资讯：东方财富 search-api-web JSONP，解析 (...) 内 JSON
- 分时数据：调用 Python 预测服务 http://localhost:8001/minute/{symbol}（Redis 锁防击穿）
Redis 缓存键与 24 小时 TTL 照抄原常量。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from decimal import Decimal, InvalidOperation
from typing import Any

from app.common import constants as C
from app.pojo.vo import StockNewsVO
from app.utils import http_client
from app.utils.redis_client import get_redis, cache_get, cache_get_json, cache_set, cache_set_json, cache_delete

logger = logging.getLogger(__name__)

# RealTimeStockServiceImpl 内部常量
REDIS_KEY_PREFIX = "stock:minute:"
EXPIRE_TIME_HOURS = 24  # 过期时间，单位小时
REFRESH_INTERVAL = 60   # 缓存刷新时间（秒）


def _to_decimal(value: str | None, default: str = "0") -> float:
    """字符串转数字，异常时返回 0（对应原 toBigDecimal，Jackson 输出数字）。"""
    if value is None or not value.strip():
        return float(Decimal(default))
    try:
        return float(Decimal(value.strip()))
    except InvalidOperation:
        logger.warning("BigDecimal转换失败，输入值：%s", value)
        return float(Decimal(default))


def _to_long(value: str | None) -> int:
    """字符串转整数，异常时返回 0（对应原 toLong）。"""
    if value is None or not value.strip():
        return 0
    try:
        return int(value.strip())
    except ValueError:
        logger.warning("Long转换失败，输入值：%s", value)
        return 0


def _safe_get(fields: list[str], index: int, default: str = "") -> str:
    """安全获取数组元素，避免越界（对应原 safeGet）。"""
    if 0 <= index < len(fields):
        return fields[index] if fields[index] is not None else default
    return default


# ====================== 实时行情（腾讯 qt.gtimg.cn） ======================

async def get_real_time_quote(market: str | None, code: str | None) -> dict[str, Any] | None:
    """获取股票实时行情（对应 getRealTimeQuote）。

    返回 {code, name, price, prevClose, open, volume, change, changePercent}，
    失败返回 None（对应原返回 null，控制器仍包 Result.success(null)）。
    """
    normalized_market = (market or "").strip().lower()
    normalized_code = (code or "").strip()
    redis_key = C.REDIS_STOCK_REAL_TIME_KEY + normalized_market + normalized_code

    cached = cache_get(redis_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:  # noqa: BLE001
            cache_delete(redis_key)

    url = C.GET_REAL_TIME_QUOTE_URL + normalized_market + normalized_code
    response = await http_client.get_text(url)
    if not response:
        logger.warning("实时行情接口返回空，市场：%s，股票代码：%s", normalized_market, normalized_code)
        return None

    # 提取引号内的数据
    start = response.find('"')
    end = response.rfind('"')
    if start == -1 or end == -1 or end <= start:
        logger.warning("实时行情数据格式错误，市场：%s，股票代码：%s", normalized_market, normalized_code)
        return None

    data = response[start + 1 : end]
    if not data:
        logger.warning("实时行情数据内容为空，市场：%s，股票代码：%s", normalized_market, normalized_code)
        return None

    # 使用 -1 保留空字段，避免字段丢失（对应 split("~", -1)）
    fields = data.split("~")
    # 确保字段数量足够（至少包含涨跌幅，索引32）
    if len(fields) < 33:
        logger.warning(
            "实时行情数据字段不足，市场：%s，股票代码：%s，实际字段数：%s",
            normalized_market, normalized_code, len(fields),
        )
        return None

    quote: dict[str, Any] = {
        "code": _safe_get(fields, 2, ""),
        "name": _safe_get(fields, 1, ""),
        "price": _to_decimal(_safe_get(fields, 3, "0")),
        "prevClose": _to_decimal(_safe_get(fields, 4, "0")),
        "open": _to_decimal(_safe_get(fields, 5, "0")),
        "volume": _to_long(_safe_get(fields, 6, "0")),  # 成交量单位：手，如需股数请 *100
        "change": _to_decimal(_safe_get(fields, 31, "0")),
        "changePercent": _to_decimal(_safe_get(fields, 32, "0")),
    }

    # 写缓存（24 小时，照抄原 EXPIRE_TIME）
    cache_set_json(redis_key, quote, expire_hours=EXPIRE_TIME_HOURS)
    return quote


# ====================== 实时资讯（东方财富 JSONP） ======================

def _normalize_news_keyword(symbol: str | None) -> str:
    """资讯关键词归一化（对应 normalizeNewsKeyword）。"""
    if symbol is None or not symbol.strip():
        return "股市"

    normalized = symbol.strip().lower()
    if normalized in ("sh000001", "000001.sh"):
        return "上证指数"
    if normalized in ("sz399001", "399001.sz"):
        return "深证成指"
    if normalized in ("sz399006", "399006.sz"):
        return "创业板指"
    if normalized.startswith("sh") or normalized.startswith("sz"):
        return normalized[2:]
    return symbol.strip()


def _clean_text(text: str | None) -> str:
    """清洗和格式化字符串（对应 cleanText：去 <em> 标签与 &nbsp;）。"""
    if text is None:
        return ""
    return text.replace("<em>", "").replace("</em>", "").replace("&nbsp;", " ").strip()


async def get_stock_news(symbol: str | None, recent_n: int) -> list[StockNewsVO]:
    """获取股票实时资讯（对应 getStockNews，东方财富 JSONP 解析照抄）。"""
    keyword = _normalize_news_keyword(symbol)

    # 构造内部参数（结构照抄原 Map 组装）
    inner_param: dict[str, Any] = {
        "uid": "",
        "keyword": keyword,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
    }
    cms_param = {
        "searchScope": "default",
        "sort": "default",
        "pageIndex": 1,
        "pageSize": recent_n,
        "preTag": "",
        "postTag": "",
    }
    inner_param["param"] = {"cmsArticleWebOld": cms_param}

    json_param = json.dumps(inner_param, ensure_ascii=False, separators=(", ", ": "))
    cb = f"jQuery35101792940631092459_{int(time.time() * 1000)}"

    request_params = {
        "cb": cb,
        "param": json_param,
        "_": str(int(time.time() * 1000)),
    }

    response = await http_client.get_text(
        C.STOCK_NEWS_URL,
        params=request_params,
        headers=http_client.eastmoney_headers(keyword),
    )

    if response and "(" in response:
        json_str = response[response.find("(") + 1 : response.rfind(")")]
        try:
            json_object = json.loads(json_str)
        except Exception:  # noqa: BLE001
            json_object = None
        if isinstance(json_object, dict) and "result" in json_object:
            result = json_object.get("result")
            if isinstance(result, dict) and "cmsArticleWebOld" in result:
                articles = result.get("cmsArticleWebOld") or []
                news_list: list[StockNewsVO] = []
                for article in articles:
                    vo = StockNewsVO(
                        keyword=keyword,
                        title=_clean_text(article.get("title")),
                        content=_clean_text(article.get("content")),
                        publishTime=article.get("date"),
                        source=article.get("mediaName"),
                    )
                    code = article.get("code")
                    if code:
                        vo.url = f"http://finance.eastmoney.com/a/{code}.html"
                    else:
                        vo.url = article.get("url")
                    news_list.append(vo)
                return news_list
    return []


# ====================== 历史K线（新浪 + 腾讯降级） ======================

def _normalize_stock_symbol(symbol: str | None) -> tuple[str, str] | None:
    """股票代码归一化，返回 (market, code)（对应 normalizeStockSymbol）。"""
    if symbol is None or not symbol.strip():
        return None

    normalized = symbol.strip().lower()
    if normalized.startswith("sh") or normalized.startswith("sz"):
        market = normalized[:2]
        code = normalized[2:]
    else:
        code = normalized
        market = "sh" if code.startswith(("5", "6", "9")) else "sz"

    if not code:
        return None
    return market, code


def _normalize_period(period: str | None) -> str:
    """周期归一化，仅允许 D/W/M，默认 D（对应 normalizePeriod）。"""
    normalized = (period or "D").strip().upper()
    if normalized not in ("W", "M"):
        return "D"
    return normalized


def _to_sina_scale(period: str) -> int:
    """周期→新浪 scale（对应 toSinaScale：D=240，W=1200，M=7200）。"""
    if period == "W":
        return 1200
    if period == "M":
        return 7200
    return 240


def _to_tencent_kline_type(period: str) -> str:
    """周期→腾讯K线类型（对应 toTencentKlineType：D=day，W=week，M=month）。"""
    if period == "W":
        return "week"
    if period == "M":
        return "month"
    return "day"


def _extract_json_array(response: str) -> str | None:
    """提取 JSON 数组文本（对应 extractJsonArray：首个 [ 至最后一个 ]）。"""
    start = response.find("[")
    end = response.rfind("]")
    if start < 0 or end <= start:
        return None
    return response[start : end + 1]


async def _fetch_history_from_sina(market: str, code: str, period: str) -> list[dict[str, Any]]:
    """新浪K线（对应 fetchHistoryFromSina）。"""
    params = {
        "symbol": market + code,
        "scale": str(_to_sina_scale(period)),
        "ma": "no",
        "datalen": "1000",
    }
    response = await http_client.get_text(
        C.STOCK_HISTORY_SINA_KLINE_URL,
        params=params,
        headers=http_client.sina_headers(),
    )
    if not response:
        logger.warning("新浪历史K线接口返回空，市场：%s，股票代码：%s，周期：%s", market, code, period)
        return []

    array_text = _extract_json_array(response)
    if array_text is None:
        logger.warning("新浪历史K线接口返回格式异常，市场：%s，股票代码：%s，周期：%s", market, code, period)
        return []

    try:
        klines = json.loads(array_text)
    except Exception:  # noqa: BLE001
        klines = None
    if not klines:
        logger.warning("新浪历史K线接口无数据，市场：%s，股票代码：%s，周期：%s", market, code, period)
        return []

    history: list[dict[str, Any]] = []
    for line in klines:
        if not isinstance(line, dict):
            continue
        date = line.get("day")
        history.append(
            {
                # day 形如 "2026-10-02 15:00:00"，截取前 10 位日期
                "date": date[:10] if isinstance(date, str) and len(date) >= 10 else date,
                "open": _to_decimal(_safe_str(line.get("open"))),
                "close": _to_decimal(_safe_str(line.get("close"))),
                "high": _to_decimal(_safe_str(line.get("high"))),
                "low": _to_decimal(_safe_str(line.get("low"))),
                "volume": _to_long(_safe_str(line.get("volume"))),
            }
        )
    return history


def _safe_str(value: Any) -> str | None:
    """任意值转字符串（新浪接口数字可能直接是数值类型）。"""
    if value is None:
        return None
    return str(value)


async def _fetch_history_from_tencent(market: str, code: str, period: str) -> list[dict[str, Any]]:
    """腾讯K线降级（对应 fetchHistoryFromTencent）。"""
    symbol = market + code
    kline_type = _to_tencent_kline_type(period)
    params = {"param": f"{symbol},{kline_type},,,1000"}
    response = await http_client.get_text(
        C.STOCK_HISTORY_TENCENT_KLINE_URL,
        params=params,
        headers=http_client.tencent_headers(),
    )
    if not response:
        logger.warning("历史K线接口返回空，市场：%s，股票代码：%s", market, code)
        return []

    try:
        json_object = json.loads(response)
    except Exception:  # noqa: BLE001
        json_object = None
    data = json_object.get("data") if isinstance(json_object, dict) else None
    stock_data = data.get(symbol) if isinstance(data, dict) else None
    klines = stock_data.get(kline_type) if isinstance(stock_data, dict) else None
    if not klines:
        logger.warning("历史K线接口无数据，市场：%s，股票代码：%s，周期：%s", market, code, period)
        return []

    history: list[dict[str, Any]] = []
    for line in klines:
        if not isinstance(line, list) or len(line) < 6:
            continue
        history.append(
            {
                "date": str(line[0]),
                "open": _to_decimal(_safe_str(line[1])),
                "close": _to_decimal(_safe_str(line[2])),
                "high": _to_decimal(_safe_str(line[3])),
                "low": _to_decimal(_safe_str(line[4])),
                "volume": _to_long(_safe_str(line[5])),
            }
        )
    return history


async def get_stock_history(symbol: str | None, period: str | None) -> list[dict[str, Any]]:
    """获取股票历史K线数据（对应 getStockHistory，Redis 缓存 24 小时）。

    缓存键：stock:history:v2:{market}{code}:{period}（RedisConstant.STOCK_HISTORY_KEY）。
    """
    stock_symbol = _normalize_stock_symbol(symbol)
    if stock_symbol is None:
        logger.warning("历史K线股票代码为空或非法，symbol=%s", symbol)
        return []
    market, code = stock_symbol

    normalized_period = _normalize_period(period)
    redis_key = C.REDIS_STOCK_HISTORY_KEY + market + code + ":" + normalized_period

    cached = cache_get(redis_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:  # noqa: BLE001
            logger.warning("读取历史K线缓存失败，key=%s", redis_key)
            cache_delete(redis_key)

    history = await _fetch_history_from_sina(market, code, normalized_period)
    if not history:
        history = await _fetch_history_from_tencent(market, code, normalized_period)
    if not history:
        return []

    cache_set_json(redis_key, history, expire_hours=EXPIRE_TIME_HOURS)
    logger.info("历史K线数据缓存到Redis，key=%s，过期时间=%s小时", redis_key, EXPIRE_TIME_HOURS)
    return history


# ====================== 分时数据（Python 预测服务） ======================

def _get_cached_minute_data(market: str, code: str) -> list[dict[str, Any]] | None:
    """从Redis中获取当日股票分时信息（对应 getCachedMinuteData）。"""
    redis_key = REDIS_KEY_PREFIX + market + code
    try:
        data = get_redis().get(redis_key)
        if data is not None:
            return json.loads(data)
    except Exception:  # noqa: BLE001
        logger.error("从Redis获取分时数据失败，市场：%s，股票代码：%s", market, code)
    return None


def _cache_minute_data(market: str, code: str, data: list[dict[str, Any]]) -> None:
    """将当日股票分时信息存入Redis，过期时间 24 小时（对应 cacheMinuteData）。"""
    redis_key = REDIS_KEY_PREFIX + market + code
    get_redis().delete(redis_key)  # 清空原有列表（如有）
    if not cache_set_json(redis_key, data, expire_hours=EXPIRE_TIME_HOURS):
        logger.error("分时数据缓存到Redis失败，市场：%s，股票代码：%s", market, code)
    else:
        logger.info("分时数据缓存到Redis，市场：%s，股票代码：%s，过期时间：%s小时", market, code, EXPIRE_TIME_HOURS)


async def _fetch_from_python_service(market: str, code: str) -> list[dict[str, Any]] | None:
    """从 Python 预测服务获取分时数据（对应 fetchFromPythonService）。

    URL 照抄 UrlConstant.PREDICTION_API_MINUTE_URL = http://localhost:8001/minute/{symbol}
    超时 30s：预测服务冷启动当日首次经 akshare 采集外网分时（含写入 CSV 缓存），
    可能耗时超过 5s；超时过短会导致冷门标的/指数首次取数被误判为失败返回空数组。
    """
    url = http_client.prediction_minute_url(market + code)
    response = await http_client.get_text(url, timeout=30.0)
    if not response:
        return None
    try:
        parsed = json.loads(response)
    except Exception:  # noqa: BLE001
        logger.error("调用 Python 服务异常：响应非 JSON")
        return None
    if not isinstance(parsed, list):
        return None
    return parsed


async def get_minute_data(market: str | None, code: str | None) -> list[dict[str, Any]]:
    """获取股票分时数据（对应 getMinuteData，含缓存新鲜度与分布式锁防击穿逻辑）。"""
    market = market or ""
    code = code or ""
    redis_key = REDIS_KEY_PREFIX + market + code

    # 1. 尝试从 Redis 获取数据
    cached_data = _get_cached_minute_data(market, code)

    # 判断是否需要刷新
    need_refresh = False
    if not cached_data:
        need_refresh = True
    else:
        update_time_key = "stock:minute:updatetime:" + market + code
        last_update_time_str = cache_get(update_time_key)
        last_update_time = int(last_update_time_str) if last_update_time_str else 0
        # 距上次更新超过60秒则刷新（原逻辑简化为总是处于可刷新状态）
        if time.time() * 1000 - last_update_time > REFRESH_INTERVAL * 1000:
            need_refresh = True

    if not need_refresh and cached_data is not None:
        return cached_data

    # 2. 需要刷新，尝试获取分布式锁，避免缓存击穿
    lock_key = C.REDIS_LOCK_PREFIX + market + code
    from app.utils import lock_util

    locked = lock_util.try_lock(lock_key, wait_time=0, lease_time=C.MINUTE_LOCK_LEASE_SECONDS)

    if locked:
        try:
            logger.info("获取锁成功，准备从 Python 服务更新分时数据，市场：%s，股票代码：%s", market, code)
            new_data = await _fetch_from_python_service(market, code)
            if new_data:
                _cache_minute_data(market, code, new_data)
                update_time_key = "stock:minute:updatetime:" + market + code
                cache_set(
                    update_time_key,
                    str(int(time.time() * 1000)),
                    expire_hours=EXPIRE_TIME_HOURS,
                )
                return new_data
            # 获取失败，有旧缓存则返回旧缓存，否则返回空
            return cached_data if cached_data is not None else []
        finally:
            # 释放锁
            lock_util.unlock(lock_key)
    else:
        # 获取锁失败：有旧数据直接降级返回；否则等待 100ms 后再读一次缓存
        if cached_data is not None:
            logger.info("获取锁失败，降级返回旧缓存数据，市场：%s，股票代码：%s", market, code)
            return cached_data
        await asyncio.sleep(0.1)
        again = _get_cached_minute_data(market, code)
        return again if again is not None else []
