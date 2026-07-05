"""Phase B Kling chunk plan — align joins to meditation pauses in the voice stem.

PHASE_B_KLING_PAUSE_ALIGNED_V2: boundaries prefer silences ≥2s (meditation pauses).
Speech blocks longer than max_chunk_s are sub-split only at pauses ≥1.5s — never
mid-phrase arbitrary cuts. Pair with 15s Cedric idle base (cedric_idle_newstyle_v4).
"""
from __future__ import annotations

from dataclasses import dataclass

from phase_a_chipper_bytedance_lipsync import chunk_audio_for_bytedance

PHASE_B_KLING_PAUSE_ALIGNED_V2 = "PHASE_B_KLING_PAUSE_ALIGNED_V2"
PHASE_B_MEDITATION_PAUSE_MIN_S = 2.0
PHASE_B_INTERNAL_PAUSE_MIN_S = 1.5
PHASE_B_KLING_PAUSE_ALIGNED_MAX_S = 45.0
PHASE_B_CEDRIC_BASE_15S_CLIP_ID = "cedric_idle_newstyle_v4"


@dataclass(frozen=True)
class PauseAlignedSegment:
    index: int
    start_s: float
    end_s: float
    boundary_kind: str  # meditation_pause | internal_pause | tail

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


def _speech_between(
    audio_dur: float,
    pauses: list[tuple[float, float]],
    *,
    window_start: float = 0.0,
    window_end: float | None = None,
) -> list[tuple[float, float]]:
    end = audio_dur if window_end is None else window_end
    pauses = sorted((s, e) for s, e in pauses if s >= window_start and e <= end)
    speech: list[tuple[float, float]] = []
    pos = window_start
    for s, e in pauses:
        if s > pos + 0.05:
            speech.append((pos, s))
        pos = max(pos, e)
    if pos < end - 0.05:
        speech.append((pos, end))
    if not speech and end - window_start > 0.05:
        speech = [(window_start, end)]
    return speech


def _merge_speech_to_max(
    speech: list[tuple[float, float]],
    max_chunk_s: float,
) -> list[tuple[float, float]]:
    if not speech:
        return []
    merged: list[tuple[float, float]] = []
    cur_start, cur_end = speech[0]
    for seg_start, seg_end in speech[1:]:
        if seg_end - cur_start <= max_chunk_s:
            cur_end = seg_end
        else:
            merged.append((cur_start, cur_end))
            cur_start, cur_end = seg_start, seg_end
    merged.append((cur_start, cur_end))
    return merged


def _force_split_equal(start: float, end: float, max_chunk_s: float) -> list[tuple[float, float]]:
    dur = end - start
    if dur <= max_chunk_s + 0.01:
        return [(start, end)]
    n = int(dur / max_chunk_s) + 1
    step = dur / n
    return [(start + i * step, start + (i + 1) * step) for i in range(n)]


def _subsplit_block_at_internal_pauses(
    start: float,
    end: float,
    silences: list[tuple[float, float]],
    *,
    internal_pause_min_s: float,
    max_chunk_s: float,
) -> list[tuple[float, float]]:
    internal = [
        (s, e) for s, e in silences
        if start <= s and e <= end and (e - s) >= internal_pause_min_s
    ]
    sub_speech = _speech_between(end, internal, window_start=start, window_end=end)
    merged = _merge_speech_to_max(sub_speech, max_chunk_s)
    fixed: list[tuple[float, float]] = []
    for a, b in merged:
        dur = b - a
        if dur <= max_chunk_s + 0.01:
            fixed.append((a, b))
            continue
        inner_sil = [(s, e) for s, e in silences if a <= s and e <= b]
        inner = chunk_audio_for_bytedance(dur, inner_sil, max_chunk_s=max_chunk_s)
        if inner and inner[0][0] <= a + 0.05:
            fixed.extend(inner)
        else:
            fixed.extend(_force_split_equal(a, b, max_chunk_s))
    return fixed or [(start, end)]


def chunk_audio_pause_aligned(
    audio_dur: float,
    silences: list[tuple[float, float]],
    *,
    meditation_pause_min_s: float = PHASE_B_MEDITATION_PAUSE_MIN_S,
    internal_pause_min_s: float = PHASE_B_INTERNAL_PAUSE_MIN_S,
    max_chunk_s: float = PHASE_B_KLING_PAUSE_ALIGNED_MAX_S,
) -> list[tuple[float, float]]:
    """Return absolute [start_s, end_s) windows; every join sits on a real pause."""
    meditation = [
        (s, e) for s, e in silences if (e - s) >= meditation_pause_min_s
    ]
    blocks = _speech_between(audio_dur, meditation)
    chunks: list[tuple[float, float]] = []
    for start, end in blocks:
        dur = end - start
        if dur <= max_chunk_s + 0.01:
            chunks.append((start, end))
        else:
            chunks.extend(
                _subsplit_block_at_internal_pauses(
                    start, end, silences,
                    internal_pause_min_s=internal_pause_min_s,
                    max_chunk_s=max_chunk_s,
                ),
            )
    return chunks


def compute_pause_aligned_segments(
    audio_dur: float,
    silences: list[tuple[float, float]],
    **kwargs,
) -> list[PauseAlignedSegment]:
    windows = chunk_audio_pause_aligned(audio_dur, silences, **kwargs)
    return [
        PauseAlignedSegment(i, start, end, "meditation_pause")
        for i, (start, end) in enumerate(windows)
    ]
