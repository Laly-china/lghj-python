"""管理端用户管理业务。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/IUserService.java
- feng-lghj/lghj-server/src/main/java/com/lghj/service/impl/UserServiceImpl.java
- feng-lghj/lghj-server/src/main/java/com/lghj/enums/UserTypeRoleMapEnum.java
  （Sex2Num/Status2Num/UserType2Num 枚举名映射亦在本文件内联照抄）

契约要点：
- 分页返回 PageResult 结构 {total, totalPage, pageNum, pageSize, list}
  （注意：与其它管理端分页的 Page{records, total} 结构不同，照抄不统一）；
- VO 中 sex/userType/status 为枚举转换后的中文名称字符串；
- 原实现多处抛 RuntimeException（如用户名重复）→ 全局兜底 SYSTEM_ERROR，照抄。
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.common.exception import BusinessException
from app.common.result import ErrorEnum
from app.mapper import user_manage_mapper, user_role_mapper
from app.pojo.dto.user_manage_dtos import UserDTO, UserUpdateDTO, UserQueryDTO
from app.pojo.entity import User, UserRole
from app.pojo.vo.user_vo import UserVO

logger = logging.getLogger(__name__)

# ====================== 枚举名映射（对应 enums/Sex2Num、Status2Num、UserType2Num） ======================

_SEX_NAMES = {1: "男", 2: "女"}
_STATUS_NAMES = {0: "禁用", 1: "正常"}
_USER_TYPE_NAMES = {1: "普通用户", 2: "机构用户", 3: "管理员"}


def _convert_state(state: int | None) -> str:
    """对应 EnumConvertUtil.convertState：无匹配返回「未知状态」。"""
    return _STATUS_NAMES.get(state, "未知状态")


def _convert_user_type(user_type: int | None) -> str:
    """对应 EnumConvertUtil.convertUserType。"""
    return _USER_TYPE_NAMES.get(user_type, "未知状态")


def _convert_sex(sex: int | None) -> str:
    """对应 EnumConvertUtil.convertSex。"""
    return _SEX_NAMES.get(sex, "未知状态")


def _get_role_id_by_user_type(user_type: int | None) -> int | None:
    """对应 UserTypeRoleMapEnum.getByUserType：userType=1→1、2→2、3→3（首个匹配）。"""
    mapping = {1: 1, 2: 2, 3: 3}
    if user_type is None:
        return None
    return mapping.get(user_type)


def _is_admin_role(role_id: int | None) -> bool:
    """对应 UserTypeRoleMapEnum.isAdminRole：非 null 且为 3/4/5/6。"""
    return role_id is not None and role_id in (3, 4, 5, 6)


def _format_time(value: datetime | None) -> str | None:
    """时间格式化（JacksonObjectMapper：yyyy-MM-dd HH:mm）。"""
    return value.strftime("%Y-%m-%d %H:%M") if value is not None else None


def _to_vo(user: User) -> UserVO:
    """实体转 VO（对应 BeanUtils.copyProperties + 枚举转换）。

    注意原 VO 无 id 字段；createUser/updateUser 在 Java 侧为 String 类型
    （DB 为 bigint，JDBC getString 输出字符串），此处 str() 保持一致。
    """
    return UserVO(
        username=user.username,
        password=user.password,
        email=user.email,
        phone=user.phone,
        sex=_convert_sex(user.sex),
        userType=_convert_user_type(user.user_type),
        status=_convert_state(user.status),
        createTime=_format_time(user.create_time),
        updateTime=_format_time(user.update_time),
        createUser=str(user.create_user) if user.create_user is not None else None,
        updateUser=str(user.update_user) if user.update_user is not None else None,
        isDeleted=user.is_deleted,
    )


def _parse_query_time(value: str | None, field_label: str) -> datetime | None:
    """查询时间参数解析（原 Spring 绑定 LocalDateTime，ISO 格式）。

    偏差说明：原 Java 仅接受 ISO（T 分隔）格式，此处额外兼容空格分隔的
    "yyyy-MM-dd HH:mm:ss"（前端常用格式），为宽松超集。
    """
    if value is None or value == "":
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise BusinessException(ErrorEnum.PARAM_INVALID, f"{field_label}格式无效") from exc


# ====================== 用户分页条件查询 ======================

def query_user_page(db: Session, current: int, size: int, dto: UserQueryDTO | None) -> dict:
    """用户分页条件查询（对应 queryUserPage，返回 PageResult 结构）。"""
    if dto is not None:
        dto.begin = _parse_query_time(dto.begin, "搜索起始时间")  # type: ignore[assignment]
        dto.end = _parse_query_time(dto.end, "搜索终止时间")  # type: ignore[assignment]

    users, total = user_manage_mapper.select_page_by_condition(db, current, size, dto)
    page_size = max(1, size)
    total_page = (total + page_size - 1) // page_size

    return {
        "total": total,
        "totalPage": total_page,
        "pageNum": max(1, current),
        "pageSize": page_size,
        "list": [_to_vo(user).model_dump() for user in users],
    }


# ====================== 新增用户 ======================

def add_user(db: Session, dto: UserDTO) -> bool:
    """新增用户（对应 addUser，事务语义：失败整体回滚）。"""
    # 兜底参数校验（对应原 @Valid 之外的 Service 层兜底）
    if dto is None:
        raise BusinessException(ErrorEnum.PARAM_NULL)
    if dto.username is None or not dto.username.strip():
        raise BusinessException(ErrorEnum.USERNAME_EMPTY)

    # 业务校验：用户名去重（原抛 RuntimeException → 全局 SYSTEM_ERROR，照抄）
    username_count = _count_username(db, dto.username)
    if username_count > 0:
        logger.error("新增用户失败：用户名 %s 已存在", dto.username)
        raise RuntimeError("新增用户失败，用户名已存在")

    # 实体拷贝（BeanUtils.copyProperties(userDTO, user)，仅非空字段生效）
    user = User(
        username=dto.username,
        password=dto.password,
        nick_name=dto.nickName,  # noqa: N815
        icon=dto.icon,
        email=dto.email,
        phone=dto.phone,
        sex=dto.sex,
        user_type=dto.userType if dto.userType is not None else 1,  # 默认普通用户（1）
        status=dto.status,
    )
    user_save_success = user_manage_mapper.insert_user(db, user)
    if not user_save_success:
        raise BusinessException(ErrorEnum.USER_SAVE_FAIL)
    new_user_id = user.id

    # 用户-角色关联（角色解析失败时整体回滚，对齐原 @Transactional）
    try:
        role_id = _resolve_role_id(dto.userType, dto.roleName)  # noqa: N815
        user_role_mapper.insert_user_role(
            db, UserRole(user_id=new_user_id, role_id=role_id)
        )
    except Exception:
        db.rollback()
        raise
    db.commit()
    logger.info("用户-角色关联表插入成功，用户ID：%s，角色ID：%s", new_user_id, role_id)
    return True


def _resolve_role_id(user_type: int | None, role_name: int | None) -> int:
    """角色解析（对应 addUser/updateUser 中的 userType→role 逻辑）。"""
    if user_type == 3:
        # 判断是否是管理员角色（3/4/5/6）
        if _is_admin_role(role_name):  # noqa: N815
            return role_name  # noqa: N815
        raise BusinessException(ErrorEnum.PARAM_INVALID, "管理员角色不存在")
    role_id = _get_role_id_by_user_type(user_type)
    if role_id is None:
        raise BusinessException(ErrorEnum.PARAM_INVALID, "userType 不合法（仅支持1/2/3）")
    return role_id


def _count_username(db: Session, username: str) -> int:
    """用户名计数（复用 user_mapper 的注册查重语义）。"""
    from app.mapper import user_mapper

    return user_mapper.select_count_by_username(db, username)


# ====================== 删除用户 ======================

def remove_user(db: Session, user_id: int) -> bool:
    """删除用户（对应 removeUser：逻辑删除用户 + 删除用户-角色关联）。"""
    # 参数校验
    if user_id is None:
        raise BusinessException(ErrorEnum.PARAM_NULL)

    # 查询用户是否存在（逻辑删除过滤）
    existing_user = user_manage_mapper.select_by_id(db, user_id)
    if existing_user is None:
        raise BusinessException(ErrorEnum.USER_NOT_EXIST)

    # 删除用户表记录（逻辑删除；原方法无 @Transactional，Mapper 自动提交，
    # 故先提交用户删除，再删关联表——与原 Java 行为一致）
    user_manage_mapper.logic_delete_by_id(db, user_id)
    db.commit()

    # 删除用户-角色关联表记录（按 userId 匹配；0 行视为失败，照抄原判断）
    role_relation_delete_success = user_role_mapper.logic_delete_by_user_id(db, user_id)
    if not role_relation_delete_success:
        raise BusinessException(ErrorEnum.SYSTEM_ERROR, "用户-角色关联记录删除失败")
    db.commit()

    logger.info("用户 %s 及对应的关联角色记录删除成功", user_id)
    return True


# ====================== 根据id查询用户 ======================

def get_user_by_id(db: Session, user_id: int) -> UserVO:
    """根据 id 查询用户（对应 getUserById，枚举名转换）。"""
    user = user_manage_mapper.select_by_id(db, user_id)
    if user is None:
        raise BusinessException(ErrorEnum.USER_NOT_EXIST)
    return _to_vo(user)


# ====================== 修改用户信息 ======================

def update_user(db: Session, dto: UserUpdateDTO) -> bool:
    """修改用户信息（对应 updateUser）。"""
    # 校验参数（ID不能为空，原抛 RuntimeException → SYSTEM_ERROR）
    if dto.id is None:
        raise RuntimeError("用户ID不能为空")

    # 查询用户是否存在
    existing_user = user_manage_mapper.select_by_id(db, dto.id)
    if existing_user is None:
        raise BusinessException(ErrorEnum.USER_NOT_EXIST)

    # 用户类型/角色联动更新（两个参数都传时才处理）
    if dto.userType is not None and dto.roleName is not None:  # noqa: N815
        role_id = _resolve_role_id(dto.userType, dto.roleName)  # noqa: N815
        user_role = user_role_mapper.select_one_by_user_id(db, dto.id)
        if user_role is None:
            # 原 Java getOne 返回 null 后直接 setRoleId 会 NPE → SYSTEM_ERROR，照抄
            db.rollback()
            raise RuntimeError("Cannot invoke method on null user role")
        update_success = user_role_mapper.update_role_id(db, user_role.id, role_id)
        if not update_success:
            db.rollback()
            raise BusinessException(ErrorEnum.SYSTEM_ERROR, "用户-角色关联记录更新失败")

    # 实体拷贝：仅非空字段更新（对应 update-strategy: not_null），自动维护修改时间
    values: dict = {"update_time": datetime.now()}
    field_map = {
        "username": "username",
        "password": "password",
        "nickName": "nick_name",
        "icon": "icon",
        "email": "email",
        "phone": "phone",
        "sex": "sex",
        "userType": "user_type",
        "status": "status",
    }
    for dto_field, column in field_map.items():
        value = getattr(dto, dto_field)
        if value is not None:
            values[column] = value

    success = user_manage_mapper.update_user_fields(db, dto.id, values)
    db.commit()
    return success


# ====================== 启用、禁用用户账号 ======================

def change_user_status(db: Session, user_id: int, status: int) -> bool:
    """启用、禁用用户账号（对应 changeUserStatus）。"""
    # 1. 校验参数（原抛 RuntimeException → SYSTEM_ERROR）
    if user_id is None or status is None:
        raise RuntimeError("用户ID和状态不能为空")
    if status not in (0, 1):
        raise RuntimeError("状态只能是0（禁用）或1（启用）")

    # 2. 查询用户是否存在
    existing_user = user_manage_mapper.select_by_id(db, user_id)
    if existing_user is None:
        raise RuntimeError("用户不存在，无法修改状态")

    # 3/4. 只更新 status 字段（对应 updateById 返回受影响行数 > 0）
    success = user_manage_mapper.update_user_fields(db, user_id, {"status": status})
    db.commit()
    return success
