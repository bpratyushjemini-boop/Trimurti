"""
NARAD Phase 3 — Mobile API Contract Schemas (Pydantic v2).
Defines strict, typed request and response contracts for the iOS client:
  - Error Contract (consistent machine-readable error models)
  - Chat API (send, stream, cancel, history, sessions)
  - Task API (create, status, progress, events, cancel, retry, result)
  - Runtime API (system status, capabilities, health, operational mode)
  - Memory API (status, recall, write, delete, scope separation)
  - Voice API (STT transcription, TTS synthesis status)
  - Notification API (device registration, pending notifications, events)
  - Auth Handshake API
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone


# =============================================================================
# 1. CONSISTENT MACHINE-READABLE ERROR CONTRACT
# =============================================================================

class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code (e.g. AUTH_REQUIRED, TASK_NOT_FOUND, OFFLINE_MODE)")
    message: str = Field(..., description="Human-readable explanation of the error")
    request_id: str = Field(..., description="Unique trace identifier for debugging")
    task_id: Optional[str] = Field(None, description="Associated task ID if error occurred in task context")
    retryable: bool = Field(False, description="Whether client should attempt automatic retry")
    provider: Optional[str] = Field(None, description="Safe provider identifier if failure was provider-related")


class ErrorResponse(BaseModel):
    error: ErrorDetail


# =============================================================================
# 2. CHAT API SCHEMAS
# =============================================================================

class SendMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message content")
    session_id: Optional[str] = Field(None, description="Existing session ID. Auto-created if omitted.")
    provider: Optional[str] = Field(None, description="Optional provider override")
    model: Optional[str] = Field(None, description="Optional model override")
    is_voice: bool = Field(False, description="True if input originated from voice transcription")


class SendMessageResponse(BaseModel):
    response: str = Field(..., description="Assistant text response")
    session_id: str = Field(..., description="Stable session identifier (ses_...)")
    message_id: str = Field(..., description="Unique message identifier")
    provider: str = Field(..., description="Provider used for generation")
    model: str = Field(..., description="Model used for generation")
    execution_mode: str = Field("cloud", description="'cloud' or 'local'")
    latency_ms: int = Field(..., description="End-to-end processing latency in milliseconds")
    status: str = Field("success", description="Status string: success or error")
    tools_executed: List[Dict[str, Any]] = Field(default_factory=list, description="List of tools executed during turn")
    created_at: str = Field(..., description="ISO 8601 UTC timestamp")


class ChatMessageItem(BaseModel):
    id: str = Field(..., description="Unique message ID")
    session_id: str = Field(..., description="Parent session ID")
    role: str = Field(..., description="'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message text")
    created_at: str = Field(..., description="ISO 8601 UTC timestamp")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadata including provider/model info")


class ConversationSessionItem(BaseModel):
    session_id: str = Field(..., description="Stable session identifier")
    title: str = Field(..., description="Human-readable title")
    created_at: str = Field(..., description="Session creation timestamp")
    updated_at: str = Field(..., description="Last updated timestamp")
    message_count: int = Field(0, description="Total number of messages in session")


class ConversationHistoryResponse(BaseModel):
    session_id: str = Field(..., description="Stable session identifier")
    title: str = Field(..., description="Session title")
    messages: List[ChatMessageItem] = Field(default_factory=list, description="Ordered conversation turns")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Update timestamp")


class CreateSessionRequest(BaseModel):
    title: Optional[str] = Field("New Briefing", description="Initial conversation title")


class CreateSessionResponse(BaseModel):
    session_id: str = Field(..., description="Generated session identifier (ses_...)")
    title: str = Field(..., description="Session title")
    created_at: str = Field(..., description="ISO 8601 UTC timestamp")


class CancelChatRequest(BaseModel):
    session_id: str = Field(..., description="Active session ID to cancel generation for")
    reason: Optional[str] = Field("User cancelled generation", description="Cancellation reason")


class CancelChatResponse(BaseModel):
    success: bool = Field(..., description="Whether cancellation was accepted")
    session_id: str = Field(..., description="Session ID")
    status: str = Field("cancelled", description="Execution status")
    message: str = Field(..., description="Human readable result")


# =============================================================================
# 3. TASK API SCHEMAS
# =============================================================================

class CreateTaskRequest(BaseModel):
    goal: str = Field(..., min_length=1, description="High-level goal or directive for the Agent Brain")
    session_id: Optional[str] = Field(None, description="Optional associated session ID")
    dry_run: bool = Field(False, description="Simulate without executing system mutations")
    confirmation_id: Optional[str] = Field(None, description="Approved confirmation token if required")


class TaskSummaryResponse(BaseModel):
    task_id: str = Field(..., description="Stable task identifier (tsk_...)")
    goal: str = Field(..., description="Task objective")
    status: str = Field(..., description="CREATED, PLANNING, EXECUTING, COMPLETED, FAILED, CANCELLED")
    verification: str = Field(..., description="PENDING, VERIFIED, FAILED, UNVERIFIED")
    duration_ms: int = Field(0, description="Execution duration in milliseconds")
    provider_used: Optional[str] = Field(None, description="AI provider used for task orchestration")
    created_at: str = Field(..., description="ISO 8601 UTC timestamp")
    completed_at: Optional[str] = Field(None, description="Completion timestamp")


class TaskProgressResponse(BaseModel):
    task_id: str = Field(..., description="Stable task identifier")
    status: str = Field(..., description="Active task status")
    total_steps: int = Field(0, description="Total planned steps")
    completed_steps: int = Field(0, description="Steps completed so far")
    current_step: Optional[str] = Field(None, description="Currently executing step description")
    progress_pct: int = Field(0, ge=0, le=100, description="Completion percentage (0 to 100)")
    active: bool = Field(False, description="True if task is still running")


class TaskResultResponse(BaseModel):
    task_id: str = Field(..., description="Stable task identifier")
    goal: str = Field(..., description="Task objective")
    status: str = Field(..., description="Final task status")
    verification: str = Field(..., description="Verification status")
    plan: List[Dict[str, Any]] = Field(default_factory=list, description="Generated plan steps")
    actions: List[Dict[str, Any]] = Field(default_factory=list, description="Step execution actions and evidence")
    result: Dict[str, Any] = Field(default_factory=dict, description="Structured task result payload")
    errors: List[str] = Field(default_factory=list, description="Error messages if any step failed")
    duration_ms: int = Field(0, description="Total execution time in ms")
    provider_used: Optional[str] = Field(None, description="Primary provider used")
    created_at: str = Field(..., description="Task creation timestamp")
    completed_at: Optional[str] = Field(None, description="Task completion timestamp")


class CancelTaskRequest(BaseModel):
    reason: Optional[str] = Field("User cancellation via mobile app", description="Reason for cancelling task")


class RetryTaskResponse(BaseModel):
    success: bool = Field(..., description="Whether retry submission was accepted")
    original_task_id: str = Field(..., description="Task ID that was retried")
    retry_task_id: str = Field(..., description="Newly spawned task identifier")
    status: str = Field(..., description="Status of retried task")
    goal: str = Field(..., description="Goal being retried")


# =============================================================================
# 4. RUNTIME & CAPABILITY SCHEMAS
# =============================================================================

class LocalCapabilities(BaseModel):
    computer_control: str = Field(..., description="AVAILABLE or UNAVAILABLE_MAC_OFFLINE")
    screen_capture: str = Field(..., description="AVAILABLE or UNAVAILABLE_MAC_OFFLINE")
    apple_music: str = Field(..., description="AVAILABLE or UNAVAILABLE_MAC_OFFLINE")
    local_ai: str = Field(..., description="AVAILABLE, STANDBY, or UNAVAILABLE")
    ollama: str = Field(..., description="AVAILABLE or UNAVAILABLE")


class CloudCapabilities(BaseModel):
    cloud_llm_inference: str = Field("AVAILABLE", description="Cloud model inference status")
    cloud_persistence: str = Field("AVAILABLE", description="PostgreSQL persistence status")
    cloud_memory: str = Field("AVAILABLE", description="Cloud Smriti memory status")
    web_search: str = Field("AVAILABLE", description="Web search capability status")
    knowledge_search: str = Field("AVAILABLE", description="Knowledge base retrieval status")


class RuntimeStatusResponse(BaseModel):
    app_name: str = Field(..., description="Application name (NARAD)")
    version: str = Field(..., description="Backend release version")
    api_version: str = Field("v1", description="Mobile API version contract")
    operational_status: str = Field(..., description="ONLINE | CLOUD | LOCAL | OFFLINE | DEGRADED")
    execution_mode: str = Field(..., description="CLOUD | LOCAL | HYBRID")
    network_state: str = Field(..., description="CONNECTED | OFFLINE")
    active_provider: str = Field(..., description="Currently active model provider")
    active_model: str = Field(..., description="Currently active model")
    autonomy_level: int = Field(..., ge=0, le=3, description="Active autonomy level (0=Chat, 1=Suggest, 2=Supervised, 3=Autonomous)")
    autonomy_mode: str = Field(..., description="CHAT_ONLY, SUGGEST, SUPERVISED, TASK_AUTONOMY")
    mac_available: bool = Field(..., description="True if host Mac is online and accessible")
    mac_status: str = Field(..., description="Human readable Mac status")
    database_backend: str = Field(..., description="Active database dialect (sqlite or postgresql)")
    database_connected: bool = Field(True, description="Database connectivity status")
    local_capabilities: LocalCapabilities
    cloud_capabilities: CloudCapabilities
    subsystems: Dict[str, str] = Field(default_factory=dict, description="Health status of all subsystems")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")


# =============================================================================
# 5. MEMORY SCHEMAS
# =============================================================================

class MemoryStatusResponse(BaseModel):
    enabled: bool = Field(True, description="Whether memory subsystem is active")
    backend: str = Field(..., description="Storage engine (sqlite / postgresql)")
    total_memories: int = Field(..., description="Total persisted memory records")
    active_memories: int = Field(..., description="Active non-expired memory records")
    local_count: int = Field(0, description="Private local-only memory records")
    cloud_count: int = Field(0, description="Cloud memory records")
    categories: Dict[str, int] = Field(default_factory=dict, description="Counts by category")


class RecallMemoryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Query string for semantic recall")
    limit: int = Field(5, ge=1, le=20, description="Max memories to return")
    scope: Optional[str] = Field(None, description="Optional scope filter: 'LOCAL', 'CLOUD', or None for all")


class RecallMemoryResponse(BaseModel):
    query: str = Field(..., description="Search query")
    count: int = Field(..., description="Number of memories retrieved")
    memories: List[Dict[str, Any]] = Field(default_factory=list, description="Retrieved memory items with scope tags")


class WriteMemoryRequest(BaseModel):
    key: str = Field(..., min_length=1, description="Memory key or entity name")
    value: str = Field(..., min_length=1, description="Fact or information to remember")
    category: Optional[str] = Field("FACTS", description="Category: IDENTITY, PREFERENCES, PROJECTS, etc.")
    scope: str = Field("CLOUD", description="Storage scope: 'CLOUD' (default for mobile) or 'LOCAL'")
    importance: float = Field(0.5, ge=0.0, le=1.0, description="Importance score")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence score")


class WriteMemoryResponse(BaseModel):
    success: bool = Field(..., description="Whether memory was stored")
    id: str = Field(..., description="Memory identifier")
    key: str = Field(..., description="Canonical key")
    value: str = Field(..., description="Stored fact")
    category: str = Field(..., description="Category")
    scope: str = Field(..., description="LOCAL or CLOUD")
    status: str = Field(..., description="'saved' or 'updated'")


# =============================================================================
# 6. VOICE SCHEMAS
# =============================================================================

class VoiceStatusResponse(BaseModel):
    stt_ready: bool = Field(..., description="Speech-to-text readiness")
    stt_engine: str = Field(..., description="STT engine label")
    stt_device: str = Field(..., description="STT hardware device")
    tts_ready: bool = Field(..., description="Text-to-speech readiness")
    tts_engine: str = Field(..., description="TTS engine label")
    tts_device: str = Field(..., description="TTS hardware device")
    supported_languages: List[str] = Field(default_factory=lambda: ["en", "hi", "hinglish"], description="Languages supported")
    local_voice_enabled: bool = Field(True, description="True if running local speech models")


class TranscriptionResponse(BaseModel):
    text: str = Field(..., description="Transcribed speech text")
    language: str = Field("auto", description="Detected or specified language")
    duration: float = Field(0.0, description="Audio duration in seconds")
    engine: str = Field(..., description="Transcription engine used")
    success: bool = Field(True, description="Transcription status")


# =============================================================================
# 7. NOTIFICATIONS & DEVICE REGISTRATION SCHEMAS
# =============================================================================

class DeviceRegistrationRequest(BaseModel):
    device_token: str = Field(..., min_length=16, description="Apple APNs push token (hex string)")
    platform: str = Field("ios", description="Device platform (ios)")
    app_version: Optional[str] = Field(None, description="Installed iOS app build/version")
    environment: str = Field("production", description="'sandbox' (TestFlight/Dev) or 'production'")


class DeviceRegistrationResponse(BaseModel):
    success: bool = Field(True, description="Registration status")
    device_id: str = Field(..., description="Assigned server device handle")
    registered_at: str = Field(..., description="ISO 8601 registration timestamp")


class NotificationItem(BaseModel):
    event_id: str = Field(..., description="Event identifier")
    event_type: str = Field(..., description="Event type string")
    title: str = Field(..., description="Notification title")
    body: str = Field(..., description="Notification body")
    priority: str = Field("normal", description="'normal', 'high', 'urgent'")
    task_id: Optional[str] = Field(None, description="Associated task ID")
    timestamp: str = Field(..., description="Event timestamp")


class PendingNotificationsResponse(BaseModel):
    count: int = Field(..., description="Number of pending notifiable events")
    notifications: List[NotificationItem] = Field(default_factory=list, description="List of notifiable events")


class AcknowledgeNotificationsRequest(BaseModel):
    event_ids: List[str] = Field(..., min_length=1, description="Event IDs to acknowledge as delivered")


# =============================================================================
# 8. AUTHENTICATION SCHEMAS
# =============================================================================

class AuthVerifyResponse(BaseModel):
    authenticated: bool = Field(..., description="True if credentials are valid")
    user: str = Field("owner", description="User identity (single-user owner)")
    system: str = Field("NARAD", description="System identifier")
    runtime_mode: str = Field(..., description="Active server runtime mode")
    token_valid: bool = Field(True, description="Whether token is currently valid")


# =============================================================================
# 9. LOCAL NODE ARCHITECTURE SCHEMAS (Future Laptop Migration)
# =============================================================================

class NodeHeartbeatRequest(BaseModel):
    node_id: str = Field(..., min_length=1, description="Unique node identifier, e.g. node_mac_laptop")
    node_name: Optional[str] = Field("Local Mac Laptop", description="Human-readable node label")
    status: Optional[str] = Field("ONLINE", description="ONLINE, STANDBY, or OFFLINE")
    capabilities: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Hardware/tool capabilities")
    runtime: Optional[Dict[str, Any]] = Field(default_factory=dict, description="OS and environment details")
    model_availability: Optional[List[str]] = Field(default_factory=list, description="Locally cached models")


class NodeHeartbeatResponse(BaseModel):
    success: bool = Field(True, description="Heartbeat acknowledgement status")
    node_id: str = Field(..., description="Node identifier")
    status: str = Field(..., description="Active node status")
    acknowledged_at: str = Field(..., description="ISO 8601 acknowledgement timestamp")
    cloud_status: str = Field("ACTIVE", description="Cloud backend operational state")


class NodeStatusResponse(BaseModel):
    connected: bool = Field(..., description="True if any local node has sent a heartbeat recently")
    active_node_id: Optional[str] = Field(None, description="Active local node identifier")
    active_node: Optional[Dict[str, Any]] = Field(None, description="Active node details")
    nodes: List[Dict[str, Any]] = Field(default_factory=list, description="List of all registered nodes")


class NodeActionCreateRequest(BaseModel):
    action_type: str = Field(..., min_length=1, description="Allowed operation: node_status, diagnostics, get_system_state, open_application, take_screenshot")
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Action arguments")
    confirmed: Optional[bool] = Field(False, description="Explicit user confirmation for sensitive actions")
    timeout_seconds: Optional[int] = Field(30, ge=1, le=300, description="Execution timeout in seconds")


class NodeActionResponse(BaseModel):
    success: bool = Field(True, description="Action creation/query status")
    action_id: str = Field(..., description="Unique action ID")
    node_id: str = Field(..., description="Target node ID")
    action_type: str = Field(..., description="Action type")
    status: str = Field(..., description="Action status (PENDING, DISPATCHED, COMPLETED, FAILED, CANCELLED, TIMEOUT)")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Action arguments")
    permission_level: int = Field(0, description="Action permission risk level")
    requires_confirmation: bool = Field(False, description="Whether confirmation is required")
    confirmed: bool = Field(False, description="Whether explicit confirmation was provided")
    result: Optional[Dict[str, Any]] = Field(None, description="Action execution result")
    error: Optional[str] = Field(None, description="Error message if failed")
    request_id: Optional[str] = Field(None, description="Correlation request ID")
    created_at: str = Field(..., description="Creation ISO timestamp")
    completed_at: Optional[str] = Field(None, description="Completion ISO timestamp")


class NodeActionResultRequest(BaseModel):
    success: bool = Field(..., description="Whether action succeeded")
    result: Optional[Dict[str, Any]] = Field(None, description="Execution output")
    error: Optional[str] = Field(None, description="Error message if failed")


class NodeActionCancelRequest(BaseModel):
    reason: Optional[str] = Field("Cancelled by user or system", description="Cancellation reason")


class NodeRevokeResponse(BaseModel):
    success: bool = Field(True, description="Revocation success")
    node_id: str = Field(..., description="Node ID")
    revoked: bool = Field(True, description="Revocation state")
    revoked_at: str = Field(..., description="Revocation ISO timestamp")


class NodeTokenRotateResponse(BaseModel):
    success: bool = Field(True, description="Rotation success")
    node_id: str = Field(..., description="Node ID")
    token: str = Field(..., description="New node authentication token")
    rotated_at: str = Field(..., description="Rotation ISO timestamp")

