from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
from app.core.config import settings
from app.db.database import get_db
from app.providers.manager import provider_manager

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("")
def check_health(db: Session = Depends(get_db)):
    """
    Returns system health and diagnostic telemetry for the NARAD HUD.
    """
    # Check SQLite database readiness
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unreachable: {str(e)}"

    return {
        "status": "online",
        "system": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "database": db_status,
        "active_provider": provider_manager.get_provider().provider_id,
        "available_providers": provider_manager.list_providers(),
        "timestamp": datetime.utcnow().isoformat()
    }
