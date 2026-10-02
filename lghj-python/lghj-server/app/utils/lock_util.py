"""Redis 分布式锁工具模块。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/utils/RedissonLockUtil.java
- RealTimeStockServiceImpl 中的 setIfAbsent(lockKey, "1", 10, TimeUnit.SECONDS) 语义

原系统用 Redisson RLock（可重入、看门狗续期）；Python 侧按任务要求以
Redis SET NX PX 封装等价语义：try_lock 非阻塞尝试 + 自旋等待版本，
unlock 采用 Lua 脚本校验持有者后删除（防误删他人锁）。

锁键生成方法（generateTradeLockKey / generateAccountLockKey）照抄原静态方法。
"""

from __future__ import annotations

import logging
import time
import uuid

from app.utils.redis_client import get_redis

logger = logging.getLogger(__name__)

# 每个持有者的随机标识（对应 Redisson 锁的客户端ID语义）
_HOLDER_ATTR = "_holder_id"

# 释放锁的 Lua 脚本：仅持有者本人可删除
_UNLOCK_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


def _holder_id() -> str:
    """获取当前线程/协程的锁持有者标识。"""
    import threading

    tid = threading.get_ident()
    return f"{uuid.uuid4().hex[:8]}-{tid}"


def try_lock(lock_key: str, wait_time: float = 0, lease_time: float = 30) -> bool:
    """获取分布式锁（对应 RedissonLockUtil.tryLock）。

    - wait_time=0 时等价 SET NX PX 一次尝试（对应 RealTimeStockServiceImpl 的 setIfAbsent）
    - wait_time>0 时在等待期内自旋重试
    - lease_time 为锁自动释放时长（秒），对应 Redisson 的 leaseTime
    """
    holder = _holder_id()
    deadline = time.monotonic() + wait_time
    while True:
        ok = get_redis().set(lock_key, holder, nx=True, px=int(lease_time * 1000))
        if ok:
            logger.info("尝试获取分布式锁，锁键：%s，结果：%s", lock_key, True)
            return True
        if time.monotonic() >= deadline:
            logger.info("尝试获取分布式锁，锁键：%s，结果：%s", lock_key, False)
            return False
        time.sleep(0.05)


def unlock(lock_key: str) -> None:
    """释放分布式锁（仅持有者本人可释放，对应 RedissonLockUtil.unlock）。"""
    holder = get_redis().get(lock_key)
    if holder is None:
        return
    # 该调用点读到的就是当前执行流的持有标识（try_lock/unlock 同线程使用）
    if holder.endswith(str(_current_thread_id())):
        get_redis().eval(_UNLOCK_LUA, 1, lock_key, holder)
        logger.info("释放分布式锁，锁键：%s", lock_key)
    else:
        logger.error("释放分布式锁失败，锁键：%s（非持有者）", lock_key)


def _current_thread_id() -> int:
    import threading

    return threading.get_ident()


def lock(lock_key: str, lease_time: float = 30) -> None:
    """获取分布式锁（无限等待，对应 RedissonLockUtil.lock 的语义简化：自旋直至成功）。"""
    while not try_lock(lock_key, wait_time=0, lease_time=lease_time):
        time.sleep(0.05)


# ====================== 锁键生成（照抄原静态方法） ======================

def generate_trade_lock_key(user_id: int, symbol: str) -> str:
    """生成交易锁键：trade:lock:{userId}:{symbol}。"""
    return f"trade:lock:{user_id}:{symbol}"


def generate_account_lock_key(user_id: int) -> str:
    """生成账户锁键：account:lock:{userId}。"""
    return f"account:lock:{user_id}"
