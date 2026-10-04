"""
NARAD V3.1 — Intelligent Model Router & Capability Registry.
Dynamically classifies user directives into logical task categories,
selects the optimal AI provider and model based on capabilities, latency,
and health status, and constructs deterministic failover candidate chains.
"""

import logging
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field

from app.providers.base import BaseLLMProvider
from app.providers.manager import provider_manager
from app.core.config import settings

logger = logging.getLogger(__name__)

# Logical Task Categories for NARAD V3.1 & V7.1 & V7.2 & Phase 2
TASK_FAST_CHAT = "FAST_CHAT"
TASK_GENERAL_CHAT = "GENERAL_CHAT"
TASK_REASONING = "REASONING"
TASK_CODING = "CODING"
TASK_TOOL_USE = "TOOL_USE"
TASK_LONG_CONTEXT = "LONG_CONTEXT"
TASK_VISION = "VISION"
TASK_VOICE = "VOICE"
TASK_LOCAL = "LOCAL"
TASK_LOCAL_FAST = "LOCAL_FAST"

# Phase 2 Token Efficiency & Classification Categories
TASK_CHAT = "CHAT"
TASK_FAST = "FAST"
TASK_AUTONOMOUS_TASK = "AUTONOMOUS_TASK"
TASK_KNOWLEDGE = "KNOWLEDGE"
TASK_MEMORY = "MEMORY"

ALL_TASK_CATEGORIES = [
    TASK_FAST_CHAT,
    TASK_GENERAL_CHAT,
    TASK_REASONING,
    TASK_CODING,
    TASK_TOOL_USE,
    TASK_LONG_CONTEXT,
    TASK_VISION,
    TASK_VOICE,
    TASK_LOCAL,
    TASK_LOCAL_FAST,
    TASK_CHAT,
    TASK_FAST,
    TASK_AUTONOMOUS_TASK,
    TASK_KNOWLEDGE,
    TASK_MEMORY,
]


@dataclass
class ModelMetadata:
    """Internal capability and benchmark metadata for a registered model."""
    provider: str
    model_id: str
    capabilities: List[str]
    speed_score: int       # 1-10
    reasoning_score: int   # 1-10
    coding_score: int      # 1-10
    context_size: int      # in tokens
    tool_support: bool
    vision_support: bool
    latency_class: str = "medium"  # "ultra_low", "low", "medium", "high"
    cost_class: str = "medium"     # "free", "low", "medium", "high"
    enabled: bool = True


@dataclass
class RouteDecision:
    """Encapsulates the deterministic routing decision made by the Model Router."""
    provider_id: str
    model_name: str
    provider: BaseLLMProvider
    is_configured: bool
    task_category: str
    routing_reason: str
    failover_candidates: List[Dict[str, str]] = field(default_factory=list)
    execution_mode: str = "cloud"
    execution: str = "cloud"
    endpoint: str = ""
    why_this_choice: str = ""
    fallback_used: bool = False
    execution_constraint: Optional[str] = None  # LOCAL_ONLY, CLOUD_ONLY, or None

    def __post_init__(self):
        from app.core.provider_truth import (
            validate_execution_mode,
            get_provider_endpoint,
            generate_why_this_choice,
        )
        # Enforce hard validation layer: Groq/NVIDIA/Gemini/OpenRouter are ALWAYS cloud; Ollama is ALWAYS local
        self.execution_mode = validate_execution_mode(self.provider_id, self.execution_mode)
        self.execution = self.execution_mode
        if not self.endpoint:
            self.endpoint = get_provider_endpoint(self.provider_id)
        if not self.why_this_choice:
            self.why_this_choice = generate_why_this_choice(
                provider_id=self.provider_id,
                model_name=self.model_name,
                task_category=self.task_category,
                execution_mode=self.execution_mode,
                route_reason=self.routing_reason,
                fallback_used=self.fallback_used
            )

    @property
    def task_type(self) -> str:
        return self.task_category.lower()

    @property
    def primary_provider(self) -> str:
        return self.provider_id

    @property
    def display_label(self) -> str:
        from app.core.provider_truth import get_provider_display_label
        return get_provider_display_label(self.provider_id, self.execution_mode)


