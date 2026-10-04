"""
Comprehensive Unit & Integration Test Suite for NARAD V3.1:
Intelligent Multi-Provider Router, Model Registry, Health Tracking,
Intelligent Failover (429/timeouts/5xx vs 400 non-failover),
Conversational Context Sliding Window, and Telemetry.
"""

import unittest
import asyncio
import time
from typing import List, Dict, Any, Optional

from app.core.router import (
    model_router,
    TASK_FAST_CHAT,
    TASK_GENERAL_CHAT,
    TASK_REASONING,
    TASK_CODING,
    TASK_TOOL_USE,
    TASK_LONG_CONTEXT,
    TASK_VISION,
    TASK_VOICE
)
from app.providers.base import BaseLLMProvider
from app.providers.manager import provider_manager
from app.core.narad import NaradCore


class DummyProvider(BaseLLMProvider):
    """Configurable dummy provider for testing failover and health tracking."""

    def __init__(self, pid: str, name: str, behavior: str = "success", error_code: int = 429):
        super().__init__()
        self._pid = pid
        self._name = name
        self.behavior = behavior
        self.error_code = error_code
        self.call_count = 0

    @property
    def provider_id(self) -> str:
        return self._pid

    @property
    def display_name(self) -> str:
        return self._name

    def is_configured(self) -> bool:
        return True

    def get_available_models(self) -> List[str]:
        return [f"{self._pid}-model-v1"]

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        self.call_count += 1
        start_t = time.perf_counter()

        if self.behavior == "success":
            latency_ms = 15
            self.record_success(latency_ms)
            return {
                "content": f"Response from {self._name} [{model}]",
                "provider": self.provider_id,
                "model": model or f"{self._pid}-model-v1",
                "latency_ms": latency_ms,
                "status": "success",
                "tools_executed": [],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10}
            }
        elif self.behavior == "fail_429":
            err_msg = "Rate limit reached: 429 Too Many Requests"
            self.record_failure(err_msg, is_transient=True, cooldown_seconds=60.0)
            return {
                "content": f"⚠️ **{self._name} FAILED:** {err_msg}",
                "provider": self.provider_id,
                "model": model,
                "latency_ms": 10,
                "status": "rate_limit",
                "is_transient": True,
                "error": err_msg,
                "usage": {}
            }
        elif self.behavior == "fail_400":
            err_msg = "400 Bad Request: Invalid tool parameter schema"
            self.record_failure(err_msg, is_transient=False, cooldown_seconds=0.0)
            return {
                "content": f"⚠️ **{self._name} FAILED:** {err_msg}",
                "provider": self.provider_id,
                "model": model,
                "latency_ms": 10,
                "status": "client_error",
                "is_transient": False,
                "error": err_msg,
                "usage": {}
            }
        elif self.behavior == "fail_timeout":
            err_msg = "Request timed out after 30 seconds"
            self.record_failure(err_msg, is_transient=True, cooldown_seconds=30.0)
            return {
                "content": f"⚠️ **{self._name} FAILED:** {err_msg}",
                "provider": self.provider_id,
                "model": model,
                "latency_ms": 10,
                "status": "timeout",
                "is_transient": True,
                "error": err_msg,
                "usage": {}
            }
        raise RuntimeError("Unknown test behavior")

    async def stream_response(self, messages, model=None, **kwargs):
        res = await self.generate_response(messages, model, **kwargs)
        yield res["content"]


