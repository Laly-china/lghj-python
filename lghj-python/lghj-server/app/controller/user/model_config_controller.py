"""用户自配大模型配置接口路由（Python 复现扩展功能，非原 Java）。

cc-switch 风格多模型选择的前端入口，均在 /api/user/** 拦截范围内（需携带
token 请求头，BaseContext 取当前 userId）：
- POST /api/user/model-config/save       保存配置（json body，按名称 upsert）
- POST /api/user/model-config/delete     删除配置（name 为 query 参数）
- POST /api/user/model-config/activate   设为当前使用（name 为 query 参数）
- GET  /api/user/model-config/list       配置列表（api_key 一律打码回显）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.common.context import BaseContext
from app.common.result import ErrorEnum, Result
from app.database import get_db
from app.service import user_model_config_service

router = APIRouter(tags=["模型配置管理接口"])


class ModelConfigSaveDTO(BaseModel):
    """保存配置请求体（camelCase 对齐前端契约）。"""

    name: str  # 配置名称（同用户唯一，重名即覆盖更新）
    baseUrl: str = ""  # noqa: N815 OpenAI 兼容接口地址
    apiKey: str = ""  # noqa: N815 用户的 API Key
    model: str = ""  # 模型名
    completionsPath: str = ""  # noqa: N815 补全路径，空则用默认 /v1/chat/completions


def _require_text(value: str | None) -> bool:
    return value is not None and value.strip() != ""


@router.post("/api/user/model-config/save")
def save(body: ModelConfigSaveDTO, db: Session = Depends(get_db)) -> Result:
    """保存配置（对应前端「保存」按钮，重名覆盖更新）。"""
    if not _require_text(body.name):
        return Result.error(ErrorEnum.PARAM_NULL, "name")
    if not (_require_text(body.baseUrl) and _require_text(body.apiKey) and _require_text(body.model)):
        return Result.error(ErrorEnum.PARAM_INVALID, "baseUrl/apiKey/model 均不能为空")
    user_id = BaseContext.get_current_id()
    ok = user_model_config_service.save_config(db, user_id, body.model_dump())
    return Result.success() if ok else Result.error(ErrorEnum.MODEL_CONFIG_SAVE_FAIL)


@router.post("/api/user/model-config/delete")
def delete_config(name: str, db: Session = Depends(get_db)) -> Result:
    """删除配置（对应前端「删除」按钮）。"""
    user_id = BaseContext.get_current_id()
    ok = user_model_config_service.delete_config(db, user_id, name.strip())
    return Result.success() if ok else Result.error(ErrorEnum.MODEL_CONFIG_NOT_FOUND)


@router.post("/api/user/model-config/activate")
def activate(name: str, db: Session = Depends(get_db)) -> Result:
    """设为当前使用（对应前端「设为当前」按钮，同用户至多一条激活）。"""
    user_id = BaseContext.get_current_id()
    ok = user_model_config_service.activate_config(db, user_id, name.strip())
    return Result.success() if ok else Result.error(ErrorEnum.MODEL_CONFIG_NOT_FOUND)


@router.get("/api/user/model-config/list")
def list_configs(db: Session = Depends(get_db)) -> Result:
    """配置列表（api_key 打码回显，明文永不出主服务）。"""
    user_id = BaseContext.get_current_id()
    return Result.success(user_model_config_service.list_configs(db, user_id))
