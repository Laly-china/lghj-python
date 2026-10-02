"""博客模块请求 DTO 集合（新增评论/评论查询/博客编辑）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/pojo/dto/BlogCommentAddDTO.java
- feng-lghj/lghj-server/src/main/java/com/lghj/pojo/dto/BlogCommentQueryDTO.java
- feng-lghj/lghj-server/src/main/java/com/lghj/pojo/dto/BlogUpdateDTO.java

校验规则照抄原 @NotNull/@NotBlank 注解；字段名保持 JSON 驼峰。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class BlogCommentAddDTO(BaseModel):
    """新增博客评论 DTO（一级/二级通用，对应 BlogCommentAddDTO.java）。"""

    # @NotNull 必传字段缺失即校验失败
    model_config = ConfigDict(validate_default=True)

    blogId: int  # noqa: N815 关联博客ID（必传）
    parentId: int = 0  # noqa: N815 父评论ID（一级评论=0，二级评论=一级评论ID）
    content: str | None = None  # 评论内容（必传，非空）

    @field_validator("content")
    @classmethod
    def _content_not_blank(cls, v: str | None) -> str | None:
        # @NotBlank(message = "评论内容不能为空")
        if v is None or not v.strip():
            raise ValueError("评论内容不能为空")
        return v


class BlogUpdateDTO(BaseModel):
    """博客编辑 DTO（对应 BlogUpdateDTO.java，仅包含前端可编辑的字段）。"""

    model_config = ConfigDict(validate_default=True)

    id: int | None = None  # 博客ID（@NotNull(message = "博客ID不能为空")）
    title: str | None = None  # 博客标题
    images: str | None = None  # 照片，最多9张，多张以","隔开

    @field_validator("id")
    @classmethod
    def _id_not_null(cls, v: int | None) -> int | None:
        if v is None:
            raise ValueError("博客ID不能为空")
        return v
