"""内部用户模型配置接口路由（供 AI Agent 服务 8091 按用户路由模型）。

Python 复现扩展功能（非原 Java）：8091 的 RoutingLlmClient 聊天时按 userId
拉取该用户自配的当前模型提供商（cc-switch 风格多模型选择）。

接口契约：
- GET /api/internal/model-config?userId={id}
      header: X-Internal-Token（token 配置非空时必须匹配）
- 响应 data: {name, baseUrl, apiKey, model, completionsPath}（明文 key）
  或 null（用户未配置/未激活）

鉴权说明同 sim_trade_profile.py：不走 JWT 拦截器，控制器自行校验
X-Internal-Token（环境变量 LGHJ_INTERNAL_API_TOKEN，默认空=不校验）。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.common.result import Result
from app.database import get_db
from app.service import user_model_config_service

router = APIRouter(tags=["内部用户模型配置接口"])


def _has_text(value: str | None) -> bool:
    """对应 Spring StringUtils.hasText。"""
    return value is not None and value.strip() != ""


@router.get("/api/internal/model-config")
def query_active_config(
    userId: str | None = None,  # noqa: N815 字符串透传（8091 的 userId 可能非数字，如测试账号）
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    db: Session = Depends(get_db),
) -> Result:
    """查询用户当前激活的模型配置（明文 key，仅服务间调用）。"""
    internal_api_token = os.environ.get("LGHJ_INTERNAL_API_TOKEN", "")
    if _has_text(internal_api_token) and internal_api_token != x_internal_token:
        return Result.error("internal token invalid")
    # userId 缺失（对齐 sim_trade_profile：Spring 缺参 → SYSTEM_ERROR）
    if not _has_text(userId):
        raise RuntimeError("Missing parameter: userId")
    # 非数字 userId（测试账号等）不可能有配置，直接返回 null，避免 DB 类型错误
    if not userId.strip().isdigit():
        return Result.success(None)
    return Result.success(user_model_config_service.get_active_plain(db, int(userId.strip())))
