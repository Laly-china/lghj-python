"""成交记录表数据访问。

对应复现原 Java mapper/TradeDealMapper.java（MyBatis-Plus BaseMapper）+ TradeServiceImpl
内联的查询构造。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.pojo.entity import TradeDeal


def insert_deal(db: Session, deal: TradeDeal) -> bool:
    """插入成交记录（对应 tradeDealMapper.insert），flush 后回填自增主键 id。"""
    db.add(deal)
    db.flush()
    return True


def select_user_deals(db: Session, user_id: int) -> list[TradeDeal]:
    """用户成交记录列表：userId + isDeleted=0，按创建时间倒序（对应 getUserDeals）。"""
    stmt = (
        select(TradeDeal)
        .where(TradeDeal.user_id == user_id, TradeDeal.is_deleted == 0)
        .order_by(TradeDeal.create_time.desc())
    )
    return list(db.execute(stmt).scalars().all())


def select_deal_page(
    db: Session,
    page_num: int,
    page_size: int,
    user_id: int | None = None,
    symbol: str | None = None,
) -> tuple[list[TradeDeal], int]:
    """分页查询成交记录（对应 queryDealPage）。

    条件：userId 可选、symbol 有值时精确匹配、isDeleted=0，按创建时间倒序；
    返回 (记录列表, 总数)。page_size 上限 1000（对应原分页插件 setMaxLimit）。
    """
    page_size = min(page_size, 1000)
    conditions = [TradeDeal.is_deleted == 0]
    if user_id is not None:
        conditions.append(TradeDeal.user_id == user_id)
    if symbol is not None and symbol.strip():
        conditions.append(TradeDeal.symbol == symbol)

    base = select(TradeDeal).where(*conditions).order_by(TradeDeal.create_time.desc())
    total = db.execute(
        select(func.count()).select_from(TradeDeal).where(*conditions)
    ).scalar_one()
    records = list(
        db.execute(
            base.limit(page_size).offset((page_num - 1) * page_size)
        ).scalars().all()
    )
    return records, int(total)
