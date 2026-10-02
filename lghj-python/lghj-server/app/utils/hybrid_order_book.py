"""混合订单簿 - 冷热数据分层存储的撮合引擎。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/utils/HybridOrderBook.java（含内部类 HybridStockOrderBook）

核心机制（逐条照抄原实现）：
- 热数据判定：价格在当前价格 ±5%（PRICE_DEVIATION_RATE=0.05）范围内的订单视为热数据；
- 热数据层：内存优先队列，买单价格高→低、卖单价格低→高，容量 HOT_QUEUE_MAX_SIZE=100；
- 溢出降级：热队列满 100 时降级一半（50 条）到 Redis；
- 冷数据层：Redis Sorted Set（member=订单 JSON，score=委托价格），键 orderbook:{symbol}:buy / orderbook:{symbol}:sell；
- 价格晋升：当前价格变化时，从 Redis 晋升落入新热区间的订单到内存热队列；
- 撮合判定：买单 委托价>=当前价 可成交，卖单 委托价<=当前价 可成交，成交价按当前价全额成交。

与原 Java 的行为对齐说明：
1) 原溢出方法注释称"移出优先级最低的一半"，但代码实际是 hotBuyOrders.poll()（买单队首=
   价格最高的买单）——本实现照抄代码行为，并保留该差异注释；
2) 同价订单的内部排序原 PriorityBlockingQueue 未定义（堆序不定），本实现用入簿顺序号作为
   堆的次级排序键（先入簿先撮合），不影响对外契约；
3) 订单 JSON 序列化字段与原 fastjson 输出一致（price 为字符串，其余为数值）。
"""

from __future__ import annotations

import heapq
import itertools
import json
import logging
from decimal import Decimal
from typing import Any, Callable

from app.pojo.entity import TradeOrder
from app.utils.redis_client import get_redis

logger = logging.getLogger(__name__)

# 热数据队列最大容量（HOT_QUEUE_MAX_SIZE = 100）
HOT_QUEUE_MAX_SIZE = 100

# 热数据价格偏差率（PRICE_DEVIATION_RATE = 0.05，即 ±5%）
PRICE_DEVIATION_RATE = Decimal("0.05")

# Redis Key 前缀（REDIS_KEY_PREFIX = "orderbook:"）
REDIS_KEY_PREFIX = "orderbook:"

# Redis 买单 Key 后缀
REDIS_BUY_KEY_SUFFIX = ":buy"

# Redis 卖单 Key 后缀
REDIS_SELL_KEY_SUFFIX = ":sell"

# 撮合回调类型：订单满足成交条件时回调订单处理器（对应 OrderQueueManager.OrderProcessor）
OrderProcessor = Callable[[TradeOrder], Any]


def _serialize_order(order: TradeOrder) -> str:
    """订单序列化为 JSON（对应 serializeOrder，字段名/取值类型照抄 fastjson 输出）。"""
    payload = {
        "id": order.id,
        "orderNo": order.order_no,
        "userId": order.user_id,
        "symbol": order.symbol,
        "direction": order.direction,
        "price": str(order.price),
        "quantity": order.quantity,
        "tradedQuantity": order.traded_quantity,
        "status": order.status,
    }
    return json.dumps(payload, ensure_ascii=False)


def _deserialize_order(order_json: str) -> TradeOrder | None:
    """JSON 反序列化为订单对象，失败返回 None（对应 deserializeOrder 的 catch 语义）。"""
    try:
        data = json.loads(order_json)
        return TradeOrder(
            id=int(data["id"]),
            order_no=str(data["orderNo"]),
            user_id=int(data["userId"]),
            symbol=str(data["symbol"]),
            direction=int(data["direction"]),
            price=Decimal(str(data["price"])),
            quantity=int(data["quantity"]),
            traded_quantity=int(data["tradedQuantity"]),
            status=int(data["status"]),
        )
    except Exception:  # noqa: BLE001 对应原 catch(Exception) 返回 null
        logger.error("反序列化订单失败：%s", order_json)
        return None


