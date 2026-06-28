"""STITCH_WRITE_TIME_PLAYBACK_ARTIFACTS_V1 — ffmpeg only on export/hydrate, never load_job GET."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


class StitchWriteTimePlaybackSourceGuards(unittest.TestCase):
    def test_load_job_has_no_playback_bake(self) -> None:
        src = (TOOLS / "server_handlers/stitch_editor.py").read_text(encoding="utf-8")
        block = src.split("def handle_stitch_load_job", 1)[1].split(
            "\ndef handle_stitch_serve_module_final", 1,
        )[0]
        self.assertIn("STITCH_WRITE_TIME_PLAYBACK_ARTIFACTS_V1", block)
        self.assertNotIn('trigger="load_job"', block)
        self.assertNotIn("trigger='load_job'", block)
        self.assertNotIn("stitch_slot_needs_playback_artifact_bake", block)

    def test_upsert_requires_playback_bake(self) -> None:
        src = (TOOLS / "server_handlers/stitch_editor.py").read_text(encoding="utf-8")
        block = src.split("def stitch_upsert_event_slot", 1)[1].split(
            "\ndef handle_stitch_loudnorm", 1,
        )[0]
        self.assertIn("_require_playback_artifacts_on_write", block)

    def test_bootstrap_repair_on_hydrate(self) -> None:
        src = (TOOLS / "server_handlers/stitch_editor.py").read_text(encoding="utf-8")
        block = src.split("def ensure_event_stitch_job_registered", 1)[1].split(
            "\ndef hydrate_stitch_canonical_slots_from_disk", 1,
        )[0]
        self.assertIn("_repair_stitch_job_playback_artifacts_on_write", block)


class StitchUpsertFailsWhenBakeFails(unittest.TestCase):
    def test_export_raises_when_mux_bake_fails(self) -> None:
        from server_handlers.stitch_editor import stitch_upsert_event_slot

        project = Path("/tmp/stitch_write_time_test")
        project.mkdir(parents=True, exist_ok=True)
        state_path = project / "stitch_editor_state.json"
        state_path.write_text(json.dumps({"version": 1, "jobs": {}}), encoding="utf-8")
        video_rel = "Production/Event_1/intro.mp4"
        (project / video_rel).parent.mkdir(parents=True, exist_ok=True)
        (project / video_rel).write_bytes(b"video" * 100)

        class StitchState:
            def read_state(self):
                return json.loads(state_path.read_text(encoding="utf-8"))

            def mutate_state(self, fn):
                state = self.read_state()
                fn(state)
                state_path.write_text(json.dumps(state), encoding="utf-8")

        h = MagicMock()
        h.app.stitch_state = StitchState()
        h._stitch_project_root = lambda: project
        h._stitch_cache_dir = lambda: project / "cache"
        (project / "cache").mkdir(exist_ok=True)
        h._stitch_resolve_path = lambda raw: str((project / raw).resolve())

        with patch(
            "server_handlers.stitch_editor.stitch_slot_export_media_preflight",
            return_value=(5000, []),
        ), patch(
            "server_handlers.stitch_editor.ensure_stitch_slot_playback_artifacts_on_export",
            return_value={"ok": False, "error": "ffmpeg failed"},
        ):
            with self.assertRaises(ValueError) as ctx:
                stitch_upsert_event_slot(
                    h,
                    "Event_1",
                    "intro",
                    {"video_path": video_rel, "source": "test"},
                    operator_export=True,
                )
            self.assertIn("STITCH_WRITE_TIME_PLAYBACK_ARTIFACTS_V1", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
