"""用户自选股表数据访问。

对应复现原 Java mapper/UserStockFollowMapper.java。
"""

from __future__ import annotations

from sqlalchemy import delete, func as sa_func, select
from sqlalchemy.orm import Session

from app.pojo.entity import UserStockFollow


def select_count(db: Session, user_id: int, stock_id: int) -> int:
    """查询关注计数（对应 selectCount(userId+stockId)，用于重复关注兜底判断）。"""
    stmt = (
        select(sa_func.count())
        .select_from(UserStockFollow)
        .where(UserStockFollow.user_id == user_id, UserStockFollow.stock_id == stock_id)
    )
    return int(db.execute(stmt).scalar_one())


def select_list_by_user(db: Session, user_id: int) -> list[UserStockFollow]:
    """查询用户全部关注（对应 selectList(eq(getUserId, userId))）。"""
    stmt = select(UserStockFollow).where(UserStockFollow.user_id == user_id)
    return list(db.execute(stmt).scalars().all())


def insert_follow(db: Session, follow: UserStockFollow) -> bool:
    """插入关注记录（对应 save），返回是否成功。"""
    db.add(follow)
    db.flush()
    return True


def delete_by_user_and_stock(db: Session, user_id: int, stock_id: int) -> int:
    """删除关注记录（对应 remove），返回受影响行数。"""
    stmt = delete(UserStockFollow).where(
        UserStockFollow.user_id == user_id, UserStockFollow.stock_id == stock_id
    )
    result = db.execute(stmt)
    return int(result.rowcount or 0)
