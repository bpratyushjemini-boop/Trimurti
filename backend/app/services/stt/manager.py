"""
STT Manager for NARAD Vāṇī.
Coordinates Speech-to-Text providers and unified status telemetry.
"""
import logging
from typing import Dict, Optional

from app.services.stt.base import BaseSTTProvider, STTStatus, STTResult
from app.services.stt.whisper import LocalWhisperSTTProvider

logger = logging.getLogger(__name__)


class STTManager:
    """
    Singleton orchestration manager for Speech-to-Text.
    """

    def __init__(self):
        self._providers: Dict[str, BaseSTTProvider] = {}
        self._active_engine: str = "local_whisper"
        self._init_providers()

    def _init_providers(self):
        self._providers["local_whisper"] = LocalWhisperSTTProvider(model_size="tiny", device="cpu", compute_type="int8")

    @property
    def active_provider(self) -> BaseSTTProvider:
        return self._providers.get(self._active_engine, self._providers["local_whisper"])

    def get_status(self) -> STTStatus:
        return self.active_provider.get_status()

    async def transcribe(self, audio_bytes: bytes, file_format: str = "wav", language: str = "auto") -> STTResult:
        return await self.active_provider.transcribe(audio_bytes=audio_bytes, file_format=file_format, language=language)


stt_manager = STTManager()
