"""
NARAD Phase 2 — Provider Truth / Anti-Hallucination Automated Test Suite.

Verifies:
A. Ollama request reports:
   - OLLAMA // LOCAL
   - qwen3.5:0.8b
B. Groq request reports:
   - GROQ // CLOUD
   - actual Groq model
C. Offline mode never calls a cloud provider.
D. Provider explanation cannot claim Groq is local.
E. Actual router metadata and displayed metadata must match.
"""

import pytest
from unittest.mock import patch, AsyncMock

from app.core.router import model_router, TASK_FAST_CHAT, TASK_REASONING, TASK_LOCAL_FAST, TASK_GENERAL_CHAT
from app.core.provider_truth import (
    validate_execution_mode,
    get_provider_endpoint,
    get_provider_display_label,
    generate_why_this_choice,
    MODE_LOCAL,
    MODE_CLOUD,
    CLOUD_PROVIDERS,
    LOCAL_PROVIDERS,
)
from app.providers.manager import provider_manager
from app.core.narad import narad_core
from app.services.connectivity import connectivity_service


# ==============================================================================
# TEST A: Ollama request reports OLLAMA // LOCAL and qwen3.5:0.8b
# ==============================================================================
@pytest.mark.asyncio
async def test_a_ollama_request_reports_local_and_qwen():
    """
    Test A: Ollama request reports:
    - OLLAMA // LOCAL
    - qwen3.5:0.8b
    - execution_mode = local
    - endpoint = http://127.0.0.1:11434
    """
    decision = model_router.resolve_route(requested_provider="ollama")

    assert decision.provider_id == "ollama"
    assert decision.execution_mode == "local"
    assert decision.execution == "local"
    assert "11434" in decision.endpoint
    assert "127.0.0.1" in decision.endpoint or "localhost" in decision.endpoint
    assert decision.display_label == "OLLAMA // LOCAL"
    assert "qwen3.5:0.8b" in decision.model_name

    # Test processing message via narad_core with mocked provider response
    ollama_prov = provider_manager.get_provider("ollama")
    mock_success = {
        "content": "This is a local response from Ollama.",
        "provider": "ollama",
        "model": "qwen3.5:0.8b",
        "latency_ms": 42,
        "status": "success",
        "usage": {"prompt_tokens": 10, "completion_tokens": 8}
    }

    with patch.object(ollama_prov, "is_configured", return_value=True), \
         patch.object(ollama_prov, "generate_response", new=AsyncMock(return_value=mock_success)):
        res = await narad_core.process_message("Test query for local", requested_provider="ollama")

        assert res["provider"] == "ollama"
        assert res["model"] == "qwen3.5:0.8b"
        assert res["execution_mode"] == "local"
        assert res["execution"] == "local"
        assert "11434" in res["endpoint"]
        assert res["status"] == "success"
        assert res["fallback_used"] is False
        assert "localhost:11434" in res["why_this_choice"] or "local" in res["why_this_choice"].lower()


# ==============================================================================
# TEST B: Groq request reports GROQ // CLOUD and actual Groq model
# ==============================================================================
@pytest.mark.asyncio
async def test_b_groq_request_reports_cloud_and_actual_model():
    """
    Test B: Groq request reports:
    - GROQ // CLOUD
    - actual Groq model (e.g. openai/gpt-oss-120b)
    - execution_mode = cloud
    - endpoint = https://api.groq.com/openai/v1
    """
    decision = model_router.resolve_route(requested_provider="groq")

    assert decision.provider_id == "groq"
    assert decision.execution_mode == "cloud"
    assert decision.execution == "cloud"
    assert decision.endpoint == "https://api.groq.com/openai/v1"
    assert decision.display_label == "GROQ // CLOUD"
    assert decision.model_name in ("openai/gpt-oss-120b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant")

    # Test processing message via narad_core
    groq_prov = provider_manager.get_provider("groq")
    mock_success = {
        "content": "This is a cloud synthesis from Groq LPU.",
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
        "latency_ms": 115,
        "status": "success",
        "usage": {"prompt_tokens": 15, "completion_tokens": 12}
    }

    with patch.object(groq_prov, "is_configured", return_value=True), \
         patch.object(groq_prov, "generate_response", new=AsyncMock(return_value=mock_success)):
        res = await narad_core.process_message("Test query for cloud", requested_provider="groq")

        assert res["provider"] == "groq"
        assert res["model"] == "openai/gpt-oss-120b"
        assert res["execution_mode"] == "cloud"
        assert res["execution"] == "cloud"
        assert res["endpoint"] == "https://api.groq.com/openai/v1"
        assert res["status"] == "success"
        assert res["fallback_used"] is False
        assert "cloud" in res["why_this_choice"].lower()
        assert "groq cloud lpu" in res["why_this_choice"].lower()


