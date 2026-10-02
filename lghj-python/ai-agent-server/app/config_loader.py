"""智能体装配配置加载（对应原 Java Spring Boot 的 ConfigurationProperties 绑定 + spring.config.import）。

复现自：
    ai-agent-scaffoid-feng-app/src/main/resources/application-dev.yml
        spring.config.import: classpath:agent/investment_advisor_supervisor.yml
                              + optional:classpath:agent/investment_advisor_supervisor_local.yml
    ai-agent-scaffoid-feng-domain/.../valobj/properties/AiAgentAutoConfigProperties.java
        （前缀 ai.agent.config：enabled + tables）

Python 侧以 PyYAML 加载双语命名的装配文件，并按 Spring 规则做深合并：
后导入的 optional local 文件覆盖同名属性（dict 递归合并，list 整体替换）。
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from app.config import Settings
from app.domain.agent.adapter.model.valobj import (
    AgentModuleVO,
    AgentTableVO,
    AgentWorkflowVO,
    AiAgentConfigTableVO,
    AiApiVO,
    AiAgentAutoConfigProperties,
    ChatModelVO,
    ModuleVO,
    RunnerVO,
)

logger = logging.getLogger(__name__)

# Spring 占位符 ${VAR:default} / ${VAR}（default 中可含冒号、斜杠等，取到第一个右花括号）
_ENV_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}")


def _substitute_env(value: Any) -> Any:
    """递归做环境变量占位替换（对齐 Spring ${VAR:default} 语义）。"""
    if isinstance(value, str):
        def _replace(match: re.Match[str]) -> str:
            var, default = match.group(1), match.group(2)
            return os.environ.get(var, default if default is not None else "")

        return _ENV_PLACEHOLDER.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Spring 风格属性合并：dict 递归合并，其余类型（含 list）整体覆盖。"""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_agent_config_properties(settings: Settings) -> AiAgentAutoConfigProperties:
    """读取装配 yml -> AiAgentAutoConfigProperties（对齐 ai.agent.config 前缀绑定）。"""
    agent_dir = Path(settings.agent_resources_dir)
    main_file = agent_dir / settings.agent_config_file
    local_file = agent_dir / settings.agent_config_local_file

    data: dict[str, Any] = _read_yaml(main_file)
    # 原 Java local 覆写为 optional import；本服务默认关闭（其为调试实验配置，
    # 会替换 agent-workflows 使 Supervisor 失去 sub-agents），可通过
    # AGENT_CONFIG_LOCAL_ENABLED=true 显式开启
    if settings.agent_config_local_enabled and local_file.exists():
        local_data = _read_yaml(local_file)
        data = _deep_merge(data, local_data)  # 对齐 optional import 的覆盖顺序
    data = _substitute_env(data)

    root = (((data or {}).get("ai") or {}).get("agent") or {}).get("config") or {}
    tables_raw: dict[str, dict[str, Any]] = root.get("tables") or {}

    tables = {key: _parse_table(value) for key, value in tables_raw.items()}
    properties = AiAgentAutoConfigProperties(enabled=bool(root.get("enabled", False)), tables=tables)
    logger.info(
        "Ai Agent 智能体装配配置加载完成: tables=%s",
        {k: (v.agent.agentId, v.appName) for k, v in tables.items()},
    )
    return properties


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        logger.warning("装配文件不存在: %s", path)
        return {}
    with path.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh)
    return loaded or {}


def _parse_table(raw: dict[str, Any]) -> AiAgentConfigTableVO:
    """解析 tables.<key> 一项为 AiAgentConfigTableVO（key 与原 Java VO 字段一一对应）。"""
    agent_raw = raw.get("agent") or {}
    module_raw = raw.get("module") or {}

    ai_api_raw = module_raw.get("ai-api") or {}
    chat_model_raw = module_raw.get("chat-model") or {}
    runner_raw = module_raw.get("runner") or {}

    agents = [
        AgentModuleVO(
            name=item.get("name"),
            instruction=item.get("instruction"),
            description=item.get("description"),
            outputKey=item.get("output-key"),
        )
        for item in (module_raw.get("agents") or [])
    ]
    workflows = [
        AgentWorkflowVO(
            type=item.get("type"),
            name=item.get("name"),
            subAgents=list(item.get("sub-agents") or []),
            description=item.get("description"),
            instruction=item.get("instruction"),
            outputKey=item.get("output-key"),
            maxIterations=item.get("max-iterations", 3),
        )
        for item in (module_raw.get("agent-workflows") or [])
    ]

    return AiAgentConfigTableVO(
        appName=raw.get("app-name"),
        agent=AgentTableVO(
            agentId=agent_raw.get("agent-id"),
            agentName=agent_raw.get("agent-name"),
            agentDesc=agent_raw.get("agent-desc"),
        ),
        module=ModuleVO(
            aiApi=AiApiVO(
                baseUrl=ai_api_raw.get("base-url"),
                apiKey=ai_api_raw.get("api-key"),
                completionsPath=ai_api_raw.get("completions-path") or "/v1/chat/completions",
                embeddingsPath=ai_api_raw.get("embeddings-path") or "/v1/embeddings",
            ),
            chatModel=ChatModelVO(
                model=chat_model_raw.get("model"),
                toolMcpList=list(chat_model_raw.get("tool-mcp-list") or []),
                toolSkillsList=list(chat_model_raw.get("tool-skills-list") or []),
            ),
            agents=agents,
            agentWorkflows=workflows,
            runner=RunnerVO(
                agentName=runner_raw.get("agent-name"),
                pluginNameList=list(runner_raw.get("plugin-name-list") or []),
            ),
        ),
    )
