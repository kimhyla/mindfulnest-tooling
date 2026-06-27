"""Still-insert Ken Burns → O3 slot clip (Beat Gen restore)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import beat_generator as bg


def test_beat_is_still_insert():
    assert bg.beat_is_still_insert({"pipeline": "still_insert"})
    assert bg.beat_is_still_insert({"beat_render_mode": "still_insert"})
    assert not bg.beat_is_still_insert({"pipeline": "kling_o3"})
    assert not bg.beat_is_still_insert({})


def test_ken_burns_zoompan_vf_uses_prescale_and_focal_center():
    vf = bg._ken_burns_zoompan_vf(
        pan_x_pct=50,
        pan_y_pct=50,
        zoom_start=1.0,
        zoom_end=1.08,
        total_frames=120,
        fps=24,
        duration_s=5.0,
    )
    assert "scale=3840:2160" in vf
    assert "flags=lanczos" in vf
    assert "zoompan" not in vf
    assert "min(t/5.000000,1)" in vf
    assert "(iw-ow)*0.5000" in vf
    assert "(ih-oh)*0.5000" in vf
    assert "s=1280x720" not in vf
    assert "scale=1280:720" in vf


def test_resolve_still_source_prefers_library_drop(tmp_path: Path):
    still = tmp_path / "scene.png"
    still.write_bytes(b"png")
    beat = {
        "accepted_library_ref": {"abs_path": str(still)},
        "bg_ref_image": {"abs_path": str(tmp_path / "other.png")},
    }
    assert bg.resolve_still_source_abs_path(beat) == still.resolve()


def test_resolve_still_source_falls_back_to_bg_ref(tmp_path: Path):
    still = tmp_path / "bg.webp"
    still.write_bytes(b"webp")
    beat = {"bg_ref_image": {"abs_path": str(still)}}
    assert bg.resolve_still_source_abs_path(beat) == still.resolve()


def test_extract_still_insert_tts_parses_embedded_speaker():
    beat = {
        "dialogue_text": (
            "Ancient mossy ruins. Lorelai [muttering, lost]: "
            "'Its got to be around here somewhere!'"
        ),
        "speaker": "[Stage Direction]",
    }
    parsed = bg.extract_still_insert_tts(beat)
    assert parsed is not None
    assert parsed["speaker"] == "Lorelai"
    assert parsed["text"] == "Its got to be around here somewhere!"
    assert "muttering" in parsed["tts_text"]


def test_extract_still_insert_tts_double_bracket_emotion_and_scene_prefix():
    beat = {
        "dialogue_text": (
            "Ancient mossy ruins in warm forest light; Lorelai with archaeological satchel. "
            'Lorelai [[muttering, lost]]: "Oooh [pause] ... Its got to be around here somewhere!"'
        ),
        "speaker": "Lorelai",
    }
    parsed = bg.extract_still_insert_tts(beat)
    assert parsed is not None
    assert parsed["speaker"] == "Lorelai"
    assert parsed["text"] == "Oooh . Its got to be around here somewhere!"
    assert parsed["tts_text"].startswith("[muttering, lost]")


def test_extract_still_insert_tts_lorelai_says_colon_format():
    beat = {
        "kling_o3_prompt": (
            'Lorelai says:  "[proud] Well I can read the picture-writing [pause]... '
            "it says ... Feel ... What's ... Real.\""
        ),
        "speaker": "Lorelai",
        "pipeline": "still_insert",
    }
    parsed = bg.extract_still_insert_tts(beat)
    assert parsed is not None
    assert parsed["speaker"] == "Lorelai"
    assert parsed["text"] == "Well I can read the picture-writing . it says . Feel . What's . Real."
    assert "warm excited conversational pace" in parsed["tts_text"]
    assert "scholarly" in parsed["tts_text"]


def test_extract_still_insert_tts_pronoun_says_does_not_steal_named_character():
    """Regression: ``Loral ... she says:`` must resolve to Lorelai, not pronoun ``she``."""
    beat = {
        "kling_o3_prompt_still": (
            'Loral speaks as if reading, she says:  "Let .... the.... flowers... bloom"'
        ),
        "kling_o3_prompt": (
            'Loral speaks as if reading, she says:  "Let .... the.... flowers... bloom"'
        ),
        "dialogue_text": "Let . the. flowers. bloom",
        "speaker": "Character",
        "pipeline": "still_insert",
    }
    parsed = bg.extract_still_insert_tts(beat)
    assert parsed is not None
    assert parsed["speaker"] == "Lorelai"
    assert "flowers" in parsed["text"].lower()
    assert "she says" not in parsed["tts_text"].lower()
    assert "warm excited conversational pace" in parsed["tts_text"]


def test_normalize_dialogue_speaker_strips_says_suffix():
    from beat_extract_policy import normalize_dialogue_speaker

    assert normalize_dialogue_speaker("Lorelai says") == "Lorelai"
    assert normalize_dialogue_speaker("Arlo speaks") == "Arlo"


def test_extract_still_insert_tts_from_kling_o3_prompt_when_dialogue_empty():
    beat = {
        "dialogue_text": "",
        "kling_o3_prompt": "[muttering, lost]: Oooh .... Its got to be around here somewhere!",
        "speaker": "Lorelai",
        "pipeline": "still_insert",
    }
    parsed = bg.extract_still_insert_tts(beat)
    assert parsed is not None
    assert parsed["speaker"] == "Lorelai"
    assert parsed["text"] == "Oooh . Its got to be around here somewhere!"
    assert parsed["tts_text"].startswith("[muttering, lost]")


def test_extract_still_insert_tts_whisper_delivery_malformed_quote():
    """Regression: colon token ``whispering:`` must not steal speaker from Lorelai."""
    beat = {
        "kling_o3_prompt": (
            'Loral whispers, in an awed whisper, disbelieving, awed, incredulous, whispering:  '
            '"No way ... is it happening again?'
        ),
        "speaker": "Lorelai",
        "pipeline": "still_insert",
        "still_tts_source_text": '"No way . is it happening again?',
    }
    parsed = bg.extract_still_insert_tts(beat)
    assert parsed is not None
    assert parsed["speaker"] == "Lorelai"
    assert parsed["tts_text"].startswith("[")
    assert "scholarly" in parsed["tts_text"]
    assert "whisper" not in parsed["tts_text"].lower()
    assert parsed["fingerprint"] != beat["still_tts_source_text"]


def test_extract_still_insert_tts_whisper_delivery_in_elevenlabs_payload():
    beat = {
        "kling_o3_prompt": (
            'Loral whispers, in an awed whisper, disbelieving, awed, incredulous, whispering:  '
            '"No way ... Is it happening again?"'
        ),
        "speaker": "Lorelai",
        "pipeline": "still_insert",
    }
    parsed = bg.extract_still_insert_tts(beat)
    assert parsed is not None
    assert "scholarly" in parsed["tts_text"]
    assert parsed["tts_text"].startswith("[")
    assert "No way" in parsed["tts_text"]
    assert parsed["fingerprint"] == parsed["tts_text"]
    assert "warm excited" in " ".join(parsed["delivery"]).lower()


def test_extract_still_insert_tts_bracket_delivery_prefix():
    beat = {
        "kling_o3_prompt": '[muttering, lost]: "Hello ruins!"',
        "speaker": "Lorelai",
        "pipeline": "still_insert",
    }
    parsed = bg.extract_still_insert_tts(beat)
    assert parsed is not None
    assert parsed["tts_text"].startswith("[muttering, lost]")
    assert "Hello ruins!" in parsed["tts_text"]


def test_still_tts_fingerprint_changes_when_delivery_changes_but_spoken_same():
    spoken = '"No way ... Is it happening again?"'
    beat_neutral = {
        "kling_o3_prompt": f'Lorelai says calmly: {spoken}',
        "speaker": "Lorelai",
    }
    beat_whisper = {
        "kling_o3_prompt": (
            'Loral whispers, in an awed whisper, disbelieving, awed, incredulous, whispering:  '
            + spoken
        ),
        "speaker": "Lorelai",
    }
    a = bg.extract_still_insert_tts(beat_neutral)
    b = bg.extract_still_insert_tts(beat_whisper)
    assert a and b
    assert a["text"] == b["text"]
    assert a["fingerprint"] != b["fingerprint"]


def test_build_still_insert_elevenlabs_text_empty_delivery():
    assert bg.build_still_insert_elevenlabs_text([], "Hello") == "Hello"


def test_sidcar_merge_preserves_still_tts_source_text():
    assert "still_tts_source_text" in bg.SIDECAR_MERGE_PRESERVE_FIELDS
    assert "audio_file" in bg.SIDECAR_MERGE_PRESERVE_FIELDS


def test_extract_still_insert_tts_prefers_kling_prompt_over_stale_dialogue():
    beat = {
        "dialogue_text": "Oooh . Its got to be around here somewhere!",
        "kling_o3_prompt": "[worried]: Hmmm .... Its gotta be around here somewhere!",
        "speaker": "Lorelai",
        "pipeline": "still_insert",
        "still_tts_source_text": "Oooh . Its got to be around here somewhere!",
    }
    parsed = bg.extract_still_insert_tts(beat)
    assert parsed is not None
    assert parsed["text"].startswith("Hmmm")
    assert parsed["tts_text"].startswith("[worried]")
    assert bg.sync_beat_dialogue_from_kling_prompt(beat) is True
    assert beat["dialogue_text"].startswith("Hmmm")


def test_sync_beat_dialogue_from_kling_prompt_still_insert():
    beat = {
        "pipeline": "still_insert",
        "dialogue_text": "",
        "kling_o3_prompt": '[muttering, lost]: "Hello ruins!"',
        "speaker": "Lorelai",
    }
    assert bg.sync_beat_dialogue_from_kling_prompt(beat) is True
    assert beat["dialogue_text"] == "Hello ruins!"
    beat = {
        "dialogue_text": "Wide establishing shot of the forest.",
        "speaker": "[Stage Direction]",
    }
    assert bg.extract_still_insert_tts(beat) is None


def test_resolve_still_insert_render_duration_from_audio(tmp_path: Path):
    audio = tmp_path / "line.mp3"
    audio.write_bytes(b"mp3")
    with patch.object(bg, "_ffprobe_duration", return_value=7.5):
        dur = bg.resolve_still_insert_render_duration_from_audio(audio)
    assert dur == 7.5 + bg.STILL_INSERT_AUDIO_TAIL_PAD_S


def test_resolve_still_insert_render_duration_without_audio(tmp_path: Path):
    beat = {"beat_id": "bg_test", "pipeline": "still_insert"}
    with patch.object(bg, "resolve_bg_beat_tts_audio_path", return_value=None):
        dur = bg.resolve_still_insert_render_duration(beat, tmp_path, fallback=4.0)
    assert dur == 4.0


def test_render_still_insert_o3_clip_uses_tts_duration(tmp_path: Path):
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    still = event_dir / "still.png"
    still.write_bytes(b"png")
    audio = event_dir / "tts.mp3"
    audio.write_bytes(b"mp3")
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_10",
        "pipeline": "still_insert",
        "bg_ref_image": {"abs_path": str(still)},
    }
    captured: dict = {}

    def _fake_ken_burns(_beat, _still_path, *_args, **kwargs):
        captured["duration"] = _args[-1] if _args else kwargs.get("duration")
        out = Path(kwargs["out_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp4")
        return {"video_path": str(out), "preview_path": _still_path}

    with patch.object(bg, "run_ken_burns", side_effect=_fake_ken_burns), patch.object(
        bg, "resolve_bg_beat_tts_audio_path", return_value=audio,
    ), patch.object(bg, "_ffprobe_duration", return_value=6.8), patch.object(
        bg, "_ffmpeg_stitch_module",
    ) as mock_fs_mod:
        mock_fs_mod.return_value.trim_normalized = lambda *a, **k: None
        result = bg.render_still_insert_o3_clip(
            beat, event_dir, method="ken_burns", duration=4.0, slot_index=0,
        )

    assert captured["duration"] == 6.8 + bg.STILL_INSERT_AUDIO_TAIL_PAD_S
    assert result["duration_s"] == 6.8 + bg.STILL_INSERT_AUDIO_TAIL_PAD_S
    assert result["tts_mixed"] is True


def test_render_still_insert_replaces_prior_still_in_same_slot(tmp_path: Path):
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    still = event_dir / "still.png"
    still.write_bytes(b"png")
    old_clip = event_dir / "old.mp4"
    old_clip.write_bytes(b"old")
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_01",
        "pipeline": "still_insert",
        "bg_ref_image": {"abs_path": str(still)},
        "kling_o3_options": [{
            "key": "old",
            "video_path": str(old_clip),
            "source": "still_insert_ken_burns",
            "slot_index": 0,
        }],
    }

    def _fake_ken_burns(_beat, _still_path, *_args, **kwargs):
        out = Path(kwargs["out_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp4")
        return {"video_path": str(out), "preview_path": _still_path}

    with patch.object(bg, "run_ken_burns", side_effect=_fake_ken_burns), patch.object(
        bg, "resolve_bg_beat_tts_audio_path", return_value=None,
    ):
        result = bg.render_still_insert_o3_clip(
            beat, event_dir, method="ken_burns", duration=4.0, slot_index=0,
        )

    assert len(beat["kling_o3_options"]) == 1
    assert beat["kling_o3_options"][0]["video_path"] == result["video_path"]


def test_render_still_insert_o3_clip_writes_o3_fields(tmp_path: Path):
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    still = event_dir / "still.png"
    still.write_bytes(b"png")
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_01",
        "pipeline": "still_insert",
        "bg_ref_image": {"abs_path": str(still)},
    }

    def _fake_ken_burns(_beat, _still_path, *_args, **kwargs):
        out = Path(kwargs["out_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp4")
        return {"video_path": str(out), "preview_path": _still_path}

    with patch.object(bg, "run_ken_burns", side_effect=_fake_ken_burns), patch.object(
        bg, "resolve_bg_beat_tts_audio_path", return_value=None,
    ):
        result = bg.render_still_insert_o3_clip(
            beat, event_dir, method="ken_burns", duration=4.0, slot_index=0,
        )

    assert Path(result["video_path"]).is_file()
    assert beat["kling_o3_status"] == "still_rendered"
    assert beat["status"] == "draft"
    assert beat["kling_o3_video_path"] == result["video_path"]
    assert any(o.get("video_path") == result["video_path"] for o in beat["kling_o3_options"])


def test_still_insert_sidecar_trim_pending():
    assert bg.still_insert_sidecar_trim_pending({"kling_o3_trim_start": 0.5})
    assert bg.still_insert_sidecar_trim_pending({"kling_o3_trim_back": 0.2})
    assert not bg.still_insert_sidecar_trim_pending({"kling_o3_trim_start": 0})


def test_bake_still_insert_trim_into_clip(tmp_path: Path, monkeypatch):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    baked = tmp_path / "clip_trimmed.mp4"

    def _fake_materialize(beat, dest, *, source_path=None):
        dest.write_bytes(b"trimmed")
        return dest

    monkeypatch.setattr(bg, "_ffprobe_duration", lambda _p: 4.0)
    monkeypatch.setattr(bg, "kling_o3_trim_is_active", lambda beat, raw_dur=None: True)
    monkeypatch.setattr(bg, "materialize_kling_o3_trimmed_clip", _fake_materialize)

    beat = {
        "kling_o3_video_path": str(clip),
        "kling_o3_trim_start": 0.5,
        "kling_o3_trim_back": 0.3,
        "kling_o3_options": [{"key": "a", "video_path": str(clip)}],
    }
    result = bg.bake_still_insert_trim_into_clip(beat)
    assert result["baked"] is True
    assert beat["kling_o3_video_path"] == str(baked.resolve())
    assert beat["kling_o3_options"][0]["video_path"] == str(baked.resolve())
    assert "kling_o3_trim_start" not in beat


def test_production_server_registers_render_still_clip_route():
    text = (Path(__file__).resolve().parent.parent / "production_server.py").read_text(
        encoding="utf-8",
    )
    assert "/api/bg/render-still-clip" in text
    assert "_handle_bg_render_still_clip" in text


def test_endpoints_and_bgtab_wiring():
    root = Path(__file__).resolve().parent.parent / "storyboard-v2" / "src"
    endpoints = (root / "api" / "endpoints.ts").read_text(encoding="utf-8")
    assert "bg_render_still_clip" in endpoints
    bgtab = (root / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "isStillInsertBeat" in bgtab
    assert "Build still video (+ TTS)" in bgtab
    assert "Approve still for stitch" in bgtab
    assert "bg_render_still_clip" in bgtab


def test_render_still_clip_handler_initializes_bg_before_use():
    """Regression: ff53fd7 used bg.STILL_INSERT_DEFAULT_DURATION_S before bg = _bg_module()."""
    text = (
        Path(__file__).resolve().parent.parent / "server_handlers" / "background.py"
    ).read_text(encoding="utf-8")
    start = text.index("def handle_bg_render_still_clip(")
    end = text.index("\ndef handle_bg_accept_option", start)
    block = text[start:end]
    bg_assign = block.index("bg = _bg_module()")
    first_bg_use = block.index("bg.")
    assert bg_assign < first_bg_use, (
        "handle_bg_render_still_clip must assign bg = _bg_module() before any bg.* access"
    )


def test_normalize_still_insert_approval_status_demotes_legacy_auto_approve():
    beat = {
        "pipeline": "still_insert",
        "kling_o3_status": "approved",
        "status": "approved",
        "kling_o3_video_path": "/tmp/bg_arc1_event2_pre_beat_01_still_insert_123_tts.mp4",
        "kling_o3_options": [{
            "source": "still_insert_ken_burns",
            "video_path": "/tmp/bg_arc1_event2_pre_beat_01_still_insert_123_tts.mp4",
        }],
    }
    assert bg.normalize_still_insert_approval_status(beat) is True
    assert beat["kling_o3_status"] == "still_rendered"
    assert beat["status"] == "draft"


def test_normalize_still_insert_preserves_explicit_stitch_approve():
    beat = {
        "pipeline": "still_insert",
        "kling_o3_status": "approved",
        "status": "approved",
        "kling_o3_still_stitch_approved": True,
        "kling_o3_video_path": "/tmp/bg_arc1_event2_pre_beat_01_still_insert_123_tts.mp4",
        "kling_o3_options": [{
            "source": "still_insert_ken_burns",
            "video_path": "/tmp/bg_arc1_event2_pre_beat_01_still_insert_123_tts.mp4",
        }],
    }
    assert bg.normalize_still_insert_approval_status(beat) is False
    assert beat["kling_o3_status"] == "approved"
    assert beat["status"] == "approved"


def test_heal_still_insert_option_keys_assigns_stable_key_from_path():
    beat = {
        "pipeline": "still_insert",
        "beat_id": "bg_arc1_event1_post_beat_21",
        "kling_o3_options": [{
            "source": "still_insert_ken_burns",
            "video_path": "/tmp/bg_arc1_event1_post_beat_21_still_insert_123_tts.mp4",
        }],
    }
    assert bg.heal_still_insert_option_keys(beat) is True
    assert beat["kling_o3_options"][0]["key"] == "bg_arc1_event1_post_beat_21_still_insert_123_tts"


def test_bgtab_still_approve_banner_and_keyless_tile_button():
    bgtab = (
        Path(__file__).resolve().parent.parent / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
    ).read_text(encoding="utf-8")
    assert "bg-still-approve-banner" in bgtab
    assert "stillBeatNeedsStitchApprove" in bgtab
    assert "resolveStillStitchApproveOptionKey" in bgtab
    assert "isStillDraft && onApproveStill ? (" in bgtab
    assert "isStillDraft && onApproveStill && option.key" not in bgtab
    assert "onClick={keyMissing || isStillDraft ? undefined : onClick}" not in bgtab
    assert "still_approve: opts?.stillApprove === true && opts?.draftOnly !== true" in bgtab
    assert "draftOnly: true" in bgtab


def test_still_draft_select_does_not_approve():
    src = (
        Path(__file__).resolve().parent.parent / "server_handlers" / "background.py"
    ).read_text(encoding="utf-8")
    assert "_apply_still_draft_pointer" in src
    assert "still_approve" in src
    assert 'beat["kling_o3_status"] = "still_rendered"' in src
    assert 'beat.pop("kling_o3_still_stitch_approved", None)' in src


def test_normalize_kling_o3_option_slots_marks_video_path_exists(tmp_path: Path):
    clip = tmp_path / "slot0.mp4"
    clip.write_bytes(b"mp4")
    beat = {
        "kling_o3_options": [
            {"slot_index": 0, "video_path": str(clip), "key": "slot0"},
            {"slot_index": 1, "video_path": str(tmp_path / "missing.mp4"), "key": "slot1"},
        ],
    }
    slots = bg.normalize_kling_o3_option_slots(beat)
    assert slots[0]["video_path_exists"] is True
    assert slots[1]["video_path_exists"] is False