# ==============================================================================
# TEST C: Offline mode never calls a cloud provider
# ==============================================================================
@pytest.mark.asyncio
async def test_c_offline_mode_never_calls_cloud_provider():
    """
    Test C: Offline mode:
    - Automatically restricts selection to verified local providers only
    - Reject Groq/NVIDIA/Gemini/OpenRouter
    - Never calls Groq API or falls back to cloud
    - Clearly reports LOCAL/OFFLINE
    """
    groq_prov = provider_manager.get_provider("groq")
    groq_mock = AsyncMock()

    with patch.object(connectivity_service, "is_online", return_value=False), \
         patch.object(groq_prov, "generate_response", new=groq_mock):

        # 1. Automatic routing in offline mode
        auto_decision = model_router.resolve_route(message="Tell me a joke")
        assert auto_decision.execution_mode == "local"
        assert auto_decision.provider_id in ("ollama", "huggingface", "mock-narad")
        # Ensure no cloud providers in failover chain
        for candidate in auto_decision.failover_candidates:
            assert candidate["provider"] in ("ollama", "huggingface", "mock-narad")
            assert candidate["provider"] not in CLOUD_PROVIDERS

        # 2. Explicit request for Groq in offline mode MUST be rejected
        explicit_decision = model_router.resolve_route(requested_provider="groq")
        assert explicit_decision.is_configured is False
        assert "offline" in explicit_decision.routing_reason.lower()
        assert explicit_decision.failover_candidates == []

        # 3. Processing message via narad_core with explicit Groq request while offline
        res = await narad_core.process_message("Compute this in groq", requested_provider="groq")

        # Groq API MUST NOT have been called
        groq_mock.assert_not_called()

        assert res["status"] == "offline_rejected"
        assert "offline" in res["response"].lower()
        assert res["execution_mode"] == "cloud"
        assert res["route_reason"] == "LOCAL/OFFLINE"
        assert res["fallback_used"] is False


# ==============================================================================
# TEST D: Provider explanation cannot claim Groq is local
# ==============================================================================
def test_d_provider_explanation_cannot_claim_groq_is_local():
    """
    Test D: Provider explanation cannot claim Groq is local:
    - Hard validation layer forces Groq execution_mode to 'cloud'
    - generate_why_this_choice explicitly identifies Groq as a remote cloud provider
    - Prohibits descriptions of Groq as local accelerator or on-device runtime
    """
    # 1. Hard validation layer enforcement
    forced_mode = validate_execution_mode("groq", proposed_mode="local")
    assert forced_mode == "cloud", "Hard validation layer must forbid Groq from being marked local."

    for cp in CLOUD_PROVIDERS:
        assert validate_execution_mode(cp, proposed_mode="local") == "cloud"

    # 2. Explanation generator enforcement
    why_groq = generate_why_this_choice(
        provider_id="groq",
        model_name="openai/gpt-oss-120b",
        task_category=TASK_FAST_CHAT,
        execution_mode="local"  # Caller attempts to pass local
    )

    # Explanation must strictly state it is a remote cloud provider
    assert "remote cloud provider" in why_groq.lower()
    assert "groq cloud lpu api" in why_groq.lower()
    assert "local accelerator" not in why_groq.lower()
    assert "on-device" not in why_groq.lower()
    assert "localhost" not in why_groq.lower()
    assert "private local" not in why_groq.lower()

    # 3. RouteDecision dataclass post-init enforcement
    groq_prov = provider_manager.get_provider("groq")
    decision = model_router.resolve_route(requested_provider="groq")
    assert decision.execution_mode == "cloud"
    assert "local accelerator" not in decision.why_this_choice.lower()
    assert "on-device" not in decision.why_this_choice.lower()
    assert decision.display_label == "GROQ // CLOUD"


# ==============================================================================
# TEST E: Actual router metadata and displayed metadata must match
# ==============================================================================
@pytest.mark.asyncio
async def test_e_router_metadata_and_displayed_metadata_match():
    """
    Test E: Actual router metadata and displayed metadata must match:
    - decision.provider_id == response['provider']
    - decision.model_name == response['model']
    - decision.execution_mode == response['execution_mode']
    - decision.endpoint == response['endpoint']
    - decision.routing_reason / category matches
    """
    test_cases = [
        ("ollama", "qwen3.5:0.8b", "local", "http://127.0.0.1:11434"),
        ("groq", "openai/gpt-oss-120b", "cloud", "https://api.groq.com/openai/v1"),
    ]

    for pid, model, expected_mode, expected_endpoint in test_cases:
        prov = provider_manager.get_provider(pid)
        mock_res = {
            "content": f"Test answer from {pid}",
            "provider": pid,
            "model": model,
            "latency_ms": 50,
            "status": "success",
            "usage": {"prompt_tokens": 10, "completion_tokens": 10}
        }

        with patch.object(prov, "is_configured", return_value=True), \
             patch.object(prov, "generate_response", new=AsyncMock(return_value=mock_res)):

            msg = f"Say hello from {pid}"
            decision = model_router.resolve_route(requested_provider=pid, requested_model=model, message=msg)
            response = await narad_core.process_message(msg, requested_provider=pid, requested_model=model)

            # Assert exact match between router decision and user-facing response metadata
            assert decision.provider_id == response["provider"] == pid
            assert decision.model_name == response["model"] == model
            assert decision.execution_mode == response["execution_mode"] == expected_mode
            assert response["execution"] == expected_mode
            assert decision.endpoint == response["endpoint"]
            assert response["endpoint"] == expected_endpoint
            assert response["latency_ms"] > 0
            assert response["latency"] == response["latency_ms"]
            assert response["why_this_choice"] == decision.why_this_choice
            assert response["fallback_used"] == decision.fallback_used

            # Verify Pydantic ChatResponse model compatibility
            from app.api.routes.chat import ChatResponse
            chat_resp = ChatResponse(
                response=response["response"],
                provider=response["provider"],
                model=response["model"],
                execution_mode=response["execution_mode"],
                execution=response["execution"],
                endpoint=response["endpoint"],
                latency_ms=response["latency_ms"],
                latency=response["latency"],
                status=response["status"],
                chat_id="test_chat_id",
                fallback=response["fallback"],
                fallback_used=response["fallback_used"],
                route_reason=response["route_reason"],
                why_this_choice=response["why_this_choice"]
            )
            assert chat_resp.provider == decision.provider_id
            assert chat_resp.execution_mode == decision.execution_mode
            assert chat_resp.endpoint == decision.endpoint
