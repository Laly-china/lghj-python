"""博客评论区接口路由（用户端）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/user/BlogCommentsController.java

接口契约（照抄）：
- POST   /api/user/blog/comments/add             新增博客评论（一级/二级通用）
- GET    /api/user/blog/comments/list            查询评论列表（二级树形，拦截器放行）
- POST   /api/user/blog/comments/like/{commentId} 评论点赞/取消点赞
- DELETE /api/user/blog/comments/delete/{commentId} 删除评论（逻辑删除）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.result import Result
from app.database import get_db
from app.pojo.dto.blog_dtos import BlogCommentAddDTO
from app.service import blog_comments_service

router = APIRouter(tags=["博客评论区接口"])


@router.post("/api/user/blog/comments/add")
def add_comment(dto: BlogCommentAddDTO, db: Session = Depends(get_db)) -> Result:
    """新增博客评论（对应 addComment，@Valid 校验）。"""
    blog_comments_service.add_comment(db, dto)
    return Result.success()


@router.get("/api/user/blog/comments/list")
def query_comment_list(
    blogId: int = Query(...),  # noqa: N815 @NotNull(message = "博客ID不能为空")
    pageNum: int = Query(1),  # noqa: N815 默认1
    pageSize: int = Query(10),  # noqa: N815 默认10（一级评论分页）
    db: Session = Depends(get_db),
) -> Result:
    """查询博客评论列表（对应 queryCommentList，带二级评论树形结构，拦截器放行）。"""
    page_result = blog_comments_service.query_comment_list(db, blogId, pageNum, pageSize)
    return Result.success(page_result)


@router.post("/api/user/blog/comments/like/{commentId}")
def like_comment(commentId: int, db: Session = Depends(get_db)) -> Result:
    """评论点赞/取消点赞（对应 likeComment，@NotNull commentId 由路径参数保证）。"""
    blog_comments_service.like_comment(db, commentId)
    return Result.success()


@router.delete("/api/user/blog/comments/delete/{commentId}")
def delete_comment(commentId: int, db: Session = Depends(get_db)) -> Result:
    """删除评论（对应 deleteComment，逻辑删除，一级评论级联删二级）。"""
    blog_comments_service.delete_comment(db, commentId)
    return Result.success()
