"""博客评论表数据访问。

对应复现原 Java mapper/BlogCommentsMapper.java（MyBatis-Plus BaseMapper）。
全局逻辑删除语义（is_deleted）同 blog_mapper.py 模块说明。
"""

from __future__ import annotations

from sqlalchemy import func as sa_func
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.pojo.entity import BlogComments


def select_by_id(db: Session, comment_id: int) -> BlogComments | None:
    """按主键查询未删除评论（对应 getById）。"""
    stmt = select(BlogComments).where(BlogComments.id == comment_id, BlogComments.is_deleted == 0).limit(1)
    return db.execute(stmt).scalar_one_or_none()


def insert_comment(db: Session, comment: BlogComments) -> bool:
    """插入评论（对应 save），调用方负责 commit。"""
    db.add(comment)
    db.flush()
    return True


def select_first_level_page(
    db: Session, blog_id: int, page_num: int, page_size: int
) -> tuple[list[BlogComments], int]:
    """分页查询一级评论（对应 lambdaQuery：blogId+parentId=0+status=1+isDeleted=0，
    按创建时间倒序），返回 (当前页记录, 总条数)。"""
    conditions = (
        BlogComments.blog_id == blog_id,
        BlogComments.parent_id == 0,
        BlogComments.status == 1,
        BlogComments.is_deleted == 0,
    )
    offset = (max(1, page_num) - 1) * page_size
    stmt = (
        select(BlogComments)
        .where(*conditions)
        .order_by(BlogComments.create_time.desc())
        .offset(offset)
        .limit(page_size)
    )
    records = list(db.execute(stmt).scalars().all())
    total = int(
        db.execute(
            select(sa_func.count()).select_from(BlogComments).where(*conditions)
        ).scalar_one()
    )
    return records, total


def select_second_level(db: Session, blog_id: int, parent_ids: list[int]) -> list[BlogComments]:
    """批量查询二级评论（对应 lambdaQuery：blogId+in(parentIds)+status=1+isDeleted=0，
    按创建时间正序）。"""
    if not parent_ids:
        return []
    stmt = (
        select(BlogComments)
        .where(
            BlogComments.blog_id == blog_id,
            BlogComments.parent_id.in_(parent_ids),
            BlogComments.status == 1,
            BlogComments.is_deleted == 0,
        )
        .order_by(BlogComments.create_time.asc())
    )
    return list(db.execute(stmt).scalars().all())


def select_second_level_by_parent(db: Session, parent_id: int, blog_id: int) -> list[BlogComments]:
    """查询某一级评论下的二级评论（对应 deleteComment 中的
    parentId=commentId+blogId+isDeleted=0，无状态过滤，照抄）。"""
    stmt = select(BlogComments).where(
        BlogComments.parent_id == parent_id,
        BlogComments.blog_id == blog_id,
        BlogComments.is_deleted == 0,
    )
    return list(db.execute(stmt).scalars().all())


def change_liked(db: Session, comment_id: int, liked_value: int) -> bool:
    """更新点赞数（对应 lambdaUpdate().set(getLiked, value).eq(getId, id).update()）。

    原实现为绝对值赋值（取自更新前查出的评论.liked ± 1），非原子自增，照抄；
    逻辑删除语义下 WHERE 隐式追加 is_deleted = 0。
    """
    stmt = (
        update(BlogComments)
        .where(BlogComments.id == comment_id, BlogComments.is_deleted == 0)
        .values(liked=liked_value)
    )
    result = db.execute(stmt)
    return bool(result.rowcount and result.rowcount > 0)


def logic_delete_by_ids(db: Session, comment_ids: list[int]) -> bool:
    """批量逻辑删除（对应 removeByIds），返回受影响行数 > 0。"""
    if not comment_ids:
        return False
    stmt = (
        update(BlogComments)
        .where(BlogComments.id.in_(comment_ids), BlogComments.is_deleted == 0)
        .values(is_deleted=1)
    )
    result = db.execute(stmt)
    return bool(result.rowcount and result.rowcount > 0)


def logic_delete_by_id(db: Session, comment_id: int) -> bool:
    """逻辑删除单条（对应 removeById）。"""
    return logic_delete_by_ids(db, [comment_id])


def select_page_all(
    db: Session, page_num: int, page_size: int, blog_id: int | None = None
) -> tuple[list[BlogComments], int]:
    """管理端分页查询评论（对应 page(page, wrapper)：可选 blogId 过滤，
    按创建时间倒序），返回 (当前页记录, 总条数)。"""
    conditions = [BlogComments.is_deleted == 0]
    if blog_id is not None:
        conditions.append(BlogComments.blog_id == blog_id)
    offset = (max(1, page_num) - 1) * page_size
    stmt = (
        select(BlogComments)
        .where(*conditions)
        .order_by(BlogComments.create_time.desc())
        .offset(offset)
        .limit(page_size)
    )
    records = list(db.execute(stmt).scalars().all())
    total = int(
        db.execute(
            select(sa_func.count()).select_from(BlogComments).where(*conditions)
        ).scalar_one()
    )
    return records, total
