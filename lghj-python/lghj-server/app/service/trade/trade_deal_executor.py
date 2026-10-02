"""成交执行器。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/trade/TradeDealExecutor.java

执行流程（照抄原实现，调用方负责事务/会话）：
1. validateBeforeDeal（账户/冻结持仓校验）
2. 生成成交单号 "DEAL" + UUID 前 16 位，插入 trade_deal
3. 累加订单已成交数量；全部成交（traded>=quantity）→ status=3 并从混合订单簿移除，
   否则 status=2；更新 trade_order
4. 调用方向策略 settle 完成账户/持仓结算（加权平均成本 + 退差价）
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.mapper import trade_deal_mapper, trade_order_mapper
from app.pojo.entity import TradeOrder
from app.service.trade.trade_direction_router import TradeDirectionRouter
from app.utils.hybrid_order_book import hybrid_order_book

logger = logging.getLogger(__name__)


class TradeDealExecutor:
    """成交执行器（对应 @Component TradeDealExecutor）。"""

    def __init__(self, direction_router: TradeDirectionRouter) -> None:
        self._direction_router = direction_router

    def execute(self, db: Session, order: TradeOrder, deal_price: Decimal, deal_quantity: int) -> None:
        """执行一笔成交（对应 execute）。"""
        strategy = self._direction_router.route(order.direction)
        strategy.validate_before_deal(db, order, deal_quantity)

        deal_no = "DEAL" + uuid4().hex[:16]
        from app.pojo.entity import TradeDeal  # 局部导入避免循环依赖

        deal = TradeDeal(
            deal_no=deal_no,
            order_id=order.id,
            user_id=order.user_id,
            symbol=order.symbol,
            deal_direction=order.direction,
            price=deal_price,
            quantity=deal_quantity,
        )
        trade_deal_mapper.insert_deal(db, deal)

        order.traded_quantity = order.traded_quantity + deal_quantity
        if order.traded_quantity >= order.quantity:
            order.status = 3
            hybrid_order_book.remove_order(order)
        else:
            order.status = 2
        trade_order_mapper.update_order(db, order)

        strategy.settle(db, order, deal_price, deal_quantity)
        logger.info(
            "Trade deal executed, dealNo=%s, orderNo=%s, symbol=%s, price=%s, quantity=%s",
            deal_no, order.order_no, order.symbol, deal_price, deal_quantity,
        )
