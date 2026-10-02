"""资金流水表实体。

对应复现原 Java pojo/entity/AccountFlow.java（表 account_flow）。
Phase 1 仅建模，不实现交易业务（归后续任务）。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.mysql import BIGINT, DECIMAL, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.pojo.entity.base import SerializationMixin


class AccountFlow(Base, SerializationMixin):
    """资金流水表。"""

    __tablename__ = "account_flow"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    flow_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)  # 流水单号
    user_id: Mapped[int] = mapped_column(BIGINT, nullable=False)
    account_id: Mapped[int] = mapped_column(BIGINT, nullable=False)
    flow_type: Mapped[int] = mapped_column(TINYINT, nullable=False)  # 1充值 2提现 3买入扣款 4卖出回款 5手续费 6调账
    amount: Mapped[Decimal] = mapped_column(DECIMAL(16, 2), nullable=False)  # 正增负减
    balance_after: Mapped[Decimal] = mapped_column(DECIMAL(16, 2), nullable=False)  # 变动后可用余额
    related_no: Mapped[str | None] = mapped_column(String(32))  # 关联单号
    remark: Mapped[str | None] = mapped_column(String(200))
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    create_user: Mapped[str | None] = mapped_column(String(50))
    update_user: Mapped[str | None] = mapped_column(String(50))
    is_deleted: Mapped[int] = mapped_column(TINYINT, nullable=False, default=0)
