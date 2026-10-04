"""
NARAD Stable Server-Side Identifiers.
Generates human-readable, collision-resistant, prefixed UUIDs suitable for
cloud persistence, iOS client routing, and event tracing:
  - ses_<uuid_hex> : Chat Session
  - msg_<uuid_hex> : Message
  - tsk_<uuid_hex> : Agent / Journal Task
  - evt_<uuid_hex> : Structured Event
  - mem_<uuid_hex> : Smriti Memory Record
"""

import uuid
import re
from typing import Optional

SESSION_PREFIX = "ses_"
MESSAGE_PREFIX = "msg_"
TASK_PREFIX = "tsk_"
EVENT_PREFIX = "evt_"
MEMORY_PREFIX = "mem_"
DEVICE_PREFIX = "dev_"


def generate_session_id() -> str:
    """Generate a stable session ID with 'ses_' prefix."""
    return f"{SESSION_PREFIX}{uuid.uuid4().hex}"


def generate_message_id() -> str:
    """Generate a stable message ID with 'msg_' prefix."""
    return f"{MESSAGE_PREFIX}{uuid.uuid4().hex}"


def generate_task_id() -> str:
    """Generate a stable task ID with 'tsk_' prefix."""
    return f"{TASK_PREFIX}{uuid.uuid4().hex}"


def generate_event_id() -> str:
    """Generate a stable event ID with 'evt_' prefix."""
    return f"{EVENT_PREFIX}{uuid.uuid4().hex}"


def generate_memory_id() -> str:
    """Generate a stable memory ID with 'mem_' prefix."""
    return f"{MEMORY_PREFIX}{uuid.uuid4().hex}"


def generate_device_id() -> str:
    """Generate a stable device registration ID with 'dev_' prefix."""
    return f"{DEVICE_PREFIX}{uuid.uuid4().hex[:12]}"


def is_valid_id(identifier: Optional[str], expected_prefix: Optional[str] = None) -> bool:
    """Validate that an identifier is non-empty and optionally matches the expected prefix or standard UUID."""
    if not identifier or not isinstance(identifier, str):
        return False
    identifier = identifier.strip()
    if expected_prefix:
        if identifier.startswith(expected_prefix):
            return len(identifier) > len(expected_prefix)
    # Also accept standard UUID4 strings for backwards compatibility
    uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
    return bool(uuid_pattern.match(identifier) or (len(identifier) >= 16))
