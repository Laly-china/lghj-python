"""关注业务。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/IFollowService.java
- feng-lghj/lghj-server/src/main/java/com/lghj/service/impl/FollowServiceImpl.java

Redis 结构（键名照抄 RedisConstant.FOLLOWS_KEY）：
- follows:{userId}  Set：member=被关注用户id（DB 与 Redis 双写）
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.community_constants import FOLLOWS_KEY
from app.common.context import BaseContext
from app.mapper import follow_mapper
from app.pojo.entity import Follow
from app.utils.redis_client import get_redis


def follow(db: Session, follow_user_id: int, is_follow: bool) -> None:
    """关注和取关（对应 follow：DB 与 Redis Set 双写）。"""
    # 1. 获取登录用户
    user_id = BaseContext.get_current_id()
    key = FOLLOWS_KEY + str(user_id)

    # 2. 判断到底是关注还是取关
    if is_follow:
        # 关注，新增数据（原系统无重复关注校验，可重复插入，照抄）
        record = Follow(user_id=user_id, follow_user_id=follow_user_id)
        is_success = follow_mapper.insert_follow(db, record)
        if is_success:
            # 把关注用户的id，放入redis的set集合 sadd userId followUserId
            get_redis().sadd(key, str(follow_user_id))
        db.commit()
    else:
        # 取关，逻辑删除 delete from tb_follow where user_id = ? and follow_user_id = ?
        is_success = follow_mapper.delete_by_user_and_follow(db, user_id, follow_user_id)
        if is_success:
            # 把关注的用户id从redis集合中移除
            get_redis().srem(key, str(follow_user_id))
        db.commit()


def is_follow(db: Session, follow_user_id: int) -> bool:
    """判断是否关注（对应 isFollow：count 查询，原实现直接查库未用 Redis）。"""
    # 1. 获取登录用户
    user_id = BaseContext.get_current_id()
    # 2. 查询是否关注 select count(*) from tb_follow where user_id = ? and follow_user_id = ?
    count = follow_mapper.count_by_user_and_follow(db, user_id, follow_user_id)
    # 3. 判断
    return count > 0
