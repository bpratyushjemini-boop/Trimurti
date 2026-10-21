import uuid
import re
from datetime import datetime
import json
from typing import Optional
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer, Float, Boolean
from sqlalchemy.orm import relationship
from app.db.database import Base
from app.core.identifiers import (
    generate_session_id,
    generate_message_id,
    generate_task_id,
    generate_event_id,
    generate_memory_id,
    generate_device_id,
)

def _format_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """Ensure datetime outputs as an ISO 8601 string with explicit UTC 'Z' timezone indicator."""
    if not dt:
        return None
    iso = dt.isoformat()
    if not iso.endswith("Z") and "+" not in iso and not re.search(r"-\d{2}:\d{2}$", iso):
        return iso + "Z"
    return iso

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(64), primary_key=True, default=generate_session_id)
    title = Column(String(255), nullable=False, default="New Briefing")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "created_at": _format_utc_iso(self.created_at),
            "updated_at": _format_utc_iso(self.updated_at),
            "message_count": len(self.messages) if self.messages else 0
        }

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String(64), primary_key=True, default=generate_message_id)
    session_id = Column(String(64), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(32), nullable=False)  # "user", "assistant", "system"
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)  # JSON string for provider metadata, stats, etc.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="messages")

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "metadata_json": self.metadata_json,
            "metadata": self.metadata_json,
            "created_at": _format_utc_iso(self.created_at)
        }

class SmritiMemory(Base):
    __tablename__ = "smriti_memories"

    id = Column(String(64), primary_key=True, default=generate_memory_id)
    key = Column(String(255), nullable=False, index=True)
    value = Column(Text, nullable=False)
    category = Column(String(64), nullable=False, default="FACTS")
    source = Column(String(64), nullable=False, default="conversation")
    confidence = Column(Float, nullable=False, default=1.0)
    importance = Column(Float, nullable=False, default=0.5)
    status = Column(String(32), nullable=False, default="ACTIVE")  # ACTIVE, FORGOTTEN, EXPIRED, ARCHIVED
    scope = Column(String(32), nullable=False, default="LOCAL")    # LOCAL vs CLOUD (explicit privacy boundary)
    device_origin = Column(String(64), nullable=True, default="mac")
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    times_used = Column(Integer, nullable=False, default=0)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        meta = {}
        if getattr(self, "metadata_json", None):
            try:
                meta = json.loads(self.metadata_json)
            except Exception:
                meta = {}

        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "category": self.category,
            "source": getattr(self, "source", "conversation") or "conversation",
            "confidence": getattr(self, "confidence", 1.0) if getattr(self, "confidence", None) is not None else 1.0,
            "importance": getattr(self, "importance", 0.5) if getattr(self, "importance", None) is not None else 0.5,
            "status": getattr(self, "status", "ACTIVE") or "ACTIVE",
            "scope": getattr(self, "scope", "LOCAL") or "LOCAL",
            "device_origin": getattr(self, "device_origin", "mac") or "mac",
            "created_at": _format_utc_iso(self.created_at),
            "updated_at": _format_utc_iso(self.updated_at),
            "last_used_at": _format_utc_iso(getattr(self, "last_used_at", None)),
            "expires_at": _format_utc_iso(getattr(self, "expires_at", None)),
            "times_used": getattr(self, "times_used", 0) or 0,
            "metadata": meta,
        }

class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    file_type = Column(String(32), nullable=False)  # pdf, txt, md, docx
    file_size = Column(Integer, nullable=False, default=0)  # bytes
    file_path = Column(String(1024), nullable=False)
    chunk_count = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="INGESTING")  # INGESTING, EXTRACTING, INDEXING, READY, FAILED
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    chunks = relationship(
        "KnowledgeChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeChunk.chunk_index"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "document_id": self.id,
            "filename": self.filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "file_path": self.file_path,
            "chunk_count": self.chunk_count,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": _format_utc_iso(self.created_at),
            "updated_at": _format_utc_iso(self.updated_at),
            "indexed_at": _format_utc_iso(self.updated_at)
        }

class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False, default=0)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=False, default=0)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("KnowledgeDocument", back_populates="chunks")

    def to_dict(self):
        return {
            "id": self.id,
            "chunk_id": self.id,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "token_count": self.token_count,
            "metadata_json": self.metadata_json,
            "created_at": _format_utc_iso(self.created_at)
        }


