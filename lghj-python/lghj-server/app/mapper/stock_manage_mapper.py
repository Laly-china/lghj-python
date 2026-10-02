"""管理端股票表数据访问（分页查询/按代码更新）。

对应复现原 Java StockServiceImpl.pageQuery / updateByCode 中
对 StockBasic 表的查询与更新语义（复用 stock_basic_mapper 的基础查询）。
全局逻辑删除语义（is_deleted）同 blog_mapper.py 模块说明。
"""

from __future__ import annotations

from sqlalchemy import func as sa_func
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.pojo.entity import StockBasic


def select_page_by_keyword(
    db: Session, page_num: int, page_size: int, keyword: str | None
) -> tuple[list[StockBasic], int]:
    """分页查询股票列表（对应 pageQuery：isDeleted=0 + keyword 对 symbol/name
    的 LIKE 相或 + 按创建时间倒序），返回 (当前页记录, 总条数)。"""
    conditions = [StockBasic.is_deleted == 0]
    if keyword is not None and keyword.strip() != "":
        like = f"%{keyword}%"
        conditions.append(
            (StockBasic.symbol.like(like)) | (StockBasic.name.like(like))
        )
    offset = (max(1, page_num) - 1) * page_size
    stmt = (
        select(StockBasic)
        .where(*conditions)
        .order_by(StockBasic.create_time.desc())
        .offset(offset)
        .limit(page_size)
    )
    records = list(db.execute(stmt).scalars().all())
    total = int(
        db.execute(
            select(sa_func.count()).select_from(StockBasic).where(*conditions)
        ).scalar_one()
    )
    return records, total


def update_by_symbol(db: Session, symbol: str | None, values: dict) -> bool:
    """按股票代码更新（对应 updateByCode：update(entity, eq(symbol))，
    非空字段进 SET；symbol 为空时对应 SQL `symbol = null` 永不匹配 → 返回 False），
    返回受影响行数 > 0。"""
    if symbol is None:
        return False
    if not values:
        return False
    stmt = (
        update(StockBasic)
        .where(StockBasic.symbol == symbol, StockBasic.is_deleted == 0)
        .values(**values)
    )
    result = db.execute(stmt)
    return bool(result.rowcount and result.rowcount > 0)
