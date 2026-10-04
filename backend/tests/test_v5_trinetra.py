"""NARAD V5 - Dedicated Trinetra Multimodal Vision Test Suite.

Verifies the 12 core Trinetra vision & screen understanding capabilities:
1. Screen capture & sips JPEG downsampling/optimization (< 500KB)
2. Active application detection via AppleScript
3. Structured observation metadata sanitization (no absolute local paths leaked)
4. Screen change detection (perceptual diff / hash)
5. Action outcome verification for application focus
6. Action outcome verification for Apple Music playback
7. Vision-capable model router strictness (TASK_VISION only routes to vision models)
8. Truthful unconfigured vision response (Zero Fake Success)
9. Manthan visual intent decomposition (Observe -> Understand -> Verify)
10. Observation safety limit (MAX_VISION_OBSERVATIONS = 5)
11. Kriya dispatcher registration of Trinetra vision tools (Level 0 Safe Read)
12. Emergency STOP integration with visual loop
"""

import asyncio
import os
import unittest
import shutil

from app.services.trinetra import trinetra_service
from app.services.action_policy import action_policy, PermissionLevel
from app.services.kriya import kriya_dispatcher
from app.services.agent_state import agent_state, AgentState
from app.services.manthan import manthan_planner
from app.core.router import model_router
from app.providers.manager import provider_manager


