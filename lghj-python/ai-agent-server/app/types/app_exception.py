"""应用异常体系。

复现自原 Java 类：
    ai-agent-scaffoid-feng/ai-agent-scaffoid-feng-types/src/main/java/cn/feng/types/exception/AppException.java

原 Java 为 RuntimeException，携带 code / info 两个字段；Python 侧继承 Exception，
trigger 层统一捕获后按 Response{code, info} 返回。
"""

from __future__ import annotations

from app.types.response_code import ResponseCode


class AppException(Exception):
    """应用异常（code + info），对齐原 Java AppException。"""

    def __init__(self, code: str, info: str | None = None, cause: BaseException | None = None) -> None:
        # 原 Java 构造器只给 code 时 info 为 null
        super().__init__(info if info is not None else code)
        self.code = code
        self.info = info
        if cause is not None:
            # 对齐原 Java initCause(cause)
            self.__cause__ = cause

    def __str__(self) -> str:  # 对齐原 Java toString() 的展示形式
        return f"AppException{{code='{self.code}', info='{self.info}'}}"


def app_exception_of(response_code: ResponseCode, info: str | None = None) -> AppException:
    """按 ResponseCode 快速构造 AppException 的便捷工厂。"""
    return AppException(response_code.value, info if info is not None else response_code.info)
