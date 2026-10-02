"""博客业务（用户端 + 管理端）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/IBlogService.java
- feng-lghj/lghj-server/src/main/java/com/lghj/service/impl/BlogServiceImpl.java

Redis 结构（键名照抄 RedisConstant，禁止改动）：
- blog:liked:{blogId}        ZSet：member=用户id，score=点赞时间戳（毫秒）
- feed:{userId}              ZSet 收件箱：member=博客id，score=发布时间戳（毫秒）

Feed 流保序：Redis ZSet 逆序区间取 id 后，用 MySQL ORDER BY FIELD(id, ...)
按收件箱顺序回表（照抄原 .last("ORDER BY FIELD(id, ...)") 语义）。
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime

from sqlalchemy.orm import Session

from app.common.community_constants import BLOG_LIKED_KEY, FEED_KEY
from app.common.context import BaseContext
from app.common.exception import BusinessException
from app.common.result import ErrorEnum
from app.mapper import blog_mapper, follow_mapper
from app.pojo.dto.blog_dtos import BlogUpdateDTO
from app.pojo.entity import Blog
from app.utils.redis_client import get_redis

logger = logging.getLogger(__name__)


# ====================== 发布博客 ======================

def save_blog(db: Session, blog: Blog) -> None:
    """发布博客（对应 saveBlog）：落库后推送博客 id 到所有粉丝的 Feed 收件箱。"""
    # 1. 获取登录用户
    user_id = BaseContext.get_current_id()
    if user_id is None:
        raise BusinessException(ErrorEnum.NO_LOGIN)
    blog.user_id = user_id

    # 2. 保存探店博文到数据库（create_time 等空字段走 DB 默认值）
    is_success = blog_mapper.insert_blog(db, blog)
    if not is_success:
        raise BusinessException(ErrorEnum.BLOG_SAVE_FAIL)
    db.commit()

    # 3. 查询笔记作者的所有粉丝（follow_user_id = 作者），逐个推送
    follows = follow_mapper.select_list_by_follow_user_id(db, user_id)
    for follow in follows:
        fan_user_id = follow.user_id
        key = FEED_KEY + str(fan_user_id)
        if blog.id is not None:
            # zadd key blogId score(当前毫秒时间戳)
            get_redis().zadd(key, {str(blog.id): int(time.time() * 1000)})
    if follows:
        logger.info("博客%s已推送到%s个粉丝的Feed收件箱", blog.id, len(follows))


# ====================== 点赞 ======================

def like_blog(db: Session, blog_id: int) -> None:
    """点赞/取消点赞（对应 likeBlog，Redis ZSet 记录点赞集合 + 数据库计数）。

    事务语义：数据库与 Redis 操作一致性（原 @Transactional）。
    """
    # 1. 获取登录用户
    user_id = BaseContext.get_current_id()
    # 2. 判断当前登录用户是否已经点赞
    key = BLOG_LIKED_KEY + str(blog_id)
    score = get_redis().zscore(key, str(user_id))
    if score is None:
        # 3. 未点赞：数据库点赞数+1，成功后 zadd 记录用户
        is_success = blog_mapper.change_liked(db, blog_id, 1)
        if is_success:
            get_redis().zadd(key, {str(user_id): int(time.time() * 1000)})
        db.commit()
    else:
        # 4. 已点赞：数据库点赞数-1，成功后 zrem 移除用户
        is_success = blog_mapper.change_liked(db, blog_id, -1)
        if is_success:
            get_redis().zrem(key, str(user_id))
        db.commit()


def _is_blog_liked(db: Session, blog: Blog, result: dict) -> None:
    """判断当前登录用户是否点赞（对应私有 isBlogLiked，写入序列化 dict）。

    用户未登录（游客访问放行接口）时不查询，isLike 输出 null
    （原 Boolean 字段默认 null，JacksonObjectMapper 未配置 NON_NULL，照抄）。
    """
    user_id = BaseContext.get_current_id()
    if user_id is None:
        result["isLike"] = None
        return
    key = BLOG_LIKED_KEY + str(blog.id)
    score = get_redis().zscore(key, str(user_id))
    result["isLike"] = score is not None


def _query_blog_user(db: Session, blog: Blog, result: dict) -> None:
    """补充博客作者昵称/头像（对应私有 queryBlogUser：setNickName/setIcon）。"""
    from app.mapper import user_manage_mapper

    user = user_manage_mapper.select_by_id(db, blog.user_id)
    # 原 Java user 为 null 时会 NPE（500），此处保持一致不判空
    result["name"] = user.nick_name
    result["icon"] = user.icon


# ====================== 查询 ======================

def query_hot_blog(db: Session, current: int, size: int) -> list[dict]:
    """根据点赞数量（热度）展示博客（对应 queryHotBlog，补充作者与点赞状态）。"""
    records = blog_mapper.select_page_hot(db, current, size)
    result: list[dict] = []
    for blog in records:
        item = blog.to_result_dict()
        _query_blog_user(db, blog, item)
        _is_blog_liked(db, blog, item)
        result.append(item)
    return result


def query_blog_by_id(db: Session, blog_id: int) -> dict:
    """根据 id 查询博客（对应 queryBlogById，补充作者与点赞状态）。"""
    blog = blog_mapper.select_by_id(db, blog_id)
    if blog is None:
        raise BusinessException(ErrorEnum.BLOG_NOT_EXIST)
    item = blog.to_result_dict()
    _query_blog_user(db, blog, item)
    _is_blog_liked(db, blog, item)
    return item


def query_my_blog(db: Session, current: int, size: int) -> list[dict]:
    """分页查看登录用户自己的博客（对应 queryMyBlog，原样返回记录列表）。"""
    user_id = BaseContext.get_current_id()
    records = blog_mapper.select_page_by_user(db, user_id, current, size)
    return [blog.to_result_dict() for blog in records]


def query_blog_by_user_id(db: Session, user_id: int, current: int, size: int) -> list[dict]:
    """查看指定用户发的博客（对应 queryBlogByUserId，原样返回记录列表）。"""
    records = blog_mapper.select_page_by_user(db, user_id, current, size)
    return [blog.to_result_dict() for blog in records]


def query_blog_of_follow(db: Session, page_num: int | None, page_size: int | None) -> dict:
    """粉丝查看关注所有用户博客接口（对应 queryBlogOfFollow：Feed 流收件箱分页）。

    保序语义：ZSet 逆序区间取博客 id → ORDER BY FIELD(id, ...) 回表保持顺序。
    """
    # 1. 参数校验与默认值赋值（PC 端分页参数兜底，照抄原逻辑）
    if page_num is None or page_num < 1:
        page_num = 1
    if page_size is None or page_size < 1 or page_size > 50:  # 限制最大每页条数
        page_size = 10

    # 2. 获取当前登录用户 ID
    user_id = BaseContext.get_current_id()
    key = FEED_KEY + str(user_id)

    # 3. Redis ZSet 按「索引区间」逆序查询（最新的在最前面）
    start_index = (page_num - 1) * page_size
    end_index = page_num * page_size - 1
    blog_id_str_list = get_redis().zrevrange(key, start_index, end_index)
    total = int(get_redis().zcard(key))

    # 4. 非空判断（无数据直接返回空分页结果）
    if not blog_id_str_list:
        return {"total": 0, "totalPage": 0, "pageNum": page_num, "pageSize": page_size, "list": []}

    # 5. 解析博客 id（原 Long.valueOf：非法值抛异常 → 系统错误）
    blog_ids = [int(s) for s in blog_id_str_list]

    # 6. 批量查询数据库，ORDER BY FIELD 保持与 Redis 一致的顺序
    blogs = blog_mapper.select_by_ids_keep_order(db, blog_ids)

    # 7. 补充点赞状态
    result: list[dict] = []
    for blog in blogs:
        item = blog.to_result_dict()
        _is_blog_liked(db, blog, item)
        result.append(item)

    # 8. 封装 PC 端分页结果（计算总页数）
    total_page = 0 if total == 0 else math.ceil(total / page_size)
    return {
        "total": total,
        "totalPage": total_page,
        "pageNum": page_num,
        "pageSize": page_size,
        "list": result,
    }


# ====================== 删除/编辑 ======================

def delete_my_blog(db: Session, blog_id: int) -> None:
    """用户删除自己的博客（对应 deleteMyBlog：逻辑删除 + 清理 Redis 缓存）。"""
    # 1. 登录校验
    user_id = BaseContext.get_current_id()
    if user_id is None:
        raise BusinessException(ErrorEnum.NO_LOGIN, "请先登录再操作")

    # 2. 查询博客，非空校验
    blog = blog_mapper.select_by_id(db, blog_id)
    if blog is None:
        raise BusinessException(ErrorEnum.BLOG_NOT_EXIST, "博客不存在或已被删除")

    # 3. 权限校验：仅发布者可删除
    if blog.user_id != user_id:
        raise BusinessException(ErrorEnum.BLOG_NO_PERMISSION, "无权限删除他人博客")

    # 4. 逻辑删除
    is_delete = blog_mapper.logic_delete_by_id(db, blog_id)
    if not is_delete:
        raise BusinessException(ErrorEnum.BLOG_DEL_FAIL, "博客删除失败")
    db.commit()
    logger.info("用户%s成功逻辑删除博客%s", user_id, blog_id)

    # 5. 同步清理 Redis 中该博客的所有相关缓存（失败仅记日志，不影响主业务）
    _clean_blog_redis_cache(blog_id)


def _clean_blog_redis_cache(blog_id: int) -> None:
    """清理指定博客的所有 Redis 缓存（对应私有 cleanBlogRedisCache）：
    1. 删除点赞 ZSet（blog:liked:{id}）
    2. 从所有用户 Feed 收件箱（feed:*）中移除该博客 id
    """
    blog_id_str = str(blog_id)
    try:
        liked_key = BLOG_LIKED_KEY + str(blog_id)
        get_redis().delete(liked_key)
        logger.info("清理Redis缓存：删除博客%s的点赞ZSet，Key=%s", blog_id, liked_key)

        feed_keys = get_redis().keys(FEED_KEY + "*")
        if feed_keys:
            for feed_key in feed_keys:
                get_redis().zrem(feed_key, blog_id_str)
            logger.info("清理Redis缓存：从%s个用户的关注流中移除博客%s", len(feed_keys), blog_id)
    except Exception as exc:  # noqa: BLE001 缓存清理失败不抛业务异常，仅记日志
        logger.error("清理博客%s的Redis缓存失败，异常信息：%s", blog_id, exc)


def update_my_blog(db: Session, dto: BlogUpdateDTO) -> None:
    """用户编辑自己的博客（对应 updateMyBlog：仅 title/images 可编辑 + 同步修改时间）。"""
    # 1. 登录校验
    user_id = BaseContext.get_current_id()
    if user_id is None:
        raise BusinessException(ErrorEnum.NO_LOGIN, "请先登录再操作")

    # 2. 查询原博客，非空校验
    original_blog = blog_mapper.select_by_id(db, dto.id)
    if original_blog is None:
        raise BusinessException(ErrorEnum.BLOG_NOT_EXIST, "博客不存在或已被删除")

    # 3. 权限校验：仅发布者可编辑
    if original_blog.user_id != user_id:
        raise BusinessException(ErrorEnum.NO_PERMISSION, "无权限编辑他人博客")

    # 4. 属性拷贝（BeanUtil：null 不覆盖）+ 自动维护修改时间
    values: dict = {"update_time": datetime.now()}
    if dto.title is not None:
        values["title"] = dto.title
    if dto.images is not None:
        values["images"] = dto.images

    # 5. 数据库执行更新
    is_update = blog_mapper.update_blog_fields(db, dto.id, values)
    if not is_update:
        raise BusinessException(ErrorEnum.BLOG_UPDATE_FAIL, "博客编辑失败")
    db.commit()
    logger.info("用户%s成功编辑博客%s", user_id, dto.id)


# ====================== 管理端（对应原 admin/BlogManageController 对
# IBlogService 泛型方法的直接调用） ======================

def admin_page(db: Session, page_num: int, page_size: int) -> dict:
    """管理端分页查询博客（对应 blogService.page(page)，无过滤条件无排序，
    返回 MyBatis-Plus Page 结构 {records, total, ...}）。"""
    records = blog_mapper.select_page_all(db, page_num, page_size)
    total = blog_mapper.count_all(db)
    from app.common.mp_page import page_to_dict

    return page_to_dict(records, total, max(1, page_num), page_size)


def admin_remove_by_id(db: Session, blog_id: int) -> bool:
    """管理端删除博客（对应 removeById 逻辑删除；原 Mapper 自动提交，此处显式 commit）。"""
    result = blog_mapper.logic_delete_by_id(db, blog_id)
    db.commit()
    return result


def admin_get_by_id(db: Session, blog_id: int) -> Blog | None:
    """管理端查看博客详情（对应 getById，原样返回实体）。"""
    return blog_mapper.select_by_id(db, blog_id)
