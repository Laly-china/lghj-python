"""用户表数据访问。

对应复现原 Java mapper/UserMapper.java（MyBatis-Plus BaseMapper）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.pojo.entity import User


def select_one_by_username(db: Session, username: str) -> User | None:
    """按用户名查询（对应 selectOne(eq(User::getUsername, username))）。"""
    stmt = select(User).where(User.username == username).limit(1)
    return db.execute(stmt).scalar_one_or_none()


def select_count_by_username(db: Session, username: str) -> int:
    """按用户名计数（对应 selectCount，用于注册查重）。"""
    from sqlalchemy import func as sa_func

    stmt = select(sa_func.count()).select_from(User).where(User.username == username)
    return int(db.execute(stmt).scalar_one())


def insert_user(db: Session, user: User) -> int:
    """插入用户，返回受影响行数（对应 baseMapper.insert）。"""
    db.add(user)
    db.flush()
    return 1
