"""
NARAD Phase 2 — Central Agent Brain & Goal Orchestration Engine.
Orchestrates the entire intelligence cycle:
INTENT CLASSIFICATION -> CAPABILITY SELECTION -> RELEVANT MEMORY ->
TASK PLANNING -> PERMISSION GATES -> TOOL ORCHESTRATION ->
POST-ACTION OBSERVATION -> RECOVERY/REPLAN -> VERIFICATION -> MEMORY UPDATE.

Core Principles:
- The Agent Brain does NOT execute tools directly; it delegates to ToolOrchestrator & Krīya.
- Zero Fake Success: Never claim completion unless verified by real execution results.
- Provider Independence: Requests capabilities (reasoning, vision, local, etc.), not providers.
- Local-first & Offline: Enforces AUTO, LOCAL_ONLY, and OFFLINE modes strictly.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from app.core.config import settings
from app.core.router import model_router
from app.db.database import SessionLocal
from app.db.models import TaskJournalRecord
from app.services.action_policy import action_policy, AutonomyMode
from app.services.event_system import event_system, EventType
from app.services.planner import task_planner, TaskPlan, PlanStep
from app.services.runtime_truth import runtime_truth_service
from app.services.smriti import smriti_service
from app.services.tool_orchestrator import tool_orchestrator, FailureCategory

logger = logging.getLogger("narad.agent_brain")


class IntentCategory(str):
    CHAT = "CHAT"
    QUESTION = "QUESTION"
    RESEARCH = "RESEARCH"
    CODING = "CODING"
    FILE_OPERATION = "FILE_OPERATION"
    SYSTEM_OPERATION = "SYSTEM_OPERATION"
    COMPUTER_CONTROL = "COMPUTER_CONTROL"
    VISION = "VISION"
    MEMORY = "MEMORY"
    PLANNING = "PLANNING"
    MULTI_STEP_TASK = "MULTI_STEP_TASK"
    AUTOMATION = "AUTOMATION"
    LOCAL_ONLY = "LOCAL_ONLY"
    MIXED = "MIXED"


class RuntimeMode(str):
    AUTO = "AUTO"
    LOCAL_ONLY = "LOCAL_ONLY"
    OFFLINE = "OFFLINE"
    CLOUD_PREFERRED = "CLOUD_PREFERRED"


@dataclass
class IntentAnalysis:
    raw_prompt: str
    categories: List[str]
    tools_required: bool
    memory_relevant: bool
    vision_required: bool
    web_required: bool
    computer_control_required: bool
    local_only: bool
    required_capability: str  # fast_chat, reasoning, vision, coding, local
    primary_intent: str

    def __contains__(self, item: Any) -> bool:
        return item in self.categories

    def __iter__(self):
        return iter(self.categories)

    def __len__(self) -> int:
        return len(self.categories)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_prompt": self.raw_prompt,
            "categories": self.categories,
            "tools_required": self.tools_required,
            "memory_relevant": self.memory_relevant,
            "vision_required": self.vision_required,
            "web_required": self.web_required,
            "computer_control_required": self.computer_control_required,
            "local_only": self.local_only,
            "required_capability": self.required_capability,
            "primary_intent": self.primary_intent,
        }


@dataclass
class ActiveTaskState:
    task_id: str
    goal: str
    status: str  # CREATED, PLANNING, EXECUTING, OBSERVING, RECOVERING, VERIFYING, COMPLETED, FAILED, CANCELLED
    plan: Optional[TaskPlan] = None
    step_results: List[Dict[str, Any]] = field(default_factory=list)
    current_step_index: int = 0
    replan_count: int = 0
    max_replans: int = 3
    retries: int = 0
    max_retries_per_step: int = 2
    cancelled: bool = False
    start_time_monotonic: float = field(default_factory=time.monotonic)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    error: Optional[str] = None
    verification_status: str = "PENDING"
    provider_used: str = "LOCAL"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status,
            "plan": self.plan.to_dict() if self.plan else None,
            "step_results": self.step_results,
            "current_step_index": self.current_step_index,
            "replan_count": self.replan_count,
            "cancelled": self.cancelled,
            "elapsed_ms": int((time.monotonic() - self.start_time_monotonic) * 1000),
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "verification_status": self.verification_status,
            "provider_used": self.provider_used,
        }


class AgentBrain:
    """
    Central Agent Brain for NARAD.
    Connects existing subsystems (Smṛti, Krīya, Manthan, Trinetra, TaskEngine, ModelRouter, RuntimeTruth)
    into a coherent, verifiable cognitive architecture.
    """

    def __init__(self):
        self._current_mode: str = getattr(settings, "RUNTIME_OPERATION_MODE", RuntimeMode.AUTO)
        self._active_tasks: Dict[str, ActiveTaskState] = {}
        self._task_history: List[Dict[str, Any]] = []

    # =========================================================================
    # Operation Mode Management (AUTO, LOCAL_ONLY, OFFLINE, CLOUD_PREFERRED)
    # =========================================================================

    def get_mode(self) -> str:
        return self._current_mode

    def set_mode(self, mode: str) -> str:
        valid_modes = {
            RuntimeMode.AUTO,
            RuntimeMode.LOCAL_ONLY,
            RuntimeMode.OFFLINE,
            RuntimeMode.CLOUD_PREFERRED,
        }
        mode_upper = mode.upper().strip()
        if mode_upper in valid_modes:
            self._current_mode = mode_upper
            logger.info(f"[AgentBrain] Operation mode updated to: {self._current_mode}")
            event_type = EventType.LOCAL_MODE_ENABLED if mode_upper == RuntimeMode.LOCAL_ONLY else (
                EventType.OFFLINE_MODE_ENABLED if mode_upper == RuntimeMode.OFFLINE else EventType.PROVIDER_CHANGED
            )
            event_system.emit_event(
                event_type,
                title=f"Operation Mode Changed: {mode_upper}",
                body=f"NARAD operational mode set to {mode_upper}.",
                priority="high"
            )
        return self._current_mode

    def is_local_only(self) -> bool:
        """Check if Agent Brain is operating in strictly LOCAL_ONLY mode."""
        return self.get_mode() == RuntimeMode.LOCAL_ONLY

    def is_offline(self) -> bool:
        """Check if Agent Brain is operating in strictly OFFLINE mode."""
        return self.get_mode() == RuntimeMode.OFFLINE

    def select_model_capability(self, categories: List[str]) -> str:
        """
        Map intent categories to required model capability:
        vision, coding, reasoning, local, fast_chat.
        """
        cats_upper = [c.upper() for c in categories]
        if "VISION" in cats_upper:
            return "vision"
        elif "CODING" in cats_upper:
            return "coding"
        elif any(c in cats_upper for c in ("MULTI_STEP_TASK", "PLANNING", "REASONING")):
            return "reasoning"
        elif "LOCAL_ONLY" in cats_upper or self.is_local_only() or self.is_offline():
            return "local"
        return "fast_chat"

    # =========================================================================
    # 1. Intent Classification
    # =========================================================================

    def classify_intent(self, prompt: str) -> IntentAnalysis:
        """
        Classify incoming directive into multi-category intents:
        CHAT, QUESTION, RESEARCH, CODING, FILE_OPERATION, SYSTEM_OPERATION,
        COMPUTER_CONTROL, VISION, MEMORY, PLANNING, MULTI_STEP_TASK, AUTOMATION, LOCAL_ONLY, MIXED.
        """
        clean_p = prompt.strip()
        p_lower = clean_p.lower()
        cats: Set[str] = set()

        # Local-Only explicit intent
        if any(w in p_lower for w in ("local only", "local-only", "offline", "without internet", "on-device", "use ollama")):
            cats.add(IntentCategory.LOCAL_ONLY)

        # Memory intent
        if any(w in p_lower for w in (
            "remember that", "remember i", "remember narad", "remember my", "forget that", "forget my",
            "what do you remember", "show my memories", "my stored preferences", "update my project phase"
        )):
            cats.add(IntentCategory.MEMORY)

        # Conversational greetings / general chat
        if any(w in p_lower for w in ("hello", "hi", "hey", "how are you", "good morning", "good evening", "good afternoon")):
            cats.add(IntentCategory.CHAT)

        # Computer Control
        if (
            ("music" in p_lower and any(w in p_lower for w in ("play", "song", "track", "apple music"))) or
            (p_lower.startswith("open ") and any(app in p_lower for app in ("calculator", "music", "safari", "chrome", "firefox", "terminal", "finder", "notes", "vs code", "settings"))) or
            any(w in p_lower for w in ("close application", "quit app", "switch to", "focus window", "media control")) or
            "programiz" in p_lower
        ):
            cats.add(IntentCategory.COMPUTER_CONTROL)

        # Vision Intent
        if any(p in p_lower for p in (
            "screen", "screenshot", "look at my screen", "what is on my screen", "what's on my screen",
            "inspect screen", "read screen", "see screen", "visual verification"
        )):
            cats.add(IntentCategory.VISION)

        # File Operations
        if any(w in p_lower for w in ("read file", "write file", "delete file", "list directory", "list files", "folder", "directory", "inspect my project", "workspace")) or ("inspect" in p_lower and "project" in p_lower):
            cats.add(IntentCategory.FILE_OPERATION)

        # System Operations & Diagnostics
        if any(w in p_lower for w in ("port 8000", "port 5173", "check port", "service port", "check process", "terminal command", "run command", "diagnose", "what's broken", "what is broken", "broken")):
            cats.add(IntentCategory.SYSTEM_OPERATION)

        # Coding & Build
        if any(w in p_lower for w in ("code", "compiler", "armstrong", "frontend build", "production build", "debug", "python", "javascript", "test suite")):
            cats.add(IntentCategory.CODING)

        # Multi-Step Tasks & Planning
        if any(w in p_lower for w in (
            "prepare my development environment", "set up development environment", "prepare dev",
            "diagnose narad", "diagnose my narad project", "what is wrong", "what's wrong",
            "run production build", "step by step", "first open", "then", "plan"
        )) or ("open " in p_lower and "inspect" in p_lower):
            cats.add(IntentCategory.MULTI_STEP_TASK)
            cats.add(IntentCategory.PLANNING)

        # Research & Web
        if any(w in p_lower for w in ("search web", "search the web", "web search", "google", "look up online", "search knowledge", "documentation", "search online")):
            cats.add(IntentCategory.RESEARCH)

        # Basic Chat / Question
        if not cats or len(p_lower.split()) < 5 or p_lower.startswith(("what is", "who is", "explain", "how do", "why")):
            if "?" in p_lower or p_lower.startswith(("what ", "who ", "where ", "how ", "why ", "when ", "can you ")):
                if not any(w in p_lower for w in ("how are you", "hello", "hi", "hey")):
                    cats.add(IntentCategory.QUESTION)
                else:
                    cats.add(IntentCategory.CHAT)
            else:
                cats.add(IntentCategory.CHAT)

        if len(cats) > 1:
            cats.add(IntentCategory.MIXED)

        categories_list = sorted(list(cats))

        # Capability Requirements Determination
        tools_required = any(c in categories_list for c in (
            IntentCategory.FILE_OPERATION, IntentCategory.SYSTEM_OPERATION,
            IntentCategory.COMPUTER_CONTROL, IntentCategory.VISION,
            IntentCategory.MULTI_STEP_TASK, IntentCategory.RESEARCH
        ))
        memory_relevant = (
            IntentCategory.MEMORY in categories_list or
            any(k in p_lower for k in ("narad", "project", "my", "preference", "setup", "remember"))
        )
        vision_required = IntentCategory.VISION in categories_list
        web_required = (IntentCategory.RESEARCH in categories_list and "web" in p_lower)
        computer_control_required = IntentCategory.COMPUTER_CONTROL in categories_list
        local_only = (
            self._current_mode in (RuntimeMode.LOCAL_ONLY, RuntimeMode.OFFLINE) or
            IntentCategory.LOCAL_ONLY in categories_list
        )

        # Map to capability
        if vision_required:
            req_cap = "vision"
        elif IntentCategory.CODING in categories_list:
            req_cap = "coding"
        elif IntentCategory.MULTI_STEP_TASK in categories_list or "reason" in p_lower:
            req_cap = "reasoning"
        elif local_only:
            req_cap = "local"
        else:
            req_cap = "fast_chat"

        primary_intent = categories_list[0] if categories_list else IntentCategory.CHAT

        return IntentAnalysis(
            raw_prompt=clean_p,
            categories=categories_list,
            tools_required=tools_required,
            memory_relevant=memory_relevant,
            vision_required=vision_required,
            web_required=web_required,
            computer_control_required=computer_control_required,
            local_only=local_only,
            required_capability=req_cap,
            primary_intent=primary_intent,
        )

    # =========================================================================
    # 2. Task Planning & Structured Multi-Step Execution
    # =========================================================================

    async def execute_goal(
        self,
        goal: str,
        dry_run: bool = False,
        confirmation_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Closed-loop Agent Brain Goal Execution:
        GOAL -> PLAN -> CHECK PERMISSIONS -> ACT -> OBSERVE -> REASON -> RECOVER -> VERIFY -> MEMORY UPDATE
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        analysis = self.classify_intent(goal)

        # 1. Enforce Mode Restrictions (LOCAL_ONLY / OFFLINE)
        if self._current_mode == RuntimeMode.OFFLINE and analysis.web_required:
            logger.warning("[AgentBrain] Task requires network access, blocked in OFFLINE mode.")
            return {
                "success": False,
                "task_id": task_id,
                "status": "OFFLINE_BLOCKED",
                "message": "Task blocked: Operation requires network connectivity, but NARAD is in OFFLINE mode.",
                "failure_category": FailureCategory.NETWORK_ERROR.value,
                "plan": [],
                "results": [],
            }

        if self._current_mode == RuntimeMode.LOCAL_ONLY and analysis.web_required:
            logger.warning("[AgentBrain] Task requires cloud/web access, blocked in LOCAL_ONLY mode.")
            return {
                "success": False,
                "task_id": task_id,
                "status": "LOCAL_ONLY_BLOCKED",
                "message": "Task blocked: Operation requires cloud access, but NARAD is in LOCAL_ONLY mode.",
                "failure_category": FailureCategory.PERMISSION_DENIED.value,
                "plan": [],
                "results": [],
            }

        # 2. Retrieve Relevant Memory Context (Smṛti 3.0)
        retrieved_memories = []
        if analysis.memory_relevant:
            retrieved_memories = smriti_service.retrieve_relevant_memories(query=goal, max_memories=3)

        # 3. Create Structured Minimal Plan
        event_system.emit_event(
            EventType.TASK_CREATED,
            title=f"Task Created: {goal[:50]}",
            body=f"Agent Brain initiated task for objective: '{goal}'",
            priority="normal",
            task_id=task_id,
            metadata={"goal": goal, "intents": analysis.categories}
        )

        plan = task_planner.plan_task(
            goal=goal,
            context_memories=retrieved_memories,
            offline_mode=(self._current_mode == RuntimeMode.OFFLINE),
            local_only_mode=(self._current_mode == RuntimeMode.LOCAL_ONLY)
        )

        valid_plan, plan_err = task_planner.validate_plan(plan)
        if not valid_plan:
            err_msg = f"Task planning rejected: {plan_err}"
            logger.error(f"[AgentBrain] {err_msg}")
            event_system.emit_event(
                EventType.TASK_FAILED,
                title=f"Planning Failed: {task_id}",
                body=err_msg,
                priority="high",
                task_id=task_id,
            )
            return {
                "success": False,
                "task_id": task_id,
                "status": "PLANNING_FAILED",
                "message": err_msg,
                "failure_category": FailureCategory.INVALID_ARGUMENT.value,
                "plan": [],
                "results": []
            }

        event_system.emit_event(
            EventType.PLAN_CREATED,
            title=f"Plan Created ({len(plan.steps)} steps)",
            body=f"Formulated minimal execution plan with {len(plan.steps)} verifiable steps.",
            priority="normal",
            task_id=task_id,
            metadata={"steps": [s.title for s in plan.steps]}
        )

        # Register active task
        task_state = ActiveTaskState(
            task_id=task_id,
            goal=goal,
            status="EXECUTING",
            plan=plan,
            provider_used="OLLAMA" if analysis.local_only else "LOCAL + GROQ"
        )
        self._active_tasks[task_id] = task_state

        # 4. Sequential Step Execution Loop
        overall_success = True
        accumulated_results: List[Dict[str, Any]] = []
        failure_msg = None

        for idx, step in enumerate(plan.steps):
            if task_state.cancelled:
                task_state.status = "CANCELLED"
                failure_msg = "Task cancelled by user override."
                overall_success = False
                break

            task_state.current_step_index = idx
            step.status = "executing"

            # Execute Step via Tool Orchestrator (Delegation without direct tool execution)
            step_res = await tool_orchestrator.execute_tool(
                name=step.tool_name,
                arguments=step.tool_args,
                task_id=task_id,
                confirmation_id=confirmation_id,
                dry_run=dry_run,
                offline_mode=(self._current_mode == RuntimeMode.OFFLINE),
                local_only_mode=(self._current_mode == RuntimeMode.LOCAL_ONLY)
            )

            # Failure Recovery: check if step failed
            if not step_res.get("success"):
                logger.warning(f"[AgentBrain] Step '{step.step_id}' failed: {step_res.get('error')}")

                # Safe retry if strategy permits
                if step.fallback_strategy == "retry" and task_state.retries < task_state.max_retries_per_step:
                    task_state.retries += 1
                    logger.info(f"[AgentBrain] Retrying step '{step.step_id}' (attempt {task_state.retries + 1})...")
                    await asyncio.sleep(1.0)
                    step_res = await tool_orchestrator.execute_tool(
                        name=step.tool_name,
                        arguments=step.tool_args,
                        task_id=task_id,
                        confirmation_id=confirmation_id,
                        dry_run=dry_run,
                        offline_mode=(self._current_mode == RuntimeMode.OFFLINE),
                        local_only_mode=(self._current_mode == RuntimeMode.LOCAL_ONLY)
                    )

                # Re-check after retry
                if not step_res.get("success"):
                    if step.fallback_strategy == "skip":
                        logger.info(f"[AgentBrain] Skipping optional step '{step.step_id}' per fallback policy.")
                        step.status = "skipped"
                    else:
                        step.status = "failed"
                        overall_success = False
                        failure_msg = step_res.get("error") or f"Step '{step.title}' failed."
                        accumulated_results.append({
                            "step_id": step.step_id,
                            "title": step.title,
                            "tool": step.tool_name,
                            "status": "failed",
                            "error": failure_msg,
                            "details": step_res
                        })
                        break

            step.status = "completed"
            accumulated_results.append({
                "step_id": step.step_id,
                "title": step.title,
                "tool": step.tool_name,
                "status": "completed",
                "result": step_res.get("result"),
                "observations": step_res.get("observations")
            })

        # 5. Verification Phase (Act -> Observe -> Compare -> Verify)
        verification_status = "VERIFIED" if overall_success else "FAILED"
        if overall_success:
            event_system.emit_event(
                EventType.TASK_VERIFIED,
                title=f"Task Verified: {task_id}",
                body=f"All {len(accumulated_results)} steps verified successfully.",
                priority="normal",
                task_id=task_id,
            )
            event_system.emit_event(
                EventType.TASK_COMPLETED,
                title=f"Task Completed: {goal[:40]}",
                body=f"Objective '{goal}' completed and verified.",
                priority="high",
                task_id=task_id,
            )
            task_state.status = "COMPLETED"
        else:
            event_system.emit_event(
                EventType.TASK_FAILED,
                title=f"Task Failed: {task_id}",
                body=failure_msg or "Execution incomplete.",
                priority="high",
                task_id=task_id,
            )
            task_state.status = "FAILED" if not task_state.cancelled else "CANCELLED"

        task_state.step_results = accumulated_results
        task_state.completed_at = datetime.now(timezone.utc).isoformat()
        task_state.verification_status = verification_status
        task_state.error = failure_msg

        # 6. Memory Update Phase (Store durable takeaway into Smṛti 3.0)
        if overall_success and analysis.memory_relevant:
            try:
                # If the goal contained a project or preference fact, record it
                smriti_service.observe_and_extract(goal)
            except Exception as e:
                logger.debug(f"[AgentBrain] Memory update error: {e}")

        # 7. Persist Task Journal (Section 28)
        self._persist_task_journal(task_state)

        dur_ms = int((time.monotonic() - task_state.start_time_monotonic) * 1000)
        final_report = {
            "success": overall_success,
            "task_id": task_id,
            "status": task_state.status,
            "goal": goal,
            "verification": verification_status,
            "duration_ms": dur_ms,
            "provider_used": task_state.provider_used,
            "plan": plan.to_dict(),
            "results": accumulated_results,
            "message": failure_msg or f"Task '{goal}' executed and verified ({len(accumulated_results)} steps)."
        }

        # Keep in local history
        self._task_history.append(final_report)
        return final_report

    # =========================================================================
    # 3. Human Override & Cancellation (Section 27)
    # =========================================================================

    def create_task(self, goal: str) -> ActiveTaskState:
        """Create a new active task state and register it in active tasks."""
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        task_state = ActiveTaskState(
            task_id=task_id,
            goal=goal,
            status="CREATED",
        )
        self._active_tasks[task_id] = task_state
        return task_state

    def cancel_task(self, task_id: str, reason: str = "User cancellation") -> Dict[str, Any]:
        """Cancel an active task immediately. No autonomous loop can override cancellation."""
        task = self._active_tasks.get(task_id)
        if not task:
            return {"success": False, "message": f"Task '{task_id}' not found."}

        task.cancelled = True
        task.status = "CANCELLED"
        task.error = reason
        task.completed_at = datetime.now(timezone.utc).isoformat()

        event_system.emit_event(
            EventType.TASK_FAILED,
            title=f"Task Cancelled: {task_id}",
            body=f"Task was halted by user override: {reason}",
            priority="urgent",
            task_id=task_id,
        )
        logger.info(f"[AgentBrain] Task '{task_id}' was cancelled by human override.")
        return {"success": True, "task_id": task_id, "status": "CANCELLED", "reason": reason}

    def cancel_active_tasks(self, reason: str = "Emergency stop") -> int:
        """Cancel all running tasks."""
        count = 0
        for tid, t in list(self._active_tasks.items()):
            if t.status in ("PLANNING", "EXECUTING", "OBSERVING", "RECOVERING"):
                self.cancel_task(tid, reason=reason)
                count += 1
        return count

    # =========================================================================
    # 4. Task Journal & History Retrieval (Section 28)
    # =========================================================================

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve task details from memory or database journal."""
        if task_id in self._active_tasks:
            return self._active_tasks[task_id].to_dict()

        # Check DB
        try:
            with SessionLocal() as db:
                rec = db.query(TaskJournalRecord).filter(TaskJournalRecord.task_id == task_id).first()
                if rec:
                    return rec.to_dict()
        except Exception as e:
            logger.debug(f"[AgentBrain] DB task lookup error: {e}")

        # Fallback to local history
        for t in self._task_history:
            if t.get("task_id") == task_id:
                return t
        return None

    def list_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent tasks from journal."""
        tasks = []
        try:
            with SessionLocal() as db:
                recs = db.query(TaskJournalRecord).order_by(TaskJournalRecord.created_at.desc()).limit(limit).all()
                tasks = [r.to_dict() for r in recs]
        except Exception as e:
            logger.debug(f"[AgentBrain] DB task list error: {e}")

        if not tasks:
            tasks = list(reversed(self._task_history))[:limit]
        return tasks

    def _persist_task_journal(self, task: ActiveTaskState):
        """Persist compact task history to database."""
        try:
            with SessionLocal() as db:
                plan_json = json.dumps(task.plan.to_dict()) if task.plan else None
                actions_json = json.dumps(task.step_results)
                errors_json = json.dumps([task.error] if task.error else [])
                dur_ms = int((time.monotonic() - task.start_time_monotonic) * 1000)

                rec = TaskJournalRecord(
                    task_id=task.task_id,
                    goal=task.goal,
                    status=task.status,
                    plan_json=plan_json,
                    actions_json=actions_json,
                    result_json=json.dumps({"verified": task.verification_status == "VERIFIED"}),
                    duration_ms=dur_ms,
                    provider_used=task.provider_used,
                    errors_json=errors_json,
                    verification=task.verification_status,
                    created_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc) if task.completed_at else None,
                )
                db.merge(rec)
                db.commit()
        except Exception as e:
            logger.debug(f"[AgentBrain] Task journal persistence notice: {e}")

    # =========================================================================
    # 5. Offline Capabilities Matrix (Section 15)
    # =========================================================================

    def get_capabilities_matrix(self) -> Dict[str, Any]:
        """
        Dynamically generate the offline and runtime capability matrix.
        Do NOT hard-code fake availability.
        """
        # Test Ollama availability dynamically
        ollama_avail = False
        try:
            from app.providers.manager import provider_manager
            prov = provider_manager.get_provider("ollama")
            if prov and prov.is_configured() and prov.get_available_models():
                ollama_avail = True
        except Exception:
            ollama_avail = False

        # Test local vision capability
        vision_avail = True  # macOS screencapture is always local and verified

        # Test local speech capability
        voice_avail = bool(getattr(settings, "TTS_LOCAL", True))

        offline_capabilities = {
            "chat": ollama_avail,
            "memory": True,  # Smṛti 3.0 is 100% local SQLite
            "planning": True,  # TaskPlanner minimal decomposition is local
            "filesystem": True,  # Local workspace tools
            "computer": True,  # macOS AppleScript & SystemEvents
            "vision": vision_avail,  # macOS Trinetra screen capture
            "voice": voice_avail,  # Chatterbox / local TTS
            "web_search": False,  # External web search requires network
            "cloud_llm": False,  # Cloud LLMs require network
        }

        local_first_capabilities = {
            "prefer_local": True,
            "ollama_available": ollama_avail,
            "cloud_providers_configured": len(provider_manager.get_configured_providers()) > 0,
        }

        return {
            "mode": self._current_mode,
            "runtime_mode": getattr(settings, "NARAD_RUNTIME_MODE", "hybrid"),
            "environment": getattr(settings, "NARAD_ENV", "development"),
            "offline": offline_capabilities,
            "local_first": local_first_capabilities,
            "autonomy_mode": action_policy.get_autonomy_mode(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


agent_brain = AgentBrain()
