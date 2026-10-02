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

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> dict[str, Any]:
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
