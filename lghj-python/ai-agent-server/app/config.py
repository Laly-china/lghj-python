"""应用配置。

复现自原 Java 配置与属性类：
    ai-agent-scaffoid-feng-app/src/main/resources/application-dev.yml      （端口 8091、lghj.client）
    ai-agent-scaffoid-feng-app/src/main/java/cn/feng/config/LghjClientProperties.java
    ai-agent-scaffoid-feng-app/src/main/java/cn/feng/config/AiAgentAutoConfig.java（装配启动逻辑）

环境变量契约（照抄原 Java application-dev.yml 的占位符）：
    LGHJ_BASE_URL                主服务地址，默认 http://127.0.0.1:8080
    LGHJ_INTERNAL_API_TOKEN      内部接口令牌（X-Internal-Token 头的值），默认空
    LGHJ_CLIENT_TIMEOUT_SECONDS  调用主服务超时秒数，默认 5
LLM 相关（原 Java 使用 AI_AGENT_API_KEY / AI_AGENT_BASE_URL / AI_AGENT_MODEL，
本服务按任务要求优先读取 DEEPSEEK_API_KEY，其次回落 AI_AGENT_API_KEY）：
    DEEPSEEK_API_KEY             DeepSeek API Key（任务指定）
    AI_AGENT_BASE_URL            默认 https://api.deepseek.com
    AI_AGENT_API_KEY             原工程的 Key 环境变量（回落用）
    AI_AGENT_MODEL               默认 deepseek-chat
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 工程根目录（ai-agent-server/），resources 定位用
SERVER_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """应用设置（环境变量注入，与原 Java yml 占位符对齐）。"""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    # ---- 服务 ----
    server_port: int = 8091  # 原 application-dev.yml: server.port=8091

    # ---- lghj.client（调主服务 8080 的内部 API）----
    lghj_base_url: str = "http://127.0.0.1:8080"
    lghj_internal_api_token: str = ""  # 环境变量 LGHJ_INTERNAL_API_TOKEN（照抄原 Java yml 占位符）
    lghj_client_timeout_seconds: int = 5

    # ---- LLM（DeepSeek，OpenAI 兼容）----
    deepseek_api_key: str = ""          # DEEPSEEK_API_KEY
    ai_agent_base_url: str = "https://api.deepseek.com"
    ai_agent_api_key: str = ""          # 原工程 AI_AGENT_API_KEY，作回落
    ai_agent_model: str = "deepseek-chat"
    ai_agent_completions_path: str = "/v1/chat/completions"

    # ---- 装配文件（资源为中文-english 双语命名，代码按实际文件名读取）----
    agent_config_file: str = "投顾装配-investment-advisor-supervisor.yml"
    agent_config_local_file: str = "投顾本地覆写-investment-advisor-supervisor-local.yml"
    agent_resources_dir: Path = SERVER_ROOT / "app" / "resources" / "agent"
    # 原 Java local 覆写文件是调试实验配置（会替换 agent-workflows 使 Supervisor 失去 sub-agents），
    # 默认不加载；如需复现该行为设 AGENT_CONFIG_LOCAL_ENABLED=true
    agent_config_local_enabled: bool = False

    # ---- 会话 ----
    # 原 Java ChatService 使用内存 ConcurrentHashMap 存 userId -> sessionId，此处保持一致

    def resolved_api_key(self) -> str:
        """解析生效的 LLM API Key：DEEPSEEK_API_KEY 优先，其次 AI_AGENT_API_KEY。"""
        return self.deepseek_api_key or self.ai_agent_api_key


def load_settings() -> Settings:
    """读取配置（每次调用重新读环境变量，便于测试注入）。"""
    return Settings()
