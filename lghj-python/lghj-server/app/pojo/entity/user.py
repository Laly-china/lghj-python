"""用户表实体。

对应复现原 Java pojo/entity/User.java（表 user，见 sql/数据库初始化-init.sql）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.pojo.entity.base import SerializationMixin


class User(Base, SerializationMixin):
    """用户表（原 @TableName("`user`")，JSON 输出驼峰字段）。"""

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(100), nullable=False)
    nick_name: Mapped[str | None] = mapped_column(String(32))
    icon: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20))
    sex: Mapped[int | None] = mapped_column(TINYINT(unsigned=True))  # 性别（1: 男，2: 女）
    user_type: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False)  # 1普通 2机构 3管理员
    status: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=1)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    create_user: Mapped[int | None] = mapped_column(BIGINT)
    update_user: Mapped[int | None] = mapped_column(BIGINT)
    is_deleted: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
