"""
NARAD Phase 2 — Local-Only Routing Test Suite.

Verifies the deterministic execution-constraint layer that runs
BEFORE task classification and BEFORE provider selection.

TEST A: "Answer using local-only inference." → LOCAL_ONLY + ollama + local
TEST B: "Answer offline." → LOCAL_ONLY + Ollama
TEST C: "Do not use cloud. Explain neural networks." → LOCAL_ONLY + Ollama
TEST D: "Normal chat question." → existing intelligent routing (no constraint)
TEST E: Ollama down + "Answer locally only." → controlled error, NO cloud fallback
TEST F: "Use cloud." → CLOUD_ONLY / remote provider
"""

import pytest
from unittest.mock import patch, AsyncMock, PropertyMock

from app.core.router import model_router, TASK_GENERAL_CHAT
from app.core.provider_truth import (
    detect_execution_constraint,
    is_local_provider,
    EXECUTION_LOCAL_ONLY,
    EXECUTION_CLOUD_ONLY,
    CLOUD_PROVIDERS,
    LOCAL_PROVIDERS,
    LOCAL_INFERENCE_PROVIDERS,
)
from app.providers.manager import provider_manager
from app.core.narad import narad_core


# ==============================================================================
# TEST A: "Answer using local-only inference." → LOCAL_ONLY + ollama + local
# ==============================================================================
@pytest.mark.asyncio
async def test_a_local_only_inference_routes_to_ollama():
    """
    Test A: Input "Answer using local-only inference."
    Expected:
      - execution_constraint == LOCAL_ONLY
      - provider == ollama
      - execution_mode == local
      - No cloud providers in failover chain
    """
    message = "NARAD, answer this using local-only inference. What is 2+2?"

    # 1. Constraint detection
    constraint = detect_execution_constraint(message)
    assert constraint == EXECUTION_LOCAL_ONLY

    # 2. Router resolve
    decision = model_router.resolve_route(message=message)
    assert decision.provider_id == "ollama"
    assert decision.execution_mode == "local"
    assert decision.execution == "local"
    assert decision.execution_constraint == EXECUTION_LOCAL_ONLY
    assert "LOCAL_ONLY" in decision.routing_reason
    # Verify NO cloud providers in failover chain
    for candidate in decision.failover_candidates:
        assert candidate["provider"] not in CLOUD_PROVIDERS, \
            f"Cloud provider '{candidate['provider']}' must NOT be in LOCAL_ONLY failover chain"

    # 3. NaradCore process_message
    ollama_prov = provider_manager.get_provider("ollama")
    mock_response = {
        "content": "2+2 equals 4.",
        "provider": "ollama",
        "model": "qwen3.5:0.8b",
        "latency_ms": 30,
        "status": "success",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}
    }
    with patch.object(ollama_prov, "is_configured", return_value=True), \
         patch.object(ollama_prov, "generate_response", new=AsyncMock(return_value=mock_response)):
        res = await narad_core.process_message(message)

        assert res["provider"] == "ollama"
        assert res["execution_mode"] == "local"
        assert res["execution"] == "local"
        assert res["execution_constraint"] == "LOCAL_ONLY"
        assert res["status"] == "success"
        assert res["fallback_used"] is False


# ==============================================================================
# TEST B: "Answer offline." → LOCAL_ONLY + Ollama
# ==============================================================================
@pytest.mark.asyncio
async def test_b_answer_offline_routes_to_ollama():
    """
    Test B: Input "Answer offline."
    Expected: LOCAL_ONLY + Ollama
    """
    message = "Answer offline."

    constraint = detect_execution_constraint(message)
    assert constraint == EXECUTION_LOCAL_ONLY

    decision = model_router.resolve_route(message=message)
    assert decision.provider_id == "ollama"
    assert decision.execution_mode == "local"
    assert decision.execution_constraint == EXECUTION_LOCAL_ONLY

    # Verify no cloud providers in failover
    for candidate in decision.failover_candidates:
        assert candidate["provider"] not in CLOUD_PROVIDERS


