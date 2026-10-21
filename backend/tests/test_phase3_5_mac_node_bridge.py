"""
NARAD Phase 3.5 — Secure Mac Node Bridge Test Suite.
Validates:
1. Registration & heartbeat authentication
2. Invalid, missing, and revoked node credentials
3. Credential revocation and rotation
4. Offline detection and reconnection
5. Capability truthfulness & Runtime Truth integration
6. Safe command relay roundtrip
7. Rejection of unauthorized commands (shell, sudo, tokens)
8. Explicit confirmation for sensitive operations
9. Action timeout, cancellation, and duplicate result idempotency
10. Cloud behavior when no Mac node is connected
11. Regression check against frozen Phase 3 iOS API contract
12. Local agent startup and graceful shutdown
"""

import os
import time
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.services.node_registry import node_registry
from app.services.runtime_truth import runtime_truth_service
from app.services.computer import computer_adapter
from app.node_agent.agent import MacNodeAgent
from app.node_agent.executor import SafeNodeExecutor


from datetime import datetime, timezone, timedelta
from app.db.database import SessionLocal, init_db
from app.db.models import LocalNodeRecord, NodeActionRecord


@pytest.fixture(autouse=True)
def clean_node_state():
    """Reset registry state before each test."""
    init_db()
    node_registry._cached_nodes.clear()
    node_registry._token_hashes.clear()
    node_registry._actions.clear()
    node_registry._action_events.clear()
    try:
        with SessionLocal() as db:
            db.query(LocalNodeRecord).delete()
            db.query(NodeActionRecord).delete()
            db.commit()
    except Exception:
        pass
    yield
    node_registry._cached_nodes.clear()
    node_registry._token_hashes.clear()
    node_registry._actions.clear()
    node_registry._action_events.clear()
    try:
        with SessionLocal() as db:
            db.query(LocalNodeRecord).delete()
            db.query(NodeActionRecord).delete()
            db.commit()
    except Exception:
        pass



@pytest.fixture
def client():
    return TestClient(app)


# =============================================================================
# 1. Registration & Heartbeat Authentication
# =============================================================================

