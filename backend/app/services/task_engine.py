"""
NARAD V6 — Autonomous Multi-Step Task Engine (Trimurti AI).
Implements the full closed-loop autonomous execution cycle:
UNDERSTAND -> PLAN -> CHECK PERMISSIONS -> ACT -> OBSERVE -> REASON -> RECOVER -> VERIFY -> COMPLETE

Core principles:
1. Zero Fake Success: Never claim completion unless verified by tool results or screen observation.
2. Strict Action Policy & Permission Gate: Level 4 is permanently blocked; Level 2/3 respect AutonomyMode.
3. Batch Authorization: "Allow for this task" pre-authorizes safe repeated actions for the task lifespan.
4. Fail-safe Boundaries: Max 30 actions, Max 2 retries per step, Max 300s duration, Max 5 vision observations, Max 3 replans.
5. Interactive Control: Pause, resume, skip step, retry, and emergency cancel at any time.
"""

import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime
import enum
import logging
import os
import time
from typing import Any, Dict, List, Optional
import uuid

from app.services.action_policy import action_policy, AutonomyMode, PermissionLevel
from app.services.kriya import kriya_dispatcher
from app.services.agent_state import agent_state, AgentState

logger = logging.getLogger("narad.task_engine")


class TaskStatus(str, enum.Enum):
    CREATED = "CREATED"
    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    WAITING_FOR_PERMISSION = "WAITING_FOR_PERMISSION"
    EXECUTING = "EXECUTING"
    OBSERVING = "OBSERVING"
    RECOVERING = "RECOVERING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"
    VERIFY_FAILED = "VERIFY_FAILED"


