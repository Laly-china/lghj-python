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


class KbSearchPort(ABC):
    """知识库检索端口（本工程扩展，原 Java 无）：个人知识库的标题列举与内容检索。"""

    @abstractmethod
    def list_titles(self, user_id: str, limit: int = 10) -> list[str]:
        """列举用户知识库文档标题（注入对话上下文用）；失败返回空列表。"""
        raise NotImplementedError

    @abstractmethod
    def search(self, user_id: str, query: str, limit: int = 5) -> list[dict]:
        """按关键词检索用户文档，返回 [{title, snippet, score}]；失败返回空列表。"""
        raise NotImplementedError