class ModelCapabilityRegistry:
    """
    Central catalog of model capabilities, context sizes, and tool support
    across all supported NARAD providers (Groq, NVIDIA NIM, Gemini, OpenRouter).
    """

    def __init__(self):
        self._models: List[ModelMetadata] = []
        self._initialize_registry()

    def _initialize_registry(self):
        # 1. Groq Models (Ultra-Low Latency LPU)
        self.register(ModelMetadata(
            provider="groq",
            model_id="openai/gpt-oss-120b",
            capabilities=[TASK_FAST_CHAT, TASK_GENERAL_CHAT, TASK_TOOL_USE, TASK_CODING, TASK_VOICE, TASK_REASONING],
            speed_score=10,
            reasoning_score=9,
            coding_score=8,
            context_size=128000,
            tool_support=True,
            vision_support=False,
            latency_class="ultra_low",
            cost_class="low"
        ))
        self.register(ModelMetadata(
            provider="groq",
            model_id="openai/gpt-oss-20b",
            capabilities=[TASK_FAST_CHAT, TASK_GENERAL_CHAT, TASK_TOOL_USE, TASK_VOICE],
            speed_score=10,
            reasoning_score=8,
            coding_score=8,
            context_size=128000,
            tool_support=True,
            vision_support=False,
            latency_class="ultra_low",
            cost_class="low"
        ))
        self.register(ModelMetadata(
            provider="groq",
            model_id="llama-3.3-70b-versatile",
            capabilities=[TASK_FAST_CHAT, TASK_GENERAL_CHAT, TASK_REASONING, TASK_CODING, TASK_TOOL_USE],
            speed_score=9,
            reasoning_score=9,
            coding_score=9,
            context_size=128000,
            tool_support=True,
            vision_support=False,
            latency_class="ultra_low",
            cost_class="low"
        ))
        self.register(ModelMetadata(
            provider="groq",
            model_id="llama-3.1-8b-instant",
            capabilities=[TASK_FAST_CHAT, TASK_VOICE],
            speed_score=10,
            reasoning_score=7,
            coding_score=7,
            context_size=128000,
            tool_support=True,
            vision_support=False,
            latency_class="ultra_low",
            cost_class="low"
        ))

        # 2. NVIDIA NIM Models (Enterprise Open Source Engines)
        self.register(ModelMetadata(
            provider="nvidia",
            model_id="nvidia/llama-3.1-nemotron-70b-instruct",
            capabilities=[TASK_GENERAL_CHAT, TASK_REASONING, TASK_CODING, TASK_TOOL_USE],
            speed_score=8,
            reasoning_score=9,
            coding_score=9,
            context_size=128000,
            tool_support=True,
            vision_support=False,
            latency_class="low",
            cost_class="medium"
        ))
        self.register(ModelMetadata(
            provider="nvidia",
            model_id="deepseek-ai/deepseek-r1",
            capabilities=[TASK_REASONING, TASK_CODING],
            speed_score=7,
            reasoning_score=10,
            coding_score=10,
            context_size=64000,
            tool_support=False,
            vision_support=False,
            latency_class="medium",
            cost_class="medium"
        ))
        self.register(ModelMetadata(
            provider="nvidia",
            model_id="meta/llama-3.1-70b-instruct",
            capabilities=[TASK_GENERAL_CHAT, TASK_CODING, TASK_TOOL_USE],
            speed_score=8,
            reasoning_score=8,
            coding_score=8,
            context_size=128000,
            tool_support=True,
            vision_support=False,
            latency_class="low",
            cost_class="medium"
        ))

        # 3. Google Gemini Models (Multimodal, Ultra-Long Context)
        self.register(ModelMetadata(
            provider="gemini",
            model_id="gemini-2.5-flash",
            capabilities=[TASK_FAST_CHAT, TASK_GENERAL_CHAT, TASK_LONG_CONTEXT, TASK_VISION, TASK_TOOL_USE, TASK_VOICE],
            speed_score=9,
            reasoning_score=8,
            coding_score=8,
            context_size=1000000,
            tool_support=True,
            vision_support=True,
            latency_class="low",
            cost_class="low"
        ))
        self.register(ModelMetadata(
            provider="gemini",
            model_id="gemini-2.5-pro",
            capabilities=[TASK_REASONING, TASK_CODING, TASK_LONG_CONTEXT, TASK_VISION],
            speed_score=7,
            reasoning_score=10,
            coding_score=10,
            context_size=2000000,
            tool_support=True,
            vision_support=True,
            latency_class="medium",
            cost_class="high"
        ))

        # 4. OpenRouter Models (Universal Gateway)
        self.register(ModelMetadata(
            provider="openrouter",
            model_id="meta-llama/llama-3.3-70b-instruct",
            capabilities=[TASK_GENERAL_CHAT, TASK_TOOL_USE, TASK_CODING],
            speed_score=8,
            reasoning_score=9,
            coding_score=9,
            context_size=128000,
            tool_support=True,
            vision_support=False,
            latency_class="low",
            cost_class="medium"
        ))
        self.register(ModelMetadata(
            provider="openrouter",
            model_id="anthropic/claude-3.5-sonnet",
            capabilities=[TASK_CODING, TASK_REASONING, TASK_TOOL_USE, TASK_VISION],
            speed_score=8,
            reasoning_score=10,
            coding_score=10,
            context_size=200000,
            tool_support=True,
            vision_support=True,
            latency_class="medium",
            cost_class="high"
        ))
        self.register(ModelMetadata(
            provider="openrouter",
            model_id="deepseek/deepseek-r1",
            capabilities=[TASK_REASONING, TASK_CODING],
            speed_score=7,
            reasoning_score=10,
            coding_score=10,
            context_size=64000,
            tool_support=False,
            vision_support=False,
            latency_class="medium",
            cost_class="medium"
        ))

        # 5. Local Hugging Face Models (On-Device, Privacy-First, Offline)
        from app.services.local_ai.manager import local_ai_manager
        self.register(ModelMetadata(
            provider="huggingface",
            model_id=local_ai_manager.model_id,
            capabilities=[TASK_LOCAL, TASK_FAST_CHAT],
            speed_score=9,
            reasoning_score=6,
            coding_score=5,
            context_size=8192,
            tool_support=False,
            vision_support=False,
            latency_class="low",
            cost_class="free"
        ))

        # 6. Native Ollama Models (Local Fast On-Device Inference)
        self.register(ModelMetadata(
            provider="ollama",
            model_id=getattr(settings, "OLLAMA_MODEL", "qwen3.5:0.8b"),
            capabilities=[TASK_LOCAL_FAST, TASK_FAST_CHAT],
            speed_score=10,
            reasoning_score=6,
            coding_score=5,
            context_size=32768,
            tool_support=True,
            vision_support=False,
            latency_class="ultra_low",
            cost_class="free"
        ))

    def register(self, meta: ModelMetadata):
        self._models.append(meta)

    def get_models_for_category(self, category: str, requires_tools: bool = False) -> List[ModelMetadata]:
        return [
            m for m in self._models
            if m.enabled
            and category in m.capabilities
            and (not requires_tools or m.tool_support)
        ]

    def get_primary_model_for_provider(self, provider_id: str) -> str:
        for m in self._models:
            if m.provider == provider_id and m.enabled:
                return m.model_id
        if provider_id == "groq":
            return "openai/gpt-oss-120b"
        elif provider_id == "nvidia":
            return "nvidia/llama-3.1-nemotron-70b-instruct"
        elif provider_id == "gemini":
            return "gemini-2.5-flash"
        elif provider_id == "openrouter":
            return "meta-llama/llama-3.3-70b-instruct"
        elif provider_id == "huggingface":
            from app.services.local_ai.manager import local_ai_manager
            return local_ai_manager.model_id
        elif provider_id == "ollama":
            return getattr(settings, "OLLAMA_MODEL", "qwen3.5:0.8b")
        return "default"

    def get_vision_model_for_provider(self, provider_id: str) -> str:
        for m in self._models:
            if m.provider == provider_id and m.enabled and m.vision_support:
                return m.model_id
        if provider_id == "gemini":
            return "gemini-2.5-flash"
        elif provider_id == "openrouter":
            return "anthropic/claude-3.5-sonnet"
        return self.get_primary_model_for_provider(provider_id)


