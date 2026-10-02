"""对外接口数据传输对象（DTO）。

复现自原 Java 类：
    ai-agent-scaffoid-feng/ai-agent-scaffoid-feng-api/src/main/java/cn/feng/api/dto/*.java
        - ChatRequestDTO          对话请求
        - ChatResponseDTO         对话响应
        - CreateSessionRequestDTO 创建会话请求
        - CreateSessionResponseDTO创建会话响应
        - AiAgentConfigResponseDTO智能体配置响应

字段名严格照抄原 Java（JSON 契约）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequestDTO(BaseModel):
    """对话请求体（照抄原 Java ChatRequestDTO）。

    原 Java 无 @NotNull 校验，字段均可缺省（None），缺失时由业务逻辑处理。
    """

    agentId: str | None = None
    userId: str | None = None
    sessionId: str | None = None
    message: str | None = None


class ChatResponseDTO(BaseModel):
    """对话响应体（照抄原 Java ChatResponseDTO）。"""

    content: str | None = None


class CreateSessionRequestDTO(BaseModel):
    """创建会话请求体（照抄原 Java CreateSessionRequestDTO）。"""

    agentId: str | None = None
    userId: str | None = None


class CreateSessionResponseDTO(BaseModel):
    """创建会话响应体（照抄原 Java CreateSessionResponseDTO）。"""

    sessionId: str | None = None


class AiAgentConfigResponseDTO(BaseModel):
    """智能体配置响应体（照抄原 Java AiAgentConfigResponseDTO）。"""

    agentId: str | None = Field(default=None, description="智能体ID")
    agentName: str | None = Field(default=None, description="智能体名称")
    agentDesc: str | None = Field(default=None, description="智能体描述")
