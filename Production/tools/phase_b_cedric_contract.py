"""Phase B Cedric base-clip contract — canonical preset for all events.

Jul 4 2026: ``cedric_idle_newstyle_v6`` — 16:9 (1280×720) wizard-desk idle,
frozen mouth, mug/fireplace steam. Supersedes v3 (4:3) and interim v5.
Deprecated camera/study/placeholder and prior newstyle ids coerce on read/submit.
"""
from __future__ import annotations

PHASE_B_CEDRIC_BASE_CLIP_CANONICAL = "cedric_idle_newstyle_v6"

# Approved ~29s bookend unit (2×15s no-trim). Auto-looped to stem length at lipsync send.
PHASE_B_CEDRIC_LOOP_UNIT_CLIP_ID = "cedric_idle_bookend_unit_v1"
PHASE_B_CEDRIC_LOOP_UNIT_FALLBACK_IDS = (
    "cedric_idle_test_2x15_bookend_v2_notrim",
    "cedric_idle_newstyle_v13_200s_7xloop",
)

# Avatar Pro route uses canonical still — not idle base loop (see phase_b_avatar_lipsync.py).
PHASE_B_LIPSYNC_METHOD_AVATAR = "kling_avatar_pro_v1"

# Kling idle-base generation (phase_b_cedric_lipsync_base.py) — shared locks.
PHASE_B_FIREPLACE_SMOKE_LOCK = (
    "FIREPLACE LOCK: flames and smoke stay ONLY inside the fireplace opening — "
    "tiny gentle wisps barely visible, never billowing, never filling the room, "
    "never crossing the hearth edge, never intensifying. Smoke must remain "
    "physically contained in the firebox at all times."
)

PHASE_B_MUG_STEAM_LOCK = (
    "MUG STEAM OFF: zero steam, zero vapor, zero wisps from the coffee mug — "
    "the mug and coffee stay completely still with no animated steam whatsoever."
)

PHASE_B_MOUTH_FROZEN_LOCK = (
    "MOUTH LOCK: lips sealed shut and completely motionless for the entire clip — "
    "no talking, no lip-sync, no mouthing words, no jaw articulation, no speech "
    "motion, no lip flap, no mouth animation. Only exception: brief closed-lip sip "
    "when drinking, then mouth returns to sealed rest immediately."
)

PHASE_B_MUG_PLACEMENT_LOCK = (
    "ONE MUG ONLY: exactly one wooden coffee mug exists in the scene — never a second "
    "mug, never a duplicate cup on the desk while he holds one. "
    "Home position: when not sipping, the single mug rests in one fixed spot on the desk "
    "and Cedric's hands are empty/relaxed. He may occasionally lift THAT same mug, take "
    "a slow gentle sip, then set it back in the exact same home spot. The mug never "
    "slides, teleports, floats, or appears from nowhere."
)

PHASE_B_DESK_PROPS_LOCK = (
    "DESK PROPS LOCK: every object on the desk and shelves stays perfectly frozen except "
    "Cedric's body and the one coffee mug when he hand-lifts it. Potions, bottles, "
    "papers, herbs, quills, candles — no steam, no vapor, no wisps, no animation. "
    "No cup holders, coasters, or props appearing, disappearing, or morphing."
)

PHASE_B_GESTURE_LOCK = (
    "Small calm hand gestures allowed occasionally — gentle open-palm emphasis, subtle "
    "point toward desk, relaxed return to neutral. No waving, no large gestures, no pacing."
)

PHASE_B_CAMERA_GAZE_LOCK = (
    "CAMERA GAZE: eyes look directly at the camera lens with warm, kindly eye contact — "
    "not staring down at the mug or desk except a brief sip if allowed."
)

PHASE_B_BOOKEND_POSE_LOCK = (
    "BOOKEND POSE (start AND end of clip): match the still exactly — facing camera, "
    "warm close-mouthed smile with lips sealed shut, relaxed hands near desk, mug in "
    "fixed home spot, zero mug steam. Open with this pose briefly, natural idle motion "
    "in the middle, then return to the identical bookend pose before the clip ends."
)

PHASE_B_ROBE_STABILITY_LOCK = (
    "ROBE LOCK: deep green robe and gold embroidery keep perfectly stable fabric — "
    "no diagonal pleats, no fold morphing, no rippling weave, no shifting embroidery."
)

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

