"""
Knowledge Base Subsystem for NARAD V2.2 — Real Local Knowledge Base.
Provides clean, provider-independent local document ingestion, text extraction,
intelligent chunking, local SQLite indexing with FTS5, and fast retrieval.

All documents remain strictly local. No documents are ever uploaded to any external service.
"""

import os
import re
import uuid
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.db.database import SessionLocal, engine
from app.db.models import KnowledgeDocument, KnowledgeChunk

logger = logging.getLogger(__name__)

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".docx"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB


class KnowledgeBaseService:
    """
    Dedicated local Knowledge Base management service.
    Handles ingestion, validation, extraction, chunking, indexing, retrieval, and deletion.
    """

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir:
            self.storage_dir = Path(storage_dir).resolve()
        else:
            self.storage_dir = Path(settings.KNOWLEDGE_BASE_DIR).resolve()

        # Ensure dedicated local storage directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._init_fts_table()

    def _init_fts_table(self):
        """Ensure SQLite FTS5 virtual table exists for local full-text search."""
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                        chunk_id UNINDEXED,
                        document_id UNINDEXED,
                        filename,
                        content,
                        tokenize='porter unicode61'
                    );
                """))
                conn.commit()
            logger.info("[KnowledgeBase] SQLite FTS5 table initialized successfully.")
        except Exception as e:
            logger.warning(f"[KnowledgeBase] Could not initialize FTS5 table: {e}. Will use lexical fallback.")

    def _safe_path_for_document(self, filename: str, doc_id: str) -> Path:
        """
        Generate a safe, collision-free local filesystem path within storage_dir.
        Enforces path containment to prevent path traversal attacks.
        """
        clean_name = os.path.basename(filename)
        clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', clean_name)
        target_path = (self.storage_dir / f"{doc_id}_{clean_name}").resolve()

        # Security check: must reside inside self.storage_dir
        if not str(target_path).startswith(str(self.storage_dir)):
            raise ValueError(f"Security violation: Illegal file path traversal attempt for filename '{filename}'.")

        return target_path

    # =========================================================================
    # Text Extraction
    # =========================================================================

    def extract_text(self, file_path: str, file_type: str) -> str:
        """
        Extract clean text from a local document (PDF, TXT, MD, DOCX).
        Raises extraction errors for corrupted, empty, or unreadable documents.
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Document file does not exist at '{file_path}'.")

        ext = file_type.lower()
        if not ext.startswith("."):
            ext = f".{ext}"

        raw_text = ""

        # 1. Plain Text and Markdown
        if ext in (".txt", ".md", ".markdown"):
            raw_bytes = path.read_bytes()
            for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
                try:
                    raw_text = raw_bytes.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if not raw_text:
                raw_text = raw_bytes.decode("utf-8", errors="replace")

        # 2. PDF Documents
        elif ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(str(path))
                if len(reader.pages) == 0:
                    raise ValueError("PDF contains 0 pages.")

                extracted_pages = []
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        extracted_pages.append(page_text.strip())

                raw_text = "\n\n".join(extracted_pages)
                if not raw_text.strip():
                    raise ValueError("PDF does not contain any extractable text (it may be scanned/image-based or protected).")
            except Exception as e:
                raise ValueError(f"PDF extraction failed: {str(e)}")

        # 3. DOCX Documents
        elif ext == ".docx":
            try:
                import docx
                doc = docx.Document(str(path))
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                # Also extract table text
                for table in doc.tables:
                    for row in table.rows:
                        row_cells = [c.text.strip() for c in row.cells if c.text.strip()]
                        if row_cells:
                            paragraphs.append(" | ".join(row_cells))
                raw_text = "\n\n".join(paragraphs)
            except Exception as docx_err:
                # Fallback: inspect raw zip XML
                try:
                    import zipfile
                    import xml.etree.ElementTree as ET
                    with zipfile.ZipFile(str(path)) as z:
                        xml_content = z.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    texts = [elem.text for elem in tree.iter() if elem.tag.endswith("}t") and elem.text]
                    raw_text = " ".join(texts)
                except Exception:
                    raise ValueError(f"DOCX extraction failed: {str(docx_err)}")

        else:
            raise ValueError(f"Unsupported document file extension '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}")

        # Normalize text
        normalized = self._normalize_text(raw_text)
        if not normalized or len(normalized.strip()) < 3:
            raise ValueError("Extracted document text is empty or too short to index.")

        return normalized

    def _normalize_text(self, text: str) -> str:
        """Clean and normalize extracted text while preserving sentence structure."""
        if not text:
            return ""
        # Remove null bytes and invisible control characters
        cleaned = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
        # Collapse multiple blank lines
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        # Collapse horizontal whitespace runs
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        return cleaned.strip()

    # =========================================================================
    # Chunking
    # =========================================================================

    def chunk_document(
        self,
        text: str,
        chunk_size: int = 500,
        chunk_overlap: int = 100
    ) -> List[str]:
        """
        Intelligently split document text into overlapping chunks.
        Respects paragraph and sentence boundaries where possible.
        """
        if not text:
            return []

        # If total length is within single chunk size, return as is
        if len(text) <= chunk_size:
            return [text.strip()]

        # Split into natural paragraphs or sentences
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: List[str] = []
        current_chunk = ""

        for para in paragraphs:
            # If paragraph itself is longer than chunk_size, split by sentences or punctuation
            if len(para) > chunk_size:
                sentences = re.split(r'(?<=[.!?\n])\s+', para)
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    if len(current_chunk) + len(sentence) + 1 <= chunk_size:
                        current_chunk = f"{current_chunk} {sentence}".strip()
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                            # Overlap: keep tail of current_chunk
                            if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                                current_chunk = current_chunk[-chunk_overlap:].strip() + " " + sentence
                            else:
                                current_chunk = sentence
                        else:
                            # Sentence itself exceeds chunk size: split into slices
                            for i in range(0, len(sentence), chunk_size - chunk_overlap):
                                chunk_slice = sentence[i:i + chunk_size].strip()
                                if chunk_slice:
                                    chunks.append(chunk_slice)
                            current_chunk = ""
            else:
                if len(current_chunk) + len(para) + 2 <= chunk_size:
                    current_chunk = f"{current_chunk}\n\n{para}".strip() if current_chunk else para
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                        if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                            current_chunk = current_chunk[-chunk_overlap:].strip() + "\n\n" + para
                        else:
                            current_chunk = para
                    else:
                        current_chunk = para

        if current_chunk and current_chunk.strip():
            chunks.append(current_chunk.strip())

        # Filter out empty or duplicate trailing chunks
        final_chunks = [c for c in chunks if len(c.strip()) > 5]
        return final_chunks if final_chunks else [text[:chunk_size]]

    # =========================================================================
    # Ingestion Pipeline
    # =========================================================================

    async def ingest_document(
        self,
        file_bytes: bytes,
        filename: str,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Complete document ingestion workflow:
        1. Validate file type and size.
        2. Store file locally in private knowledge base directory.
        3. Extract text and handle failures.
        4. Normalize and chunk document.
        5. Store metadata and chunks in SQLite.
        6. Index chunks into SQLite FTS5.
        7. Return structured status and telemetry events.
        """
        telemetry: List[str] = ["INGESTING"]
        local_db = db or SessionLocal()
        should_close = db is None

        # 1. Validation
        clean_filename = os.path.basename(filename).strip()
        _, ext = os.path.splitext(clean_filename)
        ext = ext.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            telemetry.append("FAILED")
            if should_close:
                local_db.close()
            raise ValueError(f"Unsupported file format '{ext}'. Allowed formats: {', '.join(SUPPORTED_EXTENSIONS)}")

        file_size = len(file_bytes)
        if file_size <= 0:
            telemetry.append("FAILED")
            if should_close:
                local_db.close()
            raise ValueError("File is empty (0 bytes).")

        if file_size > MAX_FILE_SIZE:
            telemetry.append("FAILED")
            if should_close:
                local_db.close()
            raise ValueError(f"File size exceeds 25 MB limit ({file_size / (1024 * 1024):.1f} MB).")

        doc_id = str(uuid.uuid4())
        dest_path = self._safe_path_for_document(clean_filename, doc_id)

        # Write file to local disk
        try:
            dest_path.write_bytes(file_bytes)
        except Exception as write_err:
            telemetry.append("FAILED")
            if should_close:
                local_db.close()
            raise IOError(f"Could not save file to local knowledge repository: {write_err}")

        # Create Document record in DB with INGESTING status
        doc_record = KnowledgeDocument(
            id=doc_id,
            filename=clean_filename,
            file_type=ext.lstrip("."),
            file_size=file_size,
            file_path=str(dest_path),
            chunk_count=0,
            status="INGESTING",
            error_message=None
        )
        local_db.add(doc_record)
        local_db.commit()
        local_db.refresh(doc_record)

        try:
            # 2. Extract Text
            telemetry.append("EXTRACTING")
            doc_record.status = "EXTRACTING"
            local_db.commit()

            text_content = self.extract_text(str(dest_path), ext)

            # 3. Chunk Text & Index
            telemetry.append("INDEXING")
            doc_record.status = "INDEXING"
            local_db.commit()

            chunks = self.chunk_document(text_content, chunk_size=500, chunk_overlap=100)
            if not chunks:
                raise ValueError("No viable chunks generated from document content.")

            # Store chunks in SQLite
            chunk_records = []
            for idx, chunk_text in enumerate(chunks):
                chunk_id = str(uuid.uuid4())
                chunk_obj = KnowledgeChunk(
                    id=chunk_id,
                    document_id=doc_id,
                    chunk_index=idx,
                    content=chunk_text,
                    token_count=len(chunk_text.split()),
                    metadata_json=None
                )
                chunk_records.append(chunk_obj)
                local_db.add(chunk_obj)

            # Index in SQLite FTS5
            try:
                with engine.connect() as conn:
                    for chunk_obj in chunk_records:
                        conn.execute(text("""
                            INSERT INTO knowledge_fts (chunk_id, document_id, filename, content)
                            VALUES (:chunk_id, :doc_id, :filename, :content)
                        """), {
                            "chunk_id": chunk_obj.id,
                            "doc_id": doc_id,
                            "filename": clean_filename,
                            "content": chunk_obj.content
                        })
                    conn.commit()
            except Exception as fts_err:
                logger.warning(f"[KnowledgeBase] FTS5 chunk indexing warning: {fts_err}")

            # 4. Mark Ready
            telemetry.append("READY")
            doc_record.status = "READY"
            doc_record.chunk_count = len(chunks)
            doc_record.updated_at = datetime.utcnow()
            local_db.commit()
            local_db.refresh(doc_record)

            logger.info(f"[KnowledgeBase] Document '{clean_filename}' ({doc_id}) successfully ingested. Chunks: {len(chunks)}.")

            result = {
                "status": "success",
                "document": doc_record.to_dict(),
                "telemetry": telemetry,
                "chunks_indexed": len(chunks)
            }
            if should_close:
                local_db.close()
            return result

        except Exception as e:
            logger.error(f"[KnowledgeBase] Document ingestion failed for '{clean_filename}': {e}", exc_info=True)
            telemetry.append("FAILED")
            doc_record.status = "FAILED"
            doc_record.error_message = str(e)
            local_db.commit()
            if should_close:
                local_db.close()
            return {
                "status": "failed",
                "error": str(e),
                "document": doc_record.to_dict(),
                "telemetry": telemetry
            }

    # =========================================================================
    # Retrieval
    # =========================================================================

    def search_knowledge(
        self,
        query: str,
        max_results: int = 4,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Search indexed local documents.
        Ranks relevant passages and returns structured citations.
        Limits the text returned to prevent model context flooding.
        """
        clean_query = query.strip() if query else ""
        if not clean_query:
            return {
                "status": "empty",
                "message": "Search query was empty.",
                "query": query,
                "count": 0,
                "results_found": 0,
                "results": []
            }

        local_db = db or SessionLocal()
        should_close = db is None
        results: List[Dict[str, Any]] = []

        try:
            # 1. Attempt SQLite FTS5 search
            stop_words = {
                "what", "is", "are", "was", "were", "the", "a", "an", "and", "or", "in", "on", "at",
                "to", "for", "of", "with", "by", "from", "up", "about", "into", "over", "after"
            }
            fts_query_tokens = [re.sub(r'[^a-zA-Z0-9]', '', t) for t in clean_query.split()]
            fts_query_tokens = [t for t in fts_query_tokens if len(t) > 1 and t.lower() not in stop_words]
            fts_results = []

            if fts_query_tokens:
                # Build safe FTS match expression: "token1" OR "token2"
                fts_expr = " OR ".join([f'"{t}"*' for t in fts_query_tokens[:8]])
                try:
                    conn = local_db.connection()
                    rows = conn.execute(text("""
                        SELECT chunk_id, document_id, filename, content, bm25(knowledge_fts) as rank
                        FROM knowledge_fts
                        WHERE knowledge_fts MATCH :expr
                        ORDER BY rank ASC
                        LIMIT :limit
                    """), {"expr": fts_expr, "limit": max_results * 2}).fetchall()
                    for row in rows:
                        fts_results.append({
                            "chunk_id": row[0],
                            "document_id": row[1],
                            "filename": row[2],
                            "content": row[3],
                            "score": float(row[4]) if row[4] is not None else 1.0
                        })
                except Exception as fts_err:
                    logger.warning(f"[KnowledgeBase] FTS5 query failed: {fts_err}. Falling back to lexical scan.")

            # 2. Fallback / supplementary lexical matching if FTS yields few results
            if len(fts_results) < max_results:
                search_terms = [t.lower() for t in clean_query.split() if len(t) > 2]
                all_chunks = local_db.query(KnowledgeChunk, KnowledgeDocument.filename).join(
                    KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id
                ).filter(KnowledgeDocument.status == "READY").all()

                lexical_candidates = []
                for chunk, fname in all_chunks:
                    c_text = chunk.content.lower()
                    term_hits = sum(1 for term in search_terms if term in c_text)
                    exact_bonus = 3 if clean_query.lower() in c_text else 0
                    total_score = term_hits + exact_bonus
                    if total_score > 0:
                        lexical_candidates.append({
                            "chunk_id": chunk.id,
                            "document_id": chunk.document_id,
                            "chunk_index": chunk.chunk_index,
                            "filename": fname,
                            "content": chunk.content,
                            "score": -total_score  # lower is better for sorting consistency
                        })

                # Merge FTS and Lexical results avoiding duplicates
                seen_ids = set()
                for item in fts_results:
                    if item["chunk_id"] not in seen_ids:
                        seen_ids.add(item["chunk_id"])
                        results.append({
                            "document_name": item["filename"],
                            "document_id": item["document_id"],
                            "passage": item["content"],
                            "relevance_score": round(item["score"], 3)
                        })

                for item in sorted(lexical_candidates, key=lambda x: x["score"]):
                    if item["chunk_id"] not in seen_ids and len(results) < max_results:
                        seen_ids.add(item["chunk_id"])
                        results.append({
                            "document_name": item["filename"],
                            "document_id": item["document_id"],
                            "chunk_index": item.get("chunk_index", 0),
                            "passage": item["content"],
                            "relevance_score": round(item["score"], 3)
                        })
            else:
                for item in fts_results[:max_results]:
                    results.append({
                        "document_name": item["filename"],
                        "document_id": item["document_id"],
                        "passage": item["content"],
                        "relevance_score": round(item["score"], 3)
                    })

            # Optional semantic re-ranking using local Hugging Face embeddings
            try:
                from app.services.embeddings.manager import embedding_manager
                if embedding_manager.is_ready() and len(results) > 1:
                    candidates_for_rerank = [{"content": r["passage"], "original": r} for r in results]
                    reranked = embedding_manager.rerank_chunks(clean_query, candidates_for_rerank, top_k=max_results)
                    results = [item["original"] for item in reranked]
            except Exception as rerank_err:
                logger.debug("Knowledge base semantic re-ranking skipped: %s", rerank_err)

            # Explicit empty-result state if zero relevant passages found
            if not results:
                return {
                    "status": "empty",
                    "message": "Zero relevant document passages found in the Knowledge Base for this query.",
                    "query": clean_query,
                    "count": 0,
                    "results_found": 0,
                    "results": []
                }

            final_results = results[:max_results]
            formatted_chunks = []
            for item in final_results:
                doc_name = item["document_name"]
                passage_text = item["passage"].strip()
                item["formatted_passage"] = f"Document: {doc_name}\nRelevant passage:\n\"{passage_text}\""
                formatted_chunks.append(item["formatted_passage"])

            formatted_context = "\n\n---\n\n".join(formatted_chunks)

            return {
                "status": "success",
                "query": clean_query,
                "count": len(final_results),
                "results_found": len(final_results),
                "formatted_context": formatted_context,
                "results": final_results
            }

        except Exception as e:
            logger.error(f"[KnowledgeBase] Search failed for query '{clean_query}': {e}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e),
                "query": clean_query,
                "count": 0,
                "results_found": 0,
                "results": []
            }
        finally:
            if should_close:
                local_db.close()

    def get_relevant_knowledge_context(
        self,
        query: str,
        max_chunks: int = 2,
        db: Optional[Session] = None
    ) -> Optional[str]:
        """
        Retrieve formatted relevant knowledge base context for system prompt injection.
        Only returns context if high-confidence relevant passages exist in local documents.
        Zero fake success: never hallucinates or invents document content.
        """
        if not query or not query.strip():
            return None

        local_db = db or SessionLocal()
        should_close = db is None
        try:
            doc_count = local_db.query(KnowledgeDocument).filter(KnowledgeDocument.status == "READY").count()
            if doc_count == 0:
                return None
        finally:
            if should_close:
                local_db.close()

        search_res = self.search_knowledge(query=query, max_results=max_chunks, db=db)
        if search_res.get("status") == "success" and search_res.get("results"):
            formatted_chunks = []
            for item in search_res["results"]:
                doc_name = item.get("document_name", "Unknown Document")
                passage = (item.get("passage") or "").strip()
                if passage:
                    formatted_chunks.append(f"Source Document: [{doc_name}]\nRelevant Passage:\n\"{passage}\"")
            if formatted_chunks:
                return "\n\n---\n\n".join(formatted_chunks)
        return None

    # =========================================================================
    # Deletion & Management
    # =========================================================================

    def delete_document(self, doc_id: str, db: Optional[Session] = None) -> bool:
        """
        Safely delete a document, its database metadata, indexed chunks,
        and its local file from disk.
        """
        local_db = db or SessionLocal()
        should_close = db is None

        try:
            doc = local_db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
            if not doc:
                return False

            # Delete file on disk
            file_path = Path(doc.file_path).resolve()
            if str(file_path).startswith(str(self.storage_dir)) and file_path.is_file():
                try:
                    file_path.unlink()
                except Exception as del_err:
                    logger.warning(f"[KnowledgeBase] Could not unlink file {file_path}: {del_err}")

            # Delete from FTS5 index
            try:
                with engine.connect() as conn:
                    conn.execute(text("DELETE FROM knowledge_fts WHERE document_id = :doc_id"), {"doc_id": doc_id})
                    conn.commit()
            except Exception as fts_del_err:
                logger.warning(f"[KnowledgeBase] Could not delete from FTS table: {fts_del_err}")

            # Delete from DB (cascades to chunks)
            local_db.delete(doc)
            local_db.commit()
            logger.info(f"[KnowledgeBase] Document {doc_id} successfully deleted.")
            return True

        except Exception as e:
            logger.error(f"[KnowledgeBase] Failed to delete document {doc_id}: {e}", exc_info=True)
            local_db.rollback()
            return False
        finally:
            if should_close:
                local_db.close()

    def list_documents(self, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """List all indexed local documents with metadata."""
        local_db = db or SessionLocal()
        should_close = db is None
        try:
            docs = local_db.query(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()).all()
            return [doc.to_dict() for doc in docs]
        finally:
            if should_close:
                local_db.close()

    def get_document(self, doc_id: str, db: Optional[Session] = None) -> Optional[Dict[str, Any]]:
        """Retrieve metadata and status for a specific document."""
        local_db = db or SessionLocal()
        should_close = db is None
        try:
            doc = local_db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
            return doc.to_dict() if doc else None
        finally:
            if should_close:
                local_db.close()


# Global singleton instance for local knowledge base operations
knowledge_service = KnowledgeBaseService()
