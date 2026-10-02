"""登录校验拦截模块（JWT 拦截器的 FastAPI 实现）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/config/WebMvcConfiguration.java（拦截路径注册）
- feng-lghj/lghj-server/src/main/java/com/lghj/interceptor/JwtTokenUserInterceptor.java
- feng-lghj/lghj-server/src/main/java/com/lghj/interceptor/JwtTokenAdminInterceptor.java

放行清单逐条照抄 WebMvcConfiguration.addInterceptors：

1) 管理端拦截器 addPathPatterns("/api/admin/**")
   - 放行 /api/login
   - 放行 /api/admin/stock/import
   - 放行 /api/admin/stock/init-es
   其余 /api/admin/** 全部要求 token（adminSecretKey 解析，userType 必须=3，否则 403）。

2) 用户端拦截器 addPathPatterns("/api/user/**")
   - 放行 /api/login
   - 放行 /api/user/blog/comments/list   查询博客评论列表（带二级评论，树形结构）
   - 放行 /api/user/realtime/quote       获取股票实时行情
   - 放行 /api/user/realtime/news        获取股票实时资讯
   - 放行 /api/user/realtime/minute      获取股票分时数据
   - 放行 /api/user/blog/query/hot       根据点赞数量（热度）展示博客
   - 放行 /api/user/blog/query/of/user   查看指定用户发的博客
   - 放行 /api/user/stock/search         搜索股票（支持代码前缀和名称模糊搜索）
   - 放行 /api/user/stock/data           获取股票历史K线数据
   其余 /api/user/** 全部要求 token（userSecretKey 解析，仅校验 userId，不校验 userType）。

3) 不匹配以上两个 pattern 的路径（如 /api/login、/api/register、/api/logout、/docs）
   原系统不拦截，本实现同样直接放行。

HTTP 状态码语义照抄：token 缺失/无效 → 401；非管理员访问管理端 → 403。
响应体均为统一 Result（由 BusinessException 处理器语义折叠而来）。
"""

from __future__ import annotations

import logging

import jwt as pyjwt
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.common.constants import JWT_CLAIMS_USER_ID, JWT_CLAIMS_USER_TYPE
from app.common.context import BaseContext
from app.common.result import ErrorEnum, Result
from app.config import settings
from app.utils.jwt_util import parse_jwt

logger = logging.getLogger(__name__)

# ====================== 放行清单（逐条照抄 excludePathPatterns） ======================

# 管理端拦截器放行清单
ADMIN_EXCLUDE_PATHS = {
    "/api/login",
    "/api/admin/stock/import",
    "/api/admin/stock/init-es",
}

# 用户端拦截器放行清单
USER_EXCLUDE_PATHS = {
    "/api/login",
    "/api/user/blog/comments/list",  # 查询博客评论列表（带二级评论，树形结构）
    "/api/user/realtime/quote",      # 获取股票实时行情
    "/api/user/realtime/news",       # 获取股票实时资讯
    "/api/user/realtime/minute",     # 获取股票分时数据
    "/api/user/blog/query/hot",      # 根据点赞数量（热度）展示博客
    "/api/user/blog/query/of/user",  # 查看指定用户发的博客
    "/api/user/stock/search",        # 搜索股票（支持代码前缀和名称模糊搜索）
    "/api/user/stock/data",          # 获取股票历史K线数据
}


def _intercept_body(error_enum: ErrorEnum) -> dict:
    """拦截器抛 BusinessException 后全局处理器实际返回的 Result 体
    （handleBusinessException 只取 errorEnum，detail 信息不进响应体）。"""
    return Result.error(error_enum).model_dump()


def _path_matches(path: str, prefix: str) -> bool:
    """等价 Spring AntPathMatcher 的 /api/xxx/** 双层匹配。"""
    return path == prefix.rstrip("/**") or path.startswith(prefix[:-3] + "/")


class JwtTokenInterceptorMiddleware(BaseHTTPMiddleware):
    """JWT 双拦截器中间件（管理端 + 用户端）。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # ---------- 管理端拦截器：/api/admin/** ----------
        if _path_matches(path, "/api/admin/**") and path not in ADMIN_EXCLUDE_PATHS:
            token = request.headers.get(settings.jwt_admin_token_name)
            # token 为空：401（对应 admin 拦截器前置空校验）
            if token is None or token.strip() == "":
                logger.error("JWT校验失败：请求头中未携带令牌，请求URL：%s", path)
                return JSONResponse(status_code=401, content=_intercept_body(ErrorEnum.NO_LOGIN))
            try:
                claims = parse_jwt(settings.jwt_admin_secret_key, token)
                user_id = int(claims.get(JWT_CLAIMS_USER_ID))
                user_type = int(claims.get(JWT_CLAIMS_USER_TYPE))
                # 管理员权限校验（userType != 3 → 403）
                if user_type != 3:
                    logger.error("JWT校验失败：无管理员权限，用户ID：%s，请求URL：%s", user_id, path)
                    return JSONResponse(
                        status_code=403, content=_intercept_body(ErrorEnum.NO_PERMISSION)
                    )
                BaseContext.set_current_id(user_id)
                logger.info("JWT校验成功，用户ID：%s，请求URL：%s", user_id, path)
            except pyjwt.PyJWTError:
                # 对应 JwtException 分支：401
                logger.error("JWT校验失败：令牌无效或已过期，请求URL：%s", path)
                return JSONResponse(status_code=401, content=_intercept_body(ErrorEnum.NO_LOGIN))
            except (TypeError, ValueError):
                # 对应 NumberFormatException 分支（令牌被篡改）：401
                logger.error("JWT校验失败：令牌内容被篡改，请求URL：%s", path)
                return JSONResponse(status_code=401, content=_intercept_body(ErrorEnum.NO_LOGIN))

        # ---------- 用户端拦截器：/api/user/** ----------
        elif _path_matches(path, "/api/user/**") and path not in USER_EXCLUDE_PATHS:
            token = request.headers.get(settings.jwt_user_token_name)
            try:
                claims = parse_jwt(settings.jwt_user_secret_key, token or "")
                user_id = int(claims.get(JWT_CLAIMS_USER_ID))
                BaseContext.set_current_id(user_id)
                logger.info("jwt校验:%s, 当前用户id：%s", token, user_id)
            except Exception:  # noqa: BLE001 对应用户拦截器 catch(Exception) 一律 401
                logger.error("用户端JWT校验失败，请求URL：%s", path)
                return JSONResponse(status_code=401, content=_intercept_body(ErrorEnum.NO_LOGIN))

        # ---------- 其余路径：原系统不拦截，直接放行 ----------
        response = await call_next(request)
        # 请求结束后清理上下文（对应 ThreadLocal 用后清理，防止协程复用串号）
        BaseContext.clear()
        return response
