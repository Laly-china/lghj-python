"""登录返回 VO。

对应复现原 Java pojo/vo/LoginVO.java。
"""

from __future__ import annotations

from pydantic import BaseModel


class LoginVO(BaseModel):
    """登录返回体 {token, id, username, userType, identityDesc, state}。"""

    token: str
    id: int
    username: str
    userType: int  # noqa: N815 身份类型
    identityDesc: str | None  # noqa: N815 身份描述（"普通用户"/"机构用户"/"管理员"）
    state: int  # 账号状态（0=禁用，1=正常）
