"""关注接口路由（用户端）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/user/FollowController.java

接口契约（照抄）：
- PUT /api/user/follow/{id}/{isFollow}    关注和取关
- GET /api/user/follow/or/not/{id}        判断是否关注
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.result import Result
from app.database import get_db
from app.service import follow_service

router = APIRouter(tags=["关注接口"])


@router.put("/api/user/follow/{id}/{isFollow}")
def follow(id: int, isFollow: bool, db: Session = Depends(get_db)) -> Result:
    """关注和取关（对应 follow，isFollow 布尔路径参数，Redis Set 与 DB 双写）。"""
    follow_service.follow(db, id, isFollow)
    return Result.success()


@router.get("/api/user/follow/or/not/{id}")
def is_follow(id: int, db: Session = Depends(get_db)) -> Result:
    """判断是否关注（对应 isFollow，返回布尔值）。"""
    result = follow_service.is_follow(db, id)
    return Result.success(result)
