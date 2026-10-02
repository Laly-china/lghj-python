"""委托单表实体。

对应复现原 Java pojo/entity/TradeOrder.java（表 trade_order）。
Phase 1 仅建模，不实现交易业务（归后续任务）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.mysql import BIGINT, DECIMAL, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.pojo.entity.base import SerializationMixin


class TradeOrder(Base, SerializationMixin):
    """委托单表。"""

    __tablename__ = "trade_order"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # 委托单号
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    direction: Mapped[int | None] = mapped_column(TINYINT)  # 买/卖（1-买，2-卖）
    price: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)  # 委托价格
    quantity: Mapped[int] = mapped_column(nullable=False)  # 委托数量（股）
    traded_quantity: Mapped[int] = mapped_column(nullable=False)  # 已成交数量
    status: Mapped[int] = mapped_column(TINYINT, nullable=False, default=1)  # 1待定 2部分完成 3已完成
    cancel_time: Mapped[datetime | None] = mapped_column(DateTime)  # 撤销时间
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    create_user: Mapped[str | None] = mapped_column(String(50))
    update_user: Mapped[str | None] = mapped_column(String(50))
    is_deleted: Mapped[int] = mapped_column(TINYINT, nullable=False, default=0)
