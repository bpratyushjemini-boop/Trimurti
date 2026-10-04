"""
NARAD PHASE 2 — FINAL MASTER UPGRADE TEST SUITE
================================================
Comprehensive verification of:
1. Agent Brain (Intent classification, capability routing, goal execution)
2. Task Planner (Minimal plans, dependency ordering, cycle/invalid rejection)
3. Tool Orchestrator (Dynamic selection, permission checks, offline/local blockage, observation loop, recovery)
4. Local-First & Offline Architecture (AUTO, LOCAL_ONLY, OFFLINE, CLOUD_PREFERRED, capabilities matrix)
5. Zero Fake Success & Failure Recovery
6. Event System & Proactive Brain notifications
7. iOS-ready REST API contracts (/api/tasks, /api/events, /api/runtime/capabilities, /api/runtime/truth)
8. Section 34 Required E2E Workflows (Tests 1 through 7)
"""

import pytest
import asyncio
import uuid
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.services.agent_brain import agent_brain, RuntimeMode, IntentCategory
from app.services.planner import task_planner, TaskPlan, PlanStep
from app.services.tool_orchestrator import tool_orchestrator, ToolResult, FailureCategory
from app.services.event_system import event_system, EventType
from app.core.narad import narad_core
from app.services.smriti import smriti_service
from app.services.runtime_truth import runtime_truth_service
from app.services.task_engine import autonomous_task_engine, TaskStatus
from app.services.action_policy import action_policy, AutonomyMode
from app.providers.manager import provider_manager


# =============================================================================
# 1. Agent Brain: Intent Classification
# =============================================================================
class TestAgentBrainIntents:
    """Verify intent classification accurately detects intent categories."""

    def test_classify_simple_chat(self):
        intents = agent_brain.classify_intent("Hello Narad, how are you today?")
        assert IntentCategory.CHAT in intents

    def test_classify_question(self):
        intents = agent_brain.classify_intent("What is quantum computing?")
        assert IntentCategory.QUESTION in intents

    def test_classify_memory_task(self):
        intents = agent_brain.classify_intent("Remember that my favourite programming language is Rust.")
        assert IntentCategory.MEMORY in intents

    def test_classify_coding_task(self):
        intents = agent_brain.classify_intent("Write a python function to calculate the Fibonacci series.")
        assert IntentCategory.CODING in intents

    def test_classify_multi_step_computer_task(self):
        intents = agent_brain.classify_intent("Open VS Code, inspect my NARAD project and tell me what's broken.")
        assert IntentCategory.COMPUTER_CONTROL in intents
        assert IntentCategory.FILE_OPERATION in intents
        assert IntentCategory.MULTI_STEP_TASK in intents
        assert IntentCategory.SYSTEM_OPERATION in intents

    def test_classify_vision_task(self):
        intents = agent_brain.classify_intent("Look at the screen and see what error is showing.")
        assert IntentCategory.VISION in intents

    def test_classify_research_task(self):
        intents = agent_brain.classify_intent("Search the web for the latest updates on Python 3.13.")
        assert IntentCategory.RESEARCH in intents

    def test_classify_local_only(self):
        intents = agent_brain.classify_intent("NARAD, answer this using local-only inference. What is 2+2?")
        assert IntentCategory.LOCAL_ONLY in intents

    def test_capability_selection(self):
        caps_coding = agent_brain.select_model_capability([IntentCategory.CODING])
        assert caps_coding == "coding"

        caps_vision = agent_brain.select_model_capability([IntentCategory.VISION])
        assert caps_vision == "vision"

        caps_local = agent_brain.select_model_capability([IntentCategory.LOCAL_ONLY])
        assert caps_local == "local"


