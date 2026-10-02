"""管理端股票数据接口路由（Phase 1 仅复现 Excel 导入入口）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/admin/StockController.java

接口契约（照抄）：
- POST /api/admin/stock/import   从 Excel 导入 A 股基础信息到 MySQL

注意：原 WebMvcConfiguration 中 /api/admin/stock/import 在管理端拦截器
excludePathPatterns 清单内，**无需 token** 即可调用。原类的 /sync-es、/init-es
为 Elasticsearch 专用接口（本工程用 MySQL LIKE 替代 ES），/page、/update、
/batch-update 为管理端业务，均不在 Phase 1 复现范围。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.result import Result
from app.database import get_db
from app.service import stock_service

router = APIRouter(tags=["管理端股票数据接口"])


@router.post("/api/admin/stock/import")
def import_data(db: Session = Depends(get_db)) -> Result:
    """从 Excel 导入 A 股基础信息到 MySQL（对应 importData）。

    原 StockServiceImpl.importStockBasic 内部吞异常，无论成败都返回
    Result.success(文案)：成功 "成功导入股票数据"，失败 "导入失败: 原因"。
    注意：Java 重载解析下 Result.success(String) 走 success(String msg) 分支，
    文案位于响应体的 msg 字段，data 为 null，此处保持一致。
    """
    msg = stock_service.import_stock_basic(db)
    return Result.success(msg=msg)
