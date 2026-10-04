"""NARAD V4 - Computer Agent State Machine & Task History.

Tracks live agent execution states:
IDLE -> UNDERSTANDING -> PLANNING -> WAITING_FOR_PERMISSION -> EXECUTING -> OBSERVING -> VERIFYING -> COMPLETED / FAILED / CANCELLED

Maintains a lightweight execution history ring buffer (distinct from Smṛti memory)
and manages global cancellation and emergency stop controls.
"""

from collections import deque
from datetime import datetime
from enum import Enum
import threading
import time
from typing import Any, Dict, List, Optional
import uuid
import logging

logger = logging.getLogger("narad.agent_state")


class AgentState(str, Enum):
    IDLE = "IDLE"
    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    WAITING_FOR_PERMISSION = "WAITING_FOR_PERMISSION"
    EXECUTING = "EXECUTING"
    OBSERVING = "OBSERVING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    VERIFY_FAILED = "VERIFY_FAILED"


class AgentStateManager:
    """Thread-safe manager for live agent state, task history, and emergency stop."""

    def __init__(self, max_history: int = 50):
        self._lock = threading.Lock()
        self.state: AgentState = AgentState.IDLE
        self.active_task_id: Optional[str] = None
        self.active_task_prompt: Optional[str] = None
        self.current_action: Optional[str] = None
        self.pending_confirmation: Optional[Dict[str, Any]] = None
        self.dry_run: bool = False
        self._cancel_requested: bool = False
        self._start_time: float = 0.0

        # Trinetra Vision Telemetry (V5)
        self.last_screenshot_ref: Optional[str] = None
        self.last_active_app: Optional[str] = None
        self.last_vision_result: Optional[Dict[str, Any]] = None
        self.last_verification_result: str = "PENDING"
        self.observation_count: int = 0

        # Ring buffer for lightweight task history
        self._history: deque = deque(maxlen=max_history)

    def transition_to(
        self,
        new_state: AgentState,
        action: Optional[str] = None,
        task_id: Optional[str] = None,
        pending_confirmation: Optional[Dict[str, Any]] = None,
    ):
        """Transition agent to a new state and notify telemetry."""
        with self._lock:
            self.state = new_state
            if action is not None:
                self.current_action = action
            if task_id is not None:
                self.active_task_id = task_id
            if pending_confirmation is not None:
                self.pending_confirmation = pending_confirmation
            elif new_state not in (AgentState.WAITING_FOR_PERMISSION,):
                self.pending_confirmation = None

            logger.info(f"[Agent State] -> {self.state.value} | Action: {self.current_action}")

    def start_task(self, prompt: str, dry_run: bool = False) -> str:
        """Initialize and mark start of an agent task."""
        with self._lock:
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            self.active_task_id = task_id
            self.active_task_prompt = prompt
            self.current_action = "Starting task"
            self.dry_run = dry_run
            self._start_time = time.time()
            self.observation_count = 0
            self.last_verification_result = "PENDING"
            if not self._cancel_requested:
                self.state = AgentState.UNDERSTANDING
            logger.info(f"[Agent Task] Started {task_id} (dry_run={dry_run}): '{prompt}'")
            return task_id

    def is_cancelled(self) -> bool:
        """Check if emergency stop / cancellation has been triggered."""
        with self._lock:
            return self._cancel_requested

    def request_stop(self) -> Dict[str, Any]:
        """Emergency Kill Switch / Stop Everything: immediately halts running and queued actions."""
        with self._lock:
            self._cancel_requested = True
            prev_state = self.state.value
            self.state = AgentState.CANCELLED
            self.current_action = "Emergency stop triggered by user"
            logger.warning(f"[Agent Emergency Kill] Global STOP triggered from state: {prev_state}")
            return {
                "success": True,
                "message": "Emergency stop signal sent. Agent execution cancelled.",
                "previous_state": prev_state,
                "current_state": AgentState.CANCELLED.value,
                "state": AgentState.CANCELLED.value,
            }

    def finish_task(
        self,
        status: str,
        actions_count: int = 0,
        plan: Optional[List[Dict[str, Any]]] = None,
        results: Optional[List[Dict[str, Any]]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record task outcome into history ring buffer and return to IDLE."""
        with self._lock:
            duration = round(time.time() - self._start_time, 2) if self._start_time else 0.0
            task_record = {
                "task_id": self.active_task_id or f"task_{uuid.uuid4().hex[:8]}",
                "prompt": self.active_task_prompt or "Unknown directive",
                "status": status,
                "actions_count": actions_count,
                "duration_seconds": duration,
                "dry_run": self.dry_run,
                "plan": plan or [],
                "results": results or [],
                "error": error,
                "timestamp": datetime.now().isoformat(),
            }
            self._history.appendleft(task_record)

            final_state = AgentState.COMPLETED if status == "COMPLETED" else (
                AgentState.CANCELLED if status == "CANCELLED" else AgentState.FAILED
            )
            self.state = final_state
            logger.info(f"[Agent Task] Finished with status '{status}' in {duration}s")
            return task_record

    def reset_to_idle(self):
        """Reset state safely to IDLE."""
        with self._lock:
            self.state = AgentState.IDLE
            self.active_task_id = None
            self.active_task_prompt = None
            self.current_action = None
            self.pending_confirmation = None
            self._cancel_requested = False
            self.observation_count = 0
            self.last_verification_result = "PENDING"

    def reset(self):
        """Alias for reset_to_idle."""
        self.reset_to_idle()

    def emergency_stop(self, reason: Optional[str] = None) -> Dict[str, Any]:
        """Alias for request_stop with optional reason logging."""
        if reason:
            logger.warning(f"[Agent Emergency Stop] Reason: {reason}")
        return self.request_stop()

    def update_vision_telemetry(
        self,
        screenshot_ref: Optional[str] = None,
        active_app: Optional[str] = None,
        vision_result: Optional[Dict[str, Any]] = None,
        verification_result: Optional[str] = None,
    ):
        """Update live Trinetra visual observation telemetry."""
        with self._lock:
            if screenshot_ref:
                self.last_screenshot_ref = screenshot_ref
            if active_app:
                self.last_active_app = active_app
            if vision_result is not None:
                self.last_vision_result = vision_result
            if verification_result:
                self.last_verification_result = verification_result

    def get_state_summary(self) -> Dict[str, Any]:
        """Get snapshot of current agent state for API and frontend HUD."""
        with self._lock:
            try:
                from app.services.trinetra import trinetra_service
                v_status = trinetra_service.get_status()
            except Exception:
                v_status = "READY [V5]"

            return {
                "state": self.state.value,
                "active_task_id": self.active_task_id,
                "active_task_prompt": self.active_task_prompt,
                "current_action": self.current_action,
                "pending_confirmation": self.pending_confirmation,
                "dry_run": self.dry_run,
                "is_cancelled": self._cancel_requested,
                "last_screenshot_ref": self.last_screenshot_ref,
                "last_active_app": self.last_active_app,
                "last_vision_result": self.last_vision_result,
                "last_verification_result": self.last_verification_result,
                "observation_count": self.observation_count,
                "vision_status": v_status,
            }

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve recent task history entries."""
        with self._lock:
            return list(self._history)[:limit]


# Global singleton agent state manager
agent_state = AgentStateManager()