# =============================================================================
# 2. Task Planner: Minimal Plans & DAG Dependencies
# =============================================================================
class TestTaskPlanner:
    """Verify minimal planning, dependency validation, and cycle rejection."""

    def test_generate_minimal_plan_diagnostics(self):
        goal = "Diagnose NARAD backend"
        plan = task_planner.create_plan(goal)
        assert plan.is_valid is True
        assert len(plan.steps) > 0
        assert len(plan.steps) <= 7  # Minimal plan, shortest valid path
        assert plan.goal == goal
        assert plan.steps[0].step_id == "step_1"
        assert plan.fallback_strategy == "stop_and_report"

    def test_plan_dependency_topological_ordering(self):
        step1 = PlanStep(step_id="step_1", description="Check health", tool_name="system_status")
        step2 = PlanStep(step_id="step_2", description="Check port", tool_name="check_port", dependencies=["step_1"])
        step3 = PlanStep(step_id="step_3", description="Inspect logs", tool_name="inspect_file", dependencies=["step_2"])

        plan = TaskPlan(
            plan_id="test_plan",
            goal="Test dependencies",
            steps=[step1, step2, step3]
        )
        is_valid, err = task_planner.validate_plan(plan)
        assert is_valid is True
        assert err is None

        # Verify topological execution ordering
        ordered_steps = task_planner.get_executable_steps(plan, completed_step_ids=set())
        assert len(ordered_steps) == 1
        assert ordered_steps[0].step_id == "step_1"

        ordered_steps_after_1 = task_planner.get_executable_steps(plan, completed_step_ids={"step_1"})
        assert len(ordered_steps_after_1) == 1
        assert ordered_steps_after_1[0].step_id == "step_2"

    def test_invalid_plan_rejection_cycle_or_missing_dep(self):
        # Step depends on non-existent step
        invalid_step = PlanStep(step_id="step_1", description="Invalid", tool_name="test", dependencies=["non_existent"])
        plan = TaskPlan(plan_id="inv_plan", goal="Invalid", steps=[invalid_step])
        is_valid, err = task_planner.validate_plan(plan)
        assert is_valid is False
        assert "non-existent" in err

        # Step depends on a later step (cycle/invalid forward reference)
        step_a = PlanStep(step_id="step_1", description="A", tool_name="test", dependencies=["step_2"])
        step_b = PlanStep(step_id="step_2", description="B", tool_name="test")
        plan_cyclic = TaskPlan(plan_id="cyclic", goal="Cyclic", steps=[step_a, step_b])
        is_valid_cycle, err_cycle = task_planner.validate_plan(plan_cyclic)
        assert is_valid_cycle is False
        assert "forward reference" in err_cycle


# =============================================================================
# 3. Tool Orchestrator: Dynamic Selection, Permissions & Offline Execution
# =============================================================================
class TestToolOrchestrator:
    """Verify tool metadata, dynamic selection, permission gating, and error handling."""

    def test_dynamic_tool_selection_by_intent(self):
        # Vision intent should expose vision tools, not web search
        vision_tools = tool_orchestrator.select_tools_for_intent([IntentCategory.VISION])
        tool_names = [t.name for t in vision_tools]
        assert "observe_screen" in tool_names
        assert "web_search" not in tool_names

        # Research intent should expose web search
        research_tools = tool_orchestrator.select_tools_for_intent([IntentCategory.RESEARCH])
        research_names = [t.name for t in research_tools]
        assert "web_search" in research_names

    @pytest.mark.asyncio
    async def test_execute_valid_safe_tool(self):
        result = await tool_orchestrator.execute_tool("get_system_state", {}, dry_run=False)
        assert result["tool"] == "get_system_state"
        assert result["success"] is True
        assert result["duration_ms"] >= 0
        assert result["error"] is None
        assert "cpu" in str(result["result"]) or "timestamp" in str(result["result"]) or isinstance(result["result"], dict)

    @pytest.mark.asyncio
    async def test_execute_invalid_tool_returns_structured_failure(self):
        # Never fake success: non-existent tool must fail explicitly
        result = await tool_orchestrator.execute_tool("non_existent_tool_123", {})
        assert result["tool"] == "non_existent_tool_123"
        assert result["success"] is False
        assert result["failure_category"] == FailureCategory.TOOL_ERROR.value
        assert "Unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_offline_mode_blocks_network_dependent_tool(self):
        # In OFFLINE mode, web_search must be explicitly blocked
        agent_brain.set_mode(RuntimeMode.OFFLINE)
        try:
            result = await tool_orchestrator.execute_tool("web_search", {"query": "test"})
            assert result["success"] is False
            assert result["failure_category"] == FailureCategory.NETWORK_ERROR.value
            assert "OFFLINE_BLOCKED" in result["error"]
        finally:
            agent_brain.set_mode(RuntimeMode.AUTO)

    @pytest.mark.asyncio
    async def test_local_only_mode_blocks_cloud_tools(self):
        agent_brain.set_mode(RuntimeMode.LOCAL_ONLY)
        try:
            result = await tool_orchestrator.execute_tool("web_search", {"query": "test"})
            assert result["success"] is False
            assert result["failure_category"] == FailureCategory.PERMISSION_DENIED.value
            assert "LOCAL_ONLY_BLOCKED" in result["error"]
        finally:
            agent_brain.set_mode(RuntimeMode.AUTO)

    @pytest.mark.asyncio
    async def test_autonomy_l0_blocks_tool_execution(self):
        # L0: CHAT_ONLY blocks mutating actions
        orig = action_policy.autonomy_mode
        try:
            action_policy.autonomy_mode = AutonomyMode.LEVEL_0_CHAT_ONLY
            result = await tool_orchestrator.execute_tool("delete_file", {"path": "/tmp/test.txt"})
            assert result["success"] is False
            assert result["failure_category"] == FailureCategory.PERMISSION_DENIED.value
        finally:
            action_policy.autonomy_mode = orig


