"""
NARAD Test Suite — Cloud-Safe Local AI Loading & Startup Verification.
Ensures that in CLOUD mode:
1. No heavyweight local-AI modules (torch, transformers) are imported during app/router/provider startup.
2. HuggingFace / Local-AI providers are gracefully marked UNAVAILABLE.
3. Health and Readiness endpoints operate normally.
4. Local AI endpoints return 503 rather than crashing or faking capabilities.
5. In LOCAL mode, local-AI functionality is preserved.
"""

import os
import sys
import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


def test_cloud_mode_does_not_import_torch_or_transformers():
    """
    Spawns a clean Python subprocess in CLOUD mode and imports app.main,
    provider_manager, router, and health routes.
    Verifies that neither torch nor transformers are loaded in sys.modules.
    """
    code = """
import os, sys
os.environ["ENVIRONMENT"] = "CLOUD"

# Import app and key components
import app.providers.manager as pm
import app.core.router as cr
import app.api.routes.health as hr
import app.api.routes.local_ai as lr
from app.main import app

assert "torch" not in sys.modules, f"torch leaked into sys.modules! Loaded: {[m for m in sys.modules if 'torch' in m]}"
assert "transformers" not in sys.modules, f"transformers leaked into sys.modules! Loaded: {[m for m in sys.modules if 'transformers' in m]}"
print("VERIFIED_CLEAN_CLOUD_IMPORT")
"""
    env = os.environ.copy()
    env["ENVIRONMENT"] = "CLOUD"
    backend_dir = str(Path(__file__).resolve().parent.parent)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=backend_dir
    )
    assert result.returncode == 0, f"Cloud import check failed:\nStdout: {result.stdout}\nStderr: {result.stderr}"
    assert "VERIFIED_CLEAN_CLOUD_IMPORT" in result.stdout


def test_cloud_mode_provider_manager_and_huggingface(monkeypatch):
    """
    In CLOUD mode, HuggingFace and Ollama providers must be registered
    but report is_configured() == False gracefully without raising exceptions.
    """
    monkeypatch.setenv("ENVIRONMENT", "CLOUD")
    from app.providers.manager import provider_manager

    hf = provider_manager.get_provider("huggingface")
    assert hf is not None
    assert hf.is_configured() is False

    ollama = provider_manager.get_provider("ollama")
    assert ollama is not None
    assert ollama.is_configured() is False


def test_cloud_mode_health_and_ready_endpoints(monkeypatch):
    """
    Health and readiness endpoints must succeed in CLOUD mode without torch.
    """
    monkeypatch.setenv("ENVIRONMENT", "CLOUD")
    from app.main import app
    client = TestClient(app)

    # Root health
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ok", "healthy", "online")

    # Readiness
    res_ready = client.get("/ready")
    assert res_ready.status_code == 200
    ready_data = res_ready.json()
    assert ready_data["status"] == "ready"

    # API health check
    res_api = client.get("/api/health")
    assert res_api.status_code == 200
    api_data = res_api.json()
    assert "status" in api_data
    # In cloud mode, local_ai should be marked UNAVAILABLE or STANDBY
    local_ai_info = api_data.get("local_ai")
    if isinstance(local_ai_info, dict):
        assert local_ai_info.get("status") in ("STANDBY", "UNAVAILABLE", "NONE")
    else:
        assert local_ai_info in ("STANDBY", "UNAVAILABLE", "NONE", None)


def test_cloud_mode_local_ai_endpoints_graceful_503(monkeypatch):
    """
    In CLOUD mode, calls to /api/local-ai/generate or /api/local-ai/embeddings
    must return 503 SERVICE UNAVAILABLE instead of crashing.
    """
    monkeypatch.setenv("ENVIRONMENT", "CLOUD")
    from app.main import app
    client = TestClient(app)

    # Local AI status returns honest UNAVAILABLE
    res_status = client.get("/api/local-ai/status")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["llm"]["status"] == "UNAVAILABLE"
    assert status_data["llm"]["device"] == "NONE"
    assert status_data["embeddings"]["ready"] is False
    assert status_data["vision"]["status"] == "UNAVAILABLE"

    # Generate returns 503
    res_gen = client.post("/api/local-ai/generate", json={"prompt": "Hello"})
    assert res_gen.status_code == 503
    assert "CLOUD" in res_gen.json()["detail"]

    # Embeddings returns 503
    res_emb = client.post("/api/local-ai/embeddings", json={"text": "Test embedding"})
    assert res_emb.status_code == 503
    assert "CLOUD" in res_emb.json()["detail"]


def test_local_mode_preserves_local_ai(monkeypatch):
    """
    In LOCAL mode, verify that local AI manager and providers preserve
    their local execution capability (or correct local status).
    """
    monkeypatch.setenv("ENVIRONMENT", "LOCAL")
    from app.core.config import settings
    assert settings.is_cloud is False

    from app.services.local_ai.manager import local_ai_manager
    status = local_ai_manager.get_status_info()
    assert "status" in status
    assert "device" in status
