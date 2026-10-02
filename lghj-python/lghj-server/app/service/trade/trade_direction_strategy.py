"""交易方向策略接口。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/trade/TradeDirectionStrategy.java

定义买入/卖出两个方向在交易各环节（预冻结、释放、可成交判定、成交前校验、结算）的差异化行为。
"""

from __future__ import annotations

import abc
from decimal import Decimal

from sqlalchemy.orm import Session

from app.pojo.entity import TradeOrder


class TradeDirectionStrategy(abc.ABC):
    """交易方向策略（对应原接口 TradeDirectionStrategy）。"""

    def direction(self) -> int:
        """交易方向（1-买，2-卖），对应 short direction()。"""
        raise NotImplementedError

    def reserve(self, db: Session, order: TradeOrder) -> None:
        """下单预冻结（资金/持仓），对应 void reserve(TradeOrder order)。"""
        raise NotImplementedError

    def release(self, db: Session, order: TradeOrder, untraded_quantity: int) -> None:
        """撤单释放（资金/持仓），对应 void release(TradeOrder order, int untradedQuantity)。"""
        raise NotImplementedError

    def can_execute(self, order: TradeOrder, current_price: Decimal) -> bool:
        """可成交判定（买价>=现价 / 卖价<=现价），对应 canExecute。"""
        raise NotImplementedError

    def validate_before_deal(self, db: Session, order: TradeOrder, deal_quantity: int) -> None:
        """成交前校验（账户/冻结持仓），对应 validateBeforeDeal。"""
        raise NotImplementedError

    def settle(self, db: Session, order: TradeOrder, deal_price: Decimal, deal_quantity: int) -> None:
        """成交结算（加权平均成本 + 退差价），对应 settle。"""
        raise NotImplementedError
