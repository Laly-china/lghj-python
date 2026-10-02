"""A股基础信息表实体。

对应复现原 Java pojo/entity/StockBasic.java（表 stock_basic）。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.pojo.entity.base import SerializationMixin


class StockBasic(Base, SerializationMixin):
    """A股基础信息表（Excel 导入的目标表）。"""

    __tablename__ = "stock_basic"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False)  # 股票代码
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # 股票名称
    short_name: Mapped[str | None] = mapped_column(String(50))  # 股票简称
    total_shares: Mapped[int | None] = mapped_column(BIGINT)  # 总股本（股）
    float_shares: Mapped[int | None] = mapped_column(BIGINT)  # 流通股（股）
    total_market_cap: Mapped[int | None] = mapped_column(BIGINT)  # 总市值（元）
    float_market_cap: Mapped[int | None] = mapped_column(BIGINT)  # 流通市值（元）
    industry: Mapped[str | None] = mapped_column(String(100))  # 所属行业
    market_type: Mapped[int | None] = mapped_column(TINYINT)  # 0未知 1沪A 2深A 3创业板 4科创板 5北交所 6新三板
    list_date: Mapped[date | None] = mapped_column(Date)  # 上市日期
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    create_user: Mapped[str | None] = mapped_column(String(50))
    update_user: Mapped[str | None] = mapped_column(String(50))
    is_deleted: Mapped[int] = mapped_column(TINYINT, nullable=False, default=0)
