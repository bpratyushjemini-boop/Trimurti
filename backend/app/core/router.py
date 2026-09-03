import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from app.providers.base import BaseLLMProvider
from app.providers.manager import provider_manager
from app.core.config import settings

logger = logging.getLogger(__name__)

@dataclass
class RouteDecision:
    """
    Encapsulates the deterministic routing decision made by the Model Router.
    """
    provider_id: str
    model_name: str
    provider: BaseLLMProvider
    is_configured: bool
    routing_reason: str

class ModelRouter:
    """
    Extensible, deterministic Model Router for NARAD Core.
    Resolves the appropriate AI model provider and model variant based on
    system configuration, request parameters, and provider readiness.
    """

    def __init__(self):
        self._default_provider_id = settings.NARAD_DEFAULT_PROVIDER or "gemini"
        self._default_model = settings.NARAD_DEFAULT_MODEL or "gemini-2.5-flash"

    def resolve_route(
        self,
        requested_provider: Optional[str] = None,
        requested_model: Optional[str] = None,
        task_type: str = "text"
    ) -> RouteDecision:
        """
        Deterministic routing resolution:
        1. Explicit requested provider (if valid in registry)
        2. System configured default provider (Gemini primary)
        3. Model selection based on target provider capabilities
        """
        target_provider_id = (requested_provider or self._default_provider_id).lower().strip()
        provider = provider_manager.get_provider(target_provider_id)
        
        # Determine actual provider id resolved (handles fallback to default if requested was invalid)
        resolved_pid = provider.provider_id

        # Model resolution logic
        if requested_model and requested_model.strip():
            resolved_model = requested_model.strip()
        elif resolved_pid == "gemini":
            resolved_model = self._default_model
        elif resolved_pid == "mock-narad":
            resolved_model = "narad-core-v1"
        elif resolved_pid == "groq":
            resolved_model = "llama-3.3-70b-versatile"
        elif resolved_pid == "claude":
            resolved_model = "claude-3-5-sonnet-latest"
        elif resolved_pid == "openai":
            resolved_model = "gpt-4o"
        elif resolved_pid == "openrouter":
            resolved_model = "auto"
        else:
            resolved_model = "default"

        is_configured = provider.is_configured()
        reason = f"Deterministic route for '{task_type}' task via '{resolved_pid}' provider."

        logger.info(f"Model Router resolved: provider={resolved_pid}, model={resolved_model}, configured={is_configured}")

        return RouteDecision(
            provider_id=resolved_pid,
            model_name=resolved_model,
            provider=provider,
            is_configured=is_configured,
            routing_reason=reason
        )

    def get_router_status(self) -> Dict[str, Any]:
        """
        Telemetry snapshot of the router's current configuration.
        """
        active_route = self.resolve_route()
        return {
            "default_provider": self._default_provider_id,
            "default_model": self._default_model,
            "active_provider": active_route.provider_id,
            "active_model": active_route.model_name,
            "is_configured": active_route.is_configured,
            "available_providers": provider_manager.list_providers()
        }

# Global singleton Model Router instance
model_router = ModelRouter()
