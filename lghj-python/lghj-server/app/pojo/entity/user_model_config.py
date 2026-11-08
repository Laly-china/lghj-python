"""用户自配大模型配置表实体。

非原 Java 表：Python 复现工程扩展功能（cc-switch 风格多模型选择，用户自配
多个 OpenAI 兼容提供商并一键切换）。唯一键 (user_id, name)；api_key 仅服务端
内部使用，对外接口一律打码回显（见 user_model_config_service.mask_key）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, text, func
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.pojo.entity.base import SerializationMixin


class UserModelConfig(Base, SerializationMixin):
    """用户自配大模型配置表。"""

    __tablename__ = "user_model_config"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="idx_user_name"),  # 同用户配置名唯一
        {"comment": "用户自配大模型配置表"},
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # 配置名称
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)  # OpenAI 兼容接口地址
    api_key: Mapped[str] = mapped_column(String(255), nullable=False)  # 用户 API Key（不外显明文）
    model: Mapped[str] = mapped_column(String(100), nullable=False)  # 模型名
    completions_path: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default="/v1/chat/completions"
    )  # 补全路径（用于推导 api_base）
    is_active: Mapped[int] = mapped_column(
        TINYINT, nullable=False, server_default=text("0")
    )  # 是否当前使用（0/1，同用户至多一条为 1）
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
