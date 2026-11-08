"""LLM 模型客户端：litellm 调 DeepSeek（OpenAI 兼容）。

复现自原 Java 装配：
    ai-agent-scaffoid-feng-domain/.../armory/node/AiApiNode.java（OpenAiApi：baseUrl/apiKey/completionsPath）
    ai-agent-scaffoid-feng-domain/.../armory/node/ChatModelNode.java（OpenAiChatModel + toolCallbacks）
    ai-agent-scaffoid-feng-domain/.../armory/node/AgentNode.java（new SpringAI(chatModel) 适配器）

原 Java 通过 Spring AI OpenAiChatModel + google-adk SpringAI 适配器访问
DeepSeek 的 OpenAI 兼容接口；Python 侧用 litellm（OpenAI 兼容协议）等价实现。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# 避免 litellm 启动时远程拉取模型价格表（离线环境/加速启动）
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

# LLM 请求超时秒数（对齐前端 chat 接口 180s 超时预算，留出工具往返余量）
_LLM_TIMEOUT_SECONDS = 180.0


class LiteLlmClient:
    """基于 litellm 的 LLM 客户端（对应 Java OpenAiApi + OpenAiChatModel 的组合能力）。

    - DeepSeek 为 OpenAI 兼容协议：model 传 "openai/<模型名>" + api_base 覆盖。
    - api_base 由 YAML 装配的 base-url + completions-path 推导（默认
      https://api.deepseek.com + /v1/chat/completions -> https://api.deepseek.com/v1）。
    - api_key 从 DEEPSEEK_API_KEY（优先）或 AI_AGENT_API_KEY 注入。
    """

    def __init__(self, model: str, base_url: str, completions_path: str, api_key: str) -> None:
        import litellm  # 延迟导入，缩短服务启动时间

        self._litellm = litellm
        # DeepSeek 无斜杠模型名走 openai/ 前缀 + 自定义 api_base（OpenAI 兼容）
        self._model = model if "/" in model else f"openai/{model}"
        self._api_base = _derive_api_base(base_url, completions_path)
        self._api_key = api_key or "EMPTY"  # 无 KEY 时仍可构建，调用时由服务端报 401 -> 走错误路径

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        user_id: str | None = None,  # 对齐 RoutingLlmClient 协议；单客户端实现忽略该参数
    ) -> dict[str, Any]:
        """阻塞补全，返回 OpenAI assistant 消息 dict（可能含 tool_calls）。"""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "api_base": self._api_base,
            "api_key": self._api_key,
            "timeout": _LLM_TIMEOUT_SECONDS,
            "num_retries": 0,
        }
        if tools:
            kwargs["tools"] = tools
        try:
            response = self._litellm.completion(**kwargs)
        except Exception:
            logger.warning("llm completion failed, model=%s api_base=%s", self._model, self._api_base, exc_info=True)
            raise
        message = response.choices[0].message  # type: ignore[attr-defined]
        return _message_to_dict(message)

    @property
    def api_base(self) -> str:
        return self._api_base


def _derive_api_base(base_url: str, completions_path: str) -> str:
    """把 base-url + completions-path 转成 litellm 的 api_base。

    例：https://api.deepseek.com + /v1/chat/completions -> https://api.deepseek.com/v1
    注意：base 已含版本段（如 DashScope .../compatible-mode/v1）时，
    completions_path 应传 "/chat/completions"，避免重复拼出 /v1/v1。
    """
    base = (base_url or "").rstrip("/")
    path = (completions_path or "").strip()
    suffix = "/chat/completions"
    if path.endswith(suffix):
        path = path[: -len(suffix)]
    elif path and not path.endswith("/v1"):
        # 非常规路径时保留原路径（litellm 会再追加 /chat/completions）
        logger.warning("unexpected completions-path: %s", path)
    return base + path


class RoutingLlmClient:
    """按用户路由的 LLM 客户端（Python 复现扩展功能，非原 Java）。

    cc-switch 风格多模型选择：聊天时按 userId 从主服务拉取该用户自配的
    当前提供商配置（ModelConfigPort，带 TTL 缓存），命中则用配置构建/复用
    LiteLlmClient；未配置、拉取失败或 user_id 缺失时回落装配默认客户端。
    """

    _CONFIG_TTL_SECONDS = 20.0  # 配置缓存 TTL：设置页切换后最迟 20s 生效
    _CACHE_MAX = 64  # 客户端缓存上限（防长期运行膨胀），超限整体重建

    def __init__(self, default_client: "LiteLlmClient", config_port: Any) -> None:
        self._default = default_client
        self._port = config_port
        self._clients: dict[tuple[str, str], LiteLlmClient] = {}
        self._configs: dict[str, tuple[float, dict[str, Any] | None]] = {}

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """按 user_id 路由补全（无 user_id/无配置/异常 → 默认客户端）。"""
        client = self._resolve(user_id) if user_id else None
        if client is None:
            client = self._default
        return client.chat(messages, tools, user_id=user_id)

    def _resolve(self, user_id: str | None) -> LiteLlmClient | None:
        """解析该用户当前应使用的客户端；无配置返回 None（回落默认）。"""
        cfg = self._fetch_config(str(user_id) if user_id else "")
        if not cfg:
            return None
        fingerprint = "|".join(
            str(cfg.get(k) or "") for k in ("baseUrl", "apiKey", "model", "completionsPath")
        )
        key = (str(user_id), fingerprint)
        client = self._clients.get(key)
        if client is None:
            try:
                client = LiteLlmClient(
                    model=str(cfg.get("model") or ""),
                    base_url=str(cfg.get("baseUrl") or ""),
                    completions_path=str(cfg.get("completionsPath") or "/v1/chat/completions"),
                    api_key=str(cfg.get("apiKey") or ""),
                )
            except Exception:  # noqa: BLE001 —— 配置非法时回落默认客户端
                logger.warning("build user LlmClient failed, userId=%s", user_id, exc_info=True)
                return None
            if len(self._clients) >= self._CACHE_MAX:
                self._clients.clear()
            self._clients[key] = client
        return client

    def _fetch_config(self, user_id: str) -> dict[str, Any] | None:
        """带 TTL 缓存地拉取用户配置；任何异常降级为 None。"""
        if not user_id:
            return None
        now = time.monotonic()
        cached = self._configs.get(user_id)
        if cached is not None and now - cached[0] < self._CONFIG_TTL_SECONDS:
            return cached[1]
        try:
            cfg = self._port.fetch_user_config(user_id)
        except Exception:  # noqa: BLE001 —— 主服务不可用等场景静默回落
            logger.warning("fetch user model config failed, userId=%s", user_id, exc_info=True)
            cfg = None
        self._configs[user_id] = (now, cfg)
        return cfg


def _message_to_dict(message: Any) -> dict[str, Any]:
    """把 litellm/openai 的 Message 对象转为可 JSON 持久化的 dict（OpenAI 格式）。"""
    msg: dict[str, Any] = {"role": "assistant", "content": message.content}
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        serialized: list[dict[str, Any]] = []
        for tc in tool_calls:
            fn = getattr(tc, "function", None)
            serialized.append({
                "id": getattr(tc, "id", None) or "",
                "type": "function",
                "function": {
                    "name": getattr(fn, "name", "") or "",
                    "arguments": getattr(fn, "arguments", "") or "{}",
                },
            })
        msg["tool_calls"] = serialized
    return msg
