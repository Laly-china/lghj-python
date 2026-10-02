"""账户管理接口路由。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/user/AccountController.java

接口契约（照抄，均在 /api/user/** 拦截范围内，需携带 token 请求头）：
- POST /api/user/account/create          创建模拟账户（初始资金 200000.00）
- GET  /api/user/account/query_info      获取账户信息（不存在返回 code=500 "账户不存在"）
- GET  /api/user/account/query_positions 获取持仓列表
- GET  /api/user/account/query_position  获取特定股票持仓（query 参数 symbol）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.context import BaseContext
from app.common.result import Result
from app.database import get_db
from app.service import account_service

router = APIRouter(tags=["账户管理接口"])


@router.post("/api/user/account/create")
def create_account(db: Session = Depends(get_db)) -> Result:
    """创建模拟账户（对应 createAccount）。"""
    user_id = BaseContext.get_current_id()
    account = account_service.create_account(db, user_id)
    return Result.success(account)


@router.get("/api/user/account/query_info")
def get_account_info(db: Session = Depends(get_db)) -> Result:
    """获取账户信息（对应 getAccountInfo）。"""
    user_id = BaseContext.get_current_id()
    account = account_service.get_account_by_user_id(db, user_id)
    return Result.success(account) if account is not None else Result.error("账户不存在")


@router.get("/api/user/account/query_positions")
def get_positions(db: Session = Depends(get_db)) -> Result:
    """获取持仓列表（对应 getPositions）。"""
    user_id = BaseContext.get_current_id()
    positions = account_service.get_user_positions(db, user_id)
    return Result.success(positions)


@router.get("/api/user/account/query_position")
def get_position(symbol: str, db: Session = Depends(get_db)) -> Result:
    """获取特定股票持仓（对应 getPosition，query 参数 symbol）。"""
    user_id = BaseContext.get_current_id()
    position = account_service.get_user_position_by_symbol(db, user_id, symbol)
    return Result.success(position) if position is not None else Result.error("持仓不存在")
