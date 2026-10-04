"""
NARAD V7.1 — Embeddings Subsystem.
"""

from app.services.embeddings.base import BaseEmbeddingProvider
from app.services.embeddings.huggingface import LocalHuggingFaceEmbeddingProvider
from app.services.embeddings.manager import embedding_manager, cosine_similarity

__all__ = [
    "BaseEmbeddingProvider",
    "LocalHuggingFaceEmbeddingProvider",
    "embedding_manager",
    "cosine_similarity"
]
