"""模拟交易用户画像服务（内部 API，供 AI Agent 服务调用）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/ISimTradeProfileService.java
- feng-lghj/lghj-server/src/main/java/com/lghj/service/impl/SimTradeProfileServiceImpl.java
- feng-lghj/lghj-server/src/main/java/com/lghj/pojo/vo/SimTradeProfileVO.java

核心功能：根据用户ID聚合账户/持仓/订单/成交数据，生成交易统计报表 + 行为标签。
数据直接查 trade_order/trade_deal/sim_account/user_position 表（只读，
不依赖交易引擎代码）；无交易数据时返回字段齐全的空画像结构。

6 个行为标签算法（照抄 behaviorTags，判定顺序与原 Java 一致）：
1. NO_TRADE_RECORD        无任何交易记录：成交列表与订单列表均为空
2. CONCENTRATED_POSITION  集中持仓：持仓数=1 或 第一重仓成本占比>=0.60
3. HIGH_ORDER_FREQUENCY   下单频率高：订单总数 >= 20
4. FREQUENT_CANCEL        频繁撤单：已撤销（status=4）订单数 >= 5
5. BUY_SIDE_BIAS          偏爱买入：买入订单数 > 卖出订单数*2 且订单非空
6. DIVERSIFIED_TRADING    分散交易：成交去重股票代码数 >= 5
"""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.mapper import sim_trade_profile_mapper
from app.pojo.entity import TradeDeal, TradeOrder, UserPosition
from app.service import account_service

logger = logging.getLogger(__name__)

# 最近记录最大限制数：订单/持仓/成交只返回最近30条（对应 RECENT_LIMIT）
RECENT_LIMIT = 30

# 金额比较常量（对应 new BigDecimal("0.60")）
_CONCENTRATED_THRESHOLD = Decimal("0.60")


def query_profile(db: Session, user_id: int) -> dict:
    """查询用户模拟交易画像（对应 queryProfile）。

    1. 查询用户基础数据：账户/持仓（对应 accountService）与订单/成交（对应
       tradeService 的只读查询，复现于 sim_trade_profile_mapper）。
    2. 构建并返回画像（只返回最近30条记录，统计数据完整计算）。
    """
    # 1. 查询用户基础数据
    account = account_service.get_account_by_user_id(db, user_id)      # 模拟账户信息
    positions = account_service.get_user_positions(db, user_id)        # 用户持仓列表
    orders = sim_trade_profile_mapper.select_orders_by_user(db, user_id)  # 用户所有订单
    deals = sim_trade_profile_mapper.select_deals_by_user(db, user_id)    # 用户所有成交

    # 2. 构建并返回画像（只返回最近30条记录，统计数据完整计算）
    return {
        "userId": user_id,
        "account": account.to_result_dict() if account is not None else None,
        "positions": _limit_list([p.to_result_dict() for p in positions]),
        "recentOrders": _limit_list([o.to_result_dict() for o in orders]),
        "recentDeals": _limit_list([d.to_result_dict() for d in deals]),
        "summary": _build_summary(positions, orders, deals),
    }


# ====================== 统计汇总构建（核心方法，对应 buildSummary） ======================

def _build_summary(
    positions: list[UserPosition],
    orders: list[TradeOrder],
    deals: list[TradeDeal],
) -> dict:
    # 1. 计算买卖总成交额（1=买入，2=卖出）
    buy_amount = _deal_amount(deals, 1)
    sell_amount = _deal_amount(deals, 2)

    # 2. 计算当前所有持仓的总成本
    current_position_cost = sum((_position_cost(p) for p in positions), Decimal("0"))

    # 3. 找出持仓成本最高的标的（第一重仓；全部为 0 成本时 Java 取列表第一个，
    #    Comparator.comparing 全 0 不抛异常返回首个元素，此处 max 同语义）
    top_position: UserPosition | None = None
    if positions:
        top_position = max(positions, key=_position_cost)

    # 4. 重仓股占总持仓成本比例（保留4位小数，HALF_UP）
    #    修复：原写法照抄 Java BigDecimal.divide(divisor, 4, HALF_UP)，但 Python
    #    decimal.Decimal 无 divide 方法，凡有持仓的用户必抛
    #    AttributeError → 500；改为 Python 除法 + quantize 等价实现
    #    （scale=4、ROUND_HALF_UP 语义不变）。
    top_position_cost_ratio = Decimal("0")
    if top_position is not None and current_position_cost > 0:
        top_position_cost_ratio = (_position_cost(top_position) / current_position_cost).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

    # 5. 按交易代码分组统计成交次数（保持插入顺序，对应 LinkedHashMap）
    deal_count_by_symbol: dict[str, int] = {}
    for deal in deals:
        if deal.symbol is not None:
            deal_count_by_symbol[deal.symbol] = deal_count_by_symbol.get(deal.symbol, 0) + 1

    # 6. 封装所有统计数据（键顺序对应原 Summary 字段声明顺序）
    return {
        "positionCount": len(positions),
        "orderCount": len(orders),
        "dealCount": len(deals),
        "buyOrderCount": _count_orders(orders, 1),
        "sellOrderCount": _count_orders(orders, 2),
        "canceledOrderCount": _count_status(orders, 4),
        "completedOrderCount": _count_status(orders, 3),
        "buyAmount": _dec_to_json(buy_amount),
        "sellAmount": _dec_to_json(sell_amount),
        "currentPositionCost": _dec_to_json(current_position_cost),
        "realizedTurnover": _dec_to_json(buy_amount + sell_amount),
        "topPositionSymbol": top_position.symbol if top_position is not None else None,
        "topPositionCostRatio": _dec_to_json(top_position_cost_ratio),
        "activeSymbols": _active_symbols(positions, deals),
        "dealCountBySymbol": deal_count_by_symbol,
        "behaviorTags": _behavior_tags(positions, orders, deals, top_position_cost_ratio),
    }


