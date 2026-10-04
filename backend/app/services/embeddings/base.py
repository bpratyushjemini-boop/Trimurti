"""
NARAD V7.1 — BaseEmbeddingProvider Interface.
Defines provider-agnostic abstraction for vector embeddings in the TRIMURTI Knowledge Base.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class BaseEmbeddingProvider(ABC):
    """Abstract interface for Knowledge Base text embedding providers."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """Generate normalized dense embedding vector for a search query."""
        pass

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate normalized dense embedding vectors for a batch of documents/chunks."""
        pass
