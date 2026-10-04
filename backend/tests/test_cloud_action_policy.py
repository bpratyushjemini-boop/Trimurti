"""
NARAD Test Suite — Cloud Action Policy & Sandbox Permissions Verification.
Validates:
1. In CLOUD mode, ActionPolicy initializes successfully without PermissionError.
2. In CLOUD mode, sandbox_dir resolves to a writable temporary directory (/tmp/narad).
3. CLOUD initialization makes zero attempts to create or touch /backend.
4. Existing LOCAL/SELF_HOSTED behavior remains intact.
5. Path sandboxing security assertions (blocking sensitive paths) remain fully enforced.
"""

import os
import sys
import tempfile
import pytest
from unittest.mock import patch

from app.services.action_policy import ActionPolicy


def test_cloud_action_policy_initializes_successfully_in_tmp(monkeypatch):
    """
    In CLOUD mode, ActionPolicy must default to a writable directory in /tmp
    and never attempt to access or create /backend.
    """
    monkeypatch.setenv("ENVIRONMENT", "CLOUD")
    from app.core.config import settings
    assert settings.is_cloud is True

    policy = ActionPolicy()
    
    # Must resolve to a writable temporary path
    assert policy.sandbox_dir in ("/tmp/narad", "/private/tmp/narad") or "tmp" in policy.sandbox_dir
    assert not policy.sandbox_dir.startswith("/backend")
    assert os.path.exists(policy.sandbox_dir)
    assert os.path.isdir(policy.sandbox_dir)

    # Prove sandbox directory is actually writable
    test_probe_file = os.path.join(policy.sandbox_dir, "cloud_probe.txt")
    try:
        with open(test_probe_file, "w", encoding="utf-8") as f:
            f.write("probe_ok")
        with open(test_probe_file, "r", encoding="utf-8") as f:
            assert f.read() == "probe_ok"
    finally:
        if os.path.exists(test_probe_file):
            os.remove(test_probe_file)


def test_cloud_action_policy_never_attempts_to_create_backend(monkeypatch):
    """
    Verify that in CLOUD mode, os.makedirs is never invoked targeting /backend.
    """
    monkeypatch.setenv("ENVIRONMENT", "CLOUD")
    real_makedirs = os.makedirs
    created_paths = []

    def tracking_makedirs(path, *args, **kwargs):
        created_paths.append(str(path))
        return real_makedirs(path, *args, **kwargs)

    with patch("os.makedirs", side_effect=tracking_makedirs):
        policy = ActionPolicy()

    # Verify no attempt to create /backend or /backend/data/sandbox
    for p in created_paths:
        assert not p.startswith("/backend"), f"Violation: os.makedirs attempted to create '{p}'!"
    
    assert any("/tmp" in p for p in created_paths or [policy.sandbox_dir])


def test_local_action_policy_preserves_local_behavior(monkeypatch):
    """
    In LOCAL mode, ActionPolicy must preserve project repository workspace
    and backend/data/sandbox layout.
    """
    monkeypatch.setenv("ENVIRONMENT", "LOCAL")
    from app.core.config import settings
    assert settings.is_cloud is False

    policy = ActionPolicy()
    assert os.path.isdir(policy.workspace_root)
    assert policy.sandbox_dir.endswith(os.path.join("data", "sandbox"))
    assert os.path.exists(policy.sandbox_dir)


def test_cloud_action_policy_security_sandboxing_intact(monkeypatch):
    """
    Sandboxing security rules must remain strictly enforced in CLOUD mode.
    """
    monkeypatch.setenv("ENVIRONMENT", "CLOUD")
    policy = ActionPolicy()

    # Sensitive paths are blocked
    is_safe, _, err = policy.validate_path_sandbox("/etc/passwd")
    assert is_safe is False

    is_safe, _, err = policy.validate_path_sandbox("~/.ssh/id_rsa")
    assert is_safe is False

    is_safe, _, err = policy.validate_path_sandbox("/app/.env")
    assert is_safe is False

    # Valid sandbox path is allowed
    safe_path = os.path.join(policy.sandbox_dir, "working_doc.txt")
    is_safe, canonical, err = policy.validate_path_sandbox(safe_path)
    assert is_safe is True
    assert canonical == os.path.realpath(safe_path)