class TaskJournalRecord(Base):
    __tablename__ = "task_journal"

    task_id = Column(String(64), primary_key=True, default=generate_task_id)
    goal = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="CREATED")
    plan_json = Column(Text, nullable=True)
    actions_json = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=False, default=0)
    provider_used = Column(String(64), nullable=True)
    errors_json = Column(Text, nullable=True)
    verification = Column(String(64), nullable=True, default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        def _parse(field_val, fallback):
            if not field_val:
                return fallback
            try:
                return json.loads(field_val)
            except Exception:
                return fallback

        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status,
            "plan": _parse(self.plan_json, []),
            "actions": _parse(self.actions_json, []),
            "result": _parse(self.result_json, {}),
            "duration_ms": self.duration_ms,
            "provider_used": self.provider_used,
            "errors": _parse(self.errors_json, []),
            "verification": self.verification,
            "created_at": _format_utc_iso(self.created_at),
            "completed_at": _format_utc_iso(self.completed_at),
        }


class EventRecord(Base):
    __tablename__ = "events"

    event_id = Column(String(64), primary_key=True, default=generate_event_id)
    event_type = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    priority = Column(String(32), nullable=False, default="normal")
    task_id = Column(String(64), nullable=True, index=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        meta = {}
        if self.metadata_json:
            try:
                meta = json.loads(self.metadata_json)
            except Exception:
                meta = {}

        return {
            "event_id": self.event_id,
            "type": self.event_type,
            "title": self.title,
            "body": self.body,
            "priority": self.priority,
            "task_id": self.task_id,
            "timestamp": _format_utc_iso(self.created_at),
            "metadata": meta,
        }


class DeviceRegistration(Base):
    __tablename__ = "device_registrations"

    id = Column(String(64), primary_key=True, default=generate_device_id)
    device_token = Column(String(255), nullable=False, unique=True, index=True)
    platform = Column(String(32), nullable=False, default="ios")
    app_version = Column(String(64), nullable=True)
    environment = Column(String(32), nullable=False, default="production")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "device_id": self.id,
            "device_token": self.device_token,
            "platform": self.platform,
            "app_version": self.app_version,
            "environment": self.environment,
            "created_at": _format_utc_iso(self.created_at),
            "updated_at": _format_utc_iso(self.updated_at),
        }


class AcknowledgedNotification(Base):
    __tablename__ = "acknowledged_notifications"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String(64), nullable=False, unique=True, index=True)
    acknowledged_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class LocalNodeRecord(Base):
    __tablename__ = "local_nodes"

    node_id = Column(String(64), primary_key=True)
    node_name = Column(String(255), nullable=False, default="Local Node")
    status = Column(String(32), nullable=False, default="ONLINE")
    capabilities_json = Column(Text, nullable=True)
    runtime_json = Column(Text, nullable=True)
    models_json = Column(Text, nullable=True)
    token_hash = Column(String(128), nullable=True)
    revoked = Column(Boolean, default=False, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        def _parse(val, fallback):
            if not val:
                return fallback
            try:
                return json.loads(val)
            except Exception:
                return fallback

        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "status": self.status,
            "capabilities": _parse(self.capabilities_json, {}),
            "runtime": _parse(self.runtime_json, {}),
            "model_availability": _parse(self.models_json, []),
            "revoked": bool(self.revoked),
            "revoked_at": _format_utc_iso(self.revoked_at),
            "last_seen": _format_utc_iso(self.last_seen),
            "created_at": _format_utc_iso(self.created_at),
        }


class NodeActionRecord(Base):
    __tablename__ = "node_actions"

    action_id = Column(String(64), primary_key=True)
    node_id = Column(String(64), nullable=False, index=True)
    action_type = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="PENDING")  # PENDING, DISPATCHED, COMPLETED, FAILED, CANCELLED, TIMEOUT
    permission_level = Column(Integer, default=0, nullable=False)
    requires_confirmation = Column(Boolean, default=False, nullable=False)
    confirmed = Column(Boolean, default=False, nullable=False)
    result_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    request_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        def _parse(val, fallback):
            if not val:
                return fallback
            try:
                return json.loads(val)
            except Exception:
                return fallback

        return {
            "action_id": self.action_id,
            "node_id": self.node_id,
            "action_type": self.action_type,
            "payload": _parse(self.payload_json, {}),
            "status": self.status,
            "permission_level": self.permission_level,
            "requires_confirmation": bool(self.requires_confirmation),
            "confirmed": bool(self.confirmed),
            "result": _parse(self.result_json, None),
            "error": self.error,
            "request_id": self.request_id,
            "created_at": _format_utc_iso(self.created_at),
            "expires_at": _format_utc_iso(self.expires_at),
            "completed_at": _format_utc_iso(self.completed_at),
        }


