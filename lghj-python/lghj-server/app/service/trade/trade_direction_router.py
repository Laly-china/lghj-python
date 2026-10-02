"""交易方向路由器。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/trade/TradeDirectionRouter.java

按 direction（1-买，2-卖）路由到对应策略实例；未支持的方向抛 IllegalArgumentException。
"""

from __future__ import annotations

from app.service.trade.buy_trade_direction_strategy import BuyTradeDirectionStrategy
from app.service.trade.sell_trade_direction_strategy import SellTradeDirectionStrategy
from app.service.trade.trade_direction_strategy import TradeDirectionStrategy


class TradeDirectionRouter:
    """方向策略路由（对应 @Component TradeDirectionRouter，构造时收集全部策略）。"""

    def __init__(self) -> None:
        strategies: list[TradeDirectionStrategy] = [
            BuyTradeDirectionStrategy(),
            SellTradeDirectionStrategy(),
        ]
        # 对应 strategies.stream().collect(toMap(TradeDirectionStrategy::direction, identity()))
        self._strategy_map: dict[int, TradeDirectionStrategy] = {
            strategy.direction(): strategy for strategy in strategies
        }

    def route(self, direction: int) -> TradeDirectionStrategy:
        """按方向取策略（对应 route），未支持方向抛 IllegalArgumentException。"""
        strategy = self._strategy_map.get(direction)
        if strategy is None:
            raise ValueError(f"Unsupported trade direction: {direction}")
        return strategy
