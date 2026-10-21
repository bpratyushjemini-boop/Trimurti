"""
NARAD Phase 2.5 / Phase 3.5 — Local Node API Router.
Enables a self-hosted Mac laptop to register, send periodic heartbeats,
receive safe commands via relay queue, and return auditable execution results.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.services.node_registry import node_registry
from app.api.v1.schemas import (
    NodeHeartbeatRequest,
    NodeHeartbeatResponse,
    NodeStatusResponse,
    NodeActionCreateRequest,
    NodeActionResponse,
    NodeActionResultRequest,
    NodeActionCancelRequest,
    NodeRevokeResponse,
    NodeTokenRotateResponse,
    ErrorResponse,
)

router = APIRouter(prefix="/nodes", tags=["v1 - Local Nodes"])


def _extract_caller_token(request: Request) -> str:
    """Extract auth token from standard headers."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[len("Bearer "):].strip()
    key_header = request.headers.get("X-Narad-Key", "")
    if key_header:
        return key_header.strip()
    node_header = request.headers.get("X-Node-Token", "")
    if node_header:
        return node_header.strip()
    return ""


@router.post(
    "/heartbeat",
    response_model=NodeHeartbeatResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
    },
    summary="Record Local Node Heartbeat / Registration"
)
def record_node_heartbeat(payload: NodeHeartbeatRequest, request: Request):
    """
    Called by a local Mac node (e.g. self-hosted laptop) to register or refresh
    its availability, hardware capabilities, and local models.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    clean_nid = payload.node_id.strip()
    if not clean_nid:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "INVALID_NODE_ID",
                    "message": "Node ID must be non-empty.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    caller_token = _extract_caller_token(request)
    res = node_registry.register_or_heartbeat(
        node_id=clean_nid,
        node_name=payload.node_name or "Local Mac Laptop",
        status=payload.status or "ONLINE",
        capabilities=payload.capabilities,
        runtime=payload.runtime,
        model_availability=payload.model_availability,
        token=caller_token or None,
    )

    if res.get("revoked") or res.get("status") == "REVOKED":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": {
                    "code": "NODE_REVOKED",
                    "message": f"Execution node '{clean_nid}' has been revoked. Re-authentication required.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    return NodeHeartbeatResponse(
        success=True,
        node_id=clean_nid,
        status=res.get("status", "ONLINE"),
        acknowledged_at=datetime.now(timezone.utc).isoformat(),
        cloud_status="ACTIVE",
    )


@router.get(
    "/status",
    response_model=NodeStatusResponse,
    summary="Check Local Node Connectivity Status"
)
def get_node_connectivity_status():
    """
    Returns whether any local Mac node is currently connected and active.
    """
    active_node = node_registry.get_active_node()
    all_nodes = node_registry.list_nodes()

    return NodeStatusResponse(
        connected=active_node is not None,
        active_node_id=active_node.get("node_id") if active_node else None,
        active_node=active_node,
        nodes=all_nodes,
    )


@router.get(
    "",
    summary="List Registered Nodes"
)
def list_registered_nodes():
    """Returns all registered local nodes and their last-seen timestamps."""
    return node_registry.list_nodes()


@router.get(
    "/{node_id}",
    responses={404: {"model": ErrorResponse}},
    summary="Get Specific Node Details"
)
def get_node_details(node_id: str, request: Request):
    """Retrieve details for a specific local execution node."""
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    node = node_registry.get_node(node_id)
    if not node:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "NODE_NOT_FOUND",
                    "message": f"Execution node '{node_id}' not found.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )
    return node


# =============================================================================
# COMMAND RELAY ENDPOINTS
# =============================================================================

@router.post(
    "/{node_id}/actions",
    response_model=NodeActionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    summary="Enqueue Command Relay Action for Node"
)
def enqueue_node_action(node_id: str, payload: NodeActionCreateRequest, request: Request):
    """
    Enqueue an approved, sandboxed action (e.g. node_status, take_screenshot,
    open_application, get_system_state) for execution on the target Mac node.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    node = node_registry.get_node(node_id)
    if not node:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "NODE_NOT_FOUND",
                    "message": f"Target execution node '{node_id}' not found.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    if not node_registry.is_node_online(node_id):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "NODE_OFFLINE",
                    "message": f"Target node '{node_id}' is currently offline. Cannot relay command.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": True,
                    "provider": None,
                }
            }
        )

    try:
        action = node_registry.enqueue_action(
            node_id=node_id,
            action_type=payload.action_type,
            payload=payload.payload,
            confirmed=bool(payload.confirmed),
            request_id=req_id,
            timeout_seconds=payload.timeout_seconds or 30,
        )
        return NodeActionResponse(**action)
    except ValueError as val_err:
        err_msg = str(val_err)
        err_code = "CONFIRMATION_REQUIRED" if "confirmation" in err_msg.lower() else "PROHIBITED_ACTION"
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": err_code,
                    "message": err_msg,
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )


