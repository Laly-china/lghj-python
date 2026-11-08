-- ============================================================================
-- 智能体扩展表-agent-extension.sql —— ai-agent-server 扩展功能（本工程新增，原 Java 无）
--
-- 用途：AI 投顾终端（agent-web）的会话历史持久化与个人知识库。
-- 说明：与 lghj 主业务 15 张表隔离（agent_* 前缀）；8091 服务启动时会用
--       CREATE TABLE IF NOT EXISTS 幂等建表（app/infrastructure/database.py），
--       本文件为 DDL 存档，手工执行亦可：
--         mysql -h127.0.0.1 -P3306 -uroot -p123456 lghj < sql/智能体扩展表-agent-extension.sql
-- ============================================================================

-- 会话索引表：一条 8091 内存会话对应一行（首个提问截取为标题）
CREATE TABLE IF NOT EXISTS agent_chat_session (
    id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    session_id  VARCHAR(64)  NOT NULL COMMENT '8091 内存会话ID',
    agent_id    VARCHAR(64)  NOT NULL COMMENT '智能体ID（investment-advisor 或专家名）',
    user_id     VARCHAR(64)  NOT NULL COMMENT '用户ID（登录返回的 id 字符串）',
    title       VARCHAR(128) NOT NULL DEFAULT '新对话' COMMENT '会话标题（首条提问截取）',
    create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后活跃时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_session (session_id),
    KEY idx_user_update (user_id, update_time)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '智能体会话索引（扩展表）';

-- 对话消息表：每轮两条（user / assistant），assistant 附本轮执行轨迹 JSON
CREATE TABLE IF NOT EXISTS agent_chat_message (
    id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    session_id  VARCHAR(64)  NOT NULL COMMENT '所属会话ID',
    role        VARCHAR(16)  NOT NULL COMMENT '角色（user/assistant）',
    content     MEDIUMTEXT   NULL COMMENT '消息内容（assistant 为最终答复全文）',
    trace_json  MEDIUMTEXT   NULL COMMENT '本轮执行轨迹 JSON（run_start/llm_call/transfer/tool/agent_text）',
    create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_session (session_id, id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '智能体对话消息（扩展表）';

-- 个人知识库文档表：按用户隔离，逻辑删除；供 queryKnowledgeBase 工具检索
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
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '用户个人知识库文档（扩展表）';
