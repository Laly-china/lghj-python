"""基础设施层：领域端口 HTTP 实现。

复现自原 Java 类：
    ai-agent-scaffoid-feng-app/src/main/java/cn/feng/adapter/port/HttpMarketDataPort.java
    ai-agent-scaffoid-feng-app/src/main/java/cn/feng/adapter/port/HttpSimTradeProfilePort.java
    ai-agent-scaffoid-feng-app/src/main/java/cn/feng/config/LghjClientProperties.java

对外契约（调主服务 8080 内部 API，严格照抄原 Java URL 与请求头）：
    GET {base-url}/api/internal/market/realtime?market=&code=&recentNewsSize=&includeMinute=
    GET {base-url}/api/internal/sim-trade/profile?userId=
    请求头：X-Internal-Token: {internal-token}（token 非空时携带）
    任何异常 -> 记录告警并返回 ""（与原 Java catch 语义一致）
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx

from app.config import Settings
from app.domain.agent.adapter.port import MarketDataPort, SimTradeProfilePort

logger = logging.getLogger(__name__)


def _build_url(base_url: str, path: str, query: dict[str, object]) -> str:
    """拼接 URL（对应原 Java UriComponentsBuilder.fromHttpUrl().path().queryParam().toUriString()）。"""
    parts = urlsplit(base_url)
    new_path = (parts.path or "") + path
    # urlencode 会把 True 序列化为 True/False 首字母大写，对齐 Java 的 Boolean.toString
    query_pairs = [(k, str(v)) for k, v in query.items() if v is not None]
    return urlunsplit((parts.scheme, parts.netloc, new_path, urlencode(query_pairs), ""))


class _BaseHttpPort:
    """公共逻辑：base_url / internal_token / timeout，X-Internal-Token 头。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def _base_url(self) -> str:
        return self._settings.lghj_base_url

    @property
    def _timeout(self) -> float:
        return float(self._settings.lghj_client_timeout_seconds)

    def _internal_headers(self) -> dict[str, str]:
        """internal-token 非空时携带 X-Internal-Token（照抄原 Java 判断逻辑）。"""
        headers: dict[str, str] = {}
        if self._settings.lghj_internal_api_token:
            headers["X-Internal-Token"] = self._settings.lghj_internal_api_token
        return headers

    def _get_text(self, url: str) -> str:
        """同步 GET，返回响应体文本；任何异常返回 "" 并告警（对齐原 Java try/catch）。"""
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(url, headers=self._internal_headers())
                return resp.text
        except Exception:  # noqa: BLE001 —— 原 Java 捕获所有异常降级为空串
            logger.warning("query internal api failed, url=%s", url, exc_info=True)
            return ""


class HttpMarketDataPort(_BaseHttpPort, MarketDataPort):
    """行情数据端口 HTTP 实现（照抄原 Java HttpMarketDataPort）。"""

    def query_realtime_market_json(self, market: str, code: str, recent_news_size: int, include_minute: bool) -> str:
        # 原 Java：code 为空直接返回 ""
        if not code or not code.strip():
            return ""
        url = _build_url(
            self._base_url,
            "/api/internal/market/realtime",
            {
                "market": market,
                "code": code,
                "recentNewsSize": recent_news_size,
                "includeMinute": include_minute,
            },
        )
        return self._get_text(url)


class HttpSimTradeProfilePort(_BaseHttpPort, SimTradeProfilePort):
    """模拟交易画像端口 HTTP 实现（照抄原 Java HttpSimTradeProfilePort）。"""

    def query_profile_json(self, user_id: str) -> str:
        # 原 Java：userId 为空直接返回 ""
        if not user_id or not user_id.strip():
            return ""
        url = _build_url(
            self._base_url,
            "/api/internal/sim-trade/profile",
            {"userId": user_id},
        )
        return self._get_text(url)
