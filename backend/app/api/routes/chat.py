from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import json
from datetime import datetime

from app.db.database import get_db
from app.db.models import ChatSession, ChatMessage
from app.core.narad import narad_core

router = APIRouter(prefix="/chat", tags=["Chat"])

class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    provider: str
    model: str
    latency_ms: int
    status: str
    chat_id: str
    user_message: Optional[Dict[str, Any]] = None
    assistant_message: Optional[Dict[str, Any]] = None

@router.post("", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat_endpoint(payload: ChatRequest, db: Session = Depends(get_db)):
    """
    Primary NARAD chat endpoint.
    Processes user directive via Model Router and Gemini/active provider,
    measures latency, and persists both turns into the local SQLite database.
    """
    content = payload.message.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")

    # 1. Resolve or create ChatSession in local SQLite
    session = None
    if payload.chat_id:
        session = db.query(ChatSession).filter(ChatSession.id == payload.chat_id).first()

    if not session:
        # Create new session with auto-generated title
        clean_title = content.replace("\n", " ").strip()
        title = (clean_title[:35] + "...") if len(clean_title) > 35 else clean_title
        session = ChatSession(title=title or "New Briefing")
        db.add(session)
        db.commit()
        db.refresh(session)

    # 2. Persist User message
    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=content
    )
    db.add(user_msg)
    
    # Update title if it was default
    if session.title == "New Briefing":
        clean_title = content.replace("\n", " ").strip()
        session.title = (clean_title[:35] + "...") if len(clean_title) > 35 else clean_title

    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user_msg)

    # 3. Retrieve prior session history for context
    history_records = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    history_payload = [
        {"role": m.role, "content": m.content}
        for m in history_records
    ]

    # 4. Dispatch through NARAD Core & Model Router
    core_result = await narad_core.process_message(
        message=content,
        history=history_payload,
        requested_provider=payload.provider,
        requested_model=payload.model
    )

    # 5. Persist Assistant message to SQLite
    assistant_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=core_result["response"],
        metadata_json=json.dumps({
            "provider": core_result["provider"],
            "model": core_result["model"],
            "latency_ms": core_result["latency_ms"],
            "status": core_result["status"],
            "usage": core_result.get("usage", {})
        })
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    return {
        "response": core_result["response"],
        "provider": core_result["provider"],
        "model": core_result["model"],
        "latency_ms": core_result["latency_ms"],
        "status": core_result["status"],
        "chat_id": session.id,
        "user_message": user_msg.to_dict(),
        "assistant_message": assistant_msg.to_dict()
    }
