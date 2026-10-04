"""
TTS Provider Package for NARAD Vāṇī.
"""
from app.services.tts.base import BaseTTSProvider, TTSStatus, TTSResult
from app.services.tts.chatterbox import ChatterboxTTSProvider
from app.services.tts.manager import tts_manager, DIAGNOSTIC_SAMPLES

__all__ = [
    "BaseTTSProvider",
    "TTSStatus",
    "TTSResult",
    "ChatterboxTTSProvider",
    "tts_manager",
    "DIAGNOSTIC_SAMPLES",
]
