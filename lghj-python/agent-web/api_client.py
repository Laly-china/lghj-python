# -*- coding: utf-8 -*-
"""api_client.py —— AI 投顾终端（agent-web）的三后端 HTTP 客户端。

- 主服务 8080：Result{code,msg,data}，成功码 200（数字），仅用于登录/登出
- 智能体服务 8091：Response{code,info,data}，成功码 "0000"（字符串），
  含本工程扩展接口 trace / agent_team / history_* / kb_*
所有函数失败时返回安全默认值（False/None/[]），不让 UI 层崩溃。
"""

from __future__ import annotations

import os
from typing import Any

import httpx

MAIN = os.environ.get("LGHJ_MAIN_URL", "http://127.0.0.1:8080")
AGENT = os.environ.get("LGHJ_AGENT_URL", "http://127.0.0.1:8091")

_SHORT = httpx.Timeout(10.0)
# chat 走 LLM 工具往返可达数十秒，读超时放宽（对齐服务端 180s 预算）
_CHAT = httpx.Timeout(180.0, connect=10.0)


# ====================== 登录（主服务 8080） ======================

def login(username: str, password: str) -> tuple[bool, dict | str]:
    """登录，成功返回登录 data（token/id/username/userType/identityDesc），失败返回错误文案。"""
    try:
        r = httpx.post(f"{MAIN}/api/login", json={"username": username, "password": password},
                       timeout=_SHORT)
        body = r.json()
    except Exception:  # noqa: BLE001
        return False, "主服务连接失败，请确认 8080 已启动"
    if body.get("code") == 200 and body.get("data"):
        return True, body["data"]
    return False, body.get("msg") or "用户名或密码错误"


# ====================== 智能体（8091，Response 包装） ======================

def _agent_post(path: str, json_body: dict[str, Any], timeout: httpx.Timeout = _SHORT) -> tuple[bool, Any, str]:
    try:
        r = httpx.post(f"{AGENT}{path}", json=json_body, timeout=timeout)
        body = r.json()
    except Exception:  # noqa: BLE001
        return False, None, "智能体服务连接失败，请确认 8091 已启动"
    return body.get("code") == "0000", body.get("data"), body.get("info") or ""


def _agent_get(path: str, params: dict[str, Any], timeout: httpx.Timeout = _SHORT) -> tuple[bool, Any, str]:
    try:
        r = httpx.get(f"{AGENT}{path}", params=params, timeout=timeout)
        body = r.json()
    except Exception:  # noqa: BLE001
        return False, None, "智能体服务连接失败，请确认 8091 已启动"
    return body.get("code") == "0000", body.get("data"), body.get("info") or ""


def agent_team(agent_id: str) -> dict | None:
    """团队结构 {supervisor, experts, tools}；不可用返回 None。"""
    ok, data, _i = _agent_get("/api/v1/agent_team", {"agentId": agent_id})
    return data if ok else None


def create_session(agent_id: str, user_id: str) -> str | None:
    """创建会话（同 (agentId,userId) 幂等复用），失败返回 None。"""
    ok, data, _i = _agent_post("/api/v1/create_session", {"agentId": agent_id, "userId": str(user_id)})
    if ok and isinstance(data, dict):
        return data.get("sessionId")
    return None


def chat(agent_id: str, user_id: str, session_id: str, message: str) -> tuple[bool, str]:
    """阻塞式对话（LLM 真调，放在后台线程执行）。"""
    ok, data, info = _agent_post("/api/v1/chat", {
        "agentId": agent_id, "userId": str(user_id),
        "sessionId": session_id, "message": message,
    }, timeout=_CHAT)
    if ok and isinstance(data, dict):
        return True, data.get("content") or ""
    return False, info or "智能体暂不可用"


def trace(agent_id: str, user_id: str, session_id: str) -> list[dict]:
    """会话执行轨迹（生成期间轮询即可看到新增事件）。"""
    ok, data, _i = _agent_get("/api/v1/trace", {
        "agentId": agent_id, "userId": str(user_id), "sessionId": session_id,
    })
    return data if ok and isinstance(data, list) else []


# ====================== 历史（8091 扩展，MySQL 持久化） ======================

def history_list(user_id: str) -> list[dict]:
    """历史会话列表 [{sessionId, agentId, title, updateTime}]（最近活跃倒序）。"""
    ok, data, _i = _agent_get("/api/v1/history_list", {"userId": str(user_id)})
    return data if ok and isinstance(data, list) else []


def history_messages(session_id: str) -> list[dict]:
    """历史消息 [{role, content, createTime}]（assistant 附 trace）。"""
    ok, data, _i = _agent_get("/api/v1/history_messages", {"sessionId": session_id})
    return data if ok and isinstance(data, list) else []


def history_delete(session_id: str, user_id: str) -> bool:
    try:
        r = httpx.delete(f"{AGENT}/api/v1/history_session",
                         params={"sessionId": session_id, "userId": str(user_id)}, timeout=_SHORT)
        return r.json().get("code") == "0000"
    except Exception:  # noqa: BLE001
        return False


# ====================== 知识库（8091 扩展，MySQL 持久化） ======================

def kb_list(user_id: str) -> list[dict]:
    """知识库文档列表 [{id, title, charCount, createTime}]。"""
    ok, data, _i = _agent_get("/api/v1/kb_list", {"userId": str(user_id)})
    return data if ok and isinstance(data, list) else []


def kb_upload(user_id: str, filename: str, content: bytes) -> tuple[bool, str]:
    """上传纯文本文档（txt/md），成功返回提示文案。"""
    try:
        r = httpx.post(f"{AGENT}/api/v1/kb_upload",
                       data={"userId": str(user_id)},
                       files={"file": (filename, content)},
                       timeout=_SHORT)
        body = r.json()
    except Exception:  # noqa: BLE001
        return False, "知识库服务连接失败"
    if body.get("code") == "0000" and isinstance(body.get("data"), dict):
        return True, f"已收录《{body['data'].get('title', filename)}》"
    return False, body.get("info") or "上传失败"


def kb_delete(doc_id: int, user_id: str) -> bool:
    try:
        r = httpx.delete(f"{AGENT}/api/v1/kb_doc",
                         params={"docId": doc_id, "userId": str(user_id)}, timeout=_SHORT)
        return r.json().get("code") == "0000"
    except Exception:  # noqa: BLE001
        return False
