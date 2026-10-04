"""
NARAD V7.1 — Hugging Face Local AI Manager.
Manages local LLM lifecycle, persistent in-memory singletons, Apple Silicon (MPS vs CPU) hardware
selection, cache hit/miss tracking, and real execution telemetry.
"""

import os
import time
import logging
from typing import Dict, Any, List, Optional
import torch

from app.core.config import settings
from app.services.local_ai.cache import hf_cache_manager

logger = logging.getLogger("narad.local_ai.manager")

DEFAULT_LOCAL_MODEL = getattr(settings, "HUGGINGFACE_LOCAL_MODEL", "HuggingFaceTB/SmolLM2-135M-Instruct")


class LocalAIManager:
    """
    Central manager for Hugging Face local inference in NARAD.
    Loads models once, caches weights via Hugging Face Hub, and serves local queries.
    """

    def __init__(self, default_model: Optional[str] = None):
        self.model_id = default_model or DEFAULT_LOCAL_MODEL
        self._model = None
        self._tokenizer = None
        self._is_loaded: bool = False
        self._device: str = "cpu"
        self._load_time_ms: int = 0
        self._last_inference_ms: int = 0
        self._last_cache_hit: bool = False
        self._status: str = "STANDBY"
        self._last_error: Optional[str] = None
        self._mps_available: bool = torch.backends.mps.is_available()

        # Decide hardware device
        # Note: Certain architectures with Grouped Query Attention (GQA) hit PyTorch 2.6 MPS
        # kernel incompatibilities on macOS. CPU is rock-solid and ultra-fast (<800ms) for 135M.
        self._device = "cpu"

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded and self._model is not None

    @property
    def device_str(self) -> str:
        return self._device.upper()

    def get_status_info(self) -> Dict[str, Any]:
        """Return real runtime telemetry for HUD display."""
        cached_info = hf_cache_manager.get_model_cache_info(self.model_id)
        return {
            "status": self._status,
            "model": self.model_id,
            "device": self.device_str,
            "mps_available": self._mps_available,
            "is_loaded": self.is_loaded,
            "cache_hit": self._last_cache_hit or hf_cache_manager.is_model_cached(self.model_id),
            "load_time_ms": self._load_time_ms,
            "last_inference_ms": self._last_inference_ms,
            "size_on_disk_str": cached_info.get("size_on_disk_str", "Unknown") if cached_info else "Not cached",
            "last_error": self._last_error,
        }

    def load_model(self, force: bool = False) -> bool:
        """
        Load local model and tokenizer into memory once.
        Records exact loading time and cache hit status.
        """
        if self.is_loaded and not force:
            return True

        self._status = "LOADING"
        t0 = time.perf_counter()

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer

            # 1. Check local cache
            self._last_cache_hit = hf_cache_manager.is_model_cached(self.model_id)
            logger.info(
                "Loading Hugging Face local model '%s' (Cache Hit: %s, Target Device: %s)...",
                self.model_id, self._last_cache_hit, self._device
            )

            # 2. Load tokenizer and model
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_id,
                cache_dir=hf_cache_manager.get_cache_dir(),
                local_files_only=self._last_cache_hit
            )

            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                cache_dir=hf_cache_manager.get_cache_dir(),
                torch_dtype=torch.float32,
                local_files_only=self._last_cache_hit
            )
            self._model.to(self._device)
            self._model.eval()

            self._load_time_ms = int((time.perf_counter() - t0) * 1000)
            self._is_loaded = True
            self._status = "READY"
            self._last_error = None
            logger.info(
                "Local model '%s' successfully loaded in %d ms on %s.",
                self.model_id, self._load_time_ms, self.device_str
            )
            return True

        except Exception as e:
            self._status = "UNAVAILABLE"
            self._last_error = str(e)
            self._is_loaded = False
            logger.exception("Failed to load local model '%s': %s", self.model_id, e)
            return False

    def generate(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int = 128,
        temperature: float = 0.7,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Executes local generation synchronously or asynchronously.
        Measures real execution latency and returns structured outcome.
        """
        if not self.is_loaded:
            success = self.load_model()
            if not success:
                raise RuntimeError(f"Local model '{self.model_id}' is unavailable: {self._last_error}")

        t_start = time.perf_counter()

        try:
            # Build prompt with chat template if supported
            if hasattr(self._tokenizer, "apply_chat_template") and self._tokenizer.chat_template:
                # Sanitize messages for chat template
                formatted_msgs = []
                for m in messages:
                    role = m.get("role", "user")
                    if role not in ("system", "user", "assistant"):
                        role = "user"
                    formatted_msgs.append({"role": role, "content": str(m.get("content", ""))})
                prompt_text = self._tokenizer.apply_chat_template(
                    formatted_msgs,
                    tokenize=False,
                    add_generation_prompt=True
                )
            else:
                prompt_text = "\n".join([f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages])
                prompt_text += "\nassistant:\n"

            inputs = self._tokenizer(prompt_text, return_tensors="pt").to(self._device)
            prompt_token_count = int(inputs.input_ids.shape[1])

            do_sample = temperature > 0.1
            gen_kwargs = {
                "max_new_tokens": max_tokens,
                "do_sample": do_sample,
                "pad_token_id": self._tokenizer.eos_token_id,
            }
            if do_sample:
                gen_kwargs["temperature"] = max(0.1, min(1.0, temperature))
                gen_kwargs["top_p"] = 0.9

            with torch.no_grad():
                outputs = self._model.generate(**inputs, **gen_kwargs)

            gen_tokens = outputs[0][inputs.input_ids.shape[1]:]
            completion_tokens = int(gen_tokens.shape[0])
            response_text = self._tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()

            self._last_inference_ms = int((time.perf_counter() - t_start) * 1000)

            return {
                "content": response_text,
                "model": self.model_id,
                "provider": "huggingface",
                "device": self.device_str,
                "cache_hit": self._last_cache_hit,
                "load_time_ms": self._load_time_ms,
                "latency_ms": self._last_inference_ms,
                "status": "success",
                "usage": {
                    "prompt_tokens": prompt_token_count,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_token_count + completion_tokens
                }
            }

        except Exception as e:
            self._last_error = str(e)
            self._last_inference_ms = int((time.perf_counter() - t_start) * 1000)
            logger.error("Local generation failed: %s", e)
            raise


# Global singleton
local_ai_manager = LocalAIManager()