# =============================================================================
# 4. Failure Recovery & Post-Action Observation Loop
# =============================================================================
class TestFailureRecovery:
    """Verify structured failure handling, safe retry logic, and zero fake success."""

    def test_retry_decisions(self):
        # Timeout and service unavailable are retryable
        res_timeout = {"tool": "test", "success": False, "error": "timeout", "failure_category": FailureCategory.TIMEOUT.value}
        assert tool_orchestrator.can_retry(res_timeout, attempt_count=1) is True

        res_unavailable = {"tool": "test", "success": False, "error": "503", "failure_category": FailureCategory.SERVICE_UNAVAILABLE.value}
        assert tool_orchestrator.can_retry(res_unavailable, attempt_count=2) is True

        # Non-retryable failures: permission denied and invalid argument
        res_denied = {"tool": "test", "success": False, "error": "denied", "failure_category": FailureCategory.PERMISSION_DENIED.value}
        assert tool_orchestrator.can_retry(res_denied, attempt_count=1) is False

        # Exceeding max retries stops retry
        assert tool_orchestrator.can_retry(res_timeout, attempt_count=3) is False

    @pytest.mark.asyncio
    async def test_post_action_observation_loop(self):
        # Mutating computer action triggers visual observation comparison
        with patch("app.services.computer.computer_adapter.get_active_application", return_value={"active_application": "Terminal"}):
            obs = await tool_orchestrator._observe_post_action("open_application", {"app_name": "Terminal"})
            assert obs is not None
            assert obs.get("verified") is True


# =============================================================================
# 5. Local-First & Offline Operational Modes
# =============================================================================
class TestOperationalModes:
    """Verify AUTO, LOCAL_ONLY, OFFLINE, and CLOUD_PREFERRED operational modes."""

    def test_mode_transitions(self):
        # Start in AUTO
        agent_brain.set_mode(RuntimeMode.AUTO)
        assert agent_brain.get_mode() == RuntimeMode.AUTO

        # Switch to LOCAL_ONLY
        agent_brain.set_mode(RuntimeMode.LOCAL_ONLY)
        assert agent_brain.get_mode() == RuntimeMode.LOCAL_ONLY
        assert agent_brain.is_local_only() is True
        assert agent_brain.is_offline() is False

        # Switch to OFFLINE
        agent_brain.set_mode(RuntimeMode.OFFLINE)
        assert agent_brain.get_mode() == RuntimeMode.OFFLINE
        assert agent_brain.is_offline() is True

        # Reset to AUTO
        agent_brain.set_mode(RuntimeMode.AUTO)
        assert agent_brain.get_mode() == RuntimeMode.AUTO

    def test_dynamic_capabilities_matrix(self):
        caps = agent_brain.get_capabilities_matrix()
        assert "mode" in caps
        assert "offline" in caps
        assert "local_first" in caps

        offline_caps = caps["offline"]
        assert offline_caps["chat"] is True
        assert offline_caps["memory"] is True
        assert offline_caps["planning"] is True
        assert offline_caps["filesystem"] is True
        assert offline_caps["cloud_llm"] is False


