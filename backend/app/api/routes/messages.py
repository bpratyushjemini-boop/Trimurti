from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import json
from datetime import datetime
from app.db.database import get_db
from app.db.models import ChatSession, ChatMessage
from app.core.narad import narad_core

from app.services.smriti import smriti_service

router = APIRouter(prefix="/chats/{chat_id}/messages", tags=["Messages"])

class MessageSendRequest(BaseModel):
    content: str
    provider_id: Optional[str] = None
    model: Optional[str] = None

@router.get("")
def list_messages(chat_id: str, db: Session = Depends(get_db)):
    """Retrieve all messages for a given chat session via Smriti."""
    session = smriti_service.get_session(session_id=chat_id, db=db)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    messages = smriti_service.get_session_messages(session_id=chat_id, db=db)
    return [m.to_dict() for m in messages]

@router.post("", status_code=status.HTTP_201_CREATED)
async def send_message(
    chat_id: str,
    payload: MessageSendRequest,
    db: Session = Depends(get_db)
):
    """
    Post a user message via Smriti, dispatch to NARAD Core & active LLM provider,
    persist both messages to SQLite via Smriti, and return the response pair.
    """
    session = smriti_service.get_session(session_id=chat_id, db=db)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content cannot be empty")

    # 1. Save User Message via Smriti
    user_msg = smriti_service.add_user_message(
        session_id=chat_id,
        content=content,
        db=db
    )

    # 2. Query ordered context history from Smriti
    formatted_history = smriti_service.get_conversation_history(
        session_id=chat_id,
        db=db
    )

    core_result = await narad_core.process_message(
        message=content,
        history=formatted_history,
        requested_provider=payload.provider_id,
        requested_model=payload.model
    )

    # 3. Save Assistant Message via Smriti
    assistant_msg = smriti_service.add_assistant_message(
        session_id=chat_id,
        content=core_result.get("response", ""),
        provider=core_result.get("provider"),
        model=core_result.get("model"),
        metadata=core_result,
        db=db
    )

    return {
        "user_message": user_msg.to_dict(),
        "assistant_message": assistant_msg.to_dict(),
        "provider": core_result.get("provider"),
        "model": core_result.get("model"),
        "latency_ms": core_result.get("latency_ms"),
        "status": core_result.get("status")
    }
