from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any, List, AsyncGenerator
import json
import asyncio
import logging
from datetime import datetime

from app.db.database import get_db, SessionLocal
from app.db.models import ChatSession, ChatMessage
from app.core.narad import narad_core
from app.services.smriti import smriti_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])

class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    is_voice: Optional[bool] = False

class ChatResponse(BaseModel):
    response: str
    provider: str
    model: str
    execution_mode: Optional[str] = "cloud"
    execution: Optional[str] = "cloud"
    network_required: Optional[bool] = None
    endpoint: Optional[str] = None
    latency_ms: int
    latency: Optional[int] = 0
    status: str
    chat_id: str
    fallback: Optional[bool] = False
    fallback_used: Optional[bool] = False
    fallback_path: Optional[str] = None
    fallback_reason: Optional[str] = None
    route_reason: Optional[str] = None
    why_this_choice: Optional[str] = None
    execution_constraint: Optional[str] = None
    tools_executed: Optional[List[Dict[str, Any]]] = []
    user_message: Optional[Dict[str, Any]] = None
    assistant_message: Optional[Dict[str, Any]] = None
    runtime_truth: Optional[Dict[str, Any]] = None

def _normalize_tools(tools_list):
    norm = []
    for t in tools_list or []:
        if isinstance(t, dict):
            t_copy = dict(t)
            val = t_copy.get("name") or t_copy.get("tool") or "unknown"
            t_copy["name"] = val
            t_copy["tool"] = val
            norm.append(t_copy)
        else:
            norm.append(t)
    return norm

@router.post("", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat_endpoint(payload: ChatRequest, db: Session = Depends(get_db)):
    """
    Primary NARAD V3.1 chat endpoint.
    Processes user directive via Smriti Memory Layer, NARAD Core & Model Router,
    executes intelligent failover if transient errors occur, measures exact latency,
    and returns rich self-awareness telemetry.
    """
    content = payload.message.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")

    # 1. Resolve or create ChatSession via Smriti
    session = smriti_service.get_or_create_session(
        session_id=payload.chat_id,
        initial_title=content,
        db=db
    )

    # 2. Persist User message via Smriti
    user_msg = smriti_service.add_user_message(
        session_id=session.id,
        content=content,
        db=db
    )

    # 3. Retrieve ordered session context history via Smriti
    history_payload = smriti_service.get_conversation_history(
        session_id=session.id,
        db=db
    )

    # 4. Dispatch through NARAD Core & Model Router (with automated failover)
    core_result = await narad_core.process_message(
        message=content,
        history=history_payload,
        session_id=session.id,
        requested_provider=payload.provider,
        requested_model=payload.model,
        is_voice=bool(payload.is_voice)
    )

    # 5. Persist Assistant message via Smriti
    assistant_msg = smriti_service.add_assistant_message(
        session_id=session.id,
        content=core_result["response"],
        provider=core_result["provider"],
        model=core_result["model"],
        metadata=core_result,
        db=db
    )

    normalized_tools = _normalize_tools(core_result.get("tools_executed", []))

    return {
        "response": core_result["response"],
        "provider": core_result["provider"],
        "model": core_result["model"],
        "execution_mode": core_result.get("execution_mode", "cloud"),
        "execution": core_result.get("execution", "cloud"),
        "endpoint": core_result.get("endpoint"),
        "latency_ms": core_result["latency_ms"],
        "latency": core_result.get("latency", core_result["latency_ms"]),
        "status": core_result["status"],
        "chat_id": session.id,
        "fallback": core_result.get("fallback", False),
        "fallback_used": core_result.get("fallback_used", core_result.get("fallback", False)),
        "fallback_path": core_result.get("fallback_path"),
        "fallback_reason": core_result.get("fallback_reason"),
        "route_reason": core_result.get("route_reason"),
        "why_this_choice": core_result.get("why_this_choice"),
        "execution_constraint": core_result.get("execution_constraint"),
        "network_required": core_result.get("network_required"),
        "runtime_truth": core_result.get("runtime_truth"),
        "tools_executed": normalized_tools,
        "user_message": user_msg.to_dict(),
        "assistant_message": assistant_msg.to_dict()
    }

@router.post("/stream")
async def chat_stream_endpoint(payload: ChatRequest):
    """
    Server-Sent Events (SSE) token streaming endpoint for NARAD V3.1.
    Streams token increments progressively while saving session dialogue turns to SQLite.
    """
    content = payload.message.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")

    async def event_generator() -> AsyncGenerator[str, None]:
        db = SessionLocal()
        try:
            session = smriti_service.get_or_create_session(
                session_id=payload.chat_id,
                initial_title=content,
                db=db
            )
            user_msg = smriti_service.add_user_message(
                session_id=session.id,
                content=content,
                db=db
            )
            history_payload = smriti_service.get_conversation_history(
                session_id=session.id,
                db=db
            )

            # First emit session creation / metadata event
            yield f"data: {json.dumps({'event': 'session', 'chat_id': session.id})}\n\n"

            # Emit thinking event
            yield f"data: {json.dumps({'event': 'thinking', 'status': 'thinking'})}\n\n"

            # Execute Core synthesis
            core_result = await narad_core.process_message(
                message=content,
                history=history_payload,
                session_id=session.id,
                requested_provider=payload.provider,
                requested_model=payload.model,
                is_voice=bool(payload.is_voice)
            )

            # If tools were executed, emit tool_execution event
            tools = core_result.get("tools_executed") or []
            if tools:
                yield f"data: {json.dumps({'event': 'tool_execution', 'status': 'tool_execution', 'tools': tools})}\n\n"

            # Persist assistant turn
            assistant_msg = smriti_service.add_assistant_message(
                session_id=session.id,
                content=core_result["response"],
                provider=core_result["provider"],
                model=core_result["model"],
                metadata=core_result,
                db=db
            )

            # Stream response in chunks
            words = core_result["response"].split(" ")
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                yield f"data: {json.dumps({'event': 'token', 'token': chunk})}\n\n"
                await asyncio.sleep(0.012)

            # Final complete telemetry event
            final_payload = {
                "event": "done",
                "chat_id": session.id,
                "provider": core_result["provider"],
                "model": core_result["model"],
                "execution_mode": core_result.get("execution_mode", "cloud"),
                "execution": core_result.get("execution", "cloud"),
                "endpoint": core_result.get("endpoint"),
                "latency_ms": core_result["latency_ms"],
                "latency": core_result.get("latency", core_result["latency_ms"]),
                "status": core_result["status"],
                "fallback": core_result.get("fallback", False),
                "fallback_used": core_result.get("fallback_used", core_result.get("fallback", False)),
                "fallback_path": core_result.get("fallback_path"),
                "fallback_reason": core_result.get("fallback_reason"),
                "route_reason": core_result.get("route_reason"),
                "why_this_choice": core_result.get("why_this_choice"),
                "network_required": core_result.get("network_required"),
                "runtime_truth": core_result.get("runtime_truth"),
                "tools_executed": _normalize_tools(core_result.get("tools_executed", []))
            }
            yield f"data: {json.dumps(final_payload)}\n\n"

        except asyncio.CancelledError:
            logger.info(f"Client disconnected or cancelled stream for session {payload.chat_id}")
            yield f"data: {json.dumps({'event': 'cancelled', 'status': 'cancelled'})}\n\n"
        except Exception as err:
            logger.error(f"Streaming error: {err}", exc_info=True)
            yield f"data: {json.dumps({'event': 'error', 'detail': str(err)})}\n\n"
        finally:
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

