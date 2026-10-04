"""
Tests for NARAD V8.2 Milestone 2: Trinetra Verified Execution & Zero Fake Success.

Validates:
1. Trinetra closed-loop verification: ACTION -> SCREEN OBSERVATION -> UNDERSTAND -> VERIFY -> NEXT ACTION.
2. Verification outcome statuses: VERIFIED vs VERIFY_FAILED vs UNVERIFIED.
3. Zero Fake Success: Execution never marks COMPLETE without verification evidence.
4. Handling of unexpected screen states (e.g. wrong active application).
5. Handling of browser navigation failures.
6. Handling of truly unsupported computer tasks with exact capability reporting.
"""

import unittest
from unittest.mock import patch, MagicMock
import asyncio

from app.services.computer import computer_adapter
from app.services.kriya import kriya_dispatcher
from app.services.trinetra import trinetra_service
from app.services.agent_state import AgentState, agent_state
from app.services.manthan import manthan_planner


class TestV82TrinetraVerification(unittest.TestCase):

    def setUp(self):
        # Reset agent state before each test
        agent_state.state = AgentState.IDLE
        agent_state.current_action = None
        agent_state._cancel_requested = False
        agent_state.observation_count = 0

    # 1. Verification of successful browser navigation
    def test_verify_browser_navigation_success(self):
        with patch.object(computer_adapter, "get_active_application", return_value={"active_application": "Firefox"}):
            v_res = trinetra_service.verify_action_outcome(
                action_type="browser_navigate",
                context={"args": {"url": "https://www.programiz.com", "browser": "Firefox"}}
            )
            self.assertTrue(v_res["verified"])
            self.assertEqual(v_res["status"], "VERIFIED")
            self.assertIn("frontmost (verified)", v_res["message"])

    # 2. Verification of browser navigation failure (wrong active app)
    def test_verify_browser_navigation_unexpected_screen_state(self):
        with patch.object(computer_adapter, "get_active_application", return_value={"active_application": "Finder"}):
            v_res = trinetra_service.verify_action_outcome(
                action_type="browser_navigate",
                context={"args": {"url": "https://www.programiz.com", "browser": "Firefox"}}
            )
            self.assertFalse(v_res["verified"])
            self.assertEqual(v_res["status"], "UNVERIFIED")
            self.assertIn("verification failed", v_res["message"])

    # 3. Verification of compiler output success
    def test_verify_compiler_output_success(self):
        with patch.object(computer_adapter, "get_active_application", return_value={"active_application": "Firefox"}):
            v_res = trinetra_service.verify_action_outcome(
                action_type="browser_compiler_workflow",
                context={
                    "args": {"expected_output": "153 is an Armstrong number"},
                    "result": {"success": True, "message": "153 is an Armstrong number", "verified": True}
                }
            )
            self.assertTrue(v_res["verified"])
            self.assertEqual(v_res["status"], "VERIFIED")
            self.assertIn("153 is an Armstrong number", v_res["message"])

    # 4. Verification of compiler output failure (Zero Fake Success)
    def test_verify_compiler_output_failure(self):
        with patch.object(computer_adapter, "get_active_application", return_value={"active_application": "Firefox"}):
            v_res = trinetra_service.verify_action_outcome(
                action_type="browser_compiler_workflow",
                context={
                    "args": {"expected_output": "153 is an Armstrong number"},
                    "result": {"success": False, "error": "Execution timed out without output."}
                }
            )
            self.assertFalse(v_res["verified"])
            self.assertEqual(v_res["status"], "VERIFY_FAILED")
            self.assertIn("Verification failed", v_res["message"])

    # 5. Closed-loop Manthan execution halts on VERIFY_FAILED and never marks COMPLETE
    def test_manthan_halts_on_verification_failure(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with patch.object(kriya_dispatcher, "execute_tool") as mock_exec, \
                 patch.object(trinetra_service, "verify_action_outcome") as mock_verify:
                mock_exec.return_value = {"success": True}

                # Fail verification on step 1 (browser navigation)
                def verify_side_effect(expected_state=None, context=None, **kwargs):
                    tool = (context or {}).get("tool", "")
                    if tool == "browser_navigate":
                        return {"status": "VERIFY_FAILED", "verified": False, "message": "Browser failed to launch."}
                    return {"status": "VERIFIED", "verified": True}

                mock_verify.side_effect = verify_side_effect

                prompt = "Open Programiz C compiler, paste the Armstrong-number program, run it, and enter 153."
                res = loop.run_until_complete(manthan_planner.execute_task(prompt))

                self.assertFalse(res["success"])
                self.assertEqual(res["status"], "VERIFY_FAILED")
                self.assertIn("Verification failed", res["message"])
                # Ensure it halted at step 1 and did not proceed to step 8
                self.assertEqual(len(res["results"]), 1)
        finally:
            loop.close()

    # 6. Truly unsupported computer actions report exact capability without fake success
    def test_manthan_reports_unsupported_action(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            prompt = "reboot the operating system immediately"
            res = loop.run_until_complete(manthan_planner.execute_task(prompt))

            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "FAILED")
            self.assertIn("not supported by the system execution adapter", res["message"])
            self.assertIn("Supported operations include", res["message"])
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
