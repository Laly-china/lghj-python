"""管理端-用户管理接口路由。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/admin/UserManageController.java

接口契约（照抄）：
- GET    /api/admin/user                      分页条件查询用户接口
- POST   /api/admin/user/add                  新增用户接口
- DELETE /api/admin/user/{id}                 删除用户接口
- GET    /api/admin/user/{id}                 根据id查询用户接口
- PUT    /api/admin/user/update               更改用户信息接口
- POST   /api/admin/user/changeStatus/{id}    启用禁用用户账号

注意（已知坑点，照抄不统一）：本控制器分页返回 PageResult 结构
{total, totalPage, pageNum, pageSize, list}；其余管理端分页
（/api/admin/blog/page 等）返回 Page 结构 {records, total, ...}。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.result import ErrorEnum, Result
from app.database import get_db
from app.pojo.dto.user_manage_dtos import UserDTO, UserQueryDTO, UserUpdateDTO
from app.service import user_manage_service

router = APIRouter(tags=["管理端-用户管理接口"])


@router.get("/api/admin/user")
def get_user_by_ids(
    dto: UserQueryDTO = Depends(),
    current: int = 1,
    size: int = 10,
    db: Session = Depends(get_db),
) -> Result:
    """分页条件查询用户接口（对应 getUserByIds，@RequestParam defaultValue=1/10）。"""
    page_result = user_manage_service.query_user_page(db, current, size, dto)
    return Result.success(page_result)


@router.post("/api/admin/user/add")
def add_user(dto: UserDTO, db: Session = Depends(get_db)) -> Result:
    """新增用户接口（对应 addUser，@Valid 校验）。"""
    success = user_manage_service.add_user(db, dto)
    return Result.success() if success else Result.error(ErrorEnum.USER_ADD_FAIL)


@router.delete("/api/admin/user/{id}")
def remove_user(id: int, db: Session = Depends(get_db)) -> Result:
    """删除用户接口（对应 removeUser）。"""
    success = user_manage_service.remove_user(db, id)
    return Result.success() if success else Result.error(ErrorEnum.USER_REMOVE_FAIL)


@router.get("/api/admin/user/{id}")
def get_user_by_id(id: int, db: Session = Depends(get_db)) -> Result:
    """根据id查询用户接口（对应 getUserById，枚举名转换后的 VO）。"""
    user_vo = user_manage_service.get_user_by_id(db, id)
    return Result.success(user_vo)


@router.put("/api/admin/user/update")
def update_user(dto: UserUpdateDTO, db: Session = Depends(get_db)) -> Result:
    """更改用户信息接口（对应 updateUser）。"""
    success = user_manage_service.update_user(db, dto)
    return Result.success() if success else Result.error(ErrorEnum.USER_UPDATE_FAIL)


@router.post("/api/admin/user/changeStatus/{id}")
def start_or_stop(id: int, status: int, db: Session = Depends(get_db)) -> Result:
    """启用禁用用户账号（对应 startOrStop，status 为 @RequestParam Short 必传）。"""
    success = user_manage_service.change_user_status(db, id, status)
    msg = "启用账号成功" if status == 1 else "禁用账号成功"
    return Result.success(msg=msg) if success else Result.error(ErrorEnum.USER_STATE_EX_FAIL)
