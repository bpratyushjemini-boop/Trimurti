"""
NARAD — Cloud Route Registration Regression Tests.

Regression for the Render outage where every URL returned a plain-text 404 with
`x-render-routing: no-server`. Root cause: `CORS_ORIGINS` was declared as `List[str]`,
and pydantic-settings JSON-decodes complex env values BEFORE field validators run.
The comma-separated value set in render.yaml therefore raised `SettingsError` while
importing `app.core.config`, so uvicorn crashed before binding a port and Render had
no server to route to.

The existing CORS test passed because it supplied CORS_ORIGINS as a constructor
kwarg (which bypasses the env source). These tests exercise the real env path:
  1. Settings() reading CORS_ORIGINS from the process environment.
  2. Importing `app.main` in a fresh interpreter with the exact env vars declared in
     render.yaml (CLOUD mode), then asserting the route table and auth behaviour.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
RENDER_YAML = BACKEND_DIR.parent / "render.yaml"

TEST_API_KEY = "route-regression-test-key"
EXPECTED_CLOUD_ROUTES = ["/", "/health", "/ready", "/openapi.json", "/api/runtime/truth"]


def _render_yaml_literal_env() -> dict:
    """Extract literal `- key: X / value: Y` env vars from render.yaml (no YAML dependency)."""
    text = RENDER_YAML.read_text(encoding="utf-8")
    env = {}
    for m in re.finditer(r"-\s*key:\s*(\S+)\s*\n\s*value:\s*(.+)", text):
        key, raw = m.group(1).strip(), m.group(2).strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
            raw = raw[1:-1]
        env[key] = raw
    return env


def _cloud_env(tmp_path: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env.update(_render_yaml_literal_env())
    # Render injects these at runtime (fromDatabase / generateValue); use local stand-ins.
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'cloud_routes.db'}"
    env["NARAD_API_KEY"] = TEST_API_KEY
    env["PYTHONPATH"] = str(BACKEND_DIR)
    return env


_PROBE_SCRIPT = r"""
import json
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

key = {key!r}
client = TestClient(app)
paths = {paths!r}
out = {{
    "environment": settings.ENVIRONMENT,
    "runtime_mode": settings.NARAD_RUNTIME_MODE,
    "cors_origins": settings.CORS_ORIGINS,
    "routes": sorted(
        {{getattr(r, "path", "") for r in app.routes if getattr(r, "path", "")}}
        | set(app.openapi().get("paths", {{}}).keys())
    ),
    "status_no_auth": {{p: client.get(p).status_code for p in paths}},
    "truth_wrong_key": client.get("/api/runtime/truth", headers={{"Authorization": "Bearer wrong"}}).status_code,
    "truth_valid_bearer": client.get("/api/runtime/truth", headers={{"Authorization": "Bearer " + key}}).status_code,
    "truth_valid_x_key": client.get("/api/runtime/truth", headers={{"X-Narad-Key": key}}).status_code,
}}
print("PROBE_RESULT=" + json.dumps(out))
"""


@pytest.fixture(scope="module")
def cloud_probe(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("cloud_routes")
    script = _PROBE_SCRIPT.format(key=TEST_API_KEY, paths=EXPECTED_CLOUD_ROUTES)
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(BACKEND_DIR),  # render.yaml rootDir: backend
        env=_cloud_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, (
        "app.main failed to import/start with render.yaml CLOUD env — Render would have no "
        f"running server.\nSTDERR:\n{proc.stderr[-4000:]}"
    )
    line = next((l for l in proc.stdout.splitlines() if l.startswith("PROBE_RESULT=")), None)
    assert line, f"Probe produced no result.\nSTDOUT:\n{proc.stdout[-4000:]}"
    return json.loads(line[len("PROBE_RESULT="):])


# ---------------------------------------------------------------------------
# 1. Env-source parsing (the exact failure mode)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://narad.local,http://localhost:5173", ["https://narad.local", "http://localhost:5173"]),
        (" https://a.app , https://b.app ,", ["https://a.app", "https://b.app"]),
        ("https://single.app", ["https://single.app"]),
        ('["https://json.app","http://localhost:5173"]', ["https://json.app", "http://localhost:5173"]),
    ],
)
def test_cors_origins_from_environment_variable(monkeypatch, raw, expected):
    from app.core.config import Settings

    monkeypatch.setenv("CORS_ORIGINS", raw)
    s = Settings()
    assert s.CORS_ORIGINS == expected
    assert isinstance(s.CORS_ORIGINS, list)


def test_render_yaml_declares_expected_startup():
    text = RENDER_YAML.read_text(encoding="utf-8")
    assert re.search(r"rootDir:\s*backend", text)
    assert "uvicorn app.main:app" in text
    assert re.search(r"healthCheckPath:\s*/health", text)
    env = _render_yaml_literal_env()
    assert env.get("ENVIRONMENT") == "CLOUD"
    assert "CORS_ORIGINS" in env


# ---------------------------------------------------------------------------
# 2. Route registration in CLOUD mode (fresh interpreter, render.yaml env)
# ---------------------------------------------------------------------------

def test_app_boots_in_cloud_mode(cloud_probe):
    assert cloud_probe["environment"] == "CLOUD"
    assert cloud_probe["runtime_mode"] == "cloud"
    expected_cors = [o.strip() for o in _render_yaml_literal_env()["CORS_ORIGINS"].split(",") if o.strip()]
    assert cloud_probe["cors_origins"] == expected_cors
    assert "http://localhost:5173" in cloud_probe["cors_origins"]


@pytest.mark.parametrize("path", EXPECTED_CLOUD_ROUTES)
def test_expected_route_registered_in_cloud_mode(cloud_probe, path):
    assert path in cloud_probe["routes"], f"{path} missing from app.routes in CLOUD mode"


@pytest.mark.parametrize("path", ["/", "/health", "/ready", "/openapi.json"])
def test_public_probe_routes_respond_without_auth(cloud_probe, path):
    assert cloud_probe["status_no_auth"][path] == 200


# ---------------------------------------------------------------------------
# 3. /api/runtime/truth must exist AND stay protected
# ---------------------------------------------------------------------------

def test_runtime_truth_requires_auth_not_404(cloud_probe):
    status = cloud_probe["status_no_auth"]["/api/runtime/truth"]
    assert status != 404, "/api/runtime/truth is not registered"
    assert status in (401, 403)


def test_runtime_truth_rejects_wrong_key(cloud_probe):
    assert cloud_probe["truth_wrong_key"] in (401, 403)


def test_runtime_truth_accepts_valid_key(cloud_probe):
    assert cloud_probe["truth_valid_bearer"] == 200
    assert cloud_probe["truth_valid_x_key"] == 200
