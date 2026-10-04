"""
NARAD V7.1 — Hugging Face Local AI Test Suite.
Validates:
1. Hugging Face import & Hub cache inspection
2. Hub connectivity and model caching
3. Model cache hit detection
4. Local inference execution & real latency measurement
5. Apple Silicon MPS/CPU detection and honest telemetry
6. Local provider integration in ProviderManager
7. Model Router TASK_LOCAL capability and priority order
8. Cloud router preservation for general chat
9. Knowledge Base local embeddings (sentence-transformers/all-MiniLM-L6-v2)
10. Local AI API endpoints (/api/local-ai/status, /generate, /embeddings)
"""

import pytest
import asyncio
from fastapi.testclient import TestClient

from app.main import app
from app.services.local_ai.cache import hf_cache_manager
from app.services.local_ai.manager import local_ai_manager
from app.services.embeddings.manager import embedding_manager
from app.services.vision.huggingface_vision import local_hf_vision_provider
from app.providers.manager import provider_manager
from app.core.router import model_router, TASK_LOCAL, TASK_FAST_CHAT, TASK_GENERAL_CHAT
from app.services.knowledge import KnowledgeBaseService

client = TestClient(app)


def test_01_hf_import_and_hub_cache():
    """Verify Hugging Face Hub cache directory and cached model discovery."""
    cache_dir = hf_cache_manager.get_cache_dir()
    assert cache_dir is not None
    assert "huggingface" in cache_dir.lower()

    cached_models = hf_cache_manager.get_cached_models()
    assert isinstance(cached_models, list)
    assert len(cached_models) >= 1

    repo_ids = [m["repo_id"] for m in cached_models]
    # Check that SmolLM2 or existing models are registered in the cache
    assert any("smollm2" in r.lower() or "chatterbox" in r.lower() or "whisper" in r.lower() for r in repo_ids)


def test_02_device_and_mps_detection():
    """Verify Apple Silicon MPS vs CPU hardware detection."""
    status = local_ai_manager.get_status_info()
    assert status["device"] in ("CPU", "MPS")
    assert "mps_available" in status
    assert isinstance(status["mps_available"], bool)

    # Embedding provider device detection
    emb_status = embedding_manager.get_status()
    assert emb_status["provider_status"]["device"] in ("MPS", "CPU")


def test_03_model_cache_hit_and_inspection():
    """Verify cache hit detection for pre-downloaded SmolLM2 model."""
    is_cached = hf_cache_manager.is_model_cached(local_ai_manager.model_id)
    assert is_cached is True

    info = hf_cache_manager.get_model_cache_info(local_ai_manager.model_id)
    assert info is not None
    assert info["size_on_disk"] > 0
    assert "M" in info["size_on_disk_str"] or "G" in info["size_on_disk_str"]


def test_04_local_llm_inference():
    """Test on-device inference with SmolLM2 and verify real latency telemetry."""
    messages = [{"role": "user", "content": "What is 2+2? Answer in one sentence."}]
    res = local_ai_manager.generate(messages, max_tokens=30, temperature=0.1)

    assert res["status"] == "success"
    assert res["provider"] == "huggingface"
    assert res["model"] == local_ai_manager.model_id
    assert len(res["content"]) > 0
    assert res["latency_ms"] > 0
    assert res["device"] in ("CPU", "MPS")
    assert res["cache_hit"] is True
    assert res["usage"]["completion_tokens"] > 0


@pytest.mark.asyncio
async def test_05_local_provider_in_provider_manager():
    """Verify LocalHuggingFaceProvider registered in ProviderManager."""
    provider = provider_manager.get_provider("huggingface")
    assert provider is not None
    assert provider.provider_id == "huggingface"
    assert provider.is_configured() is True
    assert provider.supports_tools() is False
    assert provider.supports_streaming() is True

    res = await provider.generate_response(
        messages=[{"role": "user", "content": "Hello from NARAD."}],
        max_tokens=20
    )
    assert res["status"] == "success"
    assert res["provider"] == "huggingface"
    assert len(res["content"]) > 0


