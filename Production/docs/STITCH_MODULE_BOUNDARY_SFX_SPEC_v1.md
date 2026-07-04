# Stitch Module Boundary SFX + Intro Tail Export Trim — Spec v1

**Status:** CANONICAL (2026-06-21)  
**Scope:** Module bake (intro → phase_a → phase_b → resolution) — visual dissolve, black hold, transition SFX timing, canonical intro tail export trim.

---

## 1. Classification

| Issue | Category | Layer |
|-------|----------|-------|
| Transition SFX only on tail of outgoing phase | **Code (Cat-1)** | Pipeline-only boundary SFX; remove slot tail duplicate |
| Intro whiteout hold too long on new events | **Code (Cat-1)** + **Runtime heal (Cat-2)** | Manifest default `trim_back` on mirror beat hydrate/migrate |
| Black-pause eating dialogue | **Not a bug** (when dissolve path runs) | Verify only; `fade_audio=False` + inserted black |

---

## 2. Boundary SFX (single owner)

### Intended behavior

For each module boundary (`after_slot` 0..2):

| Boundary | SFX file |
|----------|----------|
| intro → phase_a | `magic_sound.mp3` |
| phase_a → phase_b | `windy_magic.mp3` |
| phase_b → resolution | `magic_sound.mp3` |

**Pipeline** (`_stitch_apply_canonical_boundary_sfx`) overlays SFX across:

```
pre-roll (500ms) + outgoing visual fade (~600ms) + black hold (~2600ms) + incoming visual fade (~600ms) + post-roll (500ms)
```

Slot dialogue audio **hard-cuts** at clip end (`audio_xfade_ms=0`). SFX carries across the dissolve.

### Anti-pattern (removed)

`STITCH_SLOT_CANONICAL_DEFAULT_SFX` must **not** materialize `windy_magic.mp3` / `magic_sound.mp3` as **tail cues** on phase_a / phase_b. Those cues mixed before boundary expansion land at `video_dur - play_ms` and **do not span the fade**.

`stitch_boundary_sfx_baked_in_slot_cues` skip logic is **removed** — pipeline overlay always runs.

### Slot defaults retained

| Slot | Default SFX | Role |
|------|-------------|------|
| intro | `whoosh sound.mp3` (tail) | Intro ending (distinct from boundary magic) |
| resolution | head `whoosh sound.mp3` + tail exit SFX | Resolution opening whoosh (intro parity) + module ending |

### Heal

On stitch job load and pipeline hydrate: strip `auto_default` tail cues for boundary filenames from phase_a / phase_b; strip retired `after_win_return_to_map_music.mp3` head cue from resolution.

Markers: `STITCH_BOUNDARY_SFX_PIPELINE_ONLY_V1`, `STITCH_RESOLUTION_HEAD_WHOOSH_V1`

---

## 3. Visual boundaries

- `expand_clips_with_black_pause_boundaries` with `pair_ms=3800`
- Budget: ~600ms fade-out + ~2600ms black insert + ~600ms fade-in (`allocate_pair_fade_budget`)
- **All boundaries:** symmetric outgoing/incoming visual fades (`STITCH_MODULE_BOUNDARY_SYMMETRIC_FADE_V1`)
- Phase B in-clip whiteout export **never runs** (`PHASE_B_WHITEOUT_ENABLED=False`; lipsync write path does not invoke `_apply_whiteout_fade`)
- **QuickTime playback:** all kid-facing exports pass `ensure_mp4_playback_timestamps()` (`STITCH_MP4_PLAYBACK_TIMESTAMPS_V1`)
- Module bake sets `module_pipeline=true` → boundaries always apply when ≥2 slots

---

## 4. Canonical intro tail export trim

### Compose vs export

- **Compose** (`intro_tail.mp4`): full speak + LD-737 burst + whiteout hold (~2.5s in manifest)
- **Export** (Send to Stitcher): `kling_o3_trim_back` on mirror beat trims trailing whiteout only

### Default

Manifest key: `intro_canonical_beats.canonical_tail_export_trim_back_s` (default **4.0** seconds, matches Event_1 approved).

Seeded on:

- `hydrate_intro_canonical_mirror_beat`
- `_migrate_sidecar` (via hydrate on pre segments)

Operator trim preserved when `kling_o3_trim_back > 0` already set.

---

## 5. Verification contract

1. **Unit:** `boundary_sfx_overlay_plan()` returns seg1 offset ≥ pre+out before clip end; total span ≥ pair_ms
2. **Unit:** strip removes phase_a/b auto_default boundary filenames
3. **Unit:** mirror beat without trim gets manifest default trim_back
4. **Smoke:** deploy `build-sha`; load stitch job → phase_a has no windy auto_default cue
5. **User-path:** Event_2 intro re-export duration ≈ raw_tail - 4s; re-bake final includes boundary SFX span

---

## 6. Related docs

- `STITCHER_SFX_TIMELINE_SPEC_v1.md`
- `.cursor/rules/mindfulnest-intro-canonical-tail.mdc`
