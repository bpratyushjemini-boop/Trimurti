from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.db.database import get_db
from app.db.models import ChatSession, ChatMessage

router = APIRouter(prefix="/chats", tags=["Chats"])

class ChatCreateRequest(BaseModel):
    title: Optional[str] = "New Briefing"

class ChatUpdateRequest(BaseModel):
    title: str

@router.get("")
def list_chats(db: Session = Depends(get_db)):
    """List all chat sessions ordered by last update."""
    sessions = db.query(ChatSession).order_by(ChatSession.updated_at.desc()).all()
    return [s.to_dict() for s in sessions]

@router.post("", status_code=status.HTTP_201_CREATED)
def create_chat(payload: ChatCreateRequest, db: Session = Depends(get_db)):
    """Create a new chat session."""
    session = ChatSession(title=payload.title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session.to_dict()

@router.get("/{chat_id}")
def get_chat(chat_id: str, db: Session = Depends(get_db)):
    """Get chat session details and message history."""
    session = db.query(ChatSession).filter(ChatSession.id == chat_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    return {
        **session.to_dict(),
        "messages": [m.to_dict() for m in session.messages]
    }

@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(chat_id: str, db: Session = Depends(get_db)):
    """Delete a chat session and all associated messages."""
    session = db.query(ChatSession).filter(ChatSession.id == chat_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    db.delete(session)
    db.commit()
    return None
