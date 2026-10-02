"""Redis 客户端模块。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/config/RedissonConfig.java（连接配置）
- 原系统各 Service 中注入的 StringRedisTemplate（字符串读写语义）

约定：127.0.0.1:6379 database 8 无密码；decode_responses=True 对应
StringRedisTemplate 的纯字符串语义。全局单例、懒连接。
"""

from __future__ import annotations

import logging
from typing import Any

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """获取全局 Redis 客户端（对应 StringRedisTemplate）。

    redis-py 自带连接池与断线重连，行为对齐 Spring Data Redis。
    protocol=2：env 内免安装版 Redis 为旧版本（不支持 Redis 6 的 HELLO/RESP3），
    显式固定 RESP2 协议以兼容。
    """
    global _client
    if _client is None:
        _client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            decode_responses=True,
            protocol=2,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
    return _client


def cache_get(key: str) -> str | None:
    """GET 字符串值，异常时返回 None 并记日志（对齐原服务 try/catch 包裹缓存读写的写法）。"""
    try:
        return get_redis().get(key)
    except Exception as exc:  # noqa: BLE001 原系统对缓存异常一律吞掉降级
        logger.warning("读取Redis缓存失败，key=%s, 原因=%s", key, exc)
        return None


def cache_set(key: str, value: str, expire_hours: int | None = None) -> bool:
    """SET 字符串值（可带小时级 TTL），异常时返回 False 并记日志。"""
    try:
        if expire_hours is not None:
            get_redis().set(key, value, ex=expire_hours * 3600)
        else:
            get_redis().set(key, value)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入Redis缓存失败，key=%s, 原因=%s", key, exc)
        return False


def cache_delete(key: str) -> None:
    """DELETE 键，异常吞掉记日志。"""
    try:
        get_redis().delete(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("删除Redis缓存失败，key=%s, 原因=%s", key, exc)


def cache_delete_pattern(pattern: str) -> None:
    """按模式删除键（scan 游标方式，避免 KEYS 阻塞）。"""
    try:
        client = get_redis()
        for key in client.scan_iter(match=pattern, count=200):
            client.delete(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("按模式删除Redis缓存失败，pattern=%s, 原因=%s", pattern, exc)


def cache_set_json(key: str, value: Any, expire_hours: int | None = None) -> bool:
    """对象以 JSON 字符串写入（对应 stringRedisTemplate + JSON.toJSONString）。"""
    import json

    return cache_set(key, json.dumps(value, ensure_ascii=False), expire_hours)


def cache_get_json(key: str) -> Any | None:
    """读取 JSON 字符串并反序列化；损坏时删除键并返回 None（对应原 catch 中 delete 降级）。"""
    import json

    cached = cache_get(key)
    if cached is None:
        return None
    try:
        return json.loads(cached)
    except Exception:  # noqa: BLE001
        cache_delete(key)
        return None
