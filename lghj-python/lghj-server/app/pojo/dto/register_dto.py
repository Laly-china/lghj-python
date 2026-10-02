"""注册请求 DTO。

对应复现原 Java pojo/dto/RegisterDTO.java（@Valid 校验规则照抄：
用户名/密码 @NotBlank，邮箱/手机号 @Pattern 正则）。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class RegisterDTO(BaseModel):
    """注册请求体。"""

    # 缺参（字段缺失走默认值 None）也要触发 @NotBlank 校验，对齐原 @Valid 行为
    model_config = ConfigDict(validate_default=True)

    username: str | None = None
    password: str | None = None
    nickName: str | None = None  # noqa: N815 JSON 字段名照原 Java（驼峰）
    email: str | None = None
    phone: str | None = None
    sex: int | None = None

    @field_validator("username")
    @classmethod
    def _username_not_blank(cls, v: str | None) -> str | None:
        # @NotBlank(message = "用户名不能为空")：null 或纯空白均视为校验失败
        if v is None or not v.strip():
            raise ValueError("用户名不能为空")
        return v

    @field_validator("password")
    @classmethod
    def _password_not_blank(cls, v: str | None) -> str | None:
        # @NotBlank(message = "密码不能为空")：null 或纯空白均视为校验失败
        if v is None or not v.strip():
            raise ValueError("密码不能为空")
        return v

    @field_validator("email")
    @classmethod
    def _email_pattern(cls, v: str | None) -> str | None:
        # @Pattern：null 合法，非 null 必须全匹配正则（含空串，对齐 javax 校验语义）
        if v is None:
            return v
        import re

        if not re.fullmatch(r"[a-zA-Z0-9_\-]+@[a-zA-Z0-9_\-]+(\.[a-zA-Z0-9_\-]+)+", v):
            raise ValueError("邮箱格式不正确")
        return v

    @field_validator("phone")
    @classmethod
    def _phone_pattern(cls, v: str | None) -> str | None:
        # @Pattern：null 合法，非 null 必须全匹配正则（含空串）
        if v is None:
            return v
        import re

        if not re.fullmatch(r"1[3-9]\d{9}", v):
            raise ValueError("手机号格式不正确")
        return v
