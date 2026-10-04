"""
NARAD Phase 2.5 — Event System & Notification-Ready Event Engine.
Structured event tracking for task lifecycles, plans, actions, observations,
verifications, memory usage, provider routing, and proactive notifications.
Powers the HUD and future iOS task-status UI and push notifications.
"""

from collections import deque
from datetime import datetime, timezone
import json
import logging
import asyncio
from typing import Any, Dict, List, Optional, Set
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import EventRecord
from app.core.identifiers import generate_event_id

logger = logging.getLogger("narad.events")


class EventType:
    # Phase 2.5 Standard Task Events (Client Contract for iOS / HUD)
    TASK_CREATED = "TASK_CREATED"
    TASK_STARTED = "TASK_STARTED"
    PLAN_CREATED = "PLAN_CREATED"
    TOOL_STARTED = "TOOL_STARTED"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    OBSERVATION_CREATED = "OBSERVATION_CREATED"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"

    # Backward Compatibility Aliases & System Telemetry Events
    ACTION_STARTED = "TOOL_STARTED"
    ACTION_COMPLETED = "TOOL_COMPLETED"
    ACTION_FAILED = "ACTION_FAILED"
    REPLAN_STARTED = "RECOVERY_STARTED"
    TASK_VERIFIED = "TASK_VERIFIED"
    MEMORY_USED = "MEMORY_USED"
    MEMORY_CREATED = "MEMORY_CREATED"
    MODEL_SELECTED = "MODEL_SELECTED"
    PROVIDER_CHANGED = "PROVIDER_CHANGED"
    LOCAL_MODE_ENABLED = "LOCAL_MODE_ENABLED"
    OFFLINE_MODE_ENABLED = "OFFLINE_MODE_ENABLED"


class EventSystem:
    """
    Central event coordinator for NARAD.
    Provides in-memory ring-buffer for sub-millisecond retrieval,
    optional database persistence, pub/sub for real-time SSE streaming,
    and proactive notification evaluation.
    """

    def __init__(self, max_in_memory: int = 200):
        self._max_in_memory = max_in_memory
        self._in_memory_events: deque = deque(maxlen=max_in_memory)
        self._subscribers: Set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        """Register a queue to receive live emitted events in real time."""
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        """Unregister a subscriber queue."""
        self._subscribers.discard(q)

    def emit_event(
        self,
        event_type: str,
        title: str,
        body: str,
        priority: str = "normal",
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Record a structured event and prepare notification payload.
        Broadcasts to all active streaming subscribers.
        """
        now = datetime.now(timezone.utc)
        iso_ts = now.isoformat()
        event_id = generate_event_id()
        meta = metadata or {}

        # 1. Evaluate notification worthiness (Proactive Brain Foundation)
        is_notifiable = self.evaluate_notification_worthiness(event_type, priority, meta)

        event_payload = {
            "event_id": event_id,
            "type": event_type,
            "event_type": event_type,
            "title": title,
            "body": body,
            "priority": priority,
            "task_id": task_id,
            "timestamp": iso_ts,
            "metadata": meta,
            "is_notifiable": is_notifiable,
        }

        # Store in fast in-memory buffer
        self._in_memory_events.append(event_payload)
        logger.info(f"[EventSystem] {event_type} (task={task_id}): {title}")

        # Broadcast to active async subscribers (SSE streams)
        dead_subs = []
        for sub in list(self._subscribers):
            try:
                sub.put_nowait(event_payload)
            except Exception:
                dead_subs.append(sub)
        for dead in dead_subs:
            self.unsubscribe(dead)

        # Optional persistence
        should_close = False
        if db is None:
            try:
                db = SessionLocal()
                should_close = True
            except Exception as e:
                logger.debug(f"[EventSystem] Database session could not be created: {e}")
                db = None

        if db is not None:
            try:
                rec = EventRecord(
                    event_id=event_id,
                    event_type=event_type,
                    title=title,
                    body=body,
                    priority=priority,
                    task_id=task_id,
                    metadata_json=json.dumps(meta),
                    created_at=datetime.now(timezone.utc),
                )
                db.add(rec)
                db.commit()
            except Exception as e:
                logger.debug(f"[EventSystem] Could not persist event to DB: {e}")
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                if should_close:
                    db.close()

        return event_payload

    def evaluate_notification_worthiness(
        self,
        event_or_type: Any,
        priority: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Proactive Brain Foundation:
        Distinguish EVENT DETECTED from EVENT WORTH NOTIFYING ABOUT.
        High-priority completions, task failures, recovery actions, or security alerts are marked notifiable.
        """
        if isinstance(event_or_type, dict):
            e_type = event_or_type.get("event_type") or event_or_type.get("type", "")
            prio = event_or_type.get("priority", "normal")
            meta = event_or_type.get("metadata", {})
            title = event_or_type.get("title", "")
            body = event_or_type.get("body", "")
            task_id = event_or_type.get("task_id")
            ts = event_or_type.get("timestamp", datetime.now(timezone.utc).isoformat())

            is_worthy = (
                prio in ("high", "urgent") or
                e_type in (
                    EventType.TASK_COMPLETED,
                    EventType.TASK_FAILED,
                    EventType.RECOVERY_STARTED,
                    EventType.OFFLINE_MODE_ENABLED
                ) or
                meta.get("requires_attention") is True
            )
            if not is_worthy:
                return None

            return {
                "type": e_type,
                "title": title,
                "body": body,
                "priority": prio,
                "timestamp": ts,
                "task_id": task_id,
            }
        else:
            e_type = str(event_or_type)
            prio = priority or "normal"
            meta = metadata or {}
            if prio in ("high", "urgent"):
                return True
            if e_type in (
                EventType.TASK_COMPLETED,
                EventType.TASK_FAILED,
                EventType.RECOVERY_STARTED,
                EventType.OFFLINE_MODE_ENABLED
            ):
                return True
            if meta.get("requires_attention") is True:
                return True
            return False

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent events from in-memory ring-buffer or database."""
        return self.get_events(limit=limit)

    def get_events(
        self,
        limit: int = 50,
        task_id: Optional[str] = None,
        event_type: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve recent events from in-memory ring-buffer or database."""
        # First filter in-memory buffer
        events = list(self._in_memory_events)
        if task_id:
            events = [e for e in events if e.get("task_id") == task_id]
        if event_type:
            events = [e for e in events if e.get("type") == event_type or e.get("event_type") == event_type]

        if events:
            return list(reversed(events))[:limit]

        # Fallback to database
        should_close = False
        if db is None:
            try:
                db = SessionLocal()
                should_close = True
            except Exception:
                return []

        try:
            q = db.query(EventRecord)
            if task_id:
                q = q.filter(EventRecord.task_id == task_id)
            if event_type:
                q = q.filter(EventRecord.event_type == event_type)
            records = q.order_by(EventRecord.created_at.desc()).limit(limit).all()
            return [r.to_dict() for r in records]
        except Exception as e:
            logger.debug(f"[EventSystem] Could not query events from DB: {e}")
            return []
        finally:
            if should_close:
                db.close()


event_system = EventSystem()
