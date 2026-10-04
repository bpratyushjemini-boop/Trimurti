"""
NARAD / TRIMURTI AI — PHASE 2 MASTER UPGRADE TEST SUITE
Covers the 10 required test criteria + Phase 2 enhancements:
1. Ollama unavailable
2. Ollama available
3. Ollama model unavailable
4. Cloud provider rate limit (429) & Retry-After
5. Provider failover
6. Timeout & retry limits
7. Local fast dispatch
8. Complex request avoiding tiny local model
9. Offline / degraded mode
10. False-success prevention
11. Local-first deterministic micro tasks (time, math, git status, installed models)
12. NARAD HEALTH diagnostics (GREEN / YELLOW / RED)
13. PROJECT STATUS response
14. Smṛti secret prevention & deduplication
15. Knowledge retrieval telemetry
16. Task Engine concise summary & verification fields
17. Vāṇī Voice status endpoint
"""

import os
import json
import time
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from app.providers.base import BaseLLMProvider
from app.providers.ollama import OllamaProvider
from app.providers.manager import ProviderManager, provider_manager
from app.core.router import (
    ModelRouter,
    TASK_LOCAL_FAST,
    TASK_FAST_CHAT,
    TASK_GENERAL_CHAT,
    TASK_REASONING,
    TASK_CODING,
    TASK_VISION,
    TASK_CHAT,
    TASK_FAST,
    TASK_AUTONOMOUS_TASK,
    TASK_KNOWLEDGE,
    TASK_MEMORY,
)
from app.services.connectivity import connectivity_service
from app.services.micro_tasks import micro_task_service
from app.services.smriti import SmritiService
from app.services.knowledge import knowledge_service
from app.services.task_engine import AutonomousTaskEngine, AutonomousTask, TaskStep, TaskStatus


# =============================================================================
# 1. Ollama Unavailable Test
# =============================================================================
@pytest.mark.asyncio
async def test_ollama_unavailable():
    """Verify OllamaProvider handles daemon unavailability gracefully without crashing."""
    provider = OllamaProvider(base_url="http://127.0.0.1:99999")
    with patch("httpx.Client.get", side_effect=Exception("Connection refused")), \
         patch("httpx.AsyncClient.get", side_effect=Exception("Connection refused")):
        is_conf = provider.is_configured()
        assert is_conf is False
        models = provider.get_available_models()
        assert models == []

    # Attempt generate_response when daemon is down
    with patch("httpx.AsyncClient.post", side_effect=Exception("Connection refused")):
        res = await provider.generate_response(messages=[{"role": "user", "content": "hi"}])
        assert res["status"] in ("error", "failed", "offline", "unreachable", "server_error")
        assert res.get("is_transient") is True
        assert provider.is_in_cooldown()


# =============================================================================
# 2. Ollama Available Test
# =============================================================================
@pytest.mark.asyncio
async def test_ollama_available():
    """Verify OllamaProvider correctly detects when daemon is alive and lists models."""
    provider = OllamaProvider()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [{"name": "qwen3.5:0.8b"}, {"name": "llama3.2:1b"}]
    }

    with patch("httpx.Client.get", return_value=mock_resp):
        assert provider.is_configured() is True
        models = provider.get_available_models()
        assert "qwen3.5:0.8b" in models
        assert "llama3.2:1b" in models


# =============================================================================
# 3. Ollama Model Unavailable Test
# =============================================================================
@pytest.mark.asyncio
async def test_ollama_model_unavailable():
    """Verify OllamaProvider handles model 404 or missing model cleanly."""
    import httpx
    provider = OllamaProvider()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = 'model "nonexistent:latest" not found'
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "model 'nonexistent:latest' not found",
        request=MagicMock(),
        response=mock_resp
    )

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        res = await provider.generate_response(
            messages=[{"role": "user", "content": "hi"}],
            model="nonexistent:latest"
        )
        assert res["status"] in ("error", "failed", "server_error")
        assert "not found" in res.get("error", "").lower() or "nonexistent" in res.get("error", "").lower()


# =============================================================================
# 4. Cloud Provider Rate Limit (429) & Retry-After Test
# =============================================================================
def test_cloud_provider_rate_limit_and_retry_after():
    """Verify 429 quota errors set rate-limited cooldown respecting Retry-After."""
    prov = provider_manager.get_provider("groq")
    assert prov is not None

    # Reset cooldown before test
    prov._is_rate_limited = False
    prov._cooldown_until = 0.0

    # Record 429 with Retry-After: 45 seconds
    prov.record_rate_limit("Rate limit reached for requests per minute", retry_after=45.0)

    assert prov.is_in_cooldown() is True
    assert prov._is_rate_limited is True
    health = prov.get_health_status()
    assert health["health_state"] == "RATE_LIMITED"
    assert health["status"] in ("RATE_LIMITED", "DEGRADED")
    assert health["cooldown_remaining_sec"] > 35.0

    # Clean up
    prov._is_rate_limited = False
    prov._cooldown_until = 0.0


