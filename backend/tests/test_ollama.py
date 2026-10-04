"""
NARAD V7.2 — Automated Test Suite for Native Ollama Local Fast Model Provider.
Verifies daemon health, direct generation, streaming, router task classification,
capability order, graceful unavailable handling, and health telemetry.
"""

import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app
from app.providers.ollama import OllamaProvider
from app.providers.manager import provider_manager
from app.core.router import (
    model_router,
    TASK_LOCAL_FAST,
    TASK_GENERAL_CHAT,
    TASK_FAST_CHAT,
    TASK_REASONING,
    TASK_LOCAL,
)
from app.core.config import settings


@pytest.fixture(autouse=True)
def isolate_test_state():
    from app.services.agent_brain import agent_brain, RuntimeMode
    agent_brain.set_mode(RuntimeMode.AUTO)
    for p in provider_manager.get_all_providers().values():
        p._cooldown_until = 0.0
    yield
    agent_brain.set_mode(RuntimeMode.AUTO)


@pytest.fixture
def client():
    return TestClient(app)


def test_01_ollama_daemon_health():
    """Verify Ollama provider detects daemon and configured model."""
    provider = OllamaProvider()
    assert provider.provider_id == "ollama"
    assert provider.display_name == "Ollama (Local Fast)"
    assert provider.is_configured() is True

    health = asyncio.run(provider.check_health_async())
    assert health["healthy"] is True
    assert health["status"] == "ONLINE"
    assert any("qwen3.5:0.8b" in m for m in health["models"])
    assert health["model_ready"] is True


def test_02_ollama_provider_direct_generation():
    """Verify direct response generation with latency telemetry and token usage."""
    provider = OllamaProvider()
    response = asyncio.run(
        provider.generate_response(
            messages=[
                {"role": "system", "content": "Extract only the requested entity in 1-2 words."},
                {"role": "user", "content": "Extract city: I live in Berlin."},
            ],
            temperature=0.1,
            max_tokens=32,
        )
    )
    assert response is not None
    assert response["provider"] == "ollama"
    assert response["model"] == settings.OLLAMA_MODEL
    assert response["status"] == "success"
    assert response["latency_ms"] > 0
    assert "Berlin" in response["content"]
    assert response["usage"]["prompt_tokens"] > 0
    assert response["usage"]["completion_tokens"] > 0


def test_03_ollama_streaming():
    """Verify streaming yields chunks and records latency."""
    provider = OllamaProvider()

    async def collect_stream():
        chunks = []
        async for chunk in provider.stream_response(
            messages=[{"role": "user", "content": "Say hello in 3 words."}],
            temperature=0.1,
            max_tokens=24,
        ):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(collect_stream())
    assert len(chunks) > 0
    full_text = "".join(chunks)
    assert len(full_text.strip()) > 0
    assert provider.get_health_status()["latency_ms"] > 0


def test_04_router_local_fast_classification():
    """Verify directive task classification for intent, extraction, formatting."""
    # 1. Intent classification
    assert model_router.classify_task("Classify intent: book a flight to Mumbai") == TASK_LOCAL_FAST
    assert model_router.classify_task("Identify intent of this user message: cancel subscription") == TASK_LOCAL_FAST

    # 2. Information extraction
    assert model_router.classify_task("Extract json from the following paragraph") == TASK_LOCAL_FAST
    assert model_router.classify_task("Extract entities: John arrived in New York on Tuesday") == TASK_LOCAL_FAST
    assert model_router.classify_task("Extract date from the ticket receipt") == TASK_LOCAL_FAST
    assert model_router.classify_task("Extract email from contact string") == TASK_LOCAL_FAST
    assert model_router.classify_task("Extract city from the statement") == TASK_LOCAL_FAST

    # 3. Formatting
    assert model_router.classify_task("Format as json: name: Alice, age: 30") == TASK_LOCAL_FAST
    assert model_router.classify_task("Format text to clean markdown") == TASK_LOCAL_FAST

    # 4. Explicit local fast triggers
    assert model_router.classify_task("Run this on local fast model") == TASK_LOCAL_FAST
    assert model_router.classify_task("Use ollama to parse this snippet") == TASK_LOCAL_FAST


def test_05_router_local_fast_resolution():
    """Verify resolve_route routes TASK_LOCAL_FAST directly to Ollama with failovers."""
    decision = model_router.resolve_route(task_category=TASK_LOCAL_FAST)
    assert decision.provider_id == "ollama"
    assert decision.model_name == settings.OLLAMA_MODEL
    assert decision.is_configured is True
    assert decision.task_category == TASK_LOCAL_FAST
    assert len(decision.failover_candidates) > 0
    # First failover should be Groq
    assert decision.failover_candidates[0]["provider"] == "groq"


def test_06_router_general_chat_preservation():
    """Verify general conversation continues to route to Groq LPU by default."""
    decision = model_router.resolve_route(message="What is the capital of India?")
    assert decision.task_category == TASK_GENERAL_CHAT
    assert decision.provider_id == "groq"
    assert decision.model_name == settings.NARAD_DEFAULT_MODEL


def test_07_graceful_unavailable_handling():
    """Verify that when Ollama is unavailable, failover routes to Groq smoothly."""
    # Temporarily set Ollama as unreachable
    ollama_prov = provider_manager.get_provider("ollama")
    original_base_url = ollama_prov._base_url
    try:
        ollama_prov._base_url = "http://127.0.0.1:9999"  # Non-existent port
        ollama_prov._cached_liveness = None

        assert ollama_prov.is_configured() is False

        # Now resolve route for LOCAL_FAST
        decision = model_router.resolve_route(task_category=TASK_LOCAL_FAST)
        # Should fall back to the next eligible provider (Groq)
        assert decision.provider_id == "groq"
        assert decision.model_name == settings.NARAD_DEFAULT_MODEL
    finally:
        ollama_prov._base_url = original_base_url
        ollama_prov._cached_liveness = None


def test_08_health_telemetry_includes_ollama(client):
    """Verify /api/health includes Ollama in provider_matrix, subsystems, and routing_orders."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()

    assert data["version"] == "7.2.0"
    assert data["router_version"] == "V7.2"

    # Provider matrix
    matrix = data.get("provider_matrix", {})
    assert "ollama" in matrix
    assert matrix["ollama"]["is_configured"] is True
    assert matrix["ollama"]["display_name"] == "Ollama (Local Fast)"

    # Subsystems
    subsystems = data.get("subsystems", {})
    assert "ollama" in subsystems
    assert "qwen3.5:0.8b" in subsystems["ollama"]

    # Routing orders
    routing_orders = data.get("routing_orders", {})
    assert "local_fast" in routing_orders
    assert routing_orders["local_fast"][0] == "ollama"
    assert "local" in routing_orders


def test_09_chat_endpoint_local_fast_dispatch(client):
    """Verify /api/chat dispatches lightweight extraction/intent requests to Ollama."""
    res = client.post(
        "/api/chat",
        json={"message": "Classify intent: please book a train ticket."}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["provider"] == "ollama"
    assert data["model"] == settings.OLLAMA_MODEL
    assert data["latency_ms"] > 0
    assert len(data["response"]) > 0

