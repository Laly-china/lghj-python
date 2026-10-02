"""管理端股票数据接口路由（page/update/batch-update/sync-es/init-es）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/admin/StockController.java
  中除 /import（任务A 已在 stock_controller.py 复现）外的其余接口

接口契约（照抄）：
- POST /api/admin/stock/sync-es       MySQL 同步到 ES（ES 简化占位，返回成功）
- POST /api/admin/stock/init-es       Excel 初始化 ES（ES 简化占位，返回成功）
- GET  /api/admin/stock/page          分页查询股票列表（Page 结构 {records, total, ...}）
- PUT  /api/admin/stock/update        根据股票代码更新股票信息
- POST /api/admin/stock/batch-update  根据 Excel 批量更新股票信息

ES 简化说明（报告已注明）：本工程用 MySQL LIKE 替代 Elasticsearch 全文搜索，
搜索数据源即 stock_basic 表本身，故 /sync-es、/init-es 做等价占位实现——
不重建任何索引，仅保留原契约路径与响应文案；/init-es 的导入条数取
MySQL stock_basic 现有行数（数据已在库中，无需二次导入）。

拦截器说明：原 WebMvcConfiguration 放行 /api/admin/stock/init-es（无需 token），
其余接口需管理员 token（interceptor.py 已按原放行清单实现，无需改动）。
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.common.result import Result
from app.database import get_db
from app.mapper import stock_basic_mapper
from app.service import stock_manage_service

router = APIRouter(tags=["管理端股票数据接口"])


@router.post("/api/admin/stock/sync-es")
def sync_to_es() -> Result:
    """MySQL 同步股票数据到 ES（对应 syncToEs，ES 简化占位：直接返回成功文案）。

    原 Java Result.success("同步完成") 命中 String 重载 → 文案在 msg、data=null。
    """
    return Result.success(msg="同步完成")


@router.post("/api/admin/stock/init-es")
def init_es_from_excel(db: Session = Depends(get_db)) -> Result:
    """Excel 初始化 ES（对应 initEsFromExcel，ES 简化占位）。

    原 Java 从 Excel 重建 ES 索引并返回导入条数；本工程搜索直接查 MySQL，
    故此处返回库内现有股票条数（0 条时文案照原格式输出）。
    文案命中原 Result.success(String) 重载 → msg 字段、data=null。
    """
    count = stock_basic_mapper.count_all(db)
    return Result.success(msg=f"ES 初始化完成，共导入 {count} 条股票数据")


@router.get("/api/admin/stock/page")
def page(
    pageNum: int = 1,  # noqa: N815
    pageSize: int = 10,  # noqa: N815
    keyword: str | None = None,
    db: Session = Depends(get_db),
) -> Result:
    """分页查询股票列表（对应 page，keyword 对 symbol/name LIKE，返回 Page 结构）。"""
    page_result = stock_manage_service.page_query(db, pageNum, pageSize, keyword)
    return Result.success(page_result)


@router.put("/api/admin/stock/update")
def update_stock(body: dict = Body(...), db: Session = Depends(get_db)) -> Result:
    """根据股票代码更新股票信息（对应 updateStock，@RequestBody StockBasic 绑定）。

    原 Java Result.success("更新成功") 命中 String 重载 → 文案在 msg、data=null。
    """
    success = stock_manage_service.update_by_code(db, body)
    return Result.success(msg="更新成功") if success else Result.error("更新失败，股票不存在或更新失败")


@router.post("/api/admin/stock/batch-update")
def batch_update(db: Session = Depends(get_db)) -> Result:
    """根据 Excel 批量更新股票信息（对应 batchUpdateFromExcel）。"""
    stock_manage_service.batch_update_from_excel(db)
    return Result.success("批量更新任务已提交")