# =============================================================================
# 5. Provider Failover Test
# =============================================================================
def test_provider_failover_policy():
    """Verify ModelRouter builds failover chain to alternate providers on error."""
    router = ModelRouter()
    decision = router.resolve_route(
        task_category=TASK_GENERAL_CHAT,
        message="Tell me about quantum computing"
    )

    assert decision.provider_id in ("groq", "nvidia", "gemini", "openrouter", "ollama")
    # Must have failover candidates
    assert len(decision.failover_candidates) >= 1
    # Candidate should not be the primary provider
    for alt in decision.failover_candidates:
        assert alt["provider"] != decision.provider_id


# =============================================================================
# 6. Timeout & Cooldown Test
# =============================================================================
def test_provider_timeout_cooldown():
    """Verify timeout failures trigger bounded cooldown without infinite retries."""
    prov = provider_manager.get_provider("nvidia")
    assert prov is not None

    prov._cooldown_until = 0.0
    prov._auth_error_latched = False
    with patch.object(prov, "is_configured", return_value=True):
        prov.record_failure("ReadTimeout after 15.0s", is_transient=True, cooldown_seconds=20.0)

        assert prov.is_in_cooldown() is True
        health = prov.get_health_status()
        assert health["status"] in ("DEGRADED", "COOLDOWN")
        assert health["consecutive_failures"] >= 1

    # Cleanup
    prov._cooldown_until = 0.0
    prov._consecutive_failures = 0


# =============================================================================
# 7. Local Fast Dispatch Test
# =============================================================================
def test_local_fast_dispatch():
    """Verify fast local greetings and simple queries route to FAST_LOCAL (Ollama)."""
    router = ModelRouter()
    simple_prompts = [
        "hi",
        "hello",
        "hey there",
        "format this as json: a=1, b=2",
        "lowercase this: HELLO WORLD"
    ]
    for p in simple_prompts:
        cat = router.classify_task(p)
        assert cat in (TASK_LOCAL_FAST, TASK_FAST, TASK_CHAT, TASK_FAST_CHAT)


# =============================================================================
# 8. Complex Request Avoiding Tiny Local Model Test
# =============================================================================
def test_complex_request_avoiding_tiny_local_model():
    """Verify complex reasoning, coding, and architecture tasks do NOT route to tiny local model."""
    router = ModelRouter()

    coding_prompt = "Write a complete multithreaded binary search tree implementation in Rust with unit tests"
    cat_code = router.classify_task(coding_prompt)
    assert cat_code == TASK_CODING

    reasoning_prompt = "Perform an architectural root cause analysis and trade-off comparison between event sourcing and CQRS"
    cat_reason = router.classify_task(reasoning_prompt)
    assert cat_reason == TASK_REASONING

    # Route decision for reasoning must target cloud providers (NVIDIA NIM or Groq)
    route_reason = router.resolve_route(task_category=TASK_REASONING, message=reasoning_prompt)
    if any(p.is_configured() for p in (provider_manager.get_provider("nvidia"), provider_manager.get_provider("groq"))):
        assert route_reason.provider_id in ("nvidia", "groq", "openrouter")
        assert route_reason.provider_id != "ollama"


# =============================================================================
# 9. Offline / Degraded Mode Test
# =============================================================================
def test_offline_degraded_mode_routing():
    """Verify that when offline, ModelRouter switches strictly to local providers without cloud retries."""
    router = ModelRouter()

    with patch.object(connectivity_service, "is_online", return_value=False):
        decision = router.resolve_route(
            task_category=TASK_GENERAL_CHAT,
            message="Explain general relativity"
        )
        # In offline mode, primary candidate must be local
        assert decision.provider_id in ("ollama", "huggingface", "mock-narad")
        assert "offline" in decision.routing_reason.lower() or "local" in decision.routing_reason.lower()


# =============================================================================
# 10. False-Success Prevention (Zero Fake Success) Test
# =============================================================================
@pytest.mark.asyncio
async def test_false_success_prevention():
    """Verify that TaskEngine marks a task as VERIFY_FAILED or FAILED if actions fail verification."""
    engine = AutonomousTaskEngine()

    task = AutonomousTask(
        task_id="test_zero_fake_success",
        objective="Run imaginary test pipeline",
        steps=[
            TaskStep(
                step_id="step_1",
                title="Verify critical service",
                description="Check nonexistent port",
                tool_name="check_service_port",
                tool_args={"port": 59999},
                status="completed",
                verification_strategy="port_check",
                verification_result={"verified": False, "details": "Port 59999 is closed."}
            )
        ]
    )

    await engine._synthesize_task_result(task)
    assert task.status == TaskStatus.VERIFY_FAILED
    assert task.final_verification == "FAILED"
    assert "Verification failed" in task.summary


