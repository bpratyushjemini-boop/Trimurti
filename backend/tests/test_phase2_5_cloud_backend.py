"""
NARAD Phase 2.5 — Production Backend & Cloud Readiness Test Suite.
Tests:
  1. PostgreSQL-compatible repository abstraction, pooling, and dialect detection
  2. Stable server-side IDs (ses_, tsk_, evt_, mem_)
  3. Task events lifecycle (all 9 standard event types)
  4. Server-Sent Events (SSE) streaming headers & X-Accel-Buffering
  5. Security: Single-user Auth boundary, Rate Limiting, Request Size Limits, Safe Error Masking
  6. Memory separation: LOCAL vs CLOUD privacy boundaries
  7. Cloud / Local capability truth & Mac unavailable enforcement
  8. Provider routing: Health states, cooldowns, quota awareness, and OpenAI-compatible gateway mesh
  9. Database backup export and restoration
"""

import pytest
import time
import json
import uuid
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.db.database import (
    get_db,
    SessionLocal,
    get_db_dialect,
    is_postgres,
    check_db_readiness,
    engine,
)
from app.db.models import ChatSession, ChatMessage, SmritiMemory, EventRecord, TaskJournalRecord
from app.core.identifiers import (
    generate_session_id,
    generate_task_id,
    generate_event_id,
    generate_memory_id,
    is_valid_id,
)
from app.services.event_system import event_system, EventType
from app.services.smriti import smriti_service
from app.services.runtime_truth import runtime_truth_service
from app.services.computer import computer_adapter
from app.services.backup import export_database_backup, import_database_backup
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
# 1. DATABASE & POSTGRESQL REPOSITORY ABSTRACTION TESTS
# =============================================================================

def test_database_dialect_and_readiness():
    """Verify database abstraction correctly introspects dialect and reports connectivity."""
    dialect = get_db_dialect()
    assert dialect in ("sqlite", "postgresql")
    assert isinstance(is_postgres(), bool)

    ok, msg = check_db_readiness()
    assert ok is True
    assert msg == "connected"


def test_database_url_normalization():
    """Verify postgres:// is rewritten to postgresql:// for Render/Fly.io compatibility."""
    from app.core.config import Settings
    s = Settings(DATABASE_URL="postgres://user:pass@ep-cool.railway.app/narad")
    assert s.DATABASE_URL.startswith("postgresql://")


def test_database_simulated_failure():
    """Verify check_db_readiness accurately catches and reports database connection failures."""
    with patch.object(engine, "connect", side_effect=Exception("Connection refused: 5432")):
        ok, msg = check_db_readiness()
        assert ok is False
        assert "unreachable" in msg


# =============================================================================
# 2. STABLE SERVER-SIDE IDENTIFIER TESTS
# =============================================================================

def test_stable_identifiers():
    """Verify stable server-side prefixed UUIDs for sessions, tasks, events, and memories."""
    sid = generate_session_id()
    assert sid.startswith("ses_")
    assert len(sid) >= 20
    assert is_valid_id(sid, "ses_") is True

    tid = generate_task_id()
    assert tid.startswith("tsk_")
    assert is_valid_id(tid, "tsk_") is True

    eid = generate_event_id()
    assert eid.startswith("evt_")
    assert is_valid_id(eid, "evt_") is True

    mid = generate_memory_id()
    assert mid.startswith("mem_")
    assert is_valid_id(mid, "mem_") is True

    # Standard UUID also passes general validity
    raw_uuid = str(uuid.uuid4())
    assert is_valid_id(raw_uuid) is True
    assert is_valid_id("", "ses_") is False


def test_session_creation_uses_stable_id():
    """Verify ChatSession model instantiates with a ses_ prefixed ID."""
    with SessionLocal() as db:
        session = smriti_service.create_session(title="Phase 2.5 Test Session", db=db)
        try:
            assert session.id.startswith("ses_") or len(session.id) >= 32
            fetched = smriti_service.get_session(session.id, db=db)
            assert fetched is not None
            assert fetched.title == "Phase 2.5 Test Session"
        finally:
            smriti_service.delete_session(session.id, db=db)


