"""博客评论表实体。

对应复现原 Java pojo/entity/BlogComments.java（表 blog_comments）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.mysql import BIGINT, INTEGER, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.pojo.entity.base import SerializationMixin


class BlogComments(Base, SerializationMixin):
    """博客评论表。"""

    __tablename__ = "blog_comments"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    blog_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    parent_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), default=0)  # 1级评论为0
    content: Mapped[str] = mapped_column(String(255), nullable=False)
    liked: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0)
    status: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=1)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    create_user: Mapped[int | None] = mapped_column(BIGINT)
    update_user: Mapped[int | None] = mapped_column(BIGINT)
    is_deleted: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
