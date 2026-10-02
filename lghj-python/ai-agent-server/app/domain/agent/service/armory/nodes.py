"""装配树节点链。

复现自原 Java 类（ai-agent-scaffoid-feng-domain/.../armory/node/）：
    RootNode.java            根节点：路由到 AiApiNode
    AiApiNode.java           构建 OpenAiApi（baseUrl/apiKey/completionsPath）
    ChatModelNode.java       构建 OpenAiChatModel（挂载 tool-mcp-list / tool-skills-list 工具）
    AgentNode.java           构建 LlmAgent 列表（instruction/outputKey）
    AgentWorkflowNode.java   按 type 路由 loop/parallel/sequential/supervisor
    workflow/LoopAgentNode.java / ParallelAgentNode.java / SequentialAgentNode.java / SupervisorAgentNode.java
    RunnerNode.java          构建 InMemoryRunner 并注册 bean（bean 名 = agentId）

装配链：Root -> AiApi -> ChatModel -> Agent -> AgentWorkflow(可多步循环) -> Runner
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.config import Settings
from app.domain.agent.adapter.model.entity import ArmoryCommandEntity
from app.domain.agent.adapter.model.valobj import (
    AgentModuleVO,
    AgentTypeEnum,
    AiAgentConfigTableVO,
    AiAgentRegisterVO,
)
from app.domain.agent.service.armory.factory import DynamicContext
from app.domain.agent.service.armory.model_client import LiteLlmClient
from app.domain.agent.service.armory.runtime import (
    ChatModel,
    InMemoryRunner,
    LlmAgent,
    LoopAgent,
    ParallelAgent,
    SequentialAgent,
    ToolSpec,
)
from app.types.app_exception import AppException
from app.types.response_code import ResponseCode

logger = logging.getLogger(__name__)


class AbstractArmoryNode(ABC):
    """装配节点基类（对应原 Java AbstractArmorySupport + StrategyHandler 路由）。"""

    @abstractmethod
    def do_apply(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AiAgentRegisterVO | None:
        """执行本节点装配逻辑，返回最终结果或 None（None 表示继续路由下一节点）。"""
        raise NotImplementedError

    @abstractmethod
    def get(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> "AbstractArmoryNode | None":
        """路由到下一个节点；返回 None 表示装配结束。"""
        raise NotImplementedError

    def apply(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AiAgentRegisterVO | None:
        """模板方法：先执行本节点，再路由下一节点（对齐 StrategyHandler.apply + router）。"""
        result = self.do_apply(command, ctx)
        if result is not None:
            return result
        next_node = self.get(command, ctx)
        if next_node is None:
            return None
        return next_node.apply(command, ctx)


class RootNode(AbstractArmoryNode):
    """根节点（照抄原 Java RootNode：直接路由到 AiApiNode）。"""

    def __init__(self, ai_api_node: "AiApiNode") -> None:
        self._ai_api_node = ai_api_node

    def do_apply(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AiAgentRegisterVO | None:
        return None

    def get(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AbstractArmoryNode | None:
        return self._ai_api_node


class AiApiNode(AbstractArmoryNode):
    """构建 LLM API 配置（照抄原 Java AiApiNode：baseUrl/apiKey/completionsPath/embeddingsPath）。"""

    def __init__(self, chat_model_node: "ChatModelNode") -> None:
        self._chat_model_node = chat_model_node

    def do_apply(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AiAgentRegisterVO | None:
        logger.info("Ai Agent 装配操作 - AiApiNode")
        table: AiAgentConfigTableVO = command.aiAgentConfigTableVO  # type: ignore[assignment]
        ai_api = table.module.aiApi
        ctx.openAiApi = {
            "baseUrl": ai_api.baseUrl,
            "apiKey": ai_api.apiKey,
            "completionsPath": ai_api.completionsPath or "/v1/chat/completions",
            "embeddingsPath": ai_api.embeddingsPath or "/v1/embeddings",
        }
        return None

    def get(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AbstractArmoryNode | None:
        return self._chat_model_node


class ChatModelNode(AbstractArmoryNode):
    """构建 ChatModel（照抄原 Java ChatModelNode：本地 MCP 工具 + skills 工具挂载到默认 options）。"""

    def __init__(self, agent_node: "AgentNode", settings: Settings) -> None:
        self._agent_node = agent_node
        self._settings = settings

    def do_apply(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AiAgentRegisterVO | None:
        logger.info("Ai Agent 装配操作 - ChatModelNode")
        table: AiAgentConfigTableVO = command.aiAgentConfigTableVO  # type: ignore[assignment]
        ai_api_cfg = ctx.openAiApi or {}
        chat_model_cfg = table.module.chatModel

        # 1. 构建 MCP 本地工具（原 Java 走 DefaultMcpClientFactory -> LocalToolMcpCreateService）
        tools: list[ToolSpec] = []
        for tool_mcp in chat_model_cfg.toolMcpList or []:
            # yml 结构：{local: {name: xxx}} / {sse: {...}} / {stdio: {...}}
            local = (tool_mcp or {}).get("local") or {}
            name = local.get("name")
            if name:
                # registry 在 AgentNode 构建时注入：从 app state 传入
                registry_tools = self._local_registry.get(name) if self._local_registry else None
                if registry_tools:
                    tools.extend(registry_tools)
                else:
                    logger.warning("local mcp 工具未注册: %s（原 Java 行为：E0002 智能体MCP配置不在可加载范围）", name)
            elif tool_mcp and (("sse" in tool_mcp) or ("stdio" in tool_mcp)):
                # 原 Java 支持 sse/stdio MCP 客户端；本复现按主装配 yml 只使用 local，sse/stdio 记为不支持的配置
                logger.warning("sse/stdio MCP 暂未在 Python 复现中支持，跳过: %s", list(tool_mcp.keys()))

        # 2. 构建 skills 工具（原 Java 走 DefaultToolSkillsCreateService -> SkillsTool）
        for tool_skills in chat_model_cfg.toolSkillsList or []:
            skill_tool = self._build_skills_tool(tool_skills or {})
            if skill_tool is not None:
                tools.append(skill_tool)

        # 3. 构建 ChatModel（原 Java OpenAiChatModel.builder().openAiApi(openAiApi).defaultOptions(...).build()）
        # API Key：优先 YAML 占位符解析结果；为空时回落 DEEPSEEK_API_KEY / AI_AGENT_API_KEY 环境变量
        api_key = str(ai_api_cfg.get("apiKey") or "") or self._settings.resolved_api_key()
        client = LiteLlmClient(
            model=chat_model_cfg.model or "deepseek-chat",
            base_url=str(ai_api_cfg.get("baseUrl") or "https://api.deepseek.com"),
            completions_path=str(ai_api_cfg.get("completionsPath") or "/v1/chat/completions"),
            api_key=api_key,
        )
        ctx.chatModel = ChatModel(client=client, tools=tools)
        return None

    def get(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AbstractArmoryNode | None:
        return self._agent_node

    # ---- 依赖注入辅助 ----

    _local_registry: dict[str, list[ToolSpec]] | None = None

    def set_local_registry(self, registry: dict[str, list[ToolSpec]] | None) -> None:
        """注入本地工具注册表（matter/local_tools.build_local_tool_registry 的结果）。"""
        self._local_registry = registry

    def _build_skills_tool(self, tool_skills: dict[str, Any]) -> ToolSpec | None:
        """构建 skills 加载工具（对齐原 Java SkillsTool：把 SKILL.md 内容作为工具结果喂给模型）。

        原 Java 用 spring-ai-community 的 SkillsTool；第三方库的内部工具契约不影响对外 HTTP
        契约，此处以 load_skill 工具等价实现：模型按技能名加载技能说明文本。
        """
        skills_type = str(tool_skills.get("type") or "directory")
        path = str(tool_skills.get("path") or "")
        if not path:
            return None
        # resource 类型：classpath:agent/... 映射到本服务 resources 目录；directory 类型按原样路径
        if skills_type == "resource":
            normalized = path.replace("\\", "/").strip("/")
            skills_dir = self._settings.agent_resources_dir.parent / normalized
        else:
            skills_dir = Path(path)

        skills = _load_skills(skills_dir)
        if not skills:
            logger.warning("skills 目录为空或不存在: %s", skills_dir)
            return None

        catalog = "\n".join(f"- {name}: {desc}" for name, desc, _ in skills)
        content_map = {name: content for name, _, content in skills}

        def handler(args: dict[str, Any]) -> dict[str, Any]:
            skill_name = str((args or {}).get("skill_name") or "").strip()
            if skill_name in content_map:
                return {"success": True, "skill_name": skill_name, "content": content_map[skill_name]}
            return {"success": False, "message": f"技能不存在。可用技能：{catalog}"}

        return ToolSpec(
            name="load_skill",
            description=(
                "加载投资研究技能说明。可用技能：\n" + catalog
            ),
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "技能名称，见可用技能列表。"},
                },
                "required": ["skill_name"],
            },
            handler=handler,
        )


class AgentNode(AbstractArmoryNode):
    """构建专家智能体列表（照抄原 Java AgentNode：LlmAgent(name/description/model/instruction/outputKey)）。"""

    def __init__(self, workflow_node: "AgentWorkflowNode") -> None:
        self._workflow_node = workflow_node

    def do_apply(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AiAgentRegisterVO | None:
        logger.info("Ai Agent 装配操作 - AgentNode")
        table: AiAgentConfigTableVO = command.aiAgentConfigTableVO  # type: ignore[assignment]
        chat_model = ctx.chatModel

        for agent_config in table.module.agents or []:
            llm_agent = LlmAgent(
                name=agent_config.name or "",
                description=agent_config.description or "",
                model=chat_model,
                instruction=agent_config.instruction or "",
                output_key=agent_config.outputKey,
            )
            ctx.agentGroup[agent_config.name or ""] = llm_agent
        return None

    def get(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AbstractArmoryNode | None:
        return self._workflow_node


class AgentWorkflowNode(AbstractArmoryNode):
    """工作流装配路由（照抄原 Java AgentWorkflowNode：按 type 分发到 4 种工作流节点）。"""

    def __init__(
        self,
        loop_node: "LoopAgentNode",
        parallel_node: "ParallelAgentNode",
        sequential_node: "SequentialAgentNode",
        supervisor_node: "SupervisorAgentNode",
        runner_node: "RunnerNode",
    ) -> None:
        self._nodes = {
            "loopAgentNode": loop_node,
            "parallelAgentNode": parallel_node,
            "sequentialAgentNode": sequential_node,
            "supervisorAgentNode": supervisor_node,
        }
        self._runner_node = runner_node

    def do_apply(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AiAgentRegisterVO | None:
        logger.info("Ai Agent 装配操作 - AgentWorkflowNode")
        table: AiAgentConfigTableVO = command.aiAgentConfigTableVO  # type: ignore[assignment]
        agent_workflows = table.module.agentWorkflows

        if not agent_workflows or ctx.currentStepIndex >= len(agent_workflows):
            ctx.currentAgentWorkflow = None
            return None

        ctx.currentAgentWorkflow = agent_workflows[ctx.currentStepIndex]
        ctx.add_current_step_index()
        return None

    def get(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AbstractArmoryNode | None:
        current = ctx.currentAgentWorkflow
        if current is None:
            return self._runner_node

        agent_type = AgentTypeEnum.form_type(current.type)
        if agent_type is None:
            raise RuntimeError("agentWorkflow type is error!")
        return self._nodes.get(agent_type.node, self._runner_node)


class LoopAgentNode(AbstractArmoryNode):
    """循环执行装配（照抄原 Java LoopAgentNode：LoopAgent(maxIterations)）。"""

    def __init__(self, workflow_node: AgentWorkflowNode) -> None:
        self._workflow_node = workflow_node

    def do_apply(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AiAgentRegisterVO | None:
        logger.info("Ai Agent 装配操作 - LoopAgentNode")
        current = ctx.currentAgentWorkflow
        if current is None:
            return None
        sub_agents = ctx.query_agent_list(current.subAgents)
        agent = LoopAgent(
            name=current.name or "",
            description=current.description or "",
            sub_agents=sub_agents,
            max_iterations=current.maxIterations or 3,
        )
        ctx.agentGroup[current.name or ""] = agent
        return None

    def get(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AbstractArmoryNode | None:
        # 原 Java 此处 getBean("agentWorkflow") 为错误的 bean 名（运行时会失败）；
        # Python 侧修正为回工作流路由节点（行为偏差见交付报告）。
        return self._workflow_node


class ParallelAgentNode(AbstractArmoryNode):
    """并行执行装配（照抄原 Java ParallelAgentNode）。"""

    def __init__(self, workflow_node: AgentWorkflowNode) -> None:
        self._workflow_node = workflow_node

    def do_apply(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AiAgentRegisterVO | None:
        logger.info("Ai Agent 装配操作 - ParallelAgentNode")
        current = ctx.currentAgentWorkflow
        if current is None:
            return None
        sub_agents = ctx.query_agent_list(current.subAgents)
        agent = ParallelAgent(
            name=current.name or "",
            description=current.description or "",
            sub_agents=sub_agents,
        )
        ctx.agentGroup[current.name or ""] = agent
        return None

    def get(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AbstractArmoryNode | None:
        return self._workflow_node


class SequentialAgentNode(AbstractArmoryNode):
    """串行执行装配（照抄原 Java SequentialAgentNode）。"""

    def __init__(self, workflow_node: AgentWorkflowNode) -> None:
        self._workflow_node = workflow_node

    def do_apply(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AiAgentRegisterVO | None:
        logger.info("Ai Agent 装配操作 - SequentialAgentNode")
        current = ctx.currentAgentWorkflow
        if current is None:
            return None
        sub_agents = ctx.query_agent_list(current.subAgents)
        agent = SequentialAgent(
            name=current.name or "",
            description=current.description or "",
            sub_agents=sub_agents,
        )
        ctx.agentGroup[current.name or ""] = agent
        return None

    def get(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AbstractArmoryNode | None:
        return self._workflow_node


class SupervisorAgentNode(AbstractArmoryNode):
    """层级编排装配（照抄原 Java SupervisorAgentNode：LlmAgent + subAgents + instruction）。"""

    def __init__(self, workflow_node: AgentWorkflowNode) -> None:
        self._workflow_node = workflow_node

    def do_apply(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AiAgentRegisterVO | None:
        logger.info("Ai Agent 装配操作 - SupervisorAgentNode")
        current = ctx.currentAgentWorkflow
        if current is None:
            return None
        sub_agents = ctx.query_agent_list(current.subAgents)
        agent = LlmAgent(
            name=current.name or "",
            description=current.description or "",
            model=ctx.chatModel,
            instruction=current.instruction or "",
            sub_agents=sub_agents,
            output_key=(current.outputKey or None),
        )
        ctx.agentGroup[current.name or ""] = agent
        return None

    def get(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AbstractArmoryNode | None:
        return self._workflow_node


class RunnerNode(AbstractArmoryNode):
    """执行器装配（照抄原 Java RunnerNode：InMemoryRunner + 注册 bean(agentId)）。"""

    def __init__(self, factory: Any) -> None:
        self._factory = factory  # DefaultArmoryFactory

    def do_apply(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AiAgentRegisterVO | None:
        logger.info("Ai Agent 装配操作 - RunnerNode")
        table: AiAgentConfigTableVO = command.aiAgentConfigTableVO  # type: ignore[assignment]
        app_name = table.appName
        agent = table.agent

        runner = self._build_runner(ctx, table, app_name or "")

        vo = AiAgentRegisterVO(
            appName=app_name or "",
            agentId=agent.agentId or "",
            agentName=agent.agentName,
            agentDesc=agent.agentDesc,
            runner=runner,
        )
        # 注册到容器（原 Java registerBean(agentId, AiAgentRegisterVO.class, vo)）
        self._factory.register_ai_agent_register_vo(vo.agentId, vo)
        return vo

    def get(self, command: ArmoryCommandEntity, ctx: DynamicContext) -> AbstractArmoryNode | None:
        return None  # 装配结束（对应原 Java defaultStrategyHandler 终止）

    def _build_runner(self, ctx: DynamicContext, table: AiAgentConfigTableVO, app_name: str) -> InMemoryRunner:
        runner_cfg = table.module.runner
        agent_name = runner_cfg.agentName
        if not agent_name:
            logger.error("runner.agentName is null")
            raise AppException(ResponseCode.ILLEGAL_PARAMETER.value, ResponseCode.ILLEGAL_PARAMETER.info)

        base_agent = ctx.agentGroup.get(agent_name)
        if base_agent is None:
            # 原 Java 此时 InMemoryRunner 持 null 会在运行期 NPE；这里提前校验更安全
            raise AppException(ResponseCode.ILLEGAL_PARAMETER.value, f"runner.agentName 未找到已装配的智能体: {agent_name}")

        # 原 Java plugins（myTestPlugin/myLogPlugin）：仅日志职责，Python 侧以 logging 承接
        return InMemoryRunner(base_agent, app_name)


def build_armory_chain(
    factory: Any,
    settings: Settings,
    local_tool_registry: dict[str, list[ToolSpec]] | None,
) -> AbstractArmoryNode:
    """构建装配链并绑定到工厂（等价于原 Java 各节点 @Resource 互相注入 + 工厂持有 RootNode）。"""
    runner_node = RunnerNode(factory)
    supervisor_node = SupervisorAgentNode(None)  # type: ignore[arg-type]
    loop_node = LoopAgentNode(None)  # type: ignore[arg-type]
    parallel_node = ParallelAgentNode(None)  # type: ignore[arg-type]
    sequential_node = SequentialAgentNode(None)  # type: ignore[arg-type]
    workflow_node = AgentWorkflowNode(loop_node, parallel_node, sequential_node, supervisor_node, runner_node)
    # 工作流节点回环（对齐原 Java 各 workflow 节点 get() 返回 agentWorkflowNode）
    supervisor_node._workflow_node = workflow_node
    loop_node._workflow_node = workflow_node
    parallel_node._workflow_node = workflow_node
    sequential_node._workflow_node = workflow_node

    agent_node = AgentNode(workflow_node)
    chat_model_node = ChatModelNode(agent_node, settings)
    chat_model_node.set_local_registry(local_tool_registry)
    ai_api_node = AiApiNode(chat_model_node)
    root = RootNode(ai_api_node)
    factory.bind_root_node(root)
    return root


def _load_skills(skills_dir: Path) -> list[tuple[str, str, str]]:
    """读取技能目录下的 SKILL.md（name/description 取 YAML front-matter，内容全文返回）。"""
    skills: list[tuple[str, str, str]] = []
    if not skills_dir.exists():
        return skills
    for md in sorted(skills_dir.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        name, description = md.stem, ""
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].splitlines():
                    if line.startswith("name:"):
                        name = line.split(":", 1)[1].strip() or name
                    elif line.startswith("description:"):
                        description = line.split(":", 1)[1].strip()
                text = parts[2].strip()
        skills.append((name, description, text))
    return skills
