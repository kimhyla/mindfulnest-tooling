"""Phase A tab must expose one canonical preview player (stitched when fresh)."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PRODUCER = ROOT / "storyboard-v2" / "src" / "components" / "phase" / "PhaseProducer.tsx"
E2E = ROOT / "storyboard-v2" / "e2e" / "s5_5f_smoke.spec.ts"
GUARD = ROOT.parent / "scripts" / "check_storyboard_critical_features.sh"


def _producer_src() -> str:
    return PRODUCER.read_text(encoding="utf-8")


def test_phase_a_single_player_marker_and_no_duplicate_stitched_video() -> None:
    src = _producer_src()
    assert "PHASE_A_SINGLE_PLAYER_V1" in src
    assert "phaseAPreviewFile" in src
    assert "priorityAudioFileForPhase" in src
    assert 'data-testid="phase-a-stitched-preview"' not in src
    assert "mn-phase-stitched-video" not in src
    assert "Stitched preview (lipsync + ambient bed):" not in src
    assert "Preview (canonical stitched — lipsync + ambient bed):" not in src
    assert "Preview (normalized dry lipsync — ambient added in Stitcher):" in src
    assert "phase-a-mix-btn" not in src


def test_phase_a_single_player_e2e_gates_present() -> None:
    e2e = E2E.read_text(encoding="utf-8")
    assert "F17 — Phase A single canonical player (LD-829)" in e2e
    assert "phase-a-stitched-preview" in e2e
    assert "PHASE_A_SINGLE_PLAYER_V1" in e2e


def test_phase_a_single_player_deploy_guard_lists_ld829() -> None:
    guard = GUARD.read_text(encoding="utf-8")
    assert "LD-829|PHASE_A_SINGLE_PLAYER_V1" in guard


@pytest.mark.parametrize(
    "banned",
    [
        '<video\n                  controls',
        "class=\"mn-phase-stitched-video\"",
        'data-testid="phase-a-stitched-preview"',
    ],
)
def test_phase_a_no_second_stitched_player_patterns(banned: str) -> None:
    assert banned not in _producer_src()