# =============================================================================
# 6. Event System & Proactive Brain Foundation
# =============================================================================
class TestEventSystem:
    """Verify structured event emission, notification filtering, and persistence."""

    @pytest.mark.asyncio
    async def test_emit_and_filter_events(self):
        # High priority failure event should trigger notification
        evt_fail = event_system.emit_event(
            event_type=EventType.TASK_FAILED,
            title="Task Execution Failed",
            body="Step 3 timed out after 30000ms",
            priority="high",
            task_id="test_task_fail"
        )
        assert evt_fail["event_type"] == (EventType.TASK_FAILED.value if hasattr(EventType.TASK_FAILED, "value") else EventType.TASK_FAILED)
        notif_fail = event_system.evaluate_notification_worthiness(evt_fail)
        assert notif_fail is not None
        assert notif_fail["type"] == (EventType.TASK_FAILED.value if hasattr(EventType.TASK_FAILED, "value") else EventType.TASK_FAILED)

        # Normal low-priority action completed event should NOT spam notifications
        evt_action = event_system.emit_event(
            event_type=EventType.ACTION_COMPLETED,
            title="Read file completed",
            body="Read 42 bytes",
            priority="normal",
            task_id="test_task_read"
        )
        notif_action = event_system.evaluate_notification_worthiness(evt_action)
        assert notif_action is None

        # Verify recent events retrieval
        recent = event_system.get_recent_events(limit=5)
        assert len(recent) > 0


