"""
NARAD Phase 3 — iOS Client API Contract Test Suite.
Validates all mobile-facing endpoints under /api/v1/...
Tests:
  1. Single-user Mobile Auth & Security Handshake
  2. Error Contract (machine-readable code, message, request_id, retryable)
  3. Chat API (send, stream, cancel, session history, delete)
  4. Task API (create, list, status, progress, events, cancel, retry, result)
  5. Runtime API & Operational Modes (ONLINE, CLOUD, LOCAL, OFFLINE, DEGRADED, Mac availability boundary)
  6. Memory API (status, recall, cloud-default write, delete by id & key)
  7. Voice API (status, transcribe, synthesize)
  8. Notifications & APNs Event Architecture (register, pending, acknowledge, stream)
"""

import io
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.services.agent_brain import agent_brain
from app.services.event_system import event_system, EventType

client = TestClient(app)


# =============================================================================
# 1. AUTHENTICATION & SECURITY CONTRACT TESTS
# =============================================================================

def test_auth_verify_unconfigured():
    """When server has no NARAD_API_KEY, auth verify succeeds automatically."""
    with patch.object(settings, "NARAD_API_KEY", ""):
        res = client.post("/api/v1/auth/verify")
        assert res.status_code == 200
        data = res.json()
        assert data["authenticated"] is True
        assert data["user"] == "owner"
        assert data["system"] == settings.APP_NAME


def test_auth_verify_success_with_bearer():
    """Valid Bearer token succeeds."""
    with patch.object(settings, "NARAD_API_KEY", "test_secret_ios_key_xyz"):
        res = client.post(
            "/api/v1/auth/verify",
            headers={"Authorization": "Bearer test_secret_ios_key_xyz"}
        )
        assert res.status_code == 200
        assert res.json()["authenticated"] is True


def test_auth_verify_failure_invalid_token():
    """Invalid token returns 401 with standard ErrorResponse contract."""
    with patch.object(settings, "NARAD_API_KEY", "test_secret_ios_key_xyz"):
        res = client.post(
            "/api/v1/auth/verify",
            headers={"Authorization": "Bearer wrong_token"}
        )
        assert res.status_code == 401
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] == "AUTH_REQUIRED"
        assert "request_id" in data["error"]
        assert data["error"]["retryable"] is False


def test_v1_endpoint_enforces_auth_when_configured():
    """Protected v1 endpoints reject missing or invalid auth with ErrorResponse."""
    with patch.object(settings, "NARAD_API_KEY", "test_secret_ios_key_xyz"):
        res = client.post(
            "/api/v1/chat/send",
            json={"message": "Hello from iOS"},
            headers={"Authorization": "Bearer invalid_key"}
        )
        assert res.status_code == 401
        err = res.json()["error"]
        assert err["code"] == "AUTH_REQUIRED"
        assert err["request_id"].startswith("req_")


def test_v1_validation_error_contract():
    """Malformed body on v1 endpoint returns 422 with consistent ErrorResponse."""
    res = client.post(
        "/api/v1/chat/send",
        json={"wrong_field": 123}
    )
    assert res.status_code == 422
    err = res.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "request_id" in err


# =============================================================================
# 2. RUNTIME & OPERATIONAL MODES TESTS
# =============================================================================

def test_runtime_status_online_default():
    """Default runtime status returns ONLINE operational state with capabilities."""
    agent_brain.set_mode("AUTO")
    res = client.get("/api/v1/runtime/status")
    assert res.status_code == 200
    data = res.json()
    assert data["app_name"] == settings.APP_NAME
    assert data["api_version"] == "v1"
    assert data["operational_status"] in ("ONLINE", "CLOUD", "LOCAL")
    assert "local_capabilities" in data
    assert "cloud_capabilities" in data
    assert "database_backend" in data
    assert "autonomy_level" in data
    assert isinstance(data["autonomy_level"], int)


def test_runtime_capabilities_endpoint():
    """Dynamic capabilities matrix endpoint returns offline/local capabilities."""
    res = client.get("/api/v1/runtime/capabilities")
    assert res.status_code == 200
    caps = res.json()
    assert "offline" in caps
    assert "local_first" in caps