@router.get(
    "/{node_id}/actions/pending",
    response_model=List[NodeActionResponse],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    summary="Poll Pending Actions for Node (Mac Node Agent)"
)
def get_pending_actions(node_id: str, request: Request):
    """
    Called outbound by the local Mac node agent to retrieve queued tasks.
    Validates node identity and token.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    caller_token = _extract_caller_token(request)

    # Authorization verification
    if not node_registry.verify_node_authorization(node_id, caller_token):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": {
                    "code": "NODE_UNAUTHORIZED",
                    "message": f"Caller is not authorized to poll actions for node '{node_id}'.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    actions = node_registry.get_pending_actions(node_id)
    return [NodeActionResponse(**a) for a in actions]


@router.get(
    "/{node_id}/actions/{action_id}",
    response_model=NodeActionResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get Action Status and Result"
)
def get_action_details(node_id: str, action_id: str, request: Request):
    """Retrieve state and result of a specific command relay action."""
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    act = node_registry.get_action(action_id)
    if not act or act.get("node_id") != node_id:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "ACTION_NOT_FOUND",
                    "message": f"Action '{action_id}' not found for node '{node_id}'.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )
    return NodeActionResponse(**act)


@router.post(
    "/{node_id}/actions/{action_id}/result",
    response_model=NodeActionResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    summary="Submit Action Execution Result (Mac Node Agent)"
)
def submit_action_result(node_id: str, action_id: str, payload: NodeActionResultRequest, request: Request):
    """
    Submitted by the local Mac agent after executing an action locally.
    Enforces idempotency and records auditable results.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    caller_token = _extract_caller_token(request)

    if not node_registry.verify_node_authorization(node_id, caller_token):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": {
                    "code": "NODE_UNAUTHORIZED",
                    "message": f"Caller is not authorized to submit results for node '{node_id}'.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    try:
        act = node_registry.submit_action_result(
            node_id=node_id,
            action_id=action_id,
            success=payload.success,
            result=payload.result,
            error=payload.error,
        )
        return NodeActionResponse(**act)
    except ValueError as val_err:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "ACTION_NOT_FOUND",
                    "message": str(val_err),
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )


@router.post(
    "/{node_id}/actions/{action_id}/cancel",
    response_model=NodeActionResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Cancel Pending Action"
)
def cancel_node_action(node_id: str, action_id: str, payload: Optional[NodeActionCancelRequest] = None, request: Request = None):
    """Cancel a pending action in the relay queue."""
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    reason = payload.reason if payload else "Cancelled by caller"
    try:
        act = node_registry.cancel_action(node_id=node_id, action_id=action_id, reason=reason)
        return NodeActionResponse(**act)
    except ValueError as val_err:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "ACTION_NOT_FOUND",
                    "message": str(val_err),
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )


# =============================================================================
# NODE CREDENTIAL REVOCATION & ROTATION
# =============================================================================

@router.post(
    "/{node_id}/revoke",
    response_model=NodeRevokeResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    summary="Revoke Node Credentials"
)
def revoke_node(node_id: str, request: Request):
    """
    Revoke node authorization. Node will be immediately blocked from polling
    or sending heartbeats. Requires master admin API key if configured.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    caller_token = _extract_caller_token(request)
    api_key = getattr(settings, "NARAD_API_KEY", "")

    # Revocation requires master API key if NARAD_API_KEY is configured
    if api_key and caller_token != api_key:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": {
                    "code": "ADMIN_REQUIRED",
                    "message": "Only administrators with NARAD_API_KEY can revoke node credentials.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    success = node_registry.revoke_node(node_id)
    if not success:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "NODE_NOT_FOUND",
                    "message": f"Node '{node_id}' not found.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    return NodeRevokeResponse(
        success=True,
        node_id=node_id,
        revoked=True,
        revoked_at=datetime.now(timezone.utc).isoformat(),
    )


@router.post(
    "/{node_id}/rotate-token",
    response_model=NodeTokenRotateResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    summary="Rotate Node Authentication Token"
)
def rotate_node_token(node_id: str, request: Request):
    """
    Generate and assign a fresh, cryptographically secure token for node_id.
    Un-revokes node if previously revoked. Requires master admin API key if configured.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    caller_token = _extract_caller_token(request)
    api_key = getattr(settings, "NARAD_API_KEY", "")

    if api_key and caller_token != api_key:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": {
                    "code": "ADMIN_REQUIRED",
                    "message": "Only administrators with NARAD_API_KEY can rotate node credentials.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    new_token = node_registry.rotate_node_token(node_id)
    return NodeTokenRotateResponse(
        success=True,
        node_id=node_id,
        token=new_token,
        rotated_at=datetime.now(timezone.utc).isoformat(),
    )
