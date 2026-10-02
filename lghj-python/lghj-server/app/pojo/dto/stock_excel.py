"""A 股 Excel 行映射 DTO。

对应复现原 Java pojo/dto/StockExcel.java（EasyExcel @ExcelProperty 列索引照抄，
注意索引 2 列被原文件跳过不读）。
"""

from __future__ import annotations

from pydantic import BaseModel


class StockExcel(BaseModel):
    """Excel 列映射（列索引照抄原 @ExcelProperty(index=N)）。"""

    code: str | None = None            # index = 0
    name: str | None = None            # index = 1
    shortName: str | None = None       # index = 3（原文件跳过索引 2）  # noqa: N815
    totalShares: str | None = None     # index = 4  # noqa: N815
    floatShares: str | None = None     # index = 5  # noqa: N815
    totalMarketCap: str | None = None  # index = 6  # noqa: N815
    floatMarketCap: str | None = None  # index = 7  # noqa: N815
    industry: str | None = None        # index = 8
    listDateStr: str | None = None     # index = 9  # noqa: N815
