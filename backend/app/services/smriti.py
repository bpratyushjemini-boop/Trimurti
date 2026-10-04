"""
Smriti Memory Subsystem — Milestone 2: Persistent Conversation Memory Layer.
Acts as the central memory service between NARAD Core and SQLite.
Maintains session stability, message persistence, context recall, and cross-session isolation.
"""

import re
import json
import logging
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple, Set
from datetime import datetime, timedelta
from contextlib import contextmanager
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import ChatSession, ChatMessage, SmritiMemory
from app.core.config import settings

logger = logging.getLogger(__name__)

class SmritiService:
    """
    Smriti (स्मृति) — Persistent Memory Subsystem for NARAD.
    Responsible for conversational recall, session management, and dialogue history.
    """

    @contextmanager
    def _get_session(self, db: Optional[Session] = None):
        """Context manager to reuse provided db session or manage a local SessionLocal lifecycle."""
        if db is not None:
            yield db
        else:
            session = SessionLocal()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

    # =========================================================================
    # Session Operations
    # =========================================================================

    def create_session(self, title: Optional[str] = "New Briefing", db: Optional[Session] = None) -> ChatSession:
        """Create and persist a new conversation session with a stable UUID."""
        with self._get_session(db) as s:
            session = ChatSession(title=title or "New Briefing")
            s.add(session)
            s.commit()
            s.refresh(session)
            logger.info(f"[Smriti] Created new session: {session.id} ('{session.title}')")
            return session

    def get_session(self, session_id: str, db: Optional[Session] = None) -> Optional[ChatSession]:
        """Retrieve a session by its unique ID."""
        with self._get_session(db) as s:
            return s.query(ChatSession).filter(ChatSession.id == session_id).first()

    def get_or_create_session(
        self,
        session_id: Optional[str] = None,
        initial_title: Optional[str] = None,
        db: Optional[Session] = None
    ) -> ChatSession:
        """Retrieve existing session or instantiate a new one if ID is omitted or not found."""
        with self._get_session(db) as s:
            if session_id:
                existing = s.query(ChatSession).filter(ChatSession.id == session_id).first()
                if existing:
                    return existing

            clean_title = (initial_title or "New Briefing").replace("\n", " ").strip()
            title = (clean_title[:35] + "...") if len(clean_title) > 35 else (clean_title or "New Briefing")
            new_session = ChatSession(title=title)
            s.add(new_session)
            s.commit()
            s.refresh(new_session)
            logger.info(f"[Smriti] Auto-created session: {new_session.id} ('{new_session.title}')")
            return new_session

    def list_sessions(self, db: Optional[Session] = None) -> List[ChatSession]:
        """List all conversation sessions ordered by most recently updated."""
        with self._get_session(db) as s:
            return s.query(ChatSession).order_by(ChatSession.updated_at.desc()).all()

    def delete_session(self, session_id: str, db: Optional[Session] = None) -> bool:
        """Delete a conversation session and all cascading message records."""
        with self._get_session(db) as s:
            session = s.query(ChatSession).filter(ChatSession.id == session_id).first()
            if not session:
                return False
            s.delete(session)
            s.commit()
            logger.info(f"[Smriti] Deleted session {session_id} and its associated memory records.")
            return True

    def update_session_title(self, session_id: str, title: str, db: Optional[Session] = None) -> Optional[ChatSession]:
        """Update session title."""
        with self._get_session(db) as s:
            session = s.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session:
                session.title = title.strip()
                session.updated_at = datetime.utcnow()
                s.commit()
                s.refresh(session)
            return session

    # =========================================================================
    # Message Persistence & History Retrieval
    # =========================================================================

    def add_user_message(self, session_id: str, content: str, db: Optional[Session] = None) -> ChatMessage:
        """
        Persist a user directive to the session history.
        Auto-generates a title from the first message if session is on default title.
        Auto-creates session if ID not found.
        """
        with self._get_session(db) as s:
            session = s.query(ChatSession).filter(ChatSession.id == session_id).first()
            if not session:
                session = ChatSession(id=session_id, title="Briefing")
                s.add(session)
                s.commit()
                s.refresh(session)

            clean_content = content.strip()
            user_msg = ChatMessage(
                session_id=session_id,
                role="user",
                content=clean_content
            )
            s.add(user_msg)

            # Update session title if default
            if session.title in ("New Briefing", "Briefing"):
                first_line = clean_content.split("\n")[0].strip()
                session.title = (first_line[:35] + "...") if len(first_line) > 35 else (first_line or "Briefing")

            session.updated_at = datetime.utcnow()
            s.commit()
            s.refresh(user_msg)
            return user_msg

    def add_assistant_message(
        self,
        session_id: str,
        content: str,
        provider: Optional[str] = "gemini",
        model: Optional[str] = "gemini-3.6-flash",
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[Session] = None
    ) -> ChatMessage:
        """Persist an assistant response turn with complete model provider metadata."""
        with self._get_session(db) as s:
            session = s.query(ChatSession).filter(ChatSession.id == session_id).first()
            if not session:
                session = ChatSession(id=session_id, title="Briefing")
                s.add(session)
                s.commit()
                s.refresh(session)

            meta_dict = metadata or {}
            meta_dict.setdefault("provider", provider)
            meta_dict.setdefault("model", model)

            assistant_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=content,
                metadata_json=json.dumps(meta_dict)
            )
            s.add(assistant_msg)
            session.updated_at = datetime.utcnow()
            s.commit()
            s.refresh(assistant_msg)
            return assistant_msg

    def get_session_messages(self, session_id: str, db: Optional[Session] = None) -> List[ChatMessage]:
        """Retrieve all chronological messages for a given session."""
        with self._get_session(db) as s:
            return (
                s.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.asc())
                .all()
            )

    def get_conversation_history(
        self,
        session_id: str,
        limit: Optional[int] = None,
        db: Optional[Session] = None
    ) -> List[Dict[str, str]]:
        """
        Retrieve ordered conversation history formatted for model reasoning context:
        [{"role": "user" | "assistant", "content": "..."}]
        """
        with self._get_session(db) as s:
            query = (
                s.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.asc())
            )
            if limit:
                # If limited, get latest `limit` messages in chronological order
                total = query.count()
                if total > limit:
                    query = query.offset(total - limit)

            messages = query.all()
            return [
                {"role": m.role, "content": m.content}
                for m in messages
                if m.content and m.content.strip()
            ]

    def get_session_memory_context(self, session_id: str, db: Optional[Session] = None) -> str:
        """
        Produce a factual, truthful Smriti memory context summary for system prompt injection.
        Distinguishes active session state from overall local database vault state.
        """
        with self._get_session(db) as s:
            session = s.query(ChatSession).filter(ChatSession.id == session_id).first()
            if not session:
                return "- Memory Vault: Local SQLite database active. No existing persistent session records."

            msg_count = s.query(ChatMessage).filter(ChatMessage.session_id == session_id).count()
            total_sessions = s.query(ChatSession).count()

            # Retrieve past session topics (excluding current)
            past_sessions = (
                s.query(ChatSession)
                .filter(ChatSession.id != session_id)
                .order_by(ChatSession.updated_at.desc())
                .limit(5)
                .all()
            )
            past_titles = [f"'{ps.title}'" for ps in past_sessions if ps.title and ps.title != "New Briefing"]

            context_lines = [
                f"- Active Conversation Briefing: '{session.title}' (ID: {session.id})",
                f"- Recorded Dialogue Turns in Current Session: {msg_count}",
                f"- Total Sessions in Local SQLite Vault: {total_sessions}",
            ]
            if past_titles:
                context_lines.append(f"- Other Recent Vault Sessions: {', '.join(past_titles)}")
            else:
                context_lines.append("- Other Recent Vault Sessions: None")

            return "\n".join(context_lines)

    def get_conversation_summary_context(
        self,
        session_id: str,
        sliding_window_messages: int = 24,
        db: Optional[Session] = None
    ) -> str:
        """
        Produce a compact background summary of turns that have rolled out of the sliding window (>24 messages).
        Only generated when session exceeds the sliding window limit (never premature).
        Keeps summary concise (<200 words), preserving key decisions, topics, and critical entities.
        """
        with self._get_session(db) as s:
            query = (
                s.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.asc())
            )
            total = query.count()
            if total <= sliding_window_messages:
                return ""

            older_count = total - sliding_window_messages
            older_messages = query.limit(older_count).all()
            if not older_messages:
                return ""

            points = []
            for m in older_messages:
                snippet = (m.content or "").strip()
                if not snippet:
                    continue
                first_line = snippet.split("\n")[0][:100]
                if m.role == "user":
                    points.append(f"User: {first_line}")
                elif m.role == "assistant":
                    points.append(f"NARAD: {first_line}")

            summary_text = " | ".join(points[-8:])
            if len(summary_text) > 700:
                summary_text = summary_text[-700:]

            return f"Earlier discussion context (prior to active window):\n{summary_text}"


    # =========================================================================
    # Smṛti 3.0: Personal Memory Intelligence Subsystem
    # Architecture: OBSERVE → EXTRACT → CLASSIFY → STORE → RETRIEVE → UPDATE → DECAY → FORGET → EXPLAIN
    # =========================================================================

    # Explicit memory categories
    class MemoryCategory(str, Enum):
        IDENTITY = "IDENTITY"
        PREFERENCES = "PREFERENCES"
        PROJECTS = "PROJECTS"
        ROUTINES = "ROUTINES"
        DEVICES = "DEVICES"
        SKILLS = "SKILLS"
        PLANS = "PLANS"
        RELATIONSHIPS = "RELATIONSHIPS"
        FACTS = "FACTS"
        CONTEXT = "CONTEXT"

    # Common canonical alias normalization map
    ALIAS_MAP: Dict[str, str] = {
        # Identity
        "name": "user_name", "my_name": "user_name", "user_name": "user_name", "username": "user_name", "full_name": "user_name", "first_name": "user_name",
        "location": "location", "city": "location", "home_city": "location", "user_location": "location", "residence": "location",
        "timezone": "timezone", "time_zone": "timezone", "user_timezone": "timezone",
        # Preferences
        "favorite_color": "favorite_color", "favorite_colour": "favorite_color", "color_preference": "favorite_color", "fav_color": "favorite_color",
        "preferred_editor": "preferred_editor", "editor": "preferred_editor", "ide": "preferred_editor", "code_editor": "preferred_editor",
        "response_style": "response_style", "communication_style": "response_style", "style": "response_style",
        # Devices & OS
        "device": "device", "laptop": "device", "computer": "device", "my_computer": "device", "primary_device": "device", "workstation": "device",
        "operating_system": "operating_system", "os": "operating_system", "my_os": "operating_system", "current_os": "operating_system",
        # Projects
        "active_project": "active_project", "project": "active_project", "main_project": "active_project", "current_project": "active_project",
        "project_name": "project_name",
        "project_current_phase": "project_current_phase", "project_phase": "project_current_phase", "phase": "project_current_phase",
        "project_major_systems": "project_major_systems", "completed_systems": "project_major_systems",
        "project_current_objective": "project_current_objective", "project_objective": "project_current_objective",
        # Skills
        "primary_language": "primary_language", "programming_language": "primary_language", "coding_language": "primary_language",
        "framework": "primary_framework", "primary_framework": "primary_framework",
        # Routines
        "work_routine": "work_routine", "routine": "work_routine", "daily_routine": "work_routine",
        # Browsers & Tools
        "preferred_browser": "preferred_browser", "browser": "preferred_browser", "favorite_browser": "preferred_browser",
    }

    @classmethod
    def normalize_category(cls, category: Optional[str]) -> str:
        """Map input category strings into canonical Smṛti 3.0 categories."""
        if not category:
            return cls.MemoryCategory.FACTS.value
        cat_upper = str(category).strip().upper()
        mapping = {
            "IDENTITY": cls.MemoryCategory.IDENTITY.value,
            "PROFILE": cls.MemoryCategory.IDENTITY.value,
            "PERSONAL": cls.MemoryCategory.IDENTITY.value,
            "USER": cls.MemoryCategory.IDENTITY.value,
            "PREFERENCES": cls.MemoryCategory.PREFERENCES.value,
            "PREFERENCE": cls.MemoryCategory.PREFERENCES.value,
            "STYLE": cls.MemoryCategory.PREFERENCES.value,
            "PROJECTS": cls.MemoryCategory.PROJECTS.value,
            "PROJECT": cls.MemoryCategory.PROJECTS.value,
            "CODE": cls.MemoryCategory.PROJECTS.value,
            "ROUTINES": cls.MemoryCategory.ROUTINES.value,
            "ROUTINE": cls.MemoryCategory.ROUTINES.value,
            "HABIT": cls.MemoryCategory.ROUTINES.value,
            "HABITS": cls.MemoryCategory.ROUTINES.value,
            "DEVICES": cls.MemoryCategory.DEVICES.value,
            "DEVICE": cls.MemoryCategory.DEVICES.value,
            "HARDWARE": cls.MemoryCategory.DEVICES.value,
            "OS": cls.MemoryCategory.DEVICES.value,
            "SKILLS": cls.MemoryCategory.SKILLS.value,
            "SKILL": cls.MemoryCategory.SKILLS.value,
            "TECH": cls.MemoryCategory.SKILLS.value,
            "PLANS": cls.MemoryCategory.PLANS.value,
            "PLAN": cls.MemoryCategory.PLANS.value,
            "GOAL": cls.MemoryCategory.PLANS.value,
            "GOALS": cls.MemoryCategory.PLANS.value,
            "RELATIONSHIPS": cls.MemoryCategory.RELATIONSHIPS.value,
            "RELATIONSHIP": cls.MemoryCategory.RELATIONSHIPS.value,
            "FACTS": cls.MemoryCategory.FACTS.value,
            "FACT": cls.MemoryCategory.FACTS.value,
            "GENERAL": cls.MemoryCategory.FACTS.value,
            "BUDGET": cls.MemoryCategory.FACTS.value,
            "CONTEXT": cls.MemoryCategory.CONTEXT.value,
        }
        return mapping.get(cat_upper, cls.MemoryCategory.FACTS.value)

    @classmethod
    def normalize_key(cls, key: str) -> str:
        """Normalize raw memory key to canonical snake_case format."""
        clean = key.strip().lower().replace(" ", "_")
        clean = re.sub(r'[^a-z0-9_-]', '', clean)
        return cls.ALIAS_MAP.get(clean, clean)

    @staticmethod
    def detect_secrets(text: str) -> Tuple[bool, str]:
        """
        Critical Guardrail: Detect API keys, tokens, credentials, or secrets.
        Never persist raw secrets in Smṛti.
        """
        secret_patterns = [
            (r'(?i)\b(?:sk|gsk|nvapi)-[a-zA-Z0-9_\-]{15,}\b', "AI Provider API Key"),
            (r'(?i)\baizasy[a-zA-Z0-9_\-]{20,}\b', "Google API Key"),
            (r'(?i)\bghp_[a-zA-Z0-9_\-]{20,}\b', "GitHub Token"),
            (r'(?i)\bbearer\s+[a-zA-Z0-9_\-\.]{20,}\b', "Bearer Token"),
            (r'(?i)\bpassword\b\s*(?:is|[:=])\s*\S+', "Password Credential"),
            (r'(?i)\b(?:api[_-]?key|access[_-]?token|secret[_-]?key|auth[_-]?token|password|secret|token)\s*[:=]\s*["\']?\S+["\']?', "Secret Credential Key/Value"),
            (r'(?i)\b(?:api[_-]?key|token)\s+[a-zA-Z0-9_\-\.]{15,}\b', "API Key / Token"),
            (r'(?i)\b(?:sk_live|sk_test)_[a-zA-Z0-9]{20,}\b', "Stripe Secret Key"),
        ]
        for pattern, label in secret_patterns:
            if re.search(pattern, text):
                return True, label

        # Additional indicator check
        lower = text.lower()
        if any(sec in lower for sec in ("sk-", "gsk_", "nvapi-", "aizasy", "ghp_", "bearer ", "password is ", "password=", "secret=", "token=", "api_key=")) and len(text) > 8:
            return True, "API Key / Token / Secret"

        return False, ""

    @staticmethod
    def detect_sensitive_topics(text: str) -> Tuple[bool, str]:
        """
        Privacy Guardrail: Detect sensitive personal data that must never be inferred or stored.
        Health conditions, political alignment, religious beliefs, sexuality, and financial secrets.
        """
        sensitive_patterns = [
            (r'(?i)\b(?:cancer|diabetes|depression|bipolar|schizophrenia|adhd|epilepsy|hiv|covid|tumor|illness|syndrome)\b', "Health/Medical Condition"),
            (r'(?i)\b(?:diagnosed with|prescribed|my psychiatrist|my medication|chemotherapy|insulin)\b', "Medical Treatment"),
            (r'(?i)\b(?:republican party|democratic party|vote for trump|vote for biden|conservative party|liberal party)\b', "Political Preference"),
            (r'(?i)\b(?:my religion is|i practice islam|i practice christianity|i practice hinduism|i practice judaism|i am an atheist)\b', "Religious Affiliation"),
            (r'(?i)\b(?:my sexual orientation|i am gay|i am lesbian|i am bisexual|i am heterosexual)\b', "Sexual Orientation"),
            (r'\b(?:\d{4}[ -]?){3}\d{4}\b', "Credit Card Number"),
            (r'(?i)\b(?:cvv|cvc)\s*[:=]?\s*\d{3,4}\b', "Card Verification Code"),
            (r'(?i)\b(?:ssn|social security number)\s*[:=]?\s*\d{3}-\d{2}-\d{4}\b', "Social Security Number"),
        ]
        for pattern, label in sensitive_patterns:
            if re.search(pattern, text):
                return True, label
        return False, ""

    # =========================================================================
    # First-Class Project Memory Initialization
    # =========================================================================

    def init_project_memory(self, db: Optional[Session] = None) -> None:
        """
        Ensure durable, first-class project memory for NARAD / TRIMURTI AI exists
        in SQLite as specified in Milestone Section 11.
        """
        project_facts = [
            ("project_name", "NARAD / TRIMURTI AI", self.MemoryCategory.PROJECTS.value, 0.95),
            ("project_current_phase", "Phase 2", self.MemoryCategory.PROJECTS.value, 0.90),
            ("project_major_systems", "Model Router, Kriya, Smṛti, Manthan, Trinetra, Task Engine, Runtime Truth, Ollama local inference", self.MemoryCategory.PROJECTS.value, 0.85),
            ("project_current_objective", "Smṛti 3.0", self.MemoryCategory.PROJECTS.value, 0.90),
        ]
        with self._get_session(db) as s:
            # 1. Normalize any legacy categories
            all_mems = s.query(SmritiMemory).all()
            for m in all_mems:
                canon_cat = self.normalize_category(m.category)
                if m.category != canon_cat:
                    m.category = canon_cat

            # 2. Seed core project memories
            for key, val, cat, imp in project_facts:
                exists = s.query(SmritiMemory).filter(SmritiMemory.key == key).first()
                if not exists:
                    mem = SmritiMemory(
                        key=key,
                        value=val,
                        category=cat,
                        source="system_project_init",
                        confidence=1.0,
                        importance=imp,
                        status="ACTIVE",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    s.add(mem)
            s.commit()

    # =========================================================================
    # Persistent Memory Operations (Store, Retrieve, Update, Delete)
    # =========================================================================

    def save_memory(
        self,
        key: str,
        value: str,
        category: Optional[str] = None,
        source: str = "conversation",
        confidence: float = 1.0,
        importance: float = 0.5,
        scope: Optional[str] = None,
        device_origin: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Save, update, or resolve conflict for a persistent memory in Smṛti 3.0.
        Performs secret redaction, key canonicalization, deduplication, conflict provenance,
        and telemetry tracking.
        """
        clean_key = self.normalize_key(key)
        clean_val = value.strip()
        clean_cat = self.normalize_category(category)

        # 1. Privacy & Secret Guardrails
        if clean_key in ("api_key", "password", "secret", "token", "access_token", "private_key", "auth_token", "api_token", "secret_key") or "password" in clean_key or "secret" in clean_key:
            logger.warning(f"[Smriti Security] Rejected saving secret for key '{clean_key}'.")
            return {
                "success": False,
                "status": "rejected",
                "message": f"Security policy: Storing secrets, passwords, or API keys in Smṛti is prohibited.",
                "key": clean_key,
                "category": clean_cat
            }

        is_secret, sec_label = self.detect_secrets(f"{clean_key} {clean_val}")
        if is_secret:
            logger.warning(f"[Smriti Security] Rejected saving secret ({sec_label}) for key '{clean_key}'.")
            return {
                "success": False,
                "status": "rejected",
                "message": f"Security policy: Storing secrets, passwords, or API keys ({sec_label}) in Smṛti is prohibited.",
                "key": clean_key,
                "category": clean_cat
            }

        is_sensitive, sens_label = self.detect_sensitive_topics(f"{clean_key} {clean_val}")
        if is_sensitive:
            logger.warning(f"[Smriti Privacy] Rejected sensitive personal trait ({sens_label}) for key '{clean_key}'.")
            return {
                "success": False,
                "status": "rejected",
                "message": f"Privacy policy: Inferred sensitive personal traits ({sens_label}) are prohibited from persistence.",
                "key": clean_key,
                "category": clean_cat
            }

        # 2. Key Deduplication Candidates
        candidates = {clean_key}
        for alias_k, canon_k in self.ALIAS_MAP.items():
            if canon_k == clean_key or alias_k == clean_key:
                candidates.add(alias_k)
                candidates.add(canon_k)

        with self._get_session(db) as s:
            existing = s.query(SmritiMemory).filter(SmritiMemory.key.in_(candidates)).first()

            if existing:
                # Conflict Resolution / Update
                old_val = existing.value
                val_changed = (old_val.strip() != clean_val)

                # History tracking in metadata
                meta = {}
                if existing.metadata_json:
                    try:
                        meta = json.loads(existing.metadata_json)
                    except Exception:
                        meta = {}

                if val_changed:
                    history = meta.setdefault("history", [])
                    history.append({
                        "previous_value": old_val,
                        "updated_at": existing.updated_at.isoformat() if existing.updated_at else datetime.utcnow().isoformat(),
                        "source": existing.source or "unknown",
                        "previous_confidence": existing.confidence
                    })
                    logger.info(f"[Smriti Telemetry] MEMORY_CONFLICT: resolved '{existing.key}' from '{old_val}' to '{clean_val}'")

                # Merge custom metadata
                if metadata:
                    meta.update(metadata)

                if scope:
                    existing.scope = scope.upper()
                if device_origin:
                    existing.device_origin = device_origin
                existing.value = clean_val
                existing.category = clean_cat
                existing.source = source or existing.source or "conversation"
                existing.confidence = float(confidence)
                existing.importance = float(importance)
                existing.status = "ACTIVE"
                existing.expires_at = expires_at or existing.expires_at
                existing.metadata_json = json.dumps(meta)
                existing.updated_at = datetime.utcnow()
                existing.times_used = (existing.times_used or 0) + 1
                s.commit()
                s.refresh(existing)

                op_status = "updated" if val_changed else "saved"
                msg = "Updated in Smṛti." if val_changed else "Saved to Smṛti."
                logger.info(f"[Smriti Telemetry] MEMORY_{op_status.upper()}: '{existing.key}' -> '{clean_val}' [{clean_cat}] (scope={existing.scope})")
                return {
                    "success": True,
                    "status": op_status,
                    "message": msg,
                    "key": existing.key,
                    "value": clean_val,
                    "category": clean_cat,
                    "confidence": existing.confidence,
                    "importance": existing.importance,
                    "scope": existing.scope,
                    "device_origin": existing.device_origin,
                    "id": existing.id
                }
            else:
                # Brand new memory record
                meta = metadata or {}
                resolved_scope = (scope.upper() if scope else ("CLOUD" if getattr(settings, "NARAD_RUNTIME_MODE", "hybrid") == "cloud" else "LOCAL"))
                resolved_origin = device_origin or ("cloud" if getattr(settings, "NARAD_RUNTIME_MODE", "hybrid") == "cloud" else "mac")
                new_mem = SmritiMemory(
                    key=clean_key,
                    value=clean_val,
                    category=clean_cat,
                    source=source or "conversation",
                    confidence=float(confidence),
                    importance=float(importance),
                    status="ACTIVE",
                    scope=resolved_scope,
                    device_origin=resolved_origin,
                    expires_at=expires_at,
                    metadata_json=json.dumps(meta) if meta else None,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    times_used=0
                )
                s.add(new_mem)
                s.commit()
                s.refresh(new_mem)
                logger.info(f"[Smriti Telemetry] MEMORY_STORE: key='{clean_key}', cat='{clean_cat}', conf={confidence}, scope={resolved_scope}")
                return {
                    "success": True,
                    "status": "saved",
                    "message": "Saved to Smṛti.",
                    "key": clean_key,
                    "value": clean_val,
                    "category": clean_cat,
                    "confidence": float(confidence),
                    "importance": float(importance),
                    "scope": resolved_scope,
                    "device_origin": resolved_origin,
                    "id": new_mem.id
                }

    def retrieve_memory(self, key: str, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        Retrieve a specific active persistent memory by key or alias.
        Updates last_used_at and times_used for freshness tracking.
        """
        clean_key = self.normalize_key(key)
        candidates = {clean_key, key.strip().lower().replace(" ", "_")}
        for a_k, c_k in self.ALIAS_MAP.items():
            if c_k == clean_key or a_k == clean_key:
                candidates.add(a_k)
                candidates.add(c_k)

        with self._get_session(db) as s:
            mem = s.query(SmritiMemory).filter(
                SmritiMemory.key.in_(candidates),
                SmritiMemory.status == "ACTIVE"
            ).first()

            if mem:
                mem.last_used_at = datetime.utcnow()
                mem.times_used = (mem.times_used or 0) + 1
                s.commit()
                s.refresh(mem)
                return {
                    "found": True,
                    "id": mem.id,
                    "key": mem.key,
                    "value": mem.value,
                    "category": mem.category,
                    "confidence": mem.confidence,
                    "importance": mem.importance,
                    "source": mem.source,
                    "status": mem.status,
                    "updated_at": mem.updated_at.isoformat() if mem.updated_at else None
                }

            return {
                "found": False,
                "key": clean_key,
                "message": f"No active memory found in Smṛti for '{key}'."
            }

    def get_memory(self, key: str, db: Optional[Session] = None) -> Optional[str]:
        """Convenience method to retrieve memory value string directly, or None if not found."""
        res = self.retrieve_memory(key, db=db)
        if res.get("found"):
            return res.get("value")
        return None

    def get_memory_by_id(self, memory_id: str, db: Optional[Session] = None) -> Optional[Dict[str, Any]]:
        """Retrieve memory object by UUID."""
        with self._get_session(db) as s:
            mem = s.query(SmritiMemory).filter(SmritiMemory.id == memory_id).first()
            return mem.to_dict() if mem else None

    def update_memory_by_id(
        self,
        memory_id: str,
        value: Optional[str] = None,
        category: Optional[str] = None,
        importance: Optional[float] = None,
        status: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Optional[Dict[str, Any]]:
        """Update fields on an existing memory record by ID."""
        with self._get_session(db) as s:
            mem = s.query(SmritiMemory).filter(SmritiMemory.id == memory_id).first()
            if not mem:
                return None

            if value is not None:
                # Check for secrets
                is_sec, sec_lbl = self.detect_secrets(value)
                if is_sec:
                    return {"error": f"Security policy: {sec_lbl} detected."}
                mem.value = value.strip()

            if category is not None:
                mem.category = self.normalize_category(category)

            if importance is not None:
                mem.importance = float(importance)

            if status is not None:
                mem.status = status.strip().upper()

            mem.updated_at = datetime.utcnow()
            s.commit()
            s.refresh(mem)
            logger.info(f"[Smriti Telemetry] MEMORY_UPDATE: id={memory_id}, key='{mem.key}'")
            return mem.to_dict()

    def delete_memory(self, key: str, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        Delete/forget persistent memories matching key or aliases.
        Supports both soft-forget and complete removal.
        """
        clean_key = self.normalize_key(key)
        candidates = {clean_key, key.strip().lower().replace(" ", "_")}
        for a_k, c_k in self.ALIAS_MAP.items():
            if c_k == clean_key or a_k == clean_key:
                candidates.add(a_k)
                candidates.add(c_k)

        with self._get_session(db) as s:
            matches = s.query(SmritiMemory).filter(SmritiMemory.key.in_(candidates)).all()
            if not matches:
                # Substring / root term matching (e.g. 'preferred_browser' matches 'browser')
                core_terms = [clean_key.replace("my_", "").replace("preferred_", "").replace("favorite_", "")]
                for ct in core_terms:
                    if len(ct) >= 3:
                        matches = s.query(SmritiMemory).filter(SmritiMemory.key.ilike(f"%{ct}%")).all()
                        if matches:
                            break

            if matches:
                deleted_keys = [m.key for m in matches]
                for m in matches:
                    s.delete(m)
                s.commit()
                logger.info(f"[Smriti Telemetry] MEMORY_DELETE: keys={deleted_keys}")
                return {
                    "status": "deleted",
                    "message": "Deleted from Smṛti.",
                    "deleted_keys": deleted_keys
                }

            return {
                "status": "not_found",
                "message": f"No memory found in Smṛti matching '{key}'.",
                "key": clean_key
            }

    def delete_memory_by_id(self, memory_id: str, db: Optional[Session] = None) -> bool:
        """Delete single memory record by primary key UUID."""
        with self._get_session(db) as s:
            mem = s.query(SmritiMemory).filter(SmritiMemory.id == memory_id).first()
            if not mem:
                return False
            s.delete(mem)
            s.commit()
            logger.info(f"[Smriti Telemetry] MEMORY_DELETE: id={memory_id}")
            return True

    def list_memories(
        self,
        category: Optional[str] = None,
        status: Optional[str] = "ACTIVE",
        search: Optional[str] = None,
        scope: Optional[str] = None,
        limit: int = 50,
        db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """List persistent memories with optional category, search, status, and scope filtering."""
        with self._get_session(db) as s:
            query = s.query(SmritiMemory)
            if status and status.upper() != "ALL":
                query = query.filter(SmritiMemory.status == status.upper())
            if category:
                cat_clean = self.normalize_category(category)
                query = query.filter(SmritiMemory.category == cat_clean)
            if scope and scope.upper() != "ALL":
                query = query.filter(SmritiMemory.scope == scope.upper())
            if search and search.strip():
                term = f"%{search.strip().lower()}%"
                query = query.filter(
                    (SmritiMemory.key.ilike(term)) | (SmritiMemory.value.ilike(term))
                )

            records = query.order_by(SmritiMemory.updated_at.desc()).limit(limit).all()
            return [m.to_dict() for m in records]

    # =========================================================================
    # Retrieval, Multi-Factor Ranking & Context Formulation
    # =========================================================================

    def retrieve_relevant_memories(
        self,
        query: Optional[str] = None,
        max_memories: int = 5,
        min_score: float = 8.0,
        db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """
        Rank and retrieve memories using deterministic multi-factor scoring:
        score = relevance * confidence * (0.5 + 0.5 * importance) * recency_factor
        Filters out low-relevance candidates so irrelevant queries receive 0 memories.
        """
        with self._get_session(db) as s:
            all_memories = s.query(SmritiMemory).filter(SmritiMemory.status == "ACTIVE").all()
            if not all_memories:
                return []

            if not query or not query.strip():
                # Order by importance * recency
                now = datetime.utcnow()
                scored = []
                for m in all_memories:
                    days_old = (now - (m.updated_at or now)).total_seconds() / 86400.0
                    recency = 1.0 / (1.0 + (days_old * 0.01))
                    sc = (m.importance or 0.5) * (m.confidence or 1.0) * recency
                    scored.append((sc, m))
                scored.sort(key=lambda x: x[0], reverse=True)
                return [m.to_dict() for _, m in scored[:max_memories]]

            clean_q = query.lower().strip()
            stop_words = {
                "what", "is", "are", "was", "were", "my", "your", "the", "a", "an", "do",
                "you", "know", "about", "tell", "me", "how", "why", "when", "where", "who",
                "i", "to", "in", "for", "of", "and", "or", "can", "could", "would", "please",
                "remember", "recall", "stored", "memory", "smriti", "which", "should", "use",
                "give", "show", "have", "with", "from", "at", "by", "this", "that"
            }
            tokens = re.findall(r'[a-zA-Z0-9_-]+', clean_q)
            meaningful_tokens = [t for t in tokens if t not in stop_words and len(t) > 1]

            if not meaningful_tokens:
                return []

            # Domain expansion
            expanded_terms: Set[str] = set(meaningful_tokens)
            domain_synonyms = {
                "narad": ["active_project", "project", "project_name", "project_phase", "project_current_phase", "project_major_systems", "project_current_objective", "trimurti"],
                "project": ["active_project", "project_name", "project_current_phase", "project_major_systems", "project_current_objective"],
                "phase": ["project_current_phase", "active_project"],
                "objective": ["project_current_objective", "active_project"],
                "systems": ["project_major_systems"],
                "setup": ["device", "operating_system", "preferred_editor", "active_project", "primary_language"],
                "ai": ["device", "operating_system", "active_project"],
                "local": ["device", "operating_system", "active_project"],
                "machine": ["device", "operating_system"],
                "computer": ["device", "operating_system"],
                "laptop": ["device", "operating_system"],
                "mac": ["device", "operating_system"],
                "macbook": ["device", "operating_system"],
                "editor": ["preferred_editor"],
                "code": ["primary_language", "preferred_editor", "active_project"],
                "color": ["favorite_color"],
                "favourite": ["favorite_color"],
                "favorite": ["favorite_color"],
                "name": ["name"],
                "who": ["name"],
                "location": ["location"],
                "city": ["location"],
                "timezone": ["timezone"],
            }
            for tok in meaningful_tokens:
                if tok in domain_synonyms:
                    expanded_terms.update(domain_synonyms[tok])

            scored_candidates = []
            now = datetime.utcnow()

            for mem in all_memories:
                m_key = mem.key.lower()
                m_val = mem.value.lower()
                m_cat = (mem.category or "").lower()

                relevance = 0.0

                # 1. Exact canonical key match or in expanded terms
                if m_key in expanded_terms:
                    relevance += 25.0
                elif any(tok in m_key for tok in meaningful_tokens):
                    relevance += 12.0

                # 2. Value tokens match
                for tok in meaningful_tokens:
                    if tok == m_val or tok in m_val.split():
                        relevance += 18.0
                    elif tok in m_val:
                        relevance += 12.0

                # 3. Category tokens match
                for tok in meaningful_tokens:
                    if tok in m_cat:
                        relevance += 4.0

                if relevance <= 0:
                    continue

                # Multi-factor formula
                conf = float(mem.confidence if mem.confidence is not None else 1.0)
                imp = float(mem.importance if mem.importance is not None else 0.5)
                days_old = (now - (mem.updated_at or now)).total_seconds() / 86400.0
                recency_factor = 1.0 / (1.0 + (days_old * 0.005))

                final_score = relevance * conf * (0.5 + 0.5 * imp) * recency_factor

                if final_score >= min_score:
                    scored_candidates.append((final_score, mem))

            if not scored_candidates:
                return []

            # Sort descending by score
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            top = [m for _, m in scored_candidates[:max_memories]]

            # Update usage telemetry
            for m in top:
                m.last_used_at = now
                m.times_used = (m.times_used or 0) + 1
            s.commit()

            logger.info(f"[Smriti Telemetry] MEMORY_RETRIEVE: query='{query[:40]}', count={len(top)}")
            return [m.to_dict() for m in top]

    def get_relevant_memories_context(
        self,
        query: Optional[str] = None,
        max_memories: int = 5,
        min_score: float = 8.0,
        db: Optional[Session] = None
    ) -> str:
        """
        Formulate zero-hallucination factual grounding for prompt injection.
        Returns concise facts if relevant, or an explicit note if none found.
        """
        with self._get_session(db) as s:
            total_active = s.query(SmritiMemory).filter(SmritiMemory.status == "ACTIVE").count()
            if total_active == 0:
                return "- No persistent memories saved in Smṛti."

        results = self.retrieve_relevant_memories(
            query=query,
            max_memories=max_memories,
            min_score=min_score,
            db=db
        )
        if not results:
            return "- No relevant persistent memories found in Smṛti for this query."

        lines = []
        for r in results:
            lines.append(f"- {r['key']}: {r['value']} (category: {r['category']})")
        return "\n".join(lines)

    # =========================================================================
    # Automatic Observation & Durable Fact Extraction
    # =========================================================================

    def observe_and_extract(
        self,
        text: str,
        session_id: Optional[str] = None,
        db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract durable user facts automatically from conversational text.
        Rejects questions, temporary physical/mental states, temporal anchors,
        weak speculative phrases, 3rd party hearsay, and sensitive topics.
        """
        raw = text.strip()
        if not raw or len(raw) < 4:
            return []

        # 1. Reject questions
        if raw.endswith("?") or re.match(r'(?i)^(?:what|where|who|how|when|why|is|are|can|could|do|does|did|will|would)\b', raw):
            return []

        # 2. Reject temporary context anchors (e.g. "I am tired today", "I feel sick right now")
        temporal_or_transient = [
            r'(?i)\b(?:today|tonight|right now|at the moment|currently|this morning|this afternoon|this evening)\b',
            r'(?i)\bi\s+(?:am|feel)\s+(?:tired|sleepy|hungry|exhausted|busy|stressed|bored|sick|ill|down|sad|happy)\b',
            r'(?i)\bi\s+have\s+a\s+(?:headache|cold|fever)\b',
        ]
        if any(re.search(p, raw) for p in temporal_or_transient):
            logger.info(f"[Smriti Extraction] Ignored transient/temporary statement: '{raw[:50]}'")
            return []

        # 3. Reject weak / speculative statements
        speculative = [
            r'(?i)\b(?:might|maybe|perhaps|could be|someday|possibly|wondering if|thinking of|considering|probably)\b',
        ]
        if any(re.search(p, raw) for p in speculative):
            logger.info(f"[Smriti Extraction] Ignored speculative statement: '{raw[:50]}'")
            return []

        # 4. Reject 3rd party hearsay ("My friend told me...")
        hearsay = [
            r'(?i)\b(?:my friend told me|someone said|they said|my boss said|people say)\b',
        ]
        if any(re.search(p, raw) for p in hearsay):
            logger.info(f"[Smriti Extraction] Ignored hearsay statement: '{raw[:50]}'")
            return []

        extracted_facts: List[Dict[str, Any]] = []

        # Pattern A: Favorite / preferred
        m_fav = re.search(r'(?i)\bmy\s+(favorite|preferred)\s+([a-zA-Z0-9_\s]+?)\s+is\s+([a-zA-Z0-9_\s\-\+\#\.]+)', raw)
        if m_fav:
            pref_type = m_fav.group(1).lower()
            thing = m_fav.group(2).strip().lower().replace(" ", "_")
            val = m_fav.group(3).strip().rstrip(".")
            prefix = "preferred" if pref_type == "preferred" else "favorite"
            k = f"{prefix}_{thing}" if not (thing.startswith("favorite_") or thing.startswith("preferred_")) else thing
            k = self.normalize_key(k)
            extracted_facts.append({
                "key": k,
                "value": val,
                "category": self.MemoryCategory.PREFERENCES.value,
                "confidence": 0.98,
                "importance": 0.70
            })

        # Pattern B: Dislike / Hate
        m_hate = re.search(r'(?i)\bi\s+(?:hate|dislike|can\'t stand)\s+([a-zA-Z0-9_\s\-\+\#\.]+)', raw)
        if m_hate and not m_fav:
            target = m_hate.group(1).strip().rstrip(".")
            extracted_facts.append({
                "key": f"dislike_{target.lower().replace(' ', '_')}",
                "value": f"Dislikes {target}",
                "category": self.MemoryCategory.PREFERENCES.value,
                "confidence": 0.95,
                "importance": 0.65
            })

        # Pattern C: Device / OS usage ("I use a MacBook", "I use Windows", "I use Linux")
        m_use = re.search(r'(?i)\bi\s+use\s+(?:a|an)?\s*(macbook|mac\b|windows\s*laptop|windows\b|linux\b|iphone\b|android\b|vs\s*code|neovim|vim|sublime)', raw)
        if m_use:
            item = m_use.group(1).strip()
            item_lower = item.lower()
            if any(hw in item_lower for hw in ("macbook", "mac", "windows", "linux", "laptop")):
                extracted_facts.append({
                    "key": "device",
                    "value": item,
                    "category": self.MemoryCategory.DEVICES.value,
                    "confidence": 0.95,
                    "importance": 0.75
                })
            elif any(ed in item_lower for ed in ("code", "vim", "neovim", "sublime")):
                extracted_facts.append({
                    "key": "preferred_editor",
                    "value": item,
                    "category": self.MemoryCategory.PREFERENCES.value,
                    "confidence": 0.95,
                    "importance": 0.70
                })

        # Pattern D: Active Project ("I'm building NARAD", "My project is X")
        m_proj = re.search(r'(?i)\b(?:i(?:\'m|\s+am)\s+building|my\s+project\s+is)\s+([a-zA-Z0-9_\s\-\+\#\.]+)', raw)
        if m_proj:
            proj = m_proj.group(1).strip().rstrip(".")
            extracted_facts.append({
                "key": "active_project",
                "value": proj,
                "category": self.MemoryCategory.PROJECTS.value,
                "confidence": 0.95,
                "importance": 0.85
            })

        # Pattern E: Name ("My name is X", "Call me X")
        m_name = re.search(r'(?i)\b(?:my\s+name\s+is|call\s+me)\s+([A-Z][a-zA-Z0-9_\s\-]+)', raw)
        if m_name:
            n = m_name.group(1).strip().rstrip(".")
            extracted_facts.append({
                "key": "name",
                "value": n,
                "category": self.MemoryCategory.IDENTITY.value,
                "confidence": 1.0,
                "importance": 0.95
            })

        # Pattern F: Explicit "Remember that..." or "Remember I..."
        m_rem = re.search(r'(?i)\bremember\s+(?:that\s+)?(?:i\s+)?([^\.]+)', raw)
        if m_rem and not extracted_facts:
            stmt = m_rem.group(1).strip().rstrip(".")
            # Try sub-patterns
            if "prefer" in stmt.lower() or "like" in stmt.lower():
                extracted_facts.append({
                    "key": f"preference_{stmt[:20].lower().replace(' ', '_')}",
                    "value": stmt,
                    "category": self.MemoryCategory.PREFERENCES.value,
                    "confidence": 1.0,
                    "importance": 0.90
                })
            else:
                extracted_facts.append({
                    "key": f"fact_{stmt[:20].lower().replace(' ', '_')}",
                    "value": stmt,
                    "category": self.MemoryCategory.FACTS.value,
                    "confidence": 1.0,
                    "importance": 0.85
                })

        # Persist extracted facts
        saved_records = []
        for f in extracted_facts:
            res = self.save_memory(
                key=f["key"],
                value=f["value"],
                category=f["category"],
                source="auto_extraction",
                confidence=f["confidence"],
                importance=f["importance"],
                metadata={"session_id": session_id, "source_utterance": raw[:100]},
                db=db
            )
            if res.get("success"):
                saved_records.append(res)
                logger.info(f"[Smriti Telemetry] MEMORY_EXTRACT: auto-stored '{f['key']}'='{f['value']}'")

        return saved_records

    # =========================================================================
    # Direct Natural-Language Memory Commands (0 LLM Tokens)
    # =========================================================================

    def handle_memory_command(self, text: str, db: Optional[Session] = None) -> Optional[Dict[str, Any]]:
        """
        Detect and resolve explicit user memory commands deterministically:
        - "Remember that [fact]"
        - "Forget that [key]" / "Forget my preference for [key]"
        - "Update my memory [key] to [value]" / "Update my project phase to [value]"
        - "What do you remember about me?" / "Show my memories"
        - "Show my memories about NARAD" / "What do you remember about my NARAD project?"
        - "Show my stored preferences"
        - "Is this stored in memory?"
        Returns direct structured response or None if not a memory command.
        """
        raw = text.strip()
        lower = raw.lower()

        # 1. "What do you remember about me?" / "Show my memories"
        if re.search(r'(?i)\b(?:what\s+do\s+you\s+remember(?:\s+about\s+me)?|show\s+(?:all\s+)?my\s+memories|list\s+my\s+memories)\b', raw):
            memories = self.list_memories(status="ACTIVE", limit=100, db=db)
            if not memories:
                return {
                    "handled": True,
                    "response": "I do not currently have any persistent memories saved in Smṛti.",
                    "command": "LIST_ALL"
                }

            grouped: Dict[str, List[str]] = {}
            for m in memories:
                cat = m.get("category", "FACTS")
                grouped.setdefault(cat, []).append(f"- {m['key']}: {m['value']}")

            report_lines = ["SMṚTI // STORED MEMORIES\n"]
            for cat, items in grouped.items():
                report_lines.append(f"{cat}:")
                report_lines.extend(items)
                report_lines.append("")

            return {
                "handled": True,
                "response": "\n".join(report_lines).strip(),
                "command": "LIST_ALL",
                "count": len(memories)
            }

        # 2. "Show my memories about NARAD" / "What do you remember about my NARAD project?"
        if re.search(r'(?i)\b(?:memories\s+about\s+narad|remember\s+about(?:\s+my)?\s+narad(?:\s+project)?)\b', raw):
            memories = self.list_memories(category=self.MemoryCategory.PROJECTS.value, status="ACTIVE", db=db)
            if not memories:
                # Fallback to search
                memories = self.retrieve_relevant_memories(query="narad project", min_score=5.0, db=db)

            if not memories:
                return {
                    "handled": True,
                    "response": "I do not currently have any stored memories regarding NARAD.",
                    "command": "PROJECT_MEMORIES"
                }

            report_lines = ["SMṚTI // NARAD PROJECT MEMORIES\n"]
            for m in memories:
                report_lines.append(f"- {m['key']}: {m['value']}")

            return {
                "handled": True,
                "response": "\n".join(report_lines),
                "command": "PROJECT_MEMORIES",
                "count": len(memories)
            }

        # 3. "Show my stored preferences"
        if re.search(r'(?i)\b(?:show\s+(?:my\s+)?(?:stored\s+)?preferences|what\s+are\s+my\s+preferences)\b', raw):
            memories = self.list_memories(category=self.MemoryCategory.PREFERENCES.value, status="ACTIVE", db=db)
            if not memories:
                return {
                    "handled": True,
                    "response": "No user preferences are currently stored in Smṛti.",
                    "command": "LIST_PREFERENCES"
                }
            report_lines = ["SMṚTI // STORED PREFERENCES\n"]
            for m in memories:
                report_lines.append(f"- {m['key']}: {m['value']}")
            return {
                "handled": True,
                "response": "\n".join(report_lines),
                "command": "LIST_PREFERENCES",
                "count": len(memories)
            }

        # 4. "Forget that..." / "Forget my preference for..."
        m_forget = re.match(r'(?i)^forget\s+(?:that\s+)?(?:my\s+preference\s+for\s+|my\s+)?([a-zA-Z0-9_\s\-]+)', raw)
        if m_forget:
            target = m_forget.group(1).strip().rstrip(".")
            del_res = self.delete_memory(target, db=db)
            if del_res.get("status") == "deleted":
                return {
                    "handled": True,
                    "response": f"Deleted from Smṛti: '{target}'.",
                    "command": "FORGET",
                    "details": del_res
                }
            else:
                return {
                    "handled": True,
                    "response": f"I don't have a memory for '{target}' stored in Smṛti.",
                    "command": "FORGET_NOT_FOUND"
                }

        # 5. "Update my memory [key] to [value]" / "Update my project phase to [value]"
        m_upd = re.match(r'(?i)^update\s+(?:my\s+)?(?:memory\s+)?([a-zA-Z0-9_\s\-]+?)\s+to\s+([^\.]+)', raw)
        if m_upd:
            k = m_upd.group(1).strip().lower().replace(" ", "_")
            v = m_upd.group(2).strip().rstrip(".")
            save_res = self.save_memory(key=k, value=v, db=db)
            if save_res.get("success"):
                return {
                    "handled": True,
                    "response": f"Updated in Smṛti: {save_res['key']} = {save_res['value']}",
                    "command": "UPDATE",
                    "details": save_res
                }
            else:
                return {
                    "handled": True,
                    "response": f"Could not update memory: {save_res.get('message', 'Rejected by policy')}",
                    "command": "UPDATE_REJECTED"
                }

        # 6. "Remember that..." / "Remember I..."
        m_rem = re.match(r'(?i)^remember\s+(?:that\s+)?(?:i\s+)?([^\.]+)', raw)
        if m_rem:
            extracted = self.observe_and_extract(raw, db=db)
            if extracted:
                saved = extracted[0]
                return {
                    "handled": True,
                    "response": f"Saved to Smṛti: {saved.get('key')} = {saved.get('value')}",
                    "command": "REMEMBER",
                    "details": saved
                }
            else:
                # Generic fallback if not matched by heuristic
                content = m_rem.group(1).strip().rstrip(".")
                k = self.normalize_key(content[:25])
                save_res = self.save_memory(key=k, value=content, category=self.MemoryCategory.FACTS.value, db=db)
                if save_res.get("success"):
                    return {
                        "handled": True,
                        "response": f"Saved to Smṛti.",
                        "command": "REMEMBER",
                        "details": save_res
                    }
                else:
                    return {
                        "handled": True,
                        "response": f"Could not save memory: {save_res.get('message')}",
                        "command": "REMEMBER_REJECTED"
                    }

        return None

    # =========================================================================
    # Status, Explanation & Observability
    # =========================================================================

    def get_memory_status(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """Return runtime status and metrics for Smṛti 3.0."""
        with self._get_session(db) as s:
            total = s.query(SmritiMemory).count()
            active = s.query(SmritiMemory).filter(SmritiMemory.status == "ACTIVE").count()

            # Category counts
            from sqlalchemy import func
            cat_counts_raw = s.query(SmritiMemory.category, func.count(SmritiMemory.id)).group_by(SmritiMemory.category).all()
            cat_dict = {cat: count for cat, count in cat_counts_raw}

            # Scope counts
            scope_counts_raw = s.query(SmritiMemory.scope, func.count(SmritiMemory.id)).group_by(SmritiMemory.scope).all()
            scope_dict = {scope: count for scope, count in scope_counts_raw}

            return {
                "enabled": True,
                "backend": "sqlite",
                "persistent": True,
                "total_memories": total,
                "active_memories": active,
                "categories": cat_dict,
                "scopes": scope_dict,
                "subsystem_status": "ONLINE"
            }

    def explain_memory_retrieval(self, query: str, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        Explain which memories are retrieved for a query and why.
        Provides provenance: source, created_at, updated_at, times_used.
        """
        memories = self.retrieve_relevant_memories(query=query, max_memories=5, min_score=5.0, db=db)
        items = []
        for m in memories:
            items.append({
                "id": m["id"],
                "key": m["key"],
                "value": m["value"],
                "category": m["category"],
                "confidence": m["confidence"],
                "importance": m["importance"],
                "provenance": {
                    "source": m.get("source", "conversation"),
                    "created_at": m.get("created_at"),
                    "updated_at": m.get("updated_at"),
                    "times_used": m.get("times_used", 0)
                },
                "explanation": f"Retrieved because '{m['key']}' and '{m['value']}' match query concepts in category {m['category']}."
            })

        return {
            "query": query,
            "retrieved_count": len(items),
            "memories": items
        }

# Global singleton Smriti memory service
smriti_service = SmritiService()
# Ensure project memory is seeded on module load
try:
    smriti_service.init_project_memory()
except Exception as _e:
    pass
