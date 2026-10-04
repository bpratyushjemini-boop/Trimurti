"""
NARAD Phase 3 — Mobile Runtime Status & Capabilities API.
Exposes live runtime telemetry, operational status (ONLINE | CLOUD | LOCAL | OFFLINE | DEGRADED),
and strict local/cloud capability boundaries to the iOS client.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.db.database import check_db_readiness, get_db_dialect
from app.services.runtime_truth import runtime_truth_service
from app.services.agent_brain import agent_brain
from app.services.action_policy import action_policy
from app.api.v1.schemas import (
    RuntimeStatusResponse,
    LocalCapabilities,
    CloudCapabilities,
    ErrorResponse,
)

router = APIRouter(prefix="/runtime", tags=["v1 - Runtime"])


class SetModeRequest(BaseModel):
    mode: str = Field(..., description="Target mode: AUTO, LOCAL_ONLY, OFFLINE, CLOUD_PREFERRED")


@router.get(
    "/status",
    response_model=RuntimeStatusResponse,
    summary="Get Mobile-Facing Runtime & Capability Status"
)
def get_mobile_runtime_status() -> RuntimeStatusResponse:
    """
    Returns complete, non-hallucinated runtime state for the iOS application.
    Enforces strict distinction between Mac-local and cloud capabilities.
    """
    truth = runtime_truth_service.get_runtime_truth()
    db_ok, db_status = check_db_readiness()

    # 1. Determine Operational Status: ONLINE | CLOUD | LOCAL | OFFLINE | DEGRADED
    current_brain_mode = agent_brain.get_mode()
    server_runtime_mode = getattr(settings, "NARAD_RUNTIME_MODE", "hybrid").lower()

    if not db_ok:
        operational_status = "DEGRADED"
    elif current_brain_mode == "OFFLINE" or getattr(settings, "OFFLINE_MODE", False):
        operational_status = "OFFLINE"
    elif current_brain_mode == "LOCAL_ONLY" or server_runtime_mode == "local":
        operational_status = "LOCAL"
    elif server_runtime_mode == "cloud" or current_brain_mode == "CLOUD_PREFERRED":
        operational_status = "CLOUD"
    else:
        operational_status = "ONLINE"

    # 2. Local vs Cloud Capabilities Boundary
    mac_available = bool(truth.get("mac_availability", {}).get("available", False))
    mac_status = str(truth.get("mac_availability", {}).get("status", "Mac offline"))

    local_caps = LocalCapabilities(
        computer_control="AVAILABLE" if mac_available else "UNAVAILABLE_MAC_OFFLINE",
        screen_capture="AVAILABLE" if mac_available else "UNAVAILABLE_MAC_OFFLINE",
        apple_music="AVAILABLE" if mac_available else "UNAVAILABLE_MAC_OFFLINE",
        local_ai="AVAILABLE" if (mac_available and truth.get("local_models", {}).get("ollama_running", False)) else "UNAVAILABLE",
        ollama="AVAILABLE" if (mac_available and truth.get("local_models", {}).get("ollama_running", False)) else "UNAVAILABLE",
    )

    cloud_caps = CloudCapabilities(
        cloud_llm_inference="AVAILABLE" if (db_ok and operational_status != "OFFLINE") else "UNAVAILABLE",
        cloud_persistence="AVAILABLE" if db_ok else "UNAVAILABLE",
        cloud_memory="AVAILABLE" if db_ok else "UNAVAILABLE",
        web_search="AVAILABLE" if (operational_status != "OFFLINE") else "UNAVAILABLE",
        knowledge_search="AVAILABLE" if db_ok else "UNAVAILABLE",
    )

    # 3. Autonomy Mapping
    autonomy_mode_str = action_policy.get_autonomy_mode()
    autonomy_levels = {
        "CHAT_ONLY": 0,
        "SUGGEST": 1,
        "SUPERVISED": 2,
        "TASK_AUTONOMY": 3,
    }
    autonomy_level_int = autonomy_levels.get(autonomy_mode_str, 2)

    # 4. Network & Execution Mode
    network_state = "OFFLINE" if operational_status == "OFFLINE" else "CONNECTED"
    exec_mode = truth.get("inference", {}).get("execution_mode", "CLOUD").upper()

    subsystems = {
        "database": "CONNECTED" if db_ok else "DEGRADED",
        "memory": "READY" if db_ok else "DEGRADED",
        "routing": "READY",
        "security": "ENFORCED",
        "events": "ACTIVE",
        "mac_bridge": "CONNECTED" if mac_available else "OFFLINE",
    }

    return RuntimeStatusResponse(
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        api_version="v1",
        operational_status=operational_status,
        execution_mode=exec_mode,
        network_state=network_state,
        active_provider=truth.get("inference", {}).get("provider", "groq"),
        active_model=truth.get("inference", {}).get("model", "llama-3.3-70b-versatile"),
        autonomy_level=autonomy_level_int,
        autonomy_mode=autonomy_mode_str,
        mac_available=mac_available,
        mac_status=mac_status,
        database_backend=get_db_dialect(),
        database_connected=db_ok,
        local_capabilities=local_caps,
        cloud_capabilities=cloud_caps,
        subsystems=subsystems,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/capabilities",
    summary="Dynamic Capability Matrix"
)
def get_mobile_capabilities() -> Dict[str, Any]:
    """Returns dynamic capabilities matrix reflecting current local and cloud reach."""
    return agent_brain.get_capabilities_matrix()


@router.post(
    "/mode",
    summary="Change Agent Brain Runtime Mode"
)
def set_mobile_runtime_mode(
    req: Optional[SetModeRequest] = None,
    mode: Optional[str] = Query(None, description="AUTO, LOCAL_ONLY, OFFLINE, CLOUD_PREFERRED")
) -> Dict[str, Any]:
    """Set active operation mode for the Agent Brain."""
    target_mode = (req.mode if req else None) or mode or "AUTO"
    new_mode = agent_brain.set_mode(target_mode)
    return {"success": True, "mode": new_mode, "status": "updated"}
