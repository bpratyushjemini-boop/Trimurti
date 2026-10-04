"""
Unit tests for NARAD System Prompts & Identity Enforcement Subsystem.
Verifies system prompt construction, identity constraints, runtime metadata injection,
and Smriti memory summary integration.
"""

import unittest
import tempfile
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.prompts import build_narad_system_prompt
from app.db.models import Base
from app.services.smriti import SmritiService


class TestNaradPrompts(unittest.TestCase):
    def test_01_system_prompt_identity_defaults(self):
        """Verify NARAD system prompt contains mandatory identity markers and negative constraints."""
        prompt = build_narad_system_prompt(
            provider_id="groq",
            model_name="openai/gpt-oss-120b"
        )
        self.assertIn("NARAD", prompt)
        self.assertIn("TRIMURTI", prompt)
        self.assertIn("Neural Assistant for Rizz & Absolute Destruction", prompt)
        self.assertIn("Groq LPU Inference Engine", prompt)
        self.assertIn("openai/gpt-oss-120b", prompt)
        self.assertIn("NEVER claim to be ChatGPT", prompt)
        self.assertIn("Smriti", prompt)

    def test_02_system_prompt_dynamic_metadata(self):
        """Verify prompt updates dynamically with custom provider and model."""
        prompt = build_narad_system_prompt(
            provider_id="gemini",
            model_name="gemini-3.6-flash"
        )
        self.assertIn("GEMINI", prompt)
        self.assertIn("gemini-3.6-flash", prompt)

    def test_03_memory_context_formatting(self):
        """Verify Smriti get_session_memory_context returns factual session data."""
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        temp_path = temp_db.name
        temp_db.close()

        try:
            engine = create_engine(f"sqlite:///{temp_path}", connect_args={"check_same_thread": False})
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

            smriti = SmritiService()
            db = SessionLocal()

            session = smriti.create_session(title="Test Memory Briefing", db=db)
            smriti.add_user_message(session.id, "Hello NARAD", db=db)
            smriti.add_assistant_message(session.id, "Greetings.", db=db)

            summary = smriti.get_session_memory_context(session.id, db=db)
            self.assertIn("Test Memory Briefing", summary)
            self.assertIn(session.id, summary)
            self.assertIn("2", summary)  # 2 recorded dialogue turns

            prompt = build_narad_system_prompt(
                provider_id="groq",
                model_name="openai/gpt-oss-120b",
                session_id=session.id,
                memory_context=summary
            )
            self.assertIn("CURRENT SMRITI MEMORY VAULT STATE", prompt)
            self.assertIn("Test Memory Briefing", prompt)

            db.close()
            engine.dispose()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
