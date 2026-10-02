"""角色-权限关联表实体。

说明：init.sql 中存在该表（role_permission），但原 Java 未建对应实体类，
本工程按建表脚本补齐模型（表结构逐字段对照），供后续任务使用。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.pojo.entity.base import SerializationMixin


class RolePermission(Base, SerializationMixin):
    """角色-权限关联表（原 Java 无实体，按 init.sql 补齐）。"""

    __tablename__ = "role_permission"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(nullable=False)  # int
    permission: Mapped[int] = mapped_column(nullable=False)  # int
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    create_user: Mapped[int | None] = mapped_column(BIGINT)
    update_user: Mapped[int | None] = mapped_column(BIGINT)
    is_deleted: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
