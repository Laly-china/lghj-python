"""服务入口与装配启动。

复现自原 Java 类：
    ai-agent-scaffoid-feng-app/.../Application.java（SpringBootApplication 启动，端口 8091）
    ai-agent-scaffoid-feng-app/.../config/AiAgentAutoConfig.java（应用就绪后执行智能体装配）
    ai-agent-scaffoid-feng-app/.../config/LghjClientProperties.java（主服务客户端配置）

启动流程：
    1. 读取配置（环境变量 LGHJ_* / DEEPSEEK_API_KEY / AI_AGENT_*）
    2. 构建 infrastructure 端口（httpx 调 8080 /api/internal/*）
    3. 加载装配 yml -> AiAgentAutoConfigProperties
    4. 应用启动（lifespan）后执行 ArmoryService 装配：AiApi -> ChatModel -> Agent -> Workflow -> Runner
    5. 暴露 trigger 层 4 个路由（/api/v1/*）
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.config import Settings, load_settings
from app.config_loader import load_agent_config_properties
from app.domain.agent.adapter.port import MarketDataPort, SimTradeProfilePort
from app.domain.agent.service.armory.armory_service import ArmoryService
from app.domain.agent.service.armory.factory import DefaultArmoryFactory
from app.domain.agent.service.armory.nodes import build_armory_chain
from app.domain.agent.service.armory.runtime import ToolSpec
from app.domain.agent.service.chat_service import ChatService
from app.domain.agent.service.matter.local_tools import build_local_tool_registry
from app.infrastructure.adapter.http_ports import HttpMarketDataPort, HttpSimTradeProfilePort
from app.trigger.http.agent_controller import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """构建 FastAPI 应用（等价 Spring 容器组装）。"""
    settings = settings or load_settings()

    # ---- infrastructure 端口（对应原 Java -app 模块 adapter/port 的 HTTP 实现类）----
    market_data_port: MarketDataPort = HttpMarketDataPort(settings)
    sim_trade_profile_port: SimTradeProfilePort = HttpSimTradeProfilePort(settings)

    # ---- matter 本地工具注册表（对应原 Java 两个本地 MCP ToolCallbackProvider bean）----
    local_tool_registry: dict[str, list[ToolSpec]] = build_local_tool_registry(market_data_port, sim_trade_profile_port)

    # ---- 装配工厂 + 装配链（对应原 Java DefaultArmoryFactory + 各 Node @Resource 注入）----
    factory = DefaultArmoryFactory()
    build_armory_chain(factory, settings, local_tool_registry)

    # ---- 装配配置（对应 spring.config.import 的 agent yml）----
    properties = load_agent_config_properties(settings)

    # ---- 领域服务（对应原 Java @Service ChatService）----
    chat_service = ChatService(factory, properties, sim_trade_profile_port)
    armory_service = ArmoryService(factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # 对齐原 Java AiAgentAutoConfig.onApplicationEvent(ApplicationReadyEvent)：
        # 项目完全启动成功后执行智能体装配
        logger.info("Ai Agent 智能体装配开始: %s", list(properties.tables.keys()))
        armory_service.accept_armory_agents(list(properties.tables.values()))
        yield
        logger.info("ai-agent-server shutdown")

    app = FastAPI(title="ai-agent-server", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.factory = factory
    app.state.properties = properties
    app.state.chat_service = chat_service

    app.include_router(router)

    # 健康检查（运维用，不影响原契约）
    @app.get("/act/health")
    def health() -> dict[str, str]:
        return {"status": "UP"}

    return app


app = create_app()


if __name__ == "__main__":
    _settings = load_settings()
    uvicorn.run(app, host="0.0.0.0", port=_settings.server_port)
