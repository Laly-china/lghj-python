"""内部模拟交易画像接口路由（供 AI Agent 服务 8091 调用）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/internal/SimTradeProfileController.java

接口契约（照抄，与 Agent 侧客户端 http_ports.py 严格对齐）：
- GET /api/internal/sim-trade/profile?userId={id}
      header: X-Internal-Token（token 配置非空时必须匹配）
- 响应 data: {userId, account, positions, recentOrders, recentDeals, summary}
  其中 summary.behaviorTags 为 6 个行为标签算法输出（详见
  sim_trade_profile_service 模块 docstring）

鉴权说明同 market_realtime.py：不走 JWT 拦截器，控制器自行校验
X-Internal-Token（环境变量 LGHJ_INTERNAL_API_TOKEN，默认空=不校验）。
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.common.result import Result
from app.database import get_db
from app.service import sim_trade_profile_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["内部模拟交易画像接口"])


def _get_internal_api_token() -> str:
    """读取内部 API token（对应 @Value("${lghj.internal-api.token:}")）。"""
    return os.environ.get("LGHJ_INTERNAL_API_TOKEN", "")


def _has_text(value: str | None) -> bool:
    """对应 Spring StringUtils.hasText。"""
    return value is not None and value.strip() != ""


@router.get("/api/internal/sim-trade/profile")
def query_profile(
    userId: int | None = None,  # noqa: N815 @RequestParam Long userId
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    db: Session = Depends(get_db),
) -> Result:
    """查询用户模拟交易画像（对应 queryProfile）。

    契约细节：userId 完全缺失时 Spring 抛 MissingServletRequestParameterException，
    落入全局兜底 handleException → SYSTEM_ERROR（code=500），照抄。
    """
    # 1. 内部 token 校验（配置非空时必须匹配）
    internal_api_token = _get_internal_api_token()
    if _has_text(internal_api_token) and internal_api_token != x_internal_token:
        return Result.error("internal token invalid")
    # 2. userId 缺失（对应 Spring 缺参 → SYSTEM_ERROR）
    if userId is None:
        raise RuntimeError("Missing parameter: userId")
    # 3. 聚合画像（无交易数据时返回字段齐全的空画像结构）
    return Result.success(sim_trade_profile_service.query_profile(db, userId))
