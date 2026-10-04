"""
NARAD Phase 2.5 — Events & Proactive Notifications API Routes.
Exposes structured event logs and real-time SSE streaming for HUD and iOS task monitoring:
  - GET /api/events
  - GET /api/events/stream (SSE)
"""

from typing import Any, Dict, List, Optional, AsyncGenerator
import json
import asyncio
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.services.event_system import event_system

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("", response_model=List[Dict[str, Any]])
def get_events(
    limit: int = Query(50, ge=1, le=200, description="Max events to return"),
    task_id: Optional[str] = Query(None, description="Optional task ID filter"),
    event_type: Optional[str] = Query(None, description="Optional event type filter"),
):
    """
    Retrieve structured events and notification payloads.
    Provides activity feeds for HUD and iOS task status.
    """
    return event_system.get_events(limit=limit, task_id=task_id, event_type=event_type)


@router.get("/stream")
async def stream_events(
    task_id: Optional[str] = Query(None, description="Optional task ID filter for stream")
):
    """
    Server-Sent Events (SSE) stream for live task and system events.
    Enables low-latency push notifications and live progress for HUD and iOS clients.
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        q = event_system.subscribe()
        try:
            # Yield initial connection heartbeat
            yield f"data: {json.dumps({'event': 'connected', 'status': 'streaming'})}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=15.0)
                    if task_id and payload.get("task_id") != task_id:
                        continue
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive ping to prevent proxy/browser timeout
                    yield ": ping\n\n"
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
