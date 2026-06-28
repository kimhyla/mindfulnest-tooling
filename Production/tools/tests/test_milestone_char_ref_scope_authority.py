"""Milestone char ref drops must read/write JSON sidecar — never global SQLite."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_TOOLS = Path(__file__).resolve().parents[1]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))


class MilestoneSidecarAuthorityTests(unittest.TestCase):
    def test_sidecar_use_sqlite_false_when_milestone_path_torn(self) -> None:
        import beat_generator as bg  # noqa: PLC0415

        milestone_path = "/tmp/Production/Milestones/milestone1_arc1/beat_generator_sidecar.json"
        with mock.patch.object(bg, "BG_SIDECAR_PATH", milestone_path), mock.patch.object(
            bg, "_MILESTONE_SIDECAR_JSON_ONLY", False,
        ), mock.patch.object(bg, "sqlite_authority_enabled", return_value=True):
            self.assertFalse(bg._sidecar_use_sqlite())

    def test_rebind_bg_paths_from_app_keeps_milestone_json_authority(self) -> None:
        import beat_generator as bg  # noqa: PLC0415
        from server_handlers.milestone_scope import rebind_bg_paths_from_app  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev = prod / "Event_1"
            mdir = prod / "Milestones" / "milestone1_arc1"
            ev.mkdir(parents=True)
            mdir.mkdir(parents=True)
            sidecar = {
                "schema_version": 3,
                "arcs": {"arc_1": {"segments": {"event_3b_full": {"beats": [
                    {
                        "beat_id": "bg_arc1_event3b_full_beat_10",
                        "speaker": "Oliver",
                        "reference_image": {
                            "key": "library_still",
                            "abs_path": str(ev / "library" / "still.png"),
                        },
                        "reference_image_locked": True,
                    },
                ]}}}},
            }
            still = ev / "library" / "still.png"
            still.parent.mkdir(parents=True)
            still.write_bytes(b"\x89PNG\r\n")
            (mdir / "beat_generator_sidecar.json").write_text(
                json.dumps(sidecar), encoding="utf-8",
            )
            os.environ["MN_SIDECAR_SQLITE_AUTHORITY"] = "1"
            os.environ["MN_BEATGEN_DB_PATH"] = str(Path(tmp) / "beatgen.db")
            try:
                bg.init_bg_paths(ev)
                self.assertTrue(bg._sidecar_use_sqlite())
                app = SimpleNamespace(
                    scope_type="milestone",
                    active_milestone_id="milestone1_arc1",
                    milestone_dir=mdir,
                    milestone_library_event_dir=ev,
                    event_dir=ev,
                )
                rebind_bg_paths_from_app(app)
                self.assertFalse(bg._sidecar_use_sqlite())
                loaded = bg.read_sidecar()
                beat = loaded["arcs"]["arc_1"]["segments"]["event_3b_full"]["beats"][0]
                self.assertTrue(beat.get("reference_image_locked"))
                self.assertIn("still.png", str(beat.get("reference_image", {}).get("abs_path", "")))
            finally:
                os.environ.pop("MN_SIDECAR_SQLITE_AUTHORITY", None)
                os.environ.pop("MN_BEATGEN_DB_PATH", None)
                from lib.beatgen_store import BeatgenStore

                BeatgenStore.reset_singleton_for_tests()


if __name__ == "__main__":
    unittest.main()
