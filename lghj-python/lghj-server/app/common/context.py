"""用户上下文模块（ThreadLocal 的 Python 等价实现）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/context/BaseContext.java

原 Java 用 ThreadLocal 保存当前登录用户 ID；Python 侧用 contextvars
（与 asyncio 协程安全兼容），拦截器写入、业务代码读取。
"""

from __future__ import annotations

from contextvars import ContextVar

# 当前登录用户 ID（对应 BaseContext 的 ThreadLocal<Long>）
_current_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)


class BaseContext:
    """当前登录用户上下文。"""

    @staticmethod
    def set_current_id(user_id: int | None) -> None:
        _current_id.set(user_id)

    @staticmethod
    def get_current_id() -> int | None:
        return _current_id.get()

    @staticmethod
    def clear() -> None:
        _current_id.set(None)
