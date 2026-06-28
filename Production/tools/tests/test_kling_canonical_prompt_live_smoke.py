"""KLING_V2_LIVE_SMOKE_SKIP_STILL_INSERT_V1 — deploy live smoke skips still-insert beats."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "scripts" / "smoke_kling_canonical_prompt_shape_live.sh"
VERIFY = REPO / "scripts" / "verify_kling_canonical_prompt_shape_durability.sh"


def test_live_smoke_skips_still_insert_via_beat_generator() -> None:
    text = SMOKE.read_text(encoding="utf-8")
    assert "KLING_V2_LIVE_SMOKE_SKIP_STILL_INSERT_V1" in text
    assert "KLING_V2_LIVE_SMOKE_MILESTONE_FALLBACK_V1" in text
    assert "/api/milestones/load" in text
    assert "is_still_insert_prompt_text" in text
    assert "beat_is_still_insert" in text
    assert "import beat_generator as bg" in text
    assert "milestone fallback" in text


def test_live_smoke_uses_tooling_root_for_import() -> None:
    text = SMOKE.read_text(encoding="utf-8")
    assert "MN_TOOLING_ROOT" in text
    assert 'Path(os.environ["MN_TOOLING_ROOT"])' in text


def test_offline_durability_documents_still_insert_law() -> None:
    text = VERIFY.read_text(encoding="utf-8")
    assert "KLING_O3_CANONICAL_PROMPT_SHAPE_V2" in text
    assert "Emotion OUTSIDE quotes" in text
