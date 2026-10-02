"""模拟账户表实体。

对应复现原 Java pojo/entity/SimAccount.java（表 sim_account）。
version 为乐观锁字段（原 MyBatis-Plus @Version），保留。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.mysql import BIGINT, DECIMAL, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.pojo.entity.base import SerializationMixin


class SimAccount(Base, SerializationMixin):
    """模拟账户表。"""

    __tablename__ = "sim_account"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    total_cash: Mapped[Decimal] = mapped_column(DECIMAL(16, 2), nullable=False, default="200000.00")
    available_cash: Mapped[Decimal] = mapped_column(DECIMAL(16, 2), nullable=False, default="200000.00")
    frozen_cash: Mapped[Decimal] = mapped_column(DECIMAL(16, 2), nullable=False, default="0.00")
    total_asset: Mapped[Decimal] = mapped_column(DECIMAL(16, 2), nullable=False, default="200000.00")
    version: Mapped[int] = mapped_column(nullable=False, default=0)  # 乐观锁版本号
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    create_user: Mapped[str | None] = mapped_column(String(50))
    update_user: Mapped[str | None] = mapped_column(String(50))
    is_deleted: Mapped[int] = mapped_column(TINYINT, nullable=False, default=0)
