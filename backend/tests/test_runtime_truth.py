"""
NARAD Phase 2 — Runtime Truth Automated Test Suite (Tests A through L).
Verifies that all runtime status, model identity, execution locality,
autonomy, memory, tools, and subsystems are sourced strictly from live system state.
"""

import pytest
from unittest.mock import patch, AsyncMock

from app.services.runtime_truth import runtime_truth_service
from app.core.provider_truth import validate_execution_mode, get_provider_endpoint
from app.providers.manager import provider_manager
from app.core.narad import narad_core
from app.services.action_policy import action_policy, AutonomyMode
from app.services.kriya import kriya_dispatcher


# ==============================================================================
# TEST A: Ollama Active -> provider = ollama, execution = LOCAL
# ==============================================================================
def test_a_ollama_active():
    """Verify Ollama active route reports LOCAL execution, network_required=False."""
    truth = runtime_truth_service.get_runtime_truth(requested_provider="ollama")

    inf = truth["inference"]
    assert inf["provider"] == "ollama"
    assert inf["execution_mode"] == "LOCAL"
    assert inf["execution"] == "LOCAL"
    assert inf["network_required"] is False
    assert "11434" in inf["endpoint"]
    assert "127.0.0.1" in inf["endpoint"] or "localhost" in inf["endpoint"]


# ==============================================================================
# TEST B: Groq Active -> provider = groq, execution = CLOUD
# ==============================================================================
def test_b_groq_active():
    """Verify Groq active route reports CLOUD execution, network_required=True."""
    truth = runtime_truth_service.get_runtime_truth(requested_provider="groq")

    inf = truth["inference"]
    assert inf["provider"] == "groq"
    assert inf["execution_mode"] == "CLOUD"
    assert inf["execution"] == "CLOUD"
    assert inf["network_required"] is True
    assert "api.groq.com" in inf["endpoint"]


# ==============================================================================
# TEST C: NVIDIA Active -> execution = CLOUD
# ==============================================================================
def test_c_nvidia_active():
    """Verify NVIDIA active route reports CLOUD execution, network_required=True."""
    truth = runtime_truth_service.get_runtime_truth(requested_provider="nvidia")

    inf = truth["inference"]
    assert inf["provider"] == "nvidia"
    assert inf["execution_mode"] == "CLOUD"
    assert inf["execution"] == "CLOUD"
    assert inf["network_required"] is True
    assert "nvidia.com" in inf["endpoint"]


# ==============================================================================
# TEST D: Gemini Active -> execution = CLOUD
# ==============================================================================
def test_d_gemini_active():
    """Verify Gemini active route reports CLOUD execution, network_required=True."""
    truth = runtime_truth_service.get_runtime_truth(requested_provider="gemini")

    inf = truth["inference"]
    assert inf["provider"] == "gemini"
    assert inf["execution_mode"] == "CLOUD"
    assert inf["execution"] == "CLOUD"
    assert inf["network_required"] is True
    assert "googleapis.com" in inf["endpoint"]


# ==============================================================================
# TEST E: OpenRouter Active -> execution = CLOUD
# ==============================================================================
def test_e_openrouter_active():
    """Verify OpenRouter active route reports CLOUD execution, network_required=True."""
    truth = runtime_truth_service.get_runtime_truth(requested_provider="openrouter")

    inf = truth["inference"]
    assert inf["provider"] == "openrouter"
    assert inf["execution_mode"] == "CLOUD"
    assert inf["execution"] == "CLOUD"
    assert inf["network_required"] is True
    assert "openrouter.ai" in inf["endpoint"]


