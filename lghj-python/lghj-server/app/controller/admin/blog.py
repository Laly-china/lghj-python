"""管理端-博客管理接口路由。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/admin/BlogManageController.java

接口契约（照抄）：
- GET    /api/admin/blog/page    分页查询博客列表（Page 结构 {records, total, ...}）
- DELETE /api/admin/blog/{id}    删除博客（逻辑删除）
- GET    /api/admin/blog/{id}    查看博客详情

路由注册顺序：/page 必须先于 /{id} 声明（FastAPI 按注册顺序匹配）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.result import Result
from app.database import get_db
from app.service import blog_service

router = APIRouter(tags=["管理端-博客管理接口"])


@router.get("/api/admin/blog/page")
def page(
    pageNum: int = 1,  # noqa: N815
    pageSize: int = 10,  # noqa: N815
    db: Session = Depends(get_db),
) -> Result:
    """分页查询博客列表（对应 page，返回 Page 结构，records 为 null 时兜底空列表）。"""
    page_result = blog_service.admin_page(db, pageNum, pageSize)
    return Result.success(page_result)


@router.delete("/api/admin/blog/{id}")
def delete(id: int, db: Session = Depends(get_db)) -> Result:
    """删除博客（对应 delete，removeById 逻辑删除）。"""
    success = blog_service.admin_remove_by_id(db, id)
    return Result.success() if success else Result.error("删除失败")


@router.get("/api/admin/blog/{id}")
def get_by_id(id: int, db: Session = Depends(get_db)) -> Result:
    """查看博客详情（对应 getById，原样返回实体）。"""
    blog = blog_service.admin_get_by_id(db, id)
    return Result.success(blog)
