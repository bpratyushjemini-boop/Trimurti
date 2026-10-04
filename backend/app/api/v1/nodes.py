"""
NARAD Phase 2.5 / Phase 3 — Local Node API Router.
Enables a self-hosted Mac laptop to register, send periodic heartbeats,
and expose local capabilities (computer control, screen capture, local Ollama)
to the Cloud NARAD instance without modifying the iOS client.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.services.node_registry import node_registry
from app.api.v1.schemas import (
    NodeHeartbeatRequest,
    NodeHeartbeatResponse,
    NodeStatusResponse,
    ErrorResponse,
)

router = APIRouter(prefix="/nodes", tags=["v1 - Local Nodes"])


@router.post(
    "/heartbeat",
    response_model=NodeHeartbeatResponse,
    responses={400: {"model": ErrorResponse}},
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

    res = node_registry.register_or_heartbeat(
        node_id=clean_nid,
        node_name=payload.node_name or "Local Mac Laptop",
        status=payload.status or "ONLINE",
        capabilities=payload.capabilities,
        runtime=payload.runtime,
        model_availability=payload.model_availability,
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
