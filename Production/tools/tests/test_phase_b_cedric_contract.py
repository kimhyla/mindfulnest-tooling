"""Contract tests for Phase B Cedric canonical base clip."""
from __future__ import annotations

from phase_b_cedric_contract import (
    PHASE_B_CEDRIC_BASE_CLIP_CANONICAL,
    coerce_phase_b_cedric_base_clip_id,
    phase_b_cedric_base_clip_deprecated,
)


def test_canonical_is_v6() -> None:
    assert PHASE_B_CEDRIC_BASE_CLIP_CANONICAL == "cedric_idle_newstyle_v6"


def test_deprecated_ids_coerce_to_v6() -> None:
    for old in (
        "cedric_idle_newstyle_v1",
        "cedric_idle_newstyle_v2",
        "cedric_idle_newstyle_v3",
        "cedric_idle_newstyle_v4",
        "cedric_idle_newstyle_v5",
        "cedric_idle_camera_v2",
        "cedric_idle_study_v1",
        "placeholder_cedric_base_v1",
        None,
        "",
    ):
        assert phase_b_cedric_base_clip_deprecated(old)
        assert coerce_phase_b_cedric_base_clip_id(old) == "cedric_idle_newstyle_v6"


def test_v6_not_deprecated() -> None:
    assert not phase_b_cedric_base_clip_deprecated("cedric_idle_newstyle_v6")
    assert coerce_phase_b_cedric_base_clip_id("cedric_idle_newstyle_v6") == "cedric_idle_newstyle_v6"


def test_fireplace_smoke_lock_in_base_generator() -> None:
    from phase_b_cedric_contract import (
        PHASE_B_DESK_PROPS_LOCK,
        PHASE_B_FIREPLACE_SMOKE_LOCK,
        PHASE_B_MOUTH_FROZEN_LOCK,
        PHASE_B_MUG_PLACEMENT_LOCK,
        PHASE_B_MUG_STEAM_LOCK,
    )
    import phase_b_cedric_lipsync_base as base_mod

    assert "inside the fireplace opening" in PHASE_B_FIREPLACE_SMOKE_LOCK
    assert "ALWAYS ON" not in PHASE_B_MUG_STEAM_LOCK
    assert "zero steam" in PHASE_B_MUG_STEAM_LOCK.lower()
    assert "MOUTH LOCK" in PHASE_B_MOUTH_FROZEN_LOCK
    assert "no lip-sync" in PHASE_B_MOUTH_FROZEN_LOCK
    sip = base_mod.build_cedric_idle_prompt(allow_sip=True)
    no_sip = base_mod.build_cedric_idle_prompt(allow_sip=False)
    assert "at most ONE calm coffee sip" in sip
    assert "DO NOT touch" in no_sip
    assert "frame one" in sip
    assert "mug steam" in base_mod.NEGATIVE
    assert "lipsync" in base_mod.NEGATIVE
    assert "bookend_neutral" in base_mod._generate_idle_clip.__code__.co_varnames
    assert "allow_sip" in base_mod._generate_idle_clip.__code__.co_varnames


def test_alternating_sip_segments() -> None:
    import phase_b_cedric_lipsync_base as base_mod

    assert base_mod.build_cedric_idle_prompt(allow_sip=True) != base_mod.build_cedric_idle_prompt(
        allow_sip=False
    )


def test_bookend_prompt() -> None:
    import phase_b_cedric_lipsync_base as base_mod

    p = base_mod.build_cedric_idle_prompt(allow_sip=False, bookend_pose=True)
    assert "BOOKEND POSE" in p
    assert "close-mouthed smile" in p
    assert "zero mug steam" in p
    assert "DO NOT touch" in p
