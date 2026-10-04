"""会话历史与知识库数据访问（本工程扩展，原 Java 无）。

- record_turn：每轮对话落库（先建会话行再插消息，标题取首条提问截断）；
- 历史查询/删除：供 /api/v1/history_* 接口与前端历史栏使用；
- 知识库：上传/列表/删除/关键词检索（用户隔离，逻辑删除）；
- DbKbSearchPort：领域层 KbSearchPort 的 MySQL 实现，经本地工具
  queryKnowledgeBase 供 LLM 检索用户文档。

所有失败向上抛出，由调用方（chat_service / controller）决定降级方式。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from sqlalchemy import text

from app.domain.agent.adapter.port import KbSearchPort
from app.infrastructure.database import session_tx

logger = logging.getLogger(__name__)

# 会话标题长度（首条用户提问截取）
_TITLE_LIMIT = 30
# 单文档大小上限（字符）
_KB_DOC_MAX_CHARS = 200_000


# ====================== 会话历史 ======================

def record_turn(session_id: str, agent_id: str, user_id: str,
                user_text: str, assistant_text: str, trace: list[dict] | None) -> None:
    """落库一轮对话：确保会话行存在 → 插用户消息 → 插助手消息（含轨迹 JSON）。"""
    if not session_id:
        return
    with session_tx() as conn:
        conn.execute(text(
            "INSERT INTO agent_chat_session (session_id, agent_id, user_id) "
            "VALUES (:sid, :aid, :uid) ON DUPLICATE KEY UPDATE update_time = NOW()"
        ), {"sid": session_id, "aid": agent_id, "uid": user_id})
        if user_text:
            conn.execute(text(
                "INSERT INTO agent_chat_message (session_id, role, content) "
                "VALUES (:sid, 'user', :content)"
            ), {"sid": session_id, "content": user_text})
            # 首条提问作为会话标题（仍是默认标题时才更新）
            conn.execute(text(
                "UPDATE agent_chat_session SET title = :title "
                "WHERE session_id = :sid AND title = '新对话'"
            ), {"sid": session_id, "title": user_text.strip()[:_TITLE_LIMIT] or "新对话"})
        if assistant_text:
            conn.execute(text(
                "INSERT INTO agent_chat_message (session_id, role, content, trace_json) "
                "VALUES (:sid, 'assistant', :content, :trace)"
            ), {"sid": session_id, "content": assistant_text,
                "trace": json.dumps(trace or [], ensure_ascii=False) if trace is not None else None})


def list_sessions(user_id: str, limit: int = 50) -> list[dict]:
    """用户的历史会话列表（按最近活跃倒序）。"""
    with session_tx() as conn:
        rows = conn.execute(text(
            "SELECT session_id, agent_id, title, update_time "
            "FROM agent_chat_session WHERE user_id = :uid "
            "ORDER BY update_time DESC LIMIT :lim"
        ), {"uid": user_id, "lim": int(limit)}).mappings().all()
    return [
        {
            "sessionId": r["session_id"],
            "agentId": r["agent_id"],
            "title": r["title"],
            "updateTime": r["update_time"].strftime("%Y-%m-%d %H:%M") if isinstance(r["update_time"], datetime) else str(r["update_time"]),
        }
        for r in rows
    ]


def get_messages(session_id: str) -> list[dict]:
    """会话的全部消息（按时间正序；assistant 消息附带轨迹对象）。"""
    with session_tx() as conn:
        rows = conn.execute(text(
            "SELECT role, content, trace_json, create_time "
            "FROM agent_chat_message WHERE session_id = :sid ORDER BY id"
        ), {"sid": session_id}).mappings().all()
    messages: list[dict] = []
    for r in rows:
        item: dict = {
            "role": r["role"],
            "content": r["content"] or "",
            "createTime": r["create_time"].strftime("%Y-%m-%d %H:%M") if isinstance(r["create_time"], datetime) else str(r["create_time"]),
        }
        if r["role"] == "assistant":
            try:
                item["trace"] = json.loads(r["trace_json"]) if r["trace_json"] else []
            except Exception:  # noqa: BLE001 轨迹损坏按空处理
                item["trace"] = []
        messages.append(item)
    return messages


def delete_session(session_id: str, user_id: str) -> bool:
    """删除历史会话（物理删除消息，会话行按归属校验后删除）。"""
    with session_tx() as conn:
        row = conn.execute(text(
            "SELECT id FROM agent_chat_session WHERE session_id = :sid AND user_id = :uid"
        ), {"sid": session_id, "uid": user_id}).first()
        if row is None:
            return False
        conn.execute(text("DELETE FROM agent_chat_message WHERE session_id = :sid"), {"sid": session_id})
        conn.execute(text("DELETE FROM agent_chat_session WHERE session_id = :sid"), {"sid": session_id})
    return True


# ====================== 个人知识库 ======================

def add_kb_doc(user_id: str, title: str, filename: str | None, content: str) -> int:
    """新增知识库文档，返回文档 ID。"""
    content = content[:_KB_DOC_MAX_CHARS]
    with session_tx() as conn:
        result = conn.execute(text(
            "INSERT INTO agent_kb_doc (user_id, title, filename, content, char_count) "
            "VALUES (:uid, :title, :fname, :content, :chars)"
        ), {"uid": user_id, "title": title[:200], "fname": (filename or "")[:255] or None,
            "content": content, "chars": len(content)})
    return int(result.lastrowid or 0)


def list_kb_docs(user_id: str, include_content: bool = False) -> list[dict]:
    """用户的未删除文档列表（可选带正文，供检索）。"""
    cols = "id, title, filename, char_count, create_time" + (", content" if include_content else "")
    with session_tx() as conn:
        rows = conn.execute(text(
            f"SELECT {cols} FROM agent_kb_doc "
            "WHERE user_id = :uid AND is_deleted = 0 ORDER BY id DESC"
        ), {"uid": user_id}).mappings().all()
    docs: list[dict] = []
    for r in rows:
        doc: dict = {
            "id": int(r["id"]),
            "title": r["title"],
            "charCount": int(r["char_count"]),
            "createTime": r["create_time"].strftime("%Y-%m-%d %H:%M") if isinstance(r["create_time"], datetime) else str(r["create_time"]),
        }
        if include_content:
            doc["content"] = r["content"] or ""
        docs.append(doc)
    return docs


def list_kb_titles(user_id: str, limit: int = 10) -> list[str]:
    """文档标题列表（注入对话上下文，提示模型知识库可用）。"""
    with session_tx() as conn:
        rows = conn.execute(text(
            "SELECT title FROM agent_kb_doc "
            "WHERE user_id = :uid AND is_deleted = 0 ORDER BY id DESC LIMIT :lim"
        ), {"uid": user_id, "lim": int(limit)}).scalars().all()
    return list(rows)


def delete_kb_doc(doc_id: int, user_id: str) -> bool:
    """逻辑删除文档（按归属校验）。"""
    with session_tx() as conn:
        result = conn.execute(text(
            "UPDATE agent_kb_doc SET is_deleted = 1 WHERE id = :did AND user_id = :uid AND is_deleted = 0"
        ), {"did": int(doc_id), "uid": user_id})
    return bool(result.rowcount and result.rowcount > 0)


_TERM_SPLIT = re.compile(r"[\s,，。;；、:：!！?？()\[\]{}\"'`~@#$%^&*+=|\\/<>]+")
# 检索片段长度
_SNIPPET_LIMIT = 200


def search_kb(user_id: str, query: str, limit: int = 5) -> list[dict]:
    """关键词检索用户文档：按段落计分（词频求和），返回得分最高的若干片段。

    简易实现（不引入分词/向量依赖）：查询串按标点/空白切词（≥2 字符才算词），
    全量载入用户文档后逐段匹配计分——个人知识库规模（几十篇内）足够。
    """
    terms = [t for t in _TERM_SPLIT.split((query or "").strip()) if len(t) >= 2][:8]
    if not terms:
        return []
    scored: list[tuple[int, str, str]] = []
    for doc in list_kb_docs(user_id, include_content=True):
        for para in (doc.get("content") or "").split("\n"):
            para = para.strip()
            if not para:
                continue
            score = sum(para.count(t) for t in terms)
            if score > 0:
                scored.append((score, doc["title"], para))
    scored.sort(key=lambda x: -x[0])
    return [{"title": title, "snippet": snippet[:_SNIPPET_LIMIT], "score": score}
            for score, title, snippet in scored[: int(limit)]]


# ====================== 领域端口实现 ======================

class DbKbSearchPort(KbSearchPort):
    """KbSearchPort 的 MySQL 实现（注入本地工具 queryKnowledgeBase）。"""

    def list_titles(self, user_id: str, limit: int = 10) -> list[str]:
        try:
            return list_kb_titles(user_id, limit)
        except Exception:  # noqa: BLE001 上下文注入失败不阻断对话
            logger.warning("list kb titles failed", exc_info=True)
            return []

    def search(self, user_id: str, query: str, limit: int = 5) -> list[dict]:
        return search_kb(user_id, query, limit)
