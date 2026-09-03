from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
from app.core.config import settings
from app.db.database import get_db
from app.core.router import model_router
from app.providers.manager import provider_manager

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("")
def check_health(db: Session = Depends(get_db)):
    """
    Returns system health, database state, and Model Router telemetry for the NARAD HUD.
    """
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unreachable: {str(e)}"

    route = model_router.resolve_route()

    return {
        "status": "online",
        "system": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "database": db_status,
        "active_provider": route.provider_id,
        "active_model": route.model_name,
        "is_configured": route.is_configured,
        "available_providers": provider_manager.list_providers(),
        "timestamp": datetime.utcnow().isoformat()
    }
