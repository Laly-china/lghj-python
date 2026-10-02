"""分页查询封装类。

对应复现原 Java pojo/dto/PageResult.java（Phase 1 未使用，供后续任务复用）。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PageResult(BaseModel):
    """分页结果：{total, totalPage, pageNum, pageSize, list}。"""

    total: int
    totalPage: int  # noqa: N815 字段名照原 Java
    pageNum: int  # noqa: N815
    pageSize: int  # noqa: N815
    list: list[Any]
