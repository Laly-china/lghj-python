"""用户-角色关联表数据访问。

对应复现原 Java：
- mapper/UserRoleMapper.java（MyBatis-Plus BaseMapper<UserRole>）
- service/impl/UserRoleServiceImpl.java 的 save/getOne/remove/updateById 语义

全局逻辑删除语义（is_deleted）同 blog_mapper.py 模块说明。
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.pojo.entity import UserRole


def insert_user_role(db: Session, user_role: UserRole) -> bool:
    """插入关联记录（对应 userRoleService.save(userRole)），调用方负责 commit。"""
    db.add(user_role)
    db.flush()
    return True


def select_one_by_user_id(db: Session, user_id: int) -> UserRole | None:
    """按用户ID查询关联记录（对应 getOne(new LambdaQueryWrapper<>()
    .select(UserRole::getId).eq(UserRole::getUserId, userId))，逻辑删除自动过滤）。"""
    stmt = select(UserRole).where(UserRole.user_id == user_id, UserRole.is_deleted == 0).limit(1)
    return db.execute(stmt).scalar_one_or_none()


def update_role_id(db: Session, user_role_id: int, role_id: int) -> bool:
    """更新角色ID（对应 userRoleService.updateById(userRole)），返回是否成功。"""
    stmt = (
        update(UserRole)
        .where(UserRole.id == user_role_id, UserRole.is_deleted == 0)
        .values(role_id=role_id)
    )
    result = db.execute(stmt)
    return bool(result.rowcount and result.rowcount > 0)


def logic_delete_by_user_id(db: Session, user_id: int) -> bool:
    """按用户ID逻辑删除关联记录（对应 userRoleService.remove(queryWrapper)），
    返回受影响行数 > 0。"""
    stmt = (
        update(UserRole)
        .where(UserRole.user_id == user_id, UserRole.is_deleted == 0)
        .values(is_deleted=1)
    )
    result = db.execute(stmt)
    return bool(result.rowcount and result.rowcount > 0)
