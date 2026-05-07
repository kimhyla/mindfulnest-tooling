# visible-magic skill — Governance Checklist v1
# 2026-04-24 — per Rule 17, self-administered at skill startup

## Purpose
Reference checklist Claude reads at the start of any visible-magic invocation.
Walk each item, confirm it applies (or doesn't) to the current task, then proceed.
If any item is about to be violated: STOP, state the conflict, ask Kim.

---

## PRE-FLIGHT CHECKLIST

### [ ] 1. Clip registry consulted before any stitch
Before ANY ffmpeg concat or imageio stitch operation, `resolve_stitch_clips()`
from magic_compositor.py MUST be called. No exceptions.
Violation symptom: base clip used instead of approved magic version (the v2 failure).

### [ ] 2. No eyeball positioning
Path coordinates MUST come from one of:
  (a) KNOWN_SCENES in magic_compositor.py (SHA-verified), or
  (b) magic_position_finder.py pixel detection + Kim red-circle confirmation
NEVER from visual inspection of a thumbnail or preview image.
Violation symptom: magic lands in wrong position (130+ px off).

### [ ] 3. Source clip SHA verified for known scenes
When reusing a KNOWN_SCENES entry, compute sha256[:16] of frame 0 and compare
to stored source_frame_sha. If mismatch: warn Kim, offer re-calibration.
Violation symptom: stored path applied to re-rendered clip with different framing.

### [ ] 4. Locked invariants enforced
DOT_SIZES must be [1,1,1,2,2,3] — no larger values.
BLEND must be additive — no screen blend on bright backgrounds.
SCATTER must be symmetric Gaussian — no abs(gauss).
PALETTE must be warm golden-white Ori: (255,255,238),(255,252,200),(255,240,155).
These were explicitly approved by Kim and rejected alternatives are documented.

### [ ] 5. Preview PNG shown before full render
Kim sees a single preview PNG (at T_TRAIL_COMPLETE frame) before full video render.
Never render a full video without prior preview approval.
Violation: wastes 2-5 min render time on unapproved aesthetics.

### [ ] 6. Delta table used for feedback (not free-form guessing)
If Kim says "too bright" → sparkle_gain × 0.75, ambient_gain × 0.80.
If Kim says "too high" → SCATTER_Y × 0.65, blur_yx[0] × 0.65.
Max 2 iterations before stopping and asking Kim what specifically to change.

### [ ] 7. Registry updated after approval
After Kim approves output: update magic_clip_registry.json with status="approved".
New entries start as status="pending" — never auto-substitute pending clips.

### [ ] 8. No Directus writes skipped (Rule 15)
After creating or modifying any registered file, PATCH/POST prod_reference_docs
in the same operation. Do not defer to session end.

---

## STYLE STATUS TABLE (current as of 2026-04-24)

| Style     | Status   | Directus LD    | Notes                              |
|-----------|----------|----------------|------------------------------------|
| tessa_ori | approved | id=398         | Floor-flat ground trail. Locked.   |
| wide_ori  | draft    | none           | Wide clearing beam. Not locked.    |
| burst     | pending  | none           | Radial from point. Not locked.     |

---

## KNOWN FAILURE MODES (from 80-lesson extract)

| Symptom                      | Root cause                        | Fix                                  |
|-----------------------------|-----------------------------------|--------------------------------------|
| Magic 130px off target       | Eyeball positioning               | Use magic_position_finder.py         |
| Magic "floating" above floor | blur_yx[0] > 8px or SCATTER_Y > 5%| Reduce both                          |
| Magic invisible on bright bg | Screen blend or gain too low      | Switch to additive; check gain       |
| Trail cuts off halfway        | t_head = t_frac (not decoupled)  | t_head = t_frac / T_TRAIL_COMPLETE   |
| Jerkiness / popping          | Particles re-placed each frame    | Use pre-placed seeded particles      |
| Wrong clip in stitch         | No registry gate                  | Call resolve_stitch_clips() first    |
| Dots look like blobs         | dot_sizes > 3                     | Enforce [1,1,1,2,2,3]               |
| Hard horizontal slice        | abs(gauss) scatter                | Use symmetric gauss(0, 1.0)          |

---

## TOOL REFERENCES

- Rendering engine:   Production/tools/magic_compositor.py
- Position finder:    Production/tools/magic_position_finder.py
- Clip registry:      Production/tools/magic_clip_registry.json
- Skill protocol:     .claude/skills/visible-magic/SKILL.md
- Lessons (physics):  Production/Event_1/LESSONS_LEARNED_magic_path_compositor_20260422.md
- Lessons (workflow): Production/Event_1/LESSONS_LEARNED_magic_compositor_session2_20260422.md
- Lessons (v3 doc):   Production/VISIBLE_MAGIC_LESSONS_LEARNED_v3.md

---

## Lessons Learned April 25–26, 2026

### Magic Path Coordinates Are Scene-Specific — Never Import From Another Scene (LD: `MAGIC_PATH_PER_SCENE_MEASUREMENT_V1`)
Visible-magic path coordinates (`path_pts` y-values especially) MUST be visually re-measured for each source still. Coordinates from one approved clip do NOT generalize to any other clip — character foot position, framing, and zoom level all change per shot. Procedure: export a test frame at 1280×720, identify character's feet pixel position, divide by 720 for normalized y, start the path at that value. Never copy y-values across scenes. Example of failure: `tessa_exit_right` y=0.968 was incorrectly imported for the resolution scene — resolution Tessa stands at y≈0.73, placing the trail floating in mid-air.
