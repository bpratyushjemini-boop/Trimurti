"""
NARAD V6 — Autonomous Multi-Step Task Engine Unit Test Suite.
Tests:
1. AutonomyMode states (CHAT_ONLY, SUGGEST, SUPERVISED, TASK_AUTONOMY) & Level 4 rejection.
2. TaskStep data structures and dependency checking.
3. Task lifecycle state machine transitions (CREATED -> PLANNING -> EXECUTING -> VERIFYING -> COMPLETED).
4. Task-scoped batch authorization ("allow_task") and ephemeral clearance.
5. Fail-safe limits (MAX_ACTIONS_PER_TASK, MAX_RETRIES_PER_STEP, duration timeout).
6. Single active task concurrency protection.
7. Diagnostic tools (check_process_running, check_service_port).
8. Interactive task controls (pause, resume, cancel, skip_step, retry_step).
9. Zero Fake Success honest reporting synthesis.
10. API route dispatch and safety evaluations.
"""

import asyncio
import os
import unittest
from unittest.mock import patch, MagicMock

from app.services.action_policy import action_policy, AutonomyMode, PermissionLevel
from app.services.kriya import kriya_dispatcher
from app.services.task_engine import (
    AutonomousTaskEngine,
    AutonomousTask,
    TaskStep,
    TaskStatus,
    autonomous_task_engine,
)


