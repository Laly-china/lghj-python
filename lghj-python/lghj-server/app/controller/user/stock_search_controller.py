"""股票搜索与历史K线接口路由。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/user/StockSearchController.java

接口契约（照抄，两个接口均在用户端拦截器放行清单内，无需 token）：
- GET /api/user/stock/search?keyword=      搜索股票（原 ES，现为 MySQL LIKE，契约不变）
- GET /api/user/stock/data?symbol=&period=D 获取股票历史K线数据（period 默认 D，支持 D/W/M）
"""

from __future__ import annotations

from fastapi import APIRouter

from app.common.result import Result
from app.service import real_time_stock_service, stock_search_service
from app.database import get_db
from fastapi import Depends

router = APIRouter(tags=["股票搜索接口"])


@router.get("/api/user/stock/search")
def search(keyword: str, db=Depends(get_db)) -> Result:
    """搜索股票（对应 search：代码前缀 + 名称/行业模糊，最多 20 条）。"""
    result = stock_search_service.search(db, keyword)
    return Result.success(result)


@router.get("/api/user/stock/data")
async def get_stock_history(symbol: str, period: str = "D") -> Result:
    """获取股票历史K线数据（对应 getStockHistory：新浪 240/1200/7200 + 腾讯降级）。

    返回结构照抄原 List<Map>：[{date, open, close, high, low, volume}, ...]。
    """
    result = await real_time_stock_service.get_stock_history(symbol, period)
    return Result.success(result)
