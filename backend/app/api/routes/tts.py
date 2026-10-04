"""
Vāṇī TTS API Router for NARAD.
Exposes status, health checks, audio synthesis, and diagnostic test endpoints.
"""
import io
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.tts.base import TTSStatus
from app.services.tts.manager import tts_manager, DIAGNOSTIC_SAMPLES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts", tags=["TTS"])


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text string to synthesize into speech")
    language: Optional[str] = Field(default="auto", description="'en', 'hi', 'hinglish', or 'auto'")


class DiagnosticTestRequest(BaseModel):
    sample_key: str = Field(default="english", description="'english', 'hindi', or 'hinglish'")


@router.get("/status", response_model=TTSStatus, status_code=status.HTTP_200_OK)
def get_tts_status():
    """
    Returns real-time health, installation, and hardware status of the active TTS engine.
    Used by the Vāṇī HUD for telemetry and fallback indicators.
    """
    return tts_manager.get_status()


@router.get("/samples")
def list_diagnostic_samples():
    """Returns the pre-defined English, Hindi, and Hinglish diagnostic sample prompts."""
    return DIAGNOSTIC_SAMPLES


@router.get("/engines")
def get_tts_engines():
    """Returns granular per-engine status for Chatterbox and IndicVoice."""
    return tts_manager.get_all_statuses()


@router.post("/synthesize")
async def synthesize_speech(payload: SynthesizeRequest):
    """
    Synthesizes input text to WAV audio using local Chatterbox Multilingual engine.
    Fails clearly with HTTP 503 if dependencies/models are missing, triggering browser fallback.
    """
    status_info = tts_manager.get_status()
    if not status_info.ready and not status_info.installed:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "Chatterbox TTS is not ready or dependencies are missing.",
                "reason": status_info.error,
                "provider": status_info.provider,
                "fallback_recommended": True
            }
        )

    try:
        result = await tts_manager.synthesize(text=payload.text, language=payload.language or "auto")
        return StreamingResponse(
            io.BytesIO(result.audio_bytes),
            media_type="audio/wav",
            headers={
                "Content-Disposition": "inline; filename=vaani_speech.wav",
                "X-TTS-Provider": result.provider,
                "X-TTS-Language": result.language,
                "X-TTS-Sample-Rate": str(result.sample_rate),
            }
        )
    except Exception as exc:
        logger.exception("Synthesis failed in /api/tts/synthesize:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"TTS synthesis failed: {str(exc)}",
                "fallback_recommended": True
            }
        ) from exc


@router.post("/test")
async def test_speech_diagnostic(payload: DiagnosticTestRequest):
    """
    Executes one of the 3 required diagnostic voice tests (English, Hindi, or Hinglish).
    Streams back audio/wav or returns structured error if dependencies/model are unavailable.
    """
    status_info = tts_manager.get_status()
    if not status_info.ready and not status_info.installed:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": f"Cannot run diagnostic '{payload.sample_key}': Chatterbox is not initialized.",
                "reason": status_info.error,
                "fallback_recommended": True
            }
        )

    try:
        result = await tts_manager.run_diagnostic_test(sample_key=payload.sample_key)
        sample_info = DIAGNOSTIC_SAMPLES.get(payload.sample_key.lower(), {})
        return StreamingResponse(
            io.BytesIO(result.audio_bytes),
            media_type="audio/wav",
            headers={
                "Content-Disposition": f"inline; filename=vaani_test_{payload.sample_key}.wav",
                "X-TTS-Provider": result.provider,
                "X-TTS-Language": result.language,
                "X-TTS-Sample-Key": payload.sample_key,
            }
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve)) from ve
    except Exception as exc:
        logger.exception("Diagnostic test failed in /api/tts/test:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Diagnostic test execution failed: {str(exc)}"
        ) from exc
