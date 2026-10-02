"""管理端用户模块请求 DTO 集合（新增/查询/修改用户）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/pojo/dto/UserDTO.java
- feng-lghj/lghj-server/src/main/java/com/lghj/pojo/dto/UserQueryDTO.java
- feng-lghj/lghj-server/src/main/java/com/lghj/pojo/dto/UserUpdateDTO.java

校验规则照抄原 @NotNull/@NotBlank 注解；字段名保持 JSON 驼峰。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class UserDTO(BaseModel):
    """新增用户请求体（对应 UserDTO.java，@Valid 校验）。"""

    model_config = ConfigDict(validate_default=True)

    username: str | None = None  # @NotBlank(message = "用户名不能为空")
    password: str | None = None  # @NotBlank(message = "密码不能为空")
    nickName: str | None = None  # noqa: N815 昵称
    icon: str | None = None  # 头像
    email: str | None = None  # 邮箱
    phone: str | None = None  # 电话号
    sex: int | None = None  # 性别（1: 男，2: 女）
    userType: int | None = None  # noqa: N815 @NotNull 身份标识（1: 普通用户，2: 机构用户，3: 管理员）
    status: int | None = None  # 状态（0: 禁用，1: 正常）
    roleName: int | None = None  # noqa: N815 管理员等级

    @field_validator("username")
    @classmethod
    def _username_not_blank(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            raise ValueError("用户名不能为空")
        return v

    @field_validator("password")
    @classmethod
    def _password_not_blank(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            raise ValueError("密码不能为空")
        return v

    @field_validator("userType")
    @classmethod
    def _user_type_not_null(cls, v: int | None) -> int | None:
        # @NotNull(message = "身份标识不能为空")
        if v is None:
            raise ValueError("身份标识不能为空")
        return v


class UserQueryDTO(BaseModel):
    """管理端用户分页查询参数（对应 UserQueryDTO.java，Spring query 绑定）。"""

    username: str | None = None
    nickName: str | None = None  # noqa: N815
    icon: str | None = None
    email: str | None = None
    phone: str | None = None
    sex: int | None = None
    userType: int | None = None  # noqa: N815
    status: int | None = None
    begin: str | None = None  # 搜索起始时间（原 LocalDateTime，见 service 层解析）
    end: str | None = None  # 搜索终止时间
    isDeleted: int | None = None  # noqa: N815 是否已删除（0: 否，1: 是）


class UserUpdateDTO(BaseModel):
    """修改用户请求体（对应 UserUpdateDTO.java）。"""

    model_config = ConfigDict(validate_default=True)

    id: int | None = None  # @NotNull(message = "用户id不能为空")
    username: str | None = None
    password: str | None = None
    nickName: str | None = None  # noqa: N815
    icon: str | None = None
    email: str | None = None
    phone: str | None = None
    sex: int | None = None
    userType: int | None = None  # noqa: N815
    status: int | None = None
    roleName: int | None = None  # noqa: N815

    @field_validator("id")
    @classmethod
    def _id_not_null(cls, v: int | None) -> int | None:
        # @NotNull(message = "用户id不能为空")
        if v is None:
            raise ValueError("用户id不能为空")
        return v
