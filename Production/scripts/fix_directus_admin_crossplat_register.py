"""One-shot: run tests + register LD + log activity for the cross-platform fix.

Executes:
  1. Happy-path cred resolution test
  2. Graceful-degradation test (file temporarily renamed)
  3. POST prod_locked_decisions with DIRECTUS_ADMIN_CLIENT_CROSS_PLATFORM_PATH_V1
  4. POST prod_activity_log with before/after line counts, test results, LD id

Prints a machine-readable summary at end.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.directus_admin_client import DirectusAdminClient  # noqa: E402
from lib.directus import post_item_verified  # noqa: E402


def test_happy_path() -> tuple[bool, str]:
    old_e = os.environ.pop("DIRECTUS_EMAIL", None)
    old_p = os.environ.pop("DIRECTUS_PASSWORD", None)
    try:
        client = DirectusAdminClient()
        fields = client.fields("prod_activity_log")
        if not (isinstance(fields, list) and len(fields) > 0):
            return False, f"expected non-empty schema, got {fields!r}"
        return True, f"got {len(fields)} field defs for prod_activity_log"
    except Exception as e:
        return False, f"exception: {e!r}"
    finally:
        if old_e:
            os.environ["DIRECTUS_EMAIL"] = old_e
        if old_p:
            os.environ["DIRECTUS_PASSWORD"] = old_p


def test_graceful_degradation() -> tuple[bool, str]:
    old_e = os.environ.pop("DIRECTUS_EMAIL", None)
    old_p = os.environ.pop("DIRECTUS_PASSWORD", None)
    keys_path = os.path.expanduser(
        "~/Dropbox/Claude Mindfulnest Project Files/Production/API_KEYS_MASTER.md"
    )
    backup = keys_path + ".offline_test_backup"
    if not os.path.exists(keys_path):
        return False, f"precondition failed: {keys_path} not present"
    shutil.move(keys_path, backup)
    try:
        try:
            DirectusAdminClient()
            return False, "expected RuntimeError but got a client"
        except RuntimeError as e:
            msg = str(e)
            if "credentials not found" not in msg.lower():
                return False, f"unexpected err msg: {msg}"
            return True, f"RuntimeError raised: {msg}"
    finally:
        shutil.move(backup, keys_path)
        if old_e:
            os.environ["DIRECTUS_EMAIL"] = old_e
        if old_p:
            os.environ["DIRECTUS_PASSWORD"] = old_p


def main() -> int:
    summary: dict = {}

    # Tests
    ok1, msg1 = test_happy_path()
    ok2, msg2 = test_graceful_degradation()
    summary["test_1_happy_path"] = {"pass": ok1, "msg": msg1}
    summary["test_2_degradation"] = {"pass": ok2, "msg": msg2}

    if not (ok1 and ok2):
        print(json.dumps(summary, indent=2))
        print("TESTS FAILED — aborting Directus writes.", file=sys.stderr)
        return 1

    today = _dt.date.today().isoformat()

    ld_payload = {
        "decision_key": "DIRECTUS_ADMIN_CLIENT_CROSS_PLATFORM_PATH_V1",
        "decision_name": "DirectusAdminClient: cross-platform API_KEYS_MASTER.md path resolution",
        "decision_text": (
            "Bug: Production/lib/directus_admin_client.py _read_from_keys_file() "
            "hardcoded a Mac-only path (~/Library/CloudStorage/Dropbox/...) so on "
            "Kim's Windows work PC the credentials file (which is at ~/Dropbox/...) "
            "was never found. Silent fallback returned None and mn-context SAVE mode "
            "queued offline instead of writing live. Fix: introduce "
            "_candidate_keys_paths() which branches on sys.platform and always tries "
            "(a) Mac CloudStorage path, (b) generic ~/Dropbox path, (c) project-relative "
            "Production/API_KEYS_MASTER.md — in platform-preferred order. When no "
            "candidate exists, print a WARNING to stderr naming all paths tried; do NOT "
            "raise (silent offline queuing remains correct per feedback_desktop_no_hooks). "
            "Doppler-first behavior intact (env vars tried first). _parse logic untouched. "
            "Tests run (happy path + graceful degradation) and both pass."
        ),
        "source_document": "Production/lib/directus_admin_client.py",
        "task_category": "infrastructure",
        "severity": "MEDIUM",
        "date_locked": today,
        "status": "active",
    }

    ld_row = post_item_verified("prod_locked_decisions", ld_payload)
    summary["ld_id"] = ld_row.get("id")
    summary["ld_decision_key"] = ld_row.get("decision_key")

    act_payload = {
        "action": "directus_admin_client_cross_platform_path_fix",
        "details": json.dumps({
            "file": "Production/lib/directus_admin_client.py",
            "before_line_count": 173,
            "after_line_count_approx": 211,
            "change_summary": (
                "Replaced hardcoded Mac CloudStorage path with _candidate_keys_paths() "
                "that branches on sys.platform and returns Mac/generic/project-relative "
                "candidates. Added WARNING-on-miss via stderr. Added sys import."
            ),
            "tests": {
                "happy_path": msg1,
                "graceful_degradation": msg2,
            },
            "ld_id": ld_row.get("id"),
            "ld_key": "DIRECTUS_ADMIN_CLIENT_CROSS_PLATFORM_PATH_V1",
            "scope_boundaries_honored": [
                "only directus_admin_client.py modified",
                "Doppler-first env-var preference intact",
                "_parse_keys_file logic untouched",
            ],
        }),
    }

    act_row = post_item_verified("prod_activity_log", act_payload)
    summary["activity_log_id"] = act_row.get("id")

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
