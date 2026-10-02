"""买入方向交易策略。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/trade/BuyTradeDirectionStrategy.java

语义（照抄原实现）：
- reserve：冻结资金 = 委托价 × 股数（数量单位为手，×100），可用资金不足抛 DONT_HAVE_ENOUGH_MONEY；
- release：撤单解冻未成交部分资金；
- canExecute：委托价 >= 现价即可成交（按现价全额成交）；
- validateBeforeDeal：账户存在性校验；
- settle：结算 = 加权平均成本 + 退差价：
    账户：total_cash -= 实际成交额；frozen_cash -= 委托冻结额；
          available_cash += (委托冻结额 - 实际成交额)  ← 差价退回可用
    持仓：无持仓则新建（version=1，accountId=userId 照抄原 builder）；
          有持仓则 total/available 增加，成本价 = (原成本×原数量 + 成交价×成交数量) / 新数量（2位 HALF_UP）。
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.common.exception import BusinessException
from app.common.result import ErrorEnum
from app.pojo.entity import TradeOrder, UserPosition
from app.service.trade import trade_account_operator
from app.service.trade.trade_direction_strategy import TradeDirectionStrategy


class BuyTradeDirectionStrategy(TradeDirectionStrategy):
    """买入方向策略（对应 @Component BuyTradeDirectionStrategy）。"""

    def direction(self) -> int:
        return 1

    def reserve(self, db: Session, order: TradeOrder) -> None:
        account = trade_account_operator.get_account(db, order.user_id)
        if account is None:
            raise BusinessException(ErrorEnum.ACCOUNT_NOT_FOUND, "用户账户不存在")

        frozen_amount = trade_account_operator.order_amount(order.price, order.quantity)
        if account.available_cash < frozen_amount:
            raise BusinessException(ErrorEnum.DONT_HAVE_ENOUGH_MONEY, "账户可用资金不足")

        account.frozen_cash = account.frozen_cash + frozen_amount
        account.available_cash = account.available_cash - frozen_amount
        trade_account_operator.update_account(db, account)

    def release(self, db: Session, order: TradeOrder, untraded_quantity: int) -> None:
        account = trade_account_operator.get_account(db, order.user_id)
        if account is None:
            return

        unfreeze_amount = trade_account_operator.order_amount(order.price, untraded_quantity)
        account.frozen_cash = account.frozen_cash - unfreeze_amount
        account.available_cash = account.available_cash + unfreeze_amount
        trade_account_operator.update_account(db, account)

    def can_execute(self, order: TradeOrder, current_price: Decimal) -> bool:
        # 买单委托价 >= 当前价，可以成交（现价更低，按现价全额成交）
        return order.price >= current_price

    def validate_before_deal(self, db: Session, order: TradeOrder, deal_quantity: int) -> None:
        account = trade_account_operator.get_account(db, order.user_id)
        if account is None:
            raise BusinessException(ErrorEnum.ACCOUNT_NOT_FOUND, "用户账户不存在")

    def settle(self, db: Session, order: TradeOrder, deal_price: Decimal, deal_quantity: int) -> None:
        user_id = order.user_id
        symbol = order.symbol

        # ---------- 账户结算（退差价） ----------
        account = trade_account_operator.get_account(db, user_id)
        if account is not None:
            actual_amount = trade_account_operator.order_amount(deal_price, deal_quantity)
            frozen_amount = trade_account_operator.order_amount(order.price, deal_quantity)
            account.total_cash = account.total_cash - actual_amount
            account.frozen_cash = account.frozen_cash - frozen_amount
            account.available_cash = account.available_cash + (frozen_amount - actual_amount)
            trade_account_operator.update_account(db, account)

        # ---------- 持仓结算（加权平均成本） ----------
        position = trade_account_operator.get_position(db, user_id, symbol)
        stock_quantity = trade_account_operator.stock_quantity(deal_quantity)
        if position is None:
            position = UserPosition(
                user_id=user_id,
                account_id=user_id,  # 照抄原 builder：accountId(userId)
                symbol=symbol,
                total_quantity=stock_quantity,
                frozen_quantity=0,
                available_quantity=stock_quantity,
                cost_price=deal_price,
                profit_loss=Decimal("0"),
                version=1,
            )
            trade_account_operator.insert_position(db, position)
            return

        new_total_quantity = position.total_quantity + stock_quantity
        new_cost_price = (
            (position.cost_price * Decimal(position.total_quantity))
            + (deal_price * Decimal(stock_quantity))
        ) / Decimal(new_total_quantity)
        new_cost_price = new_cost_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        position.total_quantity = new_total_quantity
        position.available_quantity = position.available_quantity + stock_quantity
        position.cost_price = new_cost_price
        trade_account_operator.update_position(db, position)
