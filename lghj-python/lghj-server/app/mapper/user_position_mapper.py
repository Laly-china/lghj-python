"""用户持仓表数据访问。

对应复现原 Java mapper/UserPositionMapper.java。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.pojo.entity import UserPosition


def select_list_by_user(db: Session, user_id: int) -> list[UserPosition]:
    """查询用户全部未删除持仓（对应 selectList(userId+isDeleted=0)）。"""
    stmt = select(UserPosition).where(
        UserPosition.user_id == user_id, UserPosition.is_deleted == 0
    )
    return list(db.execute(stmt).scalars().all())


def select_one_by_user_and_symbol(db: Session, user_id: int, symbol: str) -> UserPosition | None:
    """查询用户对特定股票的未删除持仓（对应 selectOne(userId+symbol+isDeleted=0)）。"""
    stmt = (
        select(UserPosition)
        .where(
            UserPosition.user_id == user_id,
            UserPosition.symbol == symbol,
            UserPosition.is_deleted == 0,
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()
