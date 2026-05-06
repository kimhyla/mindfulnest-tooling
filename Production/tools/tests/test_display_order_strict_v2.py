#!/usr/bin/env python3
"""C-10 — TVMC-K4.1: DISPLAY_ORDER_STRICT_V2 defense-in-depth prune in
StateManager.mutate_state.

Per STORYBOARD_V59_AUTHORING_WORKFLOW_SPEC_v2.md §3.1 (K4 cite L1198-1217)
+ §11.1 (TVMC-K4.1 Pytest contract): the C-10 fix adds a post-write
prune to StateManager.mutate_state itself, matching the existing prune
in mutate_video_state. After every mutate_state call, walk state["videos"]
and for each partition with a present-list display_order, prune
partition.beats to be a subset.

Pre-C-7.5: K1/D5 sibling handlers wrote to videos.<role>.beats via
mutate_state without going through mutate_video_state — bypassed the V1
prune. The 2026-05-01 cross-event leak exploited this asymmetry: the
Accept-All seed wrote to legacy state.beats; the migration script later
lifted those into videos.intro.beats; mutate_video_state's prune never
saw them because all the writers used mutate_state.

Post-C-7.5: all v59 mutation handlers route partition writes through
mutate_video_state; V2 in mutate_state is structural-fallback / defense-
in-depth. Idempotent on every mutate_state call.

Run directly:
    python3 Production/tools/tests/test_display_order_strict_v2.py

Or via unittest:
    python3 -m unittest Production.tools.tests.test_display_order_strict_v2 -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


# sys.path setup (Production/ first; Production/tools/ at end) — see
# test_scope_router_scrambled.py top-of-file note for the order rationale.
_THIS = Path(__file__).resolve()
_PRODUCTION = _THIS.parents[2]
_TOOLS = _PRODUCTION / "tools"
if str(_PRODUCTION) not in sys.path:
    sys.path.insert(0, str(_PRODUCTION))
if str(_TOOLS) not in sys.path:
    sys.path.append(str(_TOOLS))
os.environ.setdefault("PRODUCTION_SERVER_SINGLE_MACHINE", "1")

import production_server as _ps  # noqa: E402,F401


class DisplayOrderStrictV2Tests(unittest.TestCase):
    """Defense-in-depth prune in StateManager.mutate_state."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.event_dir = Path(self._tmpdir.name) / "Event_test"
        self.event_dir.mkdir()
        # Build StateManager (seeds production_state.json + production_spend.json
        # with init shape), then overwrite production_state.json with our
        # controlled seed AFTER init.
        self.sm = _ps.StateManager(self.event_dir, "Event_test")

    def _seed_state(self, state: dict) -> None:
        """Overwrite production_state.json with a known shape (test setup)."""
        self.sm.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _read_state(self) -> dict:
        return json.loads(self.sm.state_path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # TVMC-K4.1 — list display_order: orphan beat pruned by V2
    # ------------------------------------------------------------------
    def test_TVMC_K4_1_mutate_state_prunes_orphan_beat_for_list_display_order(self):
        """Seed videos.intro with display_order=[beat_01], beats={beat_01, beat_02}.

        After any mutate_state call (here a no-op mutator), the V2 prune
        drops beat_02 because it's not in display_order. Pre-C-10 this
        path bypassed pruning; the asymmetry was K4.
        """
        self._seed_state({
            "_module_version": "test",
            "event_id": "Event_test",
            "version": 0,
            "videos": {
                "intro": {
                    "video_role": "intro",
                    "video_label": None,
                    "display_order": ["beat_01"],
                    "beats": {
                        "beat_01": {"text": "kept", "_version": 1},
                        "beat_02": {"text": "orphan; should be pruned", "_version": 1},
                    },
                    "image_overrides": {},
                    "completed_mp4_path": None,
                },
            },
        })

        # No-op mutator — exercises V2 defense-in-depth on the read-write cycle.
        self.sm.mutate_state(lambda state: None)

        post = self._read_state()
        intro = post["videos"]["intro"]
        self.assertEqual(
            sorted(intro["beats"].keys()), ["beat_01"],
            "V2 must prune beat_02 (not in display_order) on any mutate_state call",
        )
        self.assertEqual(
            intro["beats"]["beat_01"]["text"], "kept",
            "V2 prune must NOT touch beats that ARE in display_order",
        )
        self.assertEqual(
            intro["display_order"], ["beat_01"],
            "display_order itself unchanged",
        )

    # ------------------------------------------------------------------
    # TVMC-K4.1b — int display_order (legacy fixture shape): prune SKIPS
    # ------------------------------------------------------------------
    def test_TVMC_K4_1b_mutate_state_skips_prune_for_int_display_order(self):
        """Legacy pre-v3 fixtures stored display_order as an integer.

        The prune block must isinstance-guard against non-list values so
        legacy shapes don't trip a destructive prune. Event_e2e_fixture
        uses int(1) for intro / int(2) for resolution.
        """
        self._seed_state({
            "_module_version": "test",
            "event_id": "Event_test",
            "version": 0,
            "videos": {
                "intro": {
                    "video_role": "intro",
                    "video_label": None,
                    "display_order": 1,  # legacy int — prune must skip
                    "beats": {
                        "beat_01": {"text": "should survive"},
                        "beat_02": {"text": "should also survive (int do, no prune)"},
                    },
                },
            },
        })
        self.sm.mutate_state(lambda state: None)
        post = self._read_state()
        intro = post["videos"]["intro"]
        self.assertEqual(
            sorted(intro["beats"].keys()), ["beat_01", "beat_02"],
            "V2 must SKIP prune when display_order is non-list (legacy int form); "
            "destructive prune on legacy fixtures would be a regression",
        )

    # ------------------------------------------------------------------
    # TVMC-K4.1c — multi-partition: each role pruned independently
    # ------------------------------------------------------------------
    def test_TVMC_K4_1c_mutate_state_prunes_multiple_partitions(self):
        """V2 walks state.videos and prunes each role partition independently."""
        self._seed_state({
            "_module_version": "test",
            "event_id": "Event_test",
            "version": 0,
            "videos": {
                "intro": {
                    "video_role": "intro",
                    "display_order": ["beat_01"],
                    "beats": {"beat_01": {}, "beat_99_orphan": {}},
                },
                "resolution": {
                    "video_role": "resolution",
                    "display_order": ["beat_02"],
                    "beats": {"beat_02": {}, "beat_42_orphan": {}},
                },
                "standalone": {
                    "video_role": "standalone",
                    "display_order": [],  # empty list — all beats pruned
                    "beats": {"beat_77_orphan": {}},
                },
            },
        })
        self.sm.mutate_state(lambda state: None)
        post = self._read_state()
        v = post["videos"]
        self.assertEqual(sorted(v["intro"]["beats"].keys()), ["beat_01"])
        self.assertEqual(sorted(v["resolution"]["beats"].keys()), ["beat_02"])
        self.assertEqual(v["standalone"]["beats"], {})

    # ------------------------------------------------------------------
    # TVMC-K4.1d — idempotency: running mutate_state twice doesn't break
    # ------------------------------------------------------------------
    def test_TVMC_K4_1d_idempotent_across_repeated_mutate_state_calls(self):
        """Post-prune state is stable: subsequent mutate_state calls are no-op
        on display_order/beats consistency.
        """
        self._seed_state({
            "_module_version": "test",
            "event_id": "Event_test",
            "version": 0,
            "videos": {
                "intro": {
                    "video_role": "intro",
                    "display_order": ["beat_01"],
                    "beats": {"beat_01": {"text": "x"}, "beat_02": {"text": "orphan"}},
                },
            },
        })
        self.sm.mutate_state(lambda state: None)
        first_post = self._read_state()
        self.sm.mutate_state(lambda state: None)
        second_post = self._read_state()
        # Compare videos.intro beats + display_order; updated_at differs
        # between calls, so don't compare the whole state.
        self.assertEqual(
            first_post["videos"]["intro"]["beats"],
            second_post["videos"]["intro"]["beats"],
            "second mutate_state call must not perturb beats",
        )
        self.assertEqual(
            first_post["videos"]["intro"]["display_order"],
            second_post["videos"]["intro"]["display_order"],
            "display_order must be stable across repeated calls",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
