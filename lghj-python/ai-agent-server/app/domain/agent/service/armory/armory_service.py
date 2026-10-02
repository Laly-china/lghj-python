"""装配服务。

复现自原 Java 类：
    ai-agent-scaffoid-feng-domain/.../agent/service/IArmoryService.java
    ai-agent-scaffoid-feng-domain/.../agent/service/armory/ArmoryService.java
    ai-agent-scaffoid-feng-app/.../config/AiAgentAutoConfig.java（ApplicationReadyEvent 时触发装配）
"""

from __future__ import annotations

import logging

from app.domain.agent.adapter.model.entity import ArmoryCommandEntity
from app.domain.agent.adapter.model.valobj import AiAgentConfigTableVO
from app.domain.agent.service.armory.factory import DefaultArmoryFactory, DynamicContext

logger = logging.getLogger(__name__)


class ArmoryService:
    """装配服务：遍历配置表，逐个驱动装配树（对齐原 Java ArmoryService.acceptArmoryAgents）。"""

    def __init__(self, factory: DefaultArmoryFactory) -> None:
        self._factory = factory

    def accept_armory_agents(self, tables: list[AiAgentConfigTableVO]) -> None:
        """执行装配（原 Java 声明 throws Exception，装配失败向上抛）。"""
        for table in tables:
            handler = self._factory.armory_strategy_handler()
            handler.apply(
                ArmoryCommandEntity(aiAgentConfigTableVO=table),
                DynamicContext(),
            )
        logger.info("Ai Agent 智能体装配完成，已注册: %s", self._factory.registered_agent_ids())