def test_runtime_mode_offline():
    """In OFFLINE mode, operational_status is OFFLINE and cloud inference is UNAVAILABLE."""
    agent_brain.set_mode("OFFLINE")
    try:
        res = client.get("/api/v1/runtime/status")
        assert res.status_code == 200
        data = res.json()
        assert data["operational_status"] == "OFFLINE"
        assert data["network_state"] == "OFFLINE"
        assert data["cloud_capabilities"]["cloud_llm_inference"] == "UNAVAILABLE"
    finally:
        agent_brain.set_mode("AUTO")


def test_runtime_mode_local_only():
    """In LOCAL_ONLY mode, operational_status is LOCAL."""
    agent_brain.set_mode("LOCAL_ONLY")
    try:
        res = client.get("/api/v1/runtime/status")
        assert res.status_code == 200
        data = res.json()
        assert data["operational_status"] == "LOCAL"
    finally:
        agent_brain.set_mode("AUTO")


def test_runtime_mode_cloud_preferred():
    """In CLOUD_PREFERRED mode, operational_status is CLOUD."""
    agent_brain.set_mode("CLOUD_PREFERRED")
    try:
        res = client.get("/api/v1/runtime/status")
        assert res.status_code == 200
        data = res.json()
        assert data["operational_status"] == "CLOUD"
    finally:
        agent_brain.set_mode("AUTO")


def test_runtime_degraded_when_db_down():
    """When database connectivity fails, operational_status is DEGRADED."""
    with patch("app.api.v1.runtime.check_db_readiness", return_value=(False, "unreachable")):
        res = client.get("/api/v1/runtime/status")
        assert res.status_code == 200
        assert res.json()["operational_status"] == "DEGRADED"
        assert res.json()["database_connected"] is False


def test_mac_unavailable_boundary():
    """When Mac is offline, local capabilities are marked UNAVAILABLE_MAC_OFFLINE."""
    mock_truth = {
        "mac_availability": {"available": False, "status": "Host Mac sleeping/offline"},
        "inference": {"execution_mode": "cloud", "provider": "groq", "model": "llama-3.3-70b-versatile"},
        "system": {"runtime_mode": "cloud"},
        "local_models": {"ollama_running": False},
        "memory": {"backend": "sqlite", "persistent": True},
        "timestamp": "2026-10-04T12:00:00Z"
    }
    with patch("app.api.v1.runtime.runtime_truth_service.get_runtime_truth", return_value=mock_truth):
        res = client.get("/api/v1/runtime/status")
        assert res.status_code == 200
        data = res.json()
        assert data["mac_available"] is False
        assert data["local_capabilities"]["computer_control"] == "UNAVAILABLE_MAC_OFFLINE"
        assert data["local_capabilities"]["screen_capture"] == "UNAVAILABLE_MAC_OFFLINE"
        assert data["local_capabilities"]["apple_music"] == "UNAVAILABLE_MAC_OFFLINE"


# =============================================================================
# 3. CHAT API CONTRACT TESTS
# =============================================================================

def test_chat_send_success():
    """Unary chat send returns valid SendMessageResponse."""
    res = client.post(
        "/api/v1/chat/send",
        json={"message": "Status report, NARAD"}
    )
    assert res.status_code == 200
    data = res.json()
    assert "response" in data
    assert data["session_id"].startswith("ses_")
    assert data["message_id"].startswith("msg_")
    assert "provider" in data
    assert "model" in data
    assert "latency_ms" in data
    assert data["status"] == "success"


def test_chat_send_empty_message_validation():
    """Empty chat message returns 400 with ErrorResponse."""
    res = client.post(
        "/api/v1/chat/send",
        json={"message": "   "}
    )
    assert res.status_code in (400, 422)
    err = res.json()["error"]
    assert err["code"] in ("EMPTY_MESSAGE", "VALIDATION_ERROR")


