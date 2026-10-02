"""角色表实体。

对应复现原 Java pojo/entity/Role.java（表 role）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.pojo.entity.base import SerializationMixin


class Role(Base, SerializationMixin):
    """角色表。"""

    __tablename__ = "role"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)  # int
    role_name: Mapped[str] = mapped_column(String(20), nullable=False)
    role_desc: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=1)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    create_user: Mapped[int | None] = mapped_column(BIGINT)
    update_user: Mapped[int | None] = mapped_column(BIGINT)
    is_deleted: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
