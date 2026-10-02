"""模拟交易核心服务。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/ITradeService.java（接口）
- feng-lghj/lghj-server/src/main/java/com/lghj/service/impl/TradeServiceImpl.java（实现，
  同时实现 OrderQueueManager.OrderProcessor 回调接口）

撮合链路（照抄原 Java）：
1. createOrder：构建委托单（orderNo="ORDER"+UUID前16位，status=1）→ 方向策略 reserve
   （冻结资金/持仓，乐观锁）→ 落库 → 提交到该 symbol 的单线程撮合队列；
2. processOrder（OrderProcessor 回调，队列消费者线程执行）：processTrade：
   Redis 交易锁（trade:lock:{userId}:{symbol}，wait=5s/lease=30s）→ 拉现价 →
   canExecute（买价>=现价 / 卖价<=现价）→ 成交执行器 execute；否则挂入混合订单簿；
   现价不可用时也挂入订单簿等待行情调度；
3. cancelOrder：校验归属/状态（3已完成、4已取消拒绝）→ 未成交数量>0 →
   加锁 → status=4 + cancelTime → 从订单簿移除 → 方向策略 release 退回冻结；
4. 行情驱动：MarketDataSchedulerTask 每 3 秒对订单簿活跃 symbol 拉行情 →
   HybridOrderBook.processMarketData 弹出可成交订单（经撮合队列串行执行）。

与原 Java 的实现差异（详见交付报告）：
- 行情获取：原 getCurrentStockPrice 在锁内同步调用 IRealTimeStockService；本实现复用
  A 阶段的异步行情服务（共享 httpx AsyncClient 绑定主事件循环），在工作线程内经
  run_coroutine_threadsafe 提交到主循环获取，锁内顺序保持不变；
- processOrder 事务内异常：原 Java catch 后仍提交事务（部分变更落库）；本实现回滚
  整个事务，保证数据一致（成功路径行为完全一致）；
- 委托单入队时机：原 Java 在事务提交前入队；本实现在提交后入队，避免消费者读到
  未提交的冻结状态。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.mapper import trade_deal_mapper, trade_order_mapper
from app.pojo.entity import TradeOrder
from app.service.real_time_stock_service import get_real_time_quote
from app.service.trade.trade_deal_executor import TradeDealExecutor
from app.service.trade.trade_direction_router import TradeDirectionRouter
from app.utils.hybrid_order_book import hybrid_order_book
from app.utils.lock_util import generate_trade_lock_key, try_lock, unlock
from app.utils.order_queue_manager import order_queue_manager

logger = logging.getLogger(__name__)

# 现价不可用时的兜底价（对应原 getCurrentStockPrice 的 new BigDecimal("10.00")）
DEFAULT_PRICE = Decimal("10.00")


class TradeService:
    """模拟交易服务（对应 TradeServiceImpl，实现撮合回调 OrderProcessor）。"""

    def __init__(self) -> None:
        self._direction_router = TradeDirectionRouter()
        self._trade_deal_executor = TradeDealExecutor(self._direction_router)

    # ====================== 下单 ======================

    def create_order(self, db: Session, user_id: int, symbol: str, direction: int,
                     price: float, quantity: int) -> TradeOrder:
        """创建委托单（对应 @Transactional createOrder）。

        db 为请求级会话（与 A 阶段 service 层约定一致）：事务在方法内提交，
        会话由 get_db 依赖在响应后关闭——保证控制器仍可对返回实体做序列化。
        """
        order = TradeOrder(
            order_no="ORDER" + uuid4().hex[:16],
            user_id=user_id,
            symbol=symbol,
            direction=direction,
            price=Decimal(str(price)),  # 对应 BigDecimal.valueOf(double)
            quantity=quantity,
            traded_quantity=0,
            status=1,
        )

        # 方向策略预冻结（资金/持仓，乐观锁），失败抛 BusinessException 回滚
        strategy = self._direction_router.route(direction)
        strategy.reserve(db, order)

        trade_order_mapper.insert_order(db, order)
        db.commit()

        # 提交到该 symbol 的单线程撮合队列（对应 orderQueueManager.addOrder）
        order_queue_manager.add_order(order)
        logger.info(
            "Trade order created, orderNo=%s, userId=%s, symbol=%s, direction=%s, price=%s, quantity=%s",
            order.order_no, user_id, symbol, direction, price, quantity,
        )
        return order

    # ====================== 撮合回调（OrderProcessor） ======================

    def process_order(self, order: TradeOrder) -> None:
        """撮合回调（对应 TradeServiceImpl.processOrder，由队列消费者线程执行）。"""
        try:
            logger.info("Matching engine starts order, orderNo=%s, symbol=%s", order.order_no, order.symbol)
            self._process_trade(order)
            logger.info("Matching engine finished order, orderNo=%s, symbol=%s", order.order_no, order.symbol)
        except Exception:  # noqa: BLE001 对应原 catch(Exception)：记日志不中断队列
            logger.error(
                "Matching engine failed order, orderNo=%s, symbol=%s", order.order_no, order.symbol,
                exc_info=True,
            )

    def _process_trade(self, order: TradeOrder) -> None:
        """单笔订单撮合（对应 @Transactional processTrade，在工作线程内执行）。"""
        lock_key = generate_trade_lock_key(order.user_id, order.symbol)
        locked = try_lock(lock_key, 5, 30)
        if not locked:
            logger.warning("Trade skipped, lock unavailable, orderNo=%s", order.order_no)
            return

        try:
            current_price = self._get_current_stock_price(order.symbol)
            if current_price is None:
                # 现价不可用：挂入订单簿等待行情调度（对应原分支）
                hybrid_order_book.add_limit_order(order)
                logger.warning(
                    "Trade postponed, market price unavailable, symbol=%s, orderNo=%s",
                    order.symbol, order.order_no,
                )
                return

            strategy = self._direction_router.route(order.direction)
            if strategy.can_execute(order, current_price):
                # 可成交：成交执行（独立会话事务：成交记录 + 订单更新 + 账户/持仓结算）
                db = SessionLocal()
                try:
                    self._trade_deal_executor.execute(db, order, current_price, order.quantity)
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()
                return

            # 不可成交：挂入混合订单簿（对应 hybridOrderBook.addLimitOrder）
            hybrid_order_book.add_limit_order(order)
            logger.info(
                "Limit order queued, symbol=%s, orderNo=%s, orderPrice=%s, currentPrice=%s",
                order.symbol, order.order_no, order.price, current_price,
            )
        finally:
            if locked:
                unlock(lock_key)

    def _get_current_stock_price(self, symbol: str) -> Decimal | None:
        """获取现价（对应 getCurrentStockPrice）。

        行情服务复用 A 阶段异步实现；本方法运行在工作线程，故经
        run_coroutine_threadsafe 提交到主事件循环执行后同步等待结果。
        市场判定照抄原实现：仅 60 开头视为上海，其余一律深圳。
        """
        try:
            market = "sh" if symbol.startswith("60") else "sz"
            loop = order_queue_manager.get_loop()
            if loop is None or loop.is_closed():
                logger.error("Failed to fetch market price, symbol=%s: event loop unavailable", symbol)
                return None
            future = asyncio.run_coroutine_threadsafe(get_real_time_quote(market, symbol), loop)
            quote = future.result(timeout=15)
            price = quote.get("price") if quote else None
            if price is not None:
                return Decimal(str(price))
            logger.warning("Market service returned no price, using default price, symbol=%s", symbol)
            return DEFAULT_PRICE
        except Exception:  # noqa: BLE001 对应原 catch(Exception) 返回 null
            logger.error("Failed to fetch market price, symbol=%s", symbol, exc_info=True)
            return None

    # ====================== 撤单 ======================

    def cancel_order(self, db: Session, order_id: int, user_id: int) -> bool:
        """撤销委托单（对应 @Transactional cancelOrder）。"""
        order = trade_order_mapper.select_by_id(db, order_id)
        if order is None or order.user_id != user_id:
            logger.warning("Cancel rejected, order not found or user mismatch, orderId=%s, userId=%s",
                           order_id, user_id)
            return False
        if order.status == 3 or order.status == 4:
            logger.warning("Cancel rejected, order already finished, orderId=%s, status=%s",
                           order_id, order.status)
            return False

        untraded_quantity = order.quantity - order.traded_quantity
        if untraded_quantity <= 0:
            return False

        lock_key = generate_trade_lock_key(user_id, order.symbol)
        locked = try_lock(lock_key, 5, 30)
        if not locked:
            logger.warning("Cancel rejected, lock unavailable, orderId=%s", order_id)
            return False
        try:
            order.status = 4
            order.cancel_time = datetime.now()
            trade_order_mapper.update_order(db, order)
            hybrid_order_book.remove_order(order)
            self._direction_router.route(order.direction).release(db, order, untraded_quantity)

            db.commit()
            logger.info("Trade order canceled, orderId=%s, userId=%s", order_id, user_id)
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            if locked:
                unlock(lock_key)

    # ====================== 查询 ======================

    def get_user_orders(self, db: Session, user_id: int) -> list[TradeOrder]:
        """用户委托单列表（对应 getUserOrders）。"""
        return trade_order_mapper.select_user_orders(db, user_id)

    def get_user_deals(self, db: Session, user_id: int) -> list:
        """用户成交记录列表（对应 getUserDeals）。"""
        return trade_deal_mapper.select_user_deals(db, user_id)

    def query_deal_page(self, db: Session, page_num: int, page_size: int,
                        user_id: int | None, symbol: str | None) -> tuple[list, int]:
        """分页查询成交记录（对应 queryDealPage）。"""
        return trade_deal_mapper.select_deal_page(db, page_num, page_size, user_id, symbol)


# 全局单例（对应 Spring @Component 单例 Bean）
trade_service = TradeService()

# ====================== 装配（对应 TradeServiceImpl @PostConstruct init） ======================
# 撮合队列与混合订单簿的订单处理器均指向 TradeService（原 Java 两者注入 this）；
# 差异说明：订单簿弹出的可成交订单在本实现中经撮合队列串行执行
# （hybrid_order_book → order_queue_manager → trade_service.process_order），
# 以满足"每 symbol 单线程撮合队列"的复现要求；原 Java 由行情调度线程直接回调。
order_queue_manager.set_order_processor(trade_service.process_order)
hybrid_order_book.set_order_processor(order_queue_manager.add_order)
