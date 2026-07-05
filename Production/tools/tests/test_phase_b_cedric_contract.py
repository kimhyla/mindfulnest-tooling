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
