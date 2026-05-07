"""Test DirectusAdminClient cross-platform creds resolution.

Test 1: happy path — creds resolved from Windows Dropbox path.
Test 2: graceful degradation — file renamed, expect WARNING + RuntimeError.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure we can import lib.directus_admin_client
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.directus_admin_client import DirectusAdminClient  # noqa: E402


def test_happy_path() -> bool:
    print("[test 1] DirectusAdminClient() with creds file present...")
    # Scrub env so file path is exercised.
    old_email = os.environ.pop("DIRECTUS_EMAIL", None)
    old_pw = os.environ.pop("DIRECTUS_PASSWORD", None)
    try:
        client = DirectusAdminClient()
        fields = client.fields("prod_activity_log")
        assert isinstance(fields, list) and len(fields) > 0, "expected non-empty schema"
        print(f"  OK — got {len(fields)} field definitions for prod_activity_log.")
        return True
    finally:
        if old_email:
            os.environ["DIRECTUS_EMAIL"] = old_email
        if old_pw:
            os.environ["DIRECTUS_PASSWORD"] = old_pw


def test_graceful_degradation() -> bool:
    print("[test 2] DirectusAdminClient() with creds file temporarily renamed...")
    # Scrub env.
    old_email = os.environ.pop("DIRECTUS_EMAIL", None)
    old_pw = os.environ.pop("DIRECTUS_PASSWORD", None)

    # Find the file at the Windows path and rename it out of the way.
    keys_path = os.path.expanduser(
        "~/Dropbox/Claude Mindfulnest Project Files/Production/API_KEYS_MASTER.md"
    )
    backup = keys_path + ".offline_test_backup"
    assert os.path.exists(keys_path), f"precondition failed: {keys_path} missing"
    shutil.move(keys_path, backup)
    try:
        try:
            DirectusAdminClient()
            print("  FAIL — expected RuntimeError but got a client.")
            return False
        except RuntimeError as e:
            msg = str(e)
            assert "credentials not found" in msg.lower(), f"unexpected msg: {msg}"
            print(f"  OK — graceful RuntimeError: {msg}")
            return True
    finally:
        shutil.move(backup, keys_path)
        if old_email:
            os.environ["DIRECTUS_EMAIL"] = old_email
        if old_pw:
            os.environ["DIRECTUS_PASSWORD"] = old_pw


if __name__ == "__main__":
    r1 = test_happy_path()
    r2 = test_graceful_degradation()
    print()
    print(f"Test 1 (happy path): {'PASS' if r1 else 'FAIL'}")
    print(f"Test 2 (degradation): {'PASS' if r2 else 'FAIL'}")
    sys.exit(0 if (r1 and r2) else 1)
