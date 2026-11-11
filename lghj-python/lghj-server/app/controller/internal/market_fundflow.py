"""内部个股资金流接口路由（供 AI Agent 服务 8091 资金流向 Agent 调用）。

立项扩展功能（非原 Java）：8091 的 queryFundFlow 工具经本端点取个股资金流，
数据源为预测服务 8001 的 /fundflow（新浪主源 + 东财回退 + CSV 缓存降级）。

接口契约：
- GET /api/internal/fundflow?market={sh|sz|bj}&code={6位}&days={1~20}
      header: X-Internal-Token（token 配置非空时必须匹配）
- 响应 data: {symbol, items:[{date, close, changePct, turnover, mainNetInflow,
  mainNetPct, superNetInflow, bigNetInflow, midNetInflow, smallNetInflow}]}
  （金额单位元、占比单位 %，最新交易日在前）；上游不可用返回 data=null + 失败 msg

鉴权说明同 market_realtime.py：不走 JWT 拦截器，控制器自行校验
X-Internal-Token（环境变量 LGHJ_INTERNAL_API_TOKEN，默认空=不校验）。
"""

from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, Header
from app.common.result import Result
from app.utils import http_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["内部个股资金流接口"])


def _has_text(value: str | None) -> bool:
    """对应 Spring StringUtils.hasText。"""
    return value is not None and value.strip() != ""


@router.get("/api/internal/fundflow")
async def query_fundflow(
    market: str | None = None,  # noqa: N803 query 参数保持原 Java 风格小写
    code: str | None = None,  # noqa: N803
    days: int = 5,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> Result:
    """查询个股近 N 日资金流向（转发预测服务 8001 /fundflow）。"""
    internal_api_token = os.environ.get("LGHJ_INTERNAL_API_TOKEN", "")
    if _has_text(internal_api_token) and internal_api_token != x_internal_token:
        return Result.error("internal token invalid")
    # 参数校验（code 必填；days 截断 [1, 20]）
    if not _has_text(code) or not _has_text(market):
        raise RuntimeError("Missing parameter: market/code")
    days = max(1, min(int(days), 20))

    symbol = f"{market.strip().lower()}{code.strip()}"
    url = http_client.prediction_fundflow_url(symbol)
    response = await http_client.get_text(url, params={"days": days}, timeout=30.0)
    if not response:
        return Result.error("资金流数据不可用：预测服务不可达或数据源失败")
    try:
        parsed = json.loads(response)
    except ValueError:
        logger.error("资金流上游响应非 JSON symbol=%s", symbol)
        return Result.error("资金流数据响应异常")
    return Result.success(parsed)
