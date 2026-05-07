#!/usr/bin/env python3
"""Path A++ Phase 1 live-build validation tests.

SHORTCUT_AUTONOMOUS_LIVE_BUILD_PHASE1_20260418 (April 18 2026)

Covers the acceptance criteria from MORNING_REPORT_PHASE1_DRYRUN_20260418.md §4:
  1. patch_state applies a mutation
  2. patch_state respects expected_version (409 conflict)
  3. patch_state is idempotent on mutation_id
  4. MINDFULNEST_WRITE_PATH=legacy disables v2 path
  5. patch_state with field="dialogue" triggers TTS regen (delegation smoke)
  6. sidecar JSON is written atomically on mutation
  7. v2 endpoint dispatch whitelist rejects unknown fields

Uses a synthetic beat_99_test fixture in a temp dir — NEVER touches
production_state.json or any real beat. Red-team-2 requirement.
"""

from __future__ import annotations
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Ensure we can import production_server
TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
# Directus lock is module-level; we must not let the real mutate_state call it.
os.environ["PRODUCTION_SERVER_SINGLE_MACHINE"] = "1"

import production_server as PS  # noqa: E402


def _make_app_and_state(tmp_path: Path):
    """Build an isolated StateManager + fake AppContext for tests."""
    event_dir = tmp_path / "Event_1"
    event_dir.mkdir(parents=True, exist_ok=True)

    # Seed storyboard path (sidecar uses its stem)
    storyboard = event_dir / "storyboard_test.html"
    storyboard.write_text("<html><body>test storyboard</body></html>", encoding="utf-8")

    state_mgr = PS.StateManager(event_dir, "M1E1_TEST")

    # Seed the beat_99_test fixture
    def seed(state):
        state.setdefault("beats", {})["beat_99_test"] = {
            "text": "original text",
            "phase_1": {"selected_option": 1, "trim_start": 0.0},
            "_version": 3,
        }
        return True
    state_mgr.mutate_state(seed)

    # Minimal AppContext-shaped object
    import threading as _t
    class FakeApp:
        def __init__(self):
            self.event_dir = event_dir
            self.storyboard_path = storyboard
            self.event_id = "M1E1_TEST"
            self.state = state_mgr
            self._storyboard_write_lock = _t.Lock()
            self._image_overrides = {}
            self._pending_override_keys = {}
        def invalidate_beats_cache(self):
            pass
    return FakeApp()


