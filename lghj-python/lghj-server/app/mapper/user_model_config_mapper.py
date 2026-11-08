"""用户自配大模型配置表数据访问。

Python 复现扩展功能（非原 Java mapper），纯函数风格对齐 user_stock_follow_mapper。
"""

from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.pojo.entity import UserModelConfig


def select_list_by_user(db: Session, user_id: int) -> list[UserModelConfig]:
    """查询用户全部配置（按创建时间升序）。"""
    stmt = (
        select(UserModelConfig)
        .where(UserModelConfig.user_id == user_id)
        .order_by(UserModelConfig.id)
    )
    return list(db.execute(stmt).scalars().all())


def select_by_user_and_name(db: Session, user_id: int, name: str) -> UserModelConfig | None:
    """按 (userId, name) 查单条配置。"""
    stmt = select(UserModelConfig).where(
        UserModelConfig.user_id == user_id, UserModelConfig.name == name
    )
    return db.execute(stmt).scalars().first()


def select_active_by_user(db: Session, user_id: int) -> UserModelConfig | None:
    """查询用户当前激活的配置（至多一条）。"""
    stmt = select(UserModelConfig).where(
        UserModelConfig.user_id == user_id, UserModelConfig.is_active == 1
    )
    return db.execute(stmt).scalars().first()


def insert_config(db: Session, config: UserModelConfig) -> None:
    """插入配置（不 commit，由 service 层提交）。"""
    db.add(config)
    db.flush()


def clear_active_by_user(db: Session, user_id: int) -> None:
    """将该用户全部配置置为非激活（activate 前置操作）。"""
    stmt = (
        update(UserModelConfig)
        .where(UserModelConfig.user_id == user_id)
        .values(is_active=0)
    )
    db.execute(stmt)


def delete_by_user_and_name(db: Session, user_id: int, name: str) -> int:
    """删除配置，返回受影响行数。"""
    stmt = delete(UserModelConfig).where(
        UserModelConfig.user_id == user_id, UserModelConfig.name == name
    )
    result = db.execute(stmt)
    return int(result.rowcount or 0)
