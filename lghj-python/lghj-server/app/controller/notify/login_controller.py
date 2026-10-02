"""登录接口路由（notify 分组）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/notify/LoginController.java

接口契约（照抄）：
- POST /api/login    请求体 {username, password}，返回 LoginVO{token,id,username,userType,identityDesc,state}
- POST /api/register 请求体 {username,password,nickName,email,phone,sex}（@Valid 校验）
- POST /api/logout   无参数，直接返回成功
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.constants import JWT_CLAIMS_USER_ID, JWT_CLAIMS_USER_TYPE
from app.common.result import Result
from app.config import settings
from app.database import get_db
from app.pojo.dto import LoginDTO, RegisterDTO
from app.pojo.vo import LoginVO
from app.service import login_service
from app.utils.jwt_util import create_jwt

router = APIRouter(tags=["用户登录接口"])


def _user_type_name(user_type: int | None) -> str | None:
    """身份描述（对应 UserType2Num.getName）。"""
    mapping = {1: "普通用户", 2: "机构用户", 3: "管理员"}
    if user_type is None:
        return None
    return mapping.get(user_type)


@router.post("/api/login")
def login(body: LoginDTO, db: Session = Depends(get_db)) -> Result:
    """用户登录（对应 LoginController.login）。

    注意：原实现签发 JWT 用的是 **admin** 的 secretKey/ttl（getAdminSecretKey/getAdminTtl），
    claims 为 {userId, userType}，此处照抄。
    """
    user = login_service.login(db, body.username, body.password)

    claims = {JWT_CLAIMS_USER_ID: user.id, JWT_CLAIMS_USER_TYPE: user.user_type}
    token = create_jwt(
        settings.jwt_admin_secret_key,
        settings.jwt_admin_ttl,
        claims,
    )

    login_vo = LoginVO(
        token=token,
        id=user.id,
        username=user.username,
        userType=user.user_type,
        identityDesc=_user_type_name(user.user_type),
        state=user.status,
    )
    return Result.success(login_vo)


@router.post("/api/register")
def register(body: RegisterDTO, db: Session = Depends(get_db)) -> Result:
    """用户注册（对应 LoginController.register，@Valid 校验触发 PARAM_INVALID）。"""
    login_service.register(db, body)
    return Result.success()


@router.post("/api/logout")
def logout() -> Result:
    """员工退出（对应 LoginController.logout，无业务动作直接成功）。"""
    return Result.success()
