"""
NARAD Phase 3 — Mobile Notifications & APNs Event Architecture API.
Provides backend contracts for future Apple Push Notification Service (APNs):
  - Device Registration (saving APNs device token)
  - Pending Notifications Query (retrieving unacknowledged high-priority events)
  - Acknowledge Notifications (marking delivered)
  - Real-time Notification Stream (SSE for active foreground app)
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, List, Set

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.db.database import get_db, SessionLocal
from app.db.models import DeviceRegistration, AcknowledgedNotification, EventRecord
from app.core.identifiers import generate_device_id
from app.services.event_system import event_system
from app.api.v1.schemas import (
    DeviceRegistrationRequest,
    DeviceRegistrationResponse,
    NotificationItem,
    PendingNotificationsResponse,
    AcknowledgeNotificationsRequest,
    ErrorResponse,
)

logger = logging.getLogger("narad.v1.notifications")

router = APIRouter(prefix="/notifications", tags=["v1 - Notifications"])


# =============================================================================
# 1. REGISTER DEVICE
# =============================================================================

@router.post(
    "/register-device",
    response_model=DeviceRegistrationResponse,
    status_code=status.HTTP_200_OK,
    responses={400: {"model": ErrorResponse}},
    summary="Register iOS Device APNs Push Token"
)
def register_device(
    payload: DeviceRegistrationRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Registers an iOS device push token with NARAD backend for remote notifications.
    Idempotent: updates existing registration if token already registered.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    clean_token = payload.device_token.strip()
    if len(clean_token) < 16:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "INVALID_TOKEN",
                    "message": "APNs device token must be at least 16 hex characters.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    existing = db.query(DeviceRegistration).filter(DeviceRegistration.device_token == clean_token).first()
    now_utc = datetime.now(timezone.utc)

    if existing:
        existing.app_version = payload.app_version
        existing.environment = payload.environment
        existing.updated_at = now_utc
        db.commit()
        db.refresh(existing)
        dev_id = existing.id
    else:
        dev_id = generate_device_id()
        reg = DeviceRegistration(
            id=dev_id,
            device_token=clean_token,
            platform=payload.platform.lower(),
            app_version=payload.app_version,
            environment=payload.environment,
            created_at=now_utc,
            updated_at=now_utc,
        )
        db.add(reg)
        db.commit()

    return DeviceRegistrationResponse(
        success=True,
        device_id=dev_id,
        registered_at=now_utc.isoformat(),
    )


# =============================================================================
# 2. PENDING NOTIFICATIONS
# =============================================================================

@router.get(
    "/pending",
    response_model=PendingNotificationsResponse,
    summary="Get Unacknowledged Notifiable Events"
)
def get_pending_notifications(db: Session = Depends(get_db)):
    """
    Retrieves high-priority task completion, failure, recovery, or alert events
    that have not yet been marked acknowledged by the mobile client.
    """
    # 1. Fetch acknowledged event IDs
    ack_ids: Set[str] = set()
    try:
        ack_records = db.query(AcknowledgedNotification.event_id).all()
        ack_ids = {r[0] for r in ack_records}
    except Exception as e:
        logger.debug(f"[Notifications] Could not fetch ack records: {e}")

    # 2. Fetch recent events from event_system
    all_events = event_system.get_events(limit=100)
    pending_items: List[NotificationItem] = []

    for ev in all_events:
        eid = ev.get("event_id")
        if not eid or eid in ack_ids:
            continue

        # Evaluate if worthy of notifying mobile client
        if ev.get("is_notifiable") or event_system.evaluate_notification_worthiness(ev):
            pending_items.append(
                NotificationItem(
                    event_id=eid,
                    event_type=ev.get("event_type") or ev.get("type", "SYSTEM_EVENT"),
                    title=ev.get("title", ""),
                    body=ev.get("body", ""),
                    priority=ev.get("priority", "normal"),
                    task_id=ev.get("task_id"),
                    timestamp=ev.get("timestamp", datetime.now(timezone.utc).isoformat()),
                )
            )

    return PendingNotificationsResponse(
        count=len(pending_items),
        notifications=pending_items,
    )


# =============================================================================
# 3. ACKNOWLEDGE NOTIFICATIONS
# =============================================================================

@router.post(
    "/acknowledge",
    summary="Mark Notifications as Delivered / Handled"
)
def acknowledge_notifications(
    payload: AcknowledgeNotificationsRequest,
    db: Session = Depends(get_db)
):
    """
    Marks one or more notification event IDs as delivered so they are omitted
    from subsequent pending queries.
    """
    count = 0
    now_utc = datetime.now(timezone.utc)
    for eid in payload.event_ids:
        cleaned = eid.strip()
        if not cleaned:
            continue
        try:
            exists = db.query(AcknowledgedNotification).filter(AcknowledgedNotification.event_id == cleaned).first()
            if not exists:
                ack = AcknowledgedNotification(
                    id=str(uuid.uuid4()),
                    event_id=cleaned,
                    acknowledged_at=now_utc,
                )
                db.add(ack)
                count += 1
        except Exception as e:
            logger.debug(f"[Notifications] Ack record insert notice for {cleaned}: {e}")

    db.commit()
    return {"success": True, "acknowledged_count": count}


# =============================================================================
# 4. REAL-TIME NOTIFICATION SSE STREAM
# =============================================================================

@router.get(
    "/stream",
    summary="Live Push Event Stream (SSE)"
)
async def stream_notifications():
    """
    Streams proactive, notifiable events in real time to the iOS app while active.
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        q = event_system.subscribe()
        try:
            # Send initial keepalive
            yield f"data: {json.dumps({'event': 'connected', 'status': 'listening'})}\n\n"

            while True:
                try:
                    event_data = await asyncio.wait_for(q.get(), timeout=25.0)
                    if event_data.get("is_notifiable") or event_system.evaluate_notification_worthiness(event_data):
                        notif = {
                            "event": "notification",
                            "event_id": event_data.get("event_id"),
                            "type": event_data.get("event_type") or event_data.get("type"),
                            "title": event_data.get("title"),
                            "body": event_data.get("body"),
                            "priority": event_data.get("priority", "normal"),
                            "task_id": event_data.get("task_id"),
                            "timestamp": event_data.get("timestamp"),
                        }
                        yield f"data: {json.dumps(notif)}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive ping
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            event_system.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
            "X-Accel-Buffering": "no",
        }
    )
