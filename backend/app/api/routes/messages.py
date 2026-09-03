from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import json
from datetime import datetime
from app.db.database import get_db
from app.db.models import ChatSession, ChatMessage
from app.providers.manager import provider_manager

router = APIRouter(prefix="/chats/{chat_id}/messages", tags=["Messages"])

class MessageSendRequest(BaseModel):
    content: str
    provider_id: Optional[str] = None
    model: Optional[str] = None

@router.get("")
def list_messages(chat_id: str, db: Session = Depends(get_db)):
    """Retrieve all messages for a given chat session."""
    session = db.query(ChatSession).filter(ChatSession.id == chat_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == chat_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return [m.to_dict() for m in messages]

@router.post("", status_code=status.HTTP_201_CREATED)
async def send_message(
    chat_id: str,
    payload: MessageSendRequest,
    db: Session = Depends(get_db)
):
    """
    Post a user message, dispatch to the active LLM provider,
    persist both messages to SQLite, and return the response pair.
    """
    session = db.query(ChatSession).filter(ChatSession.id == chat_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content cannot be empty")

    # 1. Save User Message
    user_msg = ChatMessage(
        session_id=chat_id,
        role="user",
        content=content
    )
    db.add(user_msg)
    
    # Auto-title session if it was default
    if session.title == "New Briefing":
        # First 35 chars
        clean_title = content.replace("\n", " ").strip()
        session.title = (clean_title[:35] + "...") if len(clean_title) > 35 else clean_title

    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user_msg)

    # 2. Query Active Model Provider
    provider = provider_manager.get_provider(payload.provider_id)
    
    # Compile history for provider context
    history_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == chat_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    
    formatted_history = [
        {"role": m.role, "content": m.content}
        for m in history_messages
    ]

    provider_result = await provider.generate_response(
        messages=formatted_history,
        model=payload.model
    )

    # 3. Save Assistant Message
    assistant_msg = ChatMessage(
        session_id=chat_id,
        role="assistant",
        content=provider_result.get("content", ""),
        metadata_json=json.dumps({
            "provider": provider_result.get("provider"),
            "model": provider_result.get("model"),
            "usage": provider_result.get("usage")
        })
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    return {
        "user_message": user_msg.to_dict(),
        "assistant_message": assistant_msg.to_dict()
    }
