"""Milestone sticky bind — bare init_bg_paths must not tear JSON sidecar authority."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path


class MilestoneInitBgPathsAuthorityGuardTests(unittest.TestCase):
    def test_bare_init_preserves_milestone_json_authority(self):
        import Production.tools.beat_generator as bg  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev = prod / "Event_1"
            ev2 = prod / "Event_2"
            mdir = prod / "Milestones" / "milestone1_arc1"
            for d in (ev, ev2, mdir):
                d.mkdir(parents=True)
            (ev / "library" / "images").mkdir(parents=True)
            sidecar = {
                "schema_version": 3,
                "arcs": {"arc_1": {"segments": {"event_3b_full": {"beats": [
                    {"beat_id": "bg_arc1_event3b_full_beat_01", "speaker": "Arlo"},
                ]}}}},
            }
            sc_path = mdir / "beat_generator_sidecar.json"
            sc_path.write_text(json.dumps(sidecar), encoding="utf-8")
            bg.init_bg_paths(ev2, milestone_dir=mdir, library_event_dir=ev)
            milestone_path = Path(bg.BG_SIDECAR_PATH)
            self.assertTrue(bg._MILESTONE_SIDECAR_JSON_ONLY)
            bg.init_bg_paths(ev)  # would have torn authority before sticky bind
            self.assertTrue(bg._MILESTONE_SIDECAR_JSON_ONLY)
            self.assertEqual(Path(bg.BG_SIDECAR_PATH).resolve(), milestone_path.resolve())
            self.assertIsNotNone(bg.milestone_scope_bind())

    def test_clear_milestone_scope_allows_event_rebind(self):
        import Production.tools.beat_generator as bg  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev = prod / "Event_1"
            ev2 = prod / "Event_2"
            mdir = prod / "Milestones" / "milestone1_arc1"
            for d in (ev, ev2, mdir):
                d.mkdir(parents=True)
            bg.init_bg_paths(ev2, milestone_dir=mdir, library_event_dir=ev)
            bg.init_bg_paths(ev2, clear_milestone_scope=True)
            self.assertFalse(bg._MILESTONE_SIDECAR_JSON_ONLY)
            self.assertIsNone(bg.milestone_scope_bind())

    def test_milestone_init_never_bootstraps_sqlite(self):
        import Production.tools.beat_generator as bg  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev = prod / "Event_1"
            mdir = prod / "Milestones" / "milestone1_arc1"
            ev.mkdir(parents=True)
            mdir.mkdir(parents=True)
            (mdir / "beat_generator_sidecar.json").write_text(
                json.dumps({"schema_version": 3, "arcs": {}}), encoding="utf-8",
            )
            corrupt_db = Path(tmp) / "beatgen.db"
            corrupt_db.write_bytes(b"\x00" * 4096)
            os.environ["MN_BEATGEN_DB_PATH"] = str(corrupt_db)
            try:
                bg.init_bg_paths(ev, milestone_dir=mdir, library_event_dir=ev)
                self.assertTrue(bg._MILESTONE_SIDECAR_JSON_ONLY)
                self.assertFalse(bg._sidecar_use_sqlite())
            finally:
                os.environ.pop("MN_BEATGEN_DB_PATH", None)

    def test_resolve_o3_lifecycle_candidates_uses_library_under_milestone_bind(self):
        import Production.tools.beat_generator as bg  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev1 = prod / "Event_1"
            ev2 = prod / "Event_2"
            mdir = prod / "Milestones" / "milestone1_arc1"
            for d in (ev1, ev2, mdir):
                d.mkdir(parents=True)
            bg.init_bg_paths(ev2, milestone_dir=mdir, library_event_dir=ev1)
            beat_id = "bg_arc1_event3b_full_beat_12"
            cands = bg.resolve_o3_lifecycle_event_dir_candidates(
                beat_id, server_event_dir=ev2,
            )
            self.assertIn(ev1.resolve(), [p.resolve() for p in cands])