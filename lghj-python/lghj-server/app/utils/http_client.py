"""HTTP 客户端模块（共享 httpx 客户端）。

对应复现原 Java：
- RealTimeStockServiceImpl / StockSearchServiceImpl 中使用的
  hutool HttpUtil.createGet(...) 与 RestTemplate（调用 Python 预测服务）。

统一封装超时、浏览器级 Referer/User-Agent 请求头（照抄原代码的请求头取值）。
"""

from __future__ import annotations

import httpx

from app.config import settings

# 与原 Java 一致的浏览器 UA（Chrome/142.0.0.0）
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)

# 默认超时：原新浪/腾讯K线请求 timeout(5000)，其余接口默认 5 秒
DEFAULT_TIMEOUT = 5.0

_async_client: httpx.AsyncClient | None = None


def get_async_client() -> httpx.AsyncClient:
    """获取共享异步客户端（应用生命周期内复用连接池）。"""
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True)
    return _async_client


async def close_async_client() -> None:
    """应用关闭时释放连接池。"""
    global _async_client
    if _async_client is not None and not _async_client.is_closed:
        await _async_client.aclose()
    _async_client = None


async def get_text(
    url: str,
    params: dict[str, str | int] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str | None:
    """GET 请求并返回文本体；异常/非2xx 返回 None（对应原 HttpUtil.get 的 try/catch 语义）。"""
    try:
        client = get_async_client()
        response = await client.get(url, params=params, headers=headers, timeout=timeout)
        if response.status_code >= 400:
            return None
        return response.text
    except Exception:  # noqa: BLE001 原系统对外部接口异常一律捕获降级
        return None


def sina_headers() -> dict[str, str]:
    """新浪K线请求头（照抄原 fetchHistoryFromSina）。"""
    return {"Referer": "http://finance.sina.com.cn/", "User-Agent": BROWSER_UA}


def tencent_headers() -> dict[str, str]:
    """腾讯K线请求头（照抄原 fetchHistoryFromTencent）。"""
    return {"Referer": "https://gu.qq.com/", "User-Agent": BROWSER_UA}


def eastmoney_headers(keyword: str) -> dict[str, str]:
    """东方财富新闻请求头（照抄原 getStockNews）。"""
    return {
        "Referer": f"https://so.eastmoney.com/news/s?keyword={keyword}",
        "User-Agent": BROWSER_UA,
    }


def prediction_minute_url(symbol: str) -> str:
    """分时数据来源 URL（照抄 UrlConstant.PREDICTION_API_MINUTE_URL 的 {symbol} 替换）。"""
    return settings.prediction_api_minute_url.replace("{symbol}", symbol)
