"""博客模块响应 VO 集合（评论树/评论用户信息）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/pojo/vo/BlogCommentVO.java
- feng-lghj/lghj-server/src/main/java/com/lghj/pojo/dto/UserBlogCommentsMessageDTO.java

忠实复现说明：原 Java 用 hutool BeanUtil.copyProperties(user, UserBlogCommentsMessageDTO)
做实体转换，User 实体属性为 nickName/icon，与 DTO 的 nickname/avatar **名称不匹配**
（hutool 默认大小写敏感、无别名映射），故 nickname/avatar 恒为 null——这是原系统
既有行为，本工程照抄，不"顺手修复"。
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel


class UserBlogCommentsMessageDTO(BaseModel):
    """简易用户 DTO（评论/博客展示用，对应 UserBlogCommentsMessageDTO.java）。"""

    id: int | None = None
    nickname: str | None = None  # 原转换不生效，恒为 None（见模块 docstring）
    avatar: str | None = None  # 原转换不生效，恒为 None（见模块 docstring）

    @classmethod
    def from_user(cls, user_id: int) -> Self:
        """对应 BeanUtil.copyProperties(user, UserBlogCommentsMessageDTO.class) 的实际效果。

        仅 id 属性名匹配被拷贝；nickname/avatar 因源实体属性名为 nickName/icon
        而未被拷贝，保持 None。
        """
        return cls(id=user_id, nickname=None, avatar=None)


class BlogCommentVO(BaseModel):
    """博客评论展示 VO（含发布者信息+点赞状态+二级评论，对应 BlogCommentVO.java）。"""

    id: int | None = None  # 评论ID
    user: UserBlogCommentsMessageDTO | None = None  # 评论发布者信息
    parentId: int | None = None  # noqa: N815 父评论ID（一级=0）
    content: str | None = None  # 评论内容
    liked: int | None = None  # 点赞数量
    isLiked: int = 0  # noqa: N815 当前登录用户是否点赞（1=是，0=否；游客为0）
    createTime: str | None = None  # noqa: N815 创建时间（yyyy-MM-dd HH:mm，Jackson 格式）
    children: list["BlogCommentVO"] | None = None  # 二级评论列表（一级评论专属，二级评论为null）
