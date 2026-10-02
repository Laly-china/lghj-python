"""统一响应体。

复现自原 Java 类：
    ai-agent-scaffoid-feng/ai-agent-scaffoid-feng-api/src/main/java/cn/feng/api/response/Response.java

结构：Response{code, info, data}，code="0000" 表示成功（见 ResponseCode）。
data 允许为 None（对应原 Java builder 不 set data 时序列化为 null）。
"""

from __future__ import annotations

from typing import Generic, TypeVar

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.types.response_code import ResponseCode

T = TypeVar("T")


class Response(BaseModel, Generic[T]):
    """统一响应体（照抄原 Java Response 字段）。"""

    code: str
    info: str | None = None
    data: T | None = None

    @staticmethod
    def build(code: str, info: str | None, data: T | None = None) -> "Response[T]":
        """对应原 Java Response.builder().code(...).info(...).data(...).build()。"""
        return Response[T](code=code, info=info, data=data)

    @staticmethod
    def success(data: T | None = None) -> "Response[T]":
        """成功响应便捷方法。"""
        from app.types.response_code import ResponseCode

        return Response[T](code=ResponseCode.SUCCESS.value, info=ResponseCode.SUCCESS.info, data=data)

    @staticmethod
    def of_code(response_code: "ResponseCode", data: T | None = None) -> "Response[T]":
        """按 ResponseCode 构造响应（失败路径用）。"""
        return Response[T](code=response_code.value, info=response_code.info, data=data)
