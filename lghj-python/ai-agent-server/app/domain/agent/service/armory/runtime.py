"""AI Agent 运行时（google-adk 语义的 Python 轻量复现）。

复现自原 Java 依赖与类：
    com.google.adk.events.Event / com.google.genai.types.Content / Part
    com.google.adk.sessions.Session / InMemoryRunner
    com.google.adk.agents.BaseAgent / LlmAgent / LoopAgent / ParallelAgent / SequentialAgent
    ai-agent-scaffoid-feng-domain/.../armory/node/RunnerNode.java（InMemoryRunner 的构建方式）

说明：
- 原系统使用 google-adk-java + Spring AI；本服务为避免 google-adk-python 与
  fastapi/pydantic 的版本冲突，手写了等价的最小运行时（会话、事件流、
  transfer_to_agent 层级编排、本地工具调用），对外契约不受影响。
- Event.stringify_content() 对齐 ADK 语义：拼接事件内容中所有 text part。
- supervisor 编排对齐 ADK AutoFlow：父智能体通过 transfer_to_agent 工具把
  控制权转交给直接子智能体，子智能体输出作为工具结果回传父智能体继续决策。
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# 工具循环上限：防止 supervisor 与子智能体互相转移形成死循环
MAX_TOOL_ROUNDS = 10
# transfer_to_agent 工具名（对齐 google-adk 内置工具）
TRANSFER_TO_AGENT = "transfer_to_agent"


# ====================== 内容与事件（对应 genai Content/Part、adk Event） ======================

@dataclass
class Part:
    """消息部件（仅文本；文件/内联数据以文本占位形式支持）。"""

    text: str | None = None


@dataclass
class Content:
    """对话内容（role + parts），对应 com.google.genai.types.Content。"""

    role: str | None = None
    parts: list[Part] = field(default_factory=list)

    @staticmethod
    def from_parts(*parts: Part) -> "Content":
        """对应 Java Content.fromParts(...)。"""
        return Content(role="user", parts=list(parts))

    @staticmethod
    def from_text(text: str) -> "Content":
        """对应 Java Content.fromParts(Part.fromText(text))。"""
        return Content(role="user", parts=[Part(text=text)])

    def stringify(self) -> str:
        """拼接全部文本部件。"""
        return "".join(p.text or "" for p in self.parts if p.text)


@dataclass
class Event:
    """智能体事件（对应 com.google.adk.events.Event）。"""

    author: str
    content: Content | None = None

    def stringify_content(self) -> str:
        """对齐 ADK Event.stringifyContent()：拼接内容中的所有 text part；无内容返回空串。"""
        if self.content is None:
            return ""
        return self.content.stringify()


# ====================== 会话（对应 adk sessions Session / InMemorySessionService） ======================

@dataclass
class Session:
    """会话：保存一条对话的全部消息（OpenAI 消息格式）与状态（output_key 暂存）。"""

    id: str
    app_name: str
    user_id: str
    # OpenAI 消息格式：{"role": "...", "content": ...}，含 assistant/tool_calls/tool 消息
    messages: list[dict[str, Any]] = field(default_factory=list)
    # 会话状态：output_key -> 文本（对应 ADK session.state）
    state: dict[str, str] = field(default_factory=dict)


class InMemorySessionService:
    """内存会话服务：每个 Runner 独立一份（对齐 Java 每个InMemoryRunner 自带 sessionService）。"""

    def __init__(self) -> None:
        # (app_name, user_id, session_id) -> Session
        self._sessions: dict[tuple[str, str, str], Session] = {}

    def create_session(self, app_name: str, user_id: str) -> Session:
        """创建会话（对应 Java createSession(appName, uid).blockingGet()，同步语义）。"""
        session = Session(id=uuid.uuid4().hex, app_name=app_name, user_id=user_id)
        self._sessions[(app_name, user_id, session.id)] = session
        return session

    def get_session(self, app_name: str, user_id: str, session_id: str) -> Session | None:
        return self._sessions.get((app_name, user_id, session_id))

    def get_or_create(self, app_name: str, user_id: str, session_id: str) -> Session:
        """取会话，不存在则创建（容错：前端可能传未创建过的 sessionId）。"""
        session = self._sessions.get((app_name, user_id, session_id))
        if session is None:
            session = Session(id=session_id, app_name=app_name, user_id=user_id)
            self._sessions[(app_name, user_id, session_id)] = session
        return session


# ====================== 工具（对应 Spring AI ToolCallback） ======================

@dataclass
class ToolSpec:
    """工具定义：OpenAI function 形态 + 本地执行器。

    handler: 入参为模型给出的参数 dict，返回 str 或可 JSON 序列化的对象。
    handler 为 None 时表示由 Runner 特殊处理（如 transfer_to_agent）。
    """

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any] | None = None

    def to_openai_schema(self) -> dict[str, Any]:
        """转为 OpenAI tools 参数格式（litellm/DeepSeek 兼容）。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ====================== 模型客户端协议（对应 Spring AI ChatModel） ======================

