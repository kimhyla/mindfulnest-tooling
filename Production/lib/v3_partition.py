"""v3 video-partition helpers — LD-473 BG_VIDEO_PARTITION_V2."""

from __future__ import annotations

from typing import Iterator


def _iter_v3_beats(snap: dict) -> Iterator[tuple[str, str, dict]]:
    """Yield (video_role, beat_id, beat_dict) for every beat across all v3 partitions.

    v3 architecture (LD-473 BG_VIDEO_PARTITION_V2): beats live under
    snap['videos'][role]['beats'][beat_id]. Legacy v2 top-level 'beats'
    is preserved for back-compat reads only — new beats only land in v3.

    This helper centralizes the iteration so OrphanSweepThread, LipsyncPollingThread,
    and PollingThread can all walk the right shape.
    """
    videos = snap.get("videos") or {}
    for role in ("intro", "resolution", "standalone"):
        partition = videos.get(role) or {}
        for beat_id, beat in (partition.get("beats") or {}).items():
            if isinstance(beat, dict):
                yield role, beat_id, beat
    # Legacy fallback — yield top-level beats too, so v2 fixtures still work
    for beat_id, beat in (snap.get("beats") or {}).items():
        if isinstance(beat, dict):
            yield "legacy", beat_id, beat