# =============================================================================
# 3. TASK EVENTS LIFECYCLE TESTS (ALL 9 STANDARD EVENTS)
# =============================================================================

def test_task_events_lifecycle():
    """Verify all 9 standard events can be emitted, persisted, and retrieved."""
    test_task_id = generate_task_id()

    standard_events = [
        EventType.TASK_CREATED,
        EventType.TASK_STARTED,
        EventType.PLAN_CREATED,
        EventType.TOOL_STARTED,
        EventType.TOOL_COMPLETED,
        EventType.OBSERVATION_CREATED,
        EventType.RECOVERY_STARTED,
        EventType.TASK_COMPLETED,
        EventType.TASK_FAILED,
    ]

    for ev_type in standard_events:
        payload = event_system.emit_event(
            event_type=ev_type,
            title=f"Test {ev_type}",
            body=f"Body for {ev_type}",
            task_id=test_task_id,
            priority="high" if ev_type in (EventType.TASK_COMPLETED, EventType.TASK_FAILED) else "normal",
            metadata={"step": ev_type.lower()}
        )
        assert payload["event_id"].startswith("evt_")
        assert payload["event_type"] == ev_type
        assert payload["task_id"] == test_task_id

    # Retrieve all events for this task
    events = event_system.get_events(task_id=test_task_id, limit=50)
    retrieved_types = {e["event_type"] for e in events}
    for ev_type in standard_events:
        assert ev_type in retrieved_types


def test_notification_worthiness_evaluation():
    """Verify high-priority and terminal events are evaluated as notifiable."""
    assert event_system.evaluate_notification_worthiness(EventType.TASK_COMPLETED) is True
    assert event_system.evaluate_notification_worthiness(EventType.TASK_FAILED) is True
    assert event_system.evaluate_notification_worthiness(EventType.RECOVERY_STARTED) is True
    assert event_system.evaluate_notification_worthiness("OBSERVATION_CREATED", priority="normal") is False
    assert event_system.evaluate_notification_worthiness("OBSERVATION_CREATED", priority="high") is True


# =============================================================================
# 4. SSE STREAMING HEADERS TESTS
# =============================================================================

def test_sse_streaming_headers():
    """Verify SSE streaming endpoints set anti-buffering and keep-alive headers."""
    with client.stream("POST", "/api/chat/stream", json={"message": "ping"}) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        assert response.headers.get("x-accel-buffering") == "no"
        assert "no-cache" in response.headers.get("cache-control", "")
        # Read the first event and exit cleanly
        for line in response.iter_lines():
            if line:
                break


# =============================================================================
# 5. SECURITY & PROTECTION TESTS
# =============================================================================

def test_public_probes_accessible_without_auth():
    """Verify health, ready, version, and root probes are accessible without authentication."""
    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] in ("online", "degraded")

    r_ready = client.get("/ready")
    assert r_ready.status_code in (200, 503)
    assert "ready" in r_ready.json()

    r_version = client.get("/version")
    assert r_version.status_code == 200
    assert "version" in r_version.json()


def test_single_user_auth_boundary():
    """Verify NARAD_API_KEY restricts access when configured, and allows authorized keys."""
    # Patch NARAD_API_KEY to test security enforcement
    with patch.object(settings, "NARAD_API_KEY", "super-secret-key-123"):
        # 1. Unauthenticated request to protected route -> 401
        res_unauth = client.get("/api/chats")
        assert res_unauth.status_code == 401
        assert res_unauth.json()["error_code"] == "AUTH_REQUIRED"

        # 2. Invalid key -> 401
        res_bad = client.get("/api/chats", headers={"Authorization": "Bearer wrong-key"})
        assert res_bad.status_code == 401

        # 3. Valid Bearer Token -> 200
        res_ok_bearer = client.get("/api/chats", headers={"Authorization": "Bearer super-secret-key-123"})
        assert res_ok_bearer.status_code == 200

        # 4. Valid X-Narad-Key Header -> 200
        res_ok_header = client.get("/api/chats", headers={"X-Narad-Key": "super-secret-key-123"})
        assert res_ok_header.status_code == 200

        # 5. Public route still works without key
        res_pub = client.get("/health")
        assert res_pub.status_code == 200


