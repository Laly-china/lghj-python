"""管理端-交易管理接口路由。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/admin/TradeManageController.java

接口契约（照抄，均在 /api/admin/** 拦截范围内，需管理员 token（userType=3））：
- GET /api/admin/trade/order/page  分页查询委托单（pageNum/pageSize 默认 1/10，可选 userId/symbol）
- GET /api/admin/trade/deal/page   分页查询成交记录（同上）

分页响应对齐 MyBatis-Plus Page 的 Jackson 序列化（前端读取 records/total 字段）：
{records: [...], total: n, size: pageSize, current: pageNum, pages: 总页数}。
分页上限 1000 条/页（对应 PaginationInnerInterceptor.setMaxLimit(1000)）。
"""

from __future__ import annotations

import logging
import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.result import Result
from app.database import get_db
from app.mapper import trade_deal_mapper, trade_order_mapper
from app.service.trade.trade_service import trade_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["管理端-交易管理接口"])


def _page_payload(records: list, total: int, page_num: int, page_size: int) -> dict:
    """构造 MyBatis-Plus Page 形态的分页响应体（对齐 Page 的序列化字段）。"""
    if total == 0:
        pages = 0
    else:
        # 对齐 Page.getPages()：total/size 向上取整
        pages = math.ceil(total / page_size)
    return {
        "records": records if records is not None else [],
        "total": total,
        "size": page_size,
        "current": page_num,
        "pages": pages,
    }


@router.get("/api/admin/trade/order/page")
def order_page(
    page_num: int = Query(default=1, alias="pageNum"),
    page_size: int = Query(default=10, alias="pageSize"),
    user_id: int | None = Query(default=None, alias="userId"),
    symbol: str | None = None,
    db: Session = Depends(get_db),
) -> Result:
    """分页查询委托单（对应 orderPage：可选 userId/symbol，按创建时间倒序）。"""
    page_size = min(page_size, 1000)
    records, total = trade_order_mapper.select_order_page(db, page_num, page_size, user_id, symbol)
    return Result.success(_page_payload(records, total, page_num, page_size))


@router.get("/api/admin/trade/deal/page")
def deal_page(
    page_num: int = Query(default=1, alias="pageNum"),
    page_size: int = Query(default=10, alias="pageSize"),
    user_id: int | None = Query(default=None, alias="userId"),
    symbol: str | None = None,
    db: Session = Depends(get_db),
) -> Result:
    """分页查询成交记录（对应 dealPage → tradeService.queryDealPage）。"""
    page_size = min(page_size, 1000)
    records, total = trade_service.query_deal_page(db, page_num, page_size, user_id, symbol)
    return Result.success(_page_payload(records, total, page_num, page_size))
