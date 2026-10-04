from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging

from app.db.database import get_db
from app.services.smriti import smriti_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["Smriti Memory"])

class SaveMemoryRequest(BaseModel):
    key: str = Field(..., min_length=1, description="Memory key or entity name")
    value: str = Field(..., min_length=1, description="Memory factual value")
    category: Optional[str] = Field("FACTS", description="Memory category (IDENTITY, PREFERENCES, PROJECTS, etc.)")
    confidence: Optional[float] = Field(1.0, ge=0.0, le=1.0, description="Confidence score")
    importance: Optional[float] = Field(0.5, ge=0.0, le=1.0, description="Importance score")
    source: Optional[str] = Field("api", description="Source of memory")
    scope: Optional[str] = Field("LOCAL", description="Memory scope: LOCAL vs CLOUD (explicit privacy boundary)")

class UpdateMemoryRequest(BaseModel):
    value: Optional[str] = None
    category: Optional[str] = None
    importance: Optional[float] = Field(None, ge=0.0, le=1.0)
    status: Optional[str] = None

class ForgetRequest(BaseModel):
    key: str = Field(..., min_length=1, description="Key or entity to forget from Smṛti")

class ExplainRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Query to explain memory retrieval for")

@router.get("", status_code=status.HTTP_200_OK)
def list_memories(
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search term for key or value"),
    status: Optional[str] = Query("ACTIVE", description="Filter by status (ACTIVE, ALL)"),
    scope: Optional[str] = Query(None, description="Filter by storage tier (LOCAL, CLOUD, ALL)"),
    limit: int = Query(50, ge=1, le=200, description="Max memories to return"),
    db: Session = Depends(get_db)
):
    """List persistent memories from Smṛti vault."""
    return smriti_service.list_memories(
        category=category,
        status=status,
        search=search,
        scope=scope,
        limit=limit,
        db=db
    )

@router.get("/status", status_code=status.HTTP_200_OK)
def get_memory_status(db: Session = Depends(get_db)):
    """Retrieve Smṛti 3.0 memory status, metrics, and category distributions."""
    return smriti_service.get_memory_status(db=db)

@router.get("/search", status_code=status.HTTP_200_OK)
def search_memories(
    query: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(5, ge=1, le=20, description="Max memories to retrieve"),
    db: Session = Depends(get_db)
):
    """Retrieve ranked memories relevant to a query using multi-factor scoring."""
    return smriti_service.retrieve_relevant_memories(
        query=query,
        max_memories=limit,
        min_score=5.0,
        db=db
    )

@router.get("/{memory_id}", status_code=status.HTTP_200_OK)
def get_memory(memory_id: str, db: Session = Depends(get_db)):
    """Retrieve a single memory record by its UUID."""
    mem = smriti_service.get_memory_by_id(memory_id, db=db)
    if not mem:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found.")
    return mem

@router.post("", status_code=status.HTTP_201_CREATED)
def create_memory(payload: SaveMemoryRequest, db: Session = Depends(get_db)):
    """Create or update a persistent memory record in Smṛti."""
    res = smriti_service.save_memory(
        key=payload.key,
        value=payload.value,
        category=payload.category,
        confidence=payload.confidence or 1.0,
        importance=payload.importance or 0.5,
        source=payload.source or "api",
        scope=payload.scope or "LOCAL",
        db=db
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Memory could not be saved."))
    return res

@router.patch("/{memory_id}", status_code=status.HTTP_200_OK)
def update_memory(memory_id: str, payload: UpdateMemoryRequest, db: Session = Depends(get_db)):
    """Update fields on an existing memory record."""
    res = smriti_service.update_memory_by_id(
        memory_id=memory_id,
        value=payload.value,
        category=payload.category,
        importance=payload.importance,
        status=payload.status,
        db=db
    )
    if not res:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found.")
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@router.delete("/{memory_id}", status_code=status.HTTP_200_OK)
def delete_memory(memory_id: str, db: Session = Depends(get_db)):
    """Delete a memory record by ID."""
    success = smriti_service.delete_memory_by_id(memory_id, db=db)
    if not success:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found.")
    return {"status": "deleted", "id": memory_id, "message": "Deleted from Smṛti."}

@router.post("/forget", status_code=status.HTTP_200_OK)
def forget_memory(payload: ForgetRequest, db: Session = Depends(get_db)):
    """Forget/delete a memory by key or entity name."""
    res = smriti_service.delete_memory(payload.key, db=db)
    if res.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"No memory found matching '{payload.key}'.")
    return res

@router.post("/explain", status_code=status.HTTP_200_OK)
def explain_memory(payload: ExplainRequest, db: Session = Depends(get_db)):
    """Explain which memories are retrieved for a query and why."""
    return smriti_service.explain_memory_retrieval(payload.query, db=db)
