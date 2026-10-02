"""行情调度任务：每 3 秒拉取活跃股票行情并触发订单簿撮合。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/task/MarketDataSchedulerTask.java

原 Java 为 @Scheduled(fixedRate = 3000)（固定频率，上一轮结束与否均按 3 秒节拍触发）；
本实现为 asyncio 后台协程，每轮处理完后休眠 3 秒再拉起下一轮（fixedDelay 语义，
对单机演示环境行为等价）。

处理流程（照抄原实现）：
1. 取 HybridOrderBook 的活跃 symbol 集合（空则跳过）；
2. 逐 symbol 判定市场（60 开头=sh，其余=sz，照抄原判定逻辑）并拉取腾讯实时行情；
3. 行情价格有效时调用 HybridOrderBook.processMarketData 触发撮合（弹出可成交订单，
   经每 symbol 撮合队列串行执行成交）；
4. 单个 symbol 失败仅记日志，不影响其他 symbol（对应原 per-symbol try/catch）。
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from app.service.real_time_stock_service import get_real_time_quote
from app.utils.hybrid_order_book import hybrid_order_book

logger = logging.getLogger(__name__)

# 调度间隔（秒），对应 @Scheduled(fixedRate = 3000)
SCHEDULE_INTERVAL_SECONDS = 3


async def run_forever() -> None:
    """行情调度主循环（对应 updateMarketData 定时方法）。"""
    logger.info("MarketDataSchedulerTask 已启动，每 %s 秒更新一次行情并触发撮合", SCHEDULE_INTERVAL_SECONDS)
    while True:
        await asyncio.sleep(SCHEDULE_INTERVAL_SECONDS)
        try:
            await update_market_data()
        except Exception:  # noqa: BLE001 保底防御，循环永不退出
            logger.error("行情调度轮次异常", exc_info=True)


async def update_market_data() -> None:
    """单轮行情更新与撮合触发（对应 updateMarketData 方法体）。"""
    active_symbols = hybrid_order_book.get_active_symbols()
    if not active_symbols:
        return

    logger.debug("开始更新行情，活跃股票数量：%s", len(active_symbols))

    for symbol in active_symbols:
        try:
            # 市场判定照抄原实现：60 开头视为上海（sh），其余一律深圳（sz）
            market = "sh" if symbol.startswith("60") else "sz"
            quote = await get_real_time_quote(market, symbol)
            if quote is None:
                continue
            price = quote.get("price")
            current_price: Decimal | None = None
            if isinstance(price, (int, float)) or isinstance(price, str):
                try:
                    current_price = Decimal(str(price))
                except Exception:  # noqa: BLE001 对应原价格类型转换的防御
                    current_price = None

            if current_price is not None:
                # 撮合动作（内存堆 + 可能的 Redis 冷热迁移）放入线程池，避免阻塞事件循环
                await asyncio.to_thread(hybrid_order_book.process_market_data, symbol, current_price)
        except Exception:  # noqa: BLE001 对应原 per-symbol catch：单个失败不影响其他
            logger.error("更新行情失败，股票代码：%s", symbol, exc_info=True)