def test_registration_and_heartbeat_authenticated(client):
    """Test valid node registration and heartbeat check-in."""
    res = client.post(
        "/api/v1/nodes/heartbeat",
        json={
            "node_id": "test_mac_node_01",
            "node_name": "MacBook Pro M3",
            "status": "ONLINE",
            "capabilities": {
                "computer_control": True,
                "screen_capture": True,
                "apple_music": True,
                "local_ai": True,
                "ollama": True,
            },
            "runtime": {"os": "macOS", "arch": "arm64"},
            "model_availability": ["qwen3.5:0.8b"],
        },
        headers={"X-Node-Token": "test_node_token_123"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["node_id"] == "test_mac_node_01"
    assert data["status"] == "ONLINE"
    assert "acknowledged_at" in data

    # Verify node status endpoint
    status_res = client.get("/api/v1/nodes/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["connected"] is True
    assert status_data["active_node_id"] == "test_mac_node_01"


# =============================================================================
# 2. Invalid & Missing Node Credentials
# =============================================================================

def test_invalid_and_missing_node_credentials(client, monkeypatch):
    """Verify unauthorized requests are rejected when security is active."""
    monkeypatch.setattr(settings, "NARAD_API_KEY", "master_admin_secret_key")
    monkeypatch.setattr(settings, "NARAD_NODE_TOKEN", "dedicated_node_token_abc")

    # 1. Missing credentials on protected route
    res_missing = client.get("/api/v1/nodes")
    assert res_missing.status_code == 401
    assert res_missing.json()["error"]["code"] == "AUTH_REQUIRED"

    # 2. Invalid token
    res_invalid = client.get("/api/v1/nodes", headers={"X-Node-Token": "wrong_token"})
    assert res_invalid.status_code == 401

    # 3. Valid node token succeeds
    res_valid = client.get("/api/v1/nodes", headers={"X-Node-Token": "dedicated_node_token_abc"})
    assert res_valid.status_code == 200

    # 4. Valid master API key also succeeds
    res_admin = client.get("/api/v1/nodes", headers={"X-Narad-Key": "master_admin_secret_key"})
    assert res_admin.status_code == 200


# =============================================================================
# 3. Node Credential Revocation & Safe Rotation
# =============================================================================

def test_node_credential_revocation_and_rotation(client, monkeypatch):
    """Test credential revocation blocks the node, and rotation issues new token."""
    monkeypatch.setattr(settings, "NARAD_API_KEY", "admin_key_999")

    # 1. Admin provisions token for the node
    rotate_init = client.post(
        "/api/v1/nodes/node_to_revoke/rotate-token",
        headers={"X-Narad-Key": "admin_key_999"}
    )
    assert rotate_init.status_code == 200
    initial_token = rotate_init.json()["token"]

    # 2. Node registers with its provisioned token
    reg = client.post(
        "/api/v1/nodes/heartbeat",
        json={"node_id": "node_to_revoke", "node_name": "Test Node", "status": "ONLINE"},
        headers={"X-Node-Token": initial_token}
    )
    assert reg.status_code == 200

    # 3. Non-admin node token cannot revoke (requires admin key -> 403)
    revoke_unauthorized = client.post(
        "/api/v1/nodes/node_to_revoke/revoke",
        headers={"X-Node-Token": initial_token}
    )
    assert revoke_unauthorized.status_code == 403
    assert revoke_unauthorized.json()["error"]["code"] == "ADMIN_REQUIRED"

    revoke_res = client.post(
        "/api/v1/nodes/node_to_revoke/revoke",
        headers={"X-Narad-Key": "admin_key_999"}
    )
    assert revoke_res.status_code == 200
    assert revoke_res.json()["revoked"] is True

    # 4. Subsequent heartbeat from revoked node is rejected (401 invalid token or 403 revoked)
    h_blocked = client.post(
        "/api/v1/nodes/heartbeat",
        json={"node_id": "node_to_revoke", "status": "ONLINE"},
        headers={"X-Node-Token": initial_token}
    )
    assert h_blocked.status_code in (401, 403)


    # 4. Rotate token for the node
    rotate_res = client.post(
        "/api/v1/nodes/node_to_revoke/rotate-token",
        headers={"X-Narad-Key": "admin_key_999"}
    )
    assert rotate_res.status_code == 200
    new_token = rotate_res.json()["token"]
    assert new_token.startswith("node_")

    # 5. Node can now authenticate with the rotated token
    h_restored = client.post(
        "/api/v1/nodes/heartbeat",
        json={"node_id": "node_to_revoke", "status": "ONLINE"},
        headers={"X-Node-Token": new_token}
    )
    assert h_restored.status_code == 200
    assert h_restored.json()["status"] == "ONLINE"


# =============================================================================
# 4. Offline Detection and Reconnection
# =============================================================================

def test_offline_detection_and_reconnection(client):
    """Test node automatically transitions offline after heartbeat timeout expires."""
    # 1. Send heartbeat
    client.post(
        "/api/v1/nodes/heartbeat",
        json={"node_id": "node_offline_test", "node_name": "Test Node", "status": "ONLINE"}
    )
    assert node_registry.is_local_node_connected() is True

    # 2. Simulate heartbeat timeout (>120s)
    cached = node_registry.get_node("node_offline_test")
    cached["last_seen_epoch"] = time.time() - 150.0
    with SessionLocal() as db:
        rec = db.query(LocalNodeRecord).filter(LocalNodeRecord.node_id == "node_offline_test").first()
        if rec:
            rec.last_seen = datetime.now(timezone.utc) - timedelta(seconds=150)
            db.commit()


    # Node is now offline
    assert node_registry.is_local_node_connected() is False
    status_res = client.get("/api/v1/nodes/status").json()
    assert status_res["connected"] is False

    # 3. Node reconnects with a fresh heartbeat
    client.post(
        "/api/v1/nodes/heartbeat",
        json={"node_id": "node_offline_test", "status": "ONLINE"}
    )
    assert node_registry.is_local_node_connected() is True
    assert client.get("/api/v1/nodes/status").json()["connected"] is True


# =============================================================================
# 5. Capability Truthfulness & Runtime Truth Integration
# =============================================================================

def test_capability_truthfulness_and_runtime_truth(client, monkeypatch):
    """Verify runtime truth accurately reflects online/offline status and genuine caps."""
    monkeypatch.setattr(settings, "NARAD_RUNTIME_MODE", "cloud")

    # 1. When Mac node is OFFLINE:
    truth_offline = runtime_truth_service.get_runtime_truth()
    assert truth_offline["mac_availability"]["available"] is False
    assert "OFFLINE" in truth_offline["mac_availability"]["status"]
    assert truth_offline["capabilities"]["local"]["computer_control"] == "UNAVAILABLE_MAC_OFFLINE"
    assert truth_offline["capabilities"]["local"]["screen_capture"] == "UNAVAILABLE_MAC_OFFLINE"

    # Computer adapter also safely returns offline
    res_app = computer_adapter.open_application("Calculator")
    assert res_app["success"] is False
    assert "offline" in res_app["error"].lower()

    # 2. When Mac node is ONLINE with capabilities:
    client.post(
        "/api/v1/nodes/heartbeat",
        json={
            "node_id": "truth_node",
            "node_name": "Live Mac",
            "status": "ONLINE",
            "capabilities": {
                "computer_control": True,
                "screen_capture": True,
                "apple_music": True,
            }
        }
    )

    truth_online = runtime_truth_service.get_runtime_truth()
    assert truth_online["mac_availability"]["available"] is True
    assert "ONLINE" in truth_online["mac_availability"]["status"]
    assert truth_online["capabilities"]["local"]["computer_control"] == "AVAILABLE"
    assert truth_online["capabilities"]["local"]["screen_capture"] == "AVAILABLE"


# =============================================================================
# 6. Safe Command Relay Roundtrip
# =============================================================================

def test_command_relay_roundtrip(client):
    """Test enqueuing an action, polling it from the node, and submitting the result."""
    # 1. Register online node
    client.post(
        "/api/v1/nodes/heartbeat",
        json={"node_id": "relay_node_01", "node_name": "Relay Mac", "status": "ONLINE"}
    )

    # 2. Cloud enqueues action
    action_res = client.post(
        "/api/v1/nodes/relay_node_01/actions",
        json={
            "action_type": "node_status",
            "payload": {},
        }
    )
    assert action_res.status_code == 201
    act_data = action_res.json()
    action_id = act_data["action_id"]
    assert act_data["status"] == "PENDING"

    # 3. Node agent polls pending actions
    pending_res = client.get("/api/v1/nodes/relay_node_01/actions/pending")
    assert pending_res.status_code == 200
    pending_list = pending_res.json()
    assert len(pending_list) == 1
    assert pending_list[0]["action_id"] == action_id

    # 4. Node agent executes via executor and submits result
    executor = SafeNodeExecutor()
    exec_res = executor.execute("node_status", {})
    assert exec_res["success"] is True

    submit_res = client.post(
        f"/api/v1/nodes/relay_node_01/actions/{action_id}/result",
        json={
            "success": True,
            "result": exec_res,
        }
    )
    assert submit_res.status_code == 200
    assert submit_res.json()["status"] == "COMPLETED"

    # 5. Check action status
    detail_res = client.get(f"/api/v1/nodes/relay_node_01/actions/{action_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["status"] == "COMPLETED"
    assert detail_res.json()["result"]["platform"] is not None


# =============================================================================
# 7. Rejection of Unauthorized Commands
# =============================================================================

def test_rejection_of_unauthorized_commands(client):
    """Ensure arbitrary shell execution, dangerous tokens, and unlisted apps are rejected."""
    client.post(
        "/api/v1/nodes/heartbeat",
        json={"node_id": "security_test_node", "status": "ONLINE"}
    )

    # 1. Arbitrary shell execution action is blocked at API level
    bad_action_res = client.post(
        "/api/v1/nodes/security_test_node/actions",
        json={
            "action_type": "run_shell_script",
            "payload": {"cmd": "rm -rf /"},
        }
    )
    assert bad_action_res.status_code == 400
    assert bad_action_res.json()["error"]["code"] == "PROHIBITED_ACTION"

    # 2. SafeNodeExecutor rejects dangerous tokens and un-allowlisted apps
    executor = SafeNodeExecutor()
    res_shell = executor.execute("run_bash", {"cmd": "sudo whoami"})
    assert res_shell["success"] is False
    assert res_shell["error"] == "ACTION_PROHIBITED"

    res_app_blocked = executor.execute("open_application", {"application": "SomeMaliciousBinary; rm -rf"})
    assert res_app_blocked["success"] is False
    assert "PROHIBITED_TOKEN" in res_app_blocked["error"] or "NOT_ALLOWLISTED" in res_app_blocked["error"]


# =============================================================================
# 8. Explicit Confirmation for Sensitive Operations
# =============================================================================

def test_explicit_confirmation_for_sensitive_operations(client):
    """Screen capture without explicit confirmation must be rejected."""
    client.post(
        "/api/v1/nodes/heartbeat",
        json={"node_id": "confirm_test_node", "status": "ONLINE"}
    )

    # 1. Enqueue take_screenshot without confirmation -> Rejected
    unconfirmed_res = client.post(
        "/api/v1/nodes/confirm_test_node/actions",
        json={
            "action_type": "take_screenshot",
            "payload": {},
            "confirmed": False,
        }
    )
    assert unconfirmed_res.status_code == 400
    assert unconfirmed_res.json()["error"]["code"] == "CONFIRMATION_REQUIRED"

    # 2. Enqueue take_screenshot with confirmation -> Accepted
    confirmed_res = client.post(
        "/api/v1/nodes/confirm_test_node/actions",
        json={
            "action_type": "take_screenshot",
            "payload": {"filename": "test.png"},
            "confirmed": True,
        }
    )
    assert confirmed_res.status_code == 201
    assert confirmed_res.json()["confirmed"] is True

    # 3. SafeNodeExecutor also rejects unconfirmed take_screenshot
    executor = SafeNodeExecutor()
    exec_unconfirmed = executor.execute("take_screenshot", {}, confirmed=False)
    assert exec_unconfirmed["success"] is False
    assert exec_unconfirmed["error"] == "CONFIRMATION_REQUIRED"


# =============================================================================
# 9. Action Timeout, Cancellation, and Duplicate Idempotency
# =============================================================================

def test_action_cancellation_and_duplicate_idempotency(client):
    """Test action cancellation and verify submitting duplicate results is idempotent."""
    client.post(
        "/api/v1/nodes/heartbeat",
        json={"node_id": "cancel_node_01", "status": "ONLINE"}
    )

    action_res = client.post(
        "/api/v1/nodes/cancel_node_01/actions",
        json={"action_type": "node_status"}
    )
    action_id = action_res.json()["action_id"]

    # Cancel action
    cancel_res = client.post(
        f"/api/v1/nodes/cancel_node_01/actions/{action_id}/cancel",
        json={"reason": "User changed mind"}
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # Idempotent result submission: submitting result to cancelled action returns current status without crash
    dup_res = client.post(
        f"/api/v1/nodes/cancel_node_01/actions/{action_id}/result",
        json={"success": True, "result": {"done": True}}
    )
    assert dup_res.status_code == 200
    assert dup_res.json()["status"] == "CANCELLED"


# =============================================================================
# 10. Cloud Behavior When No Mac Node Connected
# =============================================================================

def test_cloud_behavior_when_no_mac_connected(client):
    """Attempting to dispatch action to non-existent or offline node returns 404/503."""
    # Non-existent node
    res_404 = client.post(
        "/api/v1/nodes/non_existent_node/actions",
        json={"action_type": "node_status"}
    )
    assert res_404.status_code == 404
    assert res_404.json()["error"]["code"] == "NODE_NOT_FOUND"

    # Offline node
    client.post(
        "/api/v1/nodes/heartbeat",
        json={"node_id": "sleeping_node", "status": "OFFLINE"}
    )
    res_offline = client.post(
        "/api/v1/nodes/sleeping_node/actions",
        json={"action_type": "node_status"}
    )
    assert res_offline.status_code == 503
    assert res_offline.json()["error"]["code"] == "NODE_OFFLINE"


# =============================================================================
# 11. Regression Check: Existing Phase 3 iOS API Contract
# =============================================================================

def test_regression_phase3_ios_api_contract(client):
    """Verify all existing Phase 3 routes remain completely intact and functional."""
    # Health and Ready
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
    assert client.get("/api/v1/runtime/status").status_code == 200
    assert client.post("/api/v1/auth/verify").status_code == 200


    # Nodes existing endpoints
    h_res = client.post(
        "/api/v1/nodes/heartbeat",
        json={
            "node_id": "ios_contract_node",
            "node_name": "iOS Paired Mac",
            "status": "ONLINE",
            "capabilities": {"computer_control": True},
        }
    )
    assert h_res.status_code == 200
    assert h_res.json()["success"] is True

    s_res = client.get("/api/v1/nodes/status")
    assert s_res.status_code == 200
    assert s_res.json()["connected"] is True

    l_res = client.get("/api/v1/nodes")
    assert l_res.status_code == 200
    assert any(n["node_id"] == "ios_contract_node" for n in l_res.json())

    d_res = client.get("/api/v1/nodes/ios_contract_node")
    assert d_res.status_code == 200
    assert d_res.json()["node_name"] == "iOS Paired Mac"


# =============================================================================
# 12. Local Agent Startup and Graceful Shutdown
# =============================================================================

def test_local_agent_startup_and_graceful_shutdown(client):
    """Test MacNodeAgent sends genuine capabilities and shuts down cleanly."""
    # Create test agent pointing to in-process test client
    agent = MacNodeAgent(
        server_url="http://testserver",
        node_id="mac_agent_unit_test",
        node_name="Unit Test Laptop",
    )

    # Monkeypatch agent's internal _send_request to route to FastAPI TestClient
    def mock_send_request(method, path, payload=None, timeout=10.0):
        if method == "POST":
            r = client.post(path, json=payload)
        else:
            r = client.get(path)
        data = r.json()
        if isinstance(data, dict):
            data["status_code"] = r.status_code
        return data

    agent._send_request = mock_send_request

    # 1. Startup: send initial heartbeat
    res_online = agent.send_heartbeat(status="ONLINE")
    assert res_online["status_code"] == 200
    assert res_online["status"] == "ONLINE"
    assert node_registry.is_local_node_connected() is True

    # 2. Shutdown: sends OFFLINE notification
    agent.shutdown()
    node = node_registry.get_node("mac_agent_unit_test")
    assert node["status"] == "OFFLINE"
    # Immediately offline with zero timeout lag
    assert node_registry.is_local_node_connected() is False


# =============================================================================
# 13. Node-Agent HTTP Error-Handling & False ONLINE Prevention
# =============================================================================

def test_agent_heartbeat_404_never_reports_online():
    """
    CRITICAL: Verify the node agent treats HTTP 404 (e.g. Render edge routing 'no-server'
    or missing route) as an explicit failure, sets is_online=False, raises ConnectionError,
    and NEVER reports the node as ONLINE.
    """
    agent = MacNodeAgent(
        server_url="https://narad-gqtq.onrender.com",
        node_id="mac_test_404_node",
    )

    # Mock _send_request returning HTTP 404 from Render
    def mock_404_response(method, path, payload=None, timeout=30.0):
        return {
            "status_code": 404,
            "error": "HTTP Error 404: Not Found",
            "detail": "Not Found",
        }

    agent._send_request = mock_404_response

    # Heartbeat must fail and raise ConnectionError
    with pytest.raises(ConnectionError) as exc_info:
        agent.send_heartbeat(status="ONLINE")

    assert "404" in str(exc_info.value)
    # Agent must NEVER be marked online
    assert agent.is_online is False
    assert agent.last_confirmed_status is None


def test_agent_heartbeat_auth_failure_401_403_never_reports_online():
    """Verify HTTP 401 Unauthorized or 403 Forbidden is never treated as ONLINE."""
    agent = MacNodeAgent(
        server_url="https://cloud.narad.ai",
        node_id="mac_test_auth_fail",
    )

    # 1. Test 401
    agent._send_request = lambda m, p, payload=None, timeout=30.0: {
        "status_code": 401,
        "error": {"code": "AUTH_REQUIRED", "message": "Invalid credentials"},
    }
    with pytest.raises(ConnectionError) as exc_401:
        agent.send_heartbeat(status="ONLINE")
    assert "401" in str(exc_401.value)
    assert agent.is_online is False

    # 2. Test 403 (e.g. node revoked)
    agent._send_request = lambda m, p, payload=None, timeout=30.0: {
        "status_code": 403,
        "error": {"code": "NODE_REVOKED", "message": "Execution node revoked"},
    }
    with pytest.raises(ConnectionError) as exc_403:
        agent.send_heartbeat(status="ONLINE")
    assert "403" in str(exc_403.value)
    assert agent.is_online is False


def test_agent_heartbeat_server_error_500_503_never_reports_online():
    """Verify HTTP 500 or 503 is never treated as ONLINE."""
    agent = MacNodeAgent(
        server_url="https://cloud.narad.ai",
        node_id="mac_test_500",
    )
    agent._send_request = lambda m, p, payload=None, timeout=30.0: {
        "status_code": 503,
        "error": "Service Unavailable",
    }
    with pytest.raises(ConnectionError) as exc_503:
        agent.send_heartbeat(status="ONLINE")
    assert "503" in str(exc_503.value)
    assert agent.is_online is False


def test_agent_heartbeat_mismatched_identity_rejected():
    """Even on HTTP 200, if cloud confirms a different node_id or status != ONLINE, reject."""
    agent = MacNodeAgent(
        server_url="https://cloud.narad.ai",
        node_id="expected_node_id",
    )
    # Cloud responds 200 OK, but returned node_id doesn't match
    agent._send_request = lambda m, p, payload=None, timeout=30.0: {
        "status_code": 200,
        "success": True,
        "node_id": "wrong_node_id",
        "status": "ONLINE",
    }
    with pytest.raises(ConnectionError):
        agent.send_heartbeat(status="ONLINE")
    assert agent.is_online is False


def test_agent_skips_action_polling_when_offline():
    """When node is offline, poll_and_execute_actions must not perform any outbound requests."""
    agent = MacNodeAgent(
        server_url="https://cloud.narad.ai",
        node_id="offline_poller",
    )
    assert agent.is_online is False

    poll_called = False
    def mock_poll(method, path, payload=None, timeout=30.0):
        nonlocal poll_called
        poll_called = True
        return []

    agent._send_request = mock_poll
    agent.poll_and_execute_actions()
    assert poll_called is False, "Agent should not poll pending actions when offline"


def test_agent_polling_http_error_raises_connection_error():
    """When action polling returns HTTP 404 or 401, ConnectionError must be raised to trigger backoff."""
    agent = MacNodeAgent(
        server_url="https://cloud.narad.ai",
        node_id="error_poller",
    )
    agent.is_online = True

    agent._send_request = lambda m, p, payload=None, timeout=30.0: {
        "status_code": 404,
        "error": "Node not found",
    }

    with pytest.raises(ConnectionError) as exc:
        agent.poll_and_execute_actions()
    assert "404" in str(exc.value)


def test_agent_default_server_url(monkeypatch):
    """
    CRITICAL REGRESSION: Verify default cloud server URL points to the live deployment
    https://narad-gqtp.onrender.com and correctly respects NARAD_SERVER_URL / NARAD_CLOUD_URL env vars.
    """
    monkeypatch.delenv("NARAD_SERVER_URL", raising=False)
    monkeypatch.delenv("NARAD_CLOUD_URL", raising=False)

    # 1. Default should point to narad-gqtp
    agent_default = MacNodeAgent()
    assert agent_default.server_url == "https://narad-gqtp.onrender.com"

    # 2. Overridden via constructor
    agent_custom = MacNodeAgent(server_url="https://custom.narad.ai/")
    assert agent_custom.server_url == "https://custom.narad.ai"

    # 3. Overridden via NARAD_SERVER_URL
    monkeypatch.setenv("NARAD_SERVER_URL", "https://env-server.narad.ai")
    agent_env = MacNodeAgent()
    assert agent_env.server_url == "https://env-server.narad.ai"


def test_agent_paths_match_openapi_contract():
    """
    REGRESSION: Verify all paths invoked by MacNodeAgent are exact members
    of the OpenAPI route table registered on the FastAPI app.
    """
    openapi = app.openapi()
    api_paths = set(openapi.get("paths", {}).keys())

    expected_agent_endpoints = [
        "/api/v1/nodes/heartbeat",
        "/api/v1/nodes/{node_id}/actions/pending",
        "/api/v1/nodes/{node_id}/actions/{action_id}/result",
    ]

    for ep in expected_agent_endpoints:
        assert ep in api_paths, f"Node agent endpoint '{ep}' missing from FastAPI route table"
