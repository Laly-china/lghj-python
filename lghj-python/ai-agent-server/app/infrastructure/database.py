"""扩展存储连接（本工程扩展，原 Java 无）。

会话历史（agent_chat_session / agent_chat_message）与个人知识库（agent_kb_doc）
复用主控的 MySQL lghj 库，表名 agent_* 前缀与主服务 15 张业务表隔离；
DDL 与 sql/智能体扩展表-agent-extension.sql 一致，服务启动时幂等建表
（CREATE TABLE IF NOT EXISTS），无需手工执行脚本。
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import load_settings

logger = logging.getLogger(__name__)

_engine = None
_sessionmaker: sessionmaker | None = None

# 与 sql/智能体扩展表-agent-extension.sql 保持一致
_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS agent_chat_session (
        id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键ID',
        session_id  VARCHAR(64)  NOT NULL COMMENT '8091 内存会话ID',
        agent_id    VARCHAR(64)  NOT NULL COMMENT '智能体ID（队长或专家名）',
        user_id     VARCHAR(64)  NOT NULL COMMENT '用户ID（登录返回的 id 字符串）',
        title       VARCHAR(128) NOT NULL DEFAULT '新对话' COMMENT '会话标题（首条提问截取）',
        create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
        update_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后活跃时间',
        PRIMARY KEY (id),
        UNIQUE KEY uk_session (session_id),
        KEY idx_user_update (user_id, update_time)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='智能体会话索引（扩展表）'
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_chat_message (
        id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键ID',
        session_id  VARCHAR(64)  NOT NULL COMMENT '所属会话ID',
        role        VARCHAR(16)  NOT NULL COMMENT '角色（user/assistant）',
        content     MEDIUMTEXT   NULL COMMENT '消息内容（assistant 为最终答复全文）',
        trace_json  MEDIUMTEXT   NULL COMMENT '本轮执行轨迹 JSON（run_start/llm_call/transfer/tool/agent_text）',
        create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
        PRIMARY KEY (id),
        KEY idx_session (session_id, id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='智能体对话消息（扩展表）'
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_kb_doc (
        id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键ID',
        user_id     VARCHAR(64)  NOT NULL COMMENT '所属用户ID',
        title       VARCHAR(200) NOT NULL COMMENT '文档标题（默认取文件名去扩展名）',
        filename    VARCHAR(255) NULL COMMENT '原始文件名',
        content     MEDIUMTEXT   NOT NULL COMMENT '文档正文（纯文本）',
        char_count  INT          NOT NULL DEFAULT 0 COMMENT '字符数',
        is_deleted  TINYINT      NOT NULL DEFAULT 0 COMMENT '是否已删除（0: 否，1: 是）',
        create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '上传时间',
        PRIMARY KEY (id),
        KEY idx_user (user_id, is_deleted)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户个人知识库文档（扩展表）'
    """,
]


def get_engine():
    """懒加载引擎（首次使用时建连）。"""
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_engine(
            load_settings().agent_database_url,
            pool_size=5,
            max_overflow=5,
            pool_recycle=3600,
            pool_pre_ping=True,
        )
        _sessionmaker = sessionmaker(bind=_engine)
    return _engine


def get_sessionmaker() -> sessionmaker:
    """懒加载会话工厂（首次使用时建连，不阻断服务导入期）。"""
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


@contextmanager
def session_tx() -> Iterator[Session]:
    """事务会话上下文：进入开启事务，正常退出提交、异常回滚，退出必关连接。"""
    session = get_sessionmaker()()
    try:
        with session.begin():
            yield session
    finally:
        session.close()


def ensure_tables() -> None:
    """幂等创建扩展表（应用启动钩子调用；失败仅告警，不阻断装配）。"""
    try:
        with get_engine().begin() as conn:
            for ddl in _DDL_STATEMENTS:
                conn.execute(text(ddl))
        logger.info("智能体扩展表就绪（agent_chat_session / agent_chat_message / agent_kb_doc）")
    except Exception:  # noqa: BLE001 MySQL 不可用时历史/知识库降级为不可用，服务继续
        logger.error("扩展表创建失败（历史与知识库功能将不可用）", exc_info=True)
