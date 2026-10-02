"""基于 Redis 的全局唯一 ID 生成器。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/utils/RedisIdWorker.java

ID 结构（64bit）：符号位0 | 31位时间戳（秒，自 1640995200 起） | 32位序列号
序列号 = INCR icr:{keyPrefix}:{yyyy:MM:dd}（按天分键）。

注意：原 Java 用 LocalDateTime.now().toEpochSecond(ZoneOffset.UTC)，即把
本机墙上时间当作 UTC 换算秒数——这是原系统的既有行为，此处忠实保留。
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.utils.redis_client import get_redis

# 开始时间戳（BEGIN_TIMESTAMP = 1640995200L，2022-01-01 00:00:00 UTC）
BEGIN_TIMESTAMP = 1640995200
# 序列号位数（COUNT_BITS = 32）
COUNT_BITS = 32


def next_id(key_prefix: str) -> int:
    """生成全局唯一 ID（对应 RedisIdWorker.nextId）。"""
    now = datetime.now()
    # 对齐原语义：本机墙上时间按 UTC 折算 epoch 秒
    now_second = int(now.replace(tzinfo=timezone.utc).timestamp())
    timestamp = now_second - BEGIN_TIMESTAMP

    # 按天自增序列号
    date = now.strftime("%Y:%m:%d")
    count = get_redis().incr(f"icr:{key_prefix}:{date}")

    # 拼接：时间戳左移32位 | 序列号
    return (timestamp << COUNT_BITS) | int(count)
