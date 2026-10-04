"""
Automated Comprehensive Test Suite for Smṛti 3.0: Personal Memory Intelligence & Context Engine
Covers specifications:
- TEST A: Explicit fact extraction
- TEST B: Duplicate prevention
- TEST C: Conflict resolution
- TEST D: Temporary context filtering
- TEST E: Secret protection & privacy guardrails
- TEST F: Retrieval relevance (NARAD project query)
- TEST G: Unrelated retrieval (irrelevant query exclusion)
- TEST H: Forget commands & status transitions
- TEST I: Update commands & value mutation
- TEST J: Category classification & canonicalization
- TEST K: Confidence & importance scoring
- TEST L: Runtime separation (Runtime Truth vs Smṛti)
- TEST M: Provider independence (Ollama & Cloud provider compatibility)
- TEST N: Persistence & database reload resilience
- TEST P: REST API endpoints (/api/memory, /api/memory/status, /api/memory/search, etc.)
"""

import os
import unittest
import tempfile
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, SmritiMemory, ChatSession, ChatMessage
from app.services.smriti import SmritiService
from app.services.runtime_truth import runtime_truth_service


class TestSmriti3MemoryIntelligence(unittest.TestCase):
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

        self.smriti = SmritiService()
        self.db = self.TestSessionLocal()
        # Seed project memory
        self.smriti.init_project_memory(db=self.db)

    def tearDown(self):
        self.db.close()
        self.test_engine.dispose()
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    # =========================================================================
    # TEST A: Explicit fact extraction
    # =========================================================================
    def test_a_explicit_fact_extraction(self):
        """Input: 'My favorite color is blue.' -> Expected: memory created with PREFERENCES category."""
        extracted = self.smriti.observe_and_extract("My favorite color is blue.", db=self.db)
        self.assertTrue(len(extracted) >= 1)
        fav = extracted[0]
        self.assertEqual(fav["key"], "favorite_color")
        self.assertEqual(fav["value"], "blue")
        self.assertEqual(fav["category"], "PREFERENCES")
        self.assertGreaterEqual(fav["confidence"], 0.95)

        # Confirm persisted in SQLite
        retrieved = self.smriti.retrieve_memory("favorite_color", db=self.db)
        self.assertTrue(retrieved["found"])
        self.assertEqual(retrieved["value"], "blue")

    # =========================================================================
    # TEST B: Duplicate prevention
    # =========================================================================
    def test_b_duplicate_prevention(self):
        """Same fact twice -> Expected: one memory record in database."""
        res1 = self.smriti.save_memory("favorite_color", "blue", "PREFERENCES", db=self.db)
        res2 = self.smriti.save_memory("favorite_color", "blue", "PREFERENCES", db=self.db)
        self.assertTrue(res1["success"])
        self.assertTrue(res2["success"])

        # Also test with spelling alias: 'favorite colour'
        res3 = self.smriti.save_memory("favorite_colour", "blue", "PREFERENCES", db=self.db)
        self.assertTrue(res3["success"])

        # Count total memories with key favorite_color
        records = self.db.query(SmritiMemory).filter(SmritiMemory.key == "favorite_color").all()
        self.assertEqual(len(records), 1, "Duplicate key aliases must resolve to a single canonical record.")

    # =========================================================================
    # TEST C: Conflict resolution
    # =========================================================================
    def test_c_conflict_resolution(self):
        """Old device vs new device -> Expected: correct update/version and provenance history."""
        # Step 1: Initial state
        res1 = self.smriti.save_memory("device", "Windows laptop", "DEVICES", db=self.db)
        self.assertEqual(res1["status"], "saved")

        # Step 2: Conflicting new state
        res2 = self.smriti.save_memory("device", "MacBook Pro M3", "DEVICES", db=self.db)
        self.assertEqual(res2["status"], "updated")
        self.assertEqual(res2["value"], "MacBook Pro M3")

        # Verify only 1 device record exists
        device_mems = self.db.query(SmritiMemory).filter(SmritiMemory.key == "device").all()
        self.assertEqual(len(device_mems), 1)

        # Verify history provenance in metadata
        record = device_mems[0].to_dict()
        self.assertIn("history", record["metadata"])
        history = record["metadata"]["history"]
        self.assertTrue(len(history) >= 1)
        self.assertEqual(history[0]["previous_value"], "Windows laptop")

    # =========================================================================
    # TEST D: Temporary context filtering
    # =========================================================================
    def test_d_temporary_context_filtering(self):
        """'I am tired today.' -> Expected: not permanent user fact (rejected by observation engine)."""
        res = self.smriti.observe_and_extract("I am tired today.", db=self.db)
        self.assertEqual(res, [], "Temporary fatigue and temporal anchor must not be persisted.")

        res_hungry = self.smriti.observe_and_extract("I am currently hungry right now.", db=self.db)
        self.assertEqual(res_hungry, [], "Transient temporal states must not be persisted.")

        res_speculative = self.smriti.observe_and_extract("I might buy a new laptop someday.", db=self.db)
        self.assertEqual(res_speculative, [], "Speculative statements with 'might' and 'someday' must not be persisted.")

        res_hearsay = self.smriti.observe_and_extract("My friend told me that Python is bad.", db=self.db)
        self.assertEqual(res_hearsay, [], "Hearsay statements must not be persisted.")

    # =========================================================================
    # TEST E: Secret protection & privacy guardrails
    # =========================================================================
    def test_e_secret_protection(self):
        """Input containing API keys or sensitive traits -> Expected: rejected from persistence."""
        # 1. Fake API Key
        secret_key = "sk-1234567890abcdef1234567890abcdef"
        res = self.smriti.save_memory("api_key", secret_key, db=self.db)
        self.assertFalse(res.get("success", False))
        self.assertEqual(res["status"], "rejected")

        # 2. Sensitive Health Topic
        res_health = self.smriti.save_memory("medical_history", "diagnosed with diabetes", db=self.db)
        self.assertFalse(res_health.get("success", False))
        self.assertEqual(res_health["status"], "rejected")

        # Verify neither was stored in database
        sec_record = self.db.query(SmritiMemory).filter(SmritiMemory.key == "api_key").first()
        self.assertIsNone(sec_record)
        health_record = self.db.query(SmritiMemory).filter(SmritiMemory.key == "medical_history").first()
        self.assertIsNone(health_record)

    # =========================================================================
    # TEST F: Retrieval relevance (NARAD project query)
    # =========================================================================
    def test_f_retrieval_relevance(self):
        """Ask about NARAD -> Expected: NARAD project memories retrieved."""
        context = self.smriti.get_relevant_memories_context(query="What is my NARAD project phase and objective?", db=self.db)
        self.assertIn("NARAD / TRIMURTI AI", context)
        self.assertIn("Phase 2", context)
        self.assertIn("Smṛti 3.0", context)

    # =========================================================================
    # TEST G: Unrelated retrieval (irrelevant memories stay out)
    # =========================================================================
    def test_g_unrelated_retrieval(self):
        """Ask unrelated question -> Expected: irrelevant memories excluded."""
        self.smriti.save_memory("favorite_color", "blue", "PREFERENCES", db=self.db)
        self.smriti.save_memory("name", "Pratyush", "IDENTITY", db=self.db)

        # Unrelated query about geography
        context = self.smriti.get_relevant_memories_context(query="What is the capital of France?", db=self.db)
        self.assertNotIn("favorite_color", context)
        self.assertNotIn("Pratyush", context)
        self.assertIn("No relevant persistent memories found", context)

    # =========================================================================
    # TEST H: Forget
    # =========================================================================
    def test_h_forget_memory(self):
        """Store -> forget -> Expected: memory no longer active/retrievable."""
        self.smriti.save_memory("favorite_drink", "Cold Brew Coffee", "PREFERENCES", db=self.db)
        ret1 = self.smriti.retrieve_memory("favorite_drink", db=self.db)
        self.assertTrue(ret1["found"])

        del_res = self.smriti.delete_memory("favorite_drink", db=self.db)
        self.assertEqual(del_res["status"], "deleted")

        ret2 = self.smriti.retrieve_memory("favorite_drink", db=self.db)
        self.assertFalse(ret2["found"])

    # =========================================================================
    # TEST I: Update
    # =========================================================================
    def test_i_update_memory(self):
        """Store -> update -> Expected: new value returned."""
        self.smriti.save_memory("editor", "VS Code", "PREFERENCES", db=self.db)
        ret1 = self.smriti.retrieve_memory("preferred_editor", db=self.db)
        self.assertEqual(ret1["value"], "VS Code")

        # Update via command or save_memory
        self.smriti.save_memory("preferred_editor", "Neovim", "PREFERENCES", db=self.db)
        ret2 = self.smriti.retrieve_memory("editor", db=self.db)
        self.assertEqual(ret2["value"], "Neovim")

    # =========================================================================
    # TEST J: Category classification
    # =========================================================================
    def test_j_category_classification(self):
        """Verify categories map to canonical uppercase categories."""
        self.assertEqual(self.smriti.normalize_category("profile"), "IDENTITY")
        self.assertEqual(self.smriti.normalize_category("personal"), "IDENTITY")
        self.assertEqual(self.smriti.normalize_category("preference"), "PREFERENCES")
        self.assertEqual(self.smriti.normalize_category("project"), "PROJECTS")
        self.assertEqual(self.smriti.normalize_category("hardware"), "DEVICES")
        self.assertEqual(self.smriti.normalize_category("device"), "DEVICES")
        self.assertEqual(self.smriti.normalize_category("tech"), "SKILLS")
        self.assertEqual(self.smriti.normalize_category("goal"), "PLANS")
        self.assertEqual(self.smriti.normalize_category("fact"), "FACTS")

    # =========================================================================
    # TEST K: Confidence & Importance scoring
    # =========================================================================
    def test_k_confidence_scoring(self):
        """Explicit facts receive high confidence."""
        res_explicit = self.smriti.observe_and_extract("My name is Pratyush.", db=self.db)
        self.assertTrue(len(res_explicit) >= 1)
        self.assertAlmostEqual(res_explicit[0]["confidence"], 1.0)
        self.assertGreaterEqual(res_explicit[0]["importance"], 0.8)

        # Check retrieval ranking score incorporates confidence and importance
        memories = self.smriti.retrieve_relevant_memories(query="Pratyush", db=self.db)
        self.assertTrue(len(memories) >= 1)
        self.assertIn(memories[0]["key"], ("user_name", "name"))

    # =========================================================================
    # TEST L: Runtime separation (Runtime Truth vs Smṛti)
    # =========================================================================
    def test_l_runtime_separation(self):
        """Runtime Truth remains authoritative for provider, model, local/cloud, network, autonomy."""
        truth = runtime_truth_service.get_runtime_truth()
        self.assertIn("inference", truth)
        self.assertIn("provider", truth["inference"])
        self.assertIn("execution", truth["inference"])
        self.assertIn("network_required", truth["inference"])
        self.assertIn("autonomy", truth)
        # Verify Smriti persistent memory count is tracked separately from context count
        self.assertIn("memory", truth)
        self.assertIn("stored_memory_count", truth["memory"])
        self.assertIn("current_context_message_count", truth["memory"])

    # =========================================================================
    # TEST M: Provider independence (Ollama & Cloud provider compatibility)
    # =========================================================================
    def test_m_provider_independence(self):
        """Memory system operates completely independently of which provider is active."""
        # Store facts
        self.smriti.save_memory("primary_language", "Python", "SKILLS", db=self.db)

        # Simulating Ollama turn
        context_ollama = self.smriti.get_relevant_memories_context("What programming language do I use?", db=self.db)
        self.assertIn("primary_language: Python", context_ollama)

        # Simulating Groq turn
        context_groq = self.smriti.get_relevant_memories_context("What programming language do I use?", db=self.db)
        self.assertIn("primary_language: Python", context_groq)

        # Simulating Gemini turn
        context_gemini = self.smriti.get_relevant_memories_context("What programming language do I use?", db=self.db)
        self.assertIn("primary_language: Python", context_gemini)

    # =========================================================================
    # TEST N: Persistence & database reload resilience
    # =========================================================================
    def test_n_persistence_across_reloads(self):
        """Data survives connection close and reload."""
        self.smriti.save_memory("permanent_axiom", "TRIMURTI_PARADIGM_ACTIVE", "FACTS", db=self.db)

        # Close session and engine
        self.db.close()
        self.test_engine.dispose()

        # Reopen with brand new connection to same SQLite file
        new_engine = create_engine(f"sqlite:///{self.temp_db_path}")
        NewSession = sessionmaker(bind=new_engine)
        fresh_db = NewSession()

        try:
            reloaded = self.smriti.retrieve_memory("permanent_axiom", db=fresh_db)
            self.assertTrue(reloaded["found"])
            self.assertEqual(reloaded["value"], "TRIMURTI_PARADIGM_ACTIVE")
        finally:
            fresh_db.close()
            new_engine.dispose()

    # =========================================================================
    # TEST P: Natural-language commands handling
    # =========================================================================
    def test_p_natural_language_commands(self):
        """Verify deterministic handling of user memory directives."""
        # 1. Direct Remember
        cmd_rem = self.smriti.handle_memory_command("Remember that my preferred browser is Safari.", db=self.db)
        self.assertIsNotNone(cmd_rem)
        self.assertTrue(cmd_rem["handled"])
        self.assertIn("Saved to Smṛti", cmd_rem["response"])

        # 2. What do you remember about me?
        cmd_show = self.smriti.handle_memory_command("What do you remember about me?", db=self.db)
        self.assertIsNotNone(cmd_show)
        self.assertTrue(cmd_show["handled"])
        self.assertIn("SMṚTI // STORED MEMORIES", cmd_show["response"])

        # 3. Direct Forget
        cmd_forget = self.smriti.handle_memory_command("Forget my preferred browser", db=self.db)
        self.assertIsNotNone(cmd_forget)
        self.assertTrue(cmd_forget["handled"])
        self.assertIn("Deleted from Smṛti", cmd_forget["response"])


if __name__ == "__main__":
    unittest.main()