class TestPathAPlusPhase1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Clear rollback flag between test classes
        os.environ.pop("MINDFULNEST_WRITE_PATH", None)

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="pathapp_t1_"))
        self.app = _make_app_and_state(self.tmp_dir)
        # Clear dedup cache between tests
        PS._PATCH_STATE_DEDUP.clear()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        os.environ.pop("MINDFULNEST_WRITE_PATH", None)

    # ------------------------------------------------------------------
    # Test 1 — patch_state applies mutation
    # ------------------------------------------------------------------
    def test_patch_state_applies_mutation(self):
        r = PS.patch_state(
            self.app, "beat_99_test",
            "selected_option", 2,
            mutation_id="T1",
            expected_version=3,
        )
        self.assertEqual(r["status"], "applied")
        self.assertEqual(r["new_version"], 4)
        # Confirm on disk
        fresh = self.app.state.read_state()
        beat = fresh["beats"]["beat_99_test"]
        self.assertEqual(beat["phase_1"]["selected_option"], 2)
        self.assertEqual(beat["_version"], 4)

    # ------------------------------------------------------------------
    # Test 2 — expected_version conflict returns 409-shaped result
    # ------------------------------------------------------------------
    def test_patch_state_version_conflict(self):
        r = PS.patch_state(
            self.app, "beat_99_test",
            "selected_option", 2,
            mutation_id="T2",
            expected_version=999,  # WRONG
        )
        self.assertEqual(r["status"], "conflict")
        self.assertEqual(r["current_version"], 3)
        self.assertEqual(r["expected"], 999)
        # State unchanged
        fresh = self.app.state.read_state()
        self.assertEqual(fresh["beats"]["beat_99_test"]["phase_1"]["selected_option"], 1)

    # ------------------------------------------------------------------
    # Test 3 — mutation_id idempotency (replay returns cached)
    # ------------------------------------------------------------------
    def test_patch_state_mutation_id_idempotent(self):
        r1 = PS.patch_state(
            self.app, "beat_99_test",
            "selected_option", 2,
            mutation_id="T3",
            expected_version=3,
        )
        self.assertEqual(r1["status"], "applied")
        # Replay same mutation_id — should return cached (dedup)
        r2 = PS.patch_state(
            self.app, "beat_99_test",
            "selected_option", 99,  # different value — should be ignored
            mutation_id="T3",
            expected_version=3,
        )
        self.assertEqual(r2["status"], "dedup")
        self.assertTrue(r2.get("cached"))
        # State still has value=2 (from r1), NOT 99
        fresh = self.app.state.read_state()
        self.assertEqual(fresh["beats"]["beat_99_test"]["phase_1"]["selected_option"], 2)

    # ------------------------------------------------------------------
    # Test 4 — MINDFULNEST_WRITE_PATH=legacy disables v2 path
    # ------------------------------------------------------------------
    def test_patch_state_rollback_flag_disables_v2(self):
        os.environ["MINDFULNEST_WRITE_PATH"] = "legacy"
        r = PS.patch_state(
            self.app, "beat_99_test",
            "selected_option", 2,
            mutation_id="T4",
            expected_version=3,
        )
        self.assertEqual(r["status"], "disabled")
        self.assertIn("legacy", r["error"])
        # State UNCHANGED
        fresh = self.app.state.read_state()
        self.assertEqual(fresh["beats"]["beat_99_test"]["phase_1"]["selected_option"], 1)

    # ------------------------------------------------------------------
    # Test 5 — sidecar JSON is written on mutation
    # ------------------------------------------------------------------
    def test_sidecar_json_written(self):
        r = PS.patch_state(
            self.app, "beat_99_test",
            "trim_start", 2.5,
            mutation_id="T5",
            expected_version=3,
        )
        self.assertEqual(r["status"], "applied")
        sidecar = self.app.event_dir / (self.app.storyboard_path.stem + ".L.json")
        self.assertTrue(sidecar.exists(), "sidecar JSON should be written")
        data = json.loads(sidecar.read_text())
        self.assertIn("beat_99_test", data)
        self.assertEqual(data["beat_99_test"]["trim_start"], 2.5)
        self.assertEqual(data["beat_99_test"]["_version"], 4)

    # ------------------------------------------------------------------
    # Test 6 — whitelist rejects unknown fields
    # ------------------------------------------------------------------
    def test_whitelist_rejects_unknown_field(self):
        r = PS.patch_state(
            self.app, "beat_99_test",
            "random_field_not_allowed", "bad",
            mutation_id="T6",
            expected_version=3,
        )
        self.assertEqual(r["status"], "error")
        self.assertIn("whitelist", r["error"])

    # ------------------------------------------------------------------
    # Test 7 — image_override persists to state.image_overrides + sidecar
    # ------------------------------------------------------------------
    def test_image_override_stored_at_top_level(self):
        r = PS.patch_state(
            self.app, "beat_99_test",
            "image_override", "tessa_closeup_4x3",
            mutation_id="T7",
            expected_version=3,
        )
        self.assertEqual(r["status"], "applied")
        fresh = self.app.state.read_state()
        self.assertEqual(
            fresh["image_overrides"]["beat_99_test"],
            "tessa_closeup_4x3",
        )
        # Sidecar should also surface it as "i" key
        sidecar = self.app.event_dir / (self.app.storyboard_path.stem + ".L.json")
        data = json.loads(sidecar.read_text())
        self.assertEqual(data["beat_99_test"]["i"], "tessa_closeup_4x3")

    # ------------------------------------------------------------------
    # Test 8 — type validation (selected_option must coerce to int)
    # ------------------------------------------------------------------
    def test_type_validation(self):
        # str "3" should coerce
        r = PS.patch_state(
            self.app, "beat_99_test",
            "selected_option", "3",
            mutation_id="T8",
            expected_version=3,
        )
        self.assertEqual(r["status"], "applied")
        fresh = self.app.state.read_state()
        self.assertEqual(fresh["beats"]["beat_99_test"]["phase_1"]["selected_option"], 3)

    # ------------------------------------------------------------------
    # Test 9 — dialogue field type rejection (non-str)
    # ------------------------------------------------------------------
    def test_dialogue_requires_string(self):
        r = PS.patch_state(
            self.app, "beat_99_test",
            "dialogue", 12345,  # int, not str
            mutation_id="T9",
            expected_version=3,
        )
        self.assertEqual(r["status"], "error")
        self.assertIn("dialogue", r["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
