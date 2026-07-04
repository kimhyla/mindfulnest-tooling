# TECH SPEC — Module lipsync V3 raw pin + late-fade transitions (v1)

**Status:** Implemented 2026-07-04 — **Amended:** V3 adaptive applies to Avatar Pro / Beat Gen only after legacy reinstatement; Module tab legacy Kling/ByteDance uses V2 letterbox (`TECH_SPEC_MODULE_LIPSYNC_LEGACY_REINSTATEMENT_v1.md`).  
**Tokens:** `PHASE_MODULE_LIPSYNC_RAW_PIN_V1`, `STITCH_MODULE_LATE_FADE_TRANSITIONS_V1`

## Problem class

1. **Delivery skip:** `plan_module_lipsync_reframe()` returned `mode: none` for any 1280×720 pin — including legacy `_reframed` V2 outputs — so reencode/batch jobs skipped adaptive subtitle crop. Gibberish burned into Avatar Pro output survived stitch reexport.

2. **Raw loss:** Poll handler downloaded WaveSpeed bytes directly to the delivery filename; no `_raw` sibling. Reencode had no high-res source.

3. **Audio padding gap:** Beat Gen avatar beats pad audio; phase A/B Avatar Pro submit did not.

4. **Transition regression (PR #87):** Uniform 3800ms boundaries with 600ms outgoing visual fade on every slot — dims dialogue tails. Intro→phase_a too long vs manifest.

## Raw pin contract (`PHASE_MODULE_LIPSYNC_RAW_PIN_V1`)

| Artifact | Rule |
|----------|------|
| WaveSpeed download | `phase_{a\|b}_lipsync_{ts}_raw.mp4` (native ~1920×1072) |
| Delivery pin | `phase_{a\|b}_lipsync_{ts}.mp4` (V3 1280×720, single encode) |
| State keys | `phase_*_lipsync_file` → delivery; `phase_*_lipsync_raw_file` → raw |
| **Never pin** | `*_reframed.mp4` (legacy batch V2 — deprecated) |

Reencode / batch: always source from `_raw.mp4` or undelivered download; never from `_reframed`.

## Delivery (`PHASE_MODULE_LIPSYNC_DELIVERY_V3`)

- **Always** `plan_module_lipsync_reframe_v3()` — adaptive subtitle band + bottom sacrifice.
- No `mode: none` skip at 1280×720.
- Legacy letterbox stills: V3 on full frame (side pillarbox included in sacrifice probe).

## Audio padding

Phase A/B Avatar Pro submit: `pad_audio_for_lipsync()` after stem trim; persist padded MP3 under event dir until submit returns.

## Transitions (`STITCH_MODULE_LATE_FADE_TRANSITIONS_V1`)

Per-boundary total budgets (ms):

| Boundary | fade_ms |
|----------|---------|
| intro → phase_a | 2800 |
| phase_a → phase_b | 3800 |
| phase_b → resolution | 3800 |

Visual fade split (`allocate_pair_fade_budget`):

- **Outgoing:** 200ms default; **0ms** on phase_b→resolution (no dim on Phase B tail)
- **Incoming:** 200ms
- **Black hold:** remainder (bulk in the middle)

Module bake uses stitch_editor constants — **not** intro manifest fade loaders.

## Blast radius

| Area | Risk | Mitigation |
|------|------|------------|
| Existing `_reframed` pins | Reencode now re-crops | One-time V3 reencode + update pin |
| Phase B v6 splice | Lipsync swap needs re-splice | Reencode lipsync first; operator re-export phase B preview |
| Module bake duration | Boundary 0 −1000ms | Expected; intro→A shorter |
| Batch reframe script | Obsolete | Deprecation header; use reencode from raw |

## Verification

- `pytest tests/test_phase_module_lipsync_delivery.py tests/test_black_pause_boundaries.py tests/test_stitch_module_late_fade_transitions_v1.py`
- Frame probe: subtitle band absent at bottom after V3 reencode
- Bake audit: boundary pair_fades_ms match spec
