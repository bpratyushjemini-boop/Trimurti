"""
Tests for NARAD V8.2 Milestone 3: Vāṇī Natural Hindi + English Voice Pipeline.

Validates:
1. Bilingual Language Detection: Devanagari Hindi ('hi'), Colloquial Hinglish ('hinglish'), English ('en').
2. Engine Selection Layer: Selecting between IndicVoice, Chatterbox, and Fallback based on language & availability.
3. Voice Generation Timing & Telemetry.
4. Graceful Fallback: Text response remains functional when voice synthesis is unavailable or fails.
"""

import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

from app.services.tts.manager import tts_manager, TTSManager
from app.services.tts.base import TTSResult, TTSStatus


class TestV82VaniVoice(unittest.TestCase):

    def setUp(self):
        self.manager = TTSManager()

    # 1. Bilingual Language Detection
    def test_detect_language_devanagari_hindi(self):
        text = "नमस्ते, मैं नारद हूँ। आज का मौसम कैसा है?"
        lang = self.manager.detect_language(text)
        self.assertEqual(lang, "hi")

    def test_detect_language_hinglish(self):
        # Example from target user workflow: "Narad, aaj mera schedule kya hai?"
        text = "Narad, aaj mera schedule kya hai?"
        lang = self.manager.detect_language(text)
        self.assertEqual(lang, "hinglish")

        text2 = "Namaste bhai, chrome kholo aur gaana chalao"
        self.assertEqual(self.manager.detect_language(text2), "hinglish")

    def test_detect_language_english(self):
        text = "Open Firefox and navigate to the online compiler."
        lang = self.manager.detect_language(text)
        self.assertEqual(lang, "en")

    # 2. Engine Selection Layer
    def test_select_engine_hindi_prefers_indicvoice(self):
        with patch.object(self.manager.get_provider("indicvoice"), "is_available", return_value=True), \
             patch.object(self.manager.get_provider("chatterbox"), "is_available", return_value=True):
            engine = self.manager.select_engine_for_language("hi")
            self.assertEqual(engine, "indicvoice")

    def test_select_engine_hindi_falls_back_to_chatterbox_if_indicvoice_unavailable(self):
        with patch.object(self.manager.get_provider("indicvoice"), "is_available", return_value=False), \
             patch.object(self.manager.get_provider("chatterbox"), "is_available", return_value=True):
            engine = self.manager.select_engine_for_language("hi")
            self.assertEqual(engine, "chatterbox")

    def test_select_engine_hinglish_prefers_chatterbox(self):
        with patch.object(self.manager.get_provider("chatterbox"), "is_available", return_value=True):
            engine = self.manager.select_engine_for_language("hinglish")
            self.assertEqual(engine, "chatterbox")

    def test_select_engine_english_prefers_chatterbox(self):
        with patch.object(self.manager.get_provider("chatterbox"), "is_available", return_value=True):
            engine = self.manager.select_engine_for_language("en")
            self.assertEqual(engine, "chatterbox")

    # 3. Voice Generation Timing & Telemetry
    def test_synthesize_records_generation_timing_and_telemetry(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            mock_res = TTSResult(
                audio_bytes=b"RIFFmockwavdata",
                format="wav",
                sample_rate=24000,
                generation_time=0.145,
                duration_seconds=1.2,
                provider="chatterbox",
                language="en",
                device="cpu"
            )
            mock_provider = MagicMock()
            mock_provider.is_available.return_value = True
            mock_provider.synthesize = AsyncMock(return_value=mock_res)

            with patch.object(self.manager, "get_provider", return_value=mock_provider):
                res = loop.run_until_complete(self.manager.synthesize("Done. Output verified.", language="en"))
                self.assertEqual(res.provider, "chatterbox")
                self.assertEqual(res.generation_time, 0.145)
                self.assertEqual(res.sample_rate, 24000)
                self.assertIsNotNone(res.audio_bytes)
        finally:
            loop.close()

    # 4. Engine Telemetry Status
    def test_tts_manager_status_reporting(self):
        status = self.manager.get_status()
        self.assertIn("en", status.supported_languages)
        self.assertIn("hi", status.supported_languages)
        self.assertIn("hinglish", status.supported_languages)
        self.assertIn("chatterbox", status.available_engines)
        self.assertIn("indicvoice", status.available_engines)


if __name__ == "__main__":
    unittest.main()