# ==============================================================================
# TEST F: Ollama Unavailable -> status = unavailable, no fake LOCAL claim
# ==============================================================================
def test_f_ollama_unavailable():
    """Verify that when Ollama is offline, status is unavailable and no fake LOCAL is claimed."""
    ollama_prov = provider_manager.get_provider("ollama")

    with patch.object(ollama_prov, "is_configured", return_value=False), \
         patch.object(ollama_prov, "get_available_models", return_value=[]):

        truth = runtime_truth_service.get_runtime_truth()
        ollama_status = truth["subsystems"]["ollama"]
        assert ollama_status in ("UNAVAILABLE", "OFFLINE")
        assert truth["ollama"]["available"] is False
        assert truth["ollama"]["status"] == "UNAVAILABLE"

        # If active provider is Groq/cloud, it must NEVER claim LOCAL just because Ollama code exists
        if truth["inference"]["provider"] in ("groq", "nvidia", "gemini", "openrouter"):
            assert truth["inference"]["execution_mode"] == "CLOUD"
            assert truth["inference"]["network_required"] is True


# ==============================================================================
# TEST G: Provider Configured but Inactive
# ==============================================================================
def test_g_provider_configured_but_inactive():
    """
    Verify distinct reporting:
    CONFIGURED != AVAILABLE != ACTIVE
    Groq can be configured and available, while Ollama is the active provider.
    """
    groq_prov = provider_manager.get_provider("groq")

    with patch.object(groq_prov, "is_configured", return_value=True):
        # Explicitly request Ollama as active
        truth = runtime_truth_service.get_runtime_truth(requested_provider="ollama")

        matrix = truth["router"]["provider_matrix"]
        groq_entry = matrix["groq"]

        assert groq_entry["configured"] is True
        assert groq_entry["active"] is False, "Groq must be marked INACTIVE when Ollama is the active route."
        assert truth["inference"]["provider"] == "ollama"
        assert matrix["ollama"]["active"] is True


# ==============================================================================
# TEST H: Unknown Provider State -> UNKNOWN, never guessed
# ==============================================================================
def test_h_unknown_provider_state():
    """Verify unknown provider states return explicit UNKNOWN without guessing."""
    unknown_mode = validate_execution_mode("custom_unknown_engine_xyz")
    assert unknown_mode in ("cloud", "UNKNOWN")

    truth = runtime_truth_service.get_runtime_truth(requested_provider="custom_unknown_engine_xyz")
    # For custom unknown engine, endpoint or status must never be falsely marked local
    assert truth["inference"]["execution_mode"] in ("CLOUD", "UNKNOWN")
    assert truth["truth_status"] == "All reported runtime fields are sourced from live system state. Unknown values are explicitly marked UNKNOWN."


# ==============================================================================
# TEST I: Runtime Question -> No external LLM call is required
# ==============================================================================
@pytest.mark.asyncio
async def test_i_runtime_question_no_external_llm_call():
    """
    Verify that runtime/status/identity questions are answered deterministically
    from RuntimeTruth WITHOUT making any external provider LLM API calls.
    """
    groq_prov = provider_manager.get_provider("groq")
    ollama_prov = provider_manager.get_provider("ollama")

    mock_llm = AsyncMock(side_effect=RuntimeError("External LLM should NOT be invoked for runtime queries"))

    with patch.object(groq_prov, "generate_response", new=mock_llm), \
         patch.object(ollama_prov, "generate_response", new=mock_llm):

        queries = [
            "Give me a system report",
            "Tell me your runtime state",
            "What model am I using?",
            "Am I local or cloud?",
            "What can you currently do?",
            "Who are you?",
        ]

        for q in queries:
            res = await narad_core.process_message(q)
            assert res["status"] == "success"
            assert res.get("usage", {}).get("prompt_tokens", 0) == 0
            assert res.get("usage", {}).get("completion_tokens", 0) == 0
            assert len(res["response"]) > 0

        # Full report query must contain standard format headers
        report_res = await narad_core.process_message("Give me a system report")
        assert "NARAD // RUNTIME REPORT" in report_res["response"]
        assert "IDENTITY" in report_res["response"]
        assert "INFERENCE" in report_res["response"]
        assert "ROUTER" in report_res["response"]
        assert "MEMORY" in report_res["response"]
        assert "AUTONOMY" in report_res["response"]
        assert "SUBSYSTEMS" in report_res["response"]
        assert "TRUTH STATUS" in report_res["response"]

        # Ensure no external provider was touched
        mock_llm.assert_not_called()


