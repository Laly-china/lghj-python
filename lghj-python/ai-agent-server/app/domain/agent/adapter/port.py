"""领域层端口（Port）接口。

复现自原 Java 类：
    ai-agent-scaffoid-feng-domain/.../domain/agent/adapter/port/MarketDataPort.java
    ai-agent-scaffoid-feng-domain/.../agent/adapter/port/SimTradeProfilePort.java

domain 只定义接口（六边形架构出端口），实现落在 infrastructure/adapter/http_ports.py。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class MarketDataPort(ABC):
    """行情数据端口（照抄原 Java MarketDataPort 方法签名）。"""

    @abstractmethod
    def query_realtime_market_json(self, market: str, code: str, recent_news_size: int, include_minute: bool) -> str:
        """查询实时行情 JSON；失败返回空串。"""
        raise NotImplementedError


class SimTradeProfilePort(ABC):
    """模拟交易画像端口（照抄原 Java SimTradeProfilePort 方法签名）。"""

    @abstractmethod
    def query_profile_json(self, user_id: str) -> str:
        """查询用户模拟交易画像 JSON；失败返回空串。"""
        raise NotImplementedError
