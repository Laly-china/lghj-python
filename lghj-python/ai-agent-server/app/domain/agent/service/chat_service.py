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
from threading import Lock

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
        # 用户会话缓存：userId -> sessionId（照抄原 Java ConcurrentHashMap 语义）
        self._user_sessions: dict[str, str] = {}
        self._user_sessions_lock = Lock()

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
        """创建用户与 AI 的对话会话（同一用户复用同一 sessionId）。

        原 Java：userSessions.computeIfAbsent(userId, uid -> runner.sessionService()
            .createSession(appName, uid).blockingGet().id())
        """
        register_vo = self._factory.get_ai_agent_register_vo(agent_id or "")
        if register_vo is None:
            # 智能体ID不存在
            raise AppException(ResponseCode.E0001.value, ResponseCode.E0001.info)

        app_name = register_vo.appName
        runner: InMemoryRunner = register_vo.runner

        with self._user_sessions_lock:
            session_id = self._user_sessions.get(user_id or "")
            if session_id is None:
                session = runner.session_service.create_session(app_name, user_id or "")
                session_id = session.id
                self._user_sessions[user_id or ""] = session_id
            return session_id

    # ====================== 对外接口：处理消息 ======================

    def handle_message(self, agent_id: str | None, user_id: str | None, session_id: str | None, message: str | None) -> list[str]:
        """阻塞式处理用户消息，返回各事件文本列表（对齐原 Java handleMessage）。"""
        register_vo = self._factory.get_ai_agent_register_vo(agent_id or "")
        if register_vo is None:
            raise AppException(ResponseCode.E0001.value, ResponseCode.E0001.info)

        runner: InMemoryRunner = register_vo.runner
        user_msg = Content.from_text(self._build_user_context_message(agent_id or "", user_id or "", message or ""))
        events: Iterator[Event] = runner.run_async(user_id or "", session_id or "", user_msg)

        outputs: list[str] = []
        for event in events:
            outputs.append(event.stringify_content())
        return outputs

    def handle_message_stream(self, agent_id: str | None, user_id: str | None, session_id: str | None, message: str | None) -> Iterator[Event]:
        """流式处理用户消息，返回事件生成器（对齐原 Java handleMessageStream）。"""
        register_vo = self._factory.get_ai_agent_register_vo(agent_id or "")
        if register_vo is None:
            raise AppException(ResponseCode.E0001.value, ResponseCode.E0001.info)

        runner: InMemoryRunner = register_vo.runner
        user_msg = Content.from_text(self._build_user_context_message(agent_id or "", user_id or "", message or ""))
        # 直接返回流，不阻塞，前端实时接收
        return runner.run_async(user_id or "", session_id or "", user_msg)

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