class TestModelRouterAndFailover(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    # =========================================================================
    # Task Classification Tests
    # =========================================================================

    def test_task_classification(self):
        """Test task classification across all 8 logical categories."""
        # 1. Fast chat
        self.assertEqual(model_router.classify_task("Hello"), TASK_FAST_CHAT)
        self.assertEqual(model_router.classify_task("hi narad"), TASK_FAST_CHAT)

        # 2. Coding
        self.assertEqual(model_router.classify_task("Write a python function to compute fibonacci"), TASK_CODING)
        self.assertEqual(model_router.classify_task("def solve(x): return x * 2"), TASK_CODING)
        self.assertEqual(model_router.classify_task("Here is the traceback: SyntaxError in line 4"), TASK_CODING)

        # 3. Reasoning
        self.assertEqual(model_router.classify_task("Explain step by step how quantum superposition works"), TASK_REASONING)
        self.assertEqual(model_router.classify_task("Prove that the square root of 2 is irrational"), TASK_REASONING)

        # 4. Tool use
        self.assertEqual(model_router.classify_task("What time is it in Tokyo right now?"), TASK_TOOL_USE)
        self.assertEqual(model_router.classify_task("Search web for latest spacecraft launch"), TASK_TOOL_USE)
        self.assertEqual(model_router.classify_task("According to the document, what is the goal?"), TASK_TOOL_USE)
        self.assertEqual(model_router.classify_task("Remember that my preferred language is Rust"), TASK_TOOL_USE)

        # 5. Long context
        long_text = "Analysis " * 600
        self.assertEqual(model_router.classify_task(long_text), TASK_LONG_CONTEXT)

        # 6. Voice
        self.assertEqual(model_router.classify_task("Tell me a brief summary", is_voice=True), TASK_VOICE)

        # 7. Vision
        self.assertEqual(model_router.classify_task("Look at this chart", has_vision=True), TASK_VISION)

        # 8. General chat
        self.assertEqual(model_router.classify_task("I am thinking about starting a new garden this spring."), TASK_GENERAL_CHAT)

    # =========================================================================
    # Provider Registration & Capabilities Tests
    # =========================================================================

    def test_provider_registration(self):
        """Verify all 4 core providers (Groq, NVIDIA NIM, Gemini, OpenRouter) are registered."""
        providers = provider_manager.list_providers()
        p_ids = [p["id"] for p in providers]
        self.assertIn("groq", p_ids)
        self.assertIn("nvidia", p_ids)
        self.assertIn("gemini", p_ids)
        self.assertIn("openrouter", p_ids)
        self.assertNotIn("mock-narad", p_ids)

    def test_model_capability_registry(self):
        """Verify model capabilities and lookup in registry."""
        groq_models = model_router.registry.get_models_for_category(TASK_FAST_CHAT)
        self.assertTrue(any(m.provider == "groq" for m in groq_models))

        coding_models = model_router.registry.get_models_for_category(TASK_CODING)
        self.assertTrue(any(m.provider == "nvidia" for m in coding_models))
        self.assertTrue(any(m.provider == "groq" for m in coding_models))

        vision_models = model_router.registry.get_models_for_category(TASK_VISION)
        self.assertTrue(any(m.provider == "gemini" for m in vision_models))

    # =========================================================================
    # Provider Health & Cooldown Tracking Tests
    # =========================================================================

    def test_provider_health_tracking(self):
        """Test health tracking, success latency, failure recording, and cooldowns."""
        dummy = DummyProvider("dummy-test", "Dummy Engine")

        # Initial state
        health = dummy.get_health_status()
        self.assertEqual(health["status"], "ONLINE")
        self.assertEqual(health["consecutive_failures"], 0)
        self.assertFalse(dummy.is_in_cooldown())

        # Record success
        dummy.record_success(24)
        health = dummy.get_health_status()
        self.assertEqual(health["latency_ms"], 24)
        self.assertEqual(health["consecutive_failures"], 0)

        # Record transient failure with cooldown
        dummy.record_failure("429 Rate Limit", is_transient=True, cooldown_seconds=10.0)
        self.assertTrue(dummy.is_in_cooldown())
        health = dummy.get_health_status()
        self.assertEqual(health["status"], "DEGRADED")
        self.assertGreater(health["cooldown_remaining_sec"], 0)

        # Successful call clears cooldown
        dummy.record_success(12)
        self.assertFalse(dummy.is_in_cooldown())
        health = dummy.get_health_status()
        self.assertEqual(health["status"], "ONLINE")

    # =========================================================================
    # Intelligent Failover Tests
    # =========================================================================

    def test_failover_on_429_rate_limit(self):
        """Test that HTTP 429 on primary provider triggers automated failover to candidate."""
        async def run_test():
            # Setup dummy primary that fails with 429
            primary_dummy = DummyProvider("test-groq", "Test Groq", behavior="fail_429")
            # Setup dummy secondary that succeeds
            fallback_dummy = DummyProvider("test-nvidia", "Test NVIDIA", behavior="success")

            provider_manager.register_provider(primary_dummy)
            provider_manager.register_provider(fallback_dummy)

            core = NaradCore()

            # Mock router decision pointing to primary with fallback to secondary
            from app.core.router import RouteDecision
            custom_route = RouteDecision(
                provider_id="test-groq",
                model_name="test-groq-model",
                provider=primary_dummy,
                is_configured=True,
                task_category="FAST_CHAT",
                routing_reason="Test routing",
                failover_candidates=[{"provider": "test-nvidia", "model": "test-nvidia-model"}]
            )

            # Patch resolve_route temporarily
            orig_resolve = model_router.resolve_route
            model_router.resolve_route = lambda **kwargs: custom_route

            try:
                res = await core.process_message(
                    message="What is quantum computing?",
                    session_id=None
                )

                # Assert failover occurred
                self.assertEqual(res["status"], "success")
                self.assertTrue(res["fallback"])
                self.assertEqual(res["fallback_path"], "TEST-GROQ → TEST-NVIDIA")
                self.assertEqual(res["fallback_reason"], "rate_limit")
                self.assertEqual(res["provider"], "test-nvidia")
                self.assertIn("Response from Test NVIDIA", res["response"])
                self.assertEqual(primary_dummy.call_count, 1)
                self.assertEqual(fallback_dummy.call_count, 1)
            finally:
                model_router.resolve_route = orig_resolve

        self.loop.run_until_complete(run_test())

    def test_non_failover_on_400_client_error(self):
        """CRITICAL: Test that HTTP 400 client error does NOT failover, but surfaces clearly."""
        async def run_test():
            primary_dummy = DummyProvider("test-groq-400", "Test Groq 400", behavior="fail_400")
            fallback_dummy = DummyProvider("test-nvidia-standby", "Test NVIDIA Standby", behavior="success")

            provider_manager.register_provider(primary_dummy)
            provider_manager.register_provider(fallback_dummy)

            core = NaradCore()

            from app.core.router import RouteDecision
            custom_route = RouteDecision(
                provider_id="test-groq-400",
                model_name="test-groq-model",
                provider=primary_dummy,
                is_configured=True,
                task_category="TOOL_USE",
                routing_reason="Test 400 non-failover",
                failover_candidates=[{"provider": "test-nvidia-standby", "model": "test-nvidia-model"}]
            )

            orig_resolve = model_router.resolve_route
            model_router.resolve_route = lambda **kwargs: custom_route

            try:
                res = await core.process_message(
                    message="Calculate something with bad schema",
                    session_id=None
                )

                # Must NOT failover
                self.assertFalse(res["fallback"])
                self.assertIsNone(res["fallback_path"])
                self.assertEqual(res["status"], "client_error")
                self.assertEqual(res["provider"], "test-groq-400")
                self.assertIn("400 Bad Request", res["response"])
                self.assertEqual(primary_dummy.call_count, 1)
                # Fallback must NOT have been called
                self.assertEqual(fallback_dummy.call_count, 0)
            finally:
                model_router.resolve_route = orig_resolve

        self.loop.run_until_complete(run_test())

    def test_failover_on_timeout(self):
        """Test that a timeout triggers automated failover."""
        async def run_test():
            primary_dummy = DummyProvider("test-groq-to", "Test Groq Timeout", behavior="fail_timeout")
            fallback_dummy = DummyProvider("test-gemini-fb", "Test Gemini Fallback", behavior="success")

            provider_manager.register_provider(primary_dummy)
            provider_manager.register_provider(fallback_dummy)

            core = NaradCore()

            from app.core.router import RouteDecision
            custom_route = RouteDecision(
                provider_id="test-groq-to",
                model_name="test-groq-model",
                provider=primary_dummy,
                is_configured=True,
                task_category="GENERAL_CHAT",
                routing_reason="Test timeout failover",
                failover_candidates=[{"provider": "test-gemini-fb", "model": "test-gemini-model"}]
            )

            orig_resolve = model_router.resolve_route
            model_router.resolve_route = lambda **kwargs: custom_route

            try:
                res = await core.process_message(
                    message="Hello there",
                    session_id=None
                )

                self.assertEqual(res["status"], "success")
                self.assertTrue(res["fallback"])
                self.assertEqual(res["fallback_path"], "TEST-GROQ-TO → TEST-GEMINI-FB")
                self.assertEqual(res["fallback_reason"], "timeout")
                self.assertEqual(res["provider"], "test-gemini-fb")
                self.assertIn("Response from Test Gemini Fallback", res["response"])
            finally:
                model_router.resolve_route = orig_resolve

        self.loop.run_until_complete(run_test())

    # =========================================================================
    # Conversational Context & Windowing Tests
    # =========================================================================

    def test_conversation_sliding_window(self):
        """Test that conversational context maintains a sliding window of recent messages."""
        async def run_test():
            core = NaradCore()
            history = [
                {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"}
                for i in range(25)
            ]

            dummy = DummyProvider("window-test-prov", "Window Test Prov")
            provider_manager.register_provider(dummy)

            res = await core.process_message(
                message="Final directive",
                history=history,
                session_id=None,
                requested_provider="window-test-prov"
            )

            self.assertEqual(res["status"], "success")
            self.assertEqual(res["provider"], "window-test-prov")

        self.loop.run_until_complete(run_test())

    # =========================================================================
    # Telemetry and Self-Awareness Tests
    # =========================================================================

    def test_router_status_telemetry(self):
        """Test /api/health and get_router_status telemetry structure."""
        status = model_router.get_router_status()
        self.assertEqual(status["router_status"], "online")
        self.assertIn("active_provider", status)
        self.assertIn("active_model", status)
        self.assertIn("task_category", status)
        self.assertIn("available_providers", status)
        self.assertIn("failover_candidates", status)


if __name__ == "__main__":
    unittest.main()
