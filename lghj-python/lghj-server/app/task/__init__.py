"""定时/启动任务包。

对应复现原 Java com/lghj/task 包：
- MarketDataSchedulerTask.java：@Scheduled(fixedRate = 3000) 每 3 秒拉行情并触发撮合
  （见 market_data_scheduler_task.py）
- OrderRecoveryTask.java：@PostConstruct 启动恢复未完成订单 + 每小时订单簿快照
  （见 order_recovery_task.py）

本包提供 start()/stop() 生命周期入口，由 app/main.py 的启动/关闭钩子调用
（对应 Spring 容器托管 Bean 的生命周期）：
- start()：绑定事件循环 → 执行订单恢复（重建撮合队列与订单簿）→ 启动 3 秒行情调度循环；
- stop()：取消行情调度与全部撮合队列消费者（对应原 @PreDestroy 优雅关闭）。
"""

from __future__ import annotations

import asyncio
import logging

from app.task import market_data_scheduler_task, order_recovery_task
from app.utils.order_queue_manager import order_queue_manager

logger = logging.getLogger(__name__)

# 后台任务句柄：行情调度循环
_scheduler_task: asyncio.Task | None = None

# 是否已启动（幂等保护，防止重复 start）
_started = False


def start() -> None:
    """启动全部交易后台任务（在应用启动钩子中、事件循环线程内调用）。"""
    global _scheduler_task, _started
    if _started:
        return

    loop = asyncio.get_running_loop()
    # 绑定主事件循环：撮合队列据此实现跨线程投递与异步行情调用
    order_queue_manager.bind_loop(loop)

    # 订单恢复（对应 OrderRecoveryTask @PostConstruct）：先恢复，再启动调度
    order_recovery_task.recover_unfinished_orders()

    # 3 秒行情调度循环（对应 MarketDataSchedulerTask @Scheduled(fixedRate=3000)）
    _scheduler_task = asyncio.create_task(market_data_scheduler_task.run_forever())

    _started = True
    logger.info("交易后台任务已启动（行情调度 + 撮合队列就绪）")


async def stop() -> None:
    """停止全部交易后台任务（在应用关闭钩子中调用，对应 @PreDestroy）。"""
    global _scheduler_task, _started
    if not _started:
        return

    if _scheduler_task is not None:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        _scheduler_task = None

    # 关闭全部撮合队列消费者
    await order_queue_manager.shutdown()

    _started = False
    logger.info("交易后台任务已全部停止")
