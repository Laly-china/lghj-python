"""用户-角色关联表实体。

对应复现原 Java pojo/entity/UserRole.java（表 user_role）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.pojo.entity.base import SerializationMixin


class UserRole(Base, SerializationMixin):
    """用户-角色关联表。"""

    __tablename__ = "user_role"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT, nullable=False)
    role_id: Mapped[int] = mapped_column(nullable=False)  # int
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    create_user: Mapped[int | None] = mapped_column(BIGINT)
    update_user: Mapped[int | None] = mapped_column(BIGINT)
    is_deleted: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
