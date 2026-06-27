"""Ambient + SFX mix level normalization for all stitch slots."""
from __future__ import annotations

import os
import unittest
import unittest.mock as mock
from pathlib import Path

from server_handlers.stitch_editor import (
    STITCH_AMBIENT_BED_VOLUME,
    STITCH_DEFAULT_AMBIENT_BEDS,
    STITCH_SLOT_ORDER,
    STITCH_SFX_CUE_DEFAULT_VOLUME,
    _hydrate_slot_ambient_paths,
    _resolve_stitch_ambient_bed_path,
    _slot_merge_worthy,
    apply_stitch_slot_default_ambient_preset,
    normalize_job_slots_audio,
    normalize_slot_audio_mix_levels,
    stitch_upsert_event_slot,
    _persist_stitch_job_canonical_audio,
)


class _MockStitchState:
    def __init__(self, initial=None):
        self.state = initial or {"jobs": {}}

    def read_state(self):
        return self.state

    def mutate_state(self, fn):
        fn(self.state)


class _MockHandler:
    def _stitch_project_root(self) -> Path:
        return Path(
            os.environ.get(
                "MN_TEST_PROJECT_ROOT",
                "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files",
            )
        )

    def _stitch_resolve_path(self, raw: str) -> str:
        return raw

    def _ffprobe_duration_ms(self, _path) -> int:
        return 0


