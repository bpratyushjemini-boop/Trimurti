"""
NARAD V6.1 — BaseLLMProvider with Fine-Grained Health Tracking.

Health states:
  AVAILABLE       — provider is healthy and accepting requests
  RATE_LIMITED    — hit per-minute/per-hour rate limit (transient, short cooldown)
  QUOTA_EXHAUSTED — daily/monthly quota exhausted (transient, long cooldown)
  DEGRADED        — repeated failures but still reachable
  AUTH_ERROR      — authentication failure (permanent; NEVER trigger failover retry)
  UNAVAILABLE     — network/server unreachable (transient)
  NOT CONFIGURED  — no API key set
"""

import time
from abc import ABC, abstractmethod
from typing import List, Dict, Any, AsyncGenerator, Optional
from datetime import datetime


# V6.1 Provider Health State Constants
HEALTH_AVAILABLE       = "AVAILABLE"
HEALTH_RATE_LIMITED    = "RATE_LIMITED"
HEALTH_QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
HEALTH_DEGRADED        = "DEGRADED"
HEALTH_AUTH_ERROR      = "AUTH_ERROR"
HEALTH_UNAVAILABLE     = "UNAVAILABLE"
HEALTH_NOT_CONFIGURED  = "NOT_CONFIGURED"


class BaseLLMProvider(ABC):
    """
    Abstract Base Class for all AI model providers in the NARAD ecosystem.
    Model-agnostic design ensures NARAD can swap between Groq, NVIDIA NIM,
    Gemini, OpenRouter, Claude, OpenAI, or local engines seamlessly.

    V6.1 additions:
    - Fine-grained health states (AVAILABLE/RATE_LIMITED/QUOTA_EXHAUSTED/
      DEGRADED/AUTH_ERROR/UNAVAILABLE)
    - Auth-error latch: once AUTH_ERROR is recorded, failover is never
      triggered for that provider in the current process lifetime.
    - failover_count telemetry.
    """

    def __init__(self):
        self._last_success_ts: Optional[str] = None
        self._last_failure_ts: Optional[str] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms: int = 0
        self._consecutive_failures: int = 0
        self._cooldown_until: float = 0.0
        self._health_state: str = HEALTH_AVAILABLE
        self._failover_count: int = 0          # times this provider was skipped in failover
        self._auth_error_latched: bool = False  # permanent: no failover once auth fails
        self._request_count: int = 0           # total successful requests handled
        self._total_tokens: int = 0            # approximate cumulative tokens processed
        self._is_rate_limited: bool = False    # True if currently rate-limited (429)

    # ──────────────────────────────────────────────────────────────
    # Abstract interface
    # ──────────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique provider identifier (e.g., 'groq', 'nvidia', 'gemini', 'openrouter')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider label for the HUD."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Returns True if the required environment variable/API key is present."""
        pass

    # ──────────────────────────────────────────────────────────────
    # Capability flags (subclasses override as needed)
    # ──────────────────────────────────────────────────────────────

    def get_available_models(self) -> List[str]:
        """Returns list of primary models supported by this provider."""
        return []

    def supports_tools(self) -> bool:
        """Returns True if provider supports function/tool calling."""
        return True

    def supports_streaming(self) -> bool:
        """Returns True if provider supports streaming."""
        return True

    def supports_vision(self) -> bool:
        """Returns True if provider supports multimodal/vision input."""
        return False

    # ──────────────────────────────────────────────────────────────
    # Provider Truth & Execution Mode
    # ──────────────────────────────────────────────────────────────

    @property
    def execution_mode(self) -> str:
        """
        Returns 'local' or 'cloud' via the hard validation layer.
        Guarantees that cloud providers cannot masquerade as local.
        """
        from app.core.provider_truth import validate_execution_mode
        return validate_execution_mode(self.provider_id)

    @property
    def endpoint(self) -> str:
        """Canonical network endpoint or local daemon URL for this provider."""
        from app.core.provider_truth import get_provider_endpoint
        return get_provider_endpoint(self.provider_id)

    # ──────────────────────────────────────────────────────────────
    # Health & cooldown
    # ──────────────────────────────────────────────────────────────

    def is_in_cooldown(self) -> bool:
        """Returns True if provider is currently in a cooldown state."""
        return time.time() < self._cooldown_until

    def has_auth_error(self) -> bool:
        """Returns True if this provider has a permanent auth failure latched."""
        return self._auth_error_latched

    def get_health_state(self) -> str:
        """Return the current V6.1 fine-grained health state string."""
        if not self.is_configured():
            return HEALTH_NOT_CONFIGURED
        if self._auth_error_latched:
            return HEALTH_AUTH_ERROR
        return self._health_state

    # ──────────────────────────────────────────────────────────────
    # Recording outcomes
    # ──────────────────────────────────────────────────────────────

    def record_success(self, latency_ms: int, tokens: int = 0):
        """Record a successful request and clear transient error state."""
        self._last_latency_ms = latency_ms
        self._consecutive_failures = 0
        self._cooldown_until = 0.0
        self._is_rate_limited = False
        self._last_success_ts = datetime.utcnow().isoformat()
        self._last_error = None
        self._request_count += 1
        if tokens > 0:
            self._total_tokens += tokens
        # Only clear health state if it was transient (not AUTH_ERROR)
        if not self._auth_error_latched:
            self._health_state = HEALTH_AVAILABLE

    def record_rate_limit(self, error_msg: str, retry_after: Optional[float] = None):
        """Record a 429 rate-limit error, respecting Retry-After when provided."""
        cooldown = float(retry_after) if retry_after is not None and retry_after > 0 else 60.0
        self._is_rate_limited = True
        self.record_failure(
            error_msg=error_msg,
            is_transient=True,
            cooldown_seconds=cooldown,
            health_state=HEALTH_RATE_LIMITED
        )

    def record_failure(
        self,
        error_msg: str,
        is_transient: bool = True,
        cooldown_seconds: float = 30.0,
        health_state: Optional[str] = None
    ):
        """
        Record a request failure with V6.1 fine-grained health categorisation.

        Args:
            error_msg:        Human-readable error description.
            is_transient:     True → enter cooldown (429/timeout/5xx).
                              False → expose error; do NOT enter cooldown.
            cooldown_seconds: Cooldown duration for transient errors.
            health_state:     Explicit V6.1 health state to set. If omitted,
                              inferred from is_transient.
        """
        self._consecutive_failures += 1
        self._last_failure_ts = datetime.utcnow().isoformat()
        self._last_error = str(error_msg)

        # Determine and latch health state
        if health_state:
            self._health_state = health_state
        elif not is_transient:
            self._health_state = HEALTH_AUTH_ERROR  # default for non-transient
        elif cooldown_seconds >= 3600:
            self._health_state = HEALTH_QUOTA_EXHAUSTED
        elif cooldown_seconds >= 60:
            self._health_state = HEALTH_RATE_LIMITED
        elif self._consecutive_failures >= 3:
            self._health_state = HEALTH_DEGRADED
        else:
            self._health_state = HEALTH_UNAVAILABLE

        # AUTH_ERROR latches permanently for this process lifetime
        if self._health_state == HEALTH_AUTH_ERROR:
            self._auth_error_latched = True
            return  # do NOT set cooldown for auth errors

        if is_transient:
            self._cooldown_until = time.time() + cooldown_seconds

    def record_failover_skip(self):
        """Record that this provider was skipped in a failover chain."""
        self._failover_count += 1

    # ──────────────────────────────────────────────────────────────
    # Telemetry
    # ──────────────────────────────────────────────────────────────

    def get_health_status(self) -> Dict[str, Any]:
        """
        Returns V6.1 telemetry snapshot of provider health.
        Health state is one of:
          AVAILABLE / RATE_LIMITED / QUOTA_EXHAUSTED / DEGRADED /
          AUTH_ERROR / UNAVAILABLE / NOT_CONFIGURED
        """
        state = self.get_health_state()

        # Legacy status string for backward-compat with existing HUD code
        if state == HEALTH_AVAILABLE:
            legacy_status = "ONLINE"
        elif state == HEALTH_AUTH_ERROR:
            legacy_status = "AUTH_ERROR"
        elif state == HEALTH_NOT_CONFIGURED:
            legacy_status = "NOT CONFIGURED"
        elif state in (HEALTH_RATE_LIMITED, HEALTH_QUOTA_EXHAUSTED, HEALTH_DEGRADED, HEALTH_UNAVAILABLE):
            legacy_status = "DEGRADED"
        else:
            legacy_status = "OFFLINE"

        now = time.time()
        cooldown_rem = max(0, int(self._cooldown_until - now)) if self.is_in_cooldown() else 0

        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "execution_mode": self.execution_mode,
            "endpoint": self.endpoint,
            # V6.1 fine-grained state
            "health_state": state,
            # Legacy field preserved for backward-compat
            "status": legacy_status,
            "is_configured": self.is_configured(),
            "in_cooldown": self.is_in_cooldown(),
            "is_rate_limited": self._is_rate_limited,
            "cooldown_remaining_sec": cooldown_rem,
            "latency_ms": self._last_latency_ms,
            "consecutive_failures": self._consecutive_failures,
            "failover_count": self._failover_count,
            "last_error": self._last_error,
            "last_success": self._last_success_ts,
            "last_failure": self._last_failure_ts,
            "request_count": self._request_count,
            "total_tokens": self._total_tokens,
            "models": self.get_available_models(),
            "supports_tools": self.supports_tools(),
            "supports_streaming": self.supports_streaming(),
            "supports_vision": self.supports_vision(),
        }
    
    get_status = get_health_status

    # Abstract generation methods
    # ──────────────────────────────────────────────────────────────

    @abstractmethod
    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate a complete text response."""
        pass

    @abstractmethod
    async def stream_response(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens asynchronously."""
        pass