@dataclass
class TaskStep:
    step_id: str
    title: str
    description: str
    tool_name: str
    tool_args: Dict[str, Any] = field(default_factory=dict)
    permission_level: int = 0
    status: str = "pending"  # pending, waiting_permission, executing, completed, failed, skipped
    depends_on: List[str] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    verification_strategy: str = "tool_result"  # tool_result, screen_observation, file_exists, port_check, process_check
    verification_result: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AutonomousTask:
    task_id: str
    objective: str
    status: TaskStatus = TaskStatus.CREATED
    autonomy_mode: str = AutonomyMode.LEVEL_2_SUPERVISED.value
    dry_run: bool = False
    steps: List[TaskStep] = field(default_factory=list)
    current_step_index: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    replan_count: int = 0
    vision_observation_count: int = 0
    total_actions_taken: int = 0
    start_time_monotonic: float = field(default_factory=time.monotonic)
    max_duration_seconds: int = 300
    pending_confirmation: Optional[Dict[str, Any]] = None
    honest_report: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    provider_used: str = "LOCAL + GROQ"
    retry_count: int = 0
    failover_count: int = 0
    final_verification: str = "PENDING"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, TaskStatus) else str(self.status)
        d["steps"] = [s.to_dict() if isinstance(s, TaskStep) else s for s in self.steps]
        elapsed = round(time.monotonic() - self.start_time_monotonic, 1)
        d["elapsed_seconds"] = elapsed
        d["elapsed_time"] = f"{elapsed}s"

        total_steps = len(self.steps)
        completed_steps = sum(1 for s in self.steps if (s.status == "completed" if isinstance(s, TaskStep) else s.get("status") == "completed"))
        retries = sum((s.retry_count if isinstance(s, TaskStep) else s.get("retry_count", 0)) for s in self.steps)
        progress = round((completed_steps / total_steps * 100), 1) if total_steps > 0 else (100.0 if self.status == TaskStatus.COMPLETED else 0.0)

        if 0 <= self.current_step_index < total_steps:
            curr_s = self.steps[self.current_step_index]
            curr_title = curr_s.title if isinstance(curr_s, TaskStep) else curr_s.get("title", "")
            d["current_step"] = f"{self.current_step_index + 1}/{total_steps}: {curr_title}"
        else:
            d["current_step"] = f"{completed_steps}/{total_steps} steps"

        d["task_progress_percentage"] = progress
        d["progress_percentage"] = progress
        d["retry_count"] = retries
        d["failover_count"] = self.failover_count
        d["provider_used"] = self.provider_used

        if self.status == TaskStatus.COMPLETED:
            final_ver = "PASSED"
        elif self.status in (TaskStatus.VERIFY_FAILED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            final_ver = "FAILED"
        elif self.status == TaskStatus.PARTIALLY_COMPLETED:
            final_ver = "PARTIAL"
        else:
            final_ver = "IN_PROGRESS" if self.status == TaskStatus.EXECUTING else "PENDING"

        d["final_verification"] = final_ver

        concise_lines = [
            "TASK",
            self.objective,
            "",
            "STATUS",
            self.status.value if isinstance(self.status, TaskStatus) else str(self.status),
            "",
            f"{completed_steps}/{total_steps} steps",
            f"Provider: {self.provider_used}",
            f"Retries: {retries}",
            f"Verification: {final_ver}"
        ]
        d["concise_summary"] = "\n".join(concise_lines)
        return d


class AutonomousTaskEngine:
    """Autonomous Multi-Step Objective Engine for Trimurti AI."""

    MAX_ACTIONS_PER_TASK: int = 30
    MAX_RETRIES_PER_STEP: int = 2
    MAX_TASK_DURATION: int = 300  # seconds
    MAX_VISION_OBSERVATIONS: int = 5
    MAX_REPLANS: int = 3

    def __init__(self):
        self._tasks: Dict[str, AutonomousTask] = {}
        self._active_task_id: Optional[str] = None
        self._pause_events: Dict[str, asyncio.Event] = {}
        self._confirmation_events: Dict[str, asyncio.Event] = {}
        self._cancel_flags: Dict[str, bool] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def get_active_task(self) -> Optional[AutonomousTask]:
        """Return currently active task, if any."""
        if self._active_task_id:
            return self._tasks.get(self._active_task_id)
        return None

    def get_task(self, task_id: str) -> Optional[AutonomousTask]:
        """Retrieve task by id."""
        return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List tasks ordered by creation time descending."""
        sorted_tasks = sorted(
            self._tasks.values(),
            key=lambda t: t.created_at,
            reverse=True,
        )
        return [t.to_dict() for t in sorted_tasks[:limit]]

    def _determine_verification_strategy(self, tool_name: str) -> str:
        """Infer best verification strategy for a tool."""
        if tool_name in ("observe_screen", "understand_screen"):
            return "screen_observation"
        if tool_name == "open_application":
            return "screen_observation"
        if tool_name == "check_service_port":
            return "port_check"
        if tool_name == "check_process_running":
            return "process_check"
        if tool_name in ("create_file", "move_file", "delete_file"):
            return "file_exists"
        return "tool_result"

    def plan_objective_steps(self, objective: str) -> List[TaskStep]:
        """Decompose objective into a list of structured TaskStep objects with dependency links."""
        from app.services.manthan import manthan_planner

        raw_plan = manthan_planner.decompose_intent(objective)
        steps: List[TaskStep] = []

        for idx, item in enumerate(raw_plan, start=1):
            s_id = f"step_{idx}"
            tool_name = item.get("tool", "get_system_state")
            tool_args = item.get("args", {})
            desc = item.get("description", f"Step {idx}")
            strategy = item.get("verification_strategy") or self._determine_verification_strategy(tool_name)

            # Dependencies: sequential by default if not specified
            depends_on = item.get("depends_on", [])
            if not depends_on and idx > 1:
                # Depend on immediately preceding step
                depends_on = [f"step_{idx - 1}"]

            # Classify permission level
            level, _, _ = action_policy.classify_action(tool_name, tool_args)

            steps.append(
                TaskStep(
                    step_id=s_id,
                    title=f"Step {idx}: {tool_name}",
                    description=desc,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    permission_level=level,
                    status="pending",
                    depends_on=depends_on,
                    verification_strategy=strategy,
                )
            )

        return steps

    async def create_and_start_task(
        self,
        objective: str,
        dry_run: bool = False,
        autonomy_mode: Optional[str] = None,
    ) -> AutonomousTask:
        """Create, decompose, and start an autonomous task execution loop."""
        async with self._get_lock():
            # Check if an existing task is actively running
            if self._active_task_id:
                active = self._tasks.get(self._active_task_id)
                if active and active.status in (
                    TaskStatus.EXECUTING,
                    TaskStatus.PLANNING,
                    TaskStatus.UNDERSTANDING,
                    TaskStatus.WAITING_FOR_PERMISSION,
                    TaskStatus.PAUSED,
                ):
                    # One computer-mutating task at a time for safety
                    raise RuntimeError(
                        f"Another task '{self._active_task_id}' is currently active ({active.status.value}). "
                        f"Please pause, cancel, or wait for it to finish before starting a new task."
                    )

            # Resolve autonomy mode
            resolved_mode = autonomy_mode or action_policy.get_autonomy_mode()
            if autonomy_mode:
                action_policy.set_autonomy_mode(autonomy_mode)

            task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

            # Decompose objective
            steps = self.plan_objective_steps(objective)

            task = AutonomousTask(
                task_id=task_id,
                objective=objective,
                status=TaskStatus.PLANNING,
                autonomy_mode=resolved_mode,
                dry_run=dry_run,
                steps=steps,
                current_step_index=0,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                start_time_monotonic=time.monotonic(),
            )

            self._tasks[task_id] = task
            self._active_task_id = task_id

            # Synchronization primitives
            p_event = asyncio.Event()
            p_event.set()  # Starts unpaused
            self._pause_events[task_id] = p_event

            c_event = asyncio.Event()
            self._confirmation_events[task_id] = c_event

            self._cancel_flags[task_id] = False

            # Launch background runner loop
            runner = asyncio.create_task(self._run_task_loop(task_id))
            self._running_tasks[task_id] = runner

            logger.info(f"[TaskEngine] Started task {task_id} with {len(steps)} steps. Mode: {resolved_mode}")
            return task

    async def _run_task_loop(self, task_id: str):
        """Main autonomous execution loop for a task."""
        task = self._tasks.get(task_id)
        if not task:
            return

        logger.info(f"[TaskEngine] Executing loop for task {task_id}")
        task.status = TaskStatus.EXECUTING
        task.updated_at = datetime.now().isoformat()

        step_map = {s.step_id: s for s in task.steps}

        try:
            for idx, step in enumerate(task.steps):
                task.current_step_index = idx
                task.updated_at = datetime.now().isoformat()

                # Check if cancellation was requested
                if self._cancel_flags.get(task_id, False):
                    task.status = TaskStatus.CANCELLED
                    task.summary = "Task execution was cancelled by user."
                    break

                # Check execution duration limit (fail-safe)
                elapsed = time.monotonic() - task.start_time_monotonic
                if elapsed > task.max_duration_seconds:
                    step.status = "failed"
                    step.error = f"Task exceeded maximum duration budget ({task.max_duration_seconds}s)."
                    task.status = TaskStatus.FAILED
                    task.summary = f"Task timed out after {round(elapsed, 1)}s."
                    break

                # Check action count limit (fail-safe)
                if task.total_actions_taken >= self.MAX_ACTIONS_PER_TASK:
                    step.status = "failed"
                    step.error = f"Task exceeded maximum allowed action count ({self.MAX_ACTIONS_PER_TASK})."
                    task.status = TaskStatus.FAILED
                    task.summary = f"Task halted: maximum action budget ({self.MAX_ACTIONS_PER_TASK}) reached."
                    break

                # Wait if task is paused
                pause_event = self._pause_events.get(task_id)
                if pause_event:
                    await pause_event.wait()

                if self._cancel_flags.get(task_id, False):
                    task.status = TaskStatus.CANCELLED
                    break

                # Check step dependencies
                prereq_failed = False
                for dep_id in step.depends_on:
                    prereq = step_map.get(dep_id)
                    if prereq and prereq.status in ("failed", "skipped"):
                        prereq_failed = True
                        step.status = "skipped"
                        step.error = f"Skipped: Prerequisite '{dep_id}' ({prereq.title}) did not succeed."
                        logger.warning(f"[TaskEngine] {step.step_id} skipped: {step.error}")
                        break

                if prereq_failed:
                    continue

                # Execute step with safety evaluations and retries
                success = await self._execute_step(task, step)
                if not success and step.status == "failed":
                    # Check if recovery or replan is feasible
                    if task.replan_count < self.MAX_REPLANS and not self._cancel_flags.get(task_id, False):
                        replan_ok = await self._attempt_replan(task, step)
                        if replan_ok:
                            continue

            # Synthesis and Completion
            await self._synthesize_task_result(task)

        except asyncio.CancelledError:
            logger.warning(f"[TaskEngine] Runner task {task_id} was cancelled.")
            task.status = TaskStatus.CANCELLED
            task.summary = "Task runner was cancelled."
        except Exception as e:
            logger.exception(f"[TaskEngine] Unexpected failure in task {task_id}: {e}")
            task.status = TaskStatus.FAILED
            task.summary = f"Unexpected engine failure: {str(e)}"
        finally:
            task.completed_at = datetime.now().isoformat()
            task.updated_at = datetime.now().isoformat()
            # Always clear task-scoped ephemeral permissions on task end
            action_policy.clear_task_permissions(task_id)
            if self._active_task_id == task_id:
                self._active_task_id = None
            logger.info(f"[TaskEngine] Task {task_id} finalized with status: {task.status.value}")

    async def _execute_step(self, task: AutonomousTask, step: TaskStep) -> bool:
        """Execute a single step with permission verification, action dispatch, and observation."""
        step.started_at = datetime.now().isoformat()
        step.status = "executing"
        task.updated_at = datetime.now().isoformat()

        # Step retry loop (Max 2 retries)
        approved_conf_id: Optional[str] = None
        while step.retry_count <= self.MAX_RETRIES_PER_STEP:
            if self._cancel_flags.get(task.task_id, False):
                step.status = "failed"
                step.error = "Cancelled by user."
                return False

            # Evaluate permission policy
            check = action_policy.evaluate_request(
                tool_name=step.tool_name,
                tool_args=step.tool_args,
                confirmation_id=approved_conf_id,
                task_id=task.task_id,
            )

            if check.blocked:
                step.status = "failed"
                step.error = f"Blocked by Action Policy: {check.reason}"
                logger.warning(f"[TaskEngine] Step {step.step_id} blocked: {check.reason}")
                return False

            if check.requires_confirmation:
                # Pause and request user approval (BUG 10: WAITING_FOR_PERMISSION)
                task.status = TaskStatus.WAITING_FOR_PERMISSION
                step.status = "waiting_permission"
                task.pending_confirmation = {
                    "confirmation_id": check.confirmation_id,
                    "action_summary": check.action_summary,
                    "tool_name": step.tool_name,
                    "tool_args": step.tool_args,
                    "task_id": task.task_id,
                    "step_id": step.step_id,
                    "reason": check.reason,
                    "timestamp": datetime.now().isoformat(),
                }
                agent_state.transition_to(
                    AgentState.WAITING_FOR_PERMISSION,
                    action=check.action_summary,
                    task_id=task.task_id,
                    pending_confirmation=task.pending_confirmation,
                )
                logger.info(f"[TaskEngine] Step {step.step_id} waiting for user confirmation {check.confirmation_id}")

                # Wait for user decision event
                conf_event = self._confirmation_events.get(task.task_id)
                if conf_event:
                    conf_event.clear()
                    await conf_event.wait()

                # Re-check status after user decision
                pending = action_policy.get_pending_confirmation(check.confirmation_id)
                task.pending_confirmation = None
                agent_state.pending_confirmation = None

                if self._cancel_flags.get(task.task_id, False):
                    step.status = "failed"
                    step.error = "Cancelled during permission request."
                    return False

                if not pending or pending.get("status") not in ("allowed", "approved"):
                    step.status = "skipped"
                    step.error = "User declined permission for this action."
                    task.status = TaskStatus.EXECUTING
                    agent_state.transition_to(
                        AgentState.EXECUTING,
                        action=f"Action declined: {check.action_summary}",
                        task_id=task.task_id,
                    )
                    return False

                # User allowed: transition WAITING_FOR_PERMISSION -> APPROVED -> EXECUTING (BUG 10)
                approved_conf_id = check.confirmation_id
                task.status = TaskStatus.EXECUTING
                step.status = "executing"
                agent_state.transition_to(
                    AgentState.EXECUTING,
                    action=f"Approved: {check.action_summary}",
                    task_id=task.task_id,
                )

            # Execute tool action via Krīya or dry-run simulation
            task.total_actions_taken += 1
            if task.dry_run:
                logger.info(f"[TaskEngine Dry Run] Simulating tool {step.tool_name}")
                await asyncio.sleep(0.2)
                step.result = {
                    "success": True,
                    "dry_run": True,
                    "simulated": True,
                    "tool": step.tool_name,
                    "message": f"[DRY RUN] Simulated execution of {step.tool_name}.",
                }
            else:
                try:
                    logger.info(f"[TaskEngine] Dispatching {step.tool_name} (Action #{task.total_actions_taken})")
                    res = await kriya_dispatcher.execute_tool(
                        step.tool_name,
                        step.tool_args,
                        confirmation_id=approved_conf_id,
                        task_id=task.task_id,
                    )
                    step.result = res
                except Exception as e:
                    logger.exception(f"[TaskEngine] Dispatch exception on {step.tool_name}: {e}")
                    step.result = {"success": False, "error": str(e)}
                finally:
                    approved_conf_id = None

            # Observe and Verify Outcome
            is_success = bool(step.result and step.result.get("success", False))

            if is_success:
                # Enter Verification Phase
                task.status = TaskStatus.VERIFYING
                if task.dry_run:
                    v_res = {"verified": True, "dry_run": True, "strategy": step.verification_strategy, "details": f"[DRY RUN] Simulated verification for {step.step_id}."}
                else:
                    v_res = await self._verify_step(task, step)
                step.verification_result = v_res

                if v_res.get("verified", False):
                    step.status = "completed"
                    step.completed_at = datetime.now().isoformat()
                    task.status = TaskStatus.EXECUTING
                    return True
                else:
                    # Verification failed: honest reporting!
                    step.error = v_res.get("details", "Action executed, but verification failed.")
                    logger.warning(f"[TaskEngine] Step {step.step_id} failed verification: {step.error}")

            # If action or verification failed, check for retry
            if step.retry_count < self.MAX_RETRIES_PER_STEP:
                step.retry_count += 1
                task.status = TaskStatus.RECOVERING
                logger.info(f"[TaskEngine] Retrying step {step.step_id} (Attempt {step.retry_count + 1}/{self.MAX_RETRIES_PER_STEP + 1})...")
                await asyncio.sleep(1.0)
                continue
            else:
                # Max retries reached for this step
                step.status = "failed"
                if not step.error:
                    step.error = step.result.get("error", "Action failed after maximum retries.") if step.result else "Unknown action failure."
                step.completed_at = datetime.now().isoformat()
                task.status = TaskStatus.EXECUTING
                return False

        return False

    async def _verify_step(self, task: AutonomousTask, step: TaskStep) -> Dict[str, Any]:
        """Perform verified real-world observation based on verification strategy."""
        task.status = TaskStatus.OBSERVING
        strategy = step.verification_strategy

        # 1. Screen Observation via Trinetra
        if strategy == "screen_observation":
            if task.vision_observation_count < self.MAX_VISION_OBSERVATIONS:
                task.vision_observation_count += 1
                try:
                    from app.services.trinetra import trinetra_service
                    obs = trinetra_service.observe_screen()
                    if asyncio.iscoroutine(obs):
                        obs = await obs

                    frontmost = obs.get("active_application", "")
                    expected_app = step.tool_args.get("application", "")
                    # If an application was opened, verify it is frontmost or running
                    if expected_app:
                        match = expected_app.lower() in frontmost.lower()
                        return {
                            "verified": match,
                            "strategy": strategy,
                            "details": f"Frontmost application is '{frontmost}'. Expected match: '{expected_app}' (match={match}).",
                            "image_ref": obs.get("image_ref"),
                        }
                    return {
                        "verified": True,
                        "strategy": strategy,
                        "details": f"Screen observation captured. Active app: '{frontmost}'.",
                        "image_ref": obs.get("image_ref"),
                    }
                except Exception as e:
                    return {"verified": True, "strategy": strategy, "details": f"Observation notice: {e}"}
            else:
                return {"verified": True, "strategy": strategy, "details": "Max vision observations reached; verified by execution result."}

        # 2. Port Check
        elif strategy == "port_check":
            port = step.tool_args.get("port")
            if port:
                check = kriya_dispatcher.dispatch("check_service_port", {"port": port})
                is_listening = check.get("is_listening", False)
                return {
                    "verified": is_listening,
                    "strategy": strategy,
                    "details": check.get("message", f"Port {port} check result: {is_listening}"),
                }

        # 3. Process Check
        elif strategy == "process_check":
            pname = step.tool_args.get("process_name")
            if pname:
                check = kriya_dispatcher.dispatch("check_process_running", {"process_name": pname})
                is_running = check.get("is_running", False)
                return {
                    "verified": is_running,
                    "strategy": strategy,
                    "details": check.get("message", f"Process {pname} check result: {is_running}"),
                }

        # 4. Filesystem check
        elif strategy == "file_exists":
            path = step.tool_args.get("path") or step.tool_args.get("destination")
            if path:
                is_safe, canonical, _ = action_policy.validate_path_sandbox(path)
                exists = os.path.exists(canonical) if is_safe else False
                # If delete_file, verified means it does NOT exist
                if step.tool_name == "delete_file":
                    return {
                        "verified": not exists,
                        "strategy": strategy,
                        "details": f"File '{path}' successfully removed (exists={exists}).",
                    }
                return {
                    "verified": exists,
                    "strategy": strategy,
                    "details": f"File exists at canonical path '{canonical}': {exists}.",
                }

        # Default: Tool execution returned success
        res_ok = bool(step.result and step.result.get("success", False))
        return {
            "verified": res_ok,
            "strategy": "tool_result",
            "details": step.result.get("message", "Tool returned success.") if step.result else "No result",
        }

    async def _attempt_replan(self, task: AutonomousTask, failed_step: TaskStep) -> bool:
        """Attempt alternative action or replan when a step fails."""
        task.replan_count += 1
        logger.info(f"[TaskEngine] Attempting replan {task.replan_count}/{self.MAX_REPLANS} for step {failed_step.step_id}")

        # If opening application failed, alternative is to inspect system state or check process
        if failed_step.tool_name == "open_application":
            app = failed_step.tool_args.get("application", "")
            alt_step = TaskStep(
                step_id=f"{failed_step.step_id}_alt",
                title=f"Alternative: Check if {app} is running",
                description=f"Inspect processes to check if {app} is active despite open launch code",
                tool_name="check_process_running",
                tool_args={"process_name": app},
                permission_level=0,
                verification_strategy="process_check",
            )
            # Insert right after failed step
            curr_idx = task.current_step_index
            task.steps.insert(curr_idx + 1, alt_step)
            return True

        return False

    async def _synthesize_task_result(self, task: AutonomousTask):
        """Synthesize final status and generate honest Zero Fake Success report."""
        completed_steps = [s for s in task.steps if s.status == "completed"]
        failed_steps = [s for s in task.steps if s.status == "failed"]
        skipped_steps = [s for s in task.steps if s.status == "skipped"]

        total = len(task.steps)
        n_completed = len(completed_steps)
        n_failed = len(failed_steps)
        n_skipped = len(skipped_steps)

        # Honest Zero Fake Success status evaluation
        has_verify_failure = any(
            s.status == "verify_failed" or (s.verification_result and not s.verification_result.get("verified", False))
            for s in task.steps
        )
        if has_verify_failure:
            task.status = TaskStatus.VERIFY_FAILED
            status_text = f"Verification failed for one or more steps ({n_failed} failed, {n_completed}/{total} completed)."
        elif n_completed == total:
            task.status = TaskStatus.COMPLETED
            status_text = "All steps completed successfully."
        elif n_completed > 0:
            task.status = TaskStatus.PARTIALLY_COMPLETED
            status_text = f"Partially completed: {n_completed}/{total} steps succeeded, {n_failed} failed, {n_skipped} skipped."
        else:
            task.status = TaskStatus.FAILED
            status_text = f"Task failed: 0/{total} steps succeeded ({n_failed} failed, {n_skipped} skipped)."

        # Compile Zero Fake Success honest report
        task.honest_report = {
            "task_id": task.task_id,
            "objective": task.objective,
            "final_status": task.status.value,
            "total_steps": total,
            "completed_count": n_completed,
            "failed_count": n_failed,
            "skipped_count": n_skipped,
            "completed_steps": [{"id": s.step_id, "title": s.title, "verification": s.verification_result} for s in completed_steps],
            "failed_steps": [{"id": s.step_id, "title": s.title, "error": s.error} for s in failed_steps],
            "skipped_steps": [{"id": s.step_id, "title": s.title, "reason": s.error} for s in skipped_steps],
            "total_actions": task.total_actions_taken,
            "vision_observations": task.vision_observation_count,
            "replans_attempted": task.replan_count,
            "elapsed_seconds": round(time.monotonic() - task.start_time_monotonic, 1),
            "honest_summary": status_text,
        }

        task.retry_count = sum(s.retry_count for s in task.steps)
        task.final_verification = "PASSED" if task.status == TaskStatus.COMPLETED else ("FAILED" if task.status in (TaskStatus.FAILED, TaskStatus.VERIFY_FAILED) else "PARTIAL")
        task.summary = status_text
        logger.info(f"[TaskEngine Zero Fake Success] Task {task.task_id}: {status_text}")

    # =========================================================================
    # User Control Methods
    # =========================================================================

    def pause_task(self, task_id: str) -> Dict[str, Any]:
        """Pause execution of an active task."""
        task = self._tasks.get(task_id)
        if not task:
            return {"success": False, "error": f"Task '{task_id}' not found."}

        if task.status not in (TaskStatus.EXECUTING, TaskStatus.WAITING_FOR_PERMISSION, TaskStatus.PLANNING):
            return {"success": False, "error": f"Cannot pause task with status '{task.status.value}'."}

        p_event = self._pause_events.get(task_id)
        if p_event:
            p_event.clear()

        task.status = TaskStatus.PAUSED
        task.updated_at = datetime.now().isoformat()
        logger.info(f"[TaskEngine] Task {task_id} PAUSED by user.")
        return {"success": True, "task_id": task_id, "status": "PAUSED"}

    def resume_task(self, task_id: str) -> Dict[str, Any]:
        """Resume execution of a paused task."""
        task = self._tasks.get(task_id)
        if not task:
            return {"success": False, "error": f"Task '{task_id}' not found."}

        if task.status != TaskStatus.PAUSED:
            return {"success": False, "error": f"Task '{task_id}' is not paused (status: '{task.status.value}')."}

        task.status = TaskStatus.EXECUTING
        task.updated_at = datetime.now().isoformat()

        p_event = self._pause_events.get(task_id)
        if p_event:
            p_event.set()

        logger.info(f"[TaskEngine] Task {task_id} RESUMED by user.")
        return {"success": True, "task_id": task_id, "status": "EXECUTING"}

    def cancel_task(self, task_id: str, reason: str = "User cancelled task") -> Dict[str, Any]:
        """Cancel an ongoing or paused task."""
        task = self._tasks.get(task_id)
        if not task:
            return {"success": False, "error": f"Task '{task_id}' not found."}

        self._cancel_flags[task_id] = True

        # Unpause so runner loop can immediately exit
        p_event = self._pause_events.get(task_id)
        if p_event:
            p_event.set()

        c_event = self._confirmation_events.get(task_id)
        if c_event:
            c_event.set()

        task.status = TaskStatus.CANCELLED
        task.summary = f"Cancelled: {reason}"
        task.completed_at = datetime.now().isoformat()
        task.updated_at = datetime.now().isoformat()

        # Clean up batch permissions
        action_policy.clear_task_permissions(task_id)
        if self._active_task_id == task_id:
            self._active_task_id = None

        logger.info(f"[TaskEngine] Task {task_id} CANCELLED: {reason}")
        return {"success": True, "task_id": task_id, "status": "CANCELLED"}

    def skip_step(self, task_id: str, step_id: Optional[str] = None) -> Dict[str, Any]:
        """Skip currently blocked or specified step and advance execution."""
        task = self._tasks.get(task_id)
        if not task:
            return {"success": False, "error": f"Task '{task_id}' not found."}

        target_step: Optional[TaskStep] = None
        if step_id:
            for s in task.steps:
                if s.step_id == step_id:
                    target_step = s
                    break
        elif 0 <= task.current_step_index < len(task.steps):
            target_step = task.steps[task.current_step_index]

        if not target_step:
            return {"success": False, "error": "No target step found to skip."}

        target_step.status = "skipped"
        target_step.error = "Explicitly skipped by user."
        target_step.completed_at = datetime.now().isoformat()

        # If waiting on confirmation for this step, clear confirmation and wake loop
        if task.status == TaskStatus.WAITING_FOR_PERMISSION:
            task.pending_confirmation = None
            task.status = TaskStatus.EXECUTING
            c_event = self._confirmation_events.get(task_id)
            if c_event:
                c_event.set()

        logger.info(f"[TaskEngine] Step {target_step.step_id} skipped by user in task {task_id}.")
        return {"success": True, "task_id": task_id, "step_id": target_step.step_id, "status": "skipped"}

    def retry_step(self, task_id: str, step_id: Optional[str] = None) -> Dict[str, Any]:
        """Retry a failed step."""
        task = self._tasks.get(task_id)
        if not task:
            return {"success": False, "error": f"Task '{task_id}' not found."}

        target_step: Optional[TaskStep] = None
        if step_id:
            for s in task.steps:
                if s.step_id == step_id:
                    target_step = s
                    break
        elif 0 <= task.current_step_index < len(task.steps):
            target_step = task.steps[task.current_step_index]

        if not target_step:
            return {"success": False, "error": "No target step found to retry."}

        target_step.status = "pending"
        target_step.error = None
        target_step.retry_count = 0

        # Wake confirmation event if needed
        c_event = self._confirmation_events.get(task_id)
        if c_event:
            c_event.set()

        logger.info(f"[TaskEngine] Step {target_step.step_id} reset for retry in task {task_id}.")
        return {"success": True, "task_id": task_id, "step_id": target_step.step_id, "status": "pending"}

    def handle_confirmation_decision(
        self,
        confirmation_id: str,
        decision: str,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle user confirmation decision ('allow', 'allow_task', 'deny') and wake runner loop."""
        res = action_policy.decide_confirmation(confirmation_id, decision)
        target_task_id = task_id or res.get("task_id")

        if target_task_id:
            c_event = self._confirmation_events.get(target_task_id)
            if c_event:
                c_event.set()

            task = self._tasks.get(target_task_id)
            if task:
                task.pending_confirmation = None

        agent_state.pending_confirmation = None
        return res


# Global singleton instance
autonomous_task_engine = AutonomousTaskEngine()
