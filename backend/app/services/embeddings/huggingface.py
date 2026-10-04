"""
NARAD V7.1 — Local Hugging Face Embedding Provider.
Uses Hugging Face Transformers with local model caching to generate dense text embeddings.
Runs on Apple Silicon MPS or CPU using sentence-transformers/all-MiniLM-L6-v2 (384-d, ~80MB).
"""

import time
import logging
from typing import List, Dict, Any, Optional
import torch

from app.services.embeddings.base import BaseEmbeddingProvider
from app.services.local_ai.cache import hf_cache_manager
from app.core.config import settings

logger = logging.getLogger("narad.embeddings.huggingface")

DEFAULT_EMBEDDING_MODEL = getattr(settings, "HUGGINGFACE_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


class LocalHuggingFaceEmbeddingProvider(BaseEmbeddingProvider):
    """
    On-device Hugging Face embedding provider for local Knowledge Base semantic retrieval.
    """

    def __init__(self, model_name: Optional[str] = None):
        self._model_name = model_name or DEFAULT_EMBEDDING_MODEL
        self._dimension = 384
        self._model = None
        self._tokenizer = None
        self._is_loaded = False
        self._mps_available = torch.backends.mps.is_available()
        self._device = "mps" if self._mps_available else "cpu"
        self._load_time_ms = 0
        self._last_inference_ms = 0
        self._last_error: Optional[str] = None

    @property
    def provider_id(self) -> str:
        return "huggingface"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def is_available(self) -> bool:
        return self._is_loaded and self._model is not None

    def get_status(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_id,
            "model": self._model_name,
            "dimension": self._dimension,
            "device": self._device.upper(),
            "mps_available": self._mps_available,
            "ready": self.is_available(),
            "cached": hf_cache_manager.is_model_cached(self._model_name),
            "load_time_ms": self._load_time_ms,
            "last_inference_ms": self._last_inference_ms,
            "last_error": self._last_error,
        }

    def load_model(self) -> bool:
        """Load tokenizer and model into memory on the target hardware device."""
        if self._is_loaded:
            return True

        t0 = time.perf_counter()
        try:
            from transformers import AutoModel, AutoTokenizer

            was_cached = hf_cache_manager.is_model_cached(self._model_name)
            logger.info("Loading embedding model '%s' on %s (cached: %s)...", self._model_name, self._device, was_cached)

            self._tokenizer = AutoTokenizer.from_pretrained(
                self._model_name,
                cache_dir=hf_cache_manager.get_cache_dir(),
                local_files_only=was_cached
            )
            self._model = AutoModel.from_pretrained(
                self._model_name,
                cache_dir=hf_cache_manager.get_cache_dir(),
                local_files_only=was_cached
            )
            self._model.to(self._device)
            self._model.eval()

            self._load_time_ms = int((time.perf_counter() - t0) * 1000)
            self._is_loaded = True
            self._last_error = None
            logger.info("Embedding model '%s' loaded in %d ms on %s.", self._model_name, self._load_time_ms, self._device.upper())
            return True

        except Exception as e:
            # Fallback to CPU if MPS encountered an unexpected issue
            if self._device == "mps":
                logger.warning("MPS embedding load failed (%s); falling back to CPU.", e)
                try:
                    self._device = "cpu"
                    self._model = AutoModel.from_pretrained(
                        self._model_name,
                        cache_dir=hf_cache_manager.get_cache_dir()
                    )
                    self._model.to("cpu")
                    self._model.eval()
                    self._load_time_ms = int((time.perf_counter() - t0) * 1000)
                    self._is_loaded = True
                    self._last_error = None
                    return True
                except Exception as cpu_err:
                    self._last_error = str(cpu_err)
                    self._is_loaded = False
                    return False

            self._last_error = str(e)
            self._is_loaded = False
            logger.error("Failed to load embedding model '%s': %s", self._model_name, e)
            return False

    def embed_query(self, text: str) -> List[float]:
        """Generate normalized dense embedding for a single text query."""
        results = self.embed_documents([text])
        return results[0] if results else []

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate normalized dense embeddings for a batch of texts."""
        if not texts:
            return []

        if not self._is_loaded:
            if not self.load_model():
                raise RuntimeError(f"Embedding model '{self._model_name}' could not be loaded: {self._last_error}")

        t0 = time.perf_counter()
        try:
            inputs = self._tokenizer(
                texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt"
            ).to(self._device)

            with torch.no_grad():
                outputs = self._model(**inputs)
                # Mean pooling
                attention_mask = inputs["attention_mask"].unsqueeze(-1)
                embeddings = torch.sum(outputs.last_hidden_state * attention_mask, dim=1) / torch.clamp(
                    attention_mask.sum(dim=1), min=1e-9
                )
                # L2 normalization for direct cosine similarity via dot product
                embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

            self._last_inference_ms = int((time.perf_counter() - t0) * 1000)
            return embeddings.cpu().tolist()

        except Exception as e:
            self._last_error = str(e)
            logger.error("Failed to compute embeddings: %s", e)
            raise
