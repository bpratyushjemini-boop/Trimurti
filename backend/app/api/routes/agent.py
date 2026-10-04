"""NARAD V4 - Computer Agent API Routes.

Exposes endpoints for:
- Executing or dry-running computer agent tasks (Manthan Planner)
- Approving or denying Level 2 / Level 3 action confirmation requests
- Emergency Kill Switch / Global STOP
- Agent state & HUD telemetry
- Lightweight task history
"""

import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.manthan import manthan_planner
from app.services.agent_state import agent_state
from app.services.action_policy import action_policy

router = APIRouter(prefix="/agent", tags=["Computer Agent"])


class VisionQueryRequest(BaseModel):
    question: Optional[str] = Field("What is currently on my screen?", description="Question to ask about the visible screen state.")
    image_ref: Optional[str] = Field(None, description="Optional image reference to analyze. Defaults to latest screen capture.")


class AgentExecuteRequest(BaseModel):
    prompt: Optional[str] = Field(None, description="User prompt or directive for the computer agent.")
    instruction: Optional[str] = Field(None, description="Alternative field for user prompt or directive.")
    dry_run: bool = Field(False, description="If true, generates action plan and checks safety policies without executing system mutations.")
    confirmation_id: Optional[str] = Field(None, description="Optional approved confirmation ID for an action requiring user permission.")

    def get_prompt(self) -> str:
        return (self.prompt or self.instruction or "").strip()


class AgentConfirmRequest(BaseModel):
    confirmation_id: str = Field(..., description="The unique confirmation ID for the pending action.")
    decision: str = Field(..., description="User authorization decision: 'allow', 'allow_task', or 'deny'.")
    task_id: Optional[str] = Field(None, description="Optional associated task ID.")


class TaskCreateRequest(BaseModel):
    objective: str = Field(..., description="High-level objective or directive for autonomous multi-step execution.")
    dry_run: bool = Field(False, description="If true, simulates task without system mutations.")
    autonomy_mode: Optional[str] = Field(None, description="Optional override autonomy mode: CHAT_ONLY, SUGGEST, SUPERVISED, TASK_AUTONOMY.")


class TaskStepActionRequest(BaseModel):
    step_id: Optional[str] = Field(None, description="Optional step ID to target.")


class AutonomyModeRequest(BaseModel):
    mode: str = Field(..., description="Autonomy mode: CHAT_ONLY, SUGGEST, SUPERVISED, TASK_AUTONOMY.")


@router.post("/execute")
async def execute_agent_task(req: AgentExecuteRequest):
    """Execute a personal computer agent task through Manthan reasoning and Kriya execution."""
    task_prompt = req.get_prompt()
    if not task_prompt:
        raise HTTPException(status_code=400, detail="Task prompt cannot be empty.")

    result = await manthan_planner.execute_task(
        prompt=task_prompt,
        dry_run=req.dry_run,
        confirmation_id=req.confirmation_id,
    )
    return result


@router.post("/confirm")
async def confirm_action(req: AgentConfirmRequest):
    """Authorize or deny a pending Level 2 or Level 3 action (supporting 'allow', 'allow_task', 'deny')."""
    from app.services.task_engine import autonomous_task_engine
    decision_result = autonomous_task_engine.handle_confirmation_decision(
        confirmation_id=req.confirmation_id,
        decision=req.decision,
        task_id=req.task_id,
    )
    if not decision_result.get("success"):
        raise HTTPException(status_code=404, detail=decision_result.get("error", "Confirmation request not found."))
    return decision_result


# =========================================================================
# NARAD V6 — Autonomous Task Engine Endpoints
# =========================================================================

@router.post("/task/create")
async def create_autonomous_task(req: TaskCreateRequest):
    """Create and start a multi-step autonomous task under the V6 task engine."""
    from app.services.task_engine import autonomous_task_engine
    try:
        task = await autonomous_task_engine.create_and_start_task(
            objective=req.objective,
            dry_run=req.dry_run,
            autonomy_mode=req.autonomy_mode,
        )
        return task.to_dict()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/task/active")
async def get_active_task():
    """Retrieve the currently active autonomous task, if any."""
    from app.services.task_engine import autonomous_task_engine
    task = autonomous_task_engine.get_active_task()
    if not task:
        return {"active": False, "task": None}
    return {"active": True, "task": task.to_dict()}


@router.get("/task/list")
async def list_tasks(limit: int = 20):
    """List recent autonomous tasks."""
    from app.services.task_engine import autonomous_task_engine
    return autonomous_task_engine.list_tasks(limit=limit)


@router.get("/task/{task_id}")
async def get_task_details(task_id: str):
    """Get details, steps, and honest report for a specific task."""
    from app.services.task_engine import autonomous_task_engine
    task = autonomous_task_engine.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return task.to_dict()


