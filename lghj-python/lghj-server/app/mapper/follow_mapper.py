"""关注关联表数据访问。

对应复现原 Java mapper/FollowMapper.java（MyBatis-Plus BaseMapper）。
全局逻辑删除语义（is_deleted）同 blog_mapper.py 模块说明。
"""

from __future__ import annotations

from sqlalchemy import func as sa_func
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.pojo.entity import Follow


def insert_follow(db: Session, follow: Follow) -> bool:
    """插入关注记录（对应 save），调用方负责 commit。"""
    db.add(follow)
    db.flush()
    return True


def delete_by_user_and_follow(db: Session, user_id: int, follow_user_id: int) -> bool:
    """取关（对应 remove(new QueryWrapper<>().eq("user_id",...).eq("follow_user_id",...))）。

    全局逻辑删除语义：UPDATE follow SET is_deleted=1
    WHERE user_id=? AND follow_user_id=? AND is_deleted=0，返回受影响行数 > 0。
    """
    stmt = (
        update(Follow)
        .where(
            Follow.user_id == user_id,
            Follow.follow_user_id == follow_user_id,
            Follow.is_deleted == 0,
        )
        .values(is_deleted=1)
    )
    result = db.execute(stmt)
    return bool(result.rowcount and result.rowcount > 0)


def count_by_user_and_follow(db: Session, user_id: int, follow_user_id: int) -> int:
    """计数（对应 query().eq("user_id",...).eq("follow_user_id",...).count()）。"""
    stmt = (
        select(sa_func.count())
        .select_from(Follow)
        .where(
            Follow.user_id == user_id,
            Follow.follow_user_id == follow_user_id,
            Follow.is_deleted == 0,
        )
    )
    return int(db.execute(stmt).scalar_one())


def select_list_by_follow_user_id(db: Session, follow_user_id: int) -> list[Follow]:
    """查询关注了指定用户的所有记录（粉丝列表，对应
    query().eq("follow_user_id", userId).list()，逻辑删除自动过滤）。"""
    stmt = select(Follow).where(
        Follow.follow_user_id == follow_user_id, Follow.is_deleted == 0
    )
    return list(db.execute(stmt).scalars().all())
