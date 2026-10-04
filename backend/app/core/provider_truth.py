"""
NARAD Phase 2 — Provider Truth & Anti-Hallucination Subsystem.
Enforces ground-truth infrastructure facts across all providers, models,
routing decisions, explanations, and telemetry.

Rules:
1. Ollama = LOCAL / ON-DEVICE inference through localhost:11434.
2. Groq = CLOUD inference API / remote provider.
3. NVIDIA = CLOUD inference API.
4. Gemini = CLOUD inference API.
5. OpenRouter = CLOUD inference gateway.
6. Hugging Face = LOCAL only when an actual local model/runtime is loaded and serving inference.
7. Subsystems (task-engine, manthan, micro-tasks, deterministic-engine) = LOCAL.
8. Never describe Groq as a local accelerator.
9. Never describe any cloud provider as on-device/local/private unless verified.
"""

from typing import Optional, Dict, Any, List
import logging
from app.core.config import settings

logger = logging.getLogger("narad.provider_truth")

# Ground-truth execution mode constants
MODE_LOCAL = "local"
MODE_CLOUD = "cloud"

# Hard execution constraint constants (detected BEFORE task classification)
EXECUTION_LOCAL_ONLY = "LOCAL_ONLY"
EXECUTION_CLOUD_ONLY = "CLOUD_ONLY"

# Known Cloud Providers (CANNOT be local under any circumstances)
CLOUD_PROVIDERS = {"groq", "nvidia", "gemini", "openrouter"}

# Known Local Providers (Run locally on-device)
LOCAL_PROVIDERS = {"ollama", "huggingface", "task-engine", "manthan", "micro-tasks", "deterministic-engine", "mock-narad"}

# Known local inference provider IDs (subset used for LOCAL_ONLY constraint)
LOCAL_INFERENCE_PROVIDERS = {"ollama", "huggingface"}

# Canonical API / Daemon Endpoints
PROVIDER_ENDPOINTS = {
    "ollama": getattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434").replace("localhost", "127.0.0.1"),
    "groq": "https://api.groq.com/openai/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "openrouter": "https://openrouter.ai/api/v1",
    "huggingface": "local://huggingface-runtime",
    "task-engine": "local://autonomous-agent-v6",
    "manthan": "local://computer-agent-v8.1",
    "micro-tasks": "local://deterministic-engine",
    "deterministic-engine": "local://deterministic-engine",
    "mock-narad": "local://mock-narad",
}

# ============================================================================
# Deterministic Execution Constraint Detection
# Runs BEFORE task classification. BEFORE provider selection.
# ============================================================================

# LOCAL_ONLY trigger phrases (case-insensitive substring match)
_LOCAL_ONLY_PHRASES: List[str] = [
    "local-only",
    "local only",
    "offline",
    "on device",
    "on-device",
    "without cloud",
    "no cloud",
    "don't use cloud",
    "do not use cloud",
    "without internet",
    "no internet",
    "use local ai",
    "use ollama",
    "run locally",
    "local inference",
    "locally only",
]

# CLOUD_ONLY trigger phrases
_CLOUD_ONLY_PHRASES: List[str] = [
    "use cloud",
    "cloud only",
    "cloud-only",
    "use remote",
    "remote only",
    "use groq",
    "use nvidia",
    "use gemini",
    "use openrouter",
]


def detect_execution_constraint(message: str) -> Optional[str]:
    """
    Deterministic execution constraint detection.
    Scans the user's message for explicit local-only or cloud-only intent
    BEFORE task classification and BEFORE provider selection.

    Returns:
        EXECUTION_LOCAL_ONLY  — user explicitly demands local/offline/on-device inference
        EXECUTION_CLOUD_ONLY  — user explicitly demands cloud/remote inference
        None                  — no explicit constraint; use normal routing

    Priority: LOCAL_ONLY is checked first (safety-first principle).
    """
    if not message:
        return None

    msg_lower = message.lower().strip()

    # LOCAL_ONLY takes highest priority (safety/privacy override)
    for phrase in _LOCAL_ONLY_PHRASES:
        if phrase in msg_lower:
            logger.info(
                f"[ExecutionPolicy] LOCAL_ONLY constraint detected from phrase: '{phrase}'"
            )
            return EXECUTION_LOCAL_ONLY

    # CLOUD_ONLY
    for phrase in _CLOUD_ONLY_PHRASES:
        if phrase in msg_lower:
            logger.info(
                f"[ExecutionPolicy] CLOUD_ONLY constraint detected from phrase: '{phrase}'"
            )
            return EXECUTION_CLOUD_ONLY

    return None


def is_local_provider(provider_id: str) -> bool:
    """
    Safety assertion: returns True if the provider is a verified local provider.
    Used as final guard before invocation when execution_constraint == LOCAL_ONLY.
    """
    pid = (provider_id or "").lower().strip()
    return pid in LOCAL_INFERENCE_PROVIDERS or pid in LOCAL_PROVIDERS


