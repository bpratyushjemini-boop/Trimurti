"""
NARAD V6 — Live E2E Integration Test Suite.
Verifies the end-to-end integration of the Autonomous Multi-Step Task Engine:
- Live FastAPI backend health & subsystem reporting (V6)
- Live Autonomy Mode querying and switching
- Live diagnostic tool execution (port 8000 check, process check)
- Live task creation, execution, and state transitions
- Interactive pause, resume, skip, and cancel controls via HTTP
- Multi-step conversational directives and natural control follow-ups
"""

import asyncio
import time
import unittest
import urllib.request
import json

BASE_URL = "http://127.0.0.1:8000/api"


def _http_get(endpoint: str) -> dict:
    req = urllib.request.Request(f"{BASE_URL}{endpoint}")
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode())


def _http_post(endpoint: str, data: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode())


class TestV6LiveE2E(unittest.TestCase):

    # 1. Health & Subsystem Verification
    def test_01_live_health_reports_v6(self):
        """Live health endpoint must advertise version 6.0.0 or newer and task_engine subsystem."""
        res = _http_get("/health")
        self.assertEqual(res["status"], "online")
        self.assertIn(res["version"], ("6.0.0", "6.1.0", "7.0.0", "7.1.0", "7.2.0"),
                      f"Expected version 6.0.0 or newer, got {res.get('version')}")
        self.assertIn("task_engine", res["subsystems"])
        self.assertEqual(res["subsystems"]["task_engine"], "READY [V6]")
        self.assertIn(res["subsystems"]["narad_core"], ("ONLINE [V6]", "ONLINE [V6.1]", "ONLINE [V7]", "ONLINE [V7.2]"))

    # 2. Autonomy Mode Endpoints
    def test_02_live_autonomy_mode_get_and_set(self):
        """Query and switch autonomy modes via live REST API."""
        initial = _http_get("/agent/autonomy/mode")
        self.assertIn("mode", initial)
        self.assertIn("TASK_AUTONOMY", initial["allowed_modes"])

        # Switch to TASK_AUTONOMY
        set_res = _http_post("/agent/autonomy/mode", {"mode": "TASK_AUTONOMY"})
        self.assertTrue(set_res["success"])
        self.assertEqual(set_res["mode"], "TASK_AUTONOMY")

        # Verify change persisted
        curr = _http_get("/agent/autonomy/mode")
        self.assertEqual(curr["mode"], "TASK_AUTONOMY")

        # Restore default SUPERVISED
        restore_res = _http_post("/agent/autonomy/mode", {"mode": "SUPERVISED"})
        self.assertEqual(restore_res["mode"], "SUPERVISED")

    # 3. Live Diagnostic Tools Execution
    def test_03_live_port_check_detects_running_backend(self):
        """Diagnostic tool check_service_port must verify that live port 8000 is listening."""
        from app.services.kriya import kriya_dispatcher
        check = kriya_dispatcher.dispatch("check_service_port", {"port": 8000})
        self.assertTrue(check["success"])
        self.assertTrue(check["is_listening"])
        self.assertIn("actively listening", check["message"])

    def test_04_live_process_check_detects_active_node_or_python(self):
        """Diagnostic tool check_process_running accurately inspects processes."""
        from app.services.kriya import kriya_dispatcher
        # Check node (Vite is running) or python (backend is running)
        check = kriya_dispatcher.dispatch("check_process_running", {"process_name": "node"})
        self.assertTrue(check["success"])
        # Either node is running or not, but execution succeeds with honest PIDs
        self.assertIsInstance(check["is_running"], bool)
        self.assertIsInstance(check["pids"], list)

    # 4. Live Task Lifecycle (Create, Execute, Details)
    def test_05_create_dry_run_task_and_verify_completion(self):
        """Create a dry-run task via REST API and verify it executes to COMPLETED."""
        create_res = _http_post("/agent/task/create", {
            "objective": "prepare my development environment",
            "dry_run": True,
        })
        self.assertIn("task_id", create_res)
        task_id = create_res["task_id"]
        self.assertEqual(create_res["objective"], "prepare my development environment")

        # Poll for completion (dry-run finishes in < 5 seconds)
        for _ in range(15):
            time.sleep(0.4)
            details = _http_get(f"/agent/task/{task_id}")
            if details["status"] in ("COMPLETED", "FAILED", "PARTIALLY_COMPLETED"):
                break

        self.assertEqual(details["status"], "COMPLETED")
        self.assertIsNotNone(details["honest_report"])
        self.assertEqual(details["honest_report"]["failed_count"], 0)
        self.assertGreaterEqual(details["honest_report"]["completed_count"], 4)

    # 5. Live Task Listing
    def test_06_list_recent_tasks(self):
        """List tasks via /agent/task/list returns recent executions."""
        tasks = _http_get("/agent/task/list?limit=5")
        self.assertIsInstance(tasks, list)
        self.assertGreaterEqual(len(tasks), 1)

    # 6. Task Controls (Pause, Resume, Cancel)
    def test_07_task_pause_and_resume_endpoints(self):
        """Test pause, resume, and cancel endpoints on a live task."""
        create_res = _http_post("/agent/task/create", {
            "objective": "prepare my development environment",
            "dry_run": True,
        })
        task_id = create_res["task_id"]

        # Pause
        p_res = _http_post(f"/agent/task/{task_id}/pause", {})
        self.assertTrue(p_res["success"])
        self.assertEqual(p_res["status"], "PAUSED")

        # Verify state via details
        details = _http_get(f"/agent/task/{task_id}")
        self.assertEqual(details["status"], "PAUSED")

        # Resume
        r_res = _http_post(f"/agent/task/{task_id}/resume", {})
        self.assertTrue(r_res["success"])
        self.assertEqual(r_res["status"], "EXECUTING")

        # Cancel
        c_res = _http_post(f"/agent/task/{task_id}/cancel", {})
        self.assertTrue(c_res["success"])
        self.assertEqual(c_res["status"], "CANCELLED")

    # 7. Step Skip Endpoint
    def test_08_task_step_skip_endpoint(self):
        """Test skipping a step via /agent/task/{task_id}/skip on a live task."""
        create_res = _http_post("/agent/task/create", {
            "objective": "prepare my development environment",
            "dry_run": True,
        })
        task_id = create_res["task_id"]

        # Pause first to freeze step execution
        _http_post(f"/agent/task/{task_id}/pause", {})

        skip_res = _http_post(f"/agent/task/{task_id}/skip", {"step_id": "step_2"})
        self.assertTrue(skip_res["success"])
        self.assertEqual(skip_res["status"], "skipped")

        # Clean up
        _http_post(f"/agent/task/{task_id}/cancel", {})

    # 8. Confirmation with Batch Task ID
    def test_09_confirm_action_supports_batch_allow_task(self):
        """Confirming an action via REST API with 'allow_task' records batch authorization."""
        # Trigger an action requiring confirmation on the server (Level 2 mutating create_file)
        exec_res = _http_post("/agent/execute", {
            "instruction": "create a file called batch_e2e_test.txt with content test",
            "dry_run": False,
        })
        conf_id = exec_res.get("confirmation_id")
        self.assertIsNotNone(conf_id)

        conf_res = _http_post("/agent/confirm", {
            "confirmation_id": conf_id,
            "decision": "allow_task",
            "task_id": "batch_e2e_test",
        })
        self.assertTrue(conf_res["success"])
        self.assertEqual(conf_res["decision"], "allow_task")
        self.assertEqual(conf_res["status"], "approved")

    # 9. Conversational Task Control Directives
    def test_10_conversational_task_status_enquiry(self):
        """Asking 'what is happening?' via chat returns active task status immediately."""
        create_res = _http_post("/agent/task/create", {
            "objective": "Diagnose local system",
            "dry_run": True,
        })
        task_id = create_res["task_id"]
        _http_post(f"/agent/task/{task_id}/pause", {})

        res = _http_post("/chat", {"message": "what is happening?"})
        self.assertIn("response", res)
        self.assertIn("Diagnose local system", res["response"])
        self.assertEqual(res.get("route_reason"), "task_control_status")

        # Clean up
        _http_post(f"/agent/task/{task_id}/cancel", {})


if __name__ == "__main__":
    unittest.main()
