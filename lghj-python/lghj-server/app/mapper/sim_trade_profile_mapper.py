"""模拟交易画像专用只读数据访问（trade_order / trade_deal）。

对应复现原 Java：
- service/impl/TradeServiceImpl.getUserOrders / getUserDeals 中的查询语义
  （注意：本文件只复现这两处只读查询，供内部 API 交易画像统计使用；
  交易引擎本身归并行任务B，严禁在本文件实现任何交易写操作）。

全局逻辑删除语义：SELECT 隐式过滤 is_deleted = 0（原 TradeOrder/TradeDeal
实体带 @TableLogic），此处显式写出等价条件。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.pojo.entity import TradeDeal, TradeOrder


def select_orders_by_user(db: Session, user_id: int) -> list[TradeOrder]:
    """查询用户全部订单（对应 getUserOrders：userId + isDeleted=0，
    按创建时间倒序）。"""
    stmt = (
        select(TradeOrder)
        .where(TradeOrder.user_id == user_id, TradeOrder.is_deleted == 0)
        .order_by(TradeOrder.create_time.desc())
    )
    return list(db.execute(stmt).scalars().all())


def select_deals_by_user(db: Session, user_id: int) -> list[TradeDeal]:
    """查询用户全部成交记录（对应 getUserDeals：userId + isDeleted=0，
    按创建时间倒序）。"""
    stmt = (
        select(TradeDeal)
        .where(TradeDeal.user_id == user_id, TradeDeal.is_deleted == 0)
        .order_by(TradeDeal.create_time.desc())
    )
    return list(db.execute(stmt).scalars().all())
