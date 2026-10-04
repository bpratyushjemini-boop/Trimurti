"""
NARAD Phase 2 — Tasks API Routes (iOS Client Contract Ready).
Exposes stable, stateless endpoints for task lifecycle management:
- GET /api/tasks
- GET /api/tasks/{id}
- POST /api/tasks
- POST /api/tasks/{id}/cancel
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.agent_brain import agent_brain

router = APIRouter(prefix="/tasks", tags=["Tasks"])


class CreateTaskRequest(BaseModel):
    goal: str = Field(..., description="High-level objective or directive for the Agent Brain.")
    dry_run: bool = Field(False, description="Simulate without executing system mutations.")
    session_id: Optional[str] = Field(None, description="Optional associated session ID.")
    confirmation_id: Optional[str] = Field(None, description="Optional approved confirmation ID.")


class CancelTaskRequest(BaseModel):
    reason: Optional[str] = Field("User cancellation via API", description="Reason for cancelling the task.")


@router.get("", response_model=List[Dict[str, Any]])
def list_tasks(limit: int = Query(50, ge=1, le=200, description="Max tasks to return")):
    """List recent tasks from the Agent Brain journal."""
    return agent_brain.list_tasks(limit=limit)


@router.get("/{task_id}")
def get_task(task_id: str):
    """Retrieve details, status, and verification report for a specific task."""
    task = agent_brain.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return task


@router.post("")
async def create_task(req: CreateTaskRequest):
    """Submit a goal to the Agent Brain for planning, execution, and verification."""
    clean_goal = req.goal.strip()
    if not clean_goal:
        raise HTTPException(status_code=400, detail="Goal cannot be empty.")

    result = await agent_brain.execute_goal(
        goal=clean_goal,
        dry_run=req.dry_run,
        confirmation_id=req.confirmation_id,
        session_id=req.session_id,
    )
    return result


@router.post("/{task_id}/cancel")
def cancel_task(task_id: str, req: Optional[CancelTaskRequest] = None):
    """Cancel an active task. No autonomous loop can override human cancellation."""
    reason = req.reason if req else "User cancellation via API"
    cancel_res = agent_brain.cancel_task(task_id, reason=reason)
    if not cancel_res.get("success"):
        raise HTTPException(status_code=404, detail=cancel_res.get("message", f"Task '{task_id}' not found."))
    return cancel_res
