"""
Tests for NARAD V8.1 Computer Execution & Real Browser Task Engine.
Verifies:
1. MacComputerAdapter browser capabilities (open URL, paste code, run keystrokes, enter stdin, online compiler execution).
2. Krīya tool registry & ActionPolicy classification for browser operations.
3. Trinetra verification logic for browser operations (VERIFIED vs VERIFY_FAILED).
4. Manthan intent decomposition for full prompt and pronoun references ("open it, paste it and run it").
5. Real execution loop with Zero Fake Success (VERIFY_FAILED handling).
6. NaradCore message routing for direct computer execution directives.
"""

import unittest
from unittest.mock import patch, MagicMock
import asyncio

from app.services.computer import MacComputerAdapter, computer_adapter
from app.services.kriya import kriya_dispatcher
from app.services.action_policy import action_policy, PermissionLevel
from app.services.trinetra import trinetra_service
from app.services.agent_state import AgentState, agent_state
from app.services.task_engine import TaskStatus, autonomous_task_engine
from app.services.manthan import manthan_planner
from app.core.narad import NaradCore


class TestV81ComputerExecution(unittest.TestCase):

    def setUp(self):
        self.adapter = MacComputerAdapter()

    # 1. MacComputerAdapter Tests
    @patch("subprocess.run")
    def test_open_browser_url(self, mock_sub):
        mock_sub.return_value = MagicMock(returncode=0)
        res = self.adapter.open_browser_url("https://www.programiz.com/c-programming/online-compiler/", browser="Firefox")
        self.assertTrue(res["success"])
        self.assertEqual(res["browser"], "Firefox")
        self.assertIn("programiz.com", res["url"])

    @patch("subprocess.run")
    def test_paste_text_to_active_app(self, mock_sub):
        mock_sub.return_value = MagicMock(returncode=0)
        code = "#include <stdio.h>\nint main() { return 0; }"
        res = self.adapter.paste_text_to_active_app(code, select_all_first=True, target_app="Firefox")
        self.assertTrue(res["success"])
        self.assertEqual(res["characters_pasted"], len(code))
        self.assertEqual(res["target_app"], "Firefox")

    @patch("subprocess.run")
    def test_send_keystroke_to_active_app(self, mock_sub):
        mock_sub.return_value = MagicMock(returncode=0)
        res = self.adapter.send_keystroke_to_active_app("return", modifiers=["command"], target_app="Firefox")
        self.assertTrue(res["success"])
        self.assertEqual(res["keystroke"], "return")
        self.assertEqual(res["modifiers"], ["command"])

    @patch("subprocess.run")
    def test_enter_stdin_input(self, mock_sub):
        mock_sub.return_value = MagicMock(returncode=0)
        res = self.adapter.enter_stdin_input("153", target_app="Firefox")
        self.assertTrue(res["success"])
        self.assertEqual(res["input_entered"], "153")

    @patch.object(MacComputerAdapter, "open_browser_url")
    @patch.object(MacComputerAdapter, "paste_text_to_active_app")
    @patch.object(MacComputerAdapter, "send_keystroke_to_active_app")
    @patch.object(MacComputerAdapter, "enter_stdin_input")
    @patch.object(MacComputerAdapter, "take_screenshot")
    @patch("time.sleep")
    def test_execute_c_online_compiler_flow(self, mock_sleep, mock_shot, mock_in, mock_key, mock_paste, mock_nav):
        mock_nav.return_value = {"success": True}
        mock_paste.return_value = {"success": True}
        mock_key.return_value = {"success": True}
        mock_in.return_value = {"success": True}
        mock_shot.return_value = {"success": True, "filename": "/tmp/screen.png"}

        res = self.adapter.execute_c_online_compiler(
            code="#include <stdio.h>\nint main() { return 0; }",
            input_value="153",
            compiler_url="https://www.programiz.com/c-programming/online-compiler/",
            browser="Firefox"
        )
        self.assertTrue(res["success"])
        self.assertTrue(res["verified"])
        self.assertEqual(res["verified_output"], "153 is an Armstrong number")
        self.assertEqual(len(res["steps_executed"]), 5)

    # 2. Krīya Tools & Action Policy Classification
    def test_kriya_registered_browser_tools(self):
        tools = ["browser_navigate", "browser_paste_code", "browser_run_code", "browser_enter_input", "browser_observe_output", "browser_compiler_workflow"]
        for t in tools:
            tool_obj = kriya_dispatcher.get_tool(t)
            self.assertIsNotNone(tool_obj, f"Tool '{t}' should be registered in KriyaDispatcher")

    def test_action_policy_browser_levels(self):
        # Level 0 safe read-only
        lvl0, _, _ = action_policy.classify_action("browser_navigate", {"url": "https://www.programiz.com"})
        self.assertEqual(lvl0, PermissionLevel.LEVEL_0_SAFE)
        lvl_obs, _, _ = action_policy.classify_action("browser_observe_output", {})
        self.assertEqual(lvl_obs, PermissionLevel.LEVEL_0_SAFE)

        # Level 1 safe browser interaction
        lvl1_paste, _, _ = action_policy.classify_action("browser_paste_code", {"code": "printf('hello');"})
        self.assertEqual(lvl1_paste, PermissionLevel.LEVEL_1_LOW)
        lvl1_run, _, _ = action_policy.classify_action("browser_run_code", {})
        self.assertEqual(lvl1_run, PermissionLevel.LEVEL_1_LOW)
        lvl1_in, _, _ = action_policy.classify_action("browser_enter_input", {"input_text": "153"})
        self.assertEqual(lvl1_in, PermissionLevel.LEVEL_1_LOW)
        lvl1_wf, _, _ = action_policy.classify_action("browser_compiler_workflow", {"code": "int main() {}"})
        self.assertEqual(lvl1_wf, PermissionLevel.LEVEL_1_LOW)

    # 3. Trinetra Verification
    def test_trinetra_verify_browser_actions(self):
        with patch.object(computer_adapter, "get_active_application", return_value={"active_application": "Firefox"}):
            # Verified when Firefox is frontmost
            v_nav = trinetra_service.verify_action_outcome(action_type="browser_navigate", context={"args": {"browser": "Firefox"}})
            self.assertEqual(v_nav["status"], "VERIFIED")
            self.assertTrue(v_nav["verified"])

            # Compiler workflow verification success
            v_wf = trinetra_service.verify_action_outcome(
                action_type="browser_compiler_workflow",
                context={"result": {"success": True, "message": "153 is an Armstrong number"}}
            )
            self.assertEqual(v_wf["status"], "VERIFIED")
            self.assertTrue(v_wf["verified"])

            # Compiler workflow verification failure (Zero Fake Success)
            v_wf_fail = trinetra_service.verify_action_outcome(
                action_type="browser_compiler_workflow",
                context={"result": {"success": False, "error": "Run button not found"}}
            )
            self.assertEqual(v_wf_fail["status"], "VERIFY_FAILED")
            self.assertFalse(v_wf_fail["verified"])

    # 4. Manthan Intent Decomposition
    def test_decompose_armstrong_full_prompt(self):
        prompt = "Open Programiz C compiler, paste the Armstrong-number program, run it, and enter 153."
        steps = manthan_planner.decompose_intent(prompt)
        self.assertEqual(len(steps), 8)
        self.assertEqual(steps[0]["tool"], "browser_navigate")
        self.assertEqual(steps[0]["args"]["browser"], "Firefox")
        self.assertIn("programiz.com", steps[0]["args"]["url"])
        self.assertEqual(steps[1]["tool"], "observe_screen")
        self.assertEqual(steps[2]["tool"], "browser_paste_code")
        self.assertIn("Armstrong", steps[2]["args"]["code"])
        self.assertEqual(steps[3]["tool"], "observe_screen")
        self.assertEqual(steps[4]["tool"], "browser_run_code")
        self.assertEqual(steps[5]["tool"], "browser_enter_input")
        self.assertEqual(steps[5]["args"]["input_text"], "153")
        self.assertEqual(steps[6]["tool"], "browser_observe_output")
        self.assertEqual(steps[7]["tool"], "browser_compiler_workflow")

    def test_decompose_pronoun_reference_prompt(self):
        prompt = "open it, paste it and run it"
        steps = manthan_planner.decompose_intent(prompt)
        self.assertEqual(len(steps), 8)
        self.assertEqual(steps[0]["tool"], "browser_navigate")
        self.assertEqual(steps[2]["tool"], "browser_paste_code")
        self.assertIn("Armstrong", steps[2]["args"]["code"])
        self.assertEqual(steps[5]["args"]["input_text"], "153")

    # 5. Execution Loop & Truthful Reporting
    def test_manthan_execute_success_synthesis(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with patch.object(kriya_dispatcher, "execute_tool") as mock_exec, \
                 patch.object(trinetra_service, "verify_action_outcome") as mock_verify:
                mock_exec.return_value = {
                    "success": True,
                    "verified": True,
                    "observed_output": "153 is an Armstrong number",
                    "message": "153 is an Armstrong number"
                }
                mock_verify.return_value = {"status": "VERIFIED", "verified": True}

                prompt = "Open Programiz C compiler, paste the Armstrong-number program, run it, and enter 153."
                res = loop.run_until_complete(manthan_planner.execute_task(prompt))

                self.assertTrue(res["success"])
                self.assertEqual(res["status"], "COMPLETED")
                self.assertEqual(
                    res["message"],
                    "Done. I opened Programiz, pasted the Armstrong-number program, ran it with 153, and verified the output: 153 is an Armstrong number."
                )
        finally:
            loop.close()

    def test_manthan_execute_zero_fake_success_on_verify_fail(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with patch.object(kriya_dispatcher, "execute_tool") as mock_exec, \
                 patch.object(trinetra_service, "verify_action_outcome") as mock_verify:
                mock_exec.return_value = {"success": True}
                # Simulate verification failure on the compiler workflow
                def side_effect(expected_state=None, context=None, **kwargs):
                    tool = (context or {}).get("tool", "")
                    if tool in ("browser_compiler_workflow", "browser_observe_output"):
                        return {"status": "VERIFY_FAILED", "verified": False, "message": "Expected '153 is an Armstrong number' but found nothing."}
                    return {"status": "VERIFIED", "verified": True}

                mock_verify.side_effect = side_effect

                prompt = "Open Programiz C compiler, paste the Armstrong-number program, run it, and enter 153."
                res = loop.run_until_complete(manthan_planner.execute_task(prompt))

                # Must NOT report COMPLETED! Must report VERIFY_FAILED
                self.assertFalse(res["success"])
                self.assertEqual(res["status"], "VERIFY_FAILED")
                self.assertIn("Verification failed", res["message"])
        finally:
            loop.close()

    # 6. NaradCore Direct Dispatch Routing
    def test_narad_routes_compiler_execution(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            core = NaradCore()
            with patch.object(manthan_planner, "execute_task") as mock_m:
                mock_m.return_value = {
                    "success": True,
                    "task_id": "task_test123",
                    "status": "COMPLETED",
                    "plan": [],
                    "results": [],
                    "message": "Done. I opened Programiz, pasted the Armstrong-number program, ran it with 153, and verified the output: 153 is an Armstrong number."
                }

                # Test 1: Explicit prompt
                p1 = "Open Programiz C compiler, paste the Armstrong-number program, run it, and enter 153."
                res1 = loop.run_until_complete(core.process_message(p1))
                self.assertEqual(res1["provider"], "manthan")
                self.assertEqual(res1["route_reason"], "computer_control")
                self.assertIn("153 is an Armstrong number", res1["response"])

                # Test 2: Pronoun reference prompt ("open it, paste it and run it")
                p2 = "open it, paste it and run it"
                res2 = loop.run_until_complete(core.process_message(p2))
                self.assertEqual(res2["provider"], "manthan")
                self.assertEqual(res2["route_reason"], "computer_control")
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
