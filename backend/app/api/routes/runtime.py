"""
NARAD Runtime Truth API Routes.
Exposes live, verified runtime infrastructure state for the HUD and telemetry consumers.
"""

from fastapi import APIRouter, Query, Response
from typing import Optional, Dict, Any

from app.services.runtime_truth import runtime_truth_service

router = APIRouter(prefix="/runtime", tags=["RuntimeTruth"])


@router.get("/truth")
def get_runtime_truth(
    provider: Optional[str] = Query(None, description="Optional provider override to inspect"),
    model: Optional[str] = Query(None, description="Optional model override to inspect"),
    session_id: Optional[str] = Query(None, description="Optional active chat session ID"),
) -> Dict[str, Any]:
    """
    Returns the canonical Runtime Truth JSON object.
    Every field is sourced from live system state with ZERO model hallucination.
    """
    return runtime_truth_service.get_runtime_truth(
        requested_provider=provider,
        requested_model=model,
        session_id=session_id,
    )


@router.get("/report")
def get_runtime_report(
    provider: Optional[str] = Query(None, description="Optional provider override to inspect"),
    model: Optional[str] = Query(None, description="Optional model override to inspect"),
    session_id: Optional[str] = Query(None, description="Optional active chat session ID"),
):
    """
    Returns the human-readable standard runtime report text.
    Format follows NARAD Phase 2 Section 11 specifications.
    """
    truth = runtime_truth_service.get_runtime_truth(
        requested_provider=provider,
        requested_model=model,
        session_id=session_id,
    )
    report_str = runtime_truth_service.format_runtime_report(truth)
    return Response(content=report_str, media_type="text/plain")


@router.get("/capabilities")
def get_runtime_capabilities() -> Dict[str, Any]:
    """
    Returns the dynamic offline and local-first capability matrix.
    Generated dynamically per Section 15 specifications without fake availability.
    """
    from app.services.agent_brain import agent_brain
    return agent_brain.get_capabilities_matrix()


from pydantic import BaseModel

class ModeRequest(BaseModel):
    mode: str

@router.post("/mode")
def set_runtime_mode(
    request: Optional[ModeRequest] = None,
    mode: Optional[str] = Query(None, description="Target mode: AUTO, LOCAL_ONLY, OFFLINE, CLOUD_PREFERRED")
) -> Dict[str, Any]:
    """Set the active operation mode for the Agent Brain."""
    from app.services.agent_brain import agent_brain
    target = (request.mode if request else None) or mode or "AUTO"
    new_mode = agent_brain.set_mode(target)
    return {"success": True, "mode": new_mode, "status": "updated"}


@router.get("/status")
def get_runtime_status() -> Dict[str, Any]:
    """
    Returns high-level runtime status for cloud operations and monitoring:
    runtime_mode, mac_availability, execution_mode, db_dialect, active route.
    """
    truth = runtime_truth_service.get_runtime_truth()
    return {
        "status": "online",
        "app": truth["identity"]["name"],
        "version": truth["identity"]["version"],
        "runtime_mode": truth["system"].get("runtime_mode", "hybrid"),
        "mac_available": truth["mac_availability"]["available"],
        "mac_status": truth["mac_availability"]["status"],
        "execution_mode": truth["inference"]["execution_mode"],
        "active_provider": truth["inference"]["provider"],
        "active_model": truth["inference"]["model"],
        "database_backend": truth["memory"]["backend"],
        "database_persistent": truth["memory"]["persistent"],
        "timestamp": truth["timestamp"],
    }


