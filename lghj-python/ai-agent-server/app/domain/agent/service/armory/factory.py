"""装配工厂。

复现自原 Java 类：
    ai-agent-scaffoid-feng-domain/.../armory/factory/DefaultArmoryFactory.java
        - armoryStrategyHandler()：返回装配树根节点
        - getAiAgentRegisterVO(agentId)：按 agentId 取已注册的智能体（原 Java 走 Spring 容器 getBean）
        - DynamicContext：装配链各节点间的上下文（openAiApi/chatModel/agentGroup/当前工作流步骤）
"""

from __future__ import annotations

import threading
from typing import Any

from app.domain.agent.adapter.model.valobj import AgentWorkflowVO, AiAgentRegisterVO


class DynamicContext:
    """装配链上下文（对齐原 Java DefaultArmoryFactory.DynamicContext 字段）。"""

    def __init__(self) -> None:
        self.openAiApi: dict[str, Any] | None = None          # {baseUrl, apiKey, completionsPath, embeddingsPath}
        self.chatModel: Any | None = None                      # ChatModel
        self.agentGroup: dict[str, Any] = {}                   # name -> BaseAgent
        self.currentStepIndex: int = 0                         # 当前装配的工作流步骤
        self.currentAgentWorkflow: AgentWorkflowVO | None = None

    def query_agent_list(self, agent_names: list[str] | None) -> list[Any]:
        """按名称取子智能体列表（对齐原 Java queryAgentList）。"""
        if not agent_names:
            return []
        agents = []
        for name in agent_names:
            agent = self.agentGroup.get(name)
            if agent is not None:
                agents.append(agent)
        return agents

    def add_current_step_index(self) -> None:
        """步长 +1（对齐原 Java addCurrentStepIndex）。"""
        self.currentStepIndex += 1


class DefaultArmoryFactory:
    """默认装配工厂：管理装配树入口 + 已装配完成的智能体注册表。

    原 Java 通过 Spring ApplicationContext 注册/获取 bean（bean 名 = agentId）；
    Python 侧用线程安全的字典注册表等价实现。
    """

    def __init__(self) -> None:
        self._registry: dict[str, AiAgentRegisterVO] = {}
        self._lock = threading.Lock()
        self._root_node: Any | None = None  # RootNode，由 nodes.build_armory_chain 注入

    # ---- 装配树入口 ----

    def bind_root_node(self, root_node: Any) -> None:
        """绑定装配树根节点（对应原 Java @Resource RootNode rootNode 注入）。"""
        self._root_node = root_node

    def armory_strategy_handler(self) -> Any:
        """返回装配树根节点（对齐原 Java armoryStrategyHandler()）。"""
        if self._root_node is None:
            raise RuntimeError("armory root node is not bound")
        return self._root_node

    # ---- 智能体注册表 ----

    def get_ai_agent_register_vo(self, agent_id: str) -> AiAgentRegisterVO | None:
        """按 agentId 获取已注册智能体；不存在返回 None（调用方抛 E0001）。"""
        return self._registry.get(agent_id)

    def register_ai_agent_register_vo(self, agent_id: str, vo: AiAgentRegisterVO) -> None:
        """注册智能体；已存在则覆盖（对齐原 Java registerBean 的先移除再注册语义）。"""
        with self._lock:
            self._registry[agent_id] = vo
            # 上面日志对齐原 Java log.info("成功注册Bean: {}", beanName)
            import logging

            logging.getLogger(__name__).info("成功注册Bean: %s", agent_id)

    def registered_agent_ids(self) -> list[str]:
        """已注册的 agentId 列表（自测/运维用）。"""
        return list(self._registry.keys())
