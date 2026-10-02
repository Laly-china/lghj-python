"""订单队列管理器 - 为每个股票维护独立的单消费者撮合队列。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/utils/OrderQueueManager.java

核心机制（照抄原设计）：
- 每个股票绑定一个独立的单线程执行器（Python 侧等价实现：每 symbol 一个 asyncio.Queue
  + 一个独立消费者协程，同一股票的订单严格串行处理）；
- 新订单到达时向对应队列提交任务，保证同一股票顺序性；不同股票并行处理；
- 订单处理器回调接口由 TradeService 实现（对应 OrderProcessor 接口）。

线程模型说明：
- 撮合消费者协程内部用 asyncio.to_thread 执行同步 DB/Redis 撮合动作，
  既不阻塞事件循环，又保持"同一股票串行、跨股票并行"的原 Java 语义；
- add_order 可从任意线程（请求线程池/事件循环/行情调度工作线程）安全调用：
  位于事件循环线程时直接入队，否则经 call_soon_threadsafe 投递（对应原
  executor.submit 的线程安全提交）。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable

from app.pojo.entity import TradeOrder

logger = logging.getLogger(__name__)


class OrderQueueManager:
    """每 symbol 单消费者撮合队列管理器（对应 OrderQueueManager）。"""

    def __init__(self) -> None:
        # 每个股票对应的任务队列 Key: 股票代码 → asyncio.Queue（对应 matchExecutors）
        self._queues: dict[str, asyncio.Queue] = {}

        # 每个股票对应的消费者协程任务（对应单线程执行器线程）
        self._consumers: dict[str, asyncio.Task] = {}

        # 主事件循环引用（启动时绑定，用于跨线程投递订单任务）
        self._loop: asyncio.AbstractEventLoop | None = None

        # 订单处理器回调（对应 @Setter OrderProcessor，由 TradeService 实现）
        self._processor: Callable[[TradeOrder], None] | None = None

    # ====================== 装配 ======================

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """绑定主事件循环（应用启动时调用；对应原执行器随 Spring 容器就绪）。"""
        self._loop = loop

    def get_loop(self) -> asyncio.AbstractEventLoop | None:
        """获取绑定的主事件循环（供工作线程经 run_coroutine_threadsafe 调用异步能力）。"""
        return self._loop

    def set_order_processor(self, processor: Callable[[TradeOrder], None]) -> None:
        """注入订单处理器（对应 lombok @Setter）。"""
        self._processor = processor

    # ====================== 提交订单 ======================

    def add_order(self, order: TradeOrder) -> None:
        """将订单添加到处理队列（对应 addOrder，线程安全）。

        处理流程：获取或创建该股票的队列与消费者 → 投递订单任务 →
        消费者保证同一股票的订单串行处理。
        """
        symbol = order.symbol
        if self._loop is None or self._loop.is_closed():
            logger.error("订单任务提交失败：事件循环未绑定或已关闭，股票代码：%s，委托单号：%s",
                         symbol, order.order_no)
            return

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is self._loop:
            # 已在事件循环线程内：直接入队
            self._enqueue(order)
        else:
            # 工作线程（请求线程池/撮合线程）：线程安全投递
            self._loop.call_soon_threadsafe(self._enqueue, order)

        logger.info("订单任务已提交，股票代码：%s，委托单号：%s", symbol, order.order_no)

    def _enqueue(self, order: TradeOrder) -> None:
        """入队并确保该股票的消费者协程存活（在事件循环线程内执行）。"""
        symbol = order.symbol
        queue = self._queues.get(symbol)
        if queue is None:
            queue = asyncio.Queue()
            self._queues[symbol] = queue
            logger.info("创建股票 %s 的撮合队列", symbol)

        consumer = self._consumers.get(symbol)
        if consumer is None or consumer.done():
            consumer = asyncio.create_task(self._consume_loop(symbol))
            self._consumers[symbol] = consumer

        queue.put_nowait(order)

    async def _consume_loop(self, symbol: str) -> None:
        """单股票消费者协程：严格按入队顺序串行处理（对应单线程执行器）。"""
        queue = self._queues[symbol]
        while True:
            order = await queue.get()
            try:
                # 同步撮合动作（DB/Redis）放入线程池执行，避免阻塞事件循环；
                # await 顺序执行保证同一股票的订单串行
                await asyncio.to_thread(self._process_safely, order)
            except Exception:  # noqa: BLE001 对应原 executor.submit 内 catch 继续处理后续订单
                logger.exception("撮合消费者异常，股票代码：%s，委托单号：%s", symbol, order.order_no)
            finally:
                queue.task_done()

    def _process_safely(self, order: TradeOrder) -> None:
        """在工作线程中调用订单处理器并吞异常（对应原 executor.submit 的 try/catch）。"""
        try:
            if self._processor is not None:
                self._processor(order)
        except Exception:  # noqa: BLE001
            logger.error("处理订单失败，股票代码：%s，委托单号：%s", order.symbol, order.order_no,
                         exc_info=True)

    # ====================== 生命周期 ======================

    async def shutdown(self) -> None:
        """停止所有撮合消费者（对应 @PreDestroy shutdown）。

        原 Java 先 shutdown() 再等待 5 秒、超时 shutdownNow()；Python 侧对消费者
        协程执行取消（未处理完的队列订单由重启恢复任务兜底，语义对齐 shutdownNow）。
        """
        logger.info("开始关闭所有撮合队列，共 %d 个", len(self._consumers))
        for symbol, consumer in list(self._consumers.items()):
            consumer.cancel()
            try:
                await consumer
            except asyncio.CancelledError:
                logger.info("股票 %s 的撮合队列已关闭", symbol)
        self._consumers.clear()
        self._queues.clear()
        logger.info("所有撮合队列已关闭")

    # ====================== 状态查询 ======================

    def get_active_symbol_count(self) -> int:
        """当前有撮合队列的股票数量（对应 getActiveSymbolCount）。"""
        return len(self._queues)

    def has_active_executor(self, symbol: str) -> bool:
        """检查指定股票是否有活跃的消费者（对应 hasActiveExecutor）。"""
        consumer = self._consumers.get(symbol)
        return consumer is not None and not consumer.done()


# 全局单例（对应 Spring @Component 单例 Bean）
order_queue_manager = OrderQueueManager()
