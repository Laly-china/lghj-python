"""股票搜索业务（MySQL LIKE 替代原 Elasticsearch）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/IStockSearchService.java
- feng-lghj/lghj-server/src/main/java/com/lghj/service/impl/StockSearchServiceImpl.java

原实现用 Elasticsearch boolQuery（symbol 前缀 + name/industry match，size 20）；
本工程改为 MySQL LIKE（symbol LIKE 'kw%' OR name LIKE '%kw%' OR industry LIKE '%kw%'），
接口契约不变。搜索结果映射为 StockDoc（id/symbol/name/industry/marketType）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.mapper import stock_basic_mapper
from app.pojo.vo import StockDoc


def search(db: Session, keyword: str | None) -> list[StockDoc]:
    """搜索股票（对应 StockSearchServiceImpl.search；keyword 空白返回空列表）。"""
    if keyword is None or not keyword.strip():
        return []

    rows = stock_basic_mapper.search_like(db, keyword.strip(), limit=20)
    return [
        StockDoc(
            id=row.id,
            symbol=row.symbol,
            name=row.name,
            industry=row.industry,
            marketType="" if row.market_type is None else str(row.market_type),
        )
        for row in rows
    ]