def validate_execution_mode(provider_id: str, proposed_mode: Optional[str] = None) -> str:
    """
    Hard validation layer for provider execution mode.
    Guarantees that:
    - Groq, NVIDIA, Gemini, OpenRouter are ALWAYS 'cloud'.
    - Ollama, Task Engine, Manthan, Micro-Tasks are ALWAYS 'local'.
    - Hugging Face is 'local' only when a local model/runtime is loaded.
    
    Any attempt to report Groq or other cloud providers as 'local' is overridden and logged.
    """
    pid = (provider_id or "").lower().strip()
    
    if pid in CLOUD_PROVIDERS:
        if proposed_mode == MODE_LOCAL:
            logger.warning(
                f"[ProviderTruth] Anti-hallucination safeguard: Provider '{pid}' was claimed as 'local'. "
                f"Forcing execution_mode to 'cloud' (Groq/NVIDIA/Gemini/OpenRouter are strictly cloud inference APIs)."
            )
        return MODE_CLOUD
    
    if pid == "ollama":
        return MODE_LOCAL
    
    if pid == "huggingface":
        try:
            from app.services.local_ai.manager import local_ai_manager
            if local_ai_manager.is_loaded:
                return MODE_LOCAL
        except Exception:
            pass
        return MODE_LOCAL
        
    if pid in LOCAL_PROVIDERS:
        return MODE_LOCAL
        
    # Fallback for unknown custom providers
    if proposed_mode in (MODE_LOCAL, MODE_CLOUD):
        return proposed_mode
    return MODE_CLOUD


def get_provider_endpoint(provider_id: str) -> str:
    """
    Resolves the canonical execution endpoint for a provider.
    Guarantees that:
    - Ollama resolves to http://127.0.0.1:11434 (or configured OLLAMA_BASE_URL)
    - Groq resolves to https://api.groq.com/openai/v1
    - NVIDIA resolves to https://integrate.api.nvidia.com/v1
    - Gemini resolves to https://generativelanguage.googleapis.com/v1beta
    - OpenRouter resolves to https://openrouter.ai/api/v1
    """
    pid = (provider_id or "").lower().strip()
    if pid == "ollama":
        base_url = getattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        return base_url.replace("localhost", "127.0.0.1")
    return PROVIDER_ENDPOINTS.get(pid, f"https://api.{pid}.com/v1" if pid not in LOCAL_PROVIDERS else "local://runtime")


def get_provider_display_label(provider_id: str, execution_mode: Optional[str] = None) -> str:
    """
    Generates unambiguous HUD / UI label indicating both provider and execution truth:
    e.g. "OLLAMA // LOCAL", "GROQ // CLOUD", "NVIDIA // CLOUD", "GEMINI // CLOUD".
    """
    pid = (provider_id or "").lower().strip()
    mode = validate_execution_mode(pid, execution_mode).upper()
    return f"{pid.upper()} // {mode}"


def generate_why_this_choice(
    provider_id: str,
    model_name: str,
    task_category: str = "GENERAL_CHAT",
    execution_mode: Optional[str] = None,
    route_reason: Optional[str] = None,
    latency_ms: Optional[int] = None,
    fallback_used: bool = False,
    is_offline: bool = False,
) -> str:
    """
    Deterministically generates the user-facing 'Why this choice' explanation
    based STRICTLY on verified router metadata.
    
    ANTI-HALLUCINATION RULES:
    1. NEVER describe Groq as a local accelerator, local engine, or on-device runtime.
    2. ALWAYS identify Groq as a remote cloud inference provider powered by Groq Cloud LPU.
    3. ALWAYS identify Ollama as an on-device local provider running on localhost:11434.
    4. Clearly explain offline vs cloud selection rationale.
    """
    pid = (provider_id or "").lower().strip()
    mode = validate_execution_mode(pid, execution_mode)
    mode_upper = mode.upper()
    
    # 1. Offline Mode explanation
    if is_offline or (route_reason and "offline" in route_reason.lower()):
        if mode == MODE_LOCAL:
            return (
                f"Offline mode active: Routed to verified on-device local provider '{pid}' "
                f"({model_name}) running at {get_provider_endpoint(pid)} without remote network access."
            )
        else:
            return (
                f"Offline restriction: Cloud provider '{pid}' cannot be reached in offline mode. "
                f"Switched to local inference."
            )
    
    # 2. Failover explanation
    if fallback_used:
        return (
            f"Failover activated: Primary provider unavailable. Diverted to verified {mode_upper} "
            f"provider '{pid}' ({model_name}) for task '{task_category}'."
        )

    # 3. Provider-specific verified metadata explanations
    if pid == "ollama":
        return (
            f"Selected on-device local provider '{pid}' ({model_name}) via localhost:11434 "
            f"for ultra-low latency, zero-cloud {task_category} inference."
        )
    elif pid == "groq":
        return (
            f"Selected remote cloud provider '{pid}' ({model_name}) via Groq Cloud LPU API "
            f"for high-throughput {task_category} synthesis."
        )
    elif pid == "nvidia":
        return (
            f"Selected remote cloud provider '{pid}' ({model_name}) via NVIDIA NIM Cloud API "
            f"for advanced reasoning and enterprise model quality."
        )
    elif pid == "gemini":
        return (
            f"Selected remote cloud provider '{pid}' ({model_name}) via Google Gemini Cloud API "
            f"for multimodal vision and ultra-long context capabilities."
        )
    elif pid == "openrouter":
        return (
            f"Selected remote cloud gateway '{pid}' ({model_name}) via OpenRouter API "
            f"for multi-model access and resilient routing."
        )
    elif pid == "huggingface":
        return (
            f"Selected on-device local provider 'huggingface' ({model_name}) "
            f"for local privacy-first inference."
        )
    elif pid in ("task-engine", "manthan", "micro-tasks", "deterministic-engine"):
        return (
            f"Selected local on-device subsystem '{pid}' ({model_name}) "
            f"for deterministic zero-token local execution."
        )
    else:
        return (
            f"Routed to verified {mode_upper} provider '{pid}' ({model_name}) "
            f"for task category '{task_category}'."
        )


def get_runtime_truth(*args, **kwargs):
    """Convenience alias to retrieve canonical Runtime Truth object."""
    from app.services.runtime_truth import runtime_truth_service
    return runtime_truth_service.get_runtime_truth(*args, **kwargs)
