"""Shared clients for the Option C prototype execution.

Two Directus instances:
- HOSTED: https://directus-production-3460.up.railway.app (audit rows only)
- LOCAL:  http://localhost:8055 (prototype schema + seed data + Flows)
"""
from __future__ import annotations
import sys
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve()
PROD_ROOT = HERE.parent.parent.parent  # .../Production
sys.path.insert(0, str(PROD_ROOT / "tools"))

# Load directus.py directly for this archived prototype's historical client.
def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod

_directus_path = PROD_ROOT / "tools" / "credentials_lib" / "directus.py"
if _directus_path.exists():
    _mod = _load("_option_c_directus", _directus_path)
    DirectusClient = _mod.DirectusClient
    DirectusError = _mod.DirectusError
else:
    from credentials_lib.directus import DirectusClient, DirectusError  # type: ignore

HOSTED_URL = "https://directus-production-3460.up.railway.app"
HOSTED_EMAIL = "kimhyla11@gmail.com"
HOSTED_PASSWORD = "directus11$"

LOCAL_URL = "http://localhost:8055"
LOCAL_EMAIL = "kim@mindfulnest.dev"
LOCAL_PASSWORD = "local-prototype"

TASK_ID = "option-c-prototype-exec-20260417"
PREFLIGHT_ID = 48
ORIGINAL_PREFLIGHT_ID = 47
LD_ID = 204


def hosted() -> DirectusClient:
    c = DirectusClient(HOSTED_URL, HOSTED_EMAIL, HOSTED_PASSWORD)
    c.authenticate()
    return c


def local() -> DirectusClient:
    c = DirectusClient(LOCAL_URL, LOCAL_EMAIL, LOCAL_PASSWORD)
    c.authenticate()
    return c
