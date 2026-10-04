"""
Chatterbox Multilingual Local TTS Provider for NARAD Vāṇī.
Integrates Resemble AI's open-source Chatterbox Multilingual model.
Supports English, Hindi, and Hinglish with zero cloud API keys or external fees.
"""
import io
import sys
import time
import logging
import asyncio
import re
from typing import Optional

from app.services.tts.base import BaseTTSProvider, TTSStatus, TTSResult
from app.core.config import settings

logger = logging.getLogger(__name__)

# Minimum Python runtime required by chatterbox-tts
MIN_PYTHON_VERSION = (3, 10)


class ChatterboxTTSProvider(BaseTTSProvider):
    """
    Local implementation of Chatterbox Multilingual TTS.
    Compatible with Apple Silicon (MPS), CUDA, and CPU.
    Keeps model loaded in memory for fast continuous synthesis.
    """

    def __init__(self, target_device: str = "auto"):
        self.target_device = target_device
        self._model = None
        self._load_error: Optional[str] = None
        self._init_time: Optional[float] = None
        self._last_gen_time: Optional[float] = None
        self._active_device: str = "cpu"
        self._check_environment()

    @property
    def provider_id(self) -> str:
        return "chatterbox"

    def _check_environment(self) -> None:
        """Inspect environment for Python version and dependency installation."""
        is_cloud = (
            settings.is_cloud
            or getattr(settings, "NARAD_RUNTIME_MODE", "hybrid").lower() == "cloud"
        )
        if is_cloud:
            self._load_error = "Chatterbox unavailable in CLOUD mode (Mac node offline)."
            return

        if sys.version_info < MIN_PYTHON_VERSION:
            self._load_error = (
                f"Chatterbox requires Python >= 3.10 (Current: {sys.version.split()[0]}). "
                "Please run NARAD with Python 3.10+ (recommended: Python 3.12)."
            )
            return

        try:
            import torch
            import torchaudio
        except ImportError:
            self._load_error = "PyTorch or Torchaudio not installed."
            return

        try:
            import chatterbox
        except ImportError:
            self._load_error = "chatterbox-tts package is not installed."
            return

        self._load_error = None

    def _resolve_device(self) -> str:
        """Detect best available device: mps (Apple Silicon), cuda, or cpu."""
        is_cloud = (
            settings.is_cloud
            or getattr(settings, "NARAD_RUNTIME_MODE", "hybrid").lower() == "cloud"
        )
        if is_cloud:
            return "none"

        if self.target_device and self.target_device != "auto":
            return self.target_device

        try:
            import torch
            if torch.backends.mps.is_available() and torch.backends.mps.is_built():
                return "mps"
            elif torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"

    def is_available(self) -> bool:
        """Returns True only if environment dependencies are installed."""
        self._check_environment()
        return self._load_error is None

    def get_status(self) -> TTSStatus:
        """Detailed status for telemetry, health checks, and fallback triggers."""
        self._check_environment()
        installed = (self._load_error is None or "not installed" not in self._load_error) and (sys.version_info >= MIN_PYTHON_VERSION)
        resolved_device = self._active_device if self._model is not None else self._resolve_device()

        return TTSStatus(
            provider="chatterbox",
            installed=installed,
            model_loaded=self._model is not None,
            ready=(self._model is not None) or (self.is_available()),
            mode="local",
            device=resolved_device.upper(),
            supported_languages=["en", "hi", "hinglish"],
            initialization_time=self._init_time,
            generation_time=self._last_gen_time,
            error=self._load_error,
            active_fallback=(not self.is_available()),
            fallback_provider="browser_speech_synthesis"
        )

    def _detect_language(self, text: str, requested_lang: str = "auto") -> str:
        """
        Detects whether text is Hindi, English, or Hinglish.
        Maps to valid Chatterbox language code ('en' or 'hi').
        """
        if requested_lang in ("hi", "hindi"):
            return "hi"
        if requested_lang in ("en", "english"):
            return "en"

        # Check for Devanagari script characters (U+0900 to U+097F)
        if re.search(r"[\u0900-\u097f]", text):
            return "hi"

        # Common Romanized Hindi / Hinglish tokens
        hinglish_markers = {
            "namaste", "aap", "hum", "hain", "kya", "kar", "rahe", "kaise",
            "shukriya", "dhanyavaad", "theek", "hoon", "nahi", "accha", "kripya",
            "kholo", "chalao", "bhai", "karo", "aaj", "kahan", "kaun"
        }
        words = set(re.findall(r"\b\w+\b", text.lower()))
        if words.intersection(hinglish_markers):
            return "hi"

        return "en"

    def _ensure_model_loaded(self):
        """Load ChatterboxMultilingualTTS once and keep in memory."""
        if self._model is not None:
            return self._model

        if not self.is_available():
            raise RuntimeError(f"Chatterbox Multilingual cannot initialize: {self._load_error}")

        t0 = time.time()
        try:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            device = self._resolve_device()
            logger.info("Initializing ChatterboxMultilingualTTS on device: %s", device)
            
            # Note: Chatterbox Multilingual supports CPU and MPS on Mac.
            # If MPS encounters unsupported ops during generation, fallback to CPU.
            from pathlib import Path
            snapshot_dirs = list(Path.home().glob(".cache/huggingface/hub/models--ResembleAI--chatterbox/snapshots/*"))
            local_ckpt = snapshot_dirs[0] if snapshot_dirs else None

            try:
                if local_ckpt and local_ckpt.exists():
                    logger.info("Loading ChatterboxMultilingualTTS from local snapshot: %s", local_ckpt)
                    self._model = ChatterboxMultilingualTTS.from_local(local_ckpt, device=device)
                else:
                    self._model = ChatterboxMultilingualTTS.from_pretrained(device=device)
                self._active_device = device
            except Exception as mps_err:
                if device != "cpu":
                    logger.warning("MPS init failed (%s), falling back to CPU", mps_err)
                    if local_ckpt and local_ckpt.exists():
                        self._model = ChatterboxMultilingualTTS.from_local(local_ckpt, device="cpu")
                    else:
                        self._model = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
                    self._active_device = "cpu"
                else:
                    raise mps_err

            self._init_time = round(time.time() - t0, 3)
            logger.info("Chatterbox loaded in %.3fs on %s", self._init_time, self._active_device)
            return self._model
        except Exception as e:
            self._load_error = f"Model initialization failed: {str(e)}"
            logger.exception("Failed to load ChatterboxMultilingualTTS:")
            raise RuntimeError(self._load_error) from e

    async def synthesize(self, text: str, language: str = "auto") -> TTSResult:
        """
        Synthesize speech using Chatterbox Multilingual.
        Offloads tensor execution to thread pool. Never returns mock/fake audio.
        """
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Speech synthesis text cannot be empty.")

        resolved_lang = self._detect_language(clean_text, requested_lang=language)

        def _generate_sync():
            model = self._ensure_model_loaded()
            import torchaudio as ta

            t0 = time.time()
            wav = model.generate(clean_text, language_id=resolved_lang)
            gen_time = round(time.time() - t0, 3)
            self._last_gen_time = gen_time

            # In-memory WAV buffer
            buffer = io.BytesIO()
            # Ensure tensor is on CPU before saving
            wav_cpu = wav.cpu() if hasattr(wav, "cpu") else wav
            ta.save(buffer, wav_cpu, model.sr, format="wav")
            buffer.seek(0)
            audio_bytes = buffer.read()

            duration = None
            if hasattr(wav, "shape") and len(wav.shape) > 1:
                duration = round(wav.shape[-1] / float(model.sr), 2)

            return TTSResult(
                audio_bytes=audio_bytes,
                format="wav",
                sample_rate=getattr(model, "sr", 24000),
                duration_seconds=duration,
                generation_time=gen_time,
                provider="chatterbox",
                language=resolved_lang,
                device=self._active_device.upper()
            )

        return await asyncio.to_thread(_generate_sync)
