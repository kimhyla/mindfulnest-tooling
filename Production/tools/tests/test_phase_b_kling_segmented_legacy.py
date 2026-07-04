"""Phase B legacy_28s segmented Kling — import + segment count contract."""
from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from phase_b_kling_segmented_lipsync import (  # noqa: E402
    KLING_SEGMENT_MAX_S,
    PHASE_B_KLING_SEGMENT_STRATEGY_LEGACY,
    PHASE_B_KLING_SEGMENT_STRATEGY_PAUSE_ALIGNED,
    compute_phase_b_kling_segments,
)


def test_segmented_module_imports():
    assert KLING_SEGMENT_MAX_S == 28.0


def test_legacy_28s_segment_count_for_long_stem(tmp_path: Path):
    audio = tmp_path / "long_stem.mp3"
    # ffprobe_duration + silences mocked via minimal file — use compute with mock
    import phase_b_kling_segmented_lipsync as seg

    def _fake_duration(_p):
        return 204.0

    def _fake_silences(_p):
        return [(28.0, 28.5), (56.0, 56.5), (84.0, 84.5), (112.0, 112.5)]

    orig_dur = seg.ffprobe_duration
    orig_sil = seg._detect_silences
    try:
        seg.ffprobe_duration = _fake_duration
        seg._detect_silences = _fake_silences
        _dur, specs = compute_phase_b_kling_segments(
            audio,
            strategy=PHASE_B_KLING_SEGMENT_STRATEGY_LEGACY,
        )
    finally:
        seg.ffprobe_duration = orig_dur
        seg._detect_silences = orig_sil

    assert _dur == 204.0
    assert len(specs) >= 6
    assert all(s.duration_s <= KLING_SEGMENT_MAX_S + 0.01 for s in specs)
    assert PHASE_B_KLING_SEGMENT_STRATEGY_LEGACY != PHASE_B_KLING_SEGMENT_STRATEGY_PAUSE_ALIGNED
