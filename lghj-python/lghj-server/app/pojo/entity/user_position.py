"""用户持仓表实体。

对应复现原 Java pojo/entity/UserPosition.java（表 user_position）。
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


class UserPosition(Base, SerializationMixin):
    """用户持仓表。"""

    __tablename__ = "user_position"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    account_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    total_quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    frozen_quantity: Mapped[int] = mapped_column(nullable=False, default=0)  # 冻结数量（待卖出）
    available_quantity: Mapped[int] = mapped_column(nullable=False, default=0)  # 可用数量
    cost_price: Mapped[Decimal] = mapped_column(DECIMAL(16, 2), nullable=False, default="0.00")
    profit_loss: Mapped[Decimal] = mapped_column(DECIMAL(16, 2), nullable=False, default="0.00")
    version: Mapped[int] = mapped_column(nullable=False, default=0)  # 乐观锁版本号
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    create_user: Mapped[str | None] = mapped_column(String(50))
    update_user: Mapped[str | None] = mapped_column(String(50))
    is_deleted: Mapped[int] = mapped_column(TINYINT, nullable=False, default=0)
