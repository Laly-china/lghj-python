"""订单恢复任务：系统启动时恢复未完成的订单，重建进程内订单簿。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/task/OrderRecoveryTask.java

原 Java 为 @PostConstruct（随容器启动执行一次）+ @Scheduled(cron = "0 0 * * * ?")
的订单簿快照持久化（原方法体为 TODO 空实现，仅打日志）；本实现：
- 启动恢复：应用启动钩子中同步执行一次（对应 @PostConstruct）；
- 快照持久化：原方法无实际逻辑，不复现（仅保留说明）。

恢复流程（照抄原实现）：
1. 查询全部状态为 1（待定）或 2（部分完成）且未删除的委托单；
2. 逐单重新提交到该 symbol 的单线程撮合队列；
3. 队列消费者 processTrade 时会重新拉现价：可成交则成交，不可成交则挂入
   混合订单簿——由此完成进程内订单簿的重建；订单簿活跃 symbol 集合恢复后，
   3 秒行情调度任务随之恢复对这些 symbol 的撮合驱动。
"""

from __future__ import annotations

import logging

from app.database import SessionLocal
from app.mapper import trade_order_mapper
from app.service.trade.trade_service import trade_service
from app.utils.order_queue_manager import order_queue_manager

logger = logging.getLogger(__name__)


def recover_unfinished_orders() -> None:
    """启动时恢复未完成的订单（对应 recoverUnfinishedOrders，@PostConstruct）。"""
    logger.info("开始恢复未完成的订单...")

    try:
        db = SessionLocal()
        try:
            # 查询所有状态为待定或部分完成的订单
            unfinished_orders = trade_order_mapper.select_unfinished_orders(db)
        finally:
            db.close()

        logger.info("发现 %s 个未完成的订单", len(unfinished_orders))

        # 将未完成的订单重新加入撮合队列
        for order in unfinished_orders:
            order_queue_manager.add_order(order)
            logger.info("已恢复订单，委托单号：%s，股票代码：%s", order.order_no, order.symbol)

        logger.info("订单恢复完成")
    except Exception:  # noqa: BLE001 对应原 catch(Exception)：恢复失败不阻断启动
        logger.error("恢复未完成的订单失败", exc_info=True)


def persist_order_book_snapshot() -> None:
    """订单簿快照持久化（对应 persistOrderBookSnapshot）。

    原 Java 该定时方法体为 TODO 空实现（仅打印日志：数据库为主存储，内存队列
    仅用于撮合），无实际持久化动作，故本实现同样只保留日志语义，不额外造存储。
    """
    logger.info("执行订单簿快照持久化任务")
    logger.info("订单簿快照持久化完成")
