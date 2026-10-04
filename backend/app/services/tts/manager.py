"""
TTS Manager and Dynamic Router for NARAD Vāṇī.
Coordinates Chatterbox Multilingual, IndicVoice, and fallback routing.
Language Policy:
  - English  -> Chatterbox
  - Hindi    -> IndicVoice (with Chatterbox fallback)
  - Hinglish -> Chatterbox first (with IndicVoice fallback)
Maintains models in memory as singletons (never reloads per request).
"""
import re
import logging
from typing import Dict, Optional, Any, List

from app.core.config import settings
from app.services.tts.base import BaseTTSProvider, TTSStatus, TTSResult
from app.services.tts.chatterbox import ChatterboxTTSProvider
from app.services.tts.indicvoice import IndicVoiceTTSProvider

logger = logging.getLogger(__name__)

# Standard Diagnostic Prompts for Vāṇī Validation
DIAGNOSTIC_SAMPLES = {
    "english": {
        "text": "Hello, I am NARAD. How can I help you?",
        "lang": "en",
        "description": "Standard English greeting"
    },
    "hindi": {
        "text": "नमस्ते, मैं नारद हूँ। मैं आपकी कैसे सहायता कर सकता हूँ?",
        "lang": "hi",
        "description": "Pure Hindi greeting in Devanagari script"
    },
    "hinglish": {
        "text": "Namaste, main NARAD hoon. Aaj hum kya kar rahe hain?",
        "lang": "hi",
        "description": "Colloquial Romanized Hindi / Hinglish"
    },
    "voice_command": {
        "text": "Opening Google Chrome for you now, Operator.",
        "lang": "en",
        "description": "Voice command confirmation (Chrome kholo)"
    },
    "voice_tool_command": {
        "text": "Launching Apple Music and cueing Back in Black by AC/DC.",
        "lang": "en",
        "description": "Voice tool action confirmation (Apple Music chalao)"
    }
}