# ==============================================================================
# TEST C: "Do not use cloud. Explain neural networks." → LOCAL_ONLY + Ollama
# ==============================================================================
@pytest.mark.asyncio
async def test_c_do_not_use_cloud_routes_to_ollama():
    """
    Test C: Input "Do not use cloud. Explain neural networks."
    Expected: LOCAL_ONLY + Ollama
    This tests that LOCAL_ONLY constraint overrides what would
    normally be classified as GENERAL_CHAT routed to Groq.
    """
    message = "Do not use cloud. Explain neural networks."

    constraint = detect_execution_constraint(message)
    assert constraint == EXECUTION_LOCAL_ONLY

    decision = model_router.resolve_route(message=message)
    assert decision.provider_id == "ollama"
    assert decision.execution_mode == "local"
    assert decision.execution_constraint == EXECUTION_LOCAL_ONLY
    # Crucially, this must NOT route to groq
    assert decision.provider_id != "groq"
    # Verify no cloud providers in failover
    for candidate in decision.failover_candidates:
        assert candidate["provider"] not in CLOUD_PROVIDERS


# ==============================================================================
# TEST D: "Normal chat question." → existing intelligent routing (no constraint)
# ==============================================================================
def test_d_normal_chat_uses_standard_routing():
    """
    Test D: Input "Normal chat question."
    Expected: No execution constraint, standard intelligent routing.
    """
    message = "What is the capital of France?"

    constraint = detect_execution_constraint(message)
    assert constraint is None

    decision = model_router.resolve_route(message=message)
    # Should use normal routing — no constraint forced
    assert decision.execution_constraint is None
    # Should route via standard GENERAL_CHAT → likely groq or configured default
    assert decision.provider_id in ("groq", "nvidia", "openrouter", "gemini", "ollama", "huggingface")


# ==============================================================================
# TEST E: Ollama down + "Answer locally only." → controlled error, NO cloud fallback
# ==============================================================================
@pytest.mark.asyncio
async def test_e_ollama_down_local_only_returns_error_no_cloud_fallback():
    """
    Test E: Stop Ollama + Input "Answer locally only."
    Expected:
      - Controlled local-provider-unavailable error.
      - ABSOLUTELY NO Groq/NVIDIA/Gemini/OpenRouter fallback.
    """
    message = "Answer locally only."

    constraint = detect_execution_constraint(message)
    assert constraint == EXECUTION_LOCAL_ONLY

    ollama_prov = provider_manager.get_provider("ollama")
    hf_prov = provider_manager.get_provider("huggingface")
    groq_prov = provider_manager.get_provider("groq")

    groq_mock = AsyncMock()
    nvidia_mock = AsyncMock()
    gemini_mock = AsyncMock()
    openrouter_mock = AsyncMock()

    with patch.object(ollama_prov, "is_configured", return_value=False), \
         patch.object(hf_prov, "is_configured", return_value=False), \
         patch.object(groq_prov, "generate_response", new=groq_mock), \
         patch.object(provider_manager.get_provider("nvidia"), "generate_response", new=nvidia_mock), \
         patch.object(provider_manager.get_provider("gemini"), "generate_response", new=gemini_mock), \
         patch.object(provider_manager.get_provider("openrouter"), "generate_response", new=openrouter_mock):

        # Router decision should report unavailable
        decision = model_router.resolve_route(message=message)
        assert decision.is_configured is False
        assert decision.execution_constraint == EXECUTION_LOCAL_ONLY
        assert "LOCAL_ONLY" in decision.routing_reason

        # NaradCore should return controlled error
        res = await narad_core.process_message(message)
        assert res["status"] == "local_provider_unavailable"
        assert res["execution_constraint"] == "LOCAL_ONLY"
        assert "LOCAL_ONLY" in res["route_reason"]

        # Cloud providers MUST NOT have been called
        groq_mock.assert_not_called()
        nvidia_mock.assert_not_called()
        gemini_mock.assert_not_called()
        openrouter_mock.assert_not_called()


# ==============================================================================
# TEST F: "Use cloud." → CLOUD_ONLY / remote provider
# ==============================================================================
def test_f_use_cloud_routes_to_cloud_provider():
    """
    Test F: Input "Use cloud."
    Expected: CLOUD_ONLY constraint + remote provider.
    """
    message = "Use cloud. Tell me a joke."

    constraint = detect_execution_constraint(message)
    assert constraint == EXECUTION_CLOUD_ONLY

    decision = model_router.resolve_route(message=message)
    assert decision.provider_id in CLOUD_PROVIDERS
    assert decision.execution_mode == "cloud"
    assert decision.execution_constraint == EXECUTION_CLOUD_ONLY


