"""
Unit & Integration Tests for NARAD V2.2 Local Knowledge Base.
Tests ingestion, text extraction, chunking, FTS5 indexing, retrieval,
Krīya tool integration, source discipline, security bounds, and safe deletion.
"""

import os
import unittest
import asyncio
from pathlib import Path
from app.services.knowledge import knowledge_service, SUPPORTED_EXTENSIONS
from app.services.kriya import kriya_dispatcher
from app.db.database import SessionLocal
from app.db.models import KnowledgeDocument, KnowledgeChunk


class TestKnowledgeBase(unittest.TestCase):

    def setUp(self):
        self.db = SessionLocal()
        self.created_doc_ids = []

    def tearDown(self):
        for doc_id in self.created_doc_ids:
            try:
                knowledge_service.delete_document(doc_id, self.db)
            except Exception:
                pass
        self.db.close()

    def test_supported_extensions(self):
        """Verify supported extensions are recognized."""
        for ext in [".pdf", ".txt", ".md", ".docx"]:
            self.assertIn(ext, SUPPORTED_EXTENSIONS)

    def test_path_traversal_prevention(self):
        """Verify illegal path traversal filenames are sanitized and confined."""
        malicious_filename = "../../../../etc/passwd"
        safe_path = knowledge_service._safe_path_for_document(malicious_filename, "test-id")
        self.assertTrue(str(safe_path).startswith(str(knowledge_service.storage_dir)))
        self.assertFalse(".." in str(safe_path))

    def test_chunking_logic(self):
        """Test document chunking with boundary awareness and overlap."""
        text = "Sentence one. " * 30 + "\n\n" + "Paragraph two is here. " * 20
        chunks = knowledge_service.chunk_document(text, chunk_size=200, chunk_overlap=50)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertGreater(len(c), 5)
            self.assertLessEqual(len(c), 350)  # reasonable boundary margin

    def test_ingestion_and_retrieval_lifecycle(self):
        """Verify full lifecycle: INGESTING -> EXTRACTING -> INDEXING -> READY, then search, then delete."""
        test_content = (
            "NARAD TEST DOCUMENT\n\n"
            "Project: TRIMURTI AI\n\n"
            "Purpose:\n"
            "Build a private personal AI system.\n\n"
            "Current modules:\n"
            "NARAD\n"
            "Smṛti\n"
            "Krīya\n\n"
            "Future modules:\n"
            "Manthan\n"
            "Vāṇī\n"
            "Trinetra\n\n"
            "TEST FACT:\n"
            "The project uses a local-first architecture."
        ).encode("utf-8")

        # Ingestion
        result = asyncio.run(knowledge_service.ingest_document(
            file_bytes=test_content,
            filename="trimurti_manifesto.txt",
            db=self.db
        ))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["telemetry"], ["INGESTING", "EXTRACTING", "INDEXING", "READY"])
        doc_dict = result["document"]
        doc_id = doc_dict["id"]
        self.created_doc_ids.append(doc_id)
        self.assertEqual(doc_dict["status"], "READY")
        self.assertGreaterEqual(doc_dict["chunk_count"], 1)

        # File exists on disk in private storage
        stored_file = Path(doc_dict["file_path"])
        self.assertTrue(stored_file.is_file())
        self.assertTrue(str(stored_file).startswith(str(knowledge_service.storage_dir)))

        # Retrieval 1: Match Purpose
        search_res1 = knowledge_service.search_knowledge("purpose TRIMURTI", max_results=3, db=self.db)
        self.assertEqual(search_res1["status"], "success")
        self.assertGreaterEqual(search_res1["count"], 1)
        top_match = search_res1["results"][0]
        self.assertEqual(top_match["document_name"], "trimurti_manifesto.txt")
        self.assertIn("Build a private personal AI system", top_match["passage"])

        # Retrieval 2: Future modules
        search_res2 = knowledge_service.search_knowledge("future modules", max_results=3, db=self.db)
        self.assertGreaterEqual(search_res2["count"], 1)
        self.assertIn("Manthan", search_res2["results"][0]["passage"])

        # Retrieval 3: Non-existent concept should yield 0 results
        search_res3 = knowledge_service.search_knowledge("programming language python rust", max_results=3, db=self.db)
        self.assertEqual(search_res3["count"], 0)

        # Deletion
        del_success = knowledge_service.delete_document(doc_id, self.db)
        self.assertTrue(del_success)
        self.assertFalse(stored_file.exists())

        # Verify deleted document is no longer retrievable
        search_res4 = knowledge_service.search_knowledge("trimurti_manifesto", max_results=3, db=self.db)
        retrieved_doc_ids = [r["document_id"] for r in search_res4.get("results", [])]
        self.assertNotIn(doc_id, retrieved_doc_ids)

    def test_kriya_tool_search_knowledge(self):
        """Verify Krīya dispatcher can execute search_knowledge tool."""
        # 1. Ingest document
        content = b"Local Document Test\n\nEncryption: 256-bit AES military-grade local vault."
        ingest_res = asyncio.run(knowledge_service.ingest_document(
            file_bytes=content,
            filename="vault_spec.txt",
            db=self.db
        ))
        doc_id = ingest_res["document"]["id"]
        self.created_doc_ids.append(doc_id)

        # 2. Dispatch via Krīya
        kriya_res = asyncio.run(kriya_dispatcher.execute_tool(
            "search_knowledge",
            {"query": "Encryption military-grade AES", "max_results": 2}
        ))
        self.assertEqual(kriya_res.get("status"), "success")
        self.assertGreaterEqual(kriya_res.get("count", 0), 1)
        self.assertIn("256-bit AES", kriya_res["results"][0]["passage"])

    def test_ingestion_failure_handling(self):
        """Verify invalid files gracefully produce FAILED telemetry."""
        # Unsupported file extension
        with self.assertRaises(ValueError):
            asyncio.run(knowledge_service.ingest_document(
                file_bytes=b"malicious script",
                filename="script.exe",
                db=self.db
            ))

        # Empty file
        with self.assertRaises(ValueError):
            asyncio.run(knowledge_service.ingest_document(
                file_bytes=b"",
                filename="empty.txt",
                db=self.db
            ))


if __name__ == "__main__":
    unittest.main()