class TTSManager:
    """
    Intelligent Router for Vāṇī Speech Synthesis.
    Selects the optimal engine based on language and availability.
    """

    def __init__(self):
        self._providers: Dict[str, BaseTTSProvider] = {}
        self._device: str = getattr(settings, "TTS_DEVICE", "auto")
        self._policy: str = getattr(settings, "TTS_ROUTER_POLICY", "auto")  # 'auto', 'chatterbox_only', 'indicvoice_only'
        self._init_providers()

    def _init_providers(self):
        """Register all local TTS providers."""
        self._providers["chatterbox"] = ChatterboxTTSProvider(target_device=self._device)
        self._providers["indicvoice"] = IndicVoiceTTSProvider(target_device="cpu")

    def get_provider(self, name: str) -> Optional[BaseTTSProvider]:
        return self._providers.get(name.lower())

    def detect_language(self, text: str) -> str:
        """
        Classifies text as 'hi' (Devanagari Hindi), 'hinglish', or 'en'.
        """
        # Devanagari script: U+0900 to U+097F
        if re.search(r"[\u0900-\u097f]", text):
            return "hi"

        hinglish_markers = {
            "namaste", "aap", "hum", "hain", "hai", "kya", "kar", "rahe", "kaise",
            "shukriya", "dhanyavaad", "theek", "hoon", "nahi", "accha", "kripya",
            "kholo", "chalao", "bhai", "karo", "aaj", "kahan", "kaun", "mera", "meri",
            "mere", "batao", "sunao", "dekho", "kuch", "sab", "hoga", "hogi", "kab",
            "kyun", "kaisa", "zara", "thoda", "bahut", "yaar", "dost"
        }
        words = set(re.findall(r"\b\w+\b", text.lower()))
        if words.intersection(hinglish_markers):
            return "hinglish"

        return "en"

    def select_engine_for_language(self, detected_lang: str) -> str:
        """
        Engine Selection Layer:
        Evaluates language, voice quality, latency, availability, and CPU capability.
        - Devanagari Hindi ('hi'): IndicVoice has authentic native phonetics. Fallback to Chatterbox.
        - Hinglish ('hinglish'): Chatterbox multilingual excels at code-switched phonetics. Fallback to IndicVoice.
        - English ('en'): Chatterbox native English model. Fallback to IndicVoice.
        """
        if self._policy == "chatterbox_only":
            return "chatterbox"
        if self._policy == "indicvoice_only":
            return "indicvoice"

        chatterbox = self._providers.get("chatterbox")
        indicvoice = self._providers.get("indicvoice")

        if detected_lang == "hi":
            if indicvoice and indicvoice.is_available():
                return "indicvoice"
            if chatterbox and chatterbox.is_available():
                return "chatterbox"
            return "indicvoice"
        elif detected_lang == "hinglish":
            if chatterbox and chatterbox.is_available():
                return "chatterbox"
            if indicvoice and indicvoice.is_available():
                return "indicvoice"
            return "chatterbox"
        else:
            if chatterbox and chatterbox.is_available():
                return "chatterbox"
            if indicvoice and indicvoice.is_available():
                return "indicvoice"
            return "chatterbox"

    def get_status(self) -> TTSStatus:
        """Unified status telemetry across both engines."""
        chatterbox_status = self._providers["chatterbox"].get_status()
        indicvoice_status = self._providers["indicvoice"].get_status()

        # Primary engine is chatterbox or indicvoice
        active_engine = "chatterbox" if chatterbox_status.ready else ("indicvoice" if indicvoice_status.ready else "browser_speech_synthesis")
        primary_status = chatterbox_status if active_engine == "chatterbox" else indicvoice_status

        return TTSStatus(
            provider=active_engine,
            installed=chatterbox_status.installed or indicvoice_status.installed,
            model_loaded=chatterbox_status.model_loaded or indicvoice_status.model_loaded,
            ready=chatterbox_status.ready or indicvoice_status.ready,
            mode="local",
            device=chatterbox_status.device,
            supported_languages=["en", "hi", "hinglish"],
            initialization_time=chatterbox_status.initialization_time,
            generation_time=chatterbox_status.generation_time or indicvoice_status.generation_time,
            error=chatterbox_status.error if not chatterbox_status.ready else None,
            active_fallback=not (chatterbox_status.ready or indicvoice_status.ready),
            fallback_provider="browser_speech_synthesis",
            available_engines=["chatterbox", "indicvoice"],
            engines={
                "chatterbox": chatterbox_status.model_dump(),
                "indicvoice": indicvoice_status.model_dump(),
            }
        )

    def get_all_statuses(self) -> Dict[str, Any]:
        return {
            name: provider.get_status().model_dump()
            for name, provider in self._providers.items()
        }


    async def synthesize(self, text: str, language: str = "auto") -> TTSResult:
        """
        Synthesize speech through the dynamic router.
        Auto-routes based on detected language and falls back cleanly.
        """
        detected = self.detect_language(text) if language == "auto" else language
        primary_engine_name = self.select_engine_for_language(detected)
        
        provider = self.get_provider(primary_engine_name)
        
        # Attempt primary engine
        if provider and provider.is_available():
            try:
                return await provider.synthesize(text=text, language=detected)
            except Exception as e:
                logger.warning("Primary engine '%s' failed: %s. Attempting fallback.", primary_engine_name, e)

        # Fallback to secondary engine
        secondary_engine_name = "chatterbox" if primary_engine_name == "indicvoice" else "indicvoice"
        fallback_provider = self.get_provider(secondary_engine_name)
        if fallback_provider and fallback_provider.is_available():
            try:
                return await fallback_provider.synthesize(text=text, language=detected)
            except Exception as e:
                logger.warning("Fallback engine '%s' also failed: %s", secondary_engine_name, e)

        raise RuntimeError(f"All local TTS engines failed for text (detected language: {detected})")

    async def run_diagnostic_test(self, sample_key: str = "english") -> TTSResult:
        normalized_key = sample_key.lower().strip()
        if normalized_key not in DIAGNOSTIC_SAMPLES:
            valid = list(DIAGNOSTIC_SAMPLES.keys())
            raise ValueError(f"Invalid diagnostic key '{sample_key}'. Choose from: {valid}")

        sample = DIAGNOSTIC_SAMPLES[normalized_key]
        return await self.synthesize(text=sample["text"], language=sample["lang"])


tts_manager = TTSManager()
