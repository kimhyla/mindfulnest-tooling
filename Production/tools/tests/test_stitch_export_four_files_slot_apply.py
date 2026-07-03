"""STITCH_EXPORT_FOUR_FILES_SLOT_APPLY_V1 — Send to Stitcher must persist baked playback."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from server_handlers.stitch_slot_playback import (  # noqa: E402
    STITCH_EXPORT_FOUR_FILES_SLOT_APPLY_V1,
    STITCH_FOUR_FILES_V1,
    _prepare_dry_concat_for_slot_bake,
    assert_four_files_export_slot_applied,
)


def _make_tone_mp4(path: Path, duration_s: float = 1.0) -> None:
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


class PrepareDryConcatNormalizeArgTests(unittest.TestCase):
    def test_normalize_receives_str_not_path(self) -> None:
        """Regression: PosixPath to _stitch_normalize_slot caused encode() crash."""
        dry = Path("/tmp/fake_dry_intro_kling_o3_test.mp4")
        cache = Path("/tmp/fake_cache")
        captured: list[object] = []

        h = MagicMock()

        def _capture_norm(video_path, cache_dir, *a, **kw):
            captured.append(video_path)
            return Path(video_path)

        h._stitch_normalize_slot = _capture_norm
        h._stitch_ensure_audio = lambda p, _c: p
        with patch(
            "server_handlers.speech_loudnorm.apply_speech_loudnorm_to_mp4",
            return_value=(dry, False),
        ):
            out = _prepare_dry_concat_for_slot_bake(h, dry, cache)
        self.assertEqual(out, dry)
        self.assertEqual(len(captured), 1)
        self.assertIsInstance(captured[0], str)
        self.assertEqual(captured[0], str(dry))


class AssertFourFilesSlotApplyTests(unittest.TestCase):
    def test_raises_when_slot_video_path_still_dry(self) -> None:
        with patch("tempfile.TemporaryDirectory") as _:
            project = Path("/tmp/stitch_slot_apply_test")
            project.mkdir(parents=True, exist_ok=True)
            dry_rel = "Production/Event_X/assembled/intro_kling_o3_test.mp4"
            play_rel = "Production/Event_X/assembled/intro_playback_test.mp4"
            dry_abs = project / dry_rel
            play_abs = project / play_rel
            dry_abs.parent.mkdir(parents=True, exist_ok=True)
            _make_tone_mp4(dry_abs, 0.5)
            _make_tone_mp4(play_abs, 0.5)

            state = {
                "jobs": {
                    "Event_X_stitch": {
                        "slots": {
                            "intro": {
                                "video_path": dry_rel,
                                "dry_export_path": dry_rel,
                                "playback_recipe_version": STITCH_FOUR_FILES_V1,
                            },
                        },
                    },
                },
            }

            class _Store:
                def read_state(self):
                    return state

            h = MagicMock()
            h._stitch_resolve_path = lambda raw: str((project / raw).resolve())

            artifacts = {
                "ok": True,
                "code": STITCH_FOUR_FILES_V1,
                "video_path": play_rel,
            }
            with self.assertRaises(RuntimeError) as ctx:
                assert_four_files_export_slot_applied(
                    h,
                    stitch_store=_Store(),
                    job_name="Event_X_stitch",
                    slot_key="intro",
                    dry_video_rel=dry_rel,
                    playback_artifacts=artifacts,
                )
            self.assertIn(STITCH_EXPORT_FOUR_FILES_SLOT_APPLY_V1, str(ctx.exception))
            self.assertIn("slot.video_path did not update", str(ctx.exception))


class ExportSourceGuards(unittest.TestCase):
    def test_kling_export_calls_slot_apply_assert(self) -> None:
        src = (TOOLS / "server_handlers" / "kling_o3.py").read_text(encoding="utf-8")
        block = src.split("def _run_bg_export_to_stitcher_core", 1)[1].split("\ndef _execute", 1)[0]
        self.assertIn("verify_event_slot_four_files_export_applied", block)
        self.assertIn("STITCH_EXPORT_SLOT_NOT_APPLIED", block)

    def test_phase_export_calls_shared_slot_apply_gate(self) -> None:
        src = (TOOLS / "server_handlers/phases.py").read_text(encoding="utf-8")
        block = src.split("def handle_phase_export_stitcher", 1)[1].split(
            "\ndef ensure_phase_b_stitch_slot_for_bake", 1,
        )[0]
        self.assertIn("verify_event_slot_four_files_export_applied", block)
        self.assertIn("STITCH_PLAYBACK_BAKE_FAILED", block)
        self.assertIn("STITCH_EXPORT_SLOT_NOT_APPLIED", block)
        self.assertIn("server_mutation_gate_reason", block)

    def test_phase_b_bake_refresh_calls_shared_slot_apply_gate(self) -> None:
        src = (TOOLS / "server_handlers/phases.py").read_text(encoding="utf-8")
        block = src.split("def ensure_phase_b_stitch_slot_for_bake", 1)[1].split(
            "\ndef handle_phase_b_preview", 1,
        )[0]
        self.assertIn("verify_event_slot_four_files_export_applied", block)
        self.assertIn("playback_artifacts", block)

    def test_upsert_event_slots_use_bake_and_assert(self) -> None:
        playback = (TOOLS / "server_handlers" / "stitch_slot_playback.py").read_text(encoding="utf-8")
        self.assertIn("assert_four_files_export_slot_applied", playback)
        self.assertIn(STITCH_EXPORT_FOUR_FILES_SLOT_APPLY_V1, playback)
        editor = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        block = editor.split("def stitch_upsert_event_slot", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("bake_and_persist_slot_playback_mp4", block)
        self.assertNotIn("persist_dry_authority_slot_export", block)


if __name__ == "__main__":
    unittest.main()
