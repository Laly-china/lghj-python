"""用户自配大模型配置服务（Python 复现扩展功能，非原 Java）。

cc-switch 风格多模型选择：用户可保存多个 OpenAI 兼容提供商配置
（名称/base_url/api_key/模型名），并一键切换当前使用的配置。

隐私约束：
- api_key 明文只落本表（服务器本地 MySQL），面向浏览器的接口一律打码回显；
- 明文仅经 internal API（X-Internal-Token）提供给 8091 按用户路由模型时使用。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.mapper import user_model_config_mapper as mapper
from app.pojo.entity import UserModelConfig

# 允许的配置字段（对齐前端保存契约，camelCase）
_SAVE_FIELDS = ("baseUrl", "apiKey", "model", "completionsPath")
_DEFAULT_COMPLETIONS_PATH = "/v1/chat/completions"


def mask_key(key: str) -> str:
    """API Key 打码：保留前 2 后 4，中段以 **** 代替（短 key 只留 ****）。"""
    key = key or ""
    if len(key) > 8:
        return f"{key[:2]}****{key[-4:]}"
    return "****"


def list_configs(db: Session, user_id: int) -> list[dict]:
    """查询用户全部配置（camelCase VO，api_key 打码）。"""
    result: list[dict] = []
    for c in mapper.select_list_by_user(db, user_id):
        result.append(
            {
                "id": c.id,
                "name": c.name,
                "baseUrl": c.base_url,
                "apiKey": mask_key(c.api_key),
                "model": c.model,
                "completionsPath": c.completions_path,
                "isActive": int(c.is_active or 0),
                "updateTime": c.update_time.strftime("%Y-%m-%d %H:%M:%S") if c.update_time else None,
            }
        )
    return result


def save_config(db: Session, user_id: int, data: dict) -> bool:
    """保存配置（按 user_id+name upsert；新建默认非激活）。字段已由控制器校验非空。"""
    name = str(data.get("name") or "").strip()
    values = {f: str(data.get(f) or "").strip() for f in _SAVE_FIELDS}
    if not values["completionsPath"]:
        values["completionsPath"] = _DEFAULT_COMPLETIONS_PATH
    try:
        existing = mapper.select_by_user_and_name(db, user_id, name)
        if existing is not None:
            existing.base_url = values["baseUrl"]
            existing.api_key = values["apiKey"]
            existing.model = values["model"]
            existing.completions_path = values["completionsPath"]
        else:
            mapper.insert_config(
                db,
                UserModelConfig(
                    user_id=user_id,
                    name=name,
                    base_url=values["baseUrl"],
                    api_key=values["apiKey"],
                    model=values["model"],
                    completions_path=values["completionsPath"],
                    is_active=0,
                ),
            )
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


def delete_config(db: Session, user_id: int, name: str) -> bool:
    """删除配置（存在才删），提交并返回是否删除成功。"""
    try:
        rows = mapper.delete_by_user_and_name(db, user_id, name)
        db.commit()
        return rows > 0
    except Exception:
        db.rollback()
        return False


def activate_config(db: Session, user_id: int, name: str) -> bool:
    """激活某条配置（先清同用户其它激活位，保证至多一条 is_active=1）。"""
    try:
        target = mapper.select_by_user_and_name(db, user_id, name)
        if target is None:
            return False
        mapper.clear_active_by_user(db, user_id)
        target.is_active = 1
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


def get_active_plain(db: Session, user_id: int) -> dict | None:
    """查询用户当前激活配置（**明文 key**，仅供 internal API 给 8091 使用）。"""
    c: UserModelConfig | None = mapper.select_active_by_user(db, user_id)
    if c is None:
        return None
    return {
        "name": c.name,
        "baseUrl": c.base_url,
        "apiKey": c.api_key,
        "model": c.model,
        "completionsPath": c.completions_path,
    }
