"""自选股业务。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/IUserStockFollowService.java
- feng-lghj/lghj-server/src/main/java/com/lghj/service/impl/UserStockFollowServiceImpl.java

Redis 键：user:stock:follow:{userId}（Set 结构，无 TTL，照抄原实现）。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.common.constants import REDIS_FOLLOW_PREFIX
from app.mapper import stock_basic_mapper, user_stock_follow_mapper
from app.pojo.entity import UserStockFollow
from app.pojo.vo import StockFollowVO
from app.service import real_time_stock_service

logger = logging.getLogger(__name__)


def add_follow(db: Session, user_id: int, symbol: str) -> bool:
    """添加自选股（对应 addFollow：查股票→查Redis→查DB兜底→插入→回写Redis）。"""
    # 1. 根据 symbol 查询 stock_id
    stock = stock_basic_mapper.select_one_by_symbol(db, symbol)
    if stock is None:
        logger.warning("添加自选股失败，股票不存在: %s", symbol)
        return False

    # 2. 检查是否已关注（先查Redis）
    redis_key = REDIS_FOLLOW_PREFIX + str(user_id)
    redis_client = _get_redis()
    try:
        if redis_client.sismember(redis_key, symbol):
            return True
    except Exception:  # noqa: BLE001 Redis 不可用时降级走 DB 兜底
        pass

    # 查数据库兜底
    count = user_stock_follow_mapper.select_count(db, user_id, stock.id)
    if count > 0:
        # 同步回Redis
        try:
            redis_client.sadd(redis_key, symbol)
        except Exception:  # noqa: BLE001
            pass
        return True

    # 3. 插入记录
    follow = UserStockFollow(user_id=user_id, stock_id=stock.id, symbol=stock.symbol)
    result = user_stock_follow_mapper.insert_follow(db, follow)
    db.commit()

    # 4. 更新Redis
    if result:
        try:
            redis_client.sadd(redis_key, symbol)
        except Exception:  # noqa: BLE001
            logger.warning("自选股写入Redis失败，userId=%s，symbol=%s", user_id, symbol)
    return result


def remove_follow(db: Session, user_id: int, symbol: str) -> bool:
    """取消关注（对应 removeFollow：查股票→删DB→删Redis缓存）。"""
    # 1. 根据 symbol 查询 stock_id
    stock = stock_basic_mapper.select_one_by_symbol(db, symbol)
    if stock is None:
        return False

    # 2. 删除数据库记录
    affected = user_stock_follow_mapper.delete_by_user_and_stock(db, user_id, stock.id)
    result = affected > 0
    db.commit()

    # 3. 删除Redis缓存
    if result:
        try:
            _get_redis().srem(REDIS_FOLLOW_PREFIX + str(user_id), symbol)
        except Exception:  # noqa: BLE001
            logger.warning("自选股删除Redis缓存失败，userId=%s，symbol=%s", user_id, symbol)
    return result


async def get_user_follow_list(db: Session, user_id: int) -> list[StockFollowVO]:
    """查询自选股列表（带行情）（对应 getUserFollowList）。

    Redis 优先 → DB 兜底并回写；再按 marketType 前缀拉取实时行情填充 VO。
    """
    redis_key = REDIS_FOLLOW_PREFIX + str(user_id)
    redis_client = _get_redis()

    symbols: list[str] = []
    # 1. 尝试从Redis获取
    try:
        redis_symbols = redis_client.smembers(redis_key)
    except Exception:  # noqa: BLE001
        redis_symbols = set()
    if redis_symbols:
        symbols = list(redis_symbols)
    else:
        # 2. 缓存不存在，查数据库
        follows = user_stock_follow_mapper.select_list_by_user(db, user_id)
        if not follows:
            return []
        symbols = [f.symbol for f in follows]
        # 3. 回写Redis
        try:
            if symbols:
                redis_client.sadd(redis_key, *symbols)
        except Exception:  # noqa: BLE001
            pass

    # 4. 批量获取股票基础信息（为了拿名称和市场类型）
    stocks = stock_basic_mapper.select_by_symbols(db, symbols)
    stock_map = {s.symbol: s for s in stocks}

    # 5. 构造 VO 并填充实时行情
    result: list[StockFollowVO] = []
    for symbol in symbols:
        vo = StockFollowVO(symbol=symbol)
        basic = stock_map.get(symbol)
        if basic is not None:
            vo.stockId = basic.id
            vo.name = basic.name
            # 获取行情（市场前缀映射：1沪A/4科创板→sh，其余→sz）
            market = _get_market_prefix(basic.market_type)
            quote: dict[str, Any] | None = await real_time_stock_service.get_real_time_quote(market, symbol)
            if quote is not None:
                vo.price = _as_float(quote.get("price"))
                vo.changePercent = _as_float(quote.get("changePercent"))
                vo.volume = _as_long(quote.get("volume"))
        else:
            # 数据库查不到基础信息的情况（理论不应发生）
            vo.stockId = 0
            vo.name = symbol

        result.append(vo)
    return result


def _get_redis():
    """懒加载 Redis 客户端（避免模块导入期建连）。"""
    from app.utils.redis_client import get_redis

    return get_redis()


def _get_market_prefix(market_type: int | None) -> str:
    """根据 marketType 获取市场前缀（对应 getMarketPrefix：1沪A/4科创板→sh，其余→sz，默认sh）。"""
    if market_type is None:
        return "sh"
    if market_type in (1, 4):
        return "sh"
    return "sz"


def _as_float(value: Any) -> float:
    """行情数值转换（对应原空值处理，默认 0）。"""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_long(value: Any) -> int:
    """行情成交量转换（对应 toLongValue，默认 0）。"""
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.warning("自选股成交量转换失败，value=%s", value)
        return 0
