"""实体（Entity）。

复现自原 Java 类：
    ai-agent-scaffoid-feng-domain/.../domain/agent/model/entity/ArmoryCommandEntity.java
    ai-agent-scaffoid-feng-domain/.../domain/agent/model/entity/ChatCommandEntity.java
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ArmoryCommandEntity:
    """装配命令实体：装配树各节点间传递的请求参数（照抄原 Java）。"""

    aiAgentConfigTableVO: Any | None = None  # AiAgentConfigTableVO


@dataclass
class ChatTextPart:
    """ChatCommandEntity.Content.Text"""

    message: str | None = None


@dataclass
class ChatFilePart:
    """ChatCommandEntity.Content.File"""

    fileUri: str | None = None
    mimeType: str | None = None


@dataclass
class ChatInlineDataPart:
    """ChatCommandEntity.Content.InlineData"""

    bytes: bytes | None = None
    mimeType: str | None = None


@dataclass
class ChatCommandEntity:
    """对话命令实体：支持文本 + 文件 + 内联数据的多模态对话命令（照抄原 Java）。"""

    agentId: str | None = None
    userId: str | None = None
    sessionId: str | None = None
    texts: list[ChatTextPart] = field(default_factory=list)
    files: list[ChatFilePart] = field(default_factory=list)
    inlineDatas: list[ChatInlineDataPart] = field(default_factory=list)

    @staticmethod
    def build_session_command(agent_id: str, user_id: str) -> "ChatCommandEntity":
        """对应原 Java buildSessionCommand。"""
        return ChatCommandEntity(agentId=agent_id, userId=user_id)

    @staticmethod
    def build_chat_command(agent_id: str, user_id: str, message: str) -> "ChatCommandEntity":
        """对应原 Java buildChatCommand。"""
        return ChatCommandEntity(
            agentId=agent_id,
            userId=user_id,
            texts=[ChatTextPart(message=message)],
        )
