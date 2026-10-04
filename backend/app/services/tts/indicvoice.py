"""
IndicVoice Local TTS Provider for NARAD Vāṇī.
Decoder-Only Neural TTS with native G2P frontend for Indian Languages (Kokoro-82M architecture).
"""
import io
import os
import sys
import time
import logging
import asyncio
from pathlib import Path
from typing import Optional

from app.services.tts.base import BaseTTSProvider, TTSStatus, TTSResult
from app.core.config import settings

logger = logging.getLogger(__name__)

INDIC_REPO_DIR = Path("/Users/pratyushjemini/Pagalpan/Trimurti/indic-voice")
LOCAL_WEIGHTS_PATH = INDIC_REPO_DIR / "indicvoice-v1_0.pth"
CONFIG_PATH = INDIC_REPO_DIR / "config.json"
VOICES_DIR = INDIC_REPO_DIR / "voices"


class IndicVoiceTTSProvider(BaseTTSProvider):
    """
    Local implementation of IndicVoice TTS for Hindi and Indic languages.
    Keeps model loaded in memory for fast synthesis.
    """

    def __init__(self, target_device: str = "cpu"):
        self.target_device = target_device
        self._model = None
        self._pipeline = None
        self._voice_tensor = None
        self._load_error: Optional[str] = None
        self._init_time: Optional[float] = None
        self._last_gen_time: Optional[float] = None
        self._active_device: str = "cpu"
        self._configure_espeak()

    @property
    def provider_id(self) -> str:
        return "indicvoice"

    def _configure_espeak(self) -> None:
        """Configure system espeak-ng paths from Homebrew if present."""
        brew_espeak_data = "/opt/homebrew/share/espeak-ng-data"
        brew_espeak_bin = "/opt/homebrew/bin/espeak-ng"

        if os.path.exists(brew_espeak_data):
            os.environ["ESPEAK_DATA_PATH"] = brew_espeak_data
        if os.path.exists(brew_espeak_bin):
            os.environ["PHONEMIZER_ESPEAK_PATH"] = brew_espeak_bin
            if "/opt/homebrew/bin" not in os.environ.get("PATH", ""):
                os.environ["PATH"] = f"/opt/homebrew/bin:{os.environ.get('PATH', '')}"

    def is_available(self) -> bool:
        """Returns True if indicvoice module is importable and weights exist."""
        if settings.is_cloud:
            self._load_error = "IndicVoice unavailable in CLOUD mode (Mac node offline)."
            return False
        if getattr(settings, "NARAD_RUNTIME_MODE", "hybrid").lower() == "cloud":
            self._load_error = "IndicVoice unavailable in CLOUD mode (Mac node offline)."
            return False
        try:
            import indicvoice
            if not LOCAL_WEIGHTS_PATH.exists() or LOCAL_WEIGHTS_PATH.stat().st_size < 10_000_000:
                self._load_error = "IndicVoice weights not found or still downloading."
                return False
            self._load_error = None
            return True
        except ImportError as e:
            self._load_error = f"indicvoice package not available: {str(e)}"
            return False

    def get_status(self) -> TTSStatus:
        available = self.is_available()
        return TTSStatus(
            provider="indicvoice",
            installed=available,
            model_loaded=self._pipeline is not None,
            ready=(self._pipeline is not None),
            mode="local",
            device=self._active_device.upper(),
            supported_languages=["hi"],
            initialization_time=self._init_time,
            generation_time=self._last_gen_time,
            error=self._load_error,
            active_fallback=(not available or self._pipeline is None),
            fallback_provider="chatterbox"
        )

    def _ensure_model_loaded(self):
        if self._pipeline is not None:
            return self._pipeline

        if not self.is_available():
            raise RuntimeError(f"IndicVoice cannot initialize: {self._load_error}")

        t0 = time.time()
        try:
            import torch
            from indicvoice import IndicModel, IndicPipeline

            # Patch torch.load for weights_only if needed for Kokoro custom dicts
            _orig_load = torch.load
            def _unpickler_load(*args, **kwargs):
                kwargs["weights_only"] = False
                return _orig_load(*args, **kwargs)

            torch.load = _unpickler_load
            try:
                logger.info("Initializing IndicModel with local weights at %s", LOCAL_WEIGHTS_PATH)
                self._model = IndicModel(
                    config=str(CONFIG_PATH),
                    model=str(LOCAL_WEIGHTS_PATH)
                )
                self._pipeline = IndicPipeline(lang_code="h", model=self._model, repo_id="Bindkushal/IndicVoice-82M")

                # Load default female Hindi voice
                default_voice = VOICES_DIR / "hf_alpha.pt"
                if default_voice.exists() and default_voice.stat().st_size > 1000:
                    self._voice_tensor = torch.load(str(default_voice), weights_only=True)
                else:
                    self._voice_tensor = "hf_alpha"
            finally:
                torch.load = _orig_load

            self._active_device = "CPU"
            self._init_time = round(time.time() - t0, 3)
            logger.info("IndicVoice loaded in %.3fs on %s", self._init_time, self._active_device)
            return self._pipeline
        except Exception as e:
            self._load_error = f"IndicVoice initialization failed: {str(e)}"
            logger.exception("Failed to load IndicVoice:")
            raise RuntimeError(self._load_error) from e

    async def synthesize(self, text: str, language: str = "hi") -> TTSResult:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Speech synthesis text cannot be empty.")

        def _generate_sync():
            pipeline = self._ensure_model_loaded()
            import soundfile as sf
            import numpy as np

            t0 = time.time()
            audio_segments = []
            
            for gs, ps, audio in pipeline(clean_text, voice=self._voice_tensor):
                if audio is not None:
                    audio_segments.append(audio)

            if not audio_segments:
                raise RuntimeError("IndicVoice generated empty audio output.")

            combined_audio = np.concatenate(audio_segments)
            gen_time = round(time.time() - t0, 3)
            self._last_gen_time = gen_time

            buffer = io.BytesIO()
            sf.write(buffer, combined_audio, 24000, format="WAV")
            buffer.seek(0)
            audio_bytes = buffer.read()

            duration = round(len(combined_audio) / 24000.0, 2)

            return TTSResult(
                audio_bytes=audio_bytes,
                format="wav",
                sample_rate=24000,
                duration_seconds=duration,
                generation_time=gen_time,
                provider="indicvoice",
                language="hi",
                device=self._active_device.upper()
            )

        return await asyncio.to_thread(_generate_sync)
