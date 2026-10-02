"""实体基类与序列化混入。

对应复现原 Java：
- JacksonObjectMapper.java 的 JSON 时间格式（yyyy-MM-dd HH:mm / yyyy-MM-dd）
- MyBatis-Plus map-underscore-to-camel-case + Jackson 序列化（JSON 输出驼峰字段名）

所有实体继承 Base（SQLAlchemy DeclarativeBase）与 SerializationMixin。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def snake_to_camel(name: str) -> str:
    """user_id -> userId（对齐 MyBatis-Plus 下划线转驼峰 + Jackson 输出）。"""
    parts = name.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def jackson_value(value: Any) -> Any:
    """按 JacksonObjectMapper 的规则转换单值。"""
    if isinstance(value, datetime):
        # 原 DEFAULT_DATE_TIME_FORMAT = "yyyy-MM-dd HH:mm"（精确到分）
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        # 原 DEFAULT_DATE_FORMAT = "yyyy-MM-dd"
        return value.strftime("%Y-%m-%d")
    if isinstance(value, Decimal):
        # Jackson 将 BigDecimal 序列化为 JSON 数字
        return float(value)
    return value


class SerializationMixin:
    """为 ORM 实体提供与原 Java Jackson 输出一致的 to_result_dict()。"""

    def to_result_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for column in self.__table__.columns:  # type: ignore[attr-defined]
            value = getattr(self, column.key)
            result[snake_to_camel(column.key)] = jackson_value(value)
        return result


class IdMixin:
    """主键 id（bigint auto_increment，对应 @TableId(type = IdType.AUTO)）。"""

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True)
