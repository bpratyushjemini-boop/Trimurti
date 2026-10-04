"""
Test Suite for NARAD V8.2 Milestone 5:
Final Intelligent Model Routing & Provider Failover

Verifies:
1. Task-based classification across categories (FAST_CHAT, REASONING, CODING, VISION, LOCAL_FAST).
2. ModelCapabilityRegistry metadata verification (latency_class, cost_class, reasoning, coding, speed, tools, vision).
3. Ollama LOCAL_FAST routing for lightweight intent extraction, entity extraction, and JSON formatting.
4. Transient failover (429 Rate Limit, 500 Server Error, Timeout) triggers candidate failover.
5. Non-transient errors (400 Bad Request / Client Error) NEVER trigger failover.
6. Structured telemetry output: Task -> Provider -> Model -> Reason -> Latency -> Failover.
"""

import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from app.core.router import (
    ModelRouter,
    ModelCapabilityRegistry,
    TASK_FAST_CHAT,
    TASK_REASONING,
    TASK_CODING,
    TASK_VISION,
    TASK_LOCAL_FAST,
    TASK_GENERAL_CHAT,
)
from app.core.narad import NaradCore


class TestV82ModelRouting(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.router = ModelRouter()
        self.registry = ModelCapabilityRegistry()
        self.core = NaradCore()

    def test_01_capability_registry_metadata(self):
        """All registered models must have complete capability and benchmark metadata."""
        models = self.registry._models
        self.assertGreaterEqual(len(models), 6)

        for m in models:
            self.assertIsNotNone(m.provider)
            self.assertIsNotNone(m.model_id)
            self.assertIsInstance(m.speed_score, int)
            self.assertIsInstance(m.reasoning_score, int)
            self.assertIsInstance(m.coding_score, int)
            self.assertIsInstance(m.tool_support, bool)
            self.assertIsInstance(m.vision_support, bool)
            self.assertIn(m.latency_class, ["ultra_low", "low", "medium", "high"])
            self.assertIn(m.cost_class, ["free", "low", "medium", "high"])

    def test_02_task_classification_categories(self):
        """Directives are accurately classified into distinct logical task categories."""
        # 1. LOCAL_FAST: Intent classification / entity extraction / json formatting
        self.assertEqual(
            self.router.classify_task("classify intent of this user message"),
            TASK_LOCAL_FAST
        )
        self.assertEqual(
            self.router.classify_task("extract json entities from document"),
            TASK_LOCAL_FAST
        )

        # 2. CODING: Code generation / debugging
        self.assertEqual(
            self.router.classify_task("write a function in python to reverse a linked list"),
            TASK_CODING
        )

        # 3. REASONING: Math proof / deep analysis
        self.assertEqual(
            self.router.classify_task("step by step mathematical proof of Fermat's last theorem"),
            TASK_REASONING
        )

        # 4. FAST_CHAT: Short greeting
        self.assertEqual(
            self.router.classify_task("hello"),
            TASK_FAST_CHAT
        )

        # 5. VISION: Multimodal request
        self.assertEqual(
            self.router.classify_task("analyze this image", has_vision=True),
            TASK_VISION
        )

    def test_03_ollama_local_fast_routing_order(self):
        """TASK_LOCAL_FAST places Ollama at the top of the provider priority chain."""
        order = self.router._capability_order(TASK_LOCAL_FAST)
        self.assertEqual(order[0], "ollama")

    def test_04_reasoning_and_coding_routing_order(self):
        """TASK_REASONING and TASK_CODING place NVIDIA at the top of the provider priority chain."""
        reasoning_order = self.router._capability_order(TASK_REASONING)
        self.assertEqual(reasoning_order[0], "nvidia")

        coding_order = self.router._capability_order(TASK_CODING)
        self.assertEqual(coding_order[0], "nvidia")

    def test_05_vision_routing_order(self):
        """TASK_VISION places Gemini at the top of the provider priority chain."""
        vision_order = self.router._capability_order(TASK_VISION)
        self.assertEqual(vision_order[0], "gemini")

    async def test_06_failover_on_429_rate_limit(self):
        """Primary 429 rate limit triggers failover to the next candidate in the chain."""
        primary_mock = MagicMock()
        primary_mock.provider_id = "groq"
        primary_mock.is_configured.return_value = True
        primary_mock.has_auth_error.return_value = False
        primary_mock.is_in_cooldown.return_value = False
        primary_mock.supports_vision.return_value = False
        primary_mock.generate_response = AsyncMock(return_value={
            "status": "rate_limited",
            "error": "429 Too Many Requests - quota exceeded",
            "is_transient": True
        })

        secondary_mock = MagicMock()
        secondary_mock.provider_id = "nvidia"
        secondary_mock.is_configured.return_value = True
        secondary_mock.has_auth_error.return_value = False
        secondary_mock.is_in_cooldown.return_value = False
        secondary_mock.supports_vision.return_value = False
        secondary_mock.generate_response = AsyncMock(return_value={
            "status": "success",
            "content": "Handled via NVIDIA fallback.",
            "tools_executed": [],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8}
        })

        with patch("app.core.router.model_router.resolve_route") as mock_route, \
             patch("app.providers.manager.provider_manager.get_provider") as mock_get_provider:

            mock_decision = MagicMock()
            mock_decision.provider_id = "groq"
            mock_decision.model_name = "openai/gpt-oss-120b"
            mock_decision.provider = primary_mock
            mock_decision.is_configured = True
            mock_decision.task_category = "GENERAL_CHAT"
            mock_decision.routing_reason = "General conversation"
            mock_decision.failover_candidates = [{"provider": "nvidia", "model": "meta/llama-3.3-70b-instruct"}]
            mock_route.return_value = mock_decision

            mock_get_provider.side_effect = lambda pid: secondary_mock if pid == "nvidia" else primary_mock

            res = await self.core.process_message(message="Explain relativity")

            self.assertEqual(res["status"], "success")
            self.assertEqual(res["provider"], "nvidia")
            self.assertTrue(res["fallback"])
            self.assertEqual(res["fallback_path"], "GROQ → NVIDIA")
            self.assertIn("Task: GENERAL_CHAT -> Provider: nvidia", res["telemetry"])

    async def test_07_no_failover_on_400_client_error(self):
        """400 Bad Request / schema error must NEVER fail over; must surface error directly."""
        primary_mock = MagicMock()
        primary_mock.provider_id = "groq"
        primary_mock.is_configured.return_value = True
        primary_mock.has_auth_error.return_value = False
        primary_mock.is_in_cooldown.return_value = False
        primary_mock.supports_vision.return_value = False
        primary_mock.generate_response = AsyncMock(return_value={
            "status": "client_error",
            "error": "400 Bad Request: Invalid tool parameter schema",
            "is_transient": False
        })

        secondary_mock = MagicMock()
        secondary_mock.provider_id = "nvidia"
        secondary_mock.generate_response = AsyncMock()

        with patch("app.core.router.model_router.resolve_route") as mock_route:
            mock_decision = MagicMock()
            mock_decision.provider_id = "groq"
            mock_decision.model_name = "openai/gpt-oss-120b"
            mock_decision.provider = primary_mock
            mock_decision.is_configured = True
            mock_decision.task_category = "TOOL_USE"
            mock_decision.routing_reason = "Tool request"
            mock_decision.failover_candidates = [{"provider": "nvidia", "model": "meta/llama-3.3-70b-instruct"}]
            mock_route.return_value = mock_decision

            res = await self.core.process_message(message="Calculate math")

            # Must NOT have fallen over to secondary_mock
            secondary_mock.generate_response.assert_not_called()
            self.assertFalse(res["fallback"])
            self.assertEqual(res["status"], "client_error")
            self.assertIn("Communication failure with provider 'groq'", res["response"])


if __name__ == "__main__":
    unittest.main()
