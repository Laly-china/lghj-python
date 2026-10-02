"""业务异常与全局异常处理模块。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/exception/BusinessException.java
- feng-lghj/lghj-server/src/main/java/com/lghj/handler/GlobalExceptionHandler.java

行为对齐说明：
- BusinessException 由全局处理器捕获后返回 Result.error(errorEnum)，HTTP 状态码 200
  （原 Spring @RestControllerAdvice 未加 @ResponseStatus，即默认 200）。
- 拦截器抛出异常前会手动 response.setStatus(401/403/500)，对应本工程
  interceptor.py 中直接返回对应 HTTP 状态码 + Result 体。
- 参数校验异常（原 BindException）返回 Result.error(PARAM_INVALID, 第一个错误信息)。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.result import ErrorEnum, Result

logger = logging.getLogger(__name__)


class BusinessException(Exception):
    """自定义业务异常类（照抄 com/lghj/exception/BusinessException.java）。"""

    def __init__(self, error_enum: ErrorEnum, detail_msg: str | None = None) -> None:
        # 原实现：message = errorEnum.msg 或 errorEnum.msg + "：" + detailMsg
        self.error_enum = error_enum
        self.detail_msg = detail_msg
        super().__init__(
            error_enum.msg if detail_msg is None else f"{error_enum.msg}：{detail_msg}"
        )


def _result_json(result: Result, status_code: int = 200) -> JSONResponse:
    """将 Result 序列化为 JSONResponse（原 Result 由 Jackson 输出，HTTP 状态码默认 200）。"""
    return JSONResponse(status_code=status_code, content=result.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器（对应 GlobalExceptionHandler 的三个 @ExceptionHandler）。"""

    @app.exception_handler(BusinessException)
    async def handle_business_exception(_request: Request, exc: BusinessException) -> JSONResponse:
        # 对应 handleBusinessException：Result.error(e.getErrorEnum())，HTTP 200
        logger.error("业务异常：%s", exc, exc_info=exc)
        return _result_json(Result.error(exc.error_enum))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # 对应 handleBindException：取第一个校验错误的 message
        logger.error("参数校验异常：%s", exc)
        first = exc.errors()[0] if exc.errors() else {}
        detail = str(first.get("msg", "参数格式无效"))
        return _result_json(Result.error(ErrorEnum.PARAM_INVALID, detail))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # FastAPI 框架层 404/405 等：统一转成 Result 体（原系统无此路径，兜底为系统错误语义）
        logger.error("HTTP异常：%s %s", exc.status_code, exc.detail)
        return _result_json(Result.error(ErrorEnum.SYSTEM_ERROR), exc.status_code)

    @app.exception_handler(Exception)
    async def handle_exception(_request: Request, exc: Exception) -> JSONResponse:
        # 对应 handleException：Result.error(ErrorEnum.SYSTEM_ERROR)，HTTP 200
        logger.error("系统内部异常：%s", exc, exc_info=exc)
        return _result_json(Result.error(ErrorEnum.SYSTEM_ERROR))
