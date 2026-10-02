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

from fastapi import APIRouter, Request
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
