"""讨论区博客接口路由（用户端）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/user/BlogController.java

接口契约（照抄）：
- POST   /api/user/blog                  发布博客
- PUT    /api/user/blog/like/{id}        点赞功能接口（ZSet 切换）
- GET    /api/user/blog/query/of/me      分页查看登录用户自己的博客内容
- GET    /api/user/blog/query/hot        根据点赞数量（热度）展示博客（放行）
- GET    /api/user/blog/query/of/user    查看指定用户发的博客（放行）
- GET    /api/user/blog/query/of/follow  粉丝查看关注所有用户博客接口（Feed 收件箱）
- GET    /api/user/blog/query/{id}       根据id查询博客
- DELETE /api/user/blog/delete/{id}      用户删除自己的博客
- PUT    /api/user/blog/update           用户编辑自己的博客

路由注册顺序说明：FastAPI 按注册顺序匹配，/query/hot、/query/of/me、
/query/of/user、/query/of/follow 必须先于 /query/{id} 声明，
否则会被 {id} 路径参数捕获（原 Spring 按精确路径优先匹配）。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.common.result import Result
from app.database import get_db
from app.pojo.dto.blog_dtos import BlogUpdateDTO
from app.pojo.entity import Blog
from app.service import blog_service

router = APIRouter(tags=["用户讨论区博客接口"])


class BlogSaveBody(BaseModel):
    """发布博客请求体（对应 @RequestBody Blog 直接实体绑定的可写字段）。

    原实体 userId/icon/name/isLike 为服务端维护或非表字段，不入库映射；
    liked/comments/status 缺省时由 DB 默认值（0/0/1）兜底，与 MyBatis-Plus
    非空插入策略一致。
    """

    id: int | None = None  # 原实体主键绑定（auto_increment，一般不传）
    stockId: str | None = None  # noqa: N815 关联股票代码，多个用","隔开
    title: str | None = None  # 标题
    images: str | None = None  # 照片，最多9张，多张以","隔开
    context: str | None = None  # 正文
    liked: int | None = None  # 点赞数
    comments: int | None = None  # 评论数
    status: int | None = None  # 状态（0: 禁用，1: 正常）
    createTime: str | None = None  # noqa: N815 创建时间（原 LocalDateTime 绑定）
    updateTime: str | None = None  # noqa: N815 修改时间

    def to_entity(self) -> Blog:
        """转为实体（仅非 None 字段参与插入，None 走 DB 默认值）。"""
        kwargs: dict = {}
        for field in ("id", "stockId", "title", "images", "context", "liked", "comments", "status"):
            value = getattr(self, field)
            if value is not None:
                kwargs[("stock_id" if field == "stockId" else field)] = value
        if self.createTime is not None:
            kwargs["create_time"] = datetime.fromisoformat(self.createTime)
        if self.updateTime is not None:
            kwargs["update_time"] = datetime.fromisoformat(self.updateTime)
        return Blog(**kwargs)


@router.post("/api/user/blog")
def save_blog(body: BlogSaveBody, db: Session = Depends(get_db)) -> Result:
    """发布博客（对应 saveBlog）。"""
    blog_service.save_blog(db, body.to_entity())
    return Result.success()


@router.put("/api/user/blog/like/{id}")
def like_blog(id: int, db: Session = Depends(get_db)) -> Result:
    """点赞功能接口（对应 likeBlog，Redis ZSet 点赞集合切换 + 计数）。"""
    blog_service.like_blog(db, id)
    return Result.success()


@router.get("/api/user/blog/query/of/me")
def query_my_blog(
    current: int = 1, size: int = 10, db: Session = Depends(get_db)
) -> Result:
    """分页查看登录用户自己的博客内容（对应 queryMyBlog，defaultValue=1/10）。"""
    records = blog_service.query_my_blog(db, current, size)
    return Result.success(records)


@router.get("/api/user/blog/query/hot")
def query_hot_blog(
    current: int = 1, size: int = 10, db: Session = Depends(get_db)
) -> Result:
    """根据点赞数量（热度）展示博客（对应 queryHotBlog，拦截器放行可匿名）。"""
    blog_list = blog_service.query_hot_blog(db, current, size)
    return Result.success(blog_list)


@router.get("/api/user/blog/query/of/user")
def query_blog_by_user_id(
    current: int = 1, size: int = 10, id: int = ..., db: Session = Depends(get_db)
) -> Result:
    """查看指定用户发的博客（对应 queryBlogByUserId，@RequestParam id 必传）。"""
    records = blog_service.query_blog_by_user_id(db, id, current, size)
    return Result.success(records)


@router.get("/api/user/blog/query/of/follow")
def query_blog_of_follow(
    current: int = 1, size: int = 10, db: Session = Depends(get_db)
) -> Result:
    """粉丝查看关注所有用户博客接口（对应 queryBlogOfFollow，Feed 流收件箱）。

    原 Java 服务层自行兜底 pageNum/pageSize（page<1→1，size 越界→10），
    此处将原始参数透传给服务层。
    """
    page_result = blog_service.query_blog_of_follow(db, current, size)
    return Result.success(page_result)


@router.get("/api/user/blog/query/{id}")
def query_blog_by_id(id: int, db: Session = Depends(get_db)) -> Result:
    """根据id查询博客（对应 queryBlogById，需登录）。"""
    blog = blog_service.query_blog_by_id(db, id)
    return Result.success(blog)


@router.delete("/api/user/blog/delete/{id}")
def delete_my_blog(id: int, db: Session = Depends(get_db)) -> Result:
    """用户删除自己的博客（对应 deleteMyBlog，逻辑删除 + 清理 Redis 缓存）。"""
    blog_service.delete_my_blog(db, id)
    return Result.success()


@router.put("/api/user/blog/update")
def update_my_blog(dto: BlogUpdateDTO, db: Session = Depends(get_db)) -> Result:
    """用户编辑自己的博客（对应 updateMyBlog，@Valid 校验 id 必传）。"""
    blog_service.update_my_blog(db, dto)
    return Result.success()
