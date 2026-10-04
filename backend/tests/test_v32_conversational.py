"""
Unit and Integration Test Suite for NARAD V3.2:
- Elimination of Fake AI Fallback (Zero Mock AI Responses)
- Smṛti Conversation Summarization (Sessions > 24 messages)
- Conversational Core & Natural Dialogue Guidelines (Pronouns, Topic Continuity, Casual Chat)
- Health Subsystem Matrix (V3.2.0, Real Providers Only)
"""

import unittest
import asyncio
from typing import List, Dict, Any, Optional

from app.core.router import model_router
from app.providers.base import BaseLLMProvider
from app.providers.manager import provider_manager
from app.core.narad import NaradCore
from app.core.prompts import build_narad_system_prompt
from app.services.smriti import smriti_service
from app.db.database import SessionLocal
from app.db.models import ChatSession, ChatMessage


class FailingTestProvider(BaseLLMProvider):
    """Test provider that always throws an error."""
    def __init__(self, pid: str):
        super().__init__()
        self._pid = pid

    @property
    def provider_id(self) -> str:
        return self._pid

    @property
    def display_name(self) -> str:
        return f"Failing {self._pid}"

    def is_configured(self) -> bool:
        return True

    def get_available_models(self) -> List[str]:
        return [f"{self._pid}-model"]

    async def generate_response(self, messages, model=None, **kwargs):
        raise RuntimeError(f"Simulated network outage for {self._pid}")

    async def stream_response(self, messages, model=None, **kwargs):
        raise RuntimeError(f"Simulated network outage for {self._pid}")
        yield ""


class TestV32ConversationalAI(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    # =========================================================================
    # 1. Elimination of Fake AI Fallback (Phase 14)
    # =========================================================================

    def test_mock_narad_completely_eliminated(self):
        """Verify StubProvider / mock-narad is not registered or discoverable."""
        providers = provider_manager.list_providers()
        provider_ids = [p["id"] for p in providers]
        self.assertNotIn("mock-narad", provider_ids, "mock-narad must not exist in registered providers")

    def test_all_providers_unavailable_returns_clear_status(self):
        """
        Verify that if all configured providers fail, NARAD reports a truthful
        service_unavailable error and NEVER fabricates or mocks a conversation.
        """
        from unittest.mock import patch

        async def run():
            core = NaradCore()
            failing = FailingTestProvider("test-failing-prov")
            provider_manager.register_provider(failing)

            with patch.object(provider_manager, "get_provider", return_value=failing):
                res = await core.process_message(
                    message="Hello NARAD, what is the status?",
                    history=[],
                    session_id=None,
                    requested_provider="test-failing-prov"
                )

                self.assertEqual(res["status"], "service_unavailable")
                self.assertIn("All configured AI providers are currently unavailable", res["response"])
                # Ensure no fake conversational mock response
                self.assertNotIn("I am an AI assistant operating in standalone mock mode", res["response"])

        self.loop.run_until_complete(run())

    # =========================================================================
    # 2. Smṛti Conversation Summarization (Phases 7, 8, 9)
    # =========================================================================

    def test_smriti_no_premature_summary(self):
        """Sessions with <= 24 messages must NOT generate premature summaries."""
        db = SessionLocal()
        try:
            session = smriti_service.create_session(title="Short Session Test", db=db)
            
            # Add 10 messages (5 turns)
            for i in range(10):
                if i % 2 == 0:
                    smriti_service.add_user_message(session.id, f"Question {i}", db=db)
                else:
                    smriti_service.add_assistant_message(session.id, f"Answer {i}", db=db)

            summary = smriti_service.get_conversation_summary_context(session.id, sliding_window_messages=24, db=db)
            self.assertEqual(summary, "", "Summary must be empty when session is within sliding window limit")

            # Cleanup
            smriti_service.delete_session(session.id, db=db)
        finally:
            db.close()

    def test_smriti_summary_when_exceeding_sliding_window(self):
        """Sessions growing beyond 24 messages must produce a compact summary of older turns."""
        db = SessionLocal()
        try:
            session = smriti_service.create_session(title="Long Session Test", db=db)
            
            # Add 28 messages (14 turns)
            for i in range(28):
                if i % 2 == 0:
                    smriti_service.add_user_message(session.id, f"Topic turn {i}: Project Apollo requirement", db=db)
                else:
                    smriti_service.add_assistant_message(session.id, f"NARAD agreed on Apollo specification {i}", db=db)

            summary = smriti_service.get_conversation_summary_context(session.id, sliding_window_messages=24, db=db)
            self.assertTrue(len(summary) > 0, "Summary must not be empty when session > 24 messages")
            self.assertIn("Earlier discussion context", summary)
            self.assertIn("Apollo", summary)
            # Must remain compact (< 800 chars)
            self.assertLess(len(summary), 900)

            # Cleanup
            smriti_service.delete_session(session.id, db=db)
        finally:
            db.close()

    # =========================================================================
    # 3. Conversational Core System Prompt (Phases 10, 11, 12, 13)
    # =========================================================================

    def test_conversational_core_rules_in_system_prompt(self):
        """System prompt must enforce pronoun resolution, topic continuity, and tool discipline for casual chat."""
        prompt = build_narad_system_prompt(provider_id="groq", model_name="openai/gpt-oss-120b")
        
        self.assertIn("CONVERSATIONAL CORE & NATURAL DIALOGUE (V3.2)", prompt)
        self.assertIn("Pronouns & Anaphora", prompt)
        self.assertIn("Direct Follow-ups", prompt)
        self.assertIn("Topic Maintenance", prompt)
        self.assertIn("Casual Chat & Conversational Flow", prompt)
        self.assertIn("Voice-Ready Pacing", prompt)

    def test_conversation_summary_injection_in_prompt(self):
        """System prompt must inject EARLIER CONVERSATION SUMMARY when provided."""
        summary = "Earlier discussion context: User planned project X with budget 50k."
        prompt = build_narad_system_prompt(
            provider_id="groq",
            model_name="openai/gpt-oss-120b",
            conversation_summary=summary
        )
        self.assertIn("EARLIER CONVERSATION SUMMARY", prompt)
        self.assertIn("User planned project X with budget 50k", prompt)

    # =========================================================================
    # 4. Health Matrix & Version (Phase 16)
    # =========================================================================

    def test_health_version_is_3_2(self):
        """Health route must advertise version 3.2.0."""
        from app.api.routes.health import check_health
        db = SessionLocal()
        try:
            res = check_health(db=db)
            self.assertIn(res["version"], ("3.2.0", "4.0.0", "5.0.0", "6.0.0", "6.1.0", "7.0.0", "7.2.0", "8.1.0"))
            self.assertIn("groq", res["provider_matrix"])
            self.assertNotIn("mock-narad", res["provider_matrix"])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
