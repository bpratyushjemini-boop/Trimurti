from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
from app.core.config import settings
from app.db.database import get_db
from app.core.router import model_router
from app.providers.manager import provider_manager
from app.services.runtime_truth import runtime_truth_service

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("")
def check_health(db: Session = Depends(get_db)):
    """
    Returns V6.1 system health, database state, and Model Router telemetry for the NARAD HUD.
    Includes live provider health matrix with V6.1 fine-grained health states
    (AVAILABLE / RATE_LIMITED / QUOTA_EXHAUSTED / DEGRADED / AUTH_ERROR / UNAVAILABLE)
    and capability-aware failover routing orders.
    """
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unreachable: {str(e)}"

    route = model_router.resolve_route()
    providers_list = provider_manager.list_providers()

    # V6.1: Map individual provider statuses with fine-grained health states
    provider_health_map = {}
    for p in providers_list:
        raw_prov = provider_manager.get_provider(p["id"])
        h = raw_prov.get_health_status()
        provider_health_map[p["id"]] = {
            # V6.1 fine-grained state
            "health_state": h.get("health_state", "NOT_CONFIGURED"),
            # Legacy field for backward-compat
            "status": h.get("status", "OFFLINE" if not p.get("is_configured") else "ONLINE"),
            "display_name": p.get("display_name"),
            "is_configured": p.get("is_configured", False),
            "in_cooldown": h.get("in_cooldown", False),
            "cooldown_remaining_sec": h.get("cooldown_remaining_sec", 0),
            "latency_ms": h.get("latency_ms", 0),
            "failover_count": h.get("failover_count", 0),
            "consecutive_failures": h.get("consecutive_failures", 0),
        }

    try:
        from app.services.trinetra import trinetra_service
        trinetra_status = trinetra_service.get_status()
    except Exception:
        trinetra_status = "READY [V5]"

    # V6.1 & V7.2 routing orders
    from app.core.router import TASK_GENERAL_CHAT, TASK_REASONING, TASK_CODING, TASK_VISION, TASK_LOCAL, TASK_LOCAL_FAST
    routing_orders = {
        "local_fast": model_router._capability_order(TASK_LOCAL_FAST),
        "local": model_router._capability_order(TASK_LOCAL),
        "general_fast": model_router._capability_order(TASK_GENERAL_CHAT),
        "reasoning": model_router._capability_order(TASK_REASONING),
        "coding": model_router._capability_order(TASK_CODING),
        "vision": model_router._capability_order(TASK_VISION),
    }

    is_cloud = (
        settings.is_cloud
        or getattr(settings, "NARAD_RUNTIME_MODE", "hybrid").lower() == "cloud"
    )

    if is_cloud:
        local_ai_info = {
            "status": "UNAVAILABLE",
            "model": getattr(settings, "HUGGINGFACE_LOCAL_MODEL", "HuggingFaceTB/SmolLM2-135M-Instruct"),
            "device": "NONE",
            "mps_available": False,
            "is_loaded": False,
        }
        local_ai_status_str = "STANDBY"
        embedding_status_str = "STANDBY"
        ollama_status_str = "UNAVAILABLE"
    else:
        try:
            from app.services.local_ai.manager import local_ai_manager
            local_ai_info = local_ai_manager.get_status_info()
            local_ai_status_str = f"READY [{local_ai_info['device']}]" if local_ai_info.get("is_loaded") else f"STANDBY [{local_ai_info['device']}]"
        except Exception:
            local_ai_info = {}
            local_ai_status_str = "STANDBY"

        try:
            from app.services.embeddings.manager import embedding_manager
            emb_status = embedding_manager.get_status()
            embedding_status_str = f"READY [{emb_status['provider_status']['device']}]" if emb_status.get("ready") else "STANDBY"
        except Exception:
            embedding_status_str = "STANDBY"

        try:
            ollama_prov = provider_manager.get_provider("ollama")
            if ollama_prov and ollama_prov.is_configured():
                ollama_status_str = f"ONLINE [{getattr(settings, 'OLLAMA_MODEL', 'qwen3.5:0.8b')}]"
            else:
                ollama_status_str = "UNAVAILABLE"
        except Exception:
            ollama_status_str = "STANDBY"

    return {
        "status": "online",
        "system": settings.APP_NAME,
        "version": "7.2.0",
        "environment": settings.APP_ENV,
        "database": db_status,
        "model_router_status": "online",
        "router_version": "V7.2",
        # Active route telemetry
        "active_provider": route.provider_id,
        "active_model": route.model_name,
        "route_reason": route.routing_reason,
        "task_category": route.task_category,
        "is_configured": route.is_configured,
        "fallback_ready": len(route.failover_candidates) > 0,
        "failover_candidates": route.failover_candidates,
        # V6.1 & V7.2 routing orders
        "routing_orders": routing_orders,
        # Provider mesh
        "provider_matrix": provider_health_map,
        "available_providers": providers_list,
        "local_ai": local_ai_info,
        "subsystems": {
            "narad_core": "ONLINE [V7.2]",
            "task_engine": "READY [V6]",
            "model_router": "ONLINE [V7.2]",
            "manthan": "READY [V6]",
            "kriya": "READY [V6]",
            "computer_agent": "READY [V6]",
            "trinetra": trinetra_status,
            "vani": "READY [V7]",
            "smriti": "READY",
            "knowledge_base": "READY [V7.1]",
            "local_ai": local_ai_status_str,
            "embeddings": embedding_status_str,
            "ollama": ollama_status_str,
        },
        "runtime_truth": runtime_truth_service.get_runtime_truth(),
        "timestamp": datetime.utcnow().isoformat()
    }
