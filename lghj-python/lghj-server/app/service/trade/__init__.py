"""模拟交易业务包。

对应复现原 Java com/lghj/service/trade 包（方向策略体系）与 TradeServiceImpl：

- trade_direction_strategy.py   交易方向策略接口（TradeDirectionStrategy）
- buy_trade_direction_strategy.py    买入策略（BuyTradeDirectionStrategy）
- sell_trade_direction_strategy.py   卖出策略（SellTradeDirectionStrategy）
- trade_direction_router.py          方向路由（TradeDirectionRouter）
- trade_deal_executor.py             成交执行器（TradeDealExecutor）
- trade_account_operator.py          账户操作（冻结/扣减/退回，TradeAccountOperator）
- trade_service.py                   交易核心服务（ITradeService + TradeServiceImpl）
"""

from app.service.trade.trade_service import trade_service

__all__ = ["trade_service"]