class ModelRouter:
    """
    Intelligent Model Router for NARAD Core.
    Analyzes directive task requirements, provider readiness, rate-limits,
    and health states to make deterministic, high-efficiency routing choices.
    """

    def __init__(self):
        self.registry = ModelCapabilityRegistry()

    @property
    def default_provider_id(self) -> str:
        return settings.NARAD_DEFAULT_PROVIDER or "groq"

    @property
    def default_model(self) -> str:
        return settings.NARAD_DEFAULT_MODEL or "openai/gpt-oss-120b"

    def classify_task(
        self,
        message: str,
        is_voice: bool = False,
        has_vision: bool = False
    ) -> str:
        """
        Classifies incoming request into a logical task category.
        """
        if has_vision:
            return TASK_VISION
        if is_voice:
            return TASK_VOICE

        msg_lower = message.lower().strip()

        # 0. Lightweight Extraction & Intent Classification Directives (Local Fast Tier)
        local_fast_triggers = [
            "classify intent", "intent of", "classify the intent", "identify intent",
            "extract json", "extract entities", "extract name", "extract date", "extract email",
            "extract phone", "extract keyword", "extract location", "extract city", "extract country",
            "format as json", "format text", "format as markdown", "format list",
            "local fast", "fast local", "use ollama", "run on ollama", "ollama fast"
        ]
        if any(trig in msg_lower for trig in local_fast_triggers):
            return TASK_LOCAL_FAST

        # 1. Explicit Local / Offline mode directives (Privacy-First / Offline Execution)
        local_triggers = [
            "run locally", "use local model", "offline mode", "local ai",
            "huggingface", "local inference", "use huggingface"
        ]
        if any(trig in msg_lower for trig in local_triggers):
            return TASK_LOCAL

        # 2. Code-centric directives
        code_triggers = [
            "def ", "class ", "function ", "import ", "const ", "var ",
            "let ", "```", "traceback", "syntaxerror", "sql", "bug in code",
            "write a function", "refactor", "debug", "python script", "react component",
            "implementation in rust", "implementation in python", "implementation in",
            "unit tests", "unit test", "write a script", "write a program", "binary search tree"
        ]
        if any(trig in msg_lower for trig in code_triggers):
            return TASK_CODING

        # 3. Math and deep logical reasoning
        reasoning_triggers = [
            "step by step", "prove that", "derive", "mathematical proof",
            "logical deduction", "reasoning behind", "analyze deeply", "theorem",
            "root cause analysis", "trade-off comparison", "trade-off", "tradeoff"
        ]
        if any(trig in msg_lower for trig in reasoning_triggers):
            return TASK_REASONING

        # 4. Tool use directives (web search, documents, time, calc, memory, computer control)
        tool_triggers = [
            "what time", "current time", "what date", "today's date",
            "search web", "latest news", "current price", "according to the document",
            "document mention", "remember that", "what is my name", "calculate",
            "what is 847 *", "calculate ", "who is current",
            "open music", "apple music", "play back in black", "open application",
            "launch ", "screenshot", "take screenshot", "open url", "create file",
            "delete file", "create folder", "move file"
        ]
        if any(trig in msg_lower for trig in tool_triggers):
            return TASK_TOOL_USE

        # 5. Long context
        if len(message) > 4000:
            return TASK_LONG_CONTEXT

        # 6. Fast local transformations / lightweight formatting (Phase 2 Target 1)
        fast_local_triggers = [
            "format this as", "format as", "lowercase this", "uppercase this",
            "convert to json", "format json", "capitalize this", "trim this"
        ]
        if any(trig in msg_lower for trig in fast_local_triggers):
            return TASK_LOCAL_FAST

        # 7. Fast chat / brief greetings
        if len(message.split()) <= 4 and any(g in msg_lower for g in ["hi", "hello", "hey", "who are you", "what's up"]):
            return TASK_FAST_CHAT

        return TASK_GENERAL_CHAT

    def _capability_order(self, category: str) -> List[str]:
        """
        Capability-Aware Routing Order with Offline/Degraded Mode Support.

        Returns the preferred provider priority list for a task category.
        If offline, prioritizes local on-device providers without attempting cloud requests.
        """
        from app.services.connectivity import connectivity_service
        if not connectivity_service.is_online():
            return ["ollama", "huggingface", "mock-narad"]

        if category in (TASK_LOCAL_FAST, TASK_FAST):
            return ["ollama", "groq", "nvidia", "openrouter", "gemini", "huggingface"]
        elif category in (TASK_LOCAL,):
            return ["ollama", "huggingface", "groq", "nvidia", "openrouter", "gemini"]
        elif category in (TASK_VISION,):
            return ["gemini", "openrouter", "nvidia"]
        elif category in (TASK_REASONING, TASK_CODING):
            return ["nvidia", "groq", "openrouter", "gemini", "huggingface", "ollama"]
        elif category in (TASK_FAST_CHAT,):
            return ["groq", "nvidia", "openrouter", "gemini", "ollama"]
        else:  # GENERAL_CHAT, CHAT, TOOL_USE, AUTONOMOUS_TASK, KNOWLEDGE, MEMORY, LONG_CONTEXT, VOICE
            return ["groq", "nvidia", "openrouter", "gemini", "huggingface", "ollama"]

    def _is_provider_eligible(
        self,
        provider,
        require_vision: bool = False,
        allow_cooldown: bool = False
    ) -> bool:
        """
        Returns True if a provider can be selected for dispatch.
        In offline mode, strictly rejects Groq/NVIDIA/Gemini/OpenRouter (cloud providers).
        AUTH_ERROR providers are always excluded (permanent, no retries).
        NOT CONFIGURED providers are excluded.
        Providers in cooldown are excluded unless allow_cooldown=True.
        """
        from app.services.connectivity import connectivity_service
        from app.core.provider_truth import validate_execution_mode

        if not connectivity_service.is_online():
            # Rule 6: Permit Ollama and verified local providers only; reject cloud providers
            if validate_execution_mode(provider.provider_id) != "local":
                return False

        if not provider.is_configured():
            return False
        if provider.has_auth_error():
            return False
        if not allow_cooldown and provider.is_in_cooldown():
            return False
        if require_vision and not provider.supports_vision():
            return False
        return True

    def resolve_route(
        self,
        requested_provider: Optional[str] = None,
        requested_model: Optional[str] = None,
        message: Optional[str] = None,
        is_voice: bool = False,
        task_category: Optional[str] = None,
        execution_constraint: Optional[str] = None
    ) -> RouteDecision:
        """
        V6.2 Capability-Aware Route Resolution with Execution Constraint Enforcement.

        Pipeline (in priority order):
        1. Detect execution constraint (LOCAL_ONLY / CLOUD_ONLY) — HIGHEST PRIORITY.
        2. If LOCAL_ONLY: restrict selection to verified local providers ONLY.
        3. If CLOUD_ONLY: restrict selection to cloud providers ONLY.
        4. Otherwise: classify task, get capability order, select provider.
        5. Enforce offline mode: reject cloud providers, permit Ollama/local only.
        6. Select the first eligible (configured, not AUTH_ERROR, not in cooldown) provider.
        7. Build a failover chain from the remaining eligible providers in order.
        """
        from app.services.connectivity import connectivity_service
        from app.core.provider_truth import (
            validate_execution_mode,
            get_provider_endpoint,
            generate_why_this_choice,
            detect_execution_constraint,
            is_local_provider,
            EXECUTION_LOCAL_ONLY,
            EXECUTION_CLOUD_ONLY,
            CLOUD_PROVIDERS as KNOWN_CLOUD_PROVIDERS,
        )

        is_offline = not connectivity_service.is_online()

        # =====================================================================
        # STEP 0: Detect execution constraint BEFORE task classification
        # This has HIGHEST ROUTING PRIORITY and overrides all other decisions.
        # =====================================================================
        if execution_constraint is None and message:
            execution_constraint = detect_execution_constraint(message)

        # =====================================================================
        # STEP 0a: LOCAL_ONLY HARD ENFORCEMENT
        # Priority: HARD EXECUTION CONSTRAINT > provider availability > task type > model preference > normal routing
        # =====================================================================
        if execution_constraint == EXECUTION_LOCAL_ONLY:
            category = task_category or (
                self.classify_task(message or "", is_voice=is_voice) if message else TASK_GENERAL_CHAT
            )
            # Only allow verified local providers
            local_order = ["ollama", "huggingface"]
            resolved_pid = None
            resolved_provider = None

            for pid in local_order:
                p = provider_manager.get_provider(pid)
                if p and p.is_configured() and not p.has_auth_error():
                    resolved_pid = pid
                    resolved_provider = p
                    break

            if resolved_pid is None:
                # No local provider available — return controlled error, NEVER fall back to cloud
                fallback_p = provider_manager.get_provider("ollama")
                reason = "LOCAL_ONLY: No local provider (Ollama/HuggingFace) is currently available."
                logger.warning(f"Model Router: LOCAL_ONLY constraint active but no local provider available.")
                return RouteDecision(
                    provider_id="ollama",
                    model_name=self.registry.get_primary_model_for_provider("ollama"),
                    provider=fallback_p,
                    is_configured=False,
                    task_category=category,
                    routing_reason=reason,
                    failover_candidates=[],
                    execution_mode="local",
                    endpoint=get_provider_endpoint("ollama"),
                    why_this_choice=f"LOCAL_ONLY execution constraint active: {reason} Cloud providers are forbidden.",
                    fallback_used=False,
                    execution_constraint=EXECUTION_LOCAL_ONLY,
                )

            resolved_model = (
                requested_model.strip()
                if requested_model and requested_model.strip()
                else self.registry.get_primary_model_for_provider(resolved_pid)
            )
            # Failover chain: ONLY other local providers
            failover_chain = [
                {"provider": pid, "model": self.registry.get_primary_model_for_provider(pid)}
                for pid in local_order
                if pid != resolved_pid
                and provider_manager.get_provider(pid)
                and provider_manager.get_provider(pid).is_configured()
            ]
            reason = f"LOCAL_ONLY execution constraint: Routed to verified local provider '{resolved_pid}'."
            why = (
                f"LOCAL_ONLY execution policy enforced: Selected on-device local provider '{resolved_pid}' "
                f"({resolved_model}) via {get_provider_endpoint(resolved_pid)}. "
                f"Cloud providers (Groq/NVIDIA/Gemini/OpenRouter) are forbidden by user directive. "
                f"Internet: NOT USED."
            )
            logger.info(
                f"Model Router (V6.2): LOCAL_ONLY → provider={resolved_pid}, "
                f"model={resolved_model}, task={category}, failovers={len(failover_chain)}"
            )
            return RouteDecision(
                provider_id=resolved_pid,
                model_name=resolved_model,
                provider=resolved_provider,
                is_configured=True,
                task_category=category,
                routing_reason=reason,
                failover_candidates=failover_chain,
                execution_mode="local",
                endpoint=get_provider_endpoint(resolved_pid),
                why_this_choice=why,
                fallback_used=False,
                execution_constraint=EXECUTION_LOCAL_ONLY,
            )

        # =====================================================================
        # STEP 0b: CLOUD_ONLY HARD ENFORCEMENT
        # =====================================================================
        if execution_constraint == EXECUTION_CLOUD_ONLY:
            category = task_category or (
                self.classify_task(message or "", is_voice=is_voice) if message else TASK_GENERAL_CHAT
            )
            cloud_order = ["groq", "nvidia", "openrouter", "gemini"]
            resolved_pid = None
            resolved_provider = None

            for pid in cloud_order:
                p = provider_manager.get_provider(pid)
                if self._is_provider_eligible(p):
                    resolved_pid = pid
                    resolved_provider = p
                    break

            if resolved_pid is None:
                fallback_p = provider_manager.get_provider(self.default_provider_id)
                reason = "CLOUD_ONLY: No cloud provider is currently available."
                return RouteDecision(
                    provider_id=self.default_provider_id,
                    model_name=self.registry.get_primary_model_for_provider(self.default_provider_id),
                    provider=fallback_p,
                    is_configured=False,
                    task_category=category,
                    routing_reason=reason,
                    failover_candidates=[],
                    execution_mode="cloud",
                    endpoint=get_provider_endpoint(self.default_provider_id),
                    why_this_choice=f"CLOUD_ONLY execution constraint active: {reason}",
                    fallback_used=False,
                    execution_constraint=EXECUTION_CLOUD_ONLY,
                )

            resolved_model = (
                requested_model.strip()
                if requested_model and requested_model.strip()
                else self.registry.get_primary_model_for_provider(resolved_pid)
            )
            failover_chain = [
                {"provider": pid, "model": self.registry.get_primary_model_for_provider(pid)}
                for pid in cloud_order
                if pid != resolved_pid
                and self._is_provider_eligible(provider_manager.get_provider(pid))
            ]
            reason = f"CLOUD_ONLY execution constraint: Routed to cloud provider '{resolved_pid}'."
            why = generate_why_this_choice(
                provider_id=resolved_pid,
                model_name=resolved_model,
                task_category=category,
                execution_mode="cloud",
                route_reason=reason,
            )
            logger.info(
                f"Model Router (V6.2): CLOUD_ONLY → provider={resolved_pid}, "
                f"model={resolved_model}, task={category}, failovers={len(failover_chain)}"
            )
            return RouteDecision(
                provider_id=resolved_pid,
                model_name=resolved_model,
                provider=resolved_provider,
                is_configured=True,
                task_category=category,
                routing_reason=reason,
                failover_candidates=failover_chain,
                execution_mode="cloud",
                endpoint=get_provider_endpoint(resolved_pid),
                why_this_choice=why,
                fallback_used=False,
                execution_constraint=EXECUTION_CLOUD_ONLY,
            )

        # =====================================================================
        # NORMAL ROUTING (no execution constraint)
        # =====================================================================
        category = task_category or (
            self.classify_task(message or "", is_voice=is_voice) if message else TASK_GENERAL_CHAT
        )
        require_vision = (category == TASK_VISION)

        # 1. If user explicitly requested a specific provider, honour it (subject to offline truth)
        explicit_provider = requested_provider.lower().strip() if requested_provider else None
        if explicit_provider:
            provider = provider_manager.get_provider(explicit_provider)
            target_pid = provider.provider_id
            target_mode = validate_execution_mode(target_pid)
            resolved_model = (
                requested_model.strip()
                if requested_model and requested_model.strip()
                else self.registry.get_primary_model_for_provider(target_pid)
            )

            # Rule 6: When offline, reject Groq/NVIDIA/Gemini/OpenRouter, clearly report LOCAL/OFFLINE, never silently fall back to cloud.
            if is_offline and target_mode == "cloud":
                reason = f"LOCAL/OFFLINE mode active: Cloud provider '{target_pid}' is rejected while offline."
                why = (
                    f"LOCAL/OFFLINE mode active: Cloud provider '{target_pid}' cannot be reached. "
                    f"Only local on-device providers (Ollama) are permitted."
                )
                logger.warning(f"Model Router: Rejected explicit cloud provider '{target_pid}' in offline mode.")
                return RouteDecision(
                    provider_id=target_pid,
                    model_name=resolved_model,
                    provider=provider,
                    is_configured=False,
                    task_category=category,
                    routing_reason=reason,
                    failover_candidates=[],
                    execution_mode="cloud",
                    endpoint=get_provider_endpoint(target_pid),
                    why_this_choice=why,
                    fallback_used=False
                )

            # Build failover from capability order, excluding the explicit provider
            order = self._capability_order(category)
            failover_chain = [
                {"provider": pid, "model": self.registry.get_primary_model_for_provider(pid)}
                for pid in order
                if pid != target_pid
                and self._is_provider_eligible(
                    provider_manager.get_provider(pid),
                    require_vision=require_vision
                )
            ]
            is_configured = provider.is_configured()
            reason = f"Explicit provider '{target_pid}' requested for task '{category}'."
            why = generate_why_this_choice(
                provider_id=target_pid,
                model_name=resolved_model,
                task_category=category,
                execution_mode=target_mode,
                route_reason=reason,
                is_offline=is_offline
            )
            logger.info(
                f"Model Router (V6.1): explicit override → provider={target_pid}, "
                f"model={resolved_model}, task={category}, failovers={len(failover_chain)}"
            )
            return RouteDecision(
                provider_id=target_pid,
                model_name=resolved_model,
                provider=provider,
                is_configured=is_configured,
                task_category=category,
                routing_reason=reason,
                failover_candidates=failover_chain,
                execution_mode=target_mode,
                endpoint=get_provider_endpoint(target_pid),
                why_this_choice=why,
                fallback_used=False
            )

        # 2. Capability-aware automatic provider selection
        order = self._capability_order(category)
        resolved_pid = None
        resolved_provider = None

        for pid in order:
            p = provider_manager.get_provider(pid)
            if self._is_provider_eligible(p, require_vision=require_vision):
                resolved_pid = pid
                resolved_provider = p
                break

        if resolved_pid is None:
            # All providers exhausted — in offline mode, fall back to ollama or mock-narad, NEVER cloud!
            if is_offline:
                resolved_pid = "ollama"
                resolved_provider = provider_manager.get_provider(resolved_pid)
                logger.warning(
                    f"Model Router: No eligible local provider for task '{category}' in offline mode. "
                    f"Defaulting to local daemon '{resolved_pid}'."
                )
            else:
                resolved_pid = self.default_provider_id
                resolved_provider = provider_manager.get_provider(resolved_pid)
                logger.warning(
                    f"Model Router (V6.1): No eligible provider for task '{category}'. "
                    f"Falling back to default '{resolved_pid}'."
                )

        resolved_model = (
            requested_model.strip()
            if requested_model and requested_model.strip()
            else (
                self.default_model
                if resolved_pid == self.default_provider_id and settings.NARAD_DEFAULT_MODEL
                else self.registry.get_primary_model_for_provider(resolved_pid)
            )
        )

        is_configured = resolved_provider.is_configured()
        if is_offline:
            reason = f"LOCAL/OFFLINE mode active: routed to verified local provider '{resolved_pid}'."
        else:
            reason = f"V6.1 capability-aware routing for '{category}' → '{resolved_pid}'."

        # 3. Build failover chain: remaining eligible providers in capability order
        failover_chain = [
            {"provider": pid, "model": self.registry.get_primary_model_for_provider(pid)}
            for pid in order
            if pid != resolved_pid
            and self._is_provider_eligible(
                provider_manager.get_provider(pid),
                require_vision=require_vision
            )
        ]

        resolved_mode = validate_execution_mode(resolved_pid)
        why = generate_why_this_choice(
            provider_id=resolved_pid,
            model_name=resolved_model,
            task_category=category,
            execution_mode=resolved_mode,
            route_reason=reason,
            is_offline=is_offline
        )

        logger.info(
            f"Model Router (V6.1): provider={resolved_pid}, model={resolved_model}, "
            f"task={category}, configured={is_configured}, "
            f"failovers={len(failover_chain)} {[f['provider'] for f in failover_chain]}"
        )

        return RouteDecision(
            provider_id=resolved_pid,
            model_name=resolved_model,
            provider=resolved_provider,
            is_configured=is_configured,
            task_category=category,
            routing_reason=reason,
            failover_candidates=failover_chain,
            execution_mode=resolved_mode,
            endpoint=get_provider_endpoint(resolved_pid),
            why_this_choice=why,
            fallback_used=False
        )

    def resolve_vision_route(
        self,
        requested_provider: Optional[str] = None,
        requested_model: Optional[str] = None
    ) -> RouteDecision:
        """
        Specialized router for visual/multimodal requests (TASK_VISION).
        Strictly restricts candidate selection to providers and models that support vision.
        Builds failover chains containing ONLY vision-capable providers.
        If no configured provider supports vision, returns is_configured=False with 'NO_VISION_PROVIDER_AVAILABLE'.
        """
        vision_models = [m for m in self.registry._models if m.enabled and m.vision_support]
        vision_provider_ids = list(dict.fromkeys([m.provider for m in vision_models]))

        from app.services.connectivity import connectivity_service
        from app.core.provider_truth import validate_execution_mode, get_provider_endpoint, generate_why_this_choice

        is_offline = not connectivity_service.is_online()

        # Check explicit provider request first
        if requested_provider:
            target_pid = requested_provider.lower().strip()
            prov = provider_manager.get_provider(target_pid)
            target_mode = validate_execution_mode(target_pid)

            if is_offline and target_mode == "cloud":
                return RouteDecision(
                    provider_id=target_pid,
                    model_name=requested_model or "none",
                    provider=prov,
                    is_configured=False,
                    task_category=TASK_VISION,
                    routing_reason=f"LOCAL/OFFLINE mode active: Cloud vision provider '{target_pid}' is rejected while offline.",
                    failover_candidates=[],
                    execution_mode="cloud",
                    endpoint=get_provider_endpoint(target_pid),
                    why_this_choice="Offline mode active: Cloud vision providers cannot be called.",
                    fallback_used=False
                )

            if prov and prov.supports_vision() and prov.is_configured():
                target_model = requested_model or self.registry.get_vision_model_for_provider(target_pid)
                failover_chain = []
                for alt_pid in vision_provider_ids:
                    if alt_pid != target_pid:
                        alt_p = provider_manager.get_provider(alt_pid)
                        if self._is_provider_eligible(alt_p, require_vision=True):
                            failover_chain.append({
                                "provider": alt_pid,
                                "model": self.registry.get_vision_model_for_provider(alt_pid)
                            })
                return RouteDecision(
                    provider_id=target_pid,
                    model_name=target_model,
                    provider=prov,
                    is_configured=True,
                    task_category=TASK_VISION,
                    routing_reason=f"Explicitly routed to vision provider '{target_pid}'.",
                    failover_candidates=failover_chain,
                    execution_mode=target_mode,
                    endpoint=get_provider_endpoint(target_pid),
                    why_this_choice=generate_why_this_choice(target_pid, target_model, TASK_VISION, target_mode),
                    fallback_used=False
                )

        # Look for the healthiest configured vision provider
        configured_vision_providers = []
        for pid in vision_provider_ids:
            p = provider_manager.get_provider(pid)
            if self._is_provider_eligible(p, require_vision=True):
                configured_vision_providers.append((pid, p))

        if not configured_vision_providers:
            default_p = provider_manager.get_provider("ollama" if is_offline else self.default_provider_id)
            reason = "LOCAL/OFFLINE: No local on-device provider supports vision input." if is_offline else "NO_VISION_PROVIDER_AVAILABLE: No configured provider supports vision input."
            return RouteDecision(
                provider_id="none",
                model_name="none",
                provider=default_p,
                is_configured=False,
                task_category=TASK_VISION,
                routing_reason=reason,
                failover_candidates=[],
                execution_mode="local" if is_offline else "cloud",
                endpoint=get_provider_endpoint("ollama" if is_offline else self.default_provider_id),
                why_this_choice=reason,
                fallback_used=False
            )

        # Select first non-cooldown configured vision provider
        selected_pid, selected_prov = configured_vision_providers[0]
        selected_model = self.registry.get_vision_model_for_provider(selected_pid)
        selected_mode = validate_execution_mode(selected_pid)

        failovers = []
        for pid, p in configured_vision_providers:
            if pid != selected_pid:
                failovers.append({
                    "provider": pid,
                    "model": self.registry.get_vision_model_for_provider(pid)
                })

        return RouteDecision(
            provider_id=selected_pid,
            model_name=selected_model,
            provider=selected_prov,
            is_configured=True,
            task_category=TASK_VISION,
            routing_reason=f"Routed for multimodal vision via '{selected_pid}' ({selected_model}).",
            failover_candidates=failovers,
            execution_mode=selected_mode,
            endpoint=get_provider_endpoint(selected_pid),
            why_this_choice=generate_why_this_choice(selected_pid, selected_model, TASK_VISION, selected_mode),
            fallback_used=False
        )


    def get_detected_providers(self) -> List[Dict[str, Any]]:
        """
        Returns list of all providers with their V6.1 configuration and health status.
        Includes execution_mode and canonical endpoint from provider truth.
        """
        result = []
        for pid in ["groq", "nvidia", "gemini", "openrouter"]:
            p = provider_manager.get_provider(pid)
            if not p:
                continue
            health = p.get_health_status()
            result.append({
                "id": pid,
                "display_name": p.display_name,
                "execution_mode": p.execution_mode,
                "endpoint": p.endpoint,
                "is_configured": p.is_configured(),
                "health_state": health["health_state"],
                "in_cooldown": health["in_cooldown"],
                "cooldown_remaining_sec": health["cooldown_remaining_sec"],
                "latency_ms": health["latency_ms"],
                "failover_count": health["failover_count"],
                "supports_vision": p.supports_vision(),
                "supports_tools": p.supports_tools(),
                "models": p.get_available_models(),
            })
        return result

    def get_router_status(self) -> Dict[str, Any]:
        """
        V6.1 Telemetry snapshot of the router's current configuration and all providers.
        Includes:
          - active_provider, active_model, route_reason, execution_mode, endpoint, why_this_choice
          - V6.1 health_state for every provider
          - routing_orders: shows the preferred chain per task category
          - failover_count per provider
        """
        from app.services.connectivity import connectivity_service
        active_route = self.resolve_route()
        providers = provider_manager.list_providers()
        configured_count = sum(1 for p in providers if p.get("is_configured"))
        detected = self.get_detected_providers()

        # V6.1: enrich each provider entry with health_state, execution_mode, and endpoint
        for p_entry in providers:
            raw = provider_manager.get_provider(p_entry["id"])
            if raw:
                h = raw.get_health_status()
                p_entry["health_state"] = h.get("health_state", "UNKNOWN")
                p_entry["failover_count"] = h.get("failover_count", 0)
                p_entry["execution_mode"] = raw.execution_mode
                p_entry["endpoint"] = raw.endpoint

        return {
            # V6.1 identifiers
            "router_version": "V6.1",
            "router_status": "online" if connectivity_service.is_online() else "offline",
            "is_online": connectivity_service.is_online(),
            "operating_mode": connectivity_service.get_operating_mode(),
            # Active route telemetry
            "active_provider": active_route.provider_id,
            "active_model": active_route.model_name,
            "execution_mode": active_route.execution_mode,
            "execution": active_route.execution,
            "endpoint": active_route.endpoint,
            "route_reason": active_route.routing_reason,
            "why_this_choice": active_route.why_this_choice,
            "display_label": active_route.display_label,
            "task_category": active_route.task_category,
            "is_configured": active_route.is_configured,
            "fallback_ready": len(active_route.failover_candidates) > 0,
            "failover_candidates": active_route.failover_candidates,
            # Provider mesh
            "default_provider": self.default_provider_id,
            "default_model": self.default_model,
            "configured_providers_count": configured_count,
            "detected_providers": detected,
            "available_providers": providers,
            # V6.1 routing order reference (shows capability-aware chains)
            "routing_orders": {
                "general_fast": self._capability_order(TASK_GENERAL_CHAT),
                "reasoning": self._capability_order(TASK_REASONING),
                "coding": self._capability_order(TASK_CODING),
                "vision": self._capability_order(TASK_VISION),
            },
        }

# Global singleton Model Router instance
model_router = ModelRouter()

