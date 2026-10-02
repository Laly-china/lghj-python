"""博客评论区业务（用户端 + 管理端）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/IBlogCommentsService.java
- feng-lghj/lghj-server/src/main/java/com/lghj/service/impl/BlogCommentsServiceImpl.java

Redis 结构（键名照抄 RedisConstant）：
- blog:comment:liked:{commentId}  Set：member=用户id（评论点赞集合，注意与博客点赞
  的 ZSet 结构不同，照抄原实现）
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.common.community_constants import BLOG_COMMENT_LIKED_KEY, LIKED_STATUS, UNLIKED_STATUS
from app.common.context import BaseContext
from app.common.exception import BusinessException
from app.common.result import ErrorEnum
from app.mapper import blog_comments_mapper
from app.pojo.entity import BlogComments
from app.pojo.vo.blog_vos import BlogCommentVO, UserBlogCommentsMessageDTO
from app.utils.redis_client import get_redis

logger = logging.getLogger(__name__)


# ====================== 新增评论 ======================

def add_comment(db: Session, dto) -> None:
    """新增评论（对应 addComment）：一级/二级通用，二级需校验父评论。"""
    # 1. 登录校验
    user_id = BaseContext.get_current_id()
    if user_id is None:
        raise BusinessException(ErrorEnum.NO_LOGIN)

    # 2. 二级评论需校验父评论存在（且是一级评论、状态正常、未删除）
    parent_id = dto.parentId  # noqa: N815
    if parent_id > 0:
        parent_comment = blog_comments_mapper.select_by_id(db, parent_id)
        if (
            parent_comment is None
            or parent_comment.parent_id != 0
            or parent_comment.status == 0
            or parent_comment.is_deleted == 1
        ):
            raise BusinessException(ErrorEnum.BLOG_PARENT_COMMENT_NOT_FOUND, "父评论不存在或已被禁用/删除")
        # 二级评论需与父评论归属同一博客
        if parent_comment.blog_id != dto.blogId:  # noqa: N815
            raise BusinessException(ErrorEnum.BLOG_COMMENT_MISMATCHING, "二级评论与父评论不属于同一博客")

    # 3. 封装评论实体（status 默认正常、liked 初始 0，create_time 走 DB 默认值）
    comment = BlogComments(
        user_id=user_id,
        blog_id=dto.blogId,  # noqa: N815
        parent_id=parent_id,  # noqa: N815
        content=dto.content,
        status=1,
        liked=0,
    )

    # 4. 保存到数据库
    save = blog_comments_mapper.insert_comment(db, comment)
    if not save:
        raise BusinessException(ErrorEnum.BLOG_COMMENT_SAVE_FAIL, "评论发表失败，请稍后再试")
    db.commit()
    logger.info("用户%s成功发表评论，评论ID：%s，博客ID：%s", user_id, comment.id, dto.blogId)  # noqa: N815


# ====================== 评论列表（二级树形） ======================

def query_comment_list(db: Session, blog_id: int, page_num: int, page_size: int) -> dict:
    """查询评论列表（对应 queryCommentList：一级分页 + 批量二级 + 树形组装）。"""
    current_user_id = BaseContext.get_current_id()

    # 1. 分页查询一级评论（parent_id=0、状态正常、未删除，创建时间倒序）
    first_level_comments, total = blog_comments_mapper.select_first_level_page(
        db, blog_id, page_num, page_size
    )
    if not first_level_comments:
        return {"total": 0, "totalPage": 0, "pageNum": page_num, "pageSize": page_size, "list": []}

    # 2. 批量查二级评论（避免 N+1），按父评论分组
    parent_ids = [c.id for c in first_level_comments]
    second_level_comments = blog_comments_mapper.select_second_level(db, blog_id, parent_ids)
    second_level_map: dict[int, list[BlogComments]] = {}
    for comment in second_level_comments:
        second_level_map.setdefault(comment.parent_id, []).append(comment)

    # 3. 组装 VO（含用户信息、点赞状态、二级评论）
    vo_list = _assemble_comment_vo(db, first_level_comments, second_level_map, current_user_id)

    # 4. 封装分页结果（总页数向上取整，对应 IPage.getPages()）
    total_page = (total + page_size - 1) // page_size if page_size > 0 else 0
    return {
        "total": total,
        "totalPage": total_page,
        "pageNum": page_num,
        "pageSize": page_size,
        "list": [vo.model_dump() for vo in vo_list],
    }


def _assemble_comment_vo(
    db: Session,
    first_level_comments: list[BlogComments],
    second_level_map: dict[int, list[BlogComments]],
    current_user_id: int | None,
) -> list[BlogCommentVO]:
    """组装 VO 的私有方法（对应 assembleCommentVO）。"""
    # 1. 批量查用户信息（去重；已删除用户在 Map 中缺失 → user 为 null，照抄原行为）
    user_ids: set[int] = set()
    for c in first_level_comments:
        user_ids.add(c.user_id)
    for comments in second_level_map.values():
        for c in comments:
            user_ids.add(c.user_id)
    user_dtos: dict[int, UserBlogCommentsMessageDTO] = {}
    if user_ids:
        user_rows = _select_users_by_ids(db, sorted(user_ids))
        for user in user_rows:
            user_dtos[user.id] = UserBlogCommentsMessageDTO.from_user(user.id)

    # 2. 组装一级评论 VO + 二级评论 VO
    vo_list: list[BlogCommentVO] = []
    for first in first_level_comments:
        first_vo = BlogCommentVO(
            id=first.id,
            user=user_dtos.get(first.user_id),
            parentId=first.parent_id,  # noqa: N815
            content=first.content,
            liked=first.liked,
            isLiked=_get_liked_status(first.id, current_user_id),  # noqa: N815
            createTime=first.create_time.strftime("%Y-%m-%d %H:%M") if first.create_time else None,  # noqa: N815
        )
        # 挂载二级评论（无二级时 children 保持 null，照抄原行为）
        second_list = second_level_map.get(first.id)
        if second_list:
            first_vo.children = [
                BlogCommentVO(
                    id=second.id,
                    user=user_dtos.get(second.user_id),
                    parentId=second.parent_id,  # noqa: N815
                    content=second.content,
                    liked=second.liked,
                    isLiked=_get_liked_status(second.id, current_user_id),  # noqa: N815
                    createTime=second.create_time.strftime("%Y-%m-%d %H:%M") if second.create_time else None,  # noqa: N815
                )
                for second in second_list
            ]
        vo_list.append(first_vo)
    return vo_list


def _select_users_by_ids(db: Session, user_ids: list[int]):
    """批量查询用户（对应 userService.listByIds，逻辑删除自动过滤）。

    原实现查询失败/用户不存在时 Map 缺项 → VO.user = null，此处等价。
    """
    if not user_ids:
        return []
    from app.mapper import user_manage_mapper

    return user_manage_mapper.select_by_ids(db, user_ids)


# ====================== 评论点赞 ======================

def like_comment(db: Session, comment_id: int) -> None:
    """评论点赞/取消点赞（对应 likeComment：Redis Set + 数据库计数）。

    注意：原实现点赞数为「读出的旧值 ± 1」绝对值回写，非原子自增，照抄。
    """
    # 1. 登录校验
    user_id = BaseContext.get_current_id()
    if user_id is None:
        raise BusinessException(ErrorEnum.NO_LOGIN)
    liked_key = BLOG_COMMENT_LIKED_KEY + str(comment_id)

    # 2. 校验评论是否存在（正常状态、未删除）
    comment = blog_comments_mapper.select_by_id(db, comment_id)
    if comment is None or comment.status == 0 or comment.is_deleted == 1:
        raise BusinessException(ErrorEnum.BLOG_COMMENT_NOT_FOUND, "评论不存在或已被禁用/删除")

    # 3. 判断当前用户是否已点赞（Redis Set 成员判断）
    is_liked = get_redis().sismember(liked_key, str(user_id))
    if is_liked:
        # 已点赞：取消点赞，Redis 移除用户ID，数据库点赞数-1
        get_redis().srem(liked_key, str(user_id))
        blog_comments_mapper.change_liked(db, comment_id, comment.liked - 1)
        logger.info("用户%s取消点赞评论%s", user_id, comment_id)
    else:
        # 未点赞：点赞，Redis 添加用户ID，数据库点赞数+1
        get_redis().sadd(liked_key, str(user_id))
        blog_comments_mapper.change_liked(db, comment_id, comment.liked + 1)
        logger.info("用户%s点赞评论%s", user_id, comment_id)
    db.commit()


# ====================== 删除评论 ======================

def delete_comment(db: Session, comment_id: int) -> None:
    """删除评论（对应 deleteComment：逻辑删除，一级评论级联删二级 + 清理点赞缓存）。"""
    # 1. 登录校验
    user_id = BaseContext.get_current_id()
    if user_id is None:
        raise BusinessException(ErrorEnum.NO_LOGIN)

    # 2. 校验评论是否存在
    comment = blog_comments_mapper.select_by_id(db, comment_id)
    if comment is None or comment.is_deleted == 1:
        raise BusinessException(ErrorEnum.BLOG_COMMENT_NOT_FOUND, "评论不存在或已被删除")
    blog_id = comment.blog_id

    # 3. 权限校验：原 Java 查出博客仅做存在性校验（发布者/管理员校验未实现，照抄）
    blog = _select_blog_by_id(db, blog_id)
    if blog is None:
        raise BusinessException(ErrorEnum.BLOG_NOT_EXIST, "评论所属博客不存在")

    need_clean_comment_ids: list[int] = []  # 需清理缓存的评论ID集合
    if comment.parent_id == 0:  # 是一级评论，级联删二级评论
        # 3.1 查询该一级评论下的所有二级评论（未删除）
        second_level_comments = blog_comments_mapper.select_second_level_by_parent(
            db, comment_id, blog_id
        )
        if second_level_comments:
            # 3.2/3.3 批量逻辑删除二级评论
            second_level_ids = [c.id for c in second_level_comments]
            need_clean_comment_ids.extend(second_level_ids)
            delete_second = blog_comments_mapper.logic_delete_by_ids(db, second_level_ids)
            if not delete_second:
                raise BusinessException(ErrorEnum.BLOG_COMMENT_DELETE_FAIL, "二级评论删除失败，操作终止")
            logger.info("级联删除一级评论%s的所有二级评论，共%s条", comment_id, len(second_level_ids))

    # 4. 逻辑删除当前评论
    need_clean_comment_ids.append(comment_id)
    remove_current = blog_comments_mapper.logic_delete_by_id(db, comment_id)
    if not remove_current:
        raise BusinessException(ErrorEnum.BLOG_COMMENT_DELETE_FAIL, "评论删除失败，请稍后再试")
    db.commit()

    # 5. 清理 Redis 点赞缓存
    for comment_id_to_clean in need_clean_comment_ids:
        get_redis().delete(BLOG_COMMENT_LIKED_KEY + str(comment_id_to_clean))
    logger.info("批量清理Redis缓存：共清理%s条评论的点赞Key，评论ID：%s", len(need_clean_comment_ids), need_clean_comment_ids)


# ====================== 管理端（对应原 admin/BlogCommentsManageController） ======================

def admin_page(db: Session, page_num: int, page_size: int, blog_id: int | None) -> dict:
    """管理端分页查询评论（对应 page(page, wrapper)，返回 Page 结构）。"""
    records, total = blog_comments_mapper.select_page_all(db, page_num, page_size, blog_id)
    from app.common.mp_page import page_to_dict

    return page_to_dict(records, total, max(1, page_num), page_size)


def admin_remove_by_id(db: Session, comment_id: int) -> bool:
    """管理端删除评论（对应 removeById 逻辑删除；原 Mapper 自动提交，此处显式 commit）。"""
    result = blog_comments_mapper.logic_delete_by_id(db, comment_id)
    db.commit()
    return result


# ====================== 私有工具 ======================

def _get_liked_status(comment_id: int, user_id: int | None) -> int:
    """获取当前用户对指定评论的点赞状态（对应 getLikedStatus，游客为未点赞）。"""
    if user_id is None:
        return UNLIKED_STATUS
    liked_key = BLOG_COMMENT_LIKED_KEY + str(comment_id)
    is_liked = get_redis().sismember(liked_key, str(user_id))
    return LIKED_STATUS if is_liked else UNLIKED_STATUS


def _select_blog_by_id(db: Session, blog_id: int):
    """按 id 查询博客（对应 blogService.getById，逻辑删除自动过滤）。"""
    from app.mapper import blog_mapper

    return blog_mapper.select_by_id(db, blog_id)
