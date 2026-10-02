"""用户交易操作接口路由。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/user/TradeController.java

接口契约（照抄，均在 /api/user/** 拦截范围内，需携带 token 请求头）：
- POST /api/user/trade/order         下单（query 参数 symbol/direction/price/quantity，
                                      direction 1-买 2-卖；quantity 单位为手，×100 股）
- POST /api/user/trade/cancel        撤单（query 参数 orderId；失败返回 code=500 "撤销失败"）
- GET  /api/user/trade/query_orders  获取用户委托单列表（按创建时间倒序）
- GET  /api/user/trade/query_deals   获取用户成交记录列表（按创建时间倒序）
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.context import BaseContext
from app.common.result import Result
from app.database import get_db
from app.service.trade.trade_service import trade_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["交易操作接口"])


@router.post("/api/user/trade/order")
def create_order(
    symbol: str,
    direction: int,   # 1-买，2-卖（原 Short direction）
    price: float,
    quantity: int,    # 数量（原 int quantity，单位：手）
    db: Session = Depends(get_db),
) -> Result:
    """创建委托单（对应 createOrder）。"""
    user_id = BaseContext.get_current_id()
    logger.info(
        "创建委托单: userId=%s, symbol=%s, direction=%s, price=%s, quantity=%s",
        user_id, symbol, direction, price, quantity,
    )
    order = trade_service.create_order(db, user_id, symbol, direction, price, quantity)
    return Result.success(order)


@router.post("/api/user/trade/cancel")
def cancel_order(order_id: int = Query(alias="orderId"), db: Session = Depends(get_db)) -> Result:
    """撤销委托单（对应 cancelOrder，query 参数名照原 Java 为 orderId）。"""
    user_id = BaseContext.get_current_id()
    logger.info("撤销委托单: orderId=%s, userId=%s", order_id, user_id)
    result = trade_service.cancel_order(db, order_id, user_id)
    return Result.success() if result else Result.error("撤销失败")


@router.get("/api/user/trade/query_orders")
def get_user_orders(db: Session = Depends(get_db)) -> Result:
    """获取用户委托单列表（对应 getUserOrders）。"""
    user_id = BaseContext.get_current_id()
    logger.info("获取用户委托单列表: userId=%s", user_id)
    orders = trade_service.get_user_orders(db, user_id)
    return Result.success(orders)


@router.get("/api/user/trade/query_deals")
def get_user_deals(db: Session = Depends(get_db)) -> Result:
    """获取用户成交记录列表（对应 getUserDeals）。"""
    user_id = BaseContext.get_current_id()
    logger.info("获取用户成交记录列表: userId=%s", user_id)
    deals = trade_service.get_user_deals(db, user_id)
    return Result.success(deals)
