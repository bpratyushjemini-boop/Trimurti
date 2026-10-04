"""
NARAD Phase 2.5 — Database Backup & Export Subsystem.
Provides full programmatic and API-driven backup/export and restoration across
SQLite and PostgreSQL database tiers:
  - Chat Sessions & Messages
  - Smriti Persistent Memories (preserving LOCAL vs CLOUD scope)
  - Knowledge Base Documents metadata
  - Task Journal Records
  - System Event Logs
"""

import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.db.database import get_db_dialect
from app.db.models import (
    ChatSession,
    ChatMessage,
    SmritiMemory,
    KnowledgeDocument,
    TaskJournalRecord,
    EventRecord,
)

BACKUP_VERSION = "2.5.0"


def export_database_backup(db: Session) -> Dict[str, Any]:
    """Export complete database state as a portable, dialect-agnostic JSON payload."""
    now_utc = datetime.now(timezone.utc).isoformat()
    dialect = get_db_dialect()

    # 1. Sessions & Messages
    sessions_raw = db.query(ChatSession).all()
    sessions = []
    for s in sessions_raw:
        sessions.append({
            "id": s.id,
            "title": s.title,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })

    messages_raw = db.query(ChatMessage).all()
    messages = []
    for m in messages_raw:
        messages.append({
            "id": m.id,
            "session_id": m.session_id,
            "role": m.role,
            "content": m.content,
            "metadata_json": m.metadata_json,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })

    # 2. Smriti Memories (preserving scope: LOCAL vs CLOUD)
    memories_raw = db.query(SmritiMemory).all()
    memories = []
    for mem in memories_raw:
        memories.append({
            "id": mem.id,
            "key": mem.key,
            "value": mem.value,
            "category": mem.category,
            "source": getattr(mem, "source", "conversation"),
            "confidence": getattr(mem, "confidence", 1.0),
            "importance": getattr(mem, "importance", 0.5),
            "status": getattr(mem, "status", "ACTIVE"),
            "scope": getattr(mem, "scope", "LOCAL"),
            "device_origin": getattr(mem, "device_origin", "mac"),
            "metadata_json": getattr(mem, "metadata_json", None),
            "created_at": mem.created_at.isoformat() if mem.created_at else None,
            "updated_at": mem.updated_at.isoformat() if mem.updated_at else None,
        })

    # 3. Knowledge Documents
    docs_raw = db.query(KnowledgeDocument).all()
    docs = []
    for d in docs_raw:
        docs.append({
            "id": d.id,
            "filename": d.filename,
            "file_type": d.file_type,
            "file_size": d.file_size,
            "file_path": d.file_path,
            "chunk_count": d.chunk_count,
            "status": d.status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        })

    # 4. Task Journal
    journal_raw = db.query(TaskJournalRecord).all()
    journal = []
    for j in journal_raw:
        journal.append({
            "task_id": j.task_id,
            "goal": j.goal,
            "status": j.status,
            "plan_json": j.plan_json,
            "actions_json": j.actions_json,
            "result_json": j.result_json,
            "duration_ms": j.duration_ms,
            "provider_used": j.provider_used,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        })

    # 5. Events
    events_raw = db.query(EventRecord).all()
    events = []
    for e in events_raw:
        events.append({
            "event_id": e.event_id,
            "event_type": e.event_type,
            "title": e.title,
            "body": e.body,
            "priority": e.priority,
            "task_id": e.task_id,
            "metadata_json": e.metadata_json,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })

    return {
        "backup_version": BACKUP_VERSION,
        "exported_at": now_utc,
        "source_dialect": dialect,
        "counts": {
            "sessions": len(sessions),
            "messages": len(messages),
            "memories": len(memories),
            "documents": len(docs),
            "journal_tasks": len(journal),
            "events": len(events),
        },
        "data": {
            "chat_sessions": sessions,
            "chat_messages": messages,
            "smriti_memories": memories,
            "knowledge_documents": docs,
            "task_journal": journal,
            "events": events,
        }
    }


