"""博客表数据访问。

对应复现原 Java mapper/BlogMapper.java（MyBatis-Plus BaseMapper<Blog>）。

重要：原工程 application-dev.yml 配置了全局逻辑删除
（global-config.db-config.logic-delete-field: isDeleted），故所有自动生成的
SELECT 均隐式追加 is_deleted = 0，removeById 为 UPDATE is_deleted = 1。
本文件所有查询/更新/删除均按该语义实现。
"""

from __future__ import annotations

from sqlalchemy import func as sa_func
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.pojo.entity import Blog


def select_by_id(db: Session, blog_id: int) -> Blog | None:
    """按主键查询未删除博客（对应 getById，逻辑删除自动过滤）。"""
    stmt = select(Blog).where(Blog.id == blog_id, Blog.is_deleted == 0).limit(1)
    return db.execute(stmt).scalar_one_or_none()


def select_page_by_user(db: Session, user_id: int, current: int, size: int) -> list[Blog]:
    """按用户查询博客（分页，对应 query().eq("user_id", userId).page(...)）。

    原 MP 未指定排序，返回 MySQL 默认顺序；此处同样不加 order by。
    """
    offset = (max(1, current) - 1) * size
    stmt = (
        select(Blog)
        .where(Blog.user_id == user_id, Blog.is_deleted == 0)
        .offset(offset)
        .limit(size)
    )
    return list(db.execute(stmt).scalars().all())


def select_page_hot(db: Session, current: int, size: int) -> list[Blog]:
    """按点赞数倒序分页（对应 queryHotBlog 的 orderByDesc("liked").page(...)）。"""
    offset = (max(1, current) - 1) * size
    stmt = (
        select(Blog)
        .where(Blog.is_deleted == 0)
        .order_by(Blog.liked.desc())
        .offset(offset)
        .limit(size)
    )
    return list(db.execute(stmt).scalars().all())


def select_page_all(db: Session, current: int, size: int) -> list[Blog]:
    """无条件分页（对应管理端 blogService.page(page)，无 wrapper 无排序）。"""
    offset = (max(1, current) - 1) * size
    stmt = select(Blog).where(Blog.is_deleted == 0).offset(offset).limit(size)
    return list(db.execute(stmt).scalars().all())


def count_all(db: Session) -> int:
    """无条件计数（对应管理端分页的 count 查询）。"""
    stmt = select(sa_func.count()).select_from(Blog).where(Blog.is_deleted == 0)
    return int(db.execute(stmt).scalar_one())


def select_by_ids_keep_order(db: Session, blog_ids: list[int]) -> list[Blog]:
    """按 id 集合查询并保持传入顺序（对应 Feed 流的 in + ORDER BY FIELD(id, ...)）。

    原 Java：query().in("id", blogIds).last("ORDER BY FIELD(id, " + idStr + ")").list()
    使用 MySQL FIELD 函数按 Redis ZSet 返回顺序排序；ids 为已解析的 int，无注入风险。
    """
    if not blog_ids:
        return []
    stmt = (
        select(Blog)
        .where(Blog.id.in_(blog_ids), Blog.is_deleted == 0)
        .order_by(sa_func.field(Blog.id, *blog_ids))
    )
    return list(db.execute(stmt).scalars().all())


def insert_blog(db: Session, blog: Blog) -> bool:
    """插入博客（对应 save），调用方负责 commit。"""
    db.add(blog)
    db.flush()
    return True


def change_liked(db: Session, blog_id: int, delta: int) -> bool:
    """点赞数原子增减（对应 update().setSql("liked = liked + 1").eq("id", id).update()）。

    返回受影响行数 > 0；逻辑删除语义下 WHERE 隐式追加 is_deleted = 0。
    """
    stmt = (
        update(Blog)
        .where(Blog.id == blog_id, Blog.is_deleted == 0)
        .values(liked=Blog.liked + delta)
    )
    result = db.execute(stmt)
    return bool(result.rowcount and result.rowcount > 0)


def update_blog_fields(db: Session, blog_id: int, values: dict) -> bool:
    """按主键更新非空字段（对应 updateById + update-strategy: not_null）。

    逻辑删除语义下 WHERE 追加 is_deleted = 0；返回受影响行数 > 0。
    """
    if not values:
        return False
    stmt = update(Blog).where(Blog.id == blog_id, Blog.is_deleted == 0).values(**values)
    result = db.execute(stmt)
    return bool(result.rowcount and result.rowcount > 0)


def logic_delete_by_id(db: Session, blog_id: int) -> bool:
    """逻辑删除（对应 removeById：UPDATE is_deleted=1 WHERE id=? AND is_deleted=0）。"""
    stmt = (
        update(Blog)
        .where(Blog.id == blog_id, Blog.is_deleted == 0)
        .values(is_deleted=1)
    )
    result = db.execute(stmt)
    return bool(result.rowcount and result.rowcount > 0)