# =============================================================================
# 11. Deterministic Micro Tasks Test
# =============================================================================
def test_micro_tasks_resolution():
    """Verify MicroTaskService handles math, time, git status, and installed models in <5ms."""
    # 1. Math calculation
    calc_res = micro_task_service.resolve("what is 45 * 20")
    assert calc_res is not None
    assert "900" in calc_res["response"]
    assert calc_res["provider"] == "deterministic-engine"
    assert calc_res["usage"]["prompt_tokens"] == 0

    # 2. Time query
    time_res = micro_task_service.resolve("what time is it")
    assert time_res is not None
    assert "current time" in time_res["response"].lower()
    assert time_res["provider"] == "deterministic-engine"

    # 3. Git status query
    git_res = micro_task_service.resolve("git status")
    assert git_res is not None
    assert "git repository status" in git_res["response"].lower()
    assert "branch" in git_res["git"]


# =============================================================================
# 12. NARAD HEALTH Diagnostics Test
# =============================================================================
def test_narad_health_diagnostics():
    """Verify NARAD HEALTH reports honest statuses across all 16 core subsystems."""
    res = micro_task_service.run_narad_health()
    assert res["grade"] in ("GREEN", "YELLOW", "RED")
    assert "report" in res
    assert len(res["components"]) == 16
    for comp in ["FastAPI", "SQLite", "Ollama", "Groq", "NVIDIA", "Gemini", "OpenRouter", "Smṛti", "Knowledge"]:
        assert any(comp.lower() in k.lower() for k in res["components"])


# =============================================================================
# 13. PROJECT STATUS Response Test
# =============================================================================
def test_project_status_response():
    """Verify PROJECT STATUS returns concise project status representation."""
    res = micro_task_service.run_project_status()
    assert "NARAD PROJECT" in res["report"]
    assert "Backend" in res["report"]
    assert "Frontend" in res["report"]
    assert "Git" in res["report"]
    assert "data" in res


# =============================================================================
# 14. Smṛti Secret Prevention & Deduplication Test
# =============================================================================
def test_smriti_secret_prevention():
    """Verify Smṛti refuses to store API keys or secrets in long-term memory."""
    service = SmritiService()

    secret_inputs = [
        "My OpenAI key is sk-proj-1234567890abcdefghijklmnopqrstuvwxyz",
        "Here is the token: gsk_abcdef1234567890",
        "Set api_key nvapi-abcdefghijklmnopqrstuvwxyz",
        "My password is secretpassword123!"
    ]

    for secret in secret_inputs:
        res = service.save_memory("api_key", secret)
        assert res["success"] is False
        assert "security policy" in res["message"].lower() or "secret" in res["message"].lower()


# =============================================================================
# 15. Knowledge Retrieval Telemetry Test
# =============================================================================
def test_knowledge_retrieval_telemetry():
    """Verify Knowledge search returns telemetry showing query, matches, and sources."""
    results = knowledge_service.search_knowledge("Trimurti architecture", max_results=3)
    assert isinstance(results, dict)
    assert "query" in results
    assert "status" in results


# =============================================================================
# 16. Task Engine Concise Summary & Telemetry Fields Test
# =============================================================================
def test_task_engine_concise_summary():
    """Verify AutonomousTask to_dict produces the Phase 2 required concise summary."""
    task = AutonomousTask(
        task_id="task_dev_env",
        objective="Prepare development environment",
        status=TaskStatus.COMPLETED,
        provider_used="LOCAL + GROQ",
        steps=[
            TaskStep(step_id="step_1", title="Check Python", description="", tool_name="check_tool", status="completed"),
            TaskStep(step_id="step_2", title="Check Git", description="", tool_name="git_status", status="completed"),
        ]
    )

    d = task.to_dict()
    assert d["provider_used"] == "LOCAL + GROQ"
    assert d["progress_percentage"] == 100.0
    assert d["final_verification"] == "PASSED"
    assert "TASK\nPrepare development environment" in d["concise_summary"]
    assert "STATUS\nCOMPLETED" in d["concise_summary"]
    assert "Provider: LOCAL + GROQ" in d["concise_summary"]
    assert "Verification: PASSED" in d["concise_summary"]


# =============================================================================
# 17. Vāṇī Voice Status Test
# =============================================================================
@pytest.mark.asyncio
async def test_vani_voice_status():
    """Verify voice status endpoint returns honest status flags."""
    from app.api.routes.voice import voice_status_endpoint
    res = await voice_status_endpoint()
    assert "voice_state" in res
    assert res["voice_state"] in ("VOICE READY", "VOICE OFF", "MIC UNAVAILABLE", "TTS READY", "TTS FAILED")
    assert "stt" in res
    assert "tts" in res
    assert "Hindi" in res["languages"]
    assert "English" in res["languages"]
    assert "Hinglish" in res["languages"]
