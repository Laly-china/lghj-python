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


# ====================== 专家团（Expert Team，本系统扩展能力） ======================

class ExpertTeamMemberDTO(BaseModel):
    """专家团成员（角色固定，仅权重可调）。"""

    key: str = Field(description="成员标识（对应 sub-agent 名称）")
    name: str = Field(description="成员角色名")
    desc: str = Field(description="职责说明")
    outputKey: str | None = Field(default=None, description="输出键名")
    weight: int = Field(default=0, description="权重（0~100，合计 100）")


class ExpertTeamConfigResponseDTO(BaseModel):
    """专家团配置响应体。"""

    userId: str | None = Field(default=None, description="用户ID")
    memberCount: int = Field(default=0, description="成员人数（固定）")
    editable: bool = Field(default=True, description="是否可编辑（仅权重可改）")
    isCustom: bool = Field(default=False, description="是否已自定义过权重")
    totalWeight: int = Field(default=100, description="权重合计（恒为 100）")
    members: list[ExpertTeamMemberDTO] = Field(default_factory=list, description="成员列表")


class ExpertTeamWeightUpdateRequestDTO(BaseModel):
    """专家团权重更新请求体：{userId, weights:{roleKey: weight}}。"""

    userId: str | None = None
    weights: dict[str, int] | None = None
