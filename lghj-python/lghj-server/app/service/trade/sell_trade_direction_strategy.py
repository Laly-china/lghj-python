"""卖出方向交易策略。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/trade/SellTradeDirectionStrategy.java

语义（照抄原实现）：
- reserve：冻结持仓（数量单位为手，×100），可用持仓不足抛 POSITION_NOT_ENOUGH；
- release：撤单解冻未成交部分持仓；
- canExecute：委托价 <= 现价即可成交（按现价全额成交）；
- validateBeforeDeal：冻结持仓足够性校验（不足抛 POSITION_NOT_ENOUGH）；
- settle：账户 available/total 增加实际成交额；持仓 total/frozen 减少，
  清仓（<=0）时逻辑删除持仓。
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.exception import BusinessException
from app.common.result import ErrorEnum
from app.pojo.entity import TradeOrder
from app.service.trade import trade_account_operator
from app.service.trade.trade_direction_strategy import TradeDirectionStrategy


class SellTradeDirectionStrategy(TradeDirectionStrategy):
    """卖出方向策略（对应 @Component SellTradeDirectionStrategy）。"""

    def direction(self) -> int:
        return 2

    def reserve(self, db: Session, order: TradeOrder) -> None:
        position = trade_account_operator.get_position(db, order.user_id, order.symbol)
        stock_quantity = trade_account_operator.stock_quantity(order.quantity)
        if position is None or position.available_quantity < stock_quantity:
            raise BusinessException(ErrorEnum.POSITION_NOT_ENOUGH, "持仓不足")

        position.frozen_quantity = position.frozen_quantity + stock_quantity
        position.available_quantity = position.available_quantity - stock_quantity
        trade_account_operator.update_position(db, position)

    def release(self, db: Session, order: TradeOrder, untraded_quantity: int) -> None:
        position = trade_account_operator.get_position(db, order.user_id, order.symbol)
        if position is None:
            return

        unfreeze_quantity = trade_account_operator.stock_quantity(untraded_quantity)
        position.frozen_quantity = position.frozen_quantity - unfreeze_quantity
        position.available_quantity = position.available_quantity + unfreeze_quantity
        trade_account_operator.update_position(db, position)

    def can_execute(self, order: TradeOrder, current_price: Decimal) -> bool:
        # 卖单委托价 <= 当前价，可以成交（现价更高，按现价全额成交）
        return order.price <= current_price

    def validate_before_deal(self, db: Session, order: TradeOrder, deal_quantity: int) -> None:
        position = trade_account_operator.get_position(db, order.user_id, order.symbol)
        stock_quantity = trade_account_operator.stock_quantity(deal_quantity)
        if position is None or position.frozen_quantity < stock_quantity:
            raise BusinessException(ErrorEnum.POSITION_NOT_ENOUGH, "冻结持仓不足")

    def settle(self, db: Session, order: TradeOrder, deal_price: Decimal, deal_quantity: int) -> None:
        user_id = order.user_id
        symbol = order.symbol

        # ---------- 账户结算（卖出回款） ----------
        account = trade_account_operator.get_account(db, user_id)
        if account is not None:
            total_amount = trade_account_operator.order_amount(deal_price, deal_quantity)
            account.available_cash = account.available_cash + total_amount
            account.total_cash = account.total_cash + total_amount
            trade_account_operator.update_account(db, account)

        # ---------- 持仓结算（扣减/清仓） ----------
        position = trade_account_operator.get_position(db, user_id, symbol)
        if position is None:
            return

        stock_quantity = trade_account_operator.stock_quantity(deal_quantity)
        new_total_quantity = position.total_quantity - stock_quantity
        if new_total_quantity <= 0:
            trade_account_operator.delete_position(db, position.id)
            return

        position.total_quantity = new_total_quantity
        position.frozen_quantity = position.frozen_quantity - stock_quantity
        trade_account_operator.update_position(db, position)
