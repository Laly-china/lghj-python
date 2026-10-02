"""值对象（Value Object）。

复现自原 Java 类：
    ai-agent-scaffoid-feng-domain/.../domain/agent/model/valobj/AiAgentConfigTableVO.java
    ai-agent-scaffoid-feng-domain/.../domain/agent/model/valobj/AiAgentRegisterVO.java
    ai-agent-scaffoid-feng-domain/.../domain/agent/model/valobj/enums/AgentTypeEnum.java
    ai-agent-scaffoid-feng-domain/.../domain/agent/model/valobj/properties/AiAgentAutoConfigProperties.java

字段名与 YAML key 对应（camelCase -> Python 属性 snake_case，同时保留原 JSON/YAML 读取映射）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ====================== AiAgentConfigTableVO 及内部类 ======================

@dataclass
class AgentTableVO:
    """AiAgentConfigTableVO.Agent：智能体概要（agentId/agentName/agentDesc）。"""

    agentId: str | None = None
    agentName: str | None = None
    agentDesc: str | None = None


@dataclass
class AiApiVO:
    """AiAgentConfigTableVO.Module.AiApi：LLM OpenAI 兼容 API 配置。"""

    baseUrl: str | None = None
    apiKey: str | None = None
    completionsPath: str = "/v1/chat/completions"
    embeddingsPath: str = "/v1/embeddings"


@dataclass
class ChatModelVO:
    """AiAgentConfigTableVO.Module.ChatModel：模型与工具配置。"""

    model: str | None = None
    toolMcpList: list[dict[str, Any]] = field(default_factory=list)
    toolSkillsList: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentModuleVO:
    """AiAgentConfigTableVO.Module.Agent：单个专家智能体定义。"""

    name: str | None = None
    instruction: str | None = None
    description: str | None = None
    outputKey: str | None = None


@dataclass
class AgentWorkflowVO:
    """AiAgentConfigTableVO.Module.AgentWorkflow：工作流装配定义（loop/parallel/sequential/supervisor）。"""

    type: str | None = None
    name: str | None = None
    subAgents: list[str] = field(default_factory=list)
    description: str | None = None
    instruction: str | None = None
    outputKey: str | None = None
    maxIterations: int = 3


@dataclass
class RunnerVO:
    """AiAgentConfigTableVO.Module.Runner：执行器配置。"""

    agentName: str | None = None
    pluginNameList: list[str] = field(default_factory=list)


@dataclass
class ModuleVO:
    """AiAgentConfigTableVO.Module：装配模块聚合。"""

    aiApi: AiApiVO = field(default_factory=AiApiVO)
    chatModel: ChatModelVO = field(default_factory=ChatModelVO)
    agents: list[AgentModuleVO] = field(default_factory=list)
    agentWorkflows: list[AgentWorkflowVO] = field(default_factory=list)
    runner: RunnerVO = field(default_factory=RunnerVO)


@dataclass
class AiAgentConfigTableVO:
    """Ai Agent 智能体配置表值对象（YAML 中 tables.<key> 一项）。"""

    appName: str | None = None
    agent: AgentTableVO = field(default_factory=AgentTableVO)
    module: ModuleVO = field(default_factory=ModuleVO)


# ====================== AiAgentRegisterVO ======================

@dataclass
class AiAgentRegisterVO:
    """Ai Agent 智能体注册值对象。

    原 Java 携带 google-adk 的 InMemoryRunner 实例；Python 侧携带自研
    InMemoryRunner（见 domain/agent/service/armory/runner.py），对外语义一致。
    """

    appName: str
    agentId: str
    agentName: str | None
    agentDesc: str | None
    runner: Any  # InMemoryRunner（避免循环 import 用 Any 注解）


# ====================== AgentTypeEnum ======================

class AgentTypeEnum(Enum):
    """工作流装配类型枚举（照抄原 Java AgentTypeEnum）。"""

    Loop = ("循环执行", "loop", "loopAgentNode")
    Parallel = ("并行执行", "parallel", "parallelAgentNode")
    Sequential = ("串行执行", "sequential", "sequentialAgentNode")
    Supervisor = ("层级编排", "supervisor", "supervisorAgentNode")

    def __init__(self, name_cn: str, type_code: str, node: str) -> None:
        self.name_cn = name_cn
        self.type_code = type_code
        self.node = node

    @staticmethod
    def form_type(type_str: str | None) -> "AgentTypeEnum | None":
        """按 type 字符串查枚举（忽略大小写，对齐原 Java formType）。"""
        if type_str is None:
            return None
        for value in AgentTypeEnum:
            if value.type_code.lower() == type_str.lower():
                return value
        return None


# ====================== AiAgentAutoConfigProperties ======================

@dataclass
class AiAgentAutoConfigProperties:
    """智能体自动装配配置属性（对应 ai.agent.config 前缀 + 装配 yml）。"""

    enabled: bool = False
    tables: dict[str, AiAgentConfigTableVO] = field(default_factory=dict)
