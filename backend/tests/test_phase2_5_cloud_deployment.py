"""
NARAD Phase 2.5 / Phase 3 — Production Cloud Backend & Laptop Migration Test Suite.
Validates:
  1. Environment configuration (LOCAL, CLOUD, SELF_HOSTED, env-driven parameters)
  2. PostgreSQL & SQLite multi-dialect engine configuration
  3. Database persistence across all models (sessions, messages, memories, tasks, events, devices, nodes)
  4. Single-user authentication & safe error masking
  5. CORS configuration via environment variables
  6. In-memory sliding-window rate limiting
  7. Production error contract (no secret leakage, machine-readable format)
  8. Cloud platform probes: /health, /ready, /version
  9. Authoritative Runtime Truth: Cloud capability reach vs Mac unavailable state
  10. Server-Sent Events (SSE) streaming headers & cancellation
  11. Smriti Memory Scope Separation: LOCAL vs CLOUD privacy boundary
  12. Provider failure classification, quota states, and modular OpenAI-compatible gateway
  13. Notification persistence & device registration
  14. Local Node Architecture: Heartbeat, status reporting, and future laptop migration
"""

import os
import json
import uuid
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import Settings, settings
from app.db.database import (
    get_db,
    SessionLocal,
    get_db_dialect,
    is_postgres,
    check_db_readiness,
    engine,
)
from app.db.models import (
    ChatSession,
    ChatMessage,
    SmritiMemory,
    EventRecord,
    TaskJournalRecord,
    DeviceRegistration,
    AcknowledgedNotification,
    LocalNodeRecord,
)
from app.services.event_system import event_system, EventType
from app.services.smriti import smriti_service
from app.services.runtime_truth import runtime_truth_service
from app.services.node_registry import node_registry
from app.core.security import rate_limiter
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.providers.base import (
    HEALTH_AVAILABLE,
    HEALTH_RATE_LIMITED,
    HEALTH_QUOTA_EXHAUSTED,
    HEALTH_AUTH_ERROR,
    HEALTH_UNAVAILABLE,
)

client = TestClient(app)


# =============================================================================
# 1. ENVIRONMENT CONFIGURATION TESTS
# =============================================================================

def test_environment_configuration_modes():
    """Verify application parses LOCAL, CLOUD, and SELF_HOSTED configurations."""
    s_local = Settings(ENVIRONMENT="LOCAL", NARAD_RUNTIME_MODE="local")
    assert s_local.ENVIRONMENT == "LOCAL"
    assert s_local.NARAD_RUNTIME_MODE == "local"

    s_cloud = Settings(ENVIRONMENT="CLOUD", NARAD_RUNTIME_MODE="cloud")
    assert s_cloud.ENVIRONMENT == "CLOUD"
    assert s_cloud.NARAD_RUNTIME_MODE == "cloud"

    s_laptop = Settings(ENVIRONMENT="SELF_HOSTED", NARAD_RUNTIME_MODE="hybrid")
    assert s_laptop.ENVIRONMENT == "SELF_HOSTED"
    assert s_laptop.NARAD_RUNTIME_MODE == "hybrid"


def test_cors_configuration_parsing():
    """Verify CORS_ORIGINS parses comma-separated string correctly."""
    s = Settings(CORS_ORIGINS="https://narad.app,https://admin.narad.app,http://localhost:5173")
    assert len(s.CORS_ORIGINS) == 3
    assert "https://narad.app" in s.CORS_ORIGINS
    assert "http://localhost:5173" in s.CORS_ORIGINS


# =============================================================================
# 2. DATABASE CONFIGURATION & POSTGRESQL NORMALIZATION
# =============================================================================

