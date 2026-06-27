"""STITCH_SLOT_CANONICAL_DEFAULTS_V1 — tail SFX + ambient persist durability."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

TOOLS = Path(__file__).resolve().parents[1]


class TestStitchSlotCanonicalDefaults(unittest.TestCase):
    def test_constants_and_registry(self):
        from server_handlers import stitch_editor as se

        assert se.STITCH_SLOT_CANONICAL_DEFAULTS_V1
        assert se.STITCH_CANONICAL_DEFAULTS_PERSIST_V1
        assert se.STITCH_BOUNDARY_SFX_PIPELINE_ONLY_V1
        assert se.STITCH_RESOLUTION_HEAD_WHOOSH_V1
        assert se.STITCH_PHASE_B_NO_OUTGOING_VISUAL_FADE_V1
        assert "intro" in se.STITCH_SLOT_DEFAULT_TAIL_SFX
        assert "phase_a" not in se.STITCH_SLOT_CANONICAL_DEFAULT_SFX
        assert "phase_b" not in se.STITCH_SLOT_CANONICAL_DEFAULT_SFX
        assert se.STITCH_PIPELINE_BOUNDARY_SLOT_TAIL_SFX["phase_a"] == "windy_magic.mp3"
        assert "resolution" in se.STITCH_SLOT_CANONICAL_DEFAULT_SFX
        res_specs = se.STITCH_SLOT_CANONICAL_DEFAULT_SFX["resolution"]
        self.assertEqual(len(res_specs), 2)
        self.assertEqual(res_specs[0][0], se.STITCH_RESOLUTION_HEAD_SFX_FILENAME)
        self.assertEqual(res_specs[0][2], se.STITCH_SFX_PLACEMENT_HEAD)
        self.assertEqual(res_specs[1][0], se.STITCH_RESOLUTION_TAIL_SFX_FILENAME)
        self.assertEqual(res_specs[1][2], se.STITCH_SFX_PLACEMENT_TAIL)

    def test_resolution_head_and_tail_sfx_cues(self):
        from server_handlers.stitch_editor import ensure_stitch_slot_canonical_default_sfx_cues

        h = MagicMock()
        h._ffprobe_duration_ms.side_effect = lambda p: {
            "whoosh sound.mp3": 3104,
            "exit resolution video sfx.mp3": 5180,
        }.get(Path(p).name, 49700)
        slot = {"video_path": "Production/Event_2/resolution.mp4", "video_dur_ms": 49700}
        head = "/proj/whoosh sound.mp3"
        tail = "/proj/Production/assets/sound_library/sfx/exit resolution video sfx.mp3"

        def _resolve(_h, _slot_key, filename):
            if "whoosh" in filename:
                return head
            if "exit resolution" in filename:
                return tail
            return None

        with unittest.mock.patch(
            "server_handlers.stitch_editor._resolve_stitch_slot_tail_sfx_path",
            side_effect=_resolve,
        ):
            self.assertTrue(ensure_stitch_slot_canonical_default_sfx_cues(h, "resolution", slot))

        self.assertEqual(len(slot["sfx_cues"]), 2)
        head_cue = next(c for c in slot["sfx_cues"] if "whoosh" in c["name"].lower())
        tail_cue = next(c for c in slot["sfx_cues"] if "exit resolution" in c["name"].lower())
        self.assertTrue(head_cue.get("auto_default"))
        self.assertTrue(tail_cue.get("auto_default"))
        self.assertEqual(head_cue["offset_ms"], 0)
        self.assertEqual(head_cue["duration_ms"], 3104)
        self.assertEqual(tail_cue["offset_ms"], 49700 - tail_cue["duration_ms"])

    def test_reanchor_updates_stale_tail_offset_on_duration_change(self):
        from server_handlers.stitch_editor import ensure_stitch_slot_canonical_default_sfx_cues

        h = MagicMock()
        h._ffprobe_duration_ms.side_effect = lambda p: {
            "whoosh sound.mp3": 3104,
        }.get(Path(p).name, 160287)
        slot = {
            "video_path": "Production/Event_2/intro.mp4",
            "video_dur_ms": 160287,
            "sfx_cues": [{
                "id": "cue_old",
                "name": "whoosh sound.mp3",
                "source_path": "/proj/whoosh sound.mp3",
                "offset_ms": 169852,
                "duration_ms": 3104,
                "auto_default": True,
            }],
        }
        head = "/proj/whoosh sound.mp3"

        with unittest.mock.patch(
            "server_handlers.stitch_editor._resolve_stitch_slot_tail_sfx_path",
            return_value=head,
        ):
            self.assertTrue(ensure_stitch_slot_canonical_default_sfx_cues(h, "intro", slot))

        cue = slot["sfx_cues"][0]
        self.assertEqual(cue["offset_ms"], 160287 - 3104)
        self.assertEqual(len(slot["sfx_cues"]), 1)

    def test_resolution_head_skips_when_dismissed(self):
        from server_handlers.stitch_editor import ensure_stitch_slot_canonical_default_sfx_cues

        h = MagicMock()
        slot = {
            "video_path": "Production/Event_2/resolution.mp4",
            "video_dur_ms": 49700,
            "resolution_head_sfx_default_dismissed": True,
        }
        tail = "/proj/Production/assets/sound_library/sfx/exit resolution video sfx.mp3"

        with unittest.mock.patch(
            "server_handlers.stitch_editor._resolve_stitch_slot_tail_sfx_path",
            return_value=tail,
        ), unittest.mock.patch.object(h, "_ffprobe_duration_ms", return_value=5180):
            self.assertTrue(ensure_stitch_slot_canonical_default_sfx_cues(h, "resolution", slot))

        self.assertEqual(len(slot["sfx_cues"]), 1)
        self.assertIn("exit resolution", slot["sfx_cues"][0]["name"].lower())

    def test_phase_a_no_auto_tail_boundary_cue(self):
        from server_handlers.stitch_editor import ensure_stitch_slot_default_tail_sfx_cue

        h = MagicMock()
        slot = {"video_path": "Production/Event_2/phase_a.mp4", "video_dur_ms": 22337}
        self.assertFalse(ensure_stitch_slot_default_tail_sfx_cue(h, "phase_a", slot))
        self.assertFalse(slot.get("sfx_cues"))

    def test_strip_stale_boundary_cues_on_load_path(self):
        from server_handlers.stitch_editor import strip_stale_pipeline_boundary_slot_cues

        slots = {
            "phase_a": {
                "video_path": "a.mp4",
                "sfx_cues": [{"name": "windy_magic.mp3", "auto_default": True}],
            },
        }
        self.assertTrue(strip_stale_pipeline_boundary_slot_cues(slots))
        self.assertEqual(slots["phase_a"]["sfx_cues"], [])

    def test_persist_writes_sfx_cues_and_dismiss_flags(self):
        from server_handlers.stitch_editor import _persist_stitch_job_canonical_audio

        state = {
            "jobs": {
                "Event_2_stitch": {
                    "slots": {
                        "phase_a": {"video_path": "Production/Event_2/a.mp4"},
                    },
                },
            },
        }
        normalized = {
            "phase_a": {
                "video_path": "Production/Event_2/a.mp4",
                "ambient_bed": "ambient bed pretty option2",
                "video_dur_ms": 22337,
                "sfx_cues": [
                    {"id": "cue_ab", "name": "windy_magic.mp3", "auto_default": True, "offset_ms": 20000},
                ],
            },
        }
        _persist_stitch_job_canonical_audio(state, "Event_2_stitch", normalized)
        slot = state["jobs"]["Event_2_stitch"]["slots"]["phase_a"]
        self.assertEqual(slot["ambient_bed"], "ambient bed pretty option2")
        self.assertEqual(len(slot["sfx_cues"]), 1)
        self.assertEqual(slot["sfx_cues"][0]["name"], "windy_magic.mp3")

    def test_load_job_source_exposes_defaults_applied(self):
        src = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        block = src.split("def handle_stitch_load_job", 1)[1].split("\ndef handle_stitch_save_job", 1)[0]
        assert "defaults_applied" in block
        assert "STITCH_CANONICAL_DEFAULTS_PERSIST_V1" in block

    def test_ensure_job_slot_defaults_applies_all_tail_slots(self):
        src = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        block = src.split("def ensure_job_slot_defaults", 1)[1].split("\ndef collect_stitch_job_slot_warnings", 1)[0]
        assert "STITCH_SLOT_CANONICAL_DEFAULT_SFX" in block
        assert "ensure_stitch_slot_canonical_default_sfx_cues" in block

    def test_client_canonical_defaults_markers(self):
        src = (TOOLS / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx").read_text(
            encoding="utf-8",
        )
        assert "STITCH_SLOT_CANONICAL_DEFAULTS_V1" in src
        assert "resolution_head_sfx_default_dismissed" in src
        assert "resolution_tail_sfx_default_dismissed" in src
        assert "STITCH_AMBIENT_SELECT_HYDRATE_V1" in src
        assert "ambientSelectOptions" in src
        assert "persistJobSlotsByName" in src
        assert "defaults_applied" in src
