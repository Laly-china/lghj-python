"""股票搜索文档 VO。

对应复现原 Java pojo/doc/StockDoc.java（原为 Elasticsearch 文档，本工程以
MySQL LIKE 替代 ES，返回字段契约保持 {id, symbol, name, industry, marketType}）。
"""

from __future__ import annotations

from pydantic import BaseModel


class StockDoc(BaseModel):
    """搜索结果项。"""

    id: int | None = None
    symbol: str | None = None
    name: str | None = None
    industry: str | None = None
    marketType: str | None = None  # noqa: N815 原 ES 文档中为字符串
