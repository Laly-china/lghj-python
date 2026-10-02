"""关注关联表实体。

对应复现原 Java pojo/entity/Follow.java（表 follow）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.pojo.entity.base import SerializationMixin


class Follow(Base, SerializationMixin):
    """关注关联表（user_id 关注 follow_user_id）。"""

    __tablename__ = "follow"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    follow_user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    create_user: Mapped[int | None] = mapped_column(BIGINT)
    update_user: Mapped[int | None] = mapped_column(BIGINT)
    is_deleted: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
