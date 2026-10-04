"""
NARAD Phase 3 — Mobile Task Management API Router.
Provides complete lifecycle endpoints for autonomous tasks:
  - Create / Submit Task
  - List Tasks
  - Task Status
  - Task Progress (steps & completion percentage)
  - Task Events
  - Cancel Task
  - Retry Task
  - Detailed Task Result & Evidence
"""

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from app.services.agent_brain import agent_brain
from app.services.event_system import event_system
from app.api.v1.schemas import (
    CreateTaskRequest,
    TaskSummaryResponse,
    TaskProgressResponse,
    TaskResultResponse,
    CancelTaskRequest,
    RetryTaskResponse,
    NotificationItem,
    ErrorResponse,
)

router = APIRouter(prefix="/tasks", tags=["v1 - Tasks"])


def _to_summary_response(task: Dict[str, Any]) -> TaskSummaryResponse:
    return TaskSummaryResponse(
        task_id=task.get("task_id", ""),
        goal=task.get("goal", ""),
        status=task.get("status", "CREATED"),
        verification=task.get("verification") or task.get("verification_status") or "PENDING",
        duration_ms=task.get("duration_ms") or task.get("elapsed_ms") or 0,
        provider_used=task.get("provider_used"),
        created_at=task.get("created_at", ""),
        completed_at=task.get("completed_at"),
    )


# =============================================================================
# 1. CREATE TASK
# =============================================================================

@router.post(
    "",
    response_model=TaskSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Submit Goal for Autonomous Execution"
)
async def create_task(req: CreateTaskRequest, request: Request):
    """
    Submits a high-level goal to the Agent Brain.
    Plans, verifies permissions, orchestrates tools, and observes execution.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    clean_goal = req.goal.strip()
    if not clean_goal:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "EMPTY_GOAL",
                    "message": "Task goal cannot be empty.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    result = await agent_brain.execute_goal(
        goal=clean_goal,
        dry_run=req.dry_run,
        confirmation_id=req.confirmation_id,
        session_id=req.session_id,
    )

    return _to_summary_response(result)


# =============================================================================
# 2. LIST TASKS
# =============================================================================

@router.get(
    "",
    response_model=List[TaskSummaryResponse],
    summary="List Recent Tasks"
)
def list_tasks(limit: int = Query(50, ge=1, le=200, description="Max tasks to return")):
    """List recent tasks from the Agent Brain journal."""
    raw_tasks = agent_brain.list_tasks(limit=limit)
    return [_to_summary_response(t) for t in raw_tasks]


# =============================================================================
# 3. TASK STATUS
# =============================================================================

@router.get(
    "/{task_id}",
    response_model=TaskSummaryResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get Task Status"
)
def get_task_status(task_id: str, request: Request):
    """Retrieve high-level status for a specific task."""
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    task = agent_brain.get_task(task_id)
    if not task:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": f"Task '{task_id}' not found.",
                    "request_id": req_id,
                    "task_id": task_id,
                    "retryable": False,
                    "provider": None,
                }
            }
        )
    return _to_summary_response(task)


# =============================================================================
# 4. TASK PROGRESS
# =============================================================================

@router.get(
    "/{task_id}/progress",
    response_model=TaskProgressResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get Task Real-time Progress"
)
def get_task_progress(task_id: str, request: Request):
    """
    Returns step-level execution progress, current step, and completion percentage.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    active_state = agent_brain._active_tasks.get(task_id)

    if active_state:
        plan_steps = active_state.plan.steps if (active_state.plan and active_state.plan.steps) else []
        total_steps = len(plan_steps) if plan_steps else max(1, len(active_state.step_results))
        completed_steps = len(active_state.step_results)
        
        current_step_desc = None
        if active_state.current_step_index < len(plan_steps):
            current_step_desc = plan_steps[active_state.current_step_index].description

        is_active = active_state.status not in ("COMPLETED", "FAILED", "CANCELLED")
        progress_pct = 100 if active_state.status == "COMPLETED" else int((completed_steps / max(1, total_steps)) * 100)
        progress_pct = min(100, max(0, progress_pct))

        return TaskProgressResponse(
            task_id=task_id,
            status=active_state.status,
            total_steps=total_steps,
            completed_steps=completed_steps,
            current_step=current_step_desc,
            progress_pct=progress_pct,
            active=is_active,
        )

    # Check journal for completed/archived tasks
    task = agent_brain.get_task(task_id)
    if not task:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": f"Task '{task_id}' not found.",
                    "request_id": req_id,
                    "task_id": task_id,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    plan = task.get("plan") or []
    if isinstance(plan, dict):
        plan = plan.get("steps") or []
    actions = task.get("actions") or task.get("results") or []
    total_steps = len(plan) if plan else max(1, len(actions))
    completed_steps = len(actions)
    status_str = task.get("status", "COMPLETED")
    pct = 100 if status_str == "COMPLETED" else int((completed_steps / max(1, total_steps)) * 100)

    return TaskProgressResponse(
        task_id=task_id,
        status=status_str,
        total_steps=total_steps,
        completed_steps=completed_steps,
        current_step=None,
        progress_pct=min(100, max(0, pct)),
        active=False,
    )


