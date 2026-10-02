"""登录请求 DTO。

对应复现原 Java pojo/dto/LoginDTO.java。
"""

from __future__ import annotations

from pydantic import BaseModel


class LoginDTO(BaseModel):
    """登录请求体 {username, password}（必填校验对齐 @NotBlank，但原
    LoginController.login 未加 @Valid，故缺参时由业务逻辑返回 20009/20010）。"""

    username: str | None = None
    password: str | None = None
