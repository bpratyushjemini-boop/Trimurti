"""
Automated Unit Tests for Smriti Memory Subsystem — Milestone 2.
Verifies session creation, message persistence, ordered history retrieval,
cross-session isolation, and SQLite reload persistence.
"""

import os
import unittest
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, ChatSession, ChatMessage
from app.services.smriti import SmritiService

class TestSmritiMemoryService(unittest.TestCase):
    def setUp(self):
        # Create an isolated temporary SQLite database file for testing
        self.temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = self.temp_db_file.name
        self.temp_db_file.close()

        self.test_engine = create_engine(
            f"sqlite:///{self.temp_db_path}",
            connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=self.test_engine)
        self.TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.test_engine)

        # Instantiate SmritiService overriding _get_session to use test db
        self.smriti = SmritiService()
        self.db = self.TestSessionLocal()

    def tearDown(self):
        self.db.close()
        self.test_engine.dispose()
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_01_create_session(self):
        """1. Create session: verifies stable UUID and default/custom title."""
        session = self.smriti.create_session(title="Alpha Briefing", db=self.db)
        self.assertIsNotNone(session.id)
        self.assertEqual(len(session.id), 36)
        self.assertEqual(session.title, "Alpha Briefing")
        self.assertIsNotNone(session.created_at)

    def test_02_save_user_message(self):
        """2. Save user message: appends turn to session and auto-titles if default."""
        session = self.smriti.create_session(title="New Briefing", db=self.db)
        user_msg = self.smriti.add_user_message(
            session_id=session.id,
            content="Initiate diagnostic protocol for Narad subsystem",
            db=self.db
        )
        self.assertIsNotNone(user_msg.id)
        self.assertEqual(user_msg.role, "user")
        self.assertEqual(user_msg.content, "Initiate diagnostic protocol for Narad subsystem")
        self.assertEqual(user_msg.session_id, session.id)

        # Verify auto-title updated from default
        refreshed_session = self.smriti.get_session(session.id, db=self.db)
        self.assertTrue(refreshed_session.title.startswith("Initiate diagnostic protocol"))

    def test_03_save_assistant_response(self):
        """3. Save assistant response: records turn with provider and model metadata."""
        session = self.smriti.create_session(title="Beta Session", db=self.db)
        asst_msg = self.smriti.add_assistant_message(
            session_id=session.id,
            content="All systems operational. Gemini 3.6 Flash standing by.",
            provider="gemini",
            model="gemini-3.6-flash",
            metadata={"latency_ms": 120, "status": "success"},
            db=self.db
        )
        self.assertIsNotNone(asst_msg.id)
        self.assertEqual(asst_msg.role, "assistant")
        self.assertIn("operational", asst_msg.content)
        self.assertIn("gemini-3.6-flash", asst_msg.metadata_json)

    def test_04_retrieve_session(self):
        """4. Retrieve session: verifies session lookup and message list retrieval."""
        session = self.smriti.create_session(title="Gamma Session", db=self.db)
        self.smriti.add_user_message(session.id, "Hello Smriti", db=self.db)
        self.smriti.add_assistant_message(session.id, "Hello User", db=self.db)

        retrieved = self.smriti.get_session(session.id, db=self.db)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, session.id)

        messages = self.smriti.get_session_messages(session.id, db=self.db)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[1].role, "assistant")

    def test_05_retrieve_ordered_conversation_history(self):
        """5. Retrieve ordered conversation history: formats chronologically for LLM context."""
        session = self.smriti.create_session(title="Delta Dialogue", db=self.db)
        self.smriti.add_user_message(session.id, "First user turn", db=self.db)
        self.smriti.add_assistant_message(session.id, "First assistant reply", db=self.db)
        self.smriti.add_user_message(session.id, "Second user turn", db=self.db)
        self.smriti.add_assistant_message(session.id, "Second assistant reply", db=self.db)

        history = self.smriti.get_conversation_history(session.id, db=self.db)
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0], {"role": "user", "content": "First user turn"})
        self.assertEqual(history[1], {"role": "assistant", "content": "First assistant reply"})
        self.assertEqual(history[2], {"role": "user", "content": "Second user turn"})
        self.assertEqual(history[3], {"role": "assistant", "content": "Second assistant reply"})

    def test_06_reload_persistence_from_sqlite(self):
        """6. Reload persistence from SQLite: verifies data survives connection close and reload."""
        session = self.smriti.create_session(title="Persistent Briefing", db=self.db)
        self.smriti.add_user_message(session.id, "Persisted secret: OMEGA-42", db=self.db)
        self.smriti.add_assistant_message(session.id, "Acknowledged OMEGA-42", db=self.db)

        # Close existing session and connection
        session_id = session.id
        self.db.close()
        self.test_engine.dispose()

        # Reopen a completely new connection against the same SQLite database file
        new_engine = create_engine(f"sqlite:///{self.temp_db_path}")
        NewSession = sessionmaker(bind=new_engine)
        fresh_db = NewSession()

        try:
            reloaded_session = self.smriti.get_session(session_id, db=fresh_db)
            self.assertIsNotNone(reloaded_session)
            self.assertEqual(reloaded_session.title, "Persistent Briefing")

            reloaded_history = self.smriti.get_conversation_history(session_id, db=fresh_db)
            self.assertEqual(len(reloaded_history), 2)
            self.assertEqual(reloaded_history[0]["content"], "Persisted secret: OMEGA-42")
            self.assertEqual(reloaded_history[1]["content"], "Acknowledged OMEGA-42")
        finally:
            fresh_db.close()
            new_engine.dispose()

    def test_07_create_separate_session_and_verify_isolation(self):
        """7. Create separate session and verify isolation: Session A history never leaks into Session B."""
        session_a = self.smriti.create_session(title="Session A", db=self.db)
        session_b = self.smriti.create_session(title="Session B", db=self.db)

        self.smriti.add_user_message(session_a.id, "Directive in Session A only", db=self.db)
        self.smriti.add_assistant_message(session_a.id, "Response in Session A only", db=self.db)

        self.smriti.add_user_message(session_b.id, "Directive in Session B only", db=self.db)

        history_a = self.smriti.get_conversation_history(session_a.id, db=self.db)
        history_b = self.smriti.get_conversation_history(session_b.id, db=self.db)

        self.assertEqual(len(history_a), 2)
        self.assertEqual(len(history_b), 1)

        # Ensure no cross-contamination
        contents_a = [m["content"] for m in history_a]
        contents_b = [m["content"] for m in history_b]
        self.assertNotIn("Directive in Session B only", contents_a)
        self.assertNotIn("Directive in Session A only", contents_b)

    def test_08_delete_session_cascades_messages(self):
        """8. Delete session: removes session and cascades deletion of its messages."""
        session = self.smriti.create_session(title="Temporary Session", db=self.db)
        self.smriti.add_user_message(session.id, "Will be deleted", db=self.db)

        deleted = self.smriti.delete_session(session.id, db=self.db)
        self.assertTrue(deleted)

        # Verify session and messages are gone
        self.assertIsNone(self.smriti.get_session(session.id, db=self.db))
        messages = self.smriti.get_session_messages(session.id, db=self.db)
        self.assertEqual(len(messages), 0)

if __name__ == "__main__":
    unittest.main()