def test_chat_stream_sse():
    """Streaming chat returns SSE chunks with session, thinking, token, and done."""
    res = client.post(
        "/api/v1/chat/stream",
        json={"message": "Brief greeting"},
        headers={"Accept": "text/event-stream"}
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    assert res.headers.get("X-Accel-Buffering") == "no"
    
    body = res.text
    assert "event" in body
    assert "session" in body
    assert "token" in body
    assert "done" in body


def test_chat_cancel():
    """Chat cancel endpoint accepts request and returns CancelChatResponse."""
    res = client.post(
        "/api/v1/chat/cancel",
        json={"session_id": "ses_test_12345", "reason": "User dismissed view"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["session_id"] == "ses_test_12345"
    assert data["status"] == "cancelled"


def test_chat_sessions_lifecycle():
    """Full lifecycle: create session, list sessions, fetch history, delete session."""
    # 1. Create session
    c_res = client.post(
        "/api/v1/chat/sessions",
        json={"title": "iOS Contract Session"}
    )
    assert c_res.status_code == 201
    session_id = c_res.json()["session_id"]
    assert session_id.startswith("ses_")

    # 2. List sessions
    l_res = client.get("/api/v1/chat/sessions")
    assert l_res.status_code == 200
    s_ids = [s["session_id"] for s in l_res.json()]
    assert session_id in s_ids

    # 3. Add a message to session
    client.post(
        "/api/v1/chat/send",
        json={"session_id": session_id, "message": "Test dialogue turn"}
    )

    # 4. Fetch history
    h_res = client.get(f"/api/v1/chat/sessions/{session_id}")
    assert h_res.status_code == 200
    h_data = h_res.json()
    assert h_data["session_id"] == session_id
    assert len(h_data["messages"]) >= 2  # user + assistant

    # 5. Delete session
    d_res = client.delete(f"/api/v1/chat/sessions/{session_id}")
    assert d_res.status_code == 204

    # 6. Verify 404 after deletion
    g_res = client.get(f"/api/v1/chat/sessions/{session_id}")
    assert g_res.status_code == 404
    assert g_res.json()["error"]["code"] == "SESSION_NOT_FOUND"


# =============================================================================
# 4. TASK API CONTRACT TESTS
# =============================================================================

def test_task_lifecycle_create_status_progress_result():
    """Create task, query status, progress, events, and full result."""
    # 1. Create task
    t_res = client.post(
        "/api/v1/tasks",
        json={"goal": "Verify database backup integrity", "dry_run": True}
    )
    assert t_res.status_code == 201
    t_data = t_res.json()
    task_id = t_data["task_id"]
    assert task_id.startswith("tsk_") or task_id.startswith("task_")
    assert t_data["status"] in ("COMPLETED", "CREATED", "PLANNING", "EXECUTING")

    # 2. Query status
    s_res = client.get(f"/api/v1/tasks/{task_id}")
    assert s_res.status_code == 200
    assert s_res.json()["task_id"] == task_id

    # 3. Query progress
    p_res = client.get(f"/api/v1/tasks/{task_id}/progress")
    assert p_res.status_code == 200
    p_data = p_res.json()
    assert p_data["task_id"] == task_id
    assert 0 <= p_data["progress_pct"] <= 100
    assert p_data["total_steps"] >= 0

    # 4. Query events
    e_res = client.get(f"/api/v1/tasks/{task_id}/events")
    assert e_res.status_code == 200
    assert isinstance(e_res.json(), list)

    # 5. Query detailed result
    r_res = client.get(f"/api/v1/tasks/{task_id}/result")
    assert r_res.status_code == 200
    r_data = r_res.json()
    assert r_data["task_id"] == task_id
    assert "plan" in r_data
    assert "actions" in r_data
    assert "verification" in r_data


def test_task_cancellation_and_not_found():
    """Task cancel returns 404 for unknown task with ErrorResponse."""
    res = client.post(
        "/api/v1/tasks/tsk_nonexistent_xyz/cancel",
        json={"reason": "Testing cancellation"}
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "TASK_NOT_FOUND"


def test_task_retry():
    """Retry task triggers execution and links back to original task."""
    # Create first task
    c_res = client.post(
        "/api/v1/tasks",
        json={"goal": "Check network connectivity", "dry_run": True}
    )
    orig_task_id = c_res.json()["task_id"]

    # Retry task
    ret_res = client.post(f"/api/v1/tasks/{orig_task_id}/retry")
    assert ret_res.status_code == 200
    ret_data = ret_res.json()
    assert ret_data["success"] is True
    assert ret_data["original_task_id"] == orig_task_id
    assert ret_data["retry_task_id"].startswith("tsk_") or ret_data["retry_task_id"].startswith("task_")


# =============================================================================
# 5. MEMORY API CONTRACT TESTS
# =============================================================================

def test_memory_status():
    """Memory status endpoint reports record counts and tier separation."""
    res = client.get("/api/v1/memory/status")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert "total_memories" in data
    assert "local_count" in data
    assert "cloud_count" in data


def test_memory_write_and_recall_cloud_default():
    """Writing memory defaults to scope='CLOUD' and is recalled cleanly."""
    key = "ios_test_preference"
    val = "Dark mode with high contrast"
    
    # 1. Write memory
    w_res = client.post(
        "/api/v1/memory",
        json={"key": key, "value": val, "category": "PREFERENCES"}
    )
    assert w_res.status_code == 201
    w_data = w_res.json()
    assert w_data["success"] is True
    assert w_data["scope"] == "CLOUD"
    mem_id = w_data["id"]

    # 2. Recall memory
    r_res = client.post(
        "/api/v1/memory/recall",
        json={"query": "contrast preference", "scope": "CLOUD"}
    )
    assert r_res.status_code == 200
    r_data = r_res.json()
    assert r_data["count"] >= 1
    found_keys = [m.get("key") for m in r_data["memories"]]
    assert key in found_keys

    # 3. Delete memory by ID
    d_res = client.delete(f"/api/v1/memory/{mem_id}")
    assert d_res.status_code == 200
    assert d_res.json()["status"] == "deleted"


def test_memory_delete_by_key():
    """Deleting memory by entity key succeeds."""
    key = "ios_temporary_key"
    client.post("/api/v1/memory", json={"key": key, "value": "To be deleted"})
    
    d_res = client.delete(f"/api/v1/memory/key/{key}")
    assert d_res.status_code == 200
    assert d_res.json()["status"] == "deleted"


# =============================================================================
# 6. VOICE API CONTRACT TESTS
# =============================================================================

def test_voice_status():
    """Voice status endpoint exposes readiness, engine, and language support."""
    res = client.get("/api/v1/voice/status")
    assert res.status_code == 200
    data = res.json()
    assert "stt_ready" in data
    assert "tts_ready" in data
    assert "supported_languages" in data
    assert "en" in data["supported_languages"]


def test_voice_transcribe_validation():
    """Transcribe rejects empty audio files with 400 ErrorResponse."""
    fake_empty_file = io.BytesIO(b"")
    res = client.post(
        "/api/v1/voice/transcribe",
        files={"file": ("test.wav", fake_empty_file, "audio/wav")}
    )
    assert res.status_code == 400
    err = res.json()["error"]
    assert err["code"] == "INVALID_AUDIO"


def test_voice_synthesize_empty_text():
    """Empty synthesis text returns 400 ErrorResponse."""
    res = client.post(
        "/api/v1/voice/synthesize",
        json={"text": "   "}
    )
    assert res.status_code in (400, 422)
    err = res.json()["error"]
    assert err["code"] in ("EMPTY_TEXT", "VALIDATION_ERROR")


# =============================================================================
# 7. NOTIFICATIONS & APNS CONTRACT TESTS
# =============================================================================

def test_notifications_device_registration_and_validation():
    """Register iOS device APNs token."""
    # 1. Validation failure on short token
    bad_res = client.post(
        "/api/v1/notifications/register-device",
        json={"device_token": "short", "platform": "ios"}
    )
    assert bad_res.status_code in (400, 422)

    # 2. Success on valid 64-char APNs token
    good_token = "a" * 64
    reg_res = client.post(
        "/api/v1/notifications/register-device",
        json={"device_token": good_token, "platform": "ios", "app_version": "1.0.0"}
    )
    assert reg_res.status_code == 200
    r_data = reg_res.json()
    assert r_data["success"] is True
    assert r_data["device_id"].startswith("dev_")


def test_notifications_pending_and_acknowledge():
    """Emit notifiable event, observe in pending, acknowledge it, verify omission."""
    # 1. Emit a high-priority notifiable event
    test_event = event_system.emit_event(
        EventType.TASK_COMPLETED,
        title="Mission Verification Complete",
        body="All systems green.",
        priority="urgent",
        task_id="tsk_test_notif",
    )
    event_id = test_event["event_id"]

    # 2. Check pending notifications
    p_res = client.get("/api/v1/notifications/pending")
    assert p_res.status_code == 200
    p_data = p_res.json()
    pending_ids = [n["event_id"] for n in p_data["notifications"]]
    assert event_id in pending_ids

    # 3. Acknowledge notification
    ack_res = client.post(
        "/api/v1/notifications/acknowledge",
        json={"event_ids": [event_id]}
    )
    assert ack_res.status_code == 200
    assert ack_res.json()["acknowledged_count"] >= 1

    # 4. Check pending again - should no longer be present
    p_res_after = client.get("/api/v1/notifications/pending")
    after_ids = [n["event_id"] for n in p_res_after.json()["notifications"]]
    assert event_id not in after_ids
