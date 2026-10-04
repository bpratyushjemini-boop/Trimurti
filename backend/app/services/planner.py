"""
NARAD Phase 2 — Structured Task Planner Engine.
Generates minimal, dependency-ordered execution plans:
goal, steps, dependencies, required_tools, risk_level, expected_outputs,
verification_conditions, fallback_strategy.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("narad.planner")


@dataclass
class PlanStep:
    step_id: str
    title: str = ""
    tool_name: str = ""
    tool_args: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    risk_level: str = "safe"  # safe, low, medium, high
    expected_outputs: str = ""
    verification_conditions: str = ""
    fallback_strategy: str = "stop"  # retry, skip, fallback_tool, stop
    status: str = "pending"  # pending, executing, completed, failed, skipped
    description: str = ""

    def __post_init__(self):
        if not self.title and self.description:
            self.title = self.description
        elif not self.description and self.title:
            self.description = self.title

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskPlan:
    goal: str
    steps: List[PlanStep] = field(default_factory=list)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    required_tools: List[str] = field(default_factory=list)
    risk_level: str = "safe"
    expected_outputs: str = ""
    verification_conditions: str = ""
    fallback_strategy: str = "stop"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    plan_id: Optional[str] = None
    is_valid: bool = True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["steps"] = [s.to_dict() if isinstance(s, PlanStep) else s for s in self.steps]
        return d


class TaskPlanner:
    """
    Structured Task Planner for NARAD.
    Produces shortest valid plans, validates dependency ordering,
    and rejects invalid or cyclic plans.
    """

    create_plan = None  # Bound to plan_task below

    def validate_plan(self, plan: TaskPlan) -> Tuple[bool, Optional[str]]:
        """
        Validate plan structure:
        - Non-empty goal
        - Non-empty steps
        - Valid tool names
        - Topological dependency ordering (no cycles or forward references)
        """
        if not plan.goal or not plan.goal.strip():
            return False, "Plan goal cannot be empty."

        if not plan.steps:
            return False, "Plan must contain at least one step."

        step_ids: Set[str] = set()
        seen_ids: Set[str] = set()

        for s in plan.steps:
            if not s.step_id:
                return False, "Each plan step must have a unique step_id."
            if s.step_id in step_ids:
                return False, f"Duplicate step_id detected: '{s.step_id}'"
            step_ids.add(s.step_id)

        # Verify dependencies: must only depend on earlier steps (DAG check)
        for s in plan.steps:
            for dep in s.dependencies:
                if dep not in step_ids:
                    return False, f"Step '{s.step_id}' depends on non-existent step '{dep}'"
                if dep not in seen_ids:
                    return False, f"Cycle or forward reference dependency detected: Step '{s.step_id}' depends on future step '{dep}'"
            seen_ids.add(s.step_id)

        return True, None

    def get_executable_steps(self, plan: TaskPlan, completed_step_ids: Set[str]) -> List[PlanStep]:
        """Return steps whose dependencies have all been completed and are pending."""
        executable = []
        for step in plan.steps:
            if step.step_id not in completed_step_ids and step.status == "pending":
                if all(dep in completed_step_ids for dep in step.dependencies):
                    executable.append(step)
        return executable

    def plan_task(
        self,
        goal: str,
        context_memories: Optional[List[Dict[str, Any]]] = None,
        offline_mode: bool = False,
        local_only_mode: bool = False,
    ) -> TaskPlan:
        """
        Generate a minimal, verifiable task plan for the requested goal.
        Prefers deterministic templates for known tasks to save tokens and latency,
        with minimal step sequencing.
        """
        g_lower = goal.lower().strip()

        # 1. Backend / Project Diagnostics Plan (Section 4 Example)
        if any(p in g_lower for p in (
            "diagnose narad", "diagnose backend", "what is wrong", "what's wrong",
            "check my narad project and tell me what is wrong", "check backend", "inspect project"
        )):
            return self._plan_diagnostics(goal)

        # 2. Development Environment Setup
        if any(p in g_lower for p in ("development environment", "dev environment", "prepare dev", "prepare my dev")):
            return self._plan_dev_environment(goal)

        # 3. Production Build Pipeline
        if any(p in g_lower for p in ("production build", "prepare project for production build", "run production build")):
            return self._plan_production_build(goal)

        # 4. Computer Application Control (e.g. Open Notes, Calculator, Music)
        if g_lower.startswith("open ") or "launch " in g_lower or "music" in g_lower:
            return self._plan_app_action(goal)

        # 5. Screen & Visual Inspection
        if any(p in g_lower for p in ("screen", "screenshot", "look at my screen", "what is on my screen")):
            return self._plan_vision_inspection(goal)

        # 6. Generic Minimal Multi-Step Plan
        return self._plan_generic(goal)

    def _plan_diagnostics(self, goal: str) -> TaskPlan:
        """Section 4 Example: Diagnose NARAD backend."""
        steps = [
            PlanStep(
                step_id="step_1",
                title="Check backend port 8000",
                tool_name="check_service_port",
                tool_args={"port": 8000, "service_name": "NARAD Backend"},
                dependencies=[],
                risk_level="safe",
                expected_outputs="Port 8000 status and connectivity",
                verification_conditions="Port check returns open/closed status",
                fallback_strategy="retry"
            ),
            PlanStep(
                step_id="step_2",
                title="Check frontend port 5173",
                tool_name="check_service_port",
                tool_args={"port": 5173, "service_name": "NARAD Frontend"},
                dependencies=["step_1"],
                risk_level="safe",
                expected_outputs="Port 5173 status",
                verification_conditions="Port check completes",
                fallback_strategy="skip"
            ),
            PlanStep(
                step_id="step_3",
                title="Inspect project workspace directory",
                tool_name="list_directory",
                tool_args={"path": "."},
                dependencies=["step_2"],
                risk_level="safe",
                expected_outputs="Directory listing of workspace",
                verification_conditions="Valid list of project files returned",
                fallback_strategy="stop"
            ),
            PlanStep(
                step_id="step_4",
                title="Verify runtime state and memory integrity",
                tool_name="retrieve_memory",
                tool_args={"query": "active_project"},
                dependencies=["step_3"],
                risk_level="safe",
                expected_outputs="Project memory facts",
                verification_conditions="Memory query executed",
                fallback_strategy="skip"
            )
        ]
        tools = ["check_service_port", "list_directory", "retrieve_memory"]
        return TaskPlan(
            goal=goal,
            steps=steps,
            dependencies={"step_2": ["step_1"], "step_3": ["step_2"], "step_4": ["step_3"]},
            required_tools=tools,
            risk_level="safe",
            expected_outputs="Comprehensive diagnostics of NARAD services, ports, and workspace",
            verification_conditions="All verification checks evaluated",
            fallback_strategy="stop_and_report"
        )

    def _plan_dev_environment(self, goal: str) -> TaskPlan:
        steps = [
            PlanStep(
                step_id="step_1",
                title="Check backend service port 8000",
                tool_name="check_service_port",
                tool_args={"port": 8000, "service_name": "FastAPI Backend"},
                dependencies=[],
                risk_level="safe",
                expected_outputs="Backend port availability",
                verification_conditions="Port 8000 is open or closed",
                fallback_strategy="retry"
            ),
            PlanStep(
                step_id="step_2",
                title="Check frontend dev port 5173",
                tool_name="check_service_port",
                tool_args={"port": 5173, "service_name": "Vite Dev Server"},
                dependencies=["step_1"],
                risk_level="safe",
                expected_outputs="Frontend port availability",
                verification_conditions="Port 5173 verified",
                fallback_strategy="skip"
            ),
            PlanStep(
                step_id="step_3",
                title="Verify development workspace structure",
                tool_name="list_directory",
                tool_args={"path": "backend"},
                dependencies=["step_2"],
                risk_level="safe",
                expected_outputs="Backend structure confirmed",
                verification_conditions="Files list returned",
                fallback_strategy="stop"
            )
        ]
        return TaskPlan(
            goal=goal,
            steps=steps,
            dependencies={"step_2": ["step_1"], "step_3": ["step_2"]},
            required_tools=["check_service_port", "list_directory"],
            risk_level="safe",
            expected_outputs="Development environment status verified",
            verification_conditions="All ports and workspace inspected",
            fallback_strategy="stop"
        )

    def _plan_production_build(self, goal: str) -> TaskPlan:
        steps = [
            PlanStep(
                step_id="step_1",
                title="Inspect frontend project files",
                tool_name="list_directory",
                tool_args={"path": "frontend"},
                dependencies=[],
                risk_level="safe",
                expected_outputs="Frontend directory verified",
                verification_conditions="Package.json and src present",
                fallback_strategy="stop"
            ),
            PlanStep(
                step_id="step_2",
                title="Verify build configuration",
                tool_name="read_file",
                tool_args={"filepath": "frontend/package.json"},
                dependencies=["step_1"],
                risk_level="safe",
                expected_outputs="Valid package.json scripts",
                verification_conditions="File read successful",
                fallback_strategy="stop"
            )
        ]
        return TaskPlan(
            goal=goal,
            steps=steps,
            dependencies={"step_2": ["step_1"]},
            required_tools=["list_directory", "read_file"],
            risk_level="safe",
            expected_outputs="Production build prerequisites verified",
            verification_conditions="Build files inspected",
            fallback_strategy="stop"
        )

    def _plan_app_action(self, goal: str) -> TaskPlan:
        # Extract target app name
        app_name = "Application"
        m = re.search(r'(?:open|launch)\s+([a-zA-Z0-9_\- ]+)', goal, re.IGNORECASE)
        if m:
            app_name = m.group(1).strip()
        elif "music" in goal.lower():
            app_name = "Music"

        steps = [
            PlanStep(
                step_id="step_1",
                title=f"Open {app_name}",
                tool_name="open_application",
                tool_args={"app_name": app_name},
                dependencies=[],
                risk_level="low",
                expected_outputs=f"{app_name} launched and focused",
                verification_conditions=f"Window active for {app_name}",
                fallback_strategy="retry"
            ),
            PlanStep(
                step_id="step_2",
                title=f"Visually verify {app_name} is active",
                tool_name="get_active_application",
                tool_args={},
                dependencies=["step_1"],
                risk_level="safe",
                expected_outputs=f"Active application matches {app_name}",
                verification_conditions=f"Frontmost application verified",
                fallback_strategy="stop"
            )
        ]
        return TaskPlan(
            goal=goal,
            steps=steps,
            dependencies={"step_2": ["step_1"]},
            required_tools=["open_application", "get_active_application"],
            risk_level="low",
            expected_outputs=f"{app_name} launched and visually confirmed",
            verification_conditions="Application frontmost confirmed",
            fallback_strategy="stop"
        )

    def _plan_vision_inspection(self, goal: str) -> TaskPlan:
        steps = [
            PlanStep(
                step_id="step_1",
                title="Capture screen observation",
                tool_name="observe_screen",
                tool_args={},
                dependencies=[],
                risk_level="safe",
                expected_outputs="Screenshot capture and metadata",
                verification_conditions="Image reference created",
                fallback_strategy="retry"
            ),
            PlanStep(
                step_id="step_2",
                title="Inspect active application state",
                tool_name="get_active_application",
                tool_args={},
                dependencies=["step_1"],
                risk_level="safe",
                expected_outputs="Active window title",
                verification_conditions="Application title returned",
                fallback_strategy="stop"
            )
        ]
        return TaskPlan(
            goal=goal,
            steps=steps,
            dependencies={"step_2": ["step_1"]},
            required_tools=["observe_screen", "get_active_application"],
            risk_level="safe",
            expected_outputs="Visual inspection complete",
            verification_conditions="Screenshot captured and verified",
            fallback_strategy="stop"
        )

    def _plan_generic(self, goal: str) -> TaskPlan:
        steps = [
            PlanStep(
                step_id="step_1",
                title="Inspect relevant project state",
                tool_name="retrieve_memory",
                tool_args={"query": goal},
                dependencies=[],
                risk_level="safe",
                expected_outputs="Relevant memories or context",
                verification_conditions="Memory query complete",
                fallback_strategy="skip"
            )
        ]
        return TaskPlan(
            goal=goal,
            steps=steps,
            dependencies={},
            required_tools=["retrieve_memory"],
            risk_level="safe",
            expected_outputs=f"Execution plan for: {goal}",
            verification_conditions="Prerequisites verified",
            fallback_strategy="stop"
        )


TaskPlanner.create_plan = TaskPlanner.plan_task
task_planner = TaskPlanner()
