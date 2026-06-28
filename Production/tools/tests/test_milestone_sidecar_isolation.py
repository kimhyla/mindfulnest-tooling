#!/usr/bin/env python3
"""Milestone sidecar must not inherit Event-scope segment pollution."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS.parent.parent))

from Production.lib.milestone_store import (  # noqa: E402
    isolate_milestone_sidecar,
    milestone_sidecar_is_polluted,
)
import Production.tools.beat_generator as bg  # noqa: E402


OLIVER_SKEL = {
    "arc_number": 1,
    "event_id": "3b",
    "phase": "full",
    "library_event_id": "Event_1",
}


class MilestoneSidecarIsolationTests(unittest.TestCase):
    def test_detects_event_scope_pollution(self):
        sidecar = {
            "active_context": {"arc_number": 1, "event_id": "3b", "phase": "full"},
            "arcs": {
                "arc_1": {
                    "segments": {
                        "event_1_pre": {"beats": [{"beat_id": "b1"}]},
                        "event_2_pre": {"beats": []},
                    },
                },
            },
        }
        self.assertTrue(milestone_sidecar_is_polluted(sidecar, OLIVER_SKEL))

    def test_isolate_keeps_milestone_segment_only(self):
        sidecar = {
            "active_context": {"arc_number": 1, "event_id": "3b", "phase": "full"},
            "arcs": {
                "arc_1": {
                    "segments": {
                        "event_1_pre": {"beats": [{"beat_id": "wrong"}]},
                        "event_3b_full": {
                            "name": "Oliver",
                            "beats": [{"beat_id": "arc1_event3b_full_b01"}],
                            "beat_plan_draft": {"beats_plan": [{"beat_index": 1}]},
                        },
                    },
                },
            },
        }
        self.assertTrue(isolate_milestone_sidecar(sidecar, OLIVER_SKEL))
        segs = sidecar["arcs"]["arc_1"]["segments"]
        self.assertEqual(list(segs.keys()), ["event_3b_full"])
        self.assertEqual(len(segs["event_3b_full"]["beats"]), 1)
        self.assertFalse(milestone_sidecar_is_polluted(sidecar, OLIVER_SKEL))

    def test_ensure_isolated_persists_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev = prod / "Event_1"
            mdir = prod / "Milestones" / "milestone1_arc1"
            ev.mkdir(parents=True)
            mdir.mkdir(parents=True)
            (ev / "library" / "images").mkdir(parents=True)
            polluted = {
                "schema_version": 1,
                "active_context": {"arc_number": 1, "event_id": "3b", "phase": "full"},
                "arcs": {
                    "arc_1": {
                        "segments": {
                            "event_1_pre": {"beats": [{"beat_id": "x"}]},
                        },
                    },
                },
            }
            sidecar_path = mdir / "beat_generator_sidecar.json"
            sidecar_path.write_text(json.dumps(polluted), encoding="utf-8")

            bg.set_milestone_skeleton_ref(OLIVER_SKEL)
            bg.init_bg_paths(ev, milestone_dir=mdir, library_event_dir=ev)
            self.assertTrue(bg.ensure_milestone_sidecar_isolated(persist=True))

            saved = json.loads(sidecar_path.read_text(encoding="utf-8"))
            segs = saved["arcs"]["arc_1"]["segments"]
            self.assertEqual(list(segs.keys()), ["event_3b_full"])
            self.assertEqual(saved["active_context"]["event_id"], "3b")

    def test_mirror_export_skips_milestone_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            mpath = str(Path(tmp) / "Production" / "Milestones" / "m1" / "beat_generator_sidecar.json")
            Path(mpath).parent.mkdir(parents=True)
            bg._write_sidecar_json_mirror({"arcs": {}}, mpath)
            self.assertFalse(Path(mpath).exists())


if __name__ == "__main__":
    unittest.main()
