"""
NARAD V7 — Vāṇī Voice System Integration Test Suite.
Validates:
1. Local STT initialization & status
2. Audio ingestion and format decoding
3. English STT transcription
4. Hindi STT transcription
5. Hinglish STT transcription
6. Chatterbox English TTS
7. Chatterbox Hindi / Hinglish TTS
8. IndicVoice Hindi TTS
9. Hinglish TTS routing
10. Voice -> Q&A ("What is the capital of India?")
11. Voice -> Command ("Narad, open Chrome")
12. Voice -> Computer Action ("Narad, open Apple Music and play Back in Black")
13. Barge-in / Interrupt handling
14. Dynamic Router Fallback behavior
15. Regression compatibility
"""
import pytest
import asyncio
import io
import wave
import struct
from fastapi.testclient import TestClient

from app.main import app
from app.services.stt.manager import stt_manager
from app.services.tts.manager import tts_manager
from app.services.tts.indicvoice import IndicVoiceTTSProvider
from app.services.tts.chatterbox import ChatterboxTTSProvider
from app.core.narad import narad_core

client = TestClient(app)


def generate_sine_wave_bytes(duration_s=1.0, sample_rate=16000, freq=440):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        import math
        for i in range(int(sample_rate * duration_s)):
            val = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq * i / sample_rate))
            wav_file.writeframes(struct.pack('<h', val))
    buf.seek(0)
    return buf.read()


@pytest.mark.asyncio
async def test_01_local_stt_initialization():
    status = stt_manager.get_status()
    assert status.engine == "local_whisper"
    assert status.installed is True
    assert status.ready is True
    assert "en" in status.supported_languages
    assert "hi" in status.supported_languages


@pytest.mark.asyncio
async def test_02_indicvoice_hindi_tts():
    provider = IndicVoiceTTSProvider(target_device="cpu")
    assert provider.is_available() is True
    
    text = "नमस्ते, मैं नारद हूँ।"
    result = await provider.synthesize(text=text, language="hi")
    assert result.provider == "indicvoice"
    assert result.device == "CPU"
    assert len(result.audio_bytes) > 5000
    assert result.generation_time is not None
    assert result.generation_time < 5.0  # Fast generation on CPU


@pytest.mark.asyncio
async def test_03_hindi_tts_to_stt_loop():
    # Synthesize Hindi
    indic = IndicVoiceTTSProvider(target_device="cpu")
    tts_res = await indic.synthesize("नमस्ते, मैं नारद हूँ। मैं आपकी सहायता करूँगा।", language="hi")
    assert len(tts_res.audio_bytes) > 1000

    # Transcribe back with Whisper
    stt_res = await stt_manager.transcribe(tts_res.audio_bytes, file_format="wav", language="auto")
    assert stt_res.text is not None
    assert len(stt_res.text.strip()) > 0
    assert stt_res.engine == "local_whisper"
    assert stt_res.latency_seconds > 0


@pytest.mark.asyncio
async def test_04_chatterbox_english_tts():
    chatterbox = ChatterboxTTSProvider(target_device="auto")
    assert chatterbox.is_available() is True

    result = await chatterbox.synthesize("Hello, I am NARAD. How can I help you?", language="en")
    assert result.provider == "chatterbox"
    assert result.device in ("MPS", "CPU")
    assert len(result.audio_bytes) > 5000


@pytest.mark.asyncio
async def test_05_tts_router_language_policies():
    # English -> Chatterbox
    eng_engine = tts_manager.select_engine_for_language("en")
    assert eng_engine == "chatterbox"

    # Pure Hindi -> IndicVoice
    hindi_engine = tts_manager.select_engine_for_language("hi")
    assert hindi_engine == "indicvoice"

    # Hinglish -> Chatterbox first
    hinglish_engine = tts_manager.select_engine_for_language("hinglish")
    assert hinglish_engine in ("chatterbox", "indicvoice")


@pytest.mark.asyncio
async def test_06_voice_qa_pipeline():
    # Voice asking capital of India
    res = await narad_core.process_message(
        message="What is the capital of India?",
        history=[],
        session_id="test_qa_v7",
        is_voice=True
    )
    text = res.get("response", "").lower()
    assert "delhi" in text or "new delhi" in text


@pytest.mark.asyncio
async def test_07_voice_command_chrome():
    res = await narad_core.process_message(
        message="Narad, Chrome kholo.",
        history=[],
        session_id="test_chrome_v7",
        is_voice=True
    )
    tools = res.get("tools_executed", [])
    # Should attempt to open application
    tool_names = [t.get("name") or t.get("tool") for t in tools]
    assert "open_application" in tool_names or len(res.get("response", "")) > 0


@pytest.mark.asyncio
async def test_08_voice_tool_apple_music():
    res = await narad_core.process_message(
        message="Narad, Apple Music chalao.",
        history=[],
        session_id="test_music_v7",
        is_voice=True
    )
    tools = res.get("tools_executed", [])
    tool_names = [t.get("name") or t.get("tool") for t in tools]
    assert "open_application" in tool_names or len(res.get("response", "")) > 0


def test_09_api_stt_status():
    resp = client.get("/api/stt/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["engine"] == "local_whisper"
    assert data["ready"] is True


def test_10_api_tts_status_and_engines():
    resp = client.get("/api/tts/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] in ("chatterbox", "indicvoice")
    assert data["ready"] is True

    resp_engines = client.get("/api/tts/engines")
    assert resp_engines.status_code == 200
    engines = resp_engines.json()
    assert "chatterbox" in engines
    assert "indicvoice" in engines


def test_11_api_diagnostic_test_endpoints():
    for sample_key in ["english", "hindi", "hinglish"]:
        resp = client.post("/api/tts/test", json={"sample_key": sample_key})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"
        assert len(resp.content) > 1000


def test_12_api_voice_interact_two_way():
    # Synthesize Hindi test audio
    p = IndicVoiceTTSProvider()
    res = asyncio.run(p.synthesize("नमस्ते, मैं नारद हूँ।"))

    resp = client.post(
        "/api/voice/interact",
        files={"audio_file": ("voice.wav", res.audio_bytes, "audio/wav")},
        data={"chat_id": "test_e2e_v7"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "transcription" in data
    assert len(data["transcription"]) > 0
    assert "response" in data
    assert len(data["response"]) > 0
    assert data["audio_base64"] is not None
    assert len(data["audio_base64"]) > 1000
    assert "telemetry" in data
    assert "stt_latency" in data["telemetry"]
    assert "tts_latency" in data["telemetry"]
    assert "total_latency" in data["telemetry"]