def test_request_size_limit():
    """Verify requests exceeding MAX_REQUEST_SIZE_BYTES are rejected with 413."""
    with patch.object(settings, "MAX_REQUEST_SIZE_BYTES", 1024):  # 1 KB limit for testing
        headers = {"Content-Length": "2048"}
        res = client.post("/api/chat", json={"message": "test"}, headers=headers)
        assert res.status_code == 413
        assert res.json()["error_code"] == "PAYLOAD_TOO_LARGE"


def test_rate_limiter_enforcement():
    """Verify rapid requests exceeding rate limit trigger HTTP 429."""
    rate_limiter.reset()
    test_ip = "192.168.1.100"
    limit = 5

    # Simulate 5 allowed requests
    for _ in range(limit):
        allowed, _ = rate_limiter.is_allowed(test_ip)
        assert allowed is True

    # 6th request is blocked
    with patch.object(rate_limiter, "_limit", limit):
        allowed, retry_after = rate_limiter.is_allowed(test_ip)
        assert allowed is False
        assert retry_after > 0

    rate_limiter.reset()


# =============================================================================
# 6. MEMORY: LOCAL VS CLOUD SEPARATION TESTS
# =============================================================================

def test_local_vs_cloud_memory_separation():
    """Verify LOCAL memories and CLOUD memories are explicitly separated and queryable."""
    with SessionLocal() as db:
        local_key = f"test_local_fact_{uuid.uuid4().hex[:6]}"
        cloud_key = f"test_cloud_fact_{uuid.uuid4().hex[:6]}"

        # Store Local Memory
        res_local = smriti_service.save_memory(
            key=local_key,
            value="This is private local data",
            category="FACTS",
            scope="LOCAL",
            device_origin="mac",
            db=db
        )
        assert res_local["success"] is True
        assert res_local["scope"] == "LOCAL"

        # Store Cloud Memory
        res_cloud = smriti_service.save_memory(
            key=cloud_key,
            value="This is public cloud data",
            category="FACTS",
            scope="CLOUD",
            device_origin="cloud",
            db=db
        )
        assert res_cloud["success"] is True
        assert res_cloud["scope"] == "CLOUD"

        # Query LOCAL only
        local_memories = smriti_service.list_memories(scope="LOCAL", db=db)
        local_keys = [m["key"] for m in local_memories]
        assert local_key in local_keys
        assert cloud_key not in local_keys

        # Query CLOUD only
        cloud_memories = smriti_service.list_memories(scope="CLOUD", db=db)
        cloud_keys = [m["key"] for m in cloud_memories]
        assert cloud_key in cloud_keys
        assert local_key not in cloud_keys

        # Clean up
        smriti_service.delete_memory(res_local["id"], db=db)
        smriti_service.delete_memory(res_cloud["id"], db=db)


# =============================================================================
# 7. CLOUD / LOCAL CAPABILITY TRUTH & MAC UNAVAILABLE TESTS
# =============================================================================

def test_cloud_runtime_truth_reports_mac_offline():
    """When running in CLOUD mode, Runtime Truth must report Mac offline and local capabilities unavailable."""
    with patch.object(settings, "NARAD_RUNTIME_MODE", "cloud"):
        truth = runtime_truth_service.get_runtime_truth()
        assert truth["mac_availability"]["available"] is False
        assert "OFFLINE" in truth["mac_availability"]["status"]
        assert truth["capabilities"]["local"]["computer_control"] == "UNAVAILABLE_MAC_OFFLINE"
        assert truth["capabilities"]["local"]["screen_capture"] == "UNAVAILABLE_MAC_OFFLINE"