# ==============================================================================
# Additional phrase coverage tests
# ==============================================================================
class TestLocalOnlyPhraseCoverage:
    """Verify all required LOCAL_ONLY trigger phrases are recognized."""

    @pytest.mark.parametrize("phrase,expected", [
        ("local-only", EXECUTION_LOCAL_ONLY),
        ("local only", EXECUTION_LOCAL_ONLY),
        ("offline", EXECUTION_LOCAL_ONLY),
        ("on device", EXECUTION_LOCAL_ONLY),
        ("on-device", EXECUTION_LOCAL_ONLY),
        ("without cloud", EXECUTION_LOCAL_ONLY),
        ("no cloud", EXECUTION_LOCAL_ONLY),
        ("don't use cloud", EXECUTION_LOCAL_ONLY),
        ("do not use cloud", EXECUTION_LOCAL_ONLY),
        ("without internet", EXECUTION_LOCAL_ONLY),
        ("no internet", EXECUTION_LOCAL_ONLY),
        ("use local ai", EXECUTION_LOCAL_ONLY),
        ("use ollama", EXECUTION_LOCAL_ONLY),
        ("run locally", EXECUTION_LOCAL_ONLY),
    ])
    def test_phrase_detection(self, phrase, expected):
        result = detect_execution_constraint(f"Please {phrase} to answer my question.")
        assert result == expected, f"Phrase '{phrase}' should detect as {expected}"


class TestIsLocalProvider:
    """Verify is_local_provider correctness."""

    def test_ollama_is_local(self):
        assert is_local_provider("ollama") is True

    def test_huggingface_is_local(self):
        assert is_local_provider("huggingface") is True

    def test_groq_is_not_local(self):
        assert is_local_provider("groq") is False

    def test_nvidia_is_not_local(self):
        assert is_local_provider("nvidia") is False

    def test_gemini_is_not_local(self):
        assert is_local_provider("gemini") is False

    def test_openrouter_is_not_local(self):
        assert is_local_provider("openrouter") is False

    def test_task_engine_is_local(self):
        assert is_local_provider("task-engine") is True

    def test_manthan_is_local(self):
        assert is_local_provider("manthan") is True


class TestNoConstraintNormalMessage:
    """Verify normal messages do NOT trigger execution constraints."""

    @pytest.mark.parametrize("message", [
        "What is Python?",
        "Tell me a joke",
        "Write a function in Rust",
        "Hello NARAD",
        "How does machine learning work?",
    ])
    def test_no_constraint_for_normal_message(self, message):
        result = detect_execution_constraint(message)
        assert result is None, f"Normal message '{message}' should not trigger any constraint"


# ==============================================================================
# TEST 4: "Use Ollama to explain recursion." → LOCAL_ONLY + Ollama
# ==============================================================================
def test_4_use_ollama_routes_to_ollama():
    """
    Test 4: Input "Use Ollama to explain recursion."
    Expected: LOCAL_ONLY (because 'use ollama' is a LOCAL_ONLY trigger), provider=ollama.
    """
    message = "Use Ollama to explain recursion."
    constraint = detect_execution_constraint(message)
    assert constraint == EXECUTION_LOCAL_ONLY

    decision = model_router.resolve_route(message=message)
    assert decision.provider_id == "ollama"
    assert decision.execution_mode == "local"
    assert decision.execution_constraint == EXECUTION_LOCAL_ONLY


# ==============================================================================
# TEST 8: Contradictory: "offline but use Groq" → LOCAL_ONLY wins (safety-first)
# ==============================================================================
@pytest.mark.asyncio
async def test_8_contradictory_constraint_local_wins():
    """
    Test 8: Input "offline but use Groq"
    LOCAL_ONLY is detected first (safety-first principle) → overrides cloud intent.
    Expected:
      - execution_constraint == LOCAL_ONLY
      - provider == ollama (not groq)
      - Groq MUST NOT be called
    """
    message = "Answer offline but use Groq for speed."

    constraint = detect_execution_constraint(message)
    # LOCAL_ONLY takes priority because 'offline' is checked before 'use groq'
    assert constraint == EXECUTION_LOCAL_ONLY

    decision = model_router.resolve_route(message=message)
    assert decision.provider_id == "ollama"
    assert decision.execution_mode == "local"
    assert decision.execution_constraint == EXECUTION_LOCAL_ONLY
    assert decision.provider_id != "groq"

    # Groq must NOT be called via narad_core
    groq_prov = provider_manager.get_provider("groq")
    groq_mock = AsyncMock()
    ollama_prov = provider_manager.get_provider("ollama")
    mock_response = {
        "content": "Recursion answer.",
        "provider": "ollama",
        "model": "qwen3.5:0.8b",
        "latency_ms": 35,
        "status": "success",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}
    }
    with patch.object(ollama_prov, "is_configured", return_value=True), \
         patch.object(ollama_prov, "generate_response", new=AsyncMock(return_value=mock_response)), \
         patch.object(groq_prov, "generate_response", new=groq_mock):
        res = await narad_core.process_message(message)
        assert res["provider"] == "ollama"
        assert res["execution_constraint"] == "LOCAL_ONLY"
        groq_mock.assert_not_called()


