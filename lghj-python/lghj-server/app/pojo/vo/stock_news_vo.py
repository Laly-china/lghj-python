"""股票实时资讯 VO。

对应复现原 Java pojo/vo/StockNewsVO.java。
"""

from __future__ import annotations

from pydantic import BaseModel


class StockNewsVO(BaseModel):
    """新闻条目 {keyword, title, content, publishTime, source, url}。"""

    keyword: str | None = None
    title: str | None = None
    content: str | None = None
    publishTime: str | None = None  # noqa: N815
    source: str | None = None
    url: str | None = None
