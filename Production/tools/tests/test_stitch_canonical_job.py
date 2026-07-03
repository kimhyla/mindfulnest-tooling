"""Unit tests for canonical per-event stitch job upsert + legacy migration."""
from __future__ import annotations

import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from server_handlers.stitch_editor import (
    stitch_event_job_name,
    stitch_migrate_legacy_to_canonical,
    stitch_upsert_event_slot,
    STITCH_SLOT_ORDER,
)


class _MockStitchState:
    def __init__(self, initial=None):
        self.state = initial or {"jobs": {}}

    def read_state(self):
        return self.state

    def mutate_state(self, fn):
        fn(self.state)


class _MockApp:
    def __init__(self, state=None):
        self.stitch_state = _MockStitchState(state)
        self._event_stitch_state = self.stitch_state
        self.event_dir = "Production/Event_1"


class _MockHandler:
    def __init__(self, state=None):
        self.app = _MockApp(state)

    def _stitch_project_root(self):
        from pathlib import Path
        return Path("/tmp/mn-stitch-test")

    def _stitch_resolve_path(self, raw: str) -> str:
        return raw

    def _ffprobe_duration_ms(self, _path) -> int:
        return 60_000

    def _stitch_cache_dir(self):
        return Path("/tmp/mn-stitch-test-cache")


class StitchCanonicalJobTests(unittest.TestCase):
    def test_event_job_name(self):
        self.assertEqual(stitch_event_job_name("Event_1"), "Event_1_stitch")

    def test_migrate_legacy_preserves_resolution_when_phase_b_exports(self):
        state = {
            "jobs": {
                "auto_resolution": {
                    "slots": {
                        "resolution": {"video_path": "/proj/scene_resolution.mp4"},
                    },
                },
                "phase_b_Event_1": {
                    "slots": {
                        "phase_b": {"video_path": "Production/Event_1/phase_b_lipsync_x.mp4"},
                    },
                },
            },
        }
        changed = stitch_migrate_legacy_to_canonical(state, "Event_1")
        self.assertTrue(changed)
        canonical = state["jobs"]["Event_1_stitch"]["slots"]
        self.assertIn("resolution", canonical)
        self.assertIn("phase_b", canonical)
        self.assertEqual(
            canonical["resolution"]["video_path"],
            "/proj/scene_resolution.mp4",
        )

    def test_upsert_does_not_drop_other_slots(self):
        dry_rel = "Production/Event_1/preview/phase_b/phase_b_preview_abc.mp4"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dry_abs = root / dry_rel
            dry_abs.parent.mkdir(parents=True, exist_ok=True)
            dry_abs.write_bytes(b"\x00")

            h = _MockHandler(
                {
                    "jobs": {
                        "Event_1_stitch": {
                            "slots": {
                                "resolution": {"video_path": "/proj/scene_resolution.mp4"},
                            },
                            "created_at": "2026-01-01T00:00:00Z",
                            "updated_at": "2026-01-01T00:00:00Z",
                        },
                    },
                },
            )
            h._stitch_project_root = lambda: root
            h._stitch_resolve_path = lambda raw: str(root / raw)
            h._stitch_cache_dir = lambda: root / ".cache"

            def _fake_bake(_h, _slot, *, dry_video_path, dest):
                dest = Path(dest)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(b"fake-playback-mp4")
                return 60.0

            def _fake_dest(_h, slot_key):
                assembled = root / "Production/Event_1/assembled"
                assembled.mkdir(parents=True, exist_ok=True)
                name = f"{slot_key}_playback_test.mp4"
                return assembled / name, f"Production/Event_1/assembled/{name}"

            with mock.patch(
                "server_handlers.stitch_editor.stitch_slot_export_media_preflight",
                return_value=(60_000, []),
            ), mock.patch(
                "server_handlers.stitch_editor.sync_stitch_slot_video_dur_ms",
                return_value=False,
            ), mock.patch(
                "server_handlers.stitch_slot_playback._assembled_playback_dest",
                side_effect=_fake_dest,
            ), mock.patch(
                "server_handlers.stitch_slot_playback.bake_slot_playback_mp4",
                side_effect=_fake_bake,
            ), mock.patch(
                "credentials_lib.ffmpeg_stitch.mp4_decodes_cleanly",
                return_value=True,
            ):
                stitch_upsert_event_slot(
                    h,
                    "Event_1",
                    "phase_b",
                    {"video_path": dry_rel},
                )
            slots = h.app.stitch_state.state["jobs"]["Event_1_stitch"]["slots"]
            self.assertIn("resolution", slots)
            self.assertIn("phase_b", slots)
            self.assertEqual(slots["phase_b"]["dry_export_path"], dry_rel)
            self.assertIn("_playback_", Path(slots["phase_b"]["video_path"]).name)

    def test_slot_order_constant(self):
        self.assertEqual(
            STITCH_SLOT_ORDER,
            ["intro", "phase_a", "phase_b", "resolution"],
        )


if __name__ == "__main__":
    unittest.main()
