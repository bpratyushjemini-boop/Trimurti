"""
NARAD Phase 3 — Mobile Chat API Router.
Provides stable endpoints for iOS mobile chat interactions:
  - Send message (unary)
  - Streaming token responses (SSE with X-Accel-Buffering: no)
  - Cancel generation in-flight
  - Conversation sessions (list, create, get history, delete)
"""

import json
import asyncio
import logging
import uuid
from typing import AsyncGenerator, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.db.database import get_db, SessionLocal
from app.core.narad import narad_core
from app.services.smriti import smriti_service
from app.api.v1.schemas import (
    SendMessageRequest,
    SendMessageResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    ConversationSessionItem,
    ConversationHistoryResponse,
    ChatMessageItem,
    CancelChatRequest,
    CancelChatResponse,
    ErrorResponse,
)

logger = logging.getLogger("narad.v1.chat")

router = APIRouter(prefix="/chat", tags=["v1 - Chat"])

# In-flight generation cancellation registry keyed by session_id
_active_chat_cancels: Dict[str, asyncio.Event] = {}


def _get_cancel_event(session_id: str) -> asyncio.Event:
    if session_id not in _active_chat_cancels:
        _active_chat_cancels[session_id] = asyncio.Event()
    return _active_chat_cancels[session_id]


def _clear_cancel_event(session_id: str):
    _active_chat_cancels.pop(session_id, None)


# =============================================================================
# 1. SEND MESSAGE (UNARY)
# =============================================================================

