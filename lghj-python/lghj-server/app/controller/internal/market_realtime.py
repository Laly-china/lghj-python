"""内部行情接口路由（供 AI Agent 服务 8091 调用）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/internal/MarketRealtimeController.java
- 配置：application-dev.yml 的 lghj.internal-api.token: ${LGHJ_INTERNAL_API_TOKEN:}

接口契约（照抄，与 Agent 侧客户端 http_ports.py 严格对齐）：
- GET /api/internal/market/realtime
      query: code（必传）、market（可选，缺省按代码推断：5/6/9开头→sh，否则→sz）、
             recentNewsSize（默认5，截断到 [0,20]）、includeMinute（默认true）
      header: X-Internal-Token（token 配置非空时必须匹配）
- 响应 data: {market, code, queryTime, quote, minuteData, news}
  （字段顺序照原 MarketRealtimeData 声明顺序；includeMinute=false 时
   minuteData 为 null，对应原字段未赋值）

鉴权说明：原 WebMvcConfiguration 拦截器只挂 /api/admin/** 与 /api/user/**，
/api/internal/** 不走 JWT 拦截器，由控制器自行校验 X-Internal-Token
（token 来自环境变量 LGHJ_INTERNAL_API_TOKEN，默认空=不校验），照抄。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header

from app.common.result import Result
from app.service import real_time_stock_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["内部行情接口"])


def _get_internal_api_token() -> str:
    """读取内部 API token（对应 @Value("${lghj.internal-api.token:}")，
    环境变量 LGHJ_INTERNAL_API_TOKEN，默认空串）。"""
    return os.environ.get("LGHJ_INTERNAL_API_TOKEN", "")


def _has_text(value: str | None) -> bool:
    """对应 Spring StringUtils.hasText。"""
    return value is not None and value.strip() != ""


def _infer_market(code: str) -> str:
    """市场推断（对应 inferMarket：5/6/9 开头→sh，否则→sz）。"""
    if code.startswith(("5", "6", "9")):
        return "sh"
    return "sz"


@router.get("/api/internal/market/realtime")
async def query_realtime(
    code: str | None = None,
    market: str | None = None,
    recentNewsSize: int | None = 5,  # noqa: N815
    includeMinute: bool = True,  # noqa: N815
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> Result:
    """内部实时行情聚合（对应 queryRealtime）。

    契约细节（照抄原 Spring 行为）：
    - 完全缺失 code 参数 → Spring 抛 MissingServletRequestParameterException，
      落入全局兜底 handleException → SYSTEM_ERROR（code=500）；
    - code 传了但为空白 → 控制器判 hasText → "stock code required"。
    """
    # 1. 内部 token 校验（配置非空时必须匹配）
    internal_api_token = _get_internal_api_token()
    if _has_text(internal_api_token) and internal_api_token != x_internal_token:
        return Result.error("internal token invalid")
    # 2. code 参数完全缺失（对应 Spring 缺参 → SYSTEM_ERROR）
    if code is None:
        raise RuntimeError("Missing parameter: code")
    # 3. code 为空白（对应 !StringUtils.hasText(code)）
    if not _has_text(code):
        return Result.error("stock code required")

    # 4. 参数归一化（market 小写；缺省按代码推断；新闻条数截断到 [0,20]）
    normalized_code = code.strip()
    normalized_market = market.strip().lower() if _has_text(market) else _infer_market(normalized_code)
    news_size = 5 if recentNewsSize is None else max(0, min(recentNewsSize, 20))

    # 5. 聚合行情/资讯/分时（复用任务A 的 real_time_stock_service）。
    #    键顺序照原 MarketRealtimeData 字段声明顺序：
    #    market, code, queryTime, quote, minuteData, news
    data: dict[str, Any] = {
        "market": normalized_market,
        "code": normalized_code,
        "queryTime": datetime.now().isoformat(),
        "quote": None,
        "minuteData": None,
        "news": None,
    }
    data["quote"] = await real_time_stock_service.get_real_time_quote(normalized_market, normalized_code)
    data["news"] = await real_time_stock_service.get_stock_news(normalized_code, news_size)
    if includeMinute:
        data["minuteData"] = await real_time_stock_service.get_minute_data(normalized_market, normalized_code)
    # includeMinute=false 时 minuteData 保持 None（对应原字段未赋值，Jackson 输出 null）

    return Result.success(data)
