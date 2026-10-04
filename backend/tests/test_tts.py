"""
Unit and Integration Tests for Vāṇī Local TTS Engine (Chatterbox Multilingual).
Validates provider abstraction, language detection, health status, and API behavior.
Ensures zero fake audio: fails cleanly with accurate diagnostics when dependencies are missing.
"""
import sys
import asyncio
import httpx
import pytest
import pytest_asyncio

from app.main import app
from app.services.tts.base import BaseTTSProvider, TTSStatus, TTSResult
from app.services.tts.chatterbox import ChatterboxTTSProvider
from app.services.tts.manager import tts_manager, DIAGNOSTIC_SAMPLES


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def test_base_provider_status_contract():
    """Verify TTSStatus schema validation and default fallback structure."""
    status = TTSStatus(
        provider="test_provider",
        installed=False,
        model_loaded=False,
        ready=False,
        mode="local",
        device="cpu",
        supported_languages=["en", "hi"],
        error="Dependency test error",
        active_fallback=True,
        fallback_provider="browser_speech_synthesis"
    )
    assert status.provider == "test_provider"
    assert status.installed is False
    assert status.ready is False
    assert status.active_fallback is True
    assert status.fallback_provider == "browser_speech_synthesis"


def test_chatterbox_provider_environment_detection():
    """Verify Chatterbox accurately probes Python runtime and package availability."""
    provider = ChatterboxTTSProvider(target_device="cpu")
    status = provider.get_status()

    assert status.provider == "chatterbox"
    assert status.mode == "local"
    assert "en" in status.supported_languages
    assert "hi" in status.supported_languages

    # In standard Python 3.9 / missing chatterbox-tts environments,
    # it must explicitly report not installed/not ready and activate fallback.
    assert status.model_loaded is False
    if not provider.is_available():
        assert status.ready is False
        assert status.error is not None
        assert status.active_fallback is True


def test_chatterbox_language_detection():
    """Verify language detection for English, Devanagari Hindi, and Hinglish."""
    provider = ChatterboxTTSProvider(target_device="cpu")

    # English
    en_res = provider._detect_language("Hello, I am NARAD. How can I help you?")
    assert en_res == "en"

    # Hindi (Devanagari script)
    hi_res = provider._detect_language("नमस्ते, मैं नारद हूँ। मैं आपकी कैसे सहायता कर सकता हूँ?")
    assert hi_res == "hi"

    # Hinglish / Romanized Hindi
    hinglish_res = provider._detect_language("Namaste, main NARAD hoon. Aaj hum kya kar rahe hain?")
    assert hinglish_res == "hi"

    # Explicit override
    override_res = provider._detect_language("Hello world", requested_lang="hi")
    assert override_res == "hi"


def test_tts_manager_lifecycle():
    """Verify TTSManager singleton orchestration and diagnostic samples registry."""
    status = tts_manager.get_status()
    assert status.provider == "chatterbox"

    assert "english" in DIAGNOSTIC_SAMPLES
    assert "hindi" in DIAGNOSTIC_SAMPLES
    assert "hinglish" in DIAGNOSTIC_SAMPLES

    assert DIAGNOSTIC_SAMPLES["english"]["text"] == "Hello, I am NARAD. How can I help you?"
    assert "नमस्ते" in DIAGNOSTIC_SAMPLES["hindi"]["text"]
    assert "Namaste" in DIAGNOSTIC_SAMPLES["hinglish"]["text"]


@pytest.mark.asyncio
async def test_tts_status_endpoint(client: httpx.AsyncClient):
    """Verify GET /api/tts/status returns structured telemetry."""
    response = await client.get("/api/tts/status")
    assert response.status_code == 200
    data = response.json()

    assert data["provider"] == "chatterbox"
    assert data["mode"] == "local"
    assert isinstance(data["ready"], bool)
    assert isinstance(data["installed"], bool)
    assert "en" in data["supported_languages"]
    assert "hi" in data["supported_languages"]


@pytest.mark.asyncio
async def test_tts_samples_endpoint(client: httpx.AsyncClient):
    """Verify GET /api/tts/samples returns all 3 diagnostic prompts."""
    response = await client.get("/api/tts/samples")
    assert response.status_code == 200
    data = response.json()

    assert "english" in data
    assert "hindi" in data
    assert "hinglish" in data


@pytest.mark.asyncio
async def test_tts_synthesize_uninitialized_clean_fallback(client: httpx.AsyncClient):
    """Verify /api/tts/synthesize fails cleanly with 503 and clear reason when not installed."""
    response = await client.post(
        "/api/tts/synthesize",
        json={"text": "Hello, I am NARAD.", "language": "en"}
    )
    status_info = tts_manager.get_status()
    if not status_info.ready:
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["fallback_recommended"] is True
        assert "Chatterbox" in data["detail"]["message"]


@pytest.mark.asyncio
async def test_tts_diagnostic_test_validation(client: httpx.AsyncClient):
    """Verify /api/tts/test validates sample keys and failure modes."""
    # Invalid key
    response = await client.post(
        "/api/tts/test",
        json={"sample_key": "invalid_language_key"}
    )
    status_info = tts_manager.get_status()
    if status_info.ready:
        assert response.status_code == 400
    else:
        # Pre-check fails cleanly if engine not ready
        assert response.status_code in (400, 503)


async def run_all_tests():
    print("Executing Vāṇī Local TTS Engine Test Suite...\n")

    # Synchronous unit tests
    test_base_provider_status_contract()
    print("  ✓ test_base_provider_status_contract PASSED")

    test_chatterbox_provider_environment_detection()
    print("  ✓ test_chatterbox_provider_environment_detection PASSED")

    test_chatterbox_language_detection()
    print("  ✓ test_chatterbox_language_detection PASSED")

    test_tts_manager_lifecycle()
    print("  ✓ test_tts_manager_lifecycle PASSED")

    # Asynchronous API integration tests
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await test_tts_status_endpoint(client)
        print("  ✓ test_tts_status_endpoint PASSED")

        await test_tts_samples_endpoint(client)
        print("  ✓ test_tts_samples_endpoint PASSED")

        await test_tts_synthesize_uninitialized_clean_fallback(client)
        print("  ✓ test_tts_synthesize_uninitialized_clean_fallback PASSED")

        await test_tts_diagnostic_test_validation(client)
        print("  ✓ test_tts_diagnostic_test_validation PASSED")

    print("\n" + "=" * 60)
    print("ALL 8 VĀṆĪ LOCAL TTS ENGINE TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
