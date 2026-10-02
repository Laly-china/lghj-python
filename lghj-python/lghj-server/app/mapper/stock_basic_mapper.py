"""A股基础信息表数据访问。

对应复现原 Java mapper/StockBasicMapper.java。
"""

from __future__ import annotations

from sqlalchemy import func as sa_func
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.pojo.entity import StockBasic


def select_one_by_symbol(db: Session, symbol: str) -> StockBasic | None:
    """按股票代码查询（对应 selectOne(eq(StockBasic::getSymbol, symbol))）。"""
    stmt = select(StockBasic).where(StockBasic.symbol == symbol).limit(1)
    return db.execute(stmt).scalar_one_or_none()


def select_by_symbols(db: Session, symbols: list[str]) -> list[StockBasic]:
    """按代码集合批量查询（对应 selectList(in(StockBasic::getSymbol, symbols))）。"""
    if not symbols:
        return []
    stmt = select(StockBasic).where(StockBasic.symbol.in_(symbols))
    return list(db.execute(stmt).scalars().all())


def search_like(db: Session, keyword: str, limit: int = 20) -> list[StockBasic]:
    """股票搜索（替代原 Elasticsearch boolQuery 的 MySQL LIKE 实现）。

    原 ES 查询（StockSearchServiceImpl.search）：
      should(prefixQuery("symbol", keyword))   → symbol 前缀匹配（LIKE 'kw%'）
      should(matchQuery("name", keyword))      → name 模糊匹配（LIKE '%kw%'）
      should(matchQuery("industry", keyword))  → industry 模糊匹配（LIKE '%kw%'）
      size 20
    接口契约（路径/参数/返回字段）保持不变。
    """
    pattern_prefix = f"{keyword}%"
    pattern_fuzzy = f"%{keyword}%"
    stmt = (
        select(StockBasic)
        .where(
            or_(
                StockBasic.symbol.like(pattern_prefix),
                StockBasic.name.like(pattern_fuzzy),
                StockBasic.industry.like(pattern_fuzzy),
            )
        )
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def select_all_not_deleted(db: Session) -> list[StockBasic]:
    """查询全部未删除股票（对应 selectList(eq(isDeleted, 0))，原 ES syncData 用）。"""
    stmt = select(StockBasic).where(StockBasic.is_deleted == 0)
    return list(db.execute(stmt).scalars().all())


def count_all(db: Session) -> int:
    """统计全表行数（导入后自检用）。"""
    return int(db.execute(select(sa_func.count()).select_from(StockBasic)).scalar_one())


def insert_batch(db: Session, stocks: list[StockBasic]) -> None:
    """批量插入（对应 MyBatis-Plus saveBatch，调用方负责分批与提交）。"""
    db.add_all(stocks)
    db.flush()