class StitchSlotAudioMixTests(unittest.TestCase):
    def test_slot_merge_worthy_accepts_ambient_only_patch(self):
        self.assertTrue(_slot_merge_worthy({"ambient_bed": "Intro video ambient bed"}))

    def test_hydrate_replaces_stale_path_when_preset_changes(self):
        h = _MockHandler()
        slots = [
            {
                "ambient_bed": "Intro video ambient bed",
                "ambient_bed_path": "/stale/old/path.mp3",
            }
        ]
        _hydrate_slot_ambient_paths(h, slots)
        resolved = _resolve_stitch_ambient_bed_path(h, "Intro video ambient bed")
        if resolved:
            self.assertEqual(slots[0]["ambient_bed_path"], resolved)
            self.assertNotEqual(slots[0]["ambient_bed_path"], "/stale/old/path.mp3")
        else:
            self.skipTest("Intro video ambient bed.mp3 not on disk in this environment")

    def test_hydrate_sets_canonical_ambient_volume(self):
        h = _MockHandler()
        slots = [{"ambient_bed": "Intro video ambient bed"}]
        _hydrate_slot_ambient_paths(h, slots)
        if slots[0].get("ambient_bed_path"):
            self.assertEqual(slots[0].get("ambient_volume"), STITCH_AMBIENT_BED_VOLUME)

    def test_canonical_volume_is_quiet_under_speech(self):
        self.assertEqual(STITCH_AMBIENT_BED_VOLUME, 0.15)

    def test_hydrate_clears_path_when_preset_cleared(self):
        h = _MockHandler()
        slots = [{"ambient_bed": "", "ambient_bed_path": "/some/path.mp3"}]
        _hydrate_slot_ambient_paths(h, slots)
        self.assertNotIn("ambient_bed_path", slots[0])

    def test_legacy_loud_ambient_clamped_for_all_slot_keys(self):
        job_slots = {
            key: {
                "video_path": f"Production/Event_1/{key}.mp4",
                "ambient_bed": "phase a ambient bed" if key == "phase_a" else "",
                "ambient_volume": 0.6,
            }
            for key in STITCH_SLOT_ORDER
        }
        job_slots["intro"]["ambient_bed"] = "Intro video ambient bed"
        normalize_job_slots_audio(job_slots)
        self.assertEqual(job_slots["intro"]["ambient_volume"], STITCH_AMBIENT_BED_VOLUME)
        self.assertEqual(job_slots["phase_a"]["ambient_volume"], STITCH_AMBIENT_BED_VOLUME)
        self.assertEqual(job_slots["phase_b"]["ambient_bed"], STITCH_DEFAULT_AMBIENT_BEDS["phase_b"])
        self.assertEqual(job_slots["phase_b"]["ambient_volume"], STITCH_AMBIENT_BED_VOLUME)
        self.assertEqual(job_slots["resolution"]["ambient_bed"], STITCH_DEFAULT_AMBIENT_BEDS["resolution"])

    def test_sfx_cues_get_canonical_defaults_on_any_slot(self):
        slot = {
            "video_path": "Production/Event_1/resolution.mp4",
            "sfx_cues": [{"id": "c1", "source_path": "/x.mp3", "offset_ms": 1000}],
        }
        normalize_slot_audio_mix_levels(slot)
        cue = slot["sfx_cues"][0]
        self.assertEqual(cue["volume"], STITCH_SFX_CUE_DEFAULT_VOLUME)
        self.assertEqual(cue["fadein_ms"], 300)
        self.assertEqual(cue["fadeout_ms"], 1200)

    def test_default_ambient_presets_match_canonical_map(self):
        self.assertEqual(STITCH_DEFAULT_AMBIENT_BEDS["intro"], "Intro video ambient bed")
        self.assertEqual(STITCH_DEFAULT_AMBIENT_BEDS["standalone"], "Intro video ambient bed")
        self.assertEqual(STITCH_DEFAULT_AMBIENT_BEDS["phase_a"], "ambient bed pretty option2")
        self.assertEqual(STITCH_DEFAULT_AMBIENT_BEDS["phase_b"], "ambient bed pretty option")
        self.assertEqual(STITCH_DEFAULT_AMBIENT_BEDS["resolution"], "ambien bed pretty option4")

    def test_default_ambient_applied_on_upsert_when_empty(self):
        h = _MockHandler()
        h.app = type("A", (), {"stitch_state": _MockStitchState()})()
        with mock.patch(
            "server_handlers.stitch_editor.stitch_slot_export_media_preflight",
            return_value=(60_000, []),
        ), mock.patch(
            "server_handlers.stitch_editor.sync_stitch_slot_video_dur_ms",
            return_value=False,
        ):
            stitch_upsert_event_slot(
                h,
                "Event_test",
                "phase_b",
                {"video_path": "Production/Event_test/phase_b.mp4"},
            )
        slot = h.app.stitch_state.state["jobs"]["Event_test_stitch"]["slots"]["phase_b"]
        self.assertEqual(slot["ambient_bed"], STITCH_DEFAULT_AMBIENT_BEDS["phase_b"])
        self.assertEqual(slot["ambient_volume"], STITCH_AMBIENT_BED_VOLUME)

    def test_default_ambient_preset_sets_volume_without_extra_normalize(self):
        slot = {"video_path": "Production/Event_1/resolution.mp4"}
        self.assertTrue(apply_stitch_slot_default_ambient_preset("resolution", slot))
        self.assertEqual(slot["ambient_volume"], STITCH_AMBIENT_BED_VOLUME)

    def test_job_canonical_audio_needs_persist_when_legacy_volume(self):
        live = {
            "intro": {
                "ambient_bed": "Intro video ambient bed",
                "ambient_volume": 0.6,
            }
        }
        normalized = {
            "intro": {
                "ambient_bed": "Intro video ambient bed",
                "ambient_volume": STITCH_AMBIENT_BED_VOLUME,
            }
        }
        from server_handlers.stitch_editor import _job_canonical_audio_needs_persist

        self.assertTrue(_job_canonical_audio_needs_persist(live, normalized))

    def test_persist_stitch_job_canonical_audio_writes_volume(self):
        state = {
            "jobs": {
                "Event_1_stitch": {
                    "slots": {
                        "phase_a": {
                            "video_path": "Production/Event_1/phase_a.mp4",
                            "ambient_bed": "ambient bed pretty option2",
                            "ambient_volume": 0.6,
                            "ambient_bed_path": "/stale/bed.mp3",
                        }
                    }
                }
            }
        }
        normalized = {
            "phase_a": {
                "video_path": "Production/Event_1/phase_a.mp4",
                "ambient_bed": "ambient bed pretty option2",
                "ambient_volume": STITCH_AMBIENT_BED_VOLUME,
            }
        }
        _persist_stitch_job_canonical_audio(state, "Event_1_stitch", normalized)
        slot = state["jobs"]["Event_1_stitch"]["slots"]["phase_a"]
        self.assertEqual(slot["ambient_volume"], STITCH_AMBIENT_BED_VOLUME)
        self.assertNotIn("ambient_bed_path", slot)

    def test_default_ambient_does_not_overwrite_existing(self):
        slot = {
            "video_path": "Production/Event_1/intro.mp4",
            "ambient_bed": "custom bed",
        }
        self.assertFalse(apply_stitch_slot_default_ambient_preset("intro", slot))
        self.assertEqual(slot["ambient_bed"], "custom bed")


if __name__ == "__main__":
    unittest.main()