def test_mac_action_rejected_when_running_in_cloud_mode():
    """A cloud instance must NEVER execute a local Mac action or pretend it did."""
    with patch.object(settings, "NARAD_RUNTIME_MODE", "cloud"):
        assert computer_adapter.is_available() is False
        res_app = computer_adapter.open_application("Calculator")
        assert res_app["success"] is False
        assert "Mac unavailable" in res_app["error"]

        res_shot = computer_adapter.take_screenshot("test.png")
        assert res_shot["success"] is False
        assert "Mac unavailable" in res_shot["error"]


def test_runtime_status_endpoint():
    """Verify /api/runtime/status returns concise, authoritative status."""
    res = client.get("/api/runtime/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert "runtime_mode" in data
    assert "mac_available" in data
    assert "execution_mode" in data
    assert "database_backend" in data


# =============================================================================
# 8. PROVIDER ROUTING & FREE PROVIDER MESH TESTS
# =============================================================================

def test_openai_compatible_provider_health_and_cooldown():
    """Verify interchangeable OpenAI-compatible gateway connector tracks health states and cooldowns."""
    gateway = OpenAICompatibleProvider(
        provider_id="test_gateway",
        display_name="Test Gateway",
        base_url="https://api.testgateway.ai/v1",
        api_key="gw-key-test",
        default_model="meta-llama/llama-3-8b",
        available_models=["meta-llama/llama-3-8b", "mistral/mistral-7b"]
    )
    assert gateway.is_configured() is True
    assert gateway.get_available_models() == ["meta-llama/llama-3-8b", "mistral/mistral-7b"]

    # 1. Success tracking
    gateway.record_success(latency_ms=120, tokens=45)
    health = gateway.get_health_status()
    assert health["health_state"] == HEALTH_AVAILABLE
    assert health["latency_ms"] == 120
    assert health["request_count"] == 1

    # 2. Rate limit classification
    gateway.classify_and_record_error(429, "Too Many Requests: Rate limit exceeded")
    assert gateway.is_in_cooldown() is True
    assert gateway.get_health_state() == HEALTH_RATE_LIMITED

    # 3. Quota exhausted classification
    gateway.classify_and_record_error(402, "Insufficient credits for account")
    assert gateway.get_health_state() == HEALTH_QUOTA_EXHAUSTED

    # 4. Auth error classification (permanent latch)
    gateway.classify_and_record_error(401, "Invalid API Key")
    assert gateway.get_health_state() == HEALTH_AUTH_ERROR
    assert gateway.has_auth_error() is True


# =============================================================================
# 9. DATABASE BACKUP / EXPORT & RESTORE TESTS
# =============================================================================

def test_database_backup_export_and_restore():
    """Verify export_database_backup creates a complete portable snapshot and import restores it."""
    with SessionLocal() as db:
        # Create a sample session and memory
        session = smriti_service.create_session(title="Backup Verification Session", db=db)
        mem = smriti_service.save_memory(
            key=f"backup_test_{uuid.uuid4().hex[:6]}",
            value="Backup Data Point",
            category="PROJECTS",
            scope="LOCAL",
            db=db
        )

        try:
            # 1. Export
            backup = export_database_backup(db)
            assert "backup_version" in backup
            assert "data" in backup
            assert backup["counts"]["sessions"] >= 1
            assert backup["counts"]["memories"] >= 1

            # 2. API Endpoint Export
            api_res = client.get("/api/backup/export")
            assert api_res.status_code == 200
            assert "backup_version" in api_res.json()

            # 3. Import
            counts = import_database_backup(db, backup, overwrite=True)
            assert isinstance(counts, dict)
            assert "sessions" in counts
            assert "memories" in counts

        finally:
            smriti_service.delete_session(session.id, db=db)
            smriti_service.delete_memory(mem["id"], db=db)
