"""成交记录表实体。

对应复现原 Java pojo/entity/TradeDeal.java（表 trade_deal）。
Phase 1 仅建模，不实现交易业务（归后续任务）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.mysql import BIGINT, DECIMAL, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.pojo.entity.base import SerializationMixin


class TradeDeal(Base, SerializationMixin):
    """成交记录表（一笔委托单可能对应多笔成交）。"""

    __tablename__ = "trade_deal"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    deal_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # 成交单号
    order_id: Mapped[int] = mapped_column(BIGINT, nullable=False)  # 关联委托单ID
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    deal_direction: Mapped[int] = mapped_column(TINYINT, nullable=False)  # 1买入 2卖出
    price: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    create_user: Mapped[str | None] = mapped_column(String(50))
    update_user: Mapped[str | None] = mapped_column(String(50))
    is_deleted: Mapped[int] = mapped_column(TINYINT, nullable=False, default=0)