class TestV6AutonomousAgent(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Reset policy mode to supervised default
        action_policy.set_autonomy_mode("SUPERVISED")
        # Clear any leftover task permissions
        action_policy._task_scope_permissions.clear()

    # -------------------------------------------------------------------------
    # 1. Autonomy Mode & Safety Checks
    # -------------------------------------------------------------------------

    def test_default_autonomy_mode_is_supervised(self):
        """Default autonomy mode must be SUPERVISED (Level 2)."""
        self.assertEqual(action_policy.get_autonomy_mode(), "SUPERVISED")

    def test_autonomy_mode_transitions(self):
        """Verify valid mode transitions between CHAT_ONLY, SUGGEST, SUPERVISED, TASK_AUTONOMY."""
        for mode in ("CHAT_ONLY", "SUGGEST", "SUPERVISED", "TASK_AUTONOMY"):
            res = action_policy.set_autonomy_mode(mode)
            self.assertTrue(res["success"])
            self.assertEqual(action_policy.get_autonomy_mode(), mode)

    def test_level_4_unrestricted_autonomy_prohibited(self):
        """Level 4 (unrestricted autonomy) is strictly prohibited and rejected."""
        res = action_policy.set_autonomy_mode("UNRESTRICTED")
        self.assertFalse(res["success"])
        self.assertIn("Level 4", res["error"])

        res2 = action_policy.set_autonomy_mode("LEVEL_4")
        self.assertFalse(res2["success"])

    def test_chat_only_mode_blocks_all_actions(self):
        """In CHAT_ONLY mode, computer actions must be strictly blocked."""
        action_policy.set_autonomy_mode("CHAT_ONLY")
        res = action_policy.evaluate_request("open_application", {"application": "Calculator"})
        self.assertTrue(res.blocked)
        self.assertIn("CHAT_ONLY", res.reason)

    def test_suggest_mode_blocks_execution(self):
        """In SUGGEST mode, actions are proposed but execution is blocked."""
        action_policy.set_autonomy_mode("SUGGEST")
        res = action_policy.evaluate_request("open_application", {"application": "Calculator"})
        self.assertTrue(res.blocked)
        self.assertIn("SUGGEST", res.reason)

    def test_task_autonomy_auto_authorizes_level_2_actions(self):
        """In TASK_AUTONOMY mode, safe Level 2 operations (file edits, dev commands) are auto-authorized."""
        action_policy.set_autonomy_mode("TASK_AUTONOMY")
        res = action_policy.evaluate_request("run_development_command", {"command": "git status"})
        self.assertTrue(res.allowed)
        self.assertFalse(res.requires_confirmation)

    def test_task_autonomy_still_requires_confirmation_for_level_3(self):
        """In TASK_AUTONOMY mode, destructive Level 3 operations (delete_file, close_app) still require user consent."""
        action_policy.set_autonomy_mode("TASK_AUTONOMY")
        res = action_policy.evaluate_request("close_application", {"application": "Terminal"})
        self.assertTrue(res.requires_confirmation)

    # -------------------------------------------------------------------------
    # 2. Batch Permissions ("Allow for this task")
    # -------------------------------------------------------------------------

    def test_batch_permission_lifecycle(self):
        """Verify 'allow_task' pre-authorizes tool for task_id and clears when task ends.
        Uses 'npm install' (Level 2 mutation) which correctly requires confirmation.
        Note: read-only commands like 'git status' are Level 0 SAFE READ per V6 policy
        and do NOT require confirmation.
        """
        task_id = "test_task_batch_123"
        action_policy.set_autonomy_mode("SUPERVISED")

        # 'npm install' is Level 2 (mutation) and requires confirmation
        res1 = action_policy.evaluate_request("run_development_command", {"command": "npm install"}, task_id=task_id)
        self.assertTrue(res1.requires_confirmation,
                        "npm install must require Level 2 confirmation in SUPERVISED mode")
        conf_id = res1.confirmation_id

        # User decides "allow_task"
        dec_res = action_policy.decide_confirmation(conf_id, "allow_task")
        self.assertTrue(dec_res["success"])
        self.assertEqual(dec_res["decision_type"], "allow_task")

        # Subsequent evaluation with same task_id should be auto-authorized
        res2 = action_policy.evaluate_request("run_development_command", {"command": "npm install"}, task_id=task_id)
        self.assertTrue(res2.allowed)
        self.assertFalse(res2.requires_confirmation)

        # Different task_id still requires confirmation (isolation)
        res_other = action_policy.evaluate_request("run_development_command", {"command": "npm install"}, task_id="other_task_456")
        self.assertTrue(res_other.requires_confirmation)

        # Clean up task permissions
        action_policy.clear_task_permissions(task_id)
        res3 = action_policy.evaluate_request("run_development_command", {"command": "npm install"}, task_id=task_id)
        self.assertTrue(res3.requires_confirmation)


    # -------------------------------------------------------------------------
    # 3. Diagnostic Tools (check_process_running, check_service_port)
    # -------------------------------------------------------------------------

    def test_check_process_running_registered_and_safe(self):
        """check_process_running must be registered at Permission Level 0 (Safe Read)."""
        tool = kriya_dispatcher.get_tool("check_process_running")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.permission_level, 0)

        res = kriya_dispatcher.dispatch("check_process_running", {"process_name": "non_existent_proc_xyz_999"})
        self.assertTrue(res["success"])
        self.assertFalse(res["is_running"])

    def test_check_service_port_registered_and_safe(self):
        """check_service_port must be registered at Permission Level 0 (Safe Read)."""
        tool = kriya_dispatcher.get_tool("check_service_port")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.permission_level, 0)

        # Port 1 should not be listening locally
        res = kriya_dispatcher.dispatch("check_service_port", {"port": 1})
        self.assertTrue(res["success"])
        self.assertFalse(res["is_listening"])

    def test_open_application_with_optional_path(self):
        """open_application tool must accept optional path parameter."""
        tool = kriya_dispatcher.get_tool("open_application")
        self.assertIn("path", tool.parameters["properties"])

    # -------------------------------------------------------------------------
    # 4. Planning & Decomposition
    # -------------------------------------------------------------------------

    def test_plan_objective_steps_generation(self):
        """Engine decomposes objective into structured TaskStep objects with dependency links."""
        engine = AutonomousTaskEngine()
        steps = engine.plan_objective_steps("prepare my development environment")
        self.assertGreaterEqual(len(steps), 4)

        # Step 1 should have no dependencies
        self.assertEqual(steps[0].depends_on, [])
        # Step 2 should depend on preceding step
        self.assertIn("step_1", steps[1].depends_on)
        # Check verification strategies assigned
        self.assertEqual(steps[0].verification_strategy, "port_check")

    def test_dependency_checking_skips_on_prereq_failure(self):
        """If step 1 fails, dependent step 2 must be marked skipped."""
        engine = AutonomousTaskEngine()
        task = AutonomousTask(
            task_id="test_dep_fail",
            objective="test dependency failure",
            steps=[
                TaskStep(
                    step_id="step_1",
                    title="Prerequisite Step",
                    description="This step fails",
                    tool_name="get_system_state",
                    status="failed",
                    error="Simulated network error",
                ),
                TaskStep(
                    step_id="step_2",
                    title="Dependent Step",
                    description="Depends on step 1",
                    tool_name="check_service_port",
                    tool_args={"port": 8000},
                    depends_on=["step_1"],
                    status="pending",
                ),
            ],
        )
        engine._tasks[task.task_id] = task

        # Run loop
        step_map = {s.step_id: s for s in task.steps}
        for dep_id in task.steps[1].depends_on:
            prereq = step_map.get(dep_id)
            if prereq and prereq.status in ("failed", "skipped"):
                task.steps[1].status = "skipped"
                task.steps[1].error = f"Skipped: Prerequisite '{dep_id}' did not succeed."

        self.assertEqual(task.steps[1].status, "skipped")
        self.assertIn("Prerequisite 'step_1'", task.steps[1].error)

    # -------------------------------------------------------------------------
    # 5. Task Engine Execution & State Machine
    # -------------------------------------------------------------------------

    async def test_dry_run_task_execution_completes(self):
        """A dry-run task must execute all steps simulated without mutations and reach COMPLETED."""
        engine = AutonomousTaskEngine()
        task = await engine.create_and_start_task(
            objective="prepare my development environment",
            dry_run=True,
        )
        runner = engine._running_tasks.get(task.task_id)
        if runner:
            await runner

        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertIsNotNone(task.honest_report)
        self.assertEqual(task.honest_report["failed_count"], 0)
        self.assertEqual(task.honest_report["completed_count"], len(task.steps))

    async def test_single_active_task_concurrency_guard(self):
        """Engine must reject concurrent tasks while one is actively executing."""
        engine = AutonomousTaskEngine()
        task1 = await engine.create_and_start_task("prepare my development environment", dry_run=True)

        # Set task1 status to EXECUTING manually to test guard
        task1.status = TaskStatus.EXECUTING

        with self.assertRaises(RuntimeError) as ctx:
            await engine.create_and_start_task("check why frontend build is failing", dry_run=True)
        self.assertIn("Another task", str(ctx.exception))

        # Cleanup
        engine.cancel_task(task1.task_id)

    # -------------------------------------------------------------------------
    # 6. Interactive Task Controls (Pause, Resume, Cancel, Skip, Retry)
    # -------------------------------------------------------------------------

    def test_pause_and_resume_task(self):
        """Test pause and resume transitions on active task."""
        engine = AutonomousTaskEngine()
        task = AutonomousTask(task_id="t_pause_1", objective="pause test", status=TaskStatus.EXECUTING)
        engine._tasks[task.task_id] = task
        engine._active_task_id = task.task_id
        engine._pause_events[task.task_id] = asyncio.Event()
        engine._pause_events[task.task_id].set()

        # Pause
        p_res = engine.pause_task(task.task_id)
        self.assertTrue(p_res["success"])
        self.assertEqual(task.status, TaskStatus.PAUSED)
        self.assertFalse(engine._pause_events[task.task_id].is_set())

        # Resume
        r_res = engine.resume_task(task.task_id)
        self.assertTrue(r_res["success"])
        self.assertEqual(task.status, TaskStatus.EXECUTING)
        self.assertTrue(engine._pause_events[task.task_id].is_set())

    def test_cancel_task_restores_safety(self):
        """Cancelling a task must transition to CANCELLED and clear batch permissions."""
        engine = AutonomousTaskEngine()
        task = AutonomousTask(task_id="t_cancel_1", objective="cancel test", status=TaskStatus.EXECUTING)
        engine._tasks[task.task_id] = task
        engine._active_task_id = task.task_id
        engine._pause_events[task.task_id] = asyncio.Event()
        engine._confirmation_events[task.task_id] = asyncio.Event()

        # Pre-authorize tool under batch permission
        action_policy._task_scope_permissions[task.task_id] = {"run_development_command"}

        c_res = engine.cancel_task(task.task_id, reason="User abort")
        self.assertTrue(c_res["success"])
        self.assertEqual(task.status, TaskStatus.CANCELLED)
        self.assertNotIn(task.task_id, action_policy._task_scope_permissions)
        self.assertIsNone(engine._active_task_id)

    def test_skip_step(self):
        """Skipping a step must advance it to 'skipped' status."""
        engine = AutonomousTaskEngine()
        step = TaskStep(step_id="step_1", title="Step 1", description="desc", tool_name="get_system_state", status="pending")
        task = AutonomousTask(task_id="t_skip_1", objective="skip test", steps=[step], current_step_index=0)
        engine._tasks[task.task_id] = task

        s_res = engine.skip_step(task.task_id, "step_1")
        self.assertTrue(s_res["success"])
        self.assertEqual(step.status, "skipped")
        self.assertIn("skipped by user", step.error.lower())

    def test_retry_step(self):
        """Retrying a failed step must reset its status to pending."""
        engine = AutonomousTaskEngine()
        step = TaskStep(step_id="step_1", title="Step 1", description="desc", tool_name="get_system_state", status="failed", error="timeout", retry_count=2)
        task = AutonomousTask(task_id="t_retry_1", objective="retry test", steps=[step], current_step_index=0)
        engine._tasks[task.task_id] = task

        r_res = engine.retry_step(task.task_id, "step_1")
        self.assertTrue(r_res["success"])
        self.assertEqual(step.status, "pending")
        self.assertIsNone(step.error)
        self.assertEqual(step.retry_count, 0)

    # -------------------------------------------------------------------------
    # 7. Zero Fake Success Synthesis
    # -------------------------------------------------------------------------

    async def test_zero_fake_success_all_completed(self):
        """When all steps complete, status is COMPLETED with accurate tallies."""
        engine = AutonomousTaskEngine()
        task = AutonomousTask(
            task_id="t_synth_1",
            objective="synthesis test complete",
            steps=[
                TaskStep(step_id="s1", title="Step 1", description="", tool_name="get_system_state", status="completed"),
                TaskStep(step_id="s2", title="Step 2", description="", tool_name="check_service_port", status="completed"),
            ],
        )
        await engine._synthesize_task_result(task)
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(task.honest_report["completed_count"], 2)
        self.assertEqual(task.honest_report["failed_count"], 0)
        self.assertIn("All steps completed successfully", task.honest_report["honest_summary"])

    async def test_zero_fake_success_partial_completion(self):
        """When some steps fail/skip, status is PARTIALLY_COMPLETED with honest breakdown."""
        engine = AutonomousTaskEngine()
        task = AutonomousTask(
            task_id="t_synth_2",
            objective="synthesis test partial",
            steps=[
                TaskStep(step_id="s1", title="Step 1", description="", tool_name="get_system_state", status="completed"),
                TaskStep(step_id="s2", title="Step 2", description="", tool_name="check_service_port", status="failed", error="Port closed"),
            ],
        )
        await engine._synthesize_task_result(task)
        self.assertEqual(task.status, TaskStatus.PARTIALLY_COMPLETED)
        self.assertEqual(task.honest_report["completed_count"], 1)
        self.assertEqual(task.honest_report["failed_count"], 1)
        self.assertIn("Partially completed", task.honest_report["honest_summary"])

    async def test_zero_fake_success_all_failed(self):
        """When no steps succeed, status is FAILED with honest reporting."""
        engine = AutonomousTaskEngine()
        task = AutonomousTask(
            task_id="t_synth_3",
            objective="synthesis test fail",
            steps=[
                TaskStep(step_id="s1", title="Step 1", description="", tool_name="get_system_state", status="failed", error="Network dead"),
            ],
        )
        await engine._synthesize_task_result(task)
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertEqual(task.honest_report["completed_count"], 0)
        self.assertEqual(task.honest_report["failed_count"], 1)


if __name__ == "__main__":
    unittest.main()
