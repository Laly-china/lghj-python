"""管理端用户信息展示 VO。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/pojo/vo/UserVO.java

忠实复现说明：原 VO **不含 id 字段**（BeanUtils.copyProperties 时被丢弃），
且 sex/userType/status 由枚举转换为中文名称字符串，createUser/updateUser
在 Java 侧为 String 类型（JSON 输出字符串），均照抄。
"""

from __future__ import annotations

from pydantic import BaseModel


class UserVO(BaseModel):
    """管理端用户信息展示 VO（对应 UserVO.java，字段顺序一致）。"""

    username: str | None = None  # 登录用户名
    password: str | None = None  # 密码（原 VO 即明文返回，照抄）
    email: str | None = None  # 邮箱
    phone: str | None = None  # 电话号
    sex: str | None = None  # 性别（枚举转换后的中文名称）
    userType: str | None = None  # noqa: N815 身份标识（枚举转换后的中文名称）
    status: str | None = None  # 状态（枚举转换后的中文名称）
    createTime: str | None = None  # noqa: N815 创建时间（yyyy-MM-dd HH:mm）
    updateTime: str | None = None  # noqa: N815 修改时间（yyyy-MM-dd HH:mm）
    createUser: str | None = None  # noqa: N815 创建人（原 Java String 类型，字符串）
    updateUser: str | None = None  # noqa: N815 修改人
    isDeleted: int | None = None  # noqa: N815 是否已删除（0: 否，1: 是）
