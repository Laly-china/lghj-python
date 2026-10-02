"""模拟账户表数据访问。

对应复现原 Java mapper/SimAccountMapper.java。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.pojo.entity import SimAccount


def select_one_by_user_id(db: Session, user_id: int) -> SimAccount | None:
    """按用户ID查询未删除账户（对应 getOne(eq(getUserId)+eq(getIsDeleted,0))）。"""
    stmt = (
        select(SimAccount)
        .where(SimAccount.user_id == user_id, SimAccount.is_deleted == 0)
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def insert_account(db: Session, account: SimAccount) -> bool:
    """插入模拟账户（对应 save），返回是否成功。"""
    db.add(account)
    db.flush()
    return True