class TestV5Trinetra(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        agent_state.reset()
        os.makedirs(trinetra_service.screenshots_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        agent_state.reset()

    def test_01_screen_capture_and_optimization(self):
        """TEST 1: Capture screen and verify native sips compression."""
        obs = trinetra_service.observe_screen(purpose="unit_test_capture")
        self.assertTrue(obs.get("success"), f"observe_screen failed: {obs}")
        self.assertIn("image_ref", obs)
        self.assertIn("dimensions", obs)
        self.assertIn("active_application", obs)

        img_path = trinetra_service._image_registry.get(obs["image_ref"]) or os.path.join(trinetra_service.screenshots_dir, f"{obs['image_ref']}.jpg")
        self.assertTrue(os.path.exists(img_path), f"File does not exist: {img_path}")

        # Check size < 500KB
        size_bytes = os.path.getsize(img_path)
        self.assertLess(size_bytes, 500 * 1024, f"Image exceeds 500KB limit: {size_bytes} bytes")
        self.assertTrue(img_path.endswith(".jpg"), "Optimized image must be JPEG")

    def test_02_get_active_application(self):
        """TEST 2: Active application query returns frontmost app name."""
        app_name = trinetra_service.get_active_application()
        self.assertIsInstance(app_name, str)
        self.assertTrue(len(app_name) > 0, "App name should not be empty")

    def test_03_structured_observation_metadata_sanitization(self):
        """TEST 3: Verify image_ref does not leak absolute filesystem paths."""
        obs = trinetra_service.observe_screen(purpose="sanitization_test")
        self.assertTrue(obs.get("success"))
        ref = obs.get("image_ref")
        self.assertFalse(os.path.isabs(ref), f"image_ref leaked absolute path: {ref}")
        self.assertNotIn("/", ref, f"image_ref should be a simple filename, got: {ref}")

    def test_04_screen_change_detection(self):
        """TEST 4: Compare screenshots for visual changes."""
        obs1 = trinetra_service.observe_screen(purpose="diff_test_1")
        ref1 = obs1["image_ref"]

        # Identical image comparison
        diff_same = trinetra_service.detect_screen_change(ref1, ref1)
        self.assertTrue(diff_same.get("success"))
        self.assertFalse(diff_same.get("changed"), "Identical image must report changed=False")
        self.assertEqual(diff_same.get("diff_score"), 0.0)

        # Non-identical image comparison: create a dummy different image
        diff_file = "diff_dummy.jpg"
        diff_path = os.path.join(trinetra_service.screenshots_dir, diff_file)
        with open(diff_path, "wb") as f:
            f.write(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xFF\xDB\x00C\x00\xFF\xD9")

        try:
            diff_diff = trinetra_service.detect_screen_change(ref1, diff_file)
            self.assertTrue(diff_diff.get("success"))
            self.assertTrue(diff_diff.get("changed"), "Different images must report changed=True")
        finally:
            if os.path.exists(diff_path):
                os.remove(diff_path)

    def test_05_visual_verification_app_focus(self):
        """TEST 5: Action verification for application focus."""
        current_app = trinetra_service.get_active_application()

        # Should pass when verifying the actual active app
        res_pass = trinetra_service.verify_action_outcome(
            action_type="open_application",
            target_identifier=current_app
        )
        self.assertTrue(res_pass.get("verified"))

        # Should fail when verifying an impossible/random app name
        res_fail = trinetra_service.verify_action_outcome(
            action_type="open_application",
            target_identifier="NonExistentApp999xyz"
        )
        self.assertFalse(res_fail.get("verified"))

    def test_06_visual_verification_apple_music(self):
        """TEST 6: Action verification for Apple Music playback state."""
        res = trinetra_service.verify_action_outcome(
            action_type="music_play",
            target_identifier="Back In Black"
        )
        # Should return a valid outcome dict with truthful verified flag (zero fake success)
        self.assertIn("verified", res)
        self.assertIn("details", res)
        self.assertIsInstance(res["verified"], bool)

    def test_07_vision_model_router_strictness(self):
        """TEST 7: Model Router strictly routes TASK_VISION to vision-capable providers."""
        vision_route = model_router.resolve_vision_route()
        self.assertEqual(vision_route.task_type, "vision")
        self.assertIn(vision_route.primary_provider, ["gemini", "openrouter", "unconfigured_vision", "none"])

        # Failover candidates must all support vision
        for cand in vision_route.failover_candidates:
            cand_p = cand["provider"] if isinstance(cand, dict) else cand
            self.assertIn(cand_p, ["gemini", "openrouter"])
            provider_inst = provider_manager.get_provider(cand_p)
            if provider_inst:
                self.assertTrue(provider_inst.supports_vision())

    def test_08_truthful_unconfigured_vision_response(self):
        """TEST 8: Zero Fake Success when vision models lack credentials."""
        obs = trinetra_service.observe_screen(purpose="zero_fake_test")
        ref = obs["image_ref"]

        res = asyncio.run(
            trinetra_service.understand_screen(ref, "What code is displayed on the screen?")
        )
        self.assertIn("answer", res)
        # If no Gemini or OpenRouter key is set in .env, it MUST state unavailable truthfully
        if not res.get("configured"):
            self.assertIn("Vision capability is currently unavailable", res["answer"])
            self.assertTrue(res.get("no_fake_success"))

    def test_09_manthan_visual_intent_decomposition(self):
        """TEST 9: Manthan decomposes visual requests into Observe -> Understand -> Verify loop."""
        plan_screen = manthan_planner.plan_task("What is currently on my screen?")
        tools = [step["tool"] for step in plan_screen]
        self.assertIn("observe_screen", tools)
        self.assertIn("understand_screen", tools)

        plan_open = manthan_planner.plan_task("Open Calculator and visually verify it opened")
        open_tools = [step["tool"] for step in plan_open]
        self.assertIn("open_application", open_tools)
        self.assertIn("observe_screen", open_tools)

    def test_10_observation_limit_safety(self):
        """TEST 10: Manthan enforces MAX_VISION_OBSERVATIONS limit."""
        agent_state.reset()
        agent_state.observation_count = 5  # At limit

        res = asyncio.run(
            manthan_planner.execute_task("What is on my screen?")
        )
        # Must pause or halt due to limit
        self.assertTrue(
            res.get("status") in ["limit_reached", "paused"] or "limit" in res.get("message", "").lower(),
            f"Expected limit stop, got: {res}"
        )
        agent_state.reset()

    def test_11_kriya_dispatcher_vision_tools(self):
        """TEST 11: Kriya dispatcher executes Trinetra tools with Level 0 Safe Read policy."""
        # Check action policy level
        self.assertEqual(action_policy.get_permission_level("observe_screen"), PermissionLevel.SAFE_READ)
        self.assertEqual(action_policy.get_permission_level("understand_screen"), PermissionLevel.SAFE_READ)
        self.assertEqual(action_policy.get_permission_level("detect_screen_change"), PermissionLevel.SAFE_READ)

        # Dispatch observe_screen
        obs_res = kriya_dispatcher.dispatch("observe_screen", {"purpose": "kriya_test"})
        self.assertTrue(obs_res.get("success"))
        self.assertIn("image_ref", obs_res)

    def test_12_emergency_stop_halts_agent(self):
        """TEST 12: Emergency stop immediately halts Manthan execution."""
        agent_state.emergency_stop("Safety abort initiated by user.")
        self.assertIn(agent_state.state, [AgentState.CANCELLED, "CANCELLED"])

        res = asyncio.run(
            manthan_planner.execute_task("What is on my screen?")
        )
        self.assertFalse(res.get("success"))
        self.assertIn(res.get("status"), ["CANCELLED", "stopped", "halted"])
        agent_state.reset()


if __name__ == "__main__":
    unittest.main()
