"""
NARAD Phase 2.5 — Database Backup & Export API Routes.
Exposes:
  - GET  /api/backup/export : Download full JSON snapshot of database state
  - POST /api/backup/import : Restore data snapshot into active database
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.backup import export_database_backup, import_database_backup

router = APIRouter(prefix="/backup", tags=["Backup"])


@router.get("/export", response_model=Dict[str, Any])
def export_backup(db: Session = Depends(get_db)):
    """Export complete snapshot of sessions, messages, smriti memories, and events."""
    try:
        return export_database_backup(db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate database backup: {str(e)}"
        )


@router.post("/import", response_model=Dict[str, Any])
def import_backup(
    payload: Dict[str, Any] = Body(..., description="Backup JSON payload"),
    overwrite: bool = False,
    db: Session = Depends(get_db)
):
    """Restore database snapshot from JSON backup payload."""
    if not payload or "data" not in payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid backup payload: missing 'data' root."
        )
    try:
        counts = import_database_backup(db, payload, overwrite=overwrite)
        return {
            "success": True,
            "status": "imported",
            "imported_counts": counts,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restore database backup: {str(e)}"
        )