# ==============================================================================
# TEST 9: Telemetry verification — LOCAL_ONLY telemetry fields
# ==============================================================================
@pytest.mark.asyncio
async def test_9_local_only_telemetry_fields():
    """
    Test 9: Verify that LOCAL_ONLY requests produce complete telemetry:
      MODE = LOCAL ONLY
      PROVIDER = OLLAMA
      MODEL = actual Ollama model
      EXECUTION = LOCAL
      NETWORK = NOT USED (reflected in why_this_choice)
    """
    message = "Answer using local-only inference. What is 1+1?"

    ollama_prov = provider_manager.get_provider("ollama")
    mock_response = {
        "content": "1+1 equals 2.",
        "provider": "ollama",
        "model": "qwen3.5:0.8b",
        "latency_ms": 25,
        "status": "success",
        "usage": {"prompt_tokens": 8, "completion_tokens": 4}
    }
    with patch.object(ollama_prov, "is_configured", return_value=True), \
         patch.object(ollama_prov, "generate_response", new=AsyncMock(return_value=mock_response)):
        res = await narad_core.process_message(message)

        # Execution constraint
        assert res["execution_constraint"] == "LOCAL_ONLY"
        # Provider
        assert res["provider"] == "ollama"
        # Model
        assert res["model"] == "qwen3.5:0.8b"
        # Execution mode
        assert res["execution_mode"] == "local"
        assert res["execution"] == "local"
        # Endpoint
        assert "11434" in res["endpoint"]
        assert "127.0.0.1" in res["endpoint"] or "localhost" in res["endpoint"]
        # Network not used (reflected in why_this_choice)
        assert "NOT USED" in res["why_this_choice"] or "local" in res["why_this_choice"].lower()
        # Latency is recorded (may be 0ms in fast test execution)
        assert res["latency_ms"] >= 0
        # Fallback not used
        assert res["fallback_used"] is False
        # Status
        assert res["status"] == "success"


# ==============================================================================
# TEST 11: Network safety — mock/spy ALL cloud provider clients
# ==============================================================================
@pytest.mark.asyncio
async def test_11_network_safety_no_cloud_calls_under_local_only():
    """
    Test 11: Run a LOCAL_ONLY request and verify via mocks/spies that:
      Groq call count = 0
      NVIDIA call count = 0
      Gemini call count = 0
      OpenRouter call count = 0
    The only allowed inference call is a verified local provider (Ollama).
    """
    message = "Run locally. Explain what an API is."

    ollama_prov = provider_manager.get_provider("ollama")
    groq_prov = provider_manager.get_provider("groq")
    nvidia_prov = provider_manager.get_provider("nvidia")
    gemini_prov = provider_manager.get_provider("gemini")
    openrouter_prov = provider_manager.get_provider("openrouter")

    groq_spy = AsyncMock()
    nvidia_spy = AsyncMock()
    gemini_spy = AsyncMock()
    openrouter_spy = AsyncMock()

    mock_response = {
        "content": "An API is an Application Programming Interface.",
        "provider": "ollama",
        "model": "qwen3.5:0.8b",
        "latency_ms": 40,
        "status": "success",
        "usage": {"prompt_tokens": 12, "completion_tokens": 8}
    }

    with patch.object(ollama_prov, "is_configured", return_value=True), \
         patch.object(ollama_prov, "generate_response", new=AsyncMock(return_value=mock_response)), \
         patch.object(groq_prov, "generate_response", new=groq_spy), \
         patch.object(nvidia_prov, "generate_response", new=nvidia_spy), \
         patch.object(gemini_prov, "generate_response", new=gemini_spy), \
         patch.object(openrouter_prov, "generate_response", new=openrouter_spy):

        res = await narad_core.process_message(message)

        assert res["provider"] == "ollama"
        assert res["execution_constraint"] == "LOCAL_ONLY"
        assert res["status"] == "success"

        # CRITICAL: zero cloud provider calls
        groq_spy.assert_not_called()
        nvidia_spy.assert_not_called()
        gemini_spy.assert_not_called()
        openrouter_spy.assert_not_called()

