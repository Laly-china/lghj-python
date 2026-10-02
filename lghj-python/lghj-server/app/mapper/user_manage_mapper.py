"""管理端用户表数据访问（分页条件查询/按ID更新/逻辑删除）。

对应复现原 Java mapper/UserMapper.java（MyBatis-Plus BaseMapper<User>）在
UserServiceImpl 中用到的高级查询；基础查询复用 user_mapper.py。
全局逻辑删除语义（is_deleted）同 blog_mapper.py 模块说明。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func as sa_func
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.pojo.dto.user_manage_dtos import UserQueryDTO
from app.pojo.entity import User


def select_page_by_condition(
    db: Session, current: int, size: int, q: UserQueryDTO | None
) -> tuple[list[User], int]:
    """分页条件查询用户（对应 queryUserPage 的 wrapper + selectPage）。

    条件逐条照抄：
    - username/email/phone 为 hasText 时 LIKE
    - sex/userType/status/isDeleted 非 null 时 eq
    - begin/end 非 null 时对 update_time 的 ge/le（调用方须先在 service 层把
      字符串解析为 datetime 后回填 DTO）
    - 固定按 update_time 倒序
    注意：全局逻辑删除额外隐式追加 is_deleted=0（若查询参数同时传 isDeleted=1
    则两条件相与，结果为空——原系统行为照抄）。
    """
    conditions = [User.is_deleted == 0]
    if q is not None:
        if _has_text(q.username):
            conditions.append(User.username.like(f"%{q.username}%"))
        if _has_text(q.email):
            conditions.append(User.email.like(f"%{q.email}%"))
        if _has_text(q.phone):
            conditions.append(User.phone.like(f"%{q.phone}%"))
        if q.sex is not None:
            conditions.append(User.sex == q.sex)
        if q.userType is not None:  # noqa: N815
            conditions.append(User.user_type == q.userType)
        if q.status is not None:
            conditions.append(User.status == q.status)
        if q.isDeleted is not None:  # noqa: N815
            conditions.append(User.is_deleted == q.isDeleted)
        if q.begin is not None:
            conditions.append(User.update_time >= q.begin)
        if q.end is not None:
            conditions.append(User.update_time <= q.end)

    offset = (max(1, current) - 1) * size
    stmt = (
        select(User)
        .where(*conditions)
        .order_by(User.update_time.desc())
        .offset(offset)
        .limit(size)
    )
    records = list(db.execute(stmt).scalars().all())
    total = int(
        db.execute(select(sa_func.count()).select_from(User).where(*conditions)).scalar_one()
    )
    return records, total


def select_by_id(db: Session, user_id: int) -> User | None:
    """按主键查询未删除用户（对应 baseMapper.selectById，逻辑删除自动过滤）。"""
    stmt = select(User).where(User.id == user_id, User.is_deleted == 0).limit(1)
    return db.execute(stmt).scalar_one_or_none()


def select_by_ids(db: Session, user_ids: list[int]) -> list[User]:
    """按 id 集合批量查询未删除用户（对应 listByIds，逻辑删除自动过滤）。"""
    if not user_ids:
        return []
    stmt = select(User).where(User.id.in_(user_ids), User.is_deleted == 0)
    return list(db.execute(stmt).scalars().all())


def update_user_fields(db: Session, user_id: int, values: dict) -> bool:
    """按主键更新非空字段（对应 updateById + update-strategy: not_null），
    返回受影响行数 > 0。"""
    if not values:
        return False
    stmt = update(User).where(User.id == user_id, User.is_deleted == 0).values(**values)
    result = db.execute(stmt)
    return bool(result.rowcount and result.rowcount > 0)


def logic_delete_by_id(db: Session, user_id: int) -> bool:
    """逻辑删除用户（对应 baseMapper.deleteById + @TableLogic 语义）。"""
    stmt = update(User).where(User.id == user_id, User.is_deleted == 0).values(is_deleted=1)
    result = db.execute(stmt)
    return bool(result.rowcount and result.rowcount > 0)


def insert_user(db: Session, user: User) -> bool:
    """插入用户（对应 this.save(user)），调用方负责 commit。"""
    db.add(user)
    db.flush()
    return True


def _has_text(value: str | None) -> bool:
    """对应 Spring StringUtils.hasText：非 null 且含非空白字符。"""
    return value is not None and value.strip() != ""
