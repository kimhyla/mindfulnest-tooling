#!/usr/bin/env python3
"""C2c golden tests for `Production/scripts/clean_orphan_beats_v3.py`.

Per spec v2 §2.4 cleanup-script tests + Cursor R3 safety guards:
  1. Dry-run golden: fixture with 1 orphan → correct stdout + no mutation
  2. --apply --event golden: orphan removed, display_order untouched,
     pre-image backup written, prod_activity_log row written
  3. --all rejection without prior scoped run
  4. Legacy-skip: display_order undefined → nothing mutated

Run:
    python3 -m unittest Production.tools.tests.test_clean_orphan_beats_v3 -v
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_THIS = Path(__file__).resolve()
_TOOLS = _THIS.parent.parent
_REPO_ROOT = _TOOLS.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "Production" / "scripts"))
sys.path.insert(0, str(_TOOLS))

# Bypass cross-machine Directus lock — required for atomic_json_write.
os.environ["PRODUCTION_SERVER_SINGLE_MACHINE"] = "1"

import clean_orphan_beats_v3 as cob  # noqa: E402


def _seed_event_state(prod_root: Path, event_id: str, partition_state: dict) -> Path:
    """Create Production/Event_<id>/production_state.json with given videos shape."""
    event_dir = prod_root / f"Event_{event_id}"
    event_dir.mkdir(parents=True, exist_ok=True)
    state_path = event_dir / "production_state.json"
    state_path.write_text(json.dumps({
        "event_id": f"Event_{event_id}",
        "version": "v3",
        "videos": partition_state,
        "updated_at": "2026-05-01T00:00:00Z",
    }, indent=2), encoding="utf-8")
    return state_path


class CleanOrphanBeatsV3Test(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cob_"))
        self.prod_root = self.tmp / "Production"
        self.prod_root.mkdir()
        # Point the script at our tmp tree.
        os.environ["MINDFULNEST_PRODUCTION_ROOT"] = str(self.prod_root)
        # Override the marker file path so the test's --all rejection
        # path doesn't depend on (or clobber) the user's real marker.
        self._marker_patch = patch.object(
            cob, "MARKER_DIR", self.tmp / ".cache",
        )
        self._marker_patch.start()
        self._marker_file_patch = patch.object(
            cob, "MARKER_FILE", self.tmp / ".cache" / "marker.json",
        )
        self._marker_file_patch.start()
        # Mock try_post_or_queue so prod_activity_log writes don't try
        # to reach the real Directus during tests.
        self.activity_log_writes: list[dict] = []

        def _fake_try_post_or_queue(collection, payload):
            self.activity_log_writes.append({"collection": collection,
                                             "payload": payload})
            return {"id": 99999}

        cob.TRY_POST_OR_QUEUE = _fake_try_post_or_queue

    def tearDown(self):
        self._marker_patch.stop()
        self._marker_file_patch.stop()
        cob.TRY_POST_OR_QUEUE = None
        os.environ.pop("MINDFULNEST_PRODUCTION_ROOT", None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args) -> tuple[int, str, str]:
        """Invoke main() with captured stdout/stderr."""
        out = io.StringIO()
        err = io.StringIO()
        with patch("sys.stdout", out), patch("sys.stderr", err):
            rc = cob.main(list(args))
        return rc, out.getvalue(), err.getvalue()

    # ----- Test 1: Dry-run golden -----
    def test_dry_run_reports_orphan_without_mutating(self):
        state_path = _seed_event_state(
            self.prod_root, "1",
            partition_state={
                "intro": {
                    "video_role": "intro",
                    "beats": {
                        "beat_01": {"text": "kept"},
                        "beat_99": {"text": "orphan that should be reported"},
                    },
                    "display_order": ["beat_01"],
                },
            },
        )
        before = state_path.read_text(encoding="utf-8")

        rc, out, _err = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN", out)
        self.assertIn("Event_1: 1 orphan(s)", out)
        self.assertIn("beat_99", out)
        self.assertIn("orphan that should be reported", out)

        # No mutation: file content unchanged.
        after = state_path.read_text(encoding="utf-8")
        self.assertEqual(before, after, "dry-run mutated state file")

        # No activity log writes in dry-run.
        self.assertEqual(self.activity_log_writes, [])

    # ----- Test 2: --apply --event golden -----
    def test_apply_event_removes_orphan_writes_backup_writes_log(self):
        state_path = _seed_event_state(
            self.prod_root, "2",
            partition_state={
                "intro": {
                    "video_role": "intro",
                    "beats": {
                        "beat_04": {"text": "MindfulNest orphan"},
                    },
                    "display_order": [],
                },
            },
        )

        rc, out, _err = self._run("--apply", "--event", "2")
        self.assertEqual(rc, 0, f"unexpected rc={rc}; stderr={_err!r}")

        # Orphan removed; display_order untouched.
        after = json.loads(state_path.read_text(encoding="utf-8"))
        intro = after["videos"]["intro"]
        self.assertEqual(
            intro["beats"], {},
            "orphan beat_04 not removed post --apply",
        )
        self.assertEqual(
            intro["display_order"], [],
            "display_order should not be modified by cleanup script",
        )

        # Pre-image backup written.
        backup_dir = state_path.parent / ".backups" / "state"
        backups = list(backup_dir.glob("preimage_*_clean_orphan_beats.json"))
        self.assertEqual(len(backups), 1, f"expected 1 backup, got {backups}")
        backup_content = json.loads(backups[0].read_text(encoding="utf-8"))
        self.assertEqual(
            backup_content["videos"]["intro"]["beats"]["beat_04"]["text"],
            "MindfulNest orphan",
            "pre-image backup must contain the orphan beat for forensic recovery",
        )

        # Activity log: ONE row, action="clean_orphan_beats_v3", with full
        # payload preservation per Cursor R3 + Kim 2026-05-05 (forensic).
        self.assertEqual(len(self.activity_log_writes), 1)
        row = self.activity_log_writes[0]
        self.assertEqual(row["collection"], "prod_activity_log")
        payload = row["payload"]
        self.assertEqual(payload["action"], "clean_orphan_beats_v3")
        self.assertEqual(payload["performed_by"], "claude_code_terminal_session")
        details = payload["details"]
        self.assertIn("intro:beat_04", details["removed_beat_ids"])
        # Full beat object preserved (text, etc).
        full = details["removed_beat_payload"][0]
        self.assertEqual(full["beat_id"], "beat_04")
        self.assertEqual(full["payload"]["text"], "MindfulNest orphan")
        self.assertEqual(full["display_order_at_prune"], [])
        self.assertIn("beat_cleanup", details["tags"])
        self.assertIn("DISPLAY_ORDER_STRICT_V1", details["tags"])
        self.assertTrue(details["preimage_backup_path"].endswith(".json"))

        # Marker written so subsequent --all is permitted.
        self.assertTrue(cob.MARKER_FILE.is_file())

        # Stdout summary.
        self.assertIn("APPLIED: 1 orphan(s) removed", out)

    # ----- Test 3: --all rejection without prior scoped marker -----
    def test_all_apply_refused_without_scoped_marker(self):
        # Seed at least one event so there'd be something to apply to.
        _seed_event_state(
            self.prod_root, "1",
            partition_state={
                "intro": {
                    "beats": {"beat_99": {"text": "x"}},
                    "display_order": [],
                },
            },
        )
        # Marker explicitly absent.
        self.assertFalse(cob.MARKER_FILE.is_file())

        rc, _out, err = self._run("--apply", "--all")
        self.assertEqual(rc, 3, f"expected exit 3 ('--all without marker'); got {rc}")
        self.assertIn("--all --apply refused", err)
        self.assertIn(str(cob.MARKER_FILE), err)

        # No mutation, no activity log write.
        self.assertEqual(self.activity_log_writes, [])

    # ----- Test 4: Legacy-skip — display_order undefined or non-list -----
    def test_legacy_skip_when_display_order_absent(self):
        state_path = _seed_event_state(
            self.prod_root, "5",
            partition_state={
                "intro": {
                    "video_role": "intro",
                    "beats": {
                        "beat_01": {"text": "legacy beat"},
                        "beat_99": {"text": "another legacy beat"},
                    },
                    # display_order DELIBERATELY ABSENT.
                },
            },
        )
        before = state_path.read_text(encoding="utf-8")

        # Dry-run first: should report no orphans (legacy skip).
        rc, out, _err = self._run("--event", "5")
        self.assertEqual(rc, 0)
        self.assertIn("Event_5: clean (no orphans)", out)

        # --apply: still no mutation because nothing identified as orphan.
        rc2, _out2, _err2 = self._run("--apply", "--event", "5")
        self.assertEqual(rc2, 0)
        after = state_path.read_text(encoding="utf-8")
        self.assertEqual(before, after, "legacy-skip violated: file mutated despite "
                         "display_order absent.")
        self.assertEqual(self.activity_log_writes, [],
                         "activity log written for a no-op apply")

    def test_legacy_skip_when_display_order_is_integer(self):
        """display_order=integer (pre-v3 fixture-style) — same as undefined."""
        state_path = _seed_event_state(
            self.prod_root, "6",
            partition_state={
                "intro": {
                    "video_role": "intro",
                    "beats": {
                        "beat_01": {"text": "x"},
                        "beat_02": {"text": "y"},
                    },
                    "display_order": 1,
                },
            },
        )
        before = state_path.read_text(encoding="utf-8")
        rc, _out, _err = self._run("--apply", "--event", "6")
        self.assertEqual(rc, 0)
        after = state_path.read_text(encoding="utf-8")
        self.assertEqual(before, after,
                         "non-list display_order should be skipped, not pruned")


if __name__ == "__main__":
    unittest.main(verbosity=2)
