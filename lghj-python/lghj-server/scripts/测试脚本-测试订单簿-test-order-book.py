# -*- coding: utf-8 -*-
"""任务B 引擎级自测脚本（冷热分层订单簿：冷入簿 + 溢出降级 + 冷晋升 + 撮合弹出）。

不作为 Python 包，独立运行：
    python "测试脚本-测试订单簿-test-order-book.py"

对应复现原 Java utils/HybridOrderBook 的内部机制验证：
1. 冷存储入簿：lastPrice>0 且价格偏离 ±5% 区间 → Redis ZSet；
2. 热队列溢出降级：第 101 条入簿触发降级（降 50 条到 Redis，堆顶出队）；
3. 冷晋升 + 撮合弹出：lastPrice 变化后，落入新热区间的冷订单晋升回热队列，
   满足成交条件（买>=现价 / 卖<=现价）的订单被弹出并回调处理器。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from decimal import Decimal

from app.pojo.entity import TradeOrder
from app.utils.hybrid_order_book import (
    HOT_QUEUE_MAX_SIZE,
    HybridStockOrderBook,
    hybrid_order_book,
)
from app.utils.redis_client import get_redis

SYMBOL = "sz999999"


def make_order(order_id: int, direction: int, price: str) -> TradeOrder:
    return TradeOrder(
        id=order_id,
        order_no=f"ORDERTEST{order_id:012d}",
        user_id=1,
        symbol=SYMBOL,
        direction=direction,
        price=Decimal(price),
        quantity=1,
        traded_quantity=0,
        status=1,
    )


def main() -> None:
    redis = get_redis()
    book = HybridStockOrderBook(SYMBOL)
    executed: list[int] = []

    # ---------- 1. 冷存储入簿 ----------
    book.update_hot_price_range(Decimal("10.00"))  # 热区间 [9.50, 10.50]
    cold_order = make_order(900001, 1, "8.00")     # 买 8.00，低于热区间下限 → 冷
    book.add_order(cold_order)
    assert redis.zcard(f"orderbook:{SYMBOL}:buy") == 1, "冷存储应有 1 条买单"
    assert book.get_hot_buy_queue_size() == 0, "热买单队列应为空"
    print("1) 冷存储入簿：通过（buy ZSet card=1，热队列 0）")

    # ---------- 2. 热队列溢出降级 ----------
    # 卖单价格 9.50~9.99 全部落在热区间 [9.50, 10.50] → 全部进热队列，
    # 第 101 条入簿时触发溢出：降级 50 条到 Redis（最终热 60 / 冷 50）
    for i in range(HOT_QUEUE_MAX_SIZE + 10):
        book.add_order(make_order(900100 + i, 2, f"9.{50 + (i % 50):02d}"))
    assert book.get_hot_sell_queue_size() == 60, \
        f"溢出后热卖单应为 60，实际 {book.get_hot_sell_queue_size()}"
    cold_sell = redis.zcard(f"orderbook:{SYMBOL}:sell")
    assert cold_sell == 50, f"溢出降级后冷卖单应为 50，实际 {cold_sell}"
    print(f"2) 热队列溢出降级：通过（热卖单 60，冷卖单 50）")

    # ---------- 3a. 现价跌至 8.00：冷买单晋升并撮合弹出 ----------
    book.order_processor = lambda order: executed.append((order.id, order.direction))
    book.process_market_data(Decimal("8.00"), book.order_processor)
    assert (900001, 1) in executed, "冷买单 900001 应晋升并被撮合弹出"
    assert redis.zcard(f"orderbook:{SYMBOL}:buy") == 0, "晋升后冷买单应清空"
    assert book.get_hot_sell_queue_size() == 60, "现价 8.00 时热卖单不应成交"
    print("3a) 冷买单晋升 + 撮合弹出：通过（订单 900001 弹出执行，卖单未受影响）")

    # ---------- 3b. 现价回升至 10.00：冷卖单晋升并全部撮合弹出 ----------
    book.process_market_data(Decimal("10.00"), book.order_processor)
    sell_executed = [oid for oid, d in executed if d == 2]
    assert len(sell_executed) == HOT_QUEUE_MAX_SIZE + 10, \
        f"全部 110 条卖单应成交，实际 {len(sell_executed)}"
    assert redis.zcard(f"orderbook:{SYMBOL}:sell") == 0, "晋升后冷卖单应清空"
    assert book.get_hot_sell_queue_size() == 0, "撮合后热卖单队列应清空"
    print(f"3b) 冷卖单晋升 + 全量撮合弹出：通过（{len(sell_executed)} 条卖单成交）")

    # ---------- 清理测试键与临时订单簿 ----------
    redis.delete(f"orderbook:{SYMBOL}:buy", f"orderbook:{SYMBOL}:sell")
    hybrid_order_book._stock_order_books.pop(SYMBOL, None)
    print("全部引擎级自测通过，测试键已清理")


if __name__ == "__main__":
    main()
