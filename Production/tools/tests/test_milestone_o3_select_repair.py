"""Milestone O3 select-o3 gallery repair — disk clip exists, sidecar row missing."""
from __future__ import annotations

import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import Production.tools.beat_generator as bg
from Production.tools.production_server import _bg_module
from Production.tools.server_handlers import background as bg_handler


class MilestoneO3SelectRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = Path(os.environ["TEST_TMPDIR"]) if "TEST_TMPDIR" in os.environ else None

    def test_find_o3_video_path_for_option_key_event3b_pov(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            event1 = Path(tmp) / "Production" / "Event_1"
            clips = event1 / "kling_o3_clips"
            clips.mkdir(parents=True)
            beat_id = "bg_arc1_event3b_full_beat_12"
            delivery = clips / f"{beat_id}_g1_pov_wand_wiper_delivery.mp4"
            delivery.write_bytes(b"mp4")
            option_key = f"{beat_id}_o3_video_{hashlib.sha1(str(delivery.resolve()).encode()).hexdigest()[:10]}"
            found = bg.find_o3_video_path_for_option_key(beat_id, option_key, [event1])
            self.assertEqual(found, delivery.resolve())

    def test_reconcile_imports_pov_delivery_into_sidecar(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            event1 = Path(tmp) / "Production" / "Event_1"
            clips = event1 / "kling_o3_clips"
            clips.mkdir(parents=True)
            beat_id = "bg_arc1_event3b_full_beat_12"
            delivery = clips / f"{beat_id}_g1_pov_wand_wiper_delivery.mp4"
            delivery.write_bytes(b"mp4")
            beat = {"beat_id": beat_id, "speaker": "Lorelai", "kling_o3_options": []}
            changed = bg.reconcile_o3_disk_deliveries_for_beat(beat, event1)
            self.assertTrue(changed)
            paths = [o.get("video_path") for o in beat.get("kling_o3_options") or []]
            self.assertIn(str(delivery.resolve()), paths)

    def test_repair_o3_select_before_resolve_upserts_missing_option(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            event1 = prod / "Event_1"
            event2 = prod / "Event_2"
            mdir = prod / "Milestones" / "milestone1_arc1"
            for d in (event1, event2, mdir):
                d.mkdir(parents=True)
            (event1 / "library" / "images").mkdir(parents=True)
            beat_id = "bg_arc1_event3b_full_beat_12"
            delivery = event1 / "kling_o3_clips" / f"{beat_id}_g1_pov_wand_wiper_delivery.mp4"
            delivery.parent.mkdir(parents=True)
            delivery.write_bytes(b"mp4")
            option_key = f"{beat_id}_o3_video_{hashlib.sha1(str(delivery.resolve()).encode()).hexdigest()[:10]}"
            sidecar = {
                "schema_version": 3,
                "arcs": {"arc_1": {"segments": {"event_3b_full": {"beats": [
                    {"beat_id": beat_id, "speaker": "Lorelai", "kling_o3_options": []},
                ]}}}},
            }
            (mdir / "beat_generator_sidecar.json").write_text(
                json.dumps(sidecar), encoding="utf-8",
            )
            mod = _bg_module()
            mod.init_bg_paths(event2, milestone_dir=mdir, library_event_dir=event1)
            h = MagicMock()
            h.app.event_dir = event2
            h.app.scope_type = "milestone"
            h.app.milestone_library_event_dir = event1
            h.app.milestone_dir = mdir
            bg_handler._repair_o3_select_before_resolve(h, beat_id, option_key)
            loaded = mod.read_sidecar()
            _, beat = mod.find_beat(loaded, beat_id)
            self.assertIsNotNone(beat)
            keys = [o.get("key") for o in (beat or {}).get("kling_o3_options") or []]
            self.assertIn(option_key, keys)

    def test_recover_orphan_does_not_call_init_bg_paths(self) -> None:
        import inspect

        src = inspect.getsource(bg.recover_orphan_o3_delivery)
        self.assertNotIn("init_bg_paths(", src)


if __name__ == "__main__":
    unittest.main()
