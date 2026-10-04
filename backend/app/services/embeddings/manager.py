"""
NARAD V7.1 — Embedding Manager & Vector Similarity Dispatcher.
Coordinates embedding providers, fallback lexical mechanisms, and cosine similarity re-ranking.
"""

import math
import logging
from typing import List, Dict, Any, Optional

from app.services.embeddings.base import BaseEmbeddingProvider
from app.services.embeddings.huggingface import LocalHuggingFaceEmbeddingProvider

logger = logging.getLogger("narad.embeddings.manager")


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two normalized vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    return float(dot)


class EmbeddingManager:
    """Central registry and coordinator for Knowledge Base embeddings."""

    def __init__(self):
        self.local_provider = LocalHuggingFaceEmbeddingProvider()
        self._active_provider: BaseEmbeddingProvider = self.local_provider

    @property
    def active_provider(self) -> BaseEmbeddingProvider:
        return self._active_provider

    def is_ready(self) -> bool:
        return self._active_provider.is_available()

    def get_status(self) -> Dict[str, Any]:
        return {
            "active_provider": self._active_provider.provider_id,
            "provider_status": self._active_provider.get_status(),
            "ready": self._active_provider.is_available()
        }

    def embed_query(self, query: str) -> Optional[List[float]]:
        """Safely compute query embedding, returning None on failure."""
        try:
            return self._active_provider.embed_query(query)
        except Exception as e:
            logger.warning("Embedding query computation failed: %s", e)
            return None

    def rerank_chunks(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Re-ranks a list of document chunks using cosine similarity if embeddings are available.
        Falls back to preserving existing order if embeddings cannot be computed.
        """
        if not chunks or len(chunks) <= 1:
            return chunks[:top_k]

        try:
            query_vec = self.embed_query(query)
            if not query_vec:
                return chunks[:top_k]

            texts = [c.get("content", "") for c in chunks]
            chunk_vecs = self._active_provider.embed_documents(texts)

            scored = []
            for i, chunk in enumerate(chunks):
                sim = cosine_similarity(query_vec, chunk_vecs[i])
                # Combine embedding similarity with lexical score
                combined = dict(chunk)
                combined["semantic_score"] = round(sim, 4)
                scored.append(combined)

            scored.sort(key=lambda x: x.get("semantic_score", 0.0), reverse=True)
            return scored[:top_k]

        except Exception as e:
            logger.warning("Embedding re-ranking encountered an issue (%s); preserving lexical order.", e)
            return chunks[:top_k]


# Global singleton
embedding_manager = EmbeddingManager()