# =============================================================================
# 5. TASK EVENTS
# =============================================================================

@router.get(
    "/{task_id}/events",
    response_model=List[NotificationItem],
    summary="Get Events for Task"
)
def get_task_events(task_id: str):
    """Retrieve structured lifecycle events recorded for a specific task."""
    raw_events = event_system.get_events(task_id=task_id, limit=100)
    items = []
    for e in raw_events:
        items.append(
            NotificationItem(
                event_id=e.get("event_id", ""),
                event_type=e.get("event_type") or e.get("type", "TASK_EVENT"),
                title=e.get("title", ""),
                body=e.get("body", ""),
                priority=e.get("priority", "normal"),
                task_id=task_id,
                timestamp=e.get("timestamp", ""),
            )
        )
    return items


# =============================================================================
# 6. TASK RESULT & EVIDENCE
# =============================================================================

@router.get(
    "/{task_id}/result",
    response_model=TaskResultResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get Complete Task Result & Verification Evidence"
)
def get_task_result(task_id: str, request: Request):
    """
    Retrieve full execution report including generated plan, step evidence,
    final outputs, and verification status.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    task = agent_brain.get_task(task_id)
    if not task:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": f"Task '{task_id}' not found.",
                    "request_id": req_id,
                    "task_id": task_id,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    plan = task.get("plan") or []
    if isinstance(plan, dict):
        plan = plan.get("steps") or []
    actions = task.get("actions") or task.get("results") or task.get("step_results") or []
    result = task.get("result") or {}
    if not result and "verified" in task:
        result = {"verified": task.get("verified", False)}

    errors = task.get("errors") or ([task["error"]] if task.get("error") else [])

    return TaskResultResponse(
        task_id=task_id,
        goal=task.get("goal", ""),
        status=task.get("status", "COMPLETED"),
        verification=task.get("verification") or task.get("verification_status") or "UNVERIFIED",
        plan=plan if isinstance(plan, list) else [],
        actions=actions if isinstance(actions, list) else [],
        result=result if isinstance(result, dict) else {"raw": result},
        errors=errors if isinstance(errors, list) else [str(errors)],
        duration_ms=task.get("duration_ms") or task.get("elapsed_ms") or 0,
        provider_used=task.get("provider_used"),
        created_at=task.get("created_at", ""),
        completed_at=task.get("completed_at"),
    )


# =============================================================================
# 7. CANCEL TASK
# =============================================================================

@router.post(
    "/{task_id}/cancel",
    responses={404: {"model": ErrorResponse}},
    summary="Cancel Task"
)
def cancel_task(
    task_id: str,
    request: Request,
    req: Optional[CancelTaskRequest] = None
):
    """
    Immediately cancels an active task.
    Human override takes unconditional priority over any autonomous loop.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    reason = req.reason if req and req.reason else "User cancellation via mobile app"
    cancel_res = agent_brain.cancel_task(task_id, reason=reason)
    if not cancel_res.get("success"):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": cancel_res.get("message", f"Task '{task_id}' not found."),
                    "request_id": req_id,
                    "task_id": task_id,
                    "retryable": False,
                    "provider": None,
                }
            }
        )
    return cancel_res


# =============================================================================
# 8. RETRY TASK
# =============================================================================

@router.post(
    "/{task_id}/retry",
    response_model=RetryTaskResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Retry Existing Task"
)
async def retry_task(task_id: str, request: Request):
    """
    Retries an existing task by re-submitting its original goal to the Agent Brain.
    Spawns a new task run with clear traceability to the original task ID.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    existing = agent_brain.get_task(task_id)
    if not existing:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": f"Cannot retry task: '{task_id}' does not exist.",
                    "request_id": req_id,
                    "task_id": task_id,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    goal = existing.get("goal", "")
    new_result = await agent_brain.execute_goal(goal=goal)

    return RetryTaskResponse(
        success=True,
        original_task_id=task_id,
        retry_task_id=new_result.get("task_id", ""),
        status=new_result.get("status", "COMPLETED"),
        goal=goal,
    )
