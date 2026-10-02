"""管理端-博客评论管理接口路由。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/admin/BlogCommentsManageController.java

接口契约（照抄）：
- GET    /api/admin/blog/comments/page    分页查询评论列表（可选 blogId 过滤，
                                          Page 结构 {records, total, ...}）
- DELETE /api/admin/blog/comments/{id}    删除评论（逻辑删除）

路由注册顺序：/page 必须先于 /{id} 声明（FastAPI 按注册顺序匹配）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.result import Result
from app.database import get_db
from app.service import blog_comments_service

router = APIRouter(tags=["管理端-博客评论管理接口"])


@router.get("/api/admin/blog/comments/page")
def page(
    pageNum: int = 1,  # noqa: N815
    pageSize: int = 10,  # noqa: N815
    blogId: int | None = None,  # noqa: N815 可选过滤
    db: Session = Depends(get_db),
) -> Result:
    """分页查询评论列表（对应 page，按创建时间倒序，返回 Page 结构）。"""
    page_result = blog_comments_service.admin_page(db, pageNum, pageSize, blogId)
    return Result.success(page_result)


@router.delete("/api/admin/blog/comments/{id}")
def delete(id: int, db: Session = Depends(get_db)) -> Result:
    """删除评论（对应 delete，removeById 逻辑删除）。"""
    success = blog_comments_service.admin_remove_by_id(db, id)
    return Result.success() if success else Result.error("删除失败")
