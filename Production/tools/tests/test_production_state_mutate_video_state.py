#!/usr/bin/env python3
"""C2b contract test for HARD LD `DISPLAY_ORDER_STRICT_V1`.

CONTRACT (StateManager.mutate_video_state server prune):
  After every mutator_fn invocation, when the resulting partition's
  display_order is a LIST, drop any beats[bid] whose bid is not in
  display_order. Atomic via the existing mutate_state channel; no
  bypass of LD-519. Skip pruning when display_order is missing or
  non-list (legacy data shapes).

This prune ships with C2a renderer fix to prevent the orphan
accumulation that produced the original Bug B symptom (beat_04 in
Event_2/intro/beats with display_order=[]).

Mirrors test_sidecar_display_order_int.py and test_tier3_server.py
patterns: tempdir + bypass Directus lock + StateManager directly.

Run:
    python3 -m unittest Production.tools.tests.test_production_state_mutate_video_state -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_TOOLS = _THIS.parent.parent
sys.path.insert(0, str(_TOOLS))

# Bypass cross-machine Directus lock — required for isolated tests.
os.environ["PRODUCTION_SERVER_SINGLE_MACHINE"] = "1"

import production_server as ps  # noqa: E402


class TestMutateVideoStateOrphanPrune(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mutvs_"))
        self.event_dir = self.tmp
        self.state_mgr = ps.StateManager(self.event_dir, "Event_TEST")
        # StateManager._init_files auto-creates a v3 state.json with empty
        # videos.intro/resolution partitions.

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed(self, role: str, beats: dict, display_order):
        """Seed a partition's beats + display_order via mutate_video_state."""
        def _mutator(part, _b=beats, _do=display_order):
            part["beats"] = dict(_b)
            if _do is not _SENTINEL:
                part["display_order"] = _do
        self.state_mgr.mutate_video_state(role, _mutator)

    def _read_partition(self, role: str) -> dict:
        return self.state_mgr.read_state()["videos"][role]

    def test_prune_drops_beats_not_in_display_order_list(self):
        """Spec §2.3 Part 2 base case: display_order=['beat_01'], beats has
        beat_01 + beat_99 → beat_99 dropped."""
        self._seed("intro",
                   beats={"beat_01": {"text": "one"}, "beat_99": {"text": "orphan"}},
                   display_order=["beat_01"])
        # The seed itself triggers the prune (mutator runs inside
        # mutate_video_state; the prune fires post-mutator). Read back.
        part = self._read_partition("intro")
        self.assertEqual(part["display_order"], ["beat_01"])
        self.assertIn("beat_01", part["beats"])
        self.assertNotIn(
            "beat_99", part["beats"],
            "DISPLAY_ORDER_STRICT_V1 violated: orphan beat_99 not dropped "
            "post-mutation despite display_order=['beat_01']",
        )

    def test_prune_with_empty_display_order_drops_all_beats(self):
        """display_order=[] → beats{} should be empty after mutation. This
        is the cleanup path for the live Event_2/intro orphan beat_04."""
        self._seed("intro",
                   beats={"beat_04": {"text": "MindfulNest..."}},
                   display_order=[])
        part = self._read_partition("intro")
        self.assertEqual(part["display_order"], [])
        self.assertEqual(
            part["beats"], {},
            "DISPLAY_ORDER_STRICT_V1 violated: display_order=[] but beats "
            f"still contains keys: {list(part['beats'].keys())}",
        )

    def test_prune_skips_when_display_order_is_undefined(self):
        """Legacy partition (no display_order key) → prune must NOT fire;
        all beats preserved. This protects pre-S5.5b state shapes."""
        # Direct mutation that DELETES display_order to simulate legacy.
        def _mutator(part):
            part["beats"] = {"beat_01": {"text": "one"}, "beat_99": {"text": "two"}}
            if "display_order" in part:
                del part["display_order"]
        self.state_mgr.mutate_video_state("intro", _mutator)
        part = self._read_partition("intro")
        self.assertNotIn(
            "display_order", part,
            "Test seed failed: display_order should be absent after mutator",
        )
        self.assertIn("beat_01", part["beats"])
        self.assertIn(
            "beat_99", part["beats"],
            "Legacy-skip violated: prune fired despite display_order being "
            "undefined; beat_99 was dropped.",
        )

    def test_prune_skips_when_display_order_is_non_list(self):
        """Legacy non-list display_order (e.g. integer from old fixture) →
        prune must NOT fire; all beats preserved."""
        def _mutator(part):
            part["beats"] = {"beat_01": {"text": "one"}, "beat_99": {"text": "two"}}
            part["display_order"] = 5  # malformed integer
        self.state_mgr.mutate_video_state("intro", _mutator)
        part = self._read_partition("intro")
        self.assertEqual(part["display_order"], 5)
        self.assertIn("beat_01", part["beats"])
        self.assertIn(
            "beat_99", part["beats"],
            "Non-list-skip violated: prune fired despite display_order=5 "
            "being non-list; beat_99 was dropped.",
        )

    def test_prune_idempotent_on_already_consistent_partition(self):
        """When beats and display_order already match, mutate is a no-op
        (no spurious deletions)."""
        self._seed("intro",
                   beats={"beat_01": {"text": "one"}, "beat_02": {"text": "two"}},
                   display_order=["beat_01", "beat_02"])
        # Run a no-op mutation that doesn't touch beats or display_order.
        def _noop(part):
            part["video_label"] = "Updated label"
        self.state_mgr.mutate_video_state("intro", _noop)
        part = self._read_partition("intro")
        self.assertEqual(part["display_order"], ["beat_01", "beat_02"])
        self.assertEqual(set(part["beats"].keys()), {"beat_01", "beat_02"})


# Module-level sentinel for "not provided" (vs. None which means delete).
_SENTINEL = object()


if __name__ == "__main__":
    unittest.main(verbosity=2)
