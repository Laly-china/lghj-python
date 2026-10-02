"""实时股票数据接口路由。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/user/RealTimeStockController.java

接口契约（照抄，三个接口均在用户端拦截器放行清单内，无需 token）：
- GET /api/user/realtime/quote?market=sh&code=600519     获取股票实时行情
- GET /api/user/realtime/news?symbol=600519&recentN=10   获取股票实时资讯
- GET /api/user/realtime/minute?market=sh&code=600519    获取股票分时数据
"""

from __future__ import annotations

from fastapi import APIRouter

from app.common.result import Result
from app.service import real_time_stock_service

router = APIRouter(tags=["实时股票数据接口"])


@router.get("/api/user/realtime/quote")
async def get_real_time_quote(market: str, code: str) -> Result:
    """获取股票实时行情（对应 getRealTimeQuote；失败时 data 为 null，HTTP 仍 200）。"""
    data = await real_time_stock_service.get_real_time_quote(market, code)
    return Result.success(data)


@router.get("/api/user/realtime/news")
async def get_stock_news(symbol: str, recentN: int = 10) -> Result:
    """获取股票实时资讯（对应 getStockNews，recentN 默认 10）。"""
    data = await real_time_stock_service.get_stock_news(symbol, recentN)
    return Result.success(data)


@router.get("/api/user/realtime/minute")
async def get_minute_data(market: str, code: str) -> Result:
    """获取股票分时数据（对应 getMinuteData；数据来自 Python 预测服务 8001）。"""
    data = await real_time_stock_service.get_minute_data(market, code)
    return Result.success(data)
