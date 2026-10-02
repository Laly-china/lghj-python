"""自选股管理接口路由。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/user/OptionalStockController.java

接口契约（照抄；symbol 均为 **query string** 传参（原 @RequestParam），
均在 /api/user/** 拦截范围内，需携带 token 请求头）：
- POST /api/user/optional/add?symbol=    添加自选股
- POST /api/user/optional/remove?symbol= 删除自选股
- GET  /api/user/optional/list           获取自选股列表（带实时行情）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.context import BaseContext
from app.common.result import Result
from app.database import get_db
from app.service import user_stock_follow_service

router = APIRouter(tags=["自选股管理接口"])


@router.post("/api/user/optional/add")
def add(symbol: str, db: Session = Depends(get_db)) -> Result:
    """添加自选股（对应 add）。"""
    user_id = BaseContext.get_current_id()
    success = user_stock_follow_service.add_follow(db, user_id, symbol)
    return Result.success() if success else Result.error("添加失败，可能股票不存在")


@router.post("/api/user/optional/remove")
def remove(symbol: str, db: Session = Depends(get_db)) -> Result:
    """删除自选股（对应 remove）。"""
    user_id = BaseContext.get_current_id()
    success = user_stock_follow_service.remove_follow(db, user_id, symbol)
    return Result.success() if success else Result.error("删除失败")


@router.get("/api/user/optional/list")
async def list_followed(db: Session = Depends(get_db)) -> Result:
    """获取自选股列表（对应 list，VO 填充实时行情）。"""
    user_id = BaseContext.get_current_id()
    result = await user_stock_follow_service.get_user_follow_list(db, user_id)
    return Result.success(result)
