"""主服务入口模块。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/LghjServerApplication.java（Spring Boot 启动类）
- feng-lghj/lghj-server/src/main/java/com/lghj/config/WebMvcConfiguration.java（拦截器注册）
- feng-lghj/lghj-server/src/main/java/com/lghj/handler/GlobalExceptionHandler.java（全局异常）

硬性设计：路由自动发现——递归导入 app/controller/ 下所有 Python 模块，
收集模块级 `router`（APIRouter 实例）并 include。后续在 controller/ 下新增
路由文件时**无需修改本文件**；子目录不存在/为空时自动跳过不报错。

启动方式：uvicorn app.main:app --host 127.0.0.1 --port 8080
"""

from __future__ import annotations

import logging
import pkgutil
from importlib import import_module

from fastapi import FastAPI

from app.common.exception import register_exception_handlers
from app.config import settings
from app.interceptor import JwtTokenInterceptorMiddleware
from app.utils import http_client
from app.utils.redis_client import get_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# FastAPI 实例（对应 Spring Boot 应用上下文）
app = FastAPI(
    title="量股化金接口文档",
    description="量股化金接口文档",
    version="v1.0.0",
    docs_url="/doc.html",       # 对应原 knife4j /doc.html 入口
    redoc_url=None,
)


def _register_controllers() -> None:
    """递归发现并注册 app/controller/ 下的全部路由模块。

    规则：
    - 使用 pkgutil.walk_packages 递归遍历 app/controller 包（含任意层级子目录）
    - 导入每个模块后，收集其模块级名为 router 的 APIRouter 实例
    - 子目录不存在/为空/无 __init__.py 时静默跳过，不报错
    """
    import app.controller as controller_pkg

    prefix = controller_pkg.__name__ + "."
    imported_modules: list[str] = []

    for module_info in pkgutil.walk_packages(controller_pkg.__path__, prefix=prefix):
        module_name = module_info.name
        try:
            module = import_module(module_name)
        except Exception as exc:  # noqa: BLE001
            # 单个路由模块导入失败：记录并继续，保证其余路由可用
            logger.error("路由模块导入失败：%s，原因：%s", module_name, exc)
            continue
        imported_modules.append(module_name)
        router = getattr(module, "router", None)
        if router is not None:
            app.include_router(router)
            logger.info("已注册路由模块：%s", module_name)

    logger.info("控制器自动发现完成，共导入 %d 个模块", len(imported_modules))


@app.on_event("startup")
def on_startup() -> None:
    """启动钩子：预热 Redis 连接（对应 Spring 容器就绪后连接中间件）。

    任务B 最小挂钩：Redis 就绪后调用 app/task 包的 start()，启动交易引擎的
    订单恢复与 3 秒行情撮合调度（对应原 Spring 托管的定时任务/启动任务）。
    """
    try:
        get_redis().ping()
        logger.info("Redis 连接正常（db=%s）", settings.redis_db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis 暂不可用（服务仍可启动，涉及缓存功能将降级）：%s", exc)

    # 交易后台任务（订单恢复 + 行情撮合调度）；失败不阻断服务启动
    try:
        from app import task as app_task

        app_task.start()
    except Exception as exc:  # noqa: BLE001
        logger.error("交易后台任务启动失败：%s", exc)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """关闭钩子：停止交易后台任务并释放共享 HTTP 连接池。"""
    try:
        from app import task as app_task

        await app_task.stop()
    except Exception as exc:  # noqa: BLE001
        logger.error("交易后台任务停止异常：%s", exc)
    await http_client.close_async_client()


# 注册 JWT 拦截器（对应 WebMvcConfiguration.addInterceptors）
app.add_middleware(JwtTokenInterceptorMiddleware)

# 注册全局异常处理器（对应 GlobalExceptionHandler）
register_exception_handlers(app)

# 模块导入期即完成路由自动发现（保证 `from app.main import app` 后路由可用）
_register_controllers()


@app.get("/")
def index() -> dict:
    """根路径探活（非原系统契约，仅用于冒烟自测）。"""
    return {"app": "lghj-server", "status": "up"}
