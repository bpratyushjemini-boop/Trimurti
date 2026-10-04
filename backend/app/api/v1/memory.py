"""
NARAD Phase 3 — Mobile Smriti Memory API Router.
Safe, explicit memory endpoints respecting local/cloud privacy boundaries:
  - Memory Status & Metrics
  - Relevant Memory Retrieval (Recall)
  - Explicit Memory Write (defaults to scope="CLOUD")
  - Memory Deletion (by ID and by Key)
"""

import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.database import get_db, get_db_dialect
from app.services.smriti import smriti_service
from app.api.v1.schemas import (
    MemoryStatusResponse,
    RecallMemoryRequest,
    RecallMemoryResponse,
    WriteMemoryRequest,
    WriteMemoryResponse,
    ErrorResponse,
)

router = APIRouter(prefix="/memory", tags=["v1 - Memory"])


# =============================================================================
# 1. MEMORY STATUS
# =============================================================================

@router.get(
    "/status",
    response_model=MemoryStatusResponse,
    summary="Get Smriti Memory Status & Tier Separation"
)
def get_memory_status(db: Session = Depends(get_db)):
    """
    Returns memory health, total record counts, and counts by storage tier (LOCAL vs CLOUD).
    """
    raw_status = smriti_service.get_memory_status(db=db)
    return MemoryStatusResponse(
        enabled=True,
        backend=get_db_dialect(),
        total_memories=raw_status.get("total_memories", 0),
        active_memories=raw_status.get("active_memories", 0),
        local_count=raw_status.get("local_count", 0),
        cloud_count=raw_status.get("cloud_count", 0),
        categories=raw_status.get("categories", {}),
    )


# =============================================================================
# 2. RECALL RELEVANT MEMORY
# =============================================================================

@router.post(
    "/recall",
    response_model=RecallMemoryResponse,
    responses={400: {"model": ErrorResponse}},
    summary="Semantic Memory Recall"
)
def recall_memory(
    req: RecallMemoryRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Retrieves ranked memories relevant to a query using multi-factor scoring.
    Supports optional scope filter ('LOCAL', 'CLOUD', or None for all).
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    clean_query = req.query.strip()
    if not clean_query:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "EMPTY_QUERY",
                    "message": "Recall query cannot be empty.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    results = smriti_service.retrieve_relevant_memories(
        query=clean_query,
        max_memories=req.limit,
        db=db
    )

    # Apply scope filter if specified
    if req.scope:
        target_scope = req.scope.upper()
        results = [m for m in results if m.get("scope", "LOCAL").upper() == target_scope]

    return RecallMemoryResponse(
        query=clean_query,
        count=len(results),
        memories=results,
    )


# =============================================================================
# 3. WRITE MEMORY
# =============================================================================

@router.post(
    "",
    response_model=WriteMemoryResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}},
    summary="Explicit Memory Write"
)
def write_memory(
    payload: WriteMemoryRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Explicitly stores a user fact or preference.
    Defaults scope to 'CLOUD' for seamless mobile synchronization.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    clean_key = payload.key.strip()
    clean_val = payload.value.strip()

    if not clean_key or not clean_val:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "INVALID_MEMORY",
                    "message": "Memory key and value must be non-empty.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    scope_choice = payload.scope.upper() if payload.scope else "CLOUD"
    if scope_choice not in ("LOCAL", "CLOUD"):
        scope_choice = "CLOUD"

    res = smriti_service.save_memory(
        key=clean_key,
        value=clean_val,
        category=payload.category or "FACTS",
        confidence=payload.confidence,
        importance=payload.importance,
        source="mobile_v1",
        scope=scope_choice,
        db=db,
    )

    if not res.get("success"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "MEMORY_SAVE_FAILED",
                    "message": res.get("message", "Memory could not be saved."),
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    return WriteMemoryResponse(
        success=True,
        id=res.get("id", ""),
        key=clean_key,
        value=clean_val,
        category=payload.category or "FACTS",
        scope=scope_choice,
        status=res.get("status", "saved"),
    )


# =============================================================================
# 4. DELETE MEMORY
# =============================================================================

@router.delete(
    "/{memory_id}",
    responses={404: {"model": ErrorResponse}},
    summary="Delete Memory by UUID"
)
def delete_memory_by_id(memory_id: str, request: Request, db: Session = Depends(get_db)):
    """Deletes an explicit memory record by its primary key UUID."""
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    success = smriti_service.delete_memory_by_id(memory_id, db=db)
    if not success:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "MEMORY_NOT_FOUND",
                    "message": f"Memory record '{memory_id}' not found.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )
    return {"success": True, "id": memory_id, "status": "deleted"}


@router.delete(
    "/key/{key}",
    responses={404: {"model": ErrorResponse}},
    summary="Delete Memory by Key Name"
)
def delete_memory_by_key(key: str, request: Request, db: Session = Depends(get_db)):
    """Deletes an explicit memory record by entity key name."""
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    res = smriti_service.delete_memory(key, db=db)
    if res.get("status") == "not_found":
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "MEMORY_NOT_FOUND",
                    "message": f"No memory record found for key '{key}'.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )
    return {"success": True, "key": key, "status": "deleted"}
