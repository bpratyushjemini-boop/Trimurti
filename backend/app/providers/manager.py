from typing import Dict, List, Any, Optional, AsyncGenerator
import asyncio
from app.providers.base import BaseLLMProvider
from app.providers.gemini import GeminiProvider
from app.providers.groq import GroqProvider
from app.providers.nvidia import NvidiaProvider
from app.providers.openrouter import OpenRouterProvider
from app.core.config import settings

class StubProvider(BaseLLMProvider):
    """
    Fallback diagnostic/simulated provider.
    Used when mock mode is explicitly requested or when running offline tests.
    """

    @property
    def provider_id(self) -> str:
        return "mock-narad"

    @property
    def display_name(self) -> str:
        return "NARAD Simulated Core (Fallback)"

    def is_configured(self) -> bool:
        return True

    def get_available_models(self) -> List[str]:
        return ["narad-core-v1"]

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "")
                break

        user_query_lower = last_user_msg.lower().strip()

        if any(greet in user_query_lower for greet in ["hello", "hi", "hey", "who are you", "what can you do"]):
            response_text = (
                "Greetings. I am **NARAD**—your private, personal AI assistant and primary interface "
                "for your local TRIMURTI system.\n\n"
                "I am currently operating in Milestone 2 interface mode. "
                "All sessions and messages are stored strictly on your local machine in SQLite.\n\n"
                "How may I assist you today?"
            )
        elif "status" in user_query_lower or "system" in user_query_lower:
            response_text = (
                "**NARAD System Status Overview:**\n\n"
                "• **Architecture**: Private Single-User Standalone\n"
                "• **Interface Engine**: React 18 + Vite (JARVIS HUD visual design)\n"
                "• **Local Gateway**: FastAPI 0.110 (127.0.0.1)\n"
                "• **Data Storage**: Isolated local SQLite database\n"
                "• **AI Routing Layer**: Model Router V3.1 Active\n\n"
                "All local diagnostics are nominal. Ready for your directive."
            )
        else:
            response_text = (
                f"Understood. I have logged your directive: **\"{last_user_msg}\"**\n\n"
                "This conversation is stored locally in your private SQLite database."
            )

        return {
            "content": response_text,
            "provider": self.provider_id,
            "model": model or "narad-core-v1",
            "latency_ms": 1,
            "status": "success",
            "usage": {"prompt_tokens": len(last_user_msg.split()), "completion_tokens": len(response_text.split())}
        }

    async def stream_response(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        result = await self.generate_response(messages, model, temperature, max_tokens, **kwargs)
        words = result["content"].split(" ")
        for word in words:
            yield word + " "
            await asyncio.sleep(0.02)


class FutureSlotProvider(BaseLLMProvider):
    """
    Reserved provider slot for upcoming milestones (Claude, OpenAI).
    """

    def __init__(self, pid: str, name: str, config_key: str):
        super().__init__()
        self._pid = pid
        self._name = name
        self._config_key = config_key

    @property
    def provider_id(self) -> str:
        return self._pid

    @property
    def display_name(self) -> str:
        return self._name

    def is_configured(self) -> bool:
        val = getattr(settings, self._config_key, "")
        return bool(val and val.strip())

    async def generate_response(self, messages, model=None, **kwargs) -> Dict[str, Any]:
        return {
            "content": f"⚠️ **{self._name} connector slot is reserved.** Integration will arrive in future milestone updates.",
            "provider": self.provider_id,
            "model": model or "unsupported",
            "status": "not_implemented",
            "is_transient": False,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0}
        }

    async def stream_response(self, messages, model=None, **kwargs) -> AsyncGenerator[str, None]:
        yield f"⚠️ {self._name} connector is reserved for future integration."


class ProviderManager:
    """
    Central registry and dispatcher for AI model providers in NARAD.
    Manages Groq, NVIDIA NIM, Gemini, and OpenRouter with unified health and lifecycle.
    """

    def __init__(self):
        self._providers: Dict[str, BaseLLMProvider] = {}
        self._active_provider_id: str = settings.NARAD_DEFAULT_PROVIDER or "groq"
        
        # 1. Register Groq Provider (Primary Ultra-Fast Inference)
        self.register_provider(GroqProvider())

        # 2. Register NVIDIA NIM Provider (High-Throughput Open Models)
        self.register_provider(NvidiaProvider())

        # 3. Register Gemini Provider (Multimodal & Long-Context)
        self.register_provider(GeminiProvider())

        # 4. Register OpenRouter Provider (Universal Multi-Vendor Gateway)
        self.register_provider(OpenRouterProvider())

        # 5. Register Future Slots (Claude, OpenAI)
        self.register_provider(FutureSlotProvider("claude", "Anthropic Claude", "ANTHROPIC_API_KEY"))
        self.register_provider(FutureSlotProvider("openai", "OpenAI GPT", "OPENAI_API_KEY"))

        # 6. Register Local Hugging Face Provider (On-Device Inference)
        from app.providers.huggingface import LocalHuggingFaceProvider
        self.register_provider(LocalHuggingFaceProvider())

        # 7. Register Native Ollama Provider (On-Device Fast Inference)
        from app.providers.ollama import OllamaProvider
        self.register_provider(OllamaProvider())

        # 8. Register Configured OpenAI-Compatible Interchangeable Gateway
        from app.providers.openai_compatible import OpenAICompatibleProvider
        custom_base = getattr(settings, "OPENAI_COMPATIBLE_BASE_URL", "")
        custom_key = getattr(settings, "OPENAI_COMPATIBLE_API_KEY", "")
        custom_model = getattr(settings, "OPENAI_COMPATIBLE_MODEL", "") or "default-model"
        custom_name = getattr(settings, "OPENAI_COMPATIBLE_NAME", "") or "OpenAI-Compatible Gateway"
        self.register_provider(
            OpenAICompatibleProvider(
                provider_id="custom_gateway",
                display_name=custom_name,
                base_url=custom_base,
                api_key=custom_key,
                default_model=custom_model,
                available_models=[custom_model] if custom_model else ["default-model"]
            )
        )

    def register_provider(self, provider: BaseLLMProvider):
        self._providers[provider.provider_id] = provider

    def get_provider(self, provider_id: Optional[str] = None) -> BaseLLMProvider:
        pid = (provider_id or self._active_provider_id).lower().strip()
        if pid not in self._providers:
            return (
                self._providers.get(self._active_provider_id)
                or self._providers.get("groq")
                or self._providers.get("nvidia")
                or self._providers.get("gemini")
                or self._providers.get("openrouter")
                or self._providers.get("ollama")
                or self._providers.get("mock-narad")
            )
        return self._providers[pid]

    def set_active_provider(self, provider_id: str) -> bool:
        pid = provider_id.lower().strip()
        if pid in self._providers:
            self._active_provider_id = pid
            return True
        return False

    def list_providers(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": p.provider_id,
                "display_name": p.display_name,
                "is_configured": p.is_configured(),
                "is_active": p.provider_id == self._active_provider_id,
                "health": p.get_health_status()
            }
            for p in self._providers.values()
        ]

    def get_all_providers(self) -> Dict[str, BaseLLMProvider]:
        return dict(self._providers)

    def get_configured_providers(self) -> List[BaseLLMProvider]:
        """Return all providers with valid credentials."""
        return [p for p in self._providers.values() if p.is_configured() and p.provider_id != "mock-narad"]

# Global singleton provider manager instance
provider_manager = ProviderManager()

