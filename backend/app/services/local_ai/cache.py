"""
NARAD V7.1 — Hugging Face Local Hub Cache Manager.
Handles model cache discovery, snapshot resolution, hit/miss detection, and disk footprint tracking.
Models are cached centrally in ~/.cache/huggingface/hub and loaded locally without redundant downloads.
"""

import os
import tempfile
import logging
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

import huggingface_hub
from huggingface_hub import constants, scan_cache_dir, snapshot_download

logger = logging.getLogger("narad.local_ai.cache")


class HFCacheManager:
    """Manages local model cache inspection and safe snapshot resolution."""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir or constants.HF_HUB_CACHE
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
        except (PermissionError, OSError):
            self.cache_dir = os.path.join(tempfile.gettempdir(), "narad", "hf_cache")
            os.makedirs(self.cache_dir, exist_ok=True)

    def get_cache_dir(self) -> str:
        return self.cache_dir

    def is_model_cached(self, repo_id: str) -> bool:
        """
        Check whether all required weights or snapshots for repo_id exist in the local cache.
        """
        try:
            report = scan_cache_dir(cache_dir=self.cache_dir)
            for repo in report.repos:
                if repo.repo_id.lower() == repo_id.lower():
                    return True
        except Exception as e:
            logger.warning("Failed to scan HF cache directory: %s", e)

        # Fallback check on directory name convention: models--<org>--<name>
        folder_name = "models--" + repo_id.replace("/", "--")
        expected_path = Path(self.cache_dir) / folder_name
        return expected_path.exists() and any(expected_path.iterdir())

    def get_cached_models(self) -> List[Dict[str, Any]]:
        """
        Return a structured list of all repositories currently cached locally on disk.
        """
        results = []
        try:
            report = scan_cache_dir(cache_dir=self.cache_dir)
            for repo in report.repos:
                results.append({
                    "repo_id": repo.repo_id,
                    "repo_type": repo.repo_type,
                    "size_on_disk": repo.size_on_disk,
                    "size_on_disk_str": repo.size_on_disk_str,
                    "nb_files": repo.nb_files,
                    "last_modified": getattr(repo, "last_modified", None),
                })
        except Exception as e:
            logger.warning("Error scanning cache dir '%s': %s", self.cache_dir, e)

        return results

    def get_model_cache_info(self, repo_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve cache information for a specific repository if available."""
        cached_all = self.get_cached_models()
        for item in cached_all:
            if item["repo_id"].lower() == repo_id.lower():
                return item
        return None

    def ensure_model_cached(
        self,
        repo_id: str,
        revision: Optional[str] = None,
        allow_patterns: Optional[List[str]] = None,
        ignore_patterns: Optional[List[str]] = None
    ) -> Tuple[str, bool]:
        """
        Ensures model weights exist locally.
        Returns:
            (local_path: str, was_cache_hit: bool)
        Raises RuntimeError on download failure.
        """
        was_cached = self.is_model_cached(repo_id)

        try:
            local_path = snapshot_download(
                repo_id=repo_id,
                revision=revision,
                cache_dir=self.cache_dir,
                allow_patterns=allow_patterns,
                ignore_patterns=ignore_patterns,
                local_files_only=was_cached  # Prefer local files if already cached
            )
            return local_path, was_cached
        except Exception as e:
            if was_cached:
                logger.info("Local files only failed for '%s'; retrying online check: %s", repo_id, e)
                try:
                    local_path = snapshot_download(
                        repo_id=repo_id,
                        revision=revision,
                        cache_dir=self.cache_dir,
                        allow_patterns=allow_patterns,
                        ignore_patterns=ignore_patterns,
                    )
                    return local_path, False
                except Exception as net_err:
                    raise RuntimeError(f"Failed to fetch model '{repo_id}' from Hugging Face Hub: {net_err}") from net_err
            raise RuntimeError(f"Failed to fetch model '{repo_id}' from Hugging Face Hub: {e}") from e


# Singleton cache manager
hf_cache_manager = HFCacheManager()