def import_database_backup(db: Session, backup_payload: Dict[str, Any], overwrite: bool = False) -> Dict[str, int]:
    """
    Restore data from an exported backup into the active database.
    Performs conflict-free upsert/insert.
    """
    data = backup_payload.get("data", {})
    imported_counts = {
        "sessions": 0,
        "messages": 0,
        "memories": 0,
        "documents": 0,
        "journal_tasks": 0,
        "events": 0,
    }

    # 1. Sessions
    for s_dict in data.get("chat_sessions", []):
        sid = s_dict.get("id")
        existing = db.query(ChatSession).filter(ChatSession.id == sid).first()
        if not existing:
            new_s = ChatSession(
                id=sid,
                title=s_dict.get("title", "Imported Session"),
            )
            db.add(new_s)
            imported_counts["sessions"] += 1
        elif overwrite:
            existing.title = s_dict.get("title", existing.title)

    db.commit()

    # 2. Messages
    for m_dict in data.get("chat_messages", []):
        mid = m_dict.get("id")
        existing = db.query(ChatMessage).filter(ChatMessage.id == mid).first()
        if not existing:
            new_m = ChatMessage(
                id=mid,
                session_id=m_dict.get("session_id"),
                role=m_dict.get("role", "user"),
                content=m_dict.get("content", ""),
                metadata_json=m_dict.get("metadata_json"),
            )
            db.add(new_m)
            imported_counts["messages"] += 1

    db.commit()

    # 3. Memories
    for mem_dict in data.get("smriti_memories", []):
        mem_id = mem_dict.get("id")
        existing = db.query(SmritiMemory).filter(SmritiMemory.id == mem_id).first()
        if not existing:
            new_mem = SmritiMemory(
                id=mem_id,
                key=mem_dict.get("key"),
                value=mem_dict.get("value"),
                category=mem_dict.get("category", "FACTS"),
                source=mem_dict.get("source", "conversation"),
                confidence=float(mem_dict.get("confidence", 1.0)),
                importance=float(mem_dict.get("importance", 0.5)),
                status=mem_dict.get("status", "ACTIVE"),
                scope=mem_dict.get("scope", "LOCAL"),
                device_origin=mem_dict.get("device_origin", "mac"),
                metadata_json=mem_dict.get("metadata_json"),
            )
            db.add(new_mem)
            imported_counts["memories"] += 1
        elif overwrite:
            existing.value = mem_dict.get("value", existing.value)
            existing.category = mem_dict.get("category", existing.category)
            existing.scope = mem_dict.get("scope", existing.scope)

    db.commit()

    # 4. Journal Tasks
    for j_dict in data.get("task_journal", []):
        tid = j_dict.get("task_id")
        existing = db.query(TaskJournalRecord).filter(TaskJournalRecord.task_id == tid).first()
        if not existing:
            new_j = TaskJournalRecord(
                task_id=tid,
                goal=j_dict.get("goal", ""),
                status=j_dict.get("status", "CREATED"),
                plan_json=j_dict.get("plan_json"),
                actions_json=j_dict.get("actions_json"),
                result_json=j_dict.get("result_json"),
                duration_ms=j_dict.get("duration_ms", 0),
                provider_used=j_dict.get("provider_used"),
            )
            db.add(new_j)
            imported_counts["journal_tasks"] += 1

    # 5. Events
    for e_dict in data.get("events", []):
        eid = e_dict.get("event_id")
        existing = db.query(EventRecord).filter(EventRecord.event_id == eid).first()
        if not existing:
            new_e = EventRecord(
                event_id=eid,
                event_type=e_dict.get("event_type", "TASK_CREATED"),
                title=e_dict.get("title", ""),
                body=e_dict.get("body", ""),
                priority=e_dict.get("priority", "normal"),
                task_id=e_dict.get("task_id"),
                metadata_json=e_dict.get("metadata_json"),
            )
            db.add(new_e)
            imported_counts["events"] += 1

    db.commit()
    return imported_counts