# ====================== 工具方法：统计计数 ======================

def _count_orders(orders: list[TradeOrder], direction: int) -> int:
    """统计指定方向的订单数量（1=买入，2=卖出）。"""
    return sum(1 for order in orders if order.direction == direction)


def _count_status(orders: list[TradeOrder], status: int) -> int:
    """统计指定状态的订单数量（3=完成，4=撤销）。"""
    return sum(1 for order in orders if order.status == status)


# ====================== 工具方法：金额计算 ======================

def _deal_amount(deals: list[TradeDeal], direction: int) -> Decimal:
    """指定方向成交总金额 = Σ(成交价 × 成交数量)。"""
    total = Decimal("0")
    for deal in deals:
        if deal.deal_direction == direction:
            price = deal.price if deal.price is not None else Decimal("0")
            quantity = deal.quantity if deal.quantity is not None else 0
            total += price * Decimal(quantity)
    return total


def _position_cost(position: UserPosition) -> Decimal:
    """单个持仓成本 = 成本价 × 总持仓数量。"""
    price = position.cost_price if position.cost_price is not None else Decimal("0")
    quantity = position.total_quantity if position.total_quantity is not None else 0
    return price * Decimal(quantity)


# ====================== 工具方法：交易品种 ======================

def _active_symbols(positions: list[UserPosition], deals: list[TradeDeal]) -> list[str]:
    """用户所有活跃交易品种（持仓有过 + 成交过，去重并保持顺序）。"""
    symbols: dict[str, bool] = {}
    for position in positions:
        if position.symbol is not None:
            symbols[position.symbol] = True
    for deal in deals:
        if deal.symbol is not None:
            symbols[deal.symbol] = True
    return list(symbols.keys())


# ====================== 工具方法：行为标签（对应 behaviorTags） ======================

def _behavior_tags(
    positions: list[UserPosition],
    orders: list[TradeOrder],
    deals: list[TradeDeal],
    top_position_cost_ratio: Decimal,
) -> list[str]:
    """生成用户交易行为标签（自动识别交易风格，判定条件逐条照抄）。"""
    tags: list[str] = []

    # 无任何交易记录
    if not deals and not orders:
        tags.append("NO_TRADE_RECORD")
    # 集中持仓（只有1个持仓 或 单票持仓>60%）
    if len(positions) == 1 or top_position_cost_ratio >= _CONCENTRATED_THRESHOLD:
        tags.append("CONCENTRATED_POSITION")
    # 下单频率高（订单≥20）
    if len(orders) >= 20:
        tags.append("HIGH_ORDER_FREQUENCY")
    # 频繁撤单（撤单≥5）
    if _count_status(orders, 4) >= 5:
        tags.append("FREQUENT_CANCEL")
    # 偏爱买入（买入订单是卖出的2倍以上）
    if _count_orders(orders, 1) > _count_orders(orders, 2) * 2 and orders:
        tags.append("BUY_SIDE_BIAS")
    # 分散交易（交易品种≥5）
    if len({deal.symbol for deal in deals if deal.symbol is not None}) >= 5:
        tags.append("DIVERSIFIED_TRADING")

    return tags


# ====================== 通用工具方法 ======================

def _limit_list(records: list) -> list:
    """限制列表返回数量：只返回前 RECENT_LIMIT 条（对应 limit）。"""
    if len(records) <= RECENT_LIMIT:
        return records
    return records[:RECENT_LIMIT]


def _dec_to_json(value: Decimal) -> float:
    """BigDecimal → JSON 数字（对应 Jackson 将 BigDecimal 序列化为 number）。"""
    return float(value)
