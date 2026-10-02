"""博客表实体。

对应复现原 Java pojo/entity/Blog.java（表 blog）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.mysql import BIGINT, INTEGER, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.pojo.entity.base import SerializationMixin


class Blog(Base, SerializationMixin):
    """博客表。"""

    __tablename__ = "blog"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    stock_id: Mapped[str | None] = mapped_column(String(255))  # 关联股票代码，多个用","隔开
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    images: Mapped[str | None] = mapped_column(String(2048))  # 最多9张，多张以","隔开
    context: Mapped[str] = mapped_column(String(2048), nullable=False)
    liked: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0)
    comments: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0)
    status: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=1)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    create_user: Mapped[int | None] = mapped_column(BIGINT)
    update_user: Mapped[int | None] = mapped_column(BIGINT)
    is_deleted: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
