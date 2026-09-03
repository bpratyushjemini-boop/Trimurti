import time
import logging
from typing import List, Dict, Any, Optional

from app.core.router import model_router

logger = logging.getLogger(__name__)

class NaradCore:
    """
    NARAD Core Intelligence Orchestration Service.
    Acts as the single point of entry for conversational synthesis:
    1. Receives directive / message & history
    2. Consults Model Router for provider & model selection
    3. Dispatches query to resolved provider
    4. Measures precise round-trip latency
    5. Returns response with complete model metadata
    """

    async def process_message(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        requested_provider: Optional[str] = None,
        requested_model: Optional[str] = None
    ) -> Dict[str, Any]:
        clean_message = message.strip()
        if not clean_message:
            return {
                "response": "Directive cannot be empty.",
                "provider": "narad-core",
                "model": "none",
                "latency_ms": 0,
                "status": "validation_error",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        # Assemble full conversation messages array
        messages: List[Dict[str, str]] = []
        if history:
            messages.extend(history)
        
        # Ensure current message is at the end of the context
        if not messages or messages[-1].get("content") != clean_message or messages[-1].get("role") != "user":
            messages.append({"role": "user", "content": clean_message})

        # 1. Ask Model Router for provider & model selection
        route = model_router.resolve_route(
            requested_provider=requested_provider,
            requested_model=requested_model,
            task_type="text"
        )

        logger.info(f"NARAD Core dispatching to provider '{route.provider_id}' [model: {route.model_name}]")

        # 2. Dispatch request to provider and measure exact round-trip latency
        start_time = time.perf_counter()
        try:
            provider_result = await route.provider.generate_response(
                messages=messages,
                model=route.model_name
            )
        except Exception as e:
            logger.error(f"Unexpected error in provider '{route.provider_id}': {e}", exc_info=True)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return {
                "response": f"⚠️ **NARAD Core Dispatch Error:** An error occurred while communicating with provider '{route.provider_id}': {str(e)}",
                "provider": route.provider_id,
                "model": route.model_name,
                "latency_ms": elapsed_ms,
                "status": "error",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        # 3. Assemble response + model metadata
        return {
            "response": provider_result.get("content", ""),
            "provider": provider_result.get("provider", route.provider_id),
            "model": provider_result.get("model", route.model_name),
            "latency_ms": elapsed_ms,
            "status": provider_result.get("status", "success"),
            "usage": provider_result.get("usage", {})
        }

# Global singleton NARAD Core service instance
narad_core = NaradCore()