class HybridStockOrderBook:
    """单只股票的混合订单簿（对应内部类 HybridStockOrderBook）。

    包含该股票的所有待成交订单，分为热数据（内存堆）与冷数据（Redis ZSet）两层存储。
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

        # 最新成交价格（用于计算热数据区间），初始 BigDecimal.ZERO
        self.last_price: Decimal = Decimal("0")

        # 热数据价格区间下限 = lastPrice * (1 - 0.05)
        self.hot_price_lower: Decimal = Decimal("0")

        # 热数据价格区间上限 = lastPrice * (1 + 0.05)
        self.hot_price_upper: Decimal = Decimal("0")

        # 热数据买单堆：价格高→低优先（价格高的买单先撮合）
        # 堆元素 (-price, seq, order)；seq 为入簿顺序号（同价订单按入簿先后，见模块 docstring）
        self._hot_buy_heap: list[tuple[Decimal, int, TradeOrder]] = []

        # 热数据卖单堆：价格低→高优先（价格低的卖单先撮合）
        self._hot_sell_heap: list[tuple[Decimal, int, TradeOrder]] = []

        # 入簿顺序号发生器
        self._seq = itertools.count()

        # 订单索引：Key=订单ID → Value=订单对象（快速判断存在性/支持撤销快速定位）
        self._order_index: dict[int, TradeOrder] = {}

    # ====================== 增/删 ======================

    def add_order(self, order: TradeOrder) -> None:
        """添加订单到订单簿（对应 addOrder）。

        1. 加入订单索引；2. 判断热/冷归属；3. 热队列溢出时触发降级。
        """
        # 加入订单索引
        self._order_index[order.id] = order

        # 判断是否应该存入冷数据：已有价格基准 且 价格偏离热数据区间
        if self.last_price > Decimal("0") and not self.is_in_hot_range(order.price):
            self.add_to_cold_queue(order)
        else:
            # 检查热队列是否溢出
            if len(self._hot_buy_heap) >= HOT_QUEUE_MAX_SIZE or len(self._hot_sell_heap) >= HOT_QUEUE_MAX_SIZE:
                self.overflow_to_cold_storage()
            # 加入热队列
            if order.direction == 1:
                heapq.heappush(self._hot_buy_heap, (-order.price, next(self._seq), order))
            elif order.direction == 2:
                heapq.heappush(self._hot_sell_heap, (order.price, next(self._seq), order))

    def remove_order(self, order: TradeOrder) -> None:
        """从订单簿中移除订单：索引 + 热队列 + Redis 冷存储（对应 removeOrder）。"""
        # 从索引中移除
        self._order_index.pop(order.id, None)

        # 从热队列中移除（按订单 ID 匹配，对应原 equals/hashCode 仅含 id 的语义）
        if order.direction == 1:
            self._remove_from_heap(self._hot_buy_heap, order.id)
            self.remove_from_cold_storage(order, REDIS_BUY_KEY_SUFFIX)
        elif order.direction == 2:
            self._remove_from_heap(self._hot_sell_heap, order.id)
            self.remove_from_cold_storage(order, REDIS_SELL_KEY_SUFFIX)

    @staticmethod
    def _remove_from_heap(heap: list, order_id: int) -> None:
        """从堆中移除指定订单（原 PriorityBlockingQueue.remove 是 O(n) 遍历，此处同量级）。"""
        for i, entry in enumerate(heap):
            if entry[2].id == order_id:
                heap[i] = heap[-1]
                heap.pop()
                heapq.heapify(heap)
                return

    # ====================== 行情撮合 ======================

    def process_market_data(self, current_price: Decimal, processor: OrderProcessor | None) -> None:
        """处理行情数据，执行撮合逻辑（对应 processMarketData）。"""
        # 1. 更新热数据价格区间，返回是否发生变化
        price_changed = self.update_hot_price_range(current_price)

        # 2. 价格变化时，从冷存储晋升订单到热队列
        if price_changed:
            self.promote_orders_from_cold_storage(current_price)

        # 3. 收集可成交的买单：委托价格 >= 当前价格（按价格从高到低出队）
        executable_buy_orders: list[TradeOrder] = []
        while self._hot_buy_heap:
            buy_order = self._hot_buy_heap[0][2]
            if buy_order.price >= current_price:
                heapq.heappop(self._hot_buy_heap)
                executable_buy_orders.append(buy_order)
            else:
                break  # 后面的订单价格更低，无法成交

        # 4. 收集可成交的卖单：委托价格 <= 当前价格（按价格从低到高出队）
        executable_sell_orders: list[TradeOrder] = []
        while self._hot_sell_heap:
            sell_order = self._hot_sell_heap[0][2]
            if sell_order.price <= current_price:
                heapq.heappop(self._hot_sell_heap)
                executable_sell_orders.append(sell_order)
            else:
                break  # 后面的订单价格更高，无法成交

        # 5. 执行买单成交（从索引移除后回调处理器）
        for buy_order in executable_buy_orders:
            logger.info(
                "买单可成交，股票代码：%s，委托单号：%s，委托价格：%s，当前价格：%s",
                buy_order.symbol, buy_order.order_no, buy_order.price, current_price,
            )
            self._order_index.pop(buy_order.id, None)
            if processor is not None:
                processor(buy_order)

        # 6. 执行卖单成交
        for sell_order in executable_sell_orders:
            logger.info(
                "卖单可成交，股票代码：%s，委托单号：%s，委托价格：%s，当前价格：%s",
                sell_order.symbol, sell_order.order_no, sell_order.price, current_price,
            )
            self._order_index.pop(sell_order.id, None)
            if processor is not None:
                processor(sell_order)

    # ====================== 热区间 ======================

    def update_hot_price_range(self, current_price: Decimal) -> bool:
        """更新热数据价格区间（对应 updateHotPriceRange），返回价格是否发生变化。"""
        if self.last_price == current_price:
            return False  # 价格未变化
        self.last_price = current_price
        # 偏差值 = 当前价格 * 5%（四舍五入 2 位）
        deviation = (current_price * PRICE_DEVIATION_RATE).quantize(Decimal("0.01"), rounding="ROUND_HALF_UP")
        self.hot_price_lower = current_price - deviation
        self.hot_price_upper = current_price + deviation
        logger.debug(
            "更新热数据价格区间，股票代码：%s，当前价格：%s，区间：[%s, %s]",
            self.symbol, current_price, self.hot_price_lower, self.hot_price_upper,
        )
        return True

    def is_in_hot_range(self, price: Decimal) -> bool:
        """判断价格是否在热数据区间内（对应 isInHotRange）。"""
        return self.hot_price_lower <= price <= self.hot_price_upper

    # ====================== 冷存储（Redis ZSet） ======================

    def add_to_cold_queue(self, order: TradeOrder) -> None:
        """订单加入 Redis 冷存储（对应 addToColdQueue）：member=订单JSON，score=委托价格。"""
        redis_key = self.get_redis_key(order.direction)
        score = float(order.price)
        order_json = _serialize_order(order)
        get_redis().zadd(redis_key, {order_json: score})
        logger.debug(
            "订单加入冷数据存储，股票代码：%s，委托单号：%s，价格：%s",
            order.symbol, order.order_no, order.price,
        )

    def remove_from_cold_storage(self, order: TradeOrder, suffix: str) -> None:
        """从 Redis 冷存储中移除订单（对应 removeFromColdStorage）。

        快路径：以当前订单对象序列化串精确 zrem（与入簿串一致时直接命中）。
        兜底（原 Java 同名方法的既有缺陷，此处修复）：撤单时订单经数据库回读，
        price 的 Decimal 标度变化（入簿 "3.0" vs 回读 "3.00"）导致序列化串不一致、
        zrem 无法命中，已撤订单会残留在冷存储中且后续仍可能被晋升成交；
        故 zrem 未命中时按订单 ID 扫描清除，保证撤单语义正确。
        """
        redis_key = REDIS_KEY_PREFIX + self.symbol + suffix
        order_json = _serialize_order(order)
        client = get_redis()
        if client.zrem(redis_key, order_json) > 0:
            return
        for member in client.zrange(redis_key, 0, -1):
            parsed = _deserialize_order(member)
            if parsed is not None and parsed.id == order.id:
                client.zrem(redis_key, member)
                logger.debug(
                    "按订单ID从冷存储移除订单，股票代码：%s，委托单号：%s", self.symbol, order.order_no
                )

    def overflow_to_cold_storage(self) -> None:
        """热队列溢出降级到冷存储（对应 overflowToColdStorage）。

        触发条件：热队列大小超过 HOT_QUEUE_MAX_SIZE（100）；降级一半（50 条）。
        注意：照抄原代码行为——hotBuyOrders.poll() 从堆顶（买单价格最高者）移出，
        与原方法注释（"移出价格最低的"）不一致，忠实保留原实现的实际行为。
        """
        overflow_count = HOT_QUEUE_MAX_SIZE // 2  # 移出50个

        # 买单溢出
        i = 0
        while i < overflow_count and len(self._hot_buy_heap) > HOT_QUEUE_MAX_SIZE // 2:
            entry = heapq.heappop(self._hot_buy_heap)
            self.add_to_cold_queue(entry[2])
            i += 1

        # 卖单溢出（poll() 从堆顶移出价格最低的卖单，同样照抄原代码行为）
        i = 0
        while i < overflow_count and len(self._hot_sell_heap) > HOT_QUEUE_MAX_SIZE // 2:
            entry = heapq.heappop(self._hot_sell_heap)
            self.add_to_cold_queue(entry[2])
            i += 1

    def promote_orders_from_cold_storage(self, current_price: Decimal) -> None:
        """从冷存储晋升订单到热队列（对应 promoteOrdersFromColdStorage）。"""
        self.promote_buy_orders(current_price)
        self.promote_sell_orders(current_price)

    def promote_buy_orders(self, current_price: Decimal) -> None:
        """晋升买单：查询 score >= hotPriceLower 的订单，落入热区间的晋升（对应 promoteBuyOrders）。"""
        redis_key = REDIS_KEY_PREFIX + self.symbol + REDIS_BUY_KEY_SUFFIX

        orders_to_promote = get_redis().zrangebyscore(redis_key, float(self.hot_price_lower), float("inf"))
        if not orders_to_promote:
            return

        for order_json in orders_to_promote:
            order = _deserialize_order(order_json)
            if order is not None and self.is_in_hot_range(order.price):
                heapq.heappush(self._hot_buy_heap, (-order.price, next(self._seq), order))
                get_redis().zrem(redis_key, order_json)
                logger.debug(
                    "买单从冷存储晋升到热队列，股票代码：%s，委托单号：%s，价格：%s",
                    order.symbol, order.order_no, order.price,
                )

    def promote_sell_orders(self, current_price: Decimal) -> None:
        """晋升卖单：查询 score <= hotPriceUpper 的订单，落入热区间的晋升（对应 promoteSellOrders）。"""
        redis_key = REDIS_KEY_PREFIX + self.symbol + REDIS_SELL_KEY_SUFFIX

        orders_to_promote = get_redis().zrangebyscore(redis_key, 0, float(self.hot_price_upper))
        if not orders_to_promote:
            return

        for order_json in orders_to_promote:
            order = _deserialize_order(order_json)
            if order is not None and self.is_in_hot_range(order.price):
                heapq.heappush(self._hot_sell_heap, (order.price, next(self._seq), order))
                get_redis().zrem(redis_key, order_json)
                logger.debug(
                    "卖单从冷存储晋升到热队列，股票代码：%s，委托单号：%s，价格：%s",
                    order.symbol, order.order_no, order.price,
                )

    def get_redis_key(self, direction: int) -> str:
        """获取 Redis Key（对应 getRedisKey）：orderbook:{symbol}:buy / orderbook:{symbol}:sell。"""
        return REDIS_KEY_PREFIX + self.symbol + (REDIS_BUY_KEY_SUFFIX if direction == 1 else REDIS_SELL_KEY_SUFFIX)

    # ====================== 队列规模查询 ======================

    def get_hot_buy_queue_size(self) -> int:
        """热数据买单队列大小。"""
        return len(self._hot_buy_heap)

    def get_hot_sell_queue_size(self) -> int:
        """热数据卖单队列大小。"""
        return len(self._hot_sell_heap)

    def get_cold_buy_queue_size(self) -> int:
        """Redis 冷存储中的买单数量。"""
        size = get_redis().zcard(REDIS_KEY_PREFIX + self.symbol + REDIS_BUY_KEY_SUFFIX)
        return int(size) if size is not None else 0

    def get_cold_sell_queue_size(self) -> int:
        """Redis 冷存储中的卖单数量。"""
        size = get_redis().zcard(REDIS_KEY_PREFIX + self.symbol + REDIS_SELL_KEY_SUFFIX)
        return int(size) if size is not None else 0


class HybridOrderBook:
    """混合订单簿总管理器（对应外层类 HybridOrderBook）。

    Key: 股票代码 → Value: 该股票的 HybridStockOrderBook 实例，懒加载创建，
    一旦创建即永久保留（原 Java 亦如此，symbol 将持续被行情调度轮询）。
    """

    def __init__(self) -> None:
        # 股票订单簿映射表（对应 ConcurrentHashMap）
        self._stock_order_books: dict[str, HybridStockOrderBook] = {}

        # 订单处理器回调：订单满足成交条件时回调（对应 @Setter orderProcessor）
        self.order_processor: OrderProcessor | None = None

    def set_order_processor(self, processor: OrderProcessor) -> None:
        """注入订单处理器（对应 lombok @Setter）。"""
        self.order_processor = processor

    def get_active_symbols(self) -> set[str]:
        """获取所有活跃股票代码（对应 getActiveSymbols）。"""
        return set(self._stock_order_books.keys())

    def get_stock_order_book(self, symbol: str) -> HybridStockOrderBook:
        """获取或创建指定股票的订单簿（对应 getStockOrderBook，computeIfAbsent 语义）。"""
        book = self._stock_order_books.get(symbol)
        if book is None:
            book = HybridStockOrderBook(symbol)
            self._stock_order_books[symbol] = book
        return book

    def add_limit_order(self, order: TradeOrder) -> None:
        """添加限价单到订单簿（对应 addLimitOrder）。"""
        order_book = self.get_stock_order_book(order.symbol)
        order_book.add_order(order)
        logger.info(
            "限价单已添加到混合订单簿，股票代码：%s，委托单号：%s，价格：%s，数量：%s",
            order.symbol, order.order_no, order.price, order.quantity,
        )

    def remove_order(self, order: TradeOrder) -> None:
        """从订单簿中移除订单（对应 removeOrder，订单簿不存在时静默）。"""
        order_book = self._stock_order_books.get(order.symbol)
        if order_book is not None:
            order_book.remove_order(order)
            logger.info("订单已从混合订单簿中移除，股票代码：%s，委托单号：%s", order.symbol, order.order_no)

    def process_market_data(self, symbol: str, current_price: Decimal) -> None:
        """处理行情数据，触发撮合（对应 processMarketData，由 3 秒行情调度任务调用）。"""
        order_book = self._stock_order_books.get(symbol)
        if order_book is None:
            return
        order_book.process_market_data(current_price, self.order_processor)


# 全局单例（对应 Spring @Component 单例 Bean）
hybrid_order_book = HybridOrderBook()