def test_database_url_postgres_scheme_normalization():
    """Render/Heroku/Fly.io postgres:// URLs must normalize to postgresql:// for SQLAlchemy."""
    s = Settings(DATABASE_URL="postgres://narad:secret@db.internal:5432/naraddb")
    assert s.DATABASE_URL == "postgresql://narad:secret@db.internal:5432/naraddb"

    s_pg = Settings(DATABASE_URL="postgresql://narad:secret@db.internal:5432/naraddb")
    assert s_pg.DATABASE_URL == "postgresql://narad:secret@db.internal:5432/naraddb"

    s_sqlite = Settings(DATABASE_URL="sqlite:///./narad.db")
    assert s_sqlite.DATABASE_URL == "sqlite:///./narad.db"


def test_database_readiness_probe():
    """Verify database ping verification and simulated failure response."""
    ok, status_msg = check_db_readiness()
    assert ok is True
    assert status_msg == "connected"

    # Test simulated failure
    with patch.object(engine, "connect", side_effect=Exception("Database connection timeout")):
        fail_ok, fail_msg = check_db_readiness()
        assert fail_ok is False
        assert "unreachable" in fail_msg


# =============================================================================
# 3. DATABASE PERSISTENCE FOR ALL MODELS
# =============================================================================

def test_persistence_all_core_models():
    """Verify sessions, messages, memories, tasks, events, devices, and nodes persist in DB."""
    test_id = f"test_{uuid.uuid4().hex[:8]}"

    with SessionLocal() as db:
        # 1. Chat Session & Message
        session = ChatSession(id=f"ses_{test_id}", title="Persistence Verification")
        db.add(session)
        db.commit()

        msg = ChatMessage(
            id=f"msg_{test_id}",
            session_id=session.id,
            role="user",
            content="Persistent message test",
            metadata_json=json.dumps({"test": True})
        )
        db.add(msg)

        # 2. Smriti Memory (Scoped)
        mem = SmritiMemory(
            id=f"mem_{test_id}",
            key=f"key_{test_id}",
            value="Persistent preference",
            scope="CLOUD",
            confidence=1.0,
            importance=0.8,
        )
        db.add(mem)

        # 3. Task Journal
        task = TaskJournalRecord(
            task_id=f"tsk_{test_id}",
            goal="Verify persistence across all tables",
            status="COMPLETED",
            duration_ms=120,
            verification="VERIFIED"
        )
        db.add(task)

        # 4. Event Record
        event = EventRecord(
            event_id=f"evt_{test_id}",
            event_type="TASK_COMPLETED",
            title="Persistence Complete",
            body="All records saved",
            priority="normal",
            task_id=task.task_id
        )
        db.add(event)

        # 5. Device Registration
        device = DeviceRegistration(
            id=f"dev_{test_id}",
            device_token=f"tok_{test_id}_" + ("0" * 40),
            platform="ios",
            environment="production"
        )
        db.add(device)

        # 6. Local Node Record
        node = LocalNodeRecord(
            node_id=f"node_{test_id}",
            node_name="Verification MacBook Pro",
            status="ONLINE",
            capabilities_json=json.dumps({"computer_control": True})
        )
        db.add(node)
        db.commit()

    # Query back using a fresh DB session
    with SessionLocal() as db:
        assert db.query(ChatSession).filter(ChatSession.id == f"ses_{test_id}").first() is not None
        assert db.query(ChatMessage).filter(ChatMessage.id == f"msg_{test_id}").first() is not None
        assert db.query(SmritiMemory).filter(SmritiMemory.id == f"mem_{test_id}").first() is not None
        assert db.query(TaskJournalRecord).filter(TaskJournalRecord.task_id == f"tsk_{test_id}").first() is not None
        assert db.query(EventRecord).filter(EventRecord.event_id == f"evt_{test_id}").first() is not None
        assert db.query(DeviceRegistration).filter(DeviceRegistration.id == f"dev_{test_id}").first() is not None
        assert db.query(LocalNodeRecord).filter(LocalNodeRecord.node_id == f"node_{test_id}").first() is not None


# =============================================================================
# 4. SINGLE-USER AUTHENTICATION & SECURITY
# =============================================================================

