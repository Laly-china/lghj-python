"""用户自选股表实体。

对应复现原 Java pojo/entity/UserStockFollow.java（表 user_stock_follow）。
注意：该表无 update_time/update_user/is_deleted 字段，唯一键 (user_id, stock_id)。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.pojo.entity.base import SerializationMixin


class UserStockFollow(Base, SerializationMixin):
    """用户自选股表。"""

    __tablename__ = "user_stock_follow"
    __table_args__ = (
        UniqueConstraint("user_id", "stock_id", name="idx_user_stock"),  # 用户不能重复关注同一只股票
        {"comment": "用户自选股表"},
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT, nullable=False)
    stock_id: Mapped[int] = mapped_column(BIGINT, nullable=False)  # 股票基础信息ID
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)  # 股票代码(冗余)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())  # 关注时间