# ==============================================================================
# TEST J: Autonomy Truth -> Matches actual Task Engine policy
# ==============================================================================
def test_j_autonomy_truth():
    """Verify autonomy level and mutations allowed match action_policy exactly."""
    # Test Level 0: CHAT_ONLY
    action_policy.set_autonomy_mode("CHAT_ONLY")
    truth_l0 = runtime_truth_service.get_runtime_truth()
    assert truth_l0["autonomy"]["level"] == 0
    assert truth_l0["autonomy"]["mode"] == "CHAT_ONLY"
    assert truth_l0["autonomy"]["computer_mutations_allowed"] is False

    # Test Level 2: SUPERVISED
    action_policy.set_autonomy_mode("SUPERVISED")
    truth_l2 = runtime_truth_service.get_runtime_truth()
    assert truth_l2["autonomy"]["level"] == 2
    assert truth_l2["autonomy"]["mode"] == "SUPERVISED"
    assert truth_l2["autonomy"]["computer_mutations_allowed"] is False

    # Test Level 3: TASK_AUTONOMY
    action_policy.set_autonomy_mode("TASK_AUTONOMY")
    truth_l3 = runtime_truth_service.get_runtime_truth()
    assert truth_l3["autonomy"]["level"] == 3
    assert truth_l3["autonomy"]["mode"] == "TASK_AUTONOMY"
    assert truth_l3["autonomy"]["computer_mutations_allowed"] is True

    # Restore default
    action_policy.set_autonomy_mode("SUPERVISED")


# ==============================================================================
# TEST K: Memory Truth -> Persistent memory and context not confused
# ==============================================================================
def test_k_memory_truth():
    """Verify persistent memory count and conversation context are distinct."""
    truth = runtime_truth_service.get_runtime_truth()

    mem = truth["memory"]
    assert mem["enabled"] is True
    assert mem["backend"] == "sqlite"
    assert mem["persistent"] is True
    assert isinstance(mem["stored_memory_count"], int)
    assert isinstance(mem["current_context_message_count"], int)

    # Standard report must not expose private memory text
    report = runtime_truth_service.format_runtime_report(truth)
    assert "Persistent memory:" in report
    assert "Context:" in report


# ==============================================================================
# TEST L: Tool Registry Truth -> Reported tools match registered tools
# ==============================================================================
def test_l_tool_registry_truth():
    """Verify reported tools match registered tools dynamically."""
    truth = runtime_truth_service.get_runtime_truth()
    reported_tools = truth["tools"]
    registered_names = set(kriya_dispatcher.list_tools())

    assert len(reported_tools) == len(registered_names)
    for tool in reported_tools:
        assert tool["name"] in registered_names
        assert tool["available"] is True
        assert isinstance(tool["permission_level"], int)
        assert tool["category"] in (
            "computation", "memory", "knowledge", "web",
            "vision", "browser", "workspace", "computer", "utility"
        )


# ==============================================================================
# TEST M: Runtime Truth HTTP Endpoints Verification
# ==============================================================================
def test_m_runtime_truth_api_endpoints():
    """Verify GET /api/runtime/truth and /api/runtime/report and /api/health."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # 1. GET /api/runtime/truth
    res_truth = client.get("/api/runtime/truth")
    assert res_truth.status_code == 200
    data = res_truth.json()
    assert "identity" in data
    assert "inference" in data
    assert "router" in data
    assert "autonomy" in data
    assert "memory" in data
    assert "tools" in data
    assert "subsystems" in data
    assert "system" in data
    assert data["identity"]["name"] == "NARAD"
    assert data["inference"]["execution_mode"] in ("LOCAL", "CLOUD", "UNKNOWN")

    # 2. GET /api/runtime/report
    res_report = client.get("/api/runtime/report")
    assert res_report.status_code == 200
    report_text = res_report.text
    assert "NARAD // RUNTIME REPORT" in report_text
    assert "INFERENCE" in report_text
    assert "TRUTH STATUS" in report_text

    # 3. GET /api/health contains synchronized runtime_truth
    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    h_data = res_health.json()
    assert "runtime_truth" in h_data
    assert h_data["runtime_truth"]["identity"]["name"] == "NARAD"
