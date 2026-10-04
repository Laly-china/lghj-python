"""智能体服务 HTTP 控制器。

复现自原 Java 类：
    ai-agent-scaffoid-feng-trigger/.../trigger/http/AgentServiceController.java
    ai-agent-scaffoid-feng-api/.../api/IAgentService.java（接口契约）

对外契约（严格照抄）：
    GET  /api/v1/query_ai_agent_config_list   查询智能体配置列表
    GET  /api/v1/create_session?agentId&userId  创建会话（GET）
    POST /api/v1/create_session               创建会话（POST，body: {agentId, userId}）
    POST /api/v1/chat                          阻塞对话（body: {agentId, userId, sessionId, message}）
    POST /api/v1/chat_stream                   流式对话（ResponseBodyEmitter：原样写文本流，无 SSE data: 前缀）
统一响应体 Response{code, info, data}；异常按 AppException.code / UN_ERROR 兜底。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.api.dto import (
    AiAgentConfigResponseDTO,
    ChatRequestDTO,
    ChatResponseDTO,
    CreateSessionRequestDTO,
    CreateSessionResponseDTO,
)
from app.api.response import Response
from app.domain.agent.service.chat_service import ChatService
from app.types.app_exception import AppException
from app.types.response_code import ResponseCode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


def _get_chat_service(request: Request) -> ChatService:
    """从应用状态取对话服务（等价原 Java @Resource 注入）。"""
    return request.app.state.chat_service  # type: ignore[no-any-return]


@router.get("/query_ai_agent_config_list", response_model=Response[list[AiAgentConfigResponseDTO]])
def query_ai_agent_config_list(request: Request) -> Response[list[AiAgentConfigResponseDTO]]:
    """查询 AI 智能体配置列表（照抄原 Java queryAiAgentConfigList）。"""
    try:
        agent_configs = _get_chat_service(request).query_ai_agent_config_list()
        response_dtos = [
            AiAgentConfigResponseDTO(
                agentId=config.agentId,
                agentName=config.agentName,
                agentDesc=config.agentDesc,
            )
            for config in agent_configs
        ]
        return Response.build(ResponseCode.SUCCESS.value, ResponseCode.SUCCESS.info, response_dtos)
    except AppException as exc:
        logger.error("query ai agent config list failed: %s", exc)
        return Response.build(exc.code, exc.info)
    except Exception:  # noqa: BLE001 对齐原 Java catch (Exception)
        logger.error("query ai agent config list failed", exc_info=True)
        return Response.build(ResponseCode.UN_ERROR.value, ResponseCode.UN_ERROR.info)


# ====================== create_session：GET / POST 两个入口，共用 doCreateSession ======================

@router.get("/create_session", response_model=Response[CreateSessionResponseDTO])
def create_session_by_get(request: Request, agentId: str, userId: str) -> Response[CreateSessionResponseDTO]:
    """GET 创建会话（照抄原 Java createSessionByGet：@RequestParam 必填）。"""
    return _do_create_session(request, CreateSessionRequestDTO(agentId=agentId, userId=userId))


@router.post("/create_session", response_model=Response[CreateSessionResponseDTO])
def create_session_by_post(request: Request, dto: CreateSessionRequestDTO) -> Response[CreateSessionResponseDTO]:
    """POST 创建会话（照抄原 Java createSessionByPost）。"""
    return _do_create_session(request, dto)


def _do_create_session(request: Request, dto: CreateSessionRequestDTO) -> Response[CreateSessionResponseDTO]:
    """创建会话公共逻辑（照抄原 Java doCreateSession）。"""
    try:
        session_id = _get_chat_service(request).create_session(dto.agentId, dto.userId)
        return Response.build(
            ResponseCode.SUCCESS.value,
            ResponseCode.SUCCESS.info,
            CreateSessionResponseDTO(sessionId=session_id),
        )
    except AppException as exc:
        logger.error("create session failed: %s", exc)
        return Response.build(exc.code, exc.info)
    except Exception:  # noqa: BLE001
        logger.error("create session failed", exc_info=True)
        return Response.build(ResponseCode.UN_ERROR.value, ResponseCode.UN_ERROR.info)


# ====================== chat：阻塞对话 ======================

@router.post("/chat", response_model=Response[ChatResponseDTO])
def chat(request: Request, dto: ChatRequestDTO) -> Response[ChatResponseDTO]:
    """阻塞式对话（照抄原 Java chat：sessionId 为空先建会话，输出按 \n 连接）。"""
    try:
        chat_service = _get_chat_service(request)
        session_id = dto.sessionId
        if not session_id:
            session_id = chat_service.create_session(dto.agentId, dto.userId)

        messages = chat_service.handle_message(dto.agentId, dto.userId, session_id, dto.message)

        return Response.build(
            ResponseCode.SUCCESS.value,
            ResponseCode.SUCCESS.info,
            ChatResponseDTO(content="\n".join(messages)),
        )
    except AppException as exc:
        logger.error("chat failed: %s", exc)
        return Response.build(exc.code, exc.info)
    except Exception:  # noqa: BLE001
        logger.error("chat failed", exc_info=True)
        return Response.build(ResponseCode.UN_ERROR.value, ResponseCode.UN_ERROR.info)


# ====================== chat_stream：流式对话 ======================

@router.post("/chat_stream", response_model=None)
def chat_stream(request: Request, dto: ChatRequestDTO) -> Response[ChatResponseDTO] | StreamingResponse:
    """流式对话（对应原 Java chatStream + ResponseBodyEmitter）。

    原 Java 用 ResponseBodyEmitter.send(event.stringifyContent()) 把每个事件文本
    原样写入响应体（无 "data:" SSE 前缀），超时 3 分钟。Python 侧用 StreamingResponse
    等价实现：事件粒度为一次模型响应（与原 Java 非流式事件模型一致）。

    偏差处理：原 Java 会话创建失败时 emitter.completeWithError 触发 HTTP 500；
    这里在建立流之前完成校验/建会话，失败时返回统一 Response 错误体（HTTP 200），
    与本服务其余接口的错误契约保持一致（见交付报告偏差说明）。
    """
    chat_service = _get_chat_service(request)
    try:
        session_id = dto.sessionId
        if not session_id:
            session_id = chat_service.create_session(dto.agentId, dto.userId)
    except AppException as exc:
        logger.error("chat stream failed: %s", exc)
        return Response.build(exc.code, exc.info)
    except Exception:  # noqa: BLE001
        logger.error("chat stream failed", exc_info=True)
        return Response.build(ResponseCode.UN_ERROR.value, ResponseCode.UN_ERROR.info)

    def event_body() -> Iterator[str]:
        try:
            events = chat_service.handle_message_stream(dto.agentId, dto.userId, session_id, dto.message)
            for event in events:
                text = event.stringify_content()
                if text:
                    yield text
        except Exception:  # noqa: BLE001 对齐原 Java completeWithError：记录并终止流
            logger.error("send stream event failed", exc_info=True)
            return

    return StreamingResponse(
        event_body(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx 场景关闭缓冲，保证流式
        },
    )


# ====================== 扩展接口：Agent 流程可视化（本工程扩展，原 Java 无） ======================


@router.get("/trace", response_model=Response[list[dict]])
def query_trace(request: Request, agentId: str, userId: str, sessionId: str) -> Response[list[dict]]:
    """查询会话执行轨迹（扩展接口）。

    data 为事件列表（按发生顺序）：
        {seq, ts, type, agent, name, args, result, durationMs}
    type 取值：run_start（提问边界）/ llm_call（一轮模型决策）/ transfer（Supervisor 转交）
    / tool（本地工具调用，args=入参 result=摘要）/ agent_text（文本产出）。
    会话不存在（服务重启后）返回空列表。
    """
    try:
        events = _get_chat_service(request).get_trace(agentId, userId, sessionId)
        return Response.build(ResponseCode.SUCCESS.value, ResponseCode.SUCCESS.info, events)
    except AppException as exc:
        logger.error("query trace failed: %s", exc)
        return Response.build(exc.code, exc.info)
    except Exception:  # noqa: BLE001
        logger.error("query trace failed", exc_info=True)
        return Response.build(ResponseCode.UN_ERROR.value, ResponseCode.UN_ERROR.info)


@router.get("/agent_team", response_model=Response[dict])
def query_agent_team(request: Request, agentId: str) -> Response[dict]:
    """查询智能体团队结构（扩展接口）：{agentId, supervisor, experts, tools}。

    supervisor/experts 的 name 与 description 来自装配 yml（管家的职能说明数据源）。
    """
    try:
        team = _get_chat_service(request).get_team(agentId)
        return Response.build(ResponseCode.SUCCESS.value, ResponseCode.SUCCESS.info, team)
    except AppException as exc:
        logger.error("query agent team failed: %s", exc)
        return Response.build(exc.code, exc.info)
    except Exception:  # noqa: BLE001
        logger.error("query agent team failed", exc_info=True)
        return Response.build(ResponseCode.UN_ERROR.value, ResponseCode.UN_ERROR.info)


# ====================== 扩展接口：历史会话（MySQL 持久化，原 Java 无） ======================


@router.get("/history_list", response_model=Response[list[dict]])
def history_list(request: Request, userId: str, limit: int = 50) -> Response[list[dict]]:
    """用户历史会话列表（按最近活跃倒序）：[{sessionId, agentId, title, updateTime}]。"""
    try:
        from app.infrastructure import chat_store

        return Response.build(
            ResponseCode.SUCCESS.value, ResponseCode.SUCCESS.info,
            chat_store.list_sessions(userId, limit),
        )
    except Exception:  # noqa: BLE001 存储不可用降级为空列表
        logger.error("history list failed", exc_info=True)
        return Response.build(ResponseCode.SUCCESS.value, ResponseCode.SUCCESS.info, [])


@router.get("/history_messages", response_model=Response[list[dict]])
def history_messages(request: Request, sessionId: str) -> Response[list[dict]]:
    """历史会话消息（正序）：[{role, content, createTime}]，assistant 附 trace。"""
    try:
        from app.infrastructure import chat_store

        return Response.build(
            ResponseCode.SUCCESS.value, ResponseCode.SUCCESS.info,
            chat_store.get_messages(sessionId),
        )
    except Exception:  # noqa: BLE001
        logger.error("history messages failed", exc_info=True)
        return Response.build(ResponseCode.SUCCESS.value, ResponseCode.SUCCESS.info, [])


@router.delete("/history_session", response_model=Response[dict])
def delete_history_session(request: Request, sessionId: str, userId: str) -> Response[dict]:
    """删除历史会话（按归属校验，物理删除消息与会话行）。"""
    try:
        from app.infrastructure import chat_store

        deleted = chat_store.delete_session(sessionId, userId)
        return Response.build(
            ResponseCode.SUCCESS.value, ResponseCode.SUCCESS.info,
            {"deleted": deleted},
        )
    except Exception:  # noqa: BLE001
        logger.error("history delete failed", exc_info=True)
        return Response.build(ResponseCode.UN_ERROR.value, ResponseCode.UN_ERROR.info)


# ====================== 扩展接口：个人知识库（MySQL 持久化，原 Java 无） ======================

# 单文件大小上限（字节）：纯文本演示场景
_KB_UPLOAD_MAX_BYTES = 512 * 1024
# 允许的扩展名（纯文本）
_KB_ALLOWED_SUFFIXES = (".txt", ".md")


@router.post("/kb_upload", response_model=Response[dict])
async def kb_upload(
    request: Request,
    userId: str = Form(...),
    file: UploadFile = File(...),
) -> Response[dict]:
    """上传纯文本知识库文档（txt/md，≤512KB），落库后可被 queryKnowledgeBase 检索。"""
    try:
        from app.infrastructure import chat_store

        filename = file.filename or "未命名.txt"
        if not filename.lower().endswith(_KB_ALLOWED_SUFFIXES):
            return Response.build(ResponseCode.ILLEGAL_PARAMETER.value,
                                  "仅支持 txt / md 纯文本文档")
        raw = await file.read()
        if len(raw) > _KB_UPLOAD_MAX_BYTES:
            return Response.build(ResponseCode.ILLEGAL_PARAMETER.value,
                                  "文件过大（上限 512KB）")
        # 优先 UTF-8，失败回落 GBK（Windows 导出文件常见）
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = raw.decode("gbk", errors="replace")
        title = filename.rsplit(".", 1)[0] or filename
        doc_id = chat_store.add_kb_doc(userId, title, filename, content)
        return Response.build(
            ResponseCode.SUCCESS.value, ResponseCode.SUCCESS.info,
            {"docId": doc_id, "title": title, "charCount": len(content)},
        )
    except Exception:  # noqa: BLE001
        logger.error("kb upload failed", exc_info=True)
        return Response.build(ResponseCode.UN_ERROR.value, ResponseCode.UN_ERROR.info)


@router.get("/kb_list", response_model=Response[list[dict]])
def kb_list(request: Request, userId: str) -> Response[list[dict]]:
    """用户知识库文档列表：[{id, title, charCount, createTime}]。"""
    try:
        from app.infrastructure import chat_store

        return Response.build(
            ResponseCode.SUCCESS.value, ResponseCode.SUCCESS.info,
            chat_store.list_kb_docs(userId),
        )
    except Exception:  # noqa: BLE001
        logger.error("kb list failed", exc_info=True)
        return Response.build(ResponseCode.SUCCESS.value, ResponseCode.SUCCESS.info, [])


@router.delete("/kb_doc", response_model=Response[dict])
def kb_delete(request: Request, docId: int, userId: str) -> Response[dict]:
    """删除知识库文档（逻辑删除，按归属校验）。"""
    try:
        from app.infrastructure import chat_store

        deleted = chat_store.delete_kb_doc(docId, userId)
        return Response.build(
            ResponseCode.SUCCESS.value, ResponseCode.SUCCESS.info,
            {"deleted": deleted},
        )
    except Exception:  # noqa: BLE001
        logger.error("kb delete failed", exc_info=True)
        return Response.build(ResponseCode.UN_ERROR.value, ResponseCode.UN_ERROR.info)