@router.post("/task/{task_id}/pause")
async def pause_task(task_id: str):
    """Pause an active autonomous task."""
    from app.services.task_engine import autonomous_task_engine
    res = autonomous_task_engine.pause_task(task_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res


@router.post("/task/{task_id}/resume")
async def resume_task(task_id: str):
    """Resume a paused autonomous task."""
    from app.services.task_engine import autonomous_task_engine
    res = autonomous_task_engine.resume_task(task_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res


@router.post("/task/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel an autonomous task and restore safe system state."""
    from app.services.task_engine import autonomous_task_engine
    res = autonomous_task_engine.cancel_task(task_id, reason="Cancelled via API request")
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res


@router.post("/task/{task_id}/skip")
async def skip_task_step(task_id: str, req: TaskStepActionRequest = TaskStepActionRequest()):
    """Skip the current or specified step in a task."""
    from app.services.task_engine import autonomous_task_engine
    res = autonomous_task_engine.skip_step(task_id, step_id=req.step_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res


@router.post("/task/{task_id}/retry")
async def retry_task_step(task_id: str, req: TaskStepActionRequest = TaskStepActionRequest()):
    """Retry a failed step in a task."""
    from app.services.task_engine import autonomous_task_engine
    res = autonomous_task_engine.retry_step(task_id, step_id=req.step_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res


@router.get("/autonomy/mode")
async def get_autonomy_mode():
    """Get the current system autonomy mode."""
    from app.services.action_policy import action_policy, AutonomyMode
    return {
        "mode": action_policy.get_autonomy_mode(),
        "allowed_modes": [m.value for m in AutonomyMode],
    }


@router.post("/autonomy/mode")
async def set_autonomy_mode(req: AutonomyModeRequest):
    """Update the system autonomy mode (CHAT_ONLY, SUGGEST, SUPERVISED, TASK_AUTONOMY)."""
    from app.services.action_policy import action_policy
    res = action_policy.set_autonomy_mode(req.mode)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return {
        "success": True,
        "mode": res.get("autonomy_mode"),
        "message": f"Autonomy mode updated to {res.get('autonomy_mode')}.",
    }


@router.post("/stop")
async def emergency_stop():
    """Emergency Kill Switch: immediately halts all active and pending computer-agent actions."""
    stop_result = agent_state.request_stop()
    return stop_result


@router.post("/reset")
async def reset_agent():
    """Reset agent state to IDLE and clear cancellations."""
    agent_state.reset_to_idle()
    return {"success": True, "state": "IDLE"}


@router.get("/state")
async def get_agent_state():
    """Get live agent lifecycle state and active task telemetry for the NARAD HUD."""
    return agent_state.get_state_summary()


@router.get("/history")
async def get_agent_history(limit: int = 20):
    """Get recent lightweight task execution history (separate from Smṛti)."""
    return agent_state.get_history(limit=limit)


@router.get("/confirmations")
async def get_pending_confirmations():
    """List pending Level 2 / Level 3 actions awaiting user authorization."""
    return action_policy.list_pending_confirmations()


@router.get("/screenshot/latest")
async def get_latest_screenshot():
    """Retrieve the latest captured screenshot for the HUD visual debug panel."""
    from app.services.trinetra import trinetra_service
    path = trinetra_service.get_latest_screenshot_path()
    if not path or not os.path.exists(path):
        # Capture on demand if none exists
        obs = trinetra_service.observe_screen()
        path = trinetra_service.get_latest_screenshot_path()

    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No screenshot available.")
    return FileResponse(path, media_type="image/jpeg" if path.endswith(".jpg") else "image/png")


@router.post("/vision/query")
async def query_vision(req: VisionQueryRequest):
    """Direct Trinetra screen observation and multimodal visual query."""
    from app.services.trinetra import trinetra_service
    ref = req.image_ref or trinetra_service._latest_screenshot_ref
    if not ref:
        obs = trinetra_service.observe_screen()
        ref = obs.get("image_ref")

    analysis = await trinetra_service.understand_screen(image_ref=ref, question=req.question)
    if isinstance(analysis, dict):
        analysis["image_ref"] = ref
    return analysis


@router.get("/tools")
async def get_registered_tools():
    """List all registered Kriya and agent tools with descriptions, schemas, and policy levels."""
    from app.services.kriya import kriya_dispatcher
    from app.services.action_policy import action_policy
    tools_list = []
    for name, tool in kriya_dispatcher._tools.items():
        try:
            level, action_summary, reason = action_policy.classify_action(name, {})
        except Exception:
            level = 0
            action_summary = f"Execute {name}"
            reason = "Standard tool execution"
        tools_list.append({
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "permission_level": int(level),
            "summary": action_summary,
            "reason": reason,
        })
    return {"tools": tools_list, "total": len(tools_list)}
