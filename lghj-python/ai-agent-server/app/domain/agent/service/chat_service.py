"""AI 智能体对话服务实现类。

复现自原 Java 类：
    ai-agent-scaffoid-feng-domain/.../agent/service/IChatService.java
    ai-agent-scaffoid-feng-domain/.../agent/service/chat/ChatService.java

核心功能（逻辑与文案严格照抄原 Java）：
- 查询已装配的智能体配置列表
- 创建会话（userId -> sessionId 内存 Map 复用，线程安全）
- 阻塞式对话 / 流式对话（事件流）
- 自动注入用户交易画像上下文（仅 investment-advisor；上限 6000 字符，超出截断）
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from app.domain.agent.adapter.model.entity import ChatCommandEntity
from app.domain.agent.adapter.model.valobj import AgentTableVO, AiAgentAutoConfigProperties
from app.domain.agent.adapter.port import SimTradeProfilePort
from app.domain.agent.service.armory.factory import DefaultArmoryFactory
from app.domain.agent.service.armory.runtime import Content, Event, InMemoryRunner, Part
from app.types.app_exception import AppException
from app.types.response_code import ResponseCode

logger = logging.getLogger(__name__)


class ChatService:
    """AI 智能体对话服务（专门服务于【投资顾问 AI 智能体】）。"""

    #: 投资顾问智能体唯一标识（固定ID，照抄原 Java）
    INVESTMENT_ADVISOR_AGENT_ID = "investment-advisor"

    #: 交易画像上下文最大长度限制，防止超长导致AI模型处理失败（照抄原 Java）
    MAX_PROFILE_CONTEXT_LENGTH = 6000

    def __init__(
        self,
        default_armory_factory: DefaultArmoryFactory,
        ai_agent_auto_config_properties: AiAgentAutoConfigProperties,
        sim_trade_profile_port: SimTradeProfilePort,
    ) -> None:
        self._factory = default_armory_factory
        self._properties = ai_agent_auto_config_properties
        self._sim_trade_profile_port = sim_trade_profile_port

    # ====================== 对外接口：查询AI智能体配置列表 ======================

    def query_ai_agent_config_list(self) -> list[AgentTableVO]:
        """查询所有可用的 AI 智能体配置列表（对齐原 Java queryAiAgentConfigList）。"""
        tables = self._properties.tables
        agent_list: list[AgentTableVO] = []
        if tables:
            for vo in tables.values():
                if vo.agent is not None:
                    agent_list.append(vo.agent)
        return agent_list

    # ====================== 对外接口：创建AI对话会话 ======================

    def create_session(self, agent_id: str | None, user_id: str | None) -> str:
        """创建用户与 AI 的对话会话（每次调用都新建，配合「新建对话」与历史落库语义）。

        原 Java：userSessions.computeIfAbsent(userId, uid -> runner.sessionService()
            .createSession(appName, uid).blockingGet().id()) —— 同一用户复用同一会话；
        本工程扩展历史持久化后改为每次新建：否则多轮「新建对话」都会折进同一
        历史行（标题永远停在首问、列表看不到新增），新开对话亦无法隔离上下文。
        会话上下文仍由前端 advisor_session 在单次页面会话内复用。
        """
        register_vo = self._factory.get_ai_agent_register_vo(agent_id or "")
        if register_vo is None:
            # 智能体ID不存在
            raise AppException(ResponseCode.E0001.value, ResponseCode.E0001.info)

        runner: InMemoryRunner = register_vo.runner
        return runner.session_service.create_session(
            register_vo.appName, user_id or ""
        ).id

    # ====================== 对外接口：处理消息 ======================

    def handle_message(self, agent_id: str | None, user_id: str | None, session_id: str | None, message: str | None) -> list[str]:
        """阻塞式处理用户消息，返回各事件文本列表（对齐原 Java handleMessage）。"""
        register_vo = self._factory.get_ai_agent_register_vo(agent_id or "")
        if register_vo is None:
            raise AppException(ResponseCode.E0001.value, ResponseCode.E0001.info)

        runner: InMemoryRunner = register_vo.runner
        trace_start = self._trace_start_len(register_vo, user_id or "", session_id or "")
        user_msg = Content.from_text(self._build_user_context_message(agent_id or "", user_id or "", message or ""))
        events: Iterator[Event] = runner.run_async(user_id or "", session_id or "", user_msg)

        outputs: list[str] = []
        for event in events:
            outputs.append(event.stringify_content())

        # 本工程扩展：历史落库（MySQL；失败仅告警不阻断对话）
        self._persist_turn(register_vo, user_id, session_id, message or "",
                           "\n".join(outputs), trace_start)
        return outputs

    # ====================== 扩展辅助：轨迹切片与历史落库（原 Java 无） ======================

    def _trace_start_len(self, register_vo, user_id: str, session_id: str) -> int:
        """运行前的会话轨迹长度（用于切出本轮新增事件）。"""
        session = register_vo.runner.session_service.get_session(register_vo.appName, user_id, session_id)
        return len(session.trace) if session is not None else 0

    def _trace_slice(self, register_vo, user_id: str, session_id: str, start: int) -> list[dict]:
        """切出本轮运行新增的轨迹事件。"""
        session = register_vo.runner.session_service.get_session(register_vo.appName, user_id, session_id)
        return list(session.trace[start:]) if session is not None else []

    def _persist_turn(self, register_vo, user_id: str | None, session_id: str | None,
                      user_text: str, assistant_text: str, trace_start: int) -> None:
        """一轮对话写入 MySQL 历史（agent_chat_session / agent_chat_message）。"""
        try:
            from app.infrastructure import chat_store

            trace = self._trace_slice(register_vo, user_id or "", session_id or "", trace_start)
            chat_store.record_turn(
                session_id=session_id or "",
                agent_id=register_vo.agentId,
                user_id=user_id or "",
                user_text=user_text,
                assistant_text=assistant_text,
                trace=trace,
            )
        except Exception:  # noqa: BLE001 存储不可用时降级为仅内存会话
            logger.warning("persist chat history failed", exc_info=True)

    def handle_message_stream(self, agent_id: str | None, user_id: str | None, session_id: str | None, message: str | None) -> Iterator[Event]:
        """流式处理用户消息，返回事件生成器（对齐原 Java handleMessageStream）。"""
        register_vo = self._factory.get_ai_agent_register_vo(agent_id or "")
        if register_vo is None:
            raise AppException(ResponseCode.E0001.value, ResponseCode.E0001.info)

        runner: InMemoryRunner = register_vo.runner
        trace_start = self._trace_start_len(register_vo, user_id or "", session_id or "")
        user_msg = Content.from_text(self._build_user_context_message(agent_id or "", user_id or "", message or ""))

        def _persisting(gen: Iterator[Event]) -> Iterator[Event]:
            """透传事件流，耗尽后落库历史（对齐阻塞路径的持久化语义）。"""
            outputs: list[str] = []
            for event in gen:
                outputs.append(event.stringify_content())
                yield event
            self._persist_turn(register_vo, user_id, session_id, message or "",
                               "\n".join(outputs), trace_start)

        # 直接返回流，不阻塞，前端实时接收
        return _persisting(runner.run_async(user_id or "", session_id or "", user_msg))

    def handle_message_command(self, command: ChatCommandEntity) -> list[str]:
        """复杂消息处理：文本 + 文件 + 内联数据（对齐原 Java handleMessage(ChatCommandEntity)）。"""
        register_vo = self._factory.get_ai_agent_register_vo(command.agentId or "")
        if register_vo is None:
            raise AppException(ResponseCode.E0001.value, ResponseCode.E0001.info)

        parts: list[Part] = []
        # 先加入系统上下文（用户ID + 交易画像）
        parts.append(Part(text=self._build_user_context_message(command.agentId or "", command.userId or "", "")))
        # 1. 文本消息
        for text in command.texts or []:
            parts.append(Part(text=text.message or ""))
        # 2. 文件（URL 方式）：DeepSeek 为文本模型，URI 部件以文本占位（偏差见交付报告）
        for file in command.files or []:
            parts.append(Part(text=f"[文件] {file.fileUri} ({file.mimeType})"))
        # 3. 内联数据（如图片字节流）
        for inline in command.inlineDatas or []:
            size = len(inline.bytes) if inline.bytes else 0
            parts.append(Part(text=f"[内联数据] ({inline.mimeType}) {size} bytes"))

        runner: InMemoryRunner = register_vo.runner
        content = Content(role="user", parts=parts)
        events = runner.run_async(command.userId or "", command.sessionId or "", content)

        outputs: list[str] = []
        for event in events:
            outputs.append(event.stringify_content())
        return outputs

    # ====================== 扩展：执行轨迹与团队结构（Agent 流程可视化，原 Java 无） ======================

    def get_trace(self, agent_id: str | None, user_id: str | None, session_id: str | None) -> list[dict]:
        """查询会话的执行轨迹事件列表（供前端管家团队状态灯与思考面板消费）。

        - agentId 无效：抛 E0001（与创建会话一致的语义）；
        - 会话不存在（服务重启后 / 未创建）：返回空列表宽和降级。
        """
        register_vo = self._factory.get_ai_agent_register_vo(agent_id or "")
        if register_vo is None:
            raise AppException(ResponseCode.E0001.value, ResponseCode.E0001.info)

        runner: InMemoryRunner = register_vo.runner
        session = runner.session_service.get_session(register_vo.appName, user_id or "", session_id or "")
        if session is None:
            return []
        return list(session.trace)

    def get_team(self, agent_id: str | None) -> dict:
        """查询智能体团队结构（Supervisor + 专家职能 + 可用工具名）。

        前端管家卡片的单一数据源：专家的 name/description/outputKey 均来自装配 yml。
        """
        register_vo = self._factory.get_ai_agent_register_vo(agent_id or "")
        if register_vo is None:
            raise AppException(ResponseCode.E0001.value, ResponseCode.E0001.info)

        runner: InMemoryRunner = register_vo.runner
        supervisor = runner.agent
        experts = [
            {
                "name": sub.name,
                "description": sub.description or "",
                "outputKey": getattr(sub, "output_key", None),
            }
            for sub in supervisor.sub_agents
        ]
        model = getattr(supervisor, "model", None)
        tools = [t.name for t in model.tools] if model is not None else []
        return {
            "agentId": register_vo.agentId,
            "supervisor": {"name": supervisor.name, "description": supervisor.description or ""},
            "experts": experts,
            "tools": tools,
        }

    # ====================== 核心：构建用户上下文消息（自动注入交易画像） ======================

    def _build_user_context_message(self, agent_id: str, user_id: str, message: str) -> str:
        """构建给 AI 的用户上下文消息（拼接文案照抄原 Java buildUserContextMessage）。"""
        builder: list[str] = []
        # 系统提示：限定AI只能查询当前用户的数据
        builder.append(
            f"系统上下文：当前用户ID为 {user_id}。如需查询用户个性化交易画像，只能使用该用户ID，不要查询其他用户。"
        )

        # 查询并添加用户交易画像（仅投资顾问智能体）
        profile_json = self._query_sim_trade_profile_context(agent_id, user_id)
        if profile_json and profile_json.strip():
            builder.append(
                f"\n当前用户模拟交易画像JSON：{profile_json}"
                "\n请优先基于这份画像分析账户资金、持仓、近期委托、近期成交、交易行为标签和仓位集中度。"
            )

        # 本工程扩展：用户个人知识库文档清单（全体智能体可见，提示可调用检索工具）
        try:
            from app.infrastructure import chat_store

            kb_titles = chat_store.list_kb_titles(user_id, limit=10)
        except Exception:  # noqa: BLE001 存储不可用时跳过注入
            kb_titles = []
        if kb_titles:
            builder.append(
                f"\n用户个人知识库文档：{'、'.join(kb_titles)}。"
                "如需引用其中的内容，请调用 queryKnowledgeBase 工具检索。"
            )

        # 添加用户问题
        if message and message.strip():
            builder.append(f"\n用户问题：{message}")

        return "".join(builder)

    def _query_sim_trade_profile_context(self, agent_id: str, user_id: str) -> str:
        """查询用户模拟交易画像（仅投资顾问智能体；超长截断到 6000 字符）。"""
        # 非投资顾问智能体，不返回画像
        if self.INVESTMENT_ADVISOR_AGENT_ID != agent_id:
            return ""

        # 远程调用获取画像JSON
        profile_json = self._sim_trade_profile_port.query_profile_json(user_id)
        # 空或长度正常，直接返回
        if profile_json is None or len(profile_json) <= self.MAX_PROFILE_CONTEXT_LENGTH:
            return profile_json or ""
        # 超长截断
        return profile_json[: self.MAX_PROFILE_CONTEXT_LENGTH] + "...[truncated]"