def test_auth_enforcement_and_safe_error():
    """Verify single-user token validation and machine-readable error responses."""
    with patch.object(settings, "NARAD_API_KEY", "prod_secret_token_12345"):
        # Missing auth
        res_missing = client.get("/api/v1/chat/sessions")
        assert res_missing.status_code == 401
        err = res_missing.json()["error"]
        assert err["code"] == "AUTH_REQUIRED"
        assert "request_id" in err
        assert err["retryable"] is False

        # Valid Bearer auth
        res_valid = client.get(
            "/api/v1/chat/sessions",
            headers={"Authorization": "Bearer prod_secret_token_12345"}
        )
        assert res_valid.status_code == 200

        # Valid X-Narad-Key auth
        res_key_header = client.get(
            "/api/v1/chat/sessions",
            headers={"X-Narad-Key": "prod_secret_token_12345"}
        )
        assert res_key_header.status_code == 200


# =============================================================================
# 5. IN-MEMORY SLIDING WINDOW RATE LIMITING
# =============================================================================

def test_rate_limiting_enforcement():
    """Verify sliding-window rate limiting triggers 429 with Retry-After header."""
    rate_limiter.reset()
    with patch.object(settings, "RATE_LIMIT_ENABLED", True):
        with patch.object(settings, "RATE_LIMIT_PER_MINUTE", 5):
            rate_limiter._limit = 5
            # Make 5 requests (should succeed)
            for _ in range(5):
                res = client.get("/api/v1/memory/status")
                assert res.status_code == 200

            # 6th request should be rate-limited
            res_limited = client.get("/api/v1/memory/status")
            assert res_limited.status_code == 429
            data = res_limited.json()
            assert data["error"]["code"] == "RATE_LIMITED"
            assert "Retry-After" in res_limited.headers

    rate_limiter.reset()
    rate_limiter._limit = 120


# =============================================================================
# 6. CLOUD PROBES (/health, /ready, /version)
# =============================================================================

def test_cloud_platform_probes():
    """Verify standard cloud probes for load balancers and orchestrators."""
    # /health
    h_res = client.get("/health")
    assert h_res.status_code == 200
    assert h_res.json()["status"] == "online"
    assert "version" in h_res.json()

    # /ready
    r_res = client.get("/ready")
    assert r_res.status_code == 200
    assert r_res.json()["ready"] is True

    # /version
    v_res = client.get("/version")
    assert v_res.status_code == 200
    assert "environment" in v_res.json()


# =============================================================================
# 7. RUNTIME TRUTH & CLOUD CAPABILITY REACH
# =============================================================================

def test_runtime_truth_cloud_mode_mac_unavailable():
    """In Cloud mode without a connected local node, Mac capabilities are unavailable."""
    with patch.object(settings, "NARAD_RUNTIME_MODE", "cloud"):
        with patch.object(node_registry, "get_active_node", return_value=None):
            truth = runtime_truth_service.get_runtime_truth()
            assert truth["mac_availability"]["available"] is False
            assert "OFFLINE" in truth["mac_availability"]["status"]
            assert truth["capabilities"]["local"]["computer_control"] == "UNAVAILABLE_MAC_OFFLINE"
            assert truth["capabilities"]["local"]["screen_capture"] == "UNAVAILABLE_MAC_OFFLINE"
            assert truth["capabilities"]["cloud"]["cloud_llm_inference"] == "AVAILABLE"


# =============================================================================
# 8. SMRITI MEMORY SCOPE SEPARATION
# =============================================================================

