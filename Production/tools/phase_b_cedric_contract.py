"""Phase B Cedric base-clip contract — canonical preset for all events.

Jul 4 2026: ``cedric_idle_newstyle_v6`` — 16:9 (1280×720) wizard-desk idle,
frozen mouth, mug/fireplace steam. Supersedes v3 (4:3) and interim v5.
Deprecated camera/study/placeholder and prior newstyle ids coerce on read/submit.
"""
from __future__ import annotations

PHASE_B_CEDRIC_BASE_CLIP_CANONICAL = "cedric_idle_newstyle_v6"

# Avatar Pro route uses canonical still — not idle base loop (see phase_b_avatar_lipsync.py).
PHASE_B_LIPSYNC_METHOD_AVATAR = "kling_avatar_pro_v1"

_DEPRECATED_PREFIXES = (
    "cedric_idle_camera_",
    "cedric_idle_study_",
    "placeholder_cedric_",
)

_DEPRECATED_EXACT = frozenset({
    "cedric_idle_newstyle_v1",
    "cedric_idle_newstyle_v2",
    "cedric_idle_newstyle_v3",
    "cedric_idle_newstyle_v4",
    "cedric_idle_newstyle_v5",
})


def phase_b_cedric_base_clip_deprecated(clip_id: str | None) -> bool:
    if not clip_id or not str(clip_id).strip():
        return True
    cid = str(clip_id).strip()
    if cid in _DEPRECATED_EXACT:
        return True
    return any(cid.startswith(p) for p in _DEPRECATED_PREFIXES)


def coerce_phase_b_cedric_base_clip_id(clip_id: str | None) -> str:
    if phase_b_cedric_base_clip_deprecated(clip_id):
        return PHASE_B_CEDRIC_BASE_CLIP_CANONICAL
    return str(clip_id).strip()