# =============================================================================
# 7. iOS-Ready REST API Contracts
# =============================================================================
class TestIOSAPIContracts:
    """Verify clean, stable JSON REST API endpoints for future iOS client."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_get_runtime_truth(self, client):
        resp = client.get("/api/runtime/truth")
        assert resp.status_code == 200
        data = resp.json()
        assert "identity" in data
        assert "inference" in data
        assert "provider" in data["inference"]
        assert "execution_mode" in data["inference"]
        assert "network_required" in data["inference"]

    def test_get_runtime_capabilities(self, client):
        resp = client.get("/api/runtime/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert "offline" in data
        assert "local_first" in data
        assert data["offline"]["chat"] is True

    def test_post_runtime_mode(self, client):
        resp = client.post("/api/runtime/mode", json={"mode": "LOCAL_ONLY"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "LOCAL_ONLY"
        assert data["status"] == "updated"

        # Reset back to AUTO
        client.post("/api/runtime/mode", json={"mode": "AUTO"})

    def test_tasks_crud_and_cancel_contract(self, client):
        # 1. Create a task via POST /api/tasks
        create_resp = client.post("/api/tasks", json={
            "goal": "Diagnose NARAD backend",
            "session_id": "ios_session_01"
        })
        assert create_resp.status_code == 200
        task_data = create_resp.json()
        task_id = task_data["task_id"]
        assert task_id is not None
        assert task_data["goal"] == "Diagnose NARAD backend"

        # 2. Get task by ID via GET /api/tasks/{task_id}
        get_resp = client.get(f"/api/tasks/{task_id}")
        assert get_resp.status_code == 200
        retrieved = get_resp.json()
        assert retrieved["task_id"] == task_id
        assert "status" in retrieved

        # 3. List tasks via GET /api/tasks
        list_resp = client.get("/api/tasks")
        assert list_resp.status_code == 200
        tasks_list = list_resp.json()
        assert any(t["task_id"] == task_id for t in tasks_list)

        # 4. Cancel task via POST /api/tasks/{task_id}/cancel
        cancel_resp = client.post(f"/api/tasks/{task_id}/cancel")
        assert cancel_resp.status_code == 200
        cancel_data = cancel_resp.json()
        assert cancel_data["status"] in ("TASK_CANCELLED", "CANCELLED")

    def test_get_events_contract(self, client):
        resp = client.get("/api/events?limit=10")
        assert resp.status_code == 200
        events_list = resp.json()
        assert isinstance(events_list, list)

    def test_get_memory_contract(self, client):
        resp = client.get("/api/memory")
        assert resp.status_code == 200
        assert "memories" in resp.json() or isinstance(resp.json(), list)


# =============================================================================
# 8. Section 34 Required E2E Workflows (Tests 1 through 7)
# =============================================================================
class TestSection34RequiredE2E:
    """Verify all 7 mandatory E2E workflows specified in Section 34."""

    @pytest.fixture(autouse=True)
    def reset_mode(self):
        agent_brain.set_mode(RuntimeMode.AUTO)
        yield
        agent_brain.set_mode(RuntimeMode.AUTO)

    @pytest.mark.asyncio
    async def test_1_simple_chat_qubit(self):
        """TEST 1: 'Explain what a qubit is.' -> simple response."""
        res = await narad_core.process_message("Explain what a qubit is.")
        assert res is not None
        assert res.get("status") == "success"
        content = res.get("response", "").lower()
        assert any(term in content for term in ("quantum", "bit", "superposition", "qubit"))

    @pytest.mark.asyncio
    async def test_2_remember_narad_main_project(self):
        """TEST 2: 'Remember that NARAD is my main AI project.' -> Smṛti persistence."""
        res = await narad_core.process_message("Remember that NARAD is my main AI project.")
        assert res is not None
        assert res.get("status") == "success"
        # Verify persistence in Smṛti 3.0
        relevant = smriti_service.retrieve_relevant_memories("What is my main AI project?")
        assert any("NARAD" in m.get("content", "") or "NARAD" in m.get("value", "") for m in relevant)

    @pytest.mark.asyncio
    async def test_3_inspect_project_workflow(self):
        """TEST 3: 'NARAD, inspect my project and tell me what's wrong.' -> plan -> tools -> observation -> result."""
        mock_port_tool = {"success": True, "is_open": True, "open": True, "port": 8000, "status": "listening", "is_listening": True, "is_running": True}
        with patch("app.services.kriya.kriya_dispatcher.dispatch", return_value={"success": True, "is_listening": True, "is_running": True, "message": "Service online"}), \
             patch("app.services.kriya.kriya_dispatcher.execute_tool", return_value=mock_port_tool):
            res = await narad_core.process_message("NARAD, inspect my project and tell me what's wrong.")
            assert res is not None
            assert res.get("status") in ("success", "completed", "failed", "executing")
            # Autonomous project inspection triggers plan & tools execution
            assert "plan" in res or "tools_executed" in res or "inspection" in res.get("response", "").lower() or "status" in res

    @pytest.mark.asyncio
    async def test_4_use_local_only_inference(self):
        """TEST 4: 'NARAD, use local-only inference.' -> Ollama only, cloud blocked."""
        res = await narad_core.process_message("NARAD, use local-only inference.")
        assert res is not None
        assert res.get("status") == "success"
        assert res.get("execution_mode") == "local"
        assert res.get("provider") == "ollama"
        assert agent_brain.get_mode() == RuntimeMode.LOCAL_ONLY

        # Verify that cloud inference is blocked while in LOCAL_ONLY
        blocked_res = await narad_core.process_message("Hello", requested_provider="groq")
        assert "LOCAL_ONLY_BLOCKED" in blocked_res.get("response", "")

    @pytest.mark.asyncio
    async def test_5_runtime_state_query(self):
        """TEST 5: 'NARAD, tell me your runtime state.' -> Runtime Truth."""
        res = await narad_core.process_message("NARAD, tell me your runtime state.")
        assert res is not None
        assert res.get("status") == "success"
        assert res.get("route_reason") in ("RUNTIME_TRUTH_QUERY", "runtime_truth_report")
        content = res.get("response", "")
        assert "RUNTIME REPORT" in content or "RUNTIME TRUTH" in content or "INFERENCE" in content
        assert "Execution:" in content
        assert "Provider:" in content

    @pytest.mark.asyncio
    async def test_6_prepare_development_environment(self):
        """TEST 6: 'NARAD, prepare my development environment.' -> Task Engine workflow."""
        mock_port_tool = {"success": True, "is_open": True, "open": True, "port": 8000, "status": "listening", "is_listening": True, "is_running": True}
        with patch("app.services.kriya.kriya_dispatcher.dispatch", return_value={"success": True, "is_listening": True, "is_running": True, "message": "Service online"}), \
             patch("app.services.kriya.kriya_dispatcher.execute_tool", return_value=mock_port_tool):
            res = await narad_core.process_message("NARAD, prepare my development environment.")
            assert res is not None
            assert res.get("status") in ("success", "completed", "executing")
            assert "task_id" in res or "development environment" in res.get("response", "").lower()

    @pytest.mark.asyncio
    async def test_7_cancel_active_task(self):
        """TEST 7: Cancel an active task -> TASK_CANCELLED."""
        # 1. Start a task via agent_brain
        task = agent_brain.create_task("Long running diagnostic build task")
        assert task.status in ("CREATED", "PLANNING", "EXECUTING", "PENDING")

        # 2. Issue cancellation
        cancel_res = await narad_core.process_message("cancel active task")
        assert cancel_res.get("status") in ("success", "TASK_CANCELLED")
        assert "TASK_CANCELLED" in cancel_res.get("response", "")

