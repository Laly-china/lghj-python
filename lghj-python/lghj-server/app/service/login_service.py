"""登录/注册业务。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/ILoginService.java
- feng-lghj/lghj-server/src/main/java/com/lghj/service/impl/LoginServiceImpl.java

注意：密码为**明文**存储与比对——这是原系统的既有行为（LoginServiceImpl 中
password.equals(user.getPassword())），本工程忠实复现，生产环境切勿模仿。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.common.constants import STATUS_DISABLE, STATUS_ENABLE
from app.common.exception import BusinessException
from app.common.result import ErrorEnum
from app.mapper import user_mapper
from app.pojo.dto import RegisterDTO
from app.pojo.entity import User


def login(db: Session, username: str | None, password: str | None) -> User:
    """用户登录（对应 LoginServiceImpl.login）。"""
    user = user_mapper.select_one_by_username(db, username or "")
    if user is None:
        raise BusinessException(ErrorEnum.USER_NOT_FOUND)

    # 明文比对（原系统行为）
    if password != user.password:
        raise BusinessException(ErrorEnum.PASSWORD_ERROR)

    if user.status == STATUS_DISABLE:
        raise BusinessException(ErrorEnum.ACCOUNT_LOCKED)

    return user


def register(db: Session, dto: RegisterDTO) -> None:
    """用户注册（对应 LoginServiceImpl.register）。"""
    username = dto.username
    count = user_mapper.select_count_by_username(db, username or "")
    if count > 0:
        raise BusinessException(ErrorEnum.USERNAME_EXIST)

    now = datetime.now()
    user = User(
        username=username,
        password=dto.password,  # 明文存储（原系统行为）
        nick_name=dto.nickName if dto.nickName is not None else username,
        email=dto.email,
        phone=dto.phone,
        sex=dto.sex,
        user_type=1,  # UserType2Num.COMMON
        status=STATUS_ENABLE,
        create_time=now,
        update_time=now,
        is_deleted=0,
    )
    affected = user_mapper.insert_user(db, user)
    if affected <= 0:
        raise BusinessException(ErrorEnum.USER_SAVE_FAIL)
    db.commit()
