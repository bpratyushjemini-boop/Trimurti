from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.db.database import get_db
from app.db.models import ChatSession, ChatMessage

from app.services.smriti import smriti_service

router = APIRouter(prefix="/chats", tags=["Chats"])

class ChatCreateRequest(BaseModel):
    title: Optional[str] = "New Briefing"

class ChatUpdateRequest(BaseModel):
    title: str

@router.get("")
def list_chats(db: Session = Depends(get_db)):
    """List all chat sessions ordered by last update via Smriti."""
    sessions = smriti_service.list_sessions(db=db)
    return [s.to_dict() for s in sessions]

@router.post("", status_code=status.HTTP_201_CREATED)
def create_chat(payload: ChatCreateRequest, db: Session = Depends(get_db)):
    """Create a new chat session via Smriti."""
    session = smriti_service.create_session(title=payload.title, db=db)
    return session.to_dict()

@router.get("/{chat_id}")
def get_chat(chat_id: str, db: Session = Depends(get_db)):
    """Get chat session details and message history via Smriti."""
    session = smriti_service.get_session(session_id=chat_id, db=db)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    messages = smriti_service.get_session_messages(session_id=chat_id, db=db)
    return {
        **session.to_dict(),
        "messages": [m.to_dict() for m in messages]
    }

@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(chat_id: str, db: Session = Depends(get_db)):
    """Delete a chat session and all associated messages via Smriti."""
    deleted = smriti_service.delete_session(session_id=chat_id, db=db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return None