def test_06_model_router_local_capability():
    """Verify TASK_LOCAL capability in Model Router."""
    for p in provider_manager.get_all_providers().values():
        p._cooldown_until = 0.0

    # 1. Directive classification for local requests
    task = model_router.classify_task("Please run locally: calculate primes.")
    assert task == TASK_LOCAL

    # 2. Route resolution for TASK_LOCAL
    decision = model_router.resolve_route(task_category=TASK_LOCAL)
    assert decision.provider_id in ("huggingface", "ollama")
    assert decision.is_configured is True
    assert decision.task_category == TASK_LOCAL

    # 3. Failover candidates include cloud providers
    failover_pids = [c["provider"] for c in decision.failover_candidates]
    assert "groq" in failover_pids


def test_07_general_chat_routes_to_cloud():
    """Verify general chat preserves Groq/cloud as primary provider."""
    for p in provider_manager.get_all_providers().values():
        p._cooldown_until = 0.0

    decision = model_router.resolve_route(message="What is the capital of Japan?")
    assert decision.provider_id == "groq"
    assert decision.model_name == "openai/gpt-oss-120b"


def test_08_local_embeddings_provider():
    """Verify local Hugging Face dense embeddings generation & re-ranking."""
    vec = embedding_manager.embed_query("artificial intelligence")
    assert vec is not None
    assert len(vec) == 384

    # Test re-ranking
    query = "quantum physics and particles"
    chunks = [
        {"content": "A recipe for baking chocolate cookies with sugar and flour.", "id": "1"},
        {"content": "Quantum mechanics describes subatomic particles and wave-particle duality.", "id": "2"},
        {"content": "Football matches are held in large stadiums on weekends.", "id": "3"}
    ]
    reranked = embedding_manager.rerank_chunks(query, chunks, top_k=3)
    assert reranked[0]["id"] == "2"
    assert "semantic_score" in reranked[0]


def test_09_knowledge_base_compatibility():
    """Verify KnowledgeBaseService operates cleanly with embedding re-ranking."""
    kb = KnowledgeBaseService()
    search_res = kb.search_knowledge("test query", max_results=2)
    assert search_res is not None
    assert "status" in search_res


def test_10_local_vision_provider_interface():
    """Verify local vision provider interface reports valid status."""
    v_status = local_hf_vision_provider.get_status()
    assert v_status["provider"] == "huggingface_vision"
    assert v_status["model"] == "HuggingFaceTB/SmolVLM-Instruct"
    assert "device" in v_status


def test_11_api_local_ai_status_and_generate():
    """Verify FastAPI /api/local-ai endpoints."""
    # 1. GET /api/local-ai/status
    resp_status = client.get("/api/local-ai/status")
    assert resp_status.status_code == 200
    data = resp_status.json()
    assert "llm" in data
    assert "cache" in data
    assert "embeddings" in data
    assert "vision" in data
    assert data["llm"]["device"] in ("CPU", "MPS")

    # 2. POST /api/local-ai/generate
    resp_gen = client.post(
        "/api/local-ai/generate",
        json={"prompt": "Say test in one word.", "max_tokens": 15}
    )
    assert resp_gen.status_code == 200
    gen_data = resp_gen.json()
    assert gen_data["status"] == "success"
    assert gen_data["latency_ms"] > 0

    # 3. POST /api/local-ai/embeddings
    resp_emb = client.post(
        "/api/local-ai/embeddings",
        json={"text": "Test embedding vector generation"}
    )
    assert resp_emb.status_code == 200
    emb_data = resp_emb.json()
    assert emb_data["dimension"] == 384
    assert len(emb_data["vector_sample"]) == 8


def test_12_health_subsystems_telemetry():
    """Verify /api/health includes local_ai and embeddings in telemetry."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    health = resp.json()
    assert "local_ai" in health["subsystems"]
    assert "embeddings" in health["subsystems"]
    assert "local_ai" in health
