"""
Test Suite for NARAD V8.2 Milestone 4:
Smṛti + Knowledge Integrated into Decision Making

Verifies:
1. Relevant memory is retrieved based on query keywords/aliases.
2. Irrelevant memory is ignored/filtered out.
3. Relevant knowledge is retrieved with source document citations.
4. Context reaches prompt payload in build_narad_system_prompt.
5. No-context behavior works safely and factually.
6. Memory / Knowledge retrieval failures do NOT crash chat execution.
"""

import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, SmritiMemory, KnowledgeDocument, KnowledgeChunk
from app.services.smriti import SmritiService
from app.services.knowledge import KnowledgeBaseService
from app.core.prompts import build_narad_system_prompt
from app.core.narad import NaradCore


class TestV82SmritiKnowledgeIntegration(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Create an isolated in-memory SQLite database for deterministic tests
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        self.smriti = SmritiService()
        self.knowledge = KnowledgeBaseService()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_01_relevant_memory_is_retrieved(self):
        """Query matching memory key/alias retrieves only that relevant memory."""
        # Seed memories
        self.smriti.save_memory(key="user_name", value="Pratyush", category="profile", db=self.db)
        self.smriti.save_memory(key="preferred_editor", value="Neovim", category="preferences", db=self.db)

        # Query asking for user's name
        result = self.smriti.get_relevant_memories_context(query="What is my name?", db=self.db)

        self.assertIn("user_name: Pratyush", result)
        self.assertNotIn("preferred_editor: Neovim", result)

    def test_02_irrelevant_memory_is_ignored(self):
        """Query about an unrelated topic does not return irrelevant memories."""
        self.smriti.save_memory(key="preferred_editor", value="Neovim", category="preferences", db=self.db)
        self.smriti.save_memory(key="home_city", value="Mumbai", category="profile", db=self.db)

        # Query about favorite vehicle/car
        result = self.smriti.get_relevant_memories_context(query="What car do I drive?", db=self.db)

        self.assertIn("No relevant persistent memories found", result)
        self.assertNotIn("Neovim", result)
        self.assertNotIn("Mumbai", result)

    def test_03_relevant_knowledge_is_retrieved_with_citation(self):
        """Knowledge context retrieves matched passages with source document citation."""
        doc = KnowledgeDocument(
            id="doc-123",
            filename="quarterly_report.pdf",
            file_type="pdf",
            file_size=1024,
            file_path="/tmp/quarterly_report.pdf",
            chunk_count=1,
            status="READY"
        )
        self.db.add(doc)
        chunk = KnowledgeChunk(
            id="chunk-1",
            document_id="doc-123",
            chunk_index=0,
            content="Q3 net revenue exceeded expectations by 24 percent reaching 50 million dollars.",
            token_count=15
        )
        self.db.add(chunk)
        self.db.commit()

        context = self.knowledge.get_relevant_knowledge_context(
            query="What was the Q3 net revenue?",
            max_chunks=2,
            db=self.db
        )

        self.assertIsNotNone(context)
        self.assertIn("quarterly_report.pdf", context)
        self.assertIn("net revenue exceeded expectations", context)

    def test_04_context_reaches_prompt_payload(self):
        """build_narad_system_prompt formats both Smriti and Knowledge context clearly."""
        memories = "- user_name: Pratyush (category: profile)"
        knowledge = "Source Document: [quarterly_report.pdf]\nRelevant Passage:\n\"Q3 revenue: $50M\""

        prompt = build_narad_system_prompt(
            provider_id="groq",
            model_name="openai/gpt-oss-120b",
            persistent_memories=memories,
            knowledge_context=knowledge
        )

        self.assertIn("CURRENT SMRITI PERSISTENT MEMORIES", prompt)
        self.assertIn("user_name: Pratyush", prompt)
        self.assertIn("RELEVANT LOCAL KNOWLEDGE BASE CONTEXT", prompt)
        self.assertIn("quarterly_report.pdf", prompt)
        self.assertIn("Q3 revenue: $50M", prompt)
        self.assertIn("Neural Assistant for Rizz & Absolute Destruction", prompt)

    def test_05_no_context_behavior_works_gracefully(self):
        """When memory and knowledge are empty, prompt contains clean baseline rules."""
        empty_mem = self.smriti.get_relevant_memories_context(query=None, db=self.db)
        empty_kb = self.knowledge.get_relevant_knowledge_context(query="Random query", db=self.db)

        self.assertIn("No persistent memories saved in Smṛti", empty_mem)
        self.assertIsNone(empty_kb)

        prompt = build_narad_system_prompt(
            provider_id="groq",
            model_name="openai/gpt-oss-120b",
            persistent_memories=empty_mem,
            knowledge_context=empty_kb
        )

        self.assertIn("No persistent memories saved in Smṛti", prompt)
        self.assertNotIn("RELEVANT LOCAL KNOWLEDGE BASE CONTEXT", prompt)

    async def test_06_memory_or_knowledge_failure_does_not_crash_chat(self):
        """Exceptions in Smriti or Knowledge retrieval are caught safely and do not fail the chat."""
        core = NaradCore()

        mock_provider = MagicMock()
        mock_provider.is_configured.return_value = True
        mock_provider.has_auth_error.return_value = False
        mock_provider.is_in_cooldown.return_value = False
        mock_provider.supports_vision.return_value = False
        mock_provider.generate_response = AsyncMock(return_value={
            "content": "Hello! I am operational.",
            "status": "success",
            "tools_executed": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}
        })

        with patch("app.services.smriti.smriti_service.get_relevant_memories_context", side_effect=Exception("Database lock error")), \
             patch("app.services.knowledge.knowledge_service.get_relevant_knowledge_context", side_effect=Exception("FTS index corruption")), \
             patch("app.core.router.model_router.resolve_route") as mock_route:

            mock_decision = MagicMock()
            mock_decision.provider_id = "groq"
            mock_decision.model_name = "openai/gpt-oss-120b"
            mock_decision.provider = mock_provider
            mock_decision.is_configured = True
            mock_decision.task_category = "GENERAL_CHAT"
            mock_decision.failover_candidates = []
            mock_route.return_value = mock_decision

            # Execute process_message - should succeed without raising exception
            res = await core.process_message(message="Hello")

            self.assertEqual(res["status"], "success")
            self.assertEqual(res["response"], "Hello! I am operational.")


if __name__ == "__main__":
    unittest.main()
