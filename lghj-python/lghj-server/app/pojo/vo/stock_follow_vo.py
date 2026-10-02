"""自选股 VO。

对应复现原 Java pojo/vo/StockFollowVO.java。
"""

from __future__ import annotations

from pydantic import BaseModel


class StockFollowVO(BaseModel):
    """自选股条目 {stockId, symbol, name, price, changePercent, volume}。"""

    stockId: int = 0  # noqa: N815
    symbol: str
    name: str | None = None
    price: float = 0.0
    changePercent: float = 0.0  # noqa: N815 涨跌幅%
    volume: int = 0