class LlmClient(Protocol):
    """LLM 客户端协议：输入 OpenAI 消息与工具 schema，输出 assistant 消息 dict。"""

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> dict[str, Any]:
        """阻塞式补全，返回 OpenAI assistant 消息 dict（含可能的 tool_calls）。"""
        ...


@dataclass
class ChatModel:
    """对应 Java OpenAiChatModel：模型客户端 + 默认挂载的工具（toolCallbacks）。"""

    client: LlmClient
    tools: list[ToolSpec] = field(default_factory=list)

    def chat(self, messages: list[dict[str, Any]], extra_tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        schemas = self.tool_schemas() + (extra_tools or [])
        return self.client.chat(messages, schemas or None)

    def tool_schemas(self) -> list[dict[str, Any]]:
        return [t.to_openai_schema() for t in self.tools]

    def find_tool(self, name: str) -> ToolSpec | None:
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None


# ====================== 智能体（对应 adk agents） ======================

@dataclass
class BaseAgent:
    """智能体基类（对应 com.google.adk.agents.BaseAgent）。"""

    name: str
    description: str = ""
    sub_agents: list["BaseAgent"] = field(default_factory=list)


@dataclass
class LlmAgent(BaseAgent):
    """LLM 智能体（对应 com.google.adk.agents.LlmAgent）。"""

    model: ChatModel | None = None
    instruction: str = ""
    output_key: str | None = None


@dataclass
class LoopAgent(BaseAgent):
    """循环执行智能体（对应 com.google.adk.agents.LoopAgent）。"""

    max_iterations: int = 3


@dataclass
class ParallelAgent(BaseAgent):
    """并行执行智能体（对应 com.google.adk.agents.ParallelAgent）。"""


@dataclass
class SequentialAgent(BaseAgent):
    """串行执行智能体（对应 com.google.adk.agents.SequentialAgent）。"""


# ====================== 执行器（对应 adk runner.InMemoryRunner） ======================

class InMemoryRunner:
    """内存执行器：持有根智能体与会话服务，把用户消息驱动成事件流。

    对应 Java：com.google.adk.runner.InMemoryRunner(baseAgent, appName, plugins)。
    plugins 仅承担日志职责（原 Java 的 myLogPlugin），此处用 logging 实现。
    """

    def __init__(self, agent: BaseAgent, app_name: str, session_service: InMemorySessionService | None = None) -> None:
        self.agent = agent
        self.app_name = app_name
        self.session_service = session_service or InMemorySessionService()

    # ---- 对外主入口（对应 Java runner.runAsync(userId, sessionId, content)，Python 为同步生成器）----

    def run_async(self, user_id: str, session_id: str, content: Content) -> Iterator[Event]:
        """运行一次对话：追加用户消息，产出事件流（生成器）。"""
        session = self.session_service.get_or_create(self.app_name, user_id, session_id)
        user_text = content.stringify()
        session.messages.append({"role": "user", "content": user_text})
        yield from self._run_agent(self.agent, session, depth=0)

    # ---- 内部编排 ----

    def _run_agent(self, agent: BaseAgent, session: Session, depth: int) -> Iterator[Event]:
        """按智能体类型分发执行（对应 ADK AutoFlow 的运行规则）。"""
        if depth > MAX_TOOL_ROUNDS:
            logger.warning("agent nesting depth exceeded, stop. agent=%s", agent.name)
            return
        if isinstance(agent, LlmAgent):
            yield from self._run_llm_agent(agent, session, depth)
        elif isinstance(agent, SequentialAgent):
            for sub in agent.sub_agents:
                yield from self._run_agent(sub, session, depth + 1)
        elif isinstance(agent, ParallelAgent):
            # ADK 并行执行；为保证会话消息顺序一致，此处按顺序执行（偏差见交付报告）
            for sub in agent.sub_agents:
                yield from self._run_agent(sub, session, depth + 1)
        elif isinstance(agent, LoopAgent):
            for _ in range(max(1, agent.max_iterations)):
                for sub in agent.sub_agents:
                    yield from self._run_agent(sub, session, depth + 1)
        else:
            logger.warning("unsupported agent type: %s", type(agent).__name__)

    def _run_llm_agent(self, agent: LlmAgent, session: Session, depth: int) -> Iterator[Event]:
        """运行一个 LlmAgent：模型补全 -> 工具/转交循环 -> 文本事件。"""
        if agent.model is None:
            logger.warning("agent %s has no chat model, skip", agent.name)
            return

        for _round in range(MAX_TOOL_ROUNDS):
            messages = self._build_messages(agent, session)
            # 有直接子智能体时挂载 transfer_to_agent（对齐 ADK sub_agents 自动转交能力）
            extra_tools = [transfer_tool().to_openai_schema()] if agent.sub_agents else None
            assistant_msg = agent.model.chat(messages, extra_tools)

            calls = _extract_tool_calls(assistant_msg)
            session.messages.append(assistant_msg)

            if not calls:
                text = assistant_msg.get("content") or ""
                if text:
                    if agent.output_key:
                        session.state[agent.output_key] = text
                    yield Event(author=agent.name, content=Content(role="model", parts=[Part(text=text)]))
                return

            for call in calls:
                if call["name"] == TRANSFER_TO_AGENT:
                    target_name = str(call["arguments"].get("agent_name") or "")
                    sub = self._find_sub_agent(agent, target_name)
                    if sub is None:
                        session.messages.append(_tool_message(call["id"], {
                            "success": False,
                            "message": f"子智能体不存在或不是直接子级: {target_name}",
                        }))
                        continue
                    # 递归运行子智能体，事件透出；子智能体最后文本作为工具结果回传父级
                    last_text = ""
                    for event in self._run_agent(sub, session, depth + 1):
                        text = event.stringify_content()
                        if text:
                            last_text = text
                        yield event
                    session.messages.append(_tool_message(call["id"], last_text or "（子智能体无文本输出）"))
                else:
                    tool = agent.model.find_tool(call["name"])
                    if tool is None or tool.handler is None:
                        payload: Any = {"success": False, "message": f"未注册的工具: {call['name']}"}
                    else:
                        try:
                            payload = tool.handler(call["arguments"])
                        except Exception as exc:  # noqa: BLE001 工具异常降级为失败结果，避免中断对话
                            logger.warning("tool %s execute failed", call["name"], exc_info=True)
                            payload = {"success": False, "message": f"工具执行失败: {exc}"}
                    session.messages.append(_tool_message(call["id"], payload))
            # 继续下一轮：让当前智能体基于工具结果继续决策或输出最终答复
        logger.warning("agent %s reached max tool rounds", agent.name)

    @staticmethod
    def _build_messages(agent: LlmAgent, session: Session) -> list[dict[str, Any]]:
        """组装请求消息：系统提示词 = instruction，其余为共享会话历史。"""
        return [{"role": "system", "content": agent.instruction or ""}] + session.messages

    def _find_sub_agent(self, agent: BaseAgent, name: str) -> BaseAgent | None:
        """只允许转交给直接子智能体（对齐 ADK transfer 语义）。"""
        for sub in agent.sub_agents:
            if sub.name == name:
                return sub
        return None


def transfer_tool() -> ToolSpec:
    """transfer_to_agent 工具定义（对齐 google-adk 内置转交工具）。"""
    return ToolSpec(
        name=TRANSFER_TO_AGENT,
        description="把当前对话控制权转交给指定的子智能体处理。只能选择当前智能体的直接子智能体。",
        parameters={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "要转交的子智能体名称，必须是当前智能体的直接子智能体。",
                },
            },
            "required": ["agent_name"],
        },
        handler=None,  # 由 Runner 特殊处理
    )


# ====================== 辅助函数 ======================

def _extract_tool_calls(assistant_msg: dict[str, Any]) -> list[dict[str, Any]]:
    """从 assistant 消息 dict 中提取规范化 tool_calls 列表。"""
    calls: list[dict[str, Any]] = []
    for tc in assistant_msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        raw_args = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except json.JSONDecodeError:
            args = {}
        calls.append({"id": tc.get("id") or uuid.uuid4().hex, "name": fn.get("name") or "", "arguments": args})
    return calls


def _tool_message(tool_call_id: str, payload: Any) -> dict[str, Any]:
    """构造 tool 响应消息（OpenAI 格式）。"""
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}
