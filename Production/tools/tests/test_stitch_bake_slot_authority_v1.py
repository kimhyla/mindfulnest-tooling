"""STITCH_BAKE_SLOT_AUTHORITY_V1 — module bake must not overwrite phase_b stitch slot."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from server_handlers.phases import (  # noqa: E402
    STITCH_BAKE_SLOT_AUTHORITY_V1,
    ensure_phase_b_stitch_slot_for_bake,
    validate_phase_b_stitch_slot_authority,
)


def _make_tone_mp4(path: Path, duration_s: float = 0.5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-f", "lavfi", "-i", f"color=c=black:s=320x240:d={duration_s:.3f}",
            "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


class ValidatePhaseBStitchSlotAuthorityTests(unittest.TestCase):
    def _handler(self, project: Path, stitch_state: dict) -> MagicMock:
        class _Store:
            def read_state(self):
                return stitch_state

            def mutate_state(self, fn):
                fn(stitch_state)

        h = MagicMock()
        h._stitch_resolve_path = lambda raw: str((project / raw).resolve())
        h.app.event_dir = project / "Production" / "Event_3"
        return h, _Store()

    def test_validates_pinned_manual_dry_without_upsert(self) -> None:
        project = Path("/tmp/stitch_bake_slot_auth_test")
        dry_rel = "Production/Event_3/preview/phase_b/phase_b_preview_cedric_trim_v6.mp4"
        play_rel = "Production/Event_3/assembled/phase_b_playback_v6.mp4"
        _make_tone_mp4(project / dry_rel)
        _make_tone_mp4(project / play_rel)

        stitch_state = {
            "jobs": {
                "Event_3_stitch": {
                    "slots": {
                        "phase_b": {
                            "video_path": play_rel,
                            "dry_export_path": dry_rel,
                            "video_dur_ms": 200708,
                        },
                    },
                },
            },
        }
        h, store = self._handler(project, stitch_state)
        with patch(
            "server_handlers.stitch_editor.stitch_state_store_for_job",
            return_value=store,
        ):
            out = validate_phase_b_stitch_slot_authority(h, job_name="Event_3_stitch")

        self.assertTrue(out["ok"])
        self.assertTrue(out["validated"])
        self.assertEqual(out["dry_export_path"], dry_rel)
        self.assertEqual(out["code"], STITCH_BAKE_SLOT_AUTHORITY_V1)

    def test_fails_when_phase_b_slot_empty(self) -> None:
        project = Path("/tmp/stitch_bake_slot_auth_empty")
        stitch_state = {"jobs": {"Event_3_stitch": {"slots": {}}}}
        h, store = self._handler(project, stitch_state)
        with patch(
            "server_handlers.stitch_editor.stitch_state_store_for_job",
            return_value=store,
        ):
            out = validate_phase_b_stitch_slot_authority(h, job_name="Event_3_stitch")

        self.assertFalse(out["ok"])
        self.assertIn("phase_b slot empty", out["error"])

    def test_fails_when_slot_file_missing_on_disk(self) -> None:
        project = Path("/tmp/stitch_bake_slot_auth_missing")
        dry_rel = "Production/Event_3/preview/phase_b/missing.mp4"
        stitch_state = {
            "jobs": {
                "Event_3_stitch": {
                    "slots": {
                        "phase_b": {
                            "video_path": dry_rel,
                            "dry_export_path": dry_rel,
                        },
                    },
                },
            },
        }
        h, store = self._handler(project, stitch_state)
        with patch(
            "server_handlers.stitch_editor.stitch_state_store_for_job",
            return_value=store,
        ):
            out = validate_phase_b_stitch_slot_authority(h, job_name="Event_3_stitch")

        self.assertFalse(out["ok"])
        self.assertIn("missing on disk", out["error"])


class EnsurePhaseBBakePreflightTests(unittest.TestCase):
    def test_bake_preflight_does_not_call_overlay_or_upsert(self) -> None:
        src = (TOOLS / "server_handlers" / "phases.py").read_text(encoding="utf-8")
        block = src.split("def ensure_phase_b_stitch_slot_for_bake", 1)[1].split(
            "\ndef handle_phase_b_preview", 1,
        )[0]
        self.assertIn("validate_phase_b_stitch_slot_authority", block)
        self.assertNotIn("stitch_upsert_event_slot", block)
        self.assertNotIn("_phase_ensure_overlay_mp4", block)
        self.assertNotIn("operator_export=True", block)

    def test_preflight_validates_existing_slot_when_lipsync_ready(self) -> None:
        project = Path("/tmp/stitch_bake_preflight_validate")
        dry_rel = "Production/Event_3/preview/phase_b/phase_b_preview_cedric_trim_v6.mp4"
        play_rel = "Production/Event_3/assembled/phase_b_playback_v6.mp4"
        _make_tone_mp4(project / dry_rel)
        _make_tone_mp4(project / play_rel)

        lipsync = project / "Production" / "Event_3" / "phase_b_lipsync.mp4"
        _make_tone_mp4(lipsync)

        stitch_state = {
            "jobs": {
                "Event_3_stitch": {
                    "slots": {
                        "phase_b": {
                            "video_path": play_rel,
                            "dry_export_path": dry_rel,
                            "video_dur_ms": 200708,
                        },
                    },
                },
            },
        }

        class _Store:
            def read_state(self):
                return stitch_state

            def mutate_state(self, fn):
                fn(stitch_state)

        prod_state = {
            "phase_b_lipsync_file": "phase_b_lipsync.mp4",
            "phase_b_lipsync_delivery_profile": "voice_first_upscale",
        }

        h = MagicMock()
        h._stitch_resolve_path = lambda raw: str((project / raw).resolve())
        h.app.event_dir = project / "Production" / "Event_3"
        h.app.state.read_state.return_value = prod_state

        with patch(
            "server_handlers.stitch_editor.stitch_state_store_for_job",
            return_value=_Store(),
        ), patch(
            "server_handlers.stitch_editor.stitch_upsert_event_slot",
        ) as upsert_mock, patch(
            "server_handlers.phases._phase_ensure_overlay_mp4",
        ) as overlay_mock:
            out = ensure_phase_b_stitch_slot_for_bake(h, job_name="Event_3_stitch")

        self.assertTrue(out["ok"])
        self.assertTrue(out["validated"])
        self.assertEqual(out["dry_export_path"], dry_rel)
        upsert_mock.assert_not_called()
        overlay_mock.assert_not_called()


class BakeCoreSourceGuards(unittest.TestCase):
    def test_bake_core_audits_slot_authority_validation(self) -> None:
        editor = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        block = editor.split("def _run_stitch_bake_core", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("PHASE_B_SLOT_AUTHORITY_VALIDATED", block)
        self.assertIn("PHASE_B_SLOT_AUTHORITY_FAILED", block)
        self.assertIn("Validating Phase B stitch slot", block)
        self.assertIn("ensure_phase_b_stitch_slot_for_bake(h, job_name=job_name)", block)


if __name__ == "__main__":
    unittest.main()
