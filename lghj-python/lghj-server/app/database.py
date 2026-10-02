"""数据库连接模块。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/resources/application-dev.yml（spring.datasource）
- feng-lghj/lghj-server/src/main/java/com/lghj/config/MyBatisConfiguration.java（ORM 配置）

SQLAlchemy 2.0 风格：engine + SessionLocal + get_db 依赖。
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# 创建引擎（对应 MyBatis 的 SqlSessionFactory；pool_pre_ping 对应 autoReconnect=true）
engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_size=settings.mysql_pool_size,
    max_overflow=10,
    pool_recycle=settings.mysql_pool_recycle,
    pool_pre_ping=True,
    echo=False,
)

# 会话工厂（对应 MyBatis 的 SqlSession）
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """全部 ORM 模型的声明基类（对应 MyBatis-Plus 的 BaseEntity 体系）。"""


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：提供数据库会话，请求结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