@router.post(
    "/send",
    response_model=SendMessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Send Chat Message (Unary)"
)
async def send_message(
    payload: SendMessageRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Submits a user message to NARAD and awaits complete synthesis.
    Returns full response metadata, provider/model telemetry, and latency.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    content = payload.message.strip()
    if not content:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "EMPTY_MESSAGE",
                    "message": "Message content cannot be empty.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    # 1. Resolve or create ChatSession via Smriti
    session = smriti_service.get_or_create_session(
        session_id=payload.session_id,
        initial_title=content,
        db=db
    )

    # 2. Persist User message
    user_msg = smriti_service.add_user_message(
        session_id=session.id,
        content=content,
        db=db
    )

    # 3. Retrieve conversation history
    history_payload = smriti_service.get_conversation_history(
        session_id=session.id,
        db=db
    )

    # 4. Process through NARAD Core
    try:
        core_result = await narad_core.process_message(
            message=content,
            history=history_payload,
            session_id=session.id,
            requested_provider=payload.provider,
            requested_model=payload.model,
            is_voice=bool(payload.is_voice)
        )
    except Exception as exc:
        logger.error(f"[ChatSend] Processing error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "PROVIDER_ERROR",
                    "message": "Model generation failed. Check provider status.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": True,
                    "provider": payload.provider,
                }
            }
        )

    # 5. Persist Assistant message
    assistant_msg = smriti_service.add_assistant_message(
        session_id=session.id,
        content=core_result["response"],
        provider=core_result["provider"],
        model=core_result["model"],
        metadata=core_result,
        db=db
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    return SendMessageResponse(
        response=core_result["response"],
        session_id=session.id,
        message_id=assistant_msg.id,
        provider=core_result["provider"],
        model=core_result["model"],
        execution_mode=core_result.get("execution_mode", "cloud"),
        latency_ms=core_result.get("latency_ms", 0),
        status="success",
        tools_executed=core_result.get("tools_executed") or [],
        created_at=now_iso,
    )


# =============================================================================
# 2. STREAMING RESPONSE (SSE)
# =============================================================================

@router.post(
    "/stream",
    summary="Stream Chat Response via SSE"
)
async def stream_message(
    payload: SendMessageRequest,
    request: Request,
):
    """
    Server-Sent Events (SSE) streaming endpoint.
    Streams tokens in real time with cancel support, thinking states, and final telemetry.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    content = payload.message.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")

    async def event_generator() -> AsyncGenerator[str, None]:
        db = SessionLocal()
        session_id = payload.session_id
        try:
            session = smriti_service.get_or_create_session(
                session_id=session_id,
                initial_title=content,
                db=db
            )
            session_id = session.id
            cancel_event = _get_cancel_event(session_id)
            cancel_event.clear()

            # Record user turn
            user_msg = smriti_service.add_user_message(
                session_id=session.id,
                content=content,
                db=db
            )
            history_payload = smriti_service.get_conversation_history(
                session_id=session.id,
                db=db
            )

            # 1. Emit session event
            yield f"data: {json.dumps({'event': 'session', 'session_id': session.id, 'request_id': req_id})}\n\n"

            if cancel_event.is_set():
                yield f"data: {json.dumps({'event': 'cancelled', 'session_id': session.id})}\n\n"
                return

            # 2. Emit thinking event
            yield f"data: {json.dumps({'event': 'thinking', 'status': 'thinking'})}\n\n"

            # 3. Execute generation
            core_result = await narad_core.process_message(
                message=content,
                history=history_payload,
                session_id=session.id,
                requested_provider=payload.provider,
                requested_model=payload.model,
                is_voice=bool(payload.is_voice)
            )

            if cancel_event.is_set():
                yield f"data: {json.dumps({'event': 'cancelled', 'session_id': session.id})}\n\n"
                return

            # 4. Emit tool executions if any
            tools = core_result.get("tools_executed") or []
            if tools:
                yield f"data: {json.dumps({'event': 'tool_execution', 'tools': tools})}\n\n"

            # 5. Persist assistant turn
            assistant_msg = smriti_service.add_assistant_message(
                session_id=session.id,
                content=core_result["response"],
                provider=core_result["provider"],
                model=core_result["model"],
                metadata=core_result,
                db=db
            )

            # 6. Stream tokens
            words = core_result["response"].split(" ")
            for i, word in enumerate(words):
                if cancel_event.is_set():
                    yield f"data: {json.dumps({'event': 'cancelled', 'session_id': session.id})}\n\n"
                    return
                chunk = word + (" " if i < len(words) - 1 else "")
                yield f"data: {json.dumps({'event': 'token', 'token': chunk})}\n\n"
                await asyncio.sleep(0.01)

            # 7. Final done event
            final_data = {
                "event": "done",
                "session_id": session.id,
                "message_id": assistant_msg.id,
                "provider": core_result["provider"],
                "model": core_result["model"],
                "execution_mode": core_result.get("execution_mode", "cloud"),
                "latency_ms": core_result.get("latency_ms", 0),
                "status": "success",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(final_data)}\n\n"

        except asyncio.CancelledError:
            logger.info(f"[ChatStream] Client disconnected on session {session_id}")
            yield f"data: {json.dumps({'event': 'cancelled', 'session_id': session_id})}\n\n"
        except Exception as err:
            logger.error(f"[ChatStream] Stream error: {err}", exc_info=True)
            yield f"data: {json.dumps({'event': 'error', 'detail': str(err)})}\n\n"
        finally:
            if session_id:
                _clear_cancel_event(session_id)
            db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
            "X-Accel-Buffering": "no",
        }
    )


# =============================================================================
# 3. CANCEL GENERATION
# =============================================================================

@router.post(
    "/cancel",
    response_model=CancelChatResponse,
    summary="Cancel In-Flight Generation"
)
async def cancel_chat_generation(payload: CancelChatRequest):
    """
    Signals active chat generation to cancel execution immediately.
    Halts streaming tokens and aborts downstream model synthesis.
    """
    sid = payload.session_id
    if sid in _active_chat_cancels:
        _active_chat_cancels[sid].set()
        logger.info(f"[ChatCancel] Cancelled active generation for session: {sid}")
        return CancelChatResponse(
            success=True,
            session_id=sid,
            status="cancelled",
            message=f"Generation cancelled for session {sid}."
        )

    return CancelChatResponse(
        success=True,
        session_id=sid,
        status="cancelled",
        message="No active generation found or generation already completed."
    )


# =============================================================================
# 4. CONVERSATION SESSIONS & HISTORY
# =============================================================================

@router.get(
    "/sessions",
    response_model=List[ConversationSessionItem],
    summary="List Conversation Sessions"
)
def list_sessions(db: Session = Depends(get_db)):
    """List recent conversation sessions ordered by last active turn."""
    sessions = smriti_service.list_sessions(db=db)
    items = []
    for s in sessions:
        items.append(
            ConversationSessionItem(
                session_id=s.id,
                title=s.title,
                created_at=s.to_dict()["created_at"],
                updated_at=s.to_dict()["updated_at"],
                message_count=s.to_dict().get("message_count", 0),
            )
        )
    return items


@router.post(
    "/sessions",
    response_model=CreateSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create New Conversation Session"
)
def create_session(payload: Optional[CreateSessionRequest] = None, db: Session = Depends(get_db)):
    """Creates a new empty conversation session."""
    title = (payload.title if payload and payload.title else "New Briefing").strip()
    session = smriti_service.create_session(title=title, db=db)
    return CreateSessionResponse(
        session_id=session.id,
        title=session.title,
        created_at=session.to_dict()["created_at"],
    )


@router.get(
    "/sessions/{session_id}",
    response_model=ConversationHistoryResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get Conversation History"
)
def get_session_history(session_id: str, request: Request, db: Session = Depends(get_db)):
    """Retrieve all ordered messages for a conversation session."""
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    session = smriti_service.get_session(session_id=session_id, db=db)
    if not session:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Conversation session '{session_id}' does not exist.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    messages = smriti_service.get_session_messages(session_id=session_id, db=db)
    msg_items = []
    for m in messages:
        m_dict = m.to_dict()
        meta = {}
        if m.metadata_json:
            try:
                meta = json.loads(m.metadata_json)
            except Exception:
                meta = {}
        msg_items.append(
            ChatMessageItem(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                created_at=m_dict["created_at"],
                metadata=meta,
            )
        )

    s_dict = session.to_dict()
    return ConversationHistoryResponse(
        session_id=session.id,
        title=session.title,
        messages=msg_items,
        created_at=s_dict["created_at"],
        updated_at=s_dict["updated_at"],
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
    summary="Delete Conversation Session"
)
def delete_session(session_id: str, request: Request, db: Session = Depends(get_db)):
    """Delete a conversation session and all its messages."""
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    deleted = smriti_service.delete_session(session_id=session_id, db=db)
    if not deleted:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Conversation session '{session_id}' not found.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