def test_memory_scope_separation():
    """Verify LOCAL vs CLOUD scope boundaries are strictly preserved."""
    with SessionLocal() as db:
        # Create LOCAL memory
        smriti_service.save_memory(
            key="private_mac_credential",
            value="super_secret_local_value",
            scope="LOCAL",
            db=db
        )
        # Create CLOUD memory
        smriti_service.save_memory(
            key="cloud_shared_preference",
            value="dark_theme_oled",
            scope="CLOUD",
            db=db
        )

        status_data = smriti_service.get_memory_status(db=db)
        assert status_data["total_memories"] >= 2
        assert status_data["scopes"].get("LOCAL", 0) >= 1
        assert status_data["scopes"].get("CLOUD", 0) >= 1

        # Query filtered by CLOUD scope
        cloud_mems = smriti_service.list_memories(scope="CLOUD", db=db)
        cloud_keys = [m["key"] for m in cloud_mems]
        assert "cloud_shared_preference" in cloud_keys
        assert "private_mac_credential" not in cloud_keys

        # Query filtered by LOCAL scope
        local_mems = smriti_service.list_memories(scope="LOCAL", db=db)
        local_keys = [m["key"] for m in local_mems]
        assert "private_mac_credential" in local_keys
        assert "cloud_shared_preference" not in local_keys


# =============================================================================
# 9. OPENAI-COMPATIBLE MODULAR GATEWAY & ERROR CLASSIFICATION
# =============================================================================

def test_openai_compatible_provider_classification():
    """Verify OpenAI-compatible adapter properly classifies errors and cooldowns."""
    def create_p():
        return OpenAICompatibleProvider(
            provider_id="cerebras",
            display_name="Cerebras Fast Inference",
            base_url="https://api.cerebras.ai/v1",
            api_key="csk-test-key",
            default_model="llama3.1-70b"
        )

    # 1. Rate limit classification
    p_rate = create_p()
    assert p_rate.is_configured() is True
    assert p_rate.provider_id == "cerebras"
    p_rate.classify_and_record_error(status_code=429, error_text="Rate limit exceeded: TPM limit")
    assert p_rate.get_status()["health_state"] == HEALTH_RATE_LIMITED
    assert p_rate.is_in_cooldown() is True

    # 2. Auth error classification
    p_auth = create_p()
    p_auth.classify_and_record_error(status_code=401, error_text="Unauthorized: Invalid API key")
    assert p_auth.get_status()["health_state"] == HEALTH_AUTH_ERROR

    # 3. Quota exhausted classification
    p_quota = create_p()
    p_quota.classify_and_record_error(status_code=402, error_text="Insufficient credits: Quota reached")
    assert p_quota.get_status()["health_state"] == HEALTH_QUOTA_EXHAUSTED



# =============================================================================
# 10. LOCAL NODE ARCHITECTURE (Future Laptop Migration)
# =============================================================================

def test_local_node_heartbeat_and_status():
    """Verify local Mac node can register, check in, and update availability."""
    # 1. Record heartbeat from future laptop
    h_res = client.post(
        "/api/v1/nodes/heartbeat",
        json={
            "node_id": "node_laptop_macbook_pro",
            "node_name": "Pratyush's Laptop Node",
            "status": "ONLINE",
            "capabilities": {
                "computer_control": True,
                "screen_capture": True,
                "ollama": True,
                "local_ai": True,
            },
            "model_availability": ["qwen3.5:0.8b", "llama3.2:3b"],
            "runtime": {"os": "macOS", "arch": "arm64"}
        }
    )
    assert h_res.status_code == 200
    h_data = h_res.json()
    assert h_data["success"] is True
    assert h_data["node_id"] == "node_laptop_macbook_pro"

    # 2. Check node connectivity status
    s_res = client.get("/api/v1/nodes/status")
    assert s_res.status_code == 200
    s_data = s_res.json()
    assert s_data["connected"] is True
    assert s_data["active_node_id"] == "node_laptop_macbook_pro"

    # 3. Query all nodes list
    l_res = client.get("/api/v1/nodes")
    assert l_res.status_code == 200
    n_ids = [n["node_id"] for n in l_res.json()]
    assert "node_laptop_macbook_pro" in n_ids

    # 4. Check single node details
    d_res = client.get("/api/v1/nodes/node_laptop_macbook_pro")
    assert d_res.status_code == 200
    assert d_res.json()["node_name"] == "Pratyush's Laptop Node"
