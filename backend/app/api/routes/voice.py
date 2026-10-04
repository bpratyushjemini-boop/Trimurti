"""
Two-Way Voice Pipeline Router for NARAD Vāṇī.
MIC Audio -> Local STT (Whisper) -> NARAD Core / Router / Tools -> Local TTS (Chatterbox/IndicVoice) -> Audio Playback.
Integrates directly into existing NARAD intelligence and tool paths without creating duplicate intelligence.
"""
import base64
import time
import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.narad import narad_core
from app.services.smriti import smriti_service
from app.services.stt.manager import stt_manager
from app.services.tts.manager import tts_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["Voice"])


@router.get("/status", status_code=status.HTTP_200_OK)
async def voice_status_endpoint():
    """
    Exposes unified Vāṇī Voice Stack telemetry:
    - STT status (Local Whisper)
    - TTS status (Chatterbox / IndicVoice)
    - State: VOICE READY, VOICE OFF, MIC UNAVAILABLE, TTS READY, TTS FAILED
    - Supported languages: Hindi, English, Hinglish
    """
    stt_status = stt_manager.get_status()
    tts_status = tts_manager.get_status()

    stt_ready = getattr(stt_status, "is_available", False)
    tts_ready = getattr(tts_status, "is_available", False)

    # Determine overall voice state
    if stt_ready and tts_ready:
        voice_state = "VOICE READY"
    elif stt_ready and not tts_ready:
        voice_state = "TTS FAILED"
    elif not stt_ready and tts_ready:
        voice_state = "MIC UNAVAILABLE"
    else:
        voice_state = "VOICE OFF"

    return {
        "voice_state": voice_state,
        "stt": {
            "engine": getattr(stt_status, "engine", "local_whisper"),
            "status": "READY" if stt_ready else "NOT_CONFIGURED",
            "device": getattr(stt_status, "device", "cpu"),
            "model_size": getattr(stt_status, "model_size", "tiny"),
        },
        "tts": {
            "engine": getattr(tts_status, "engine", "chatterbox"),
            "status": "TTS READY" if tts_ready else "TTS FAILED",
            "device": getattr(tts_status, "device", "cpu"),
            "active_router_policy": getattr(tts_manager, "_policy", "auto"),
        },
        "languages": ["Hindi", "English", "Hinglish"],
        "sample_prompts": [
            "Namaste Pratyush, aaj NARAD ka system health check complete hai.",
            "Hello Pratyush, all systems are operational.",
            "नमस्ते, मैं आपकी क्या सहायता कर सकता हूँ?"
        ]
    }


@router.post("/interact", status_code=status.HTTP_200_OK)
async def voice_interact_endpoint(
    audio_file: UploadFile = File(...),
    chat_id: Optional[str] = Form(default=None),
    provider: Optional[str] = Form(default=None),
    model: Optional[str] = Form(default=None),
    db: Session = Depends(get_db)
):
    """
    Two-way voice interaction:
    1. Transcribes voice input via Local Whisper STT.
    2. Enters existing NARAD Core / Tool / Router pipeline (same as typed input).
    3. Synthesizes assistant response via TTS Router (Chatterbox / IndicVoice).
    4. Returns text, audio (base64), and real latency telemetry.
    """
    total_start = time.time()

    # Step 1: Speech-to-Text
    audio_bytes = await audio_file.read()
    if not audio_bytes or len(audio_bytes) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio recording is empty or unreadable."
        )

    filename = audio_file.filename or "recording.wav"
    ext = filename.split(".")[-1] if "." in filename else "wav"

    try:
        stt_result = await stt_manager.transcribe(audio_bytes=audio_bytes, file_format=ext, language="auto")
    except Exception as exc:
        logger.exception("STT failed in voice interaction:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Speech transcription failed: {str(exc)}"
        ) from exc

    user_text = stt_result.text.strip()
    if not user_text:
        return {
            "transcription": "",
            "detected_language": stt_result.language,
            "response": "I didn't catch that. Please speak again.",
            "audio_base64": None,
            "telemetry": {
                "stt_engine": stt_result.engine,
                "stt_latency": stt_result.latency_seconds,
                "llm_latency": 0.0,
                "tts_latency": 0.0,
                "total_latency": round(time.time() - total_start, 3),
                "device": "CPU"
            }
        }

    # Step 2: Session & Smriti Memory
    session = smriti_service.get_or_create_session(
        session_id=chat_id,
        initial_title=user_text,
        db=db
    )
    user_msg = smriti_service.add_user_message(
        session_id=session.id,
        content=user_text,
        db=db
    )
    history_payload = smriti_service.get_conversation_history(
        session_id=session.id,
        db=db
    )

    # Step 3: NARAD Core Processing (Fast-path, Tools, LLM)
    llm_start = time.time()
    try:
        core_result = await narad_core.process_message(
            message=user_text,
            history=history_payload,
            session_id=session.id,
            requested_provider=provider,
            requested_model=model,
            is_voice=True
        )
        llm_latency = round(time.time() - llm_start, 3)
    except Exception as exc:
        logger.exception("NARAD Core message processing failed:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Core intelligence processing failed: {str(exc)}"
        ) from exc

    assistant_text = core_result.get("response", "").strip()

    # Persist assistant message
    assistant_msg = smriti_service.add_assistant_message(
        session_id=session.id,
        content=assistant_text,
        provider=core_result.get("provider", "unknown"),
        model=core_result.get("model", "unknown"),
        metadata=core_result,
        db=db
    )

    # Step 4: Text-to-Speech via TTS Router
    tts_start = time.time()
    audio_b64 = None
    tts_provider_name = "browser_fallback"
    tts_device = "CPU"
    tts_latency = 0.0

    try:
        tts_result = await tts_manager.synthesize(
            text=assistant_text,
            language=stt_result.language
        )
        audio_b64 = base64.b64encode(tts_result.audio_bytes).decode("ascii")
        tts_provider_name = tts_result.provider
        tts_device = tts_result.device
        tts_latency = round(time.time() - tts_start, 3)
    except Exception as tts_exc:
        logger.warning("Local TTS synthesis failed (%s), returning text with browser fallback flag", tts_exc)
        tts_latency = round(time.time() - tts_start, 3)

    total_latency = round(time.time() - total_start, 3)

    return {
        "transcription": user_text,
        "detected_language": stt_result.language,
        "response": assistant_text,
        "chat_id": session.id,
        "audio_base64": audio_b64,
        "audio_format": "wav",
        "provider": core_result.get("provider"),
        "model": core_result.get("model"),
        "tools_executed": core_result.get("tools_executed", []),
        "telemetry": {
            "stt_engine": stt_result.engine,
            "stt_latency": stt_result.latency_seconds,
            "llm_engine": core_result.get("model", "core"),
            "llm_latency": llm_latency,
            "tts_engine": tts_provider_name,
            "tts_device": tts_device,
            "tts_latency": tts_latency,
            "total_latency": total_latency,
            "device": tts_device
        },
        "user_message": user_msg.to_dict(),
        "assistant_message": assistant_msg.to_dict()
    }
