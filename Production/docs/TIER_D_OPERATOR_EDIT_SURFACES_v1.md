# Tier D — Operator Edit Surfaces (2026-06-29)

**Marker:** `TIER_D_OPERATOR_EDIT_SURFACES_V1`  
**Status:** Shipped — Phase A/B P0+P1 surfaces **shipped** (closure audit 2026-07-03)  
**Canonical spec:** `Production/docs/TECH_SPEC_OPERATOR_EDIT_AUTHORITY_V1.md` (`OPERATOR_EDIT_AUTHORITY_V1`)  
**Parent:** Tier C closed server/export authority; Tier D closes **client hydration vs optimistic edit** authority across **all tabs, all beats, all events**.

---

## Why Tier D exists

Tier C answered: *"Which disk field / server predicate is authoritative for export and scope?"*

Tier D answers: *"While the operator is editing, who owns in-memory geometry until the server acks?"*

The Phase B watercolor vanish bug (Event_3, 2026-06-28) proved persistence could be correct while the UI wiped cues on `refreshAll()` — because PhaseProducer used **dual state** without a declared merge owner. Stitcher SFX already had `STITCH_SAVE_REFRESH_LOCAL_CUES_V1`; Phase B did not.

---

## Registry extension (operator edit surfaces)

| ID | Surface | Server field / API | Client owner | Status | Risk if unchecked |
|----|---------|-------------------|--------------|--------|-------------------|
| **phase_watercolor_cue_geometry** | Phase A/B waveform watercolor cues | `phase_*_watercolor_cues_json` | `usePhaseWatercolorCues` + `mergeWatercolorCuesOnHydrate` | **shipped** | Cue markers vanish on focus/visibility refresh |
| **stitch_sfx_cue_geometry** | Stitcher slot waveform SFX | `stitch_save_job` slot `sfx_cues` | `jobSlotsSnapshotRef` + `mergeStitchJobSlotsClientPatch` | shipped (Tier C) | Dragged SFX revert after save refresh |
| **phase_script_draft** | Phase A/B script textarea | `phase_*_script` | `useProtectedPromptField` in PhaseProducer | **shipped** | refreshAll must not clobber draft |
| **phase_stem_cut_geometry** | Phase A/B stem cut handles | `phase_*_voice_stem_cut_*_s` | `usePhaseStemCut` + mergeOperatorFieldOnHydrate | **shipped** | cut rectangle revert on refresh race |
| **bg_beat_prompt_field** | BG beat prompt textarea | `_derived.display_prompt` + stored fields | `useProtectedPromptField` | shipped | cursor snap-back on poll |
| **storyboard_dialogue_cell** | Storyboard beat dialogue | `beat_update_text` | `useStoryboardDialogueField` | **shipped** | SB-DIALOGUE-HYDRATE-1 |
| **stitch_ambient_bed_selection** | Stitcher ambient per slot | slot `ambient_bed` in job | `mergeStitchAmbientBedOnHydrate` | **shipped** | STITCH-AMBIENT-HYDRATE-1 |
| **phase_ambient_preset** | Phase A/B ambient preset select | `phase_*_ambient_preset_id` | `usePhaseAmbientPreset` | **shipped** | AMBIENT-HYDRATE-1 |
| **phase_base_clip_picker** | Cedric/Arlo base clip | `phase_*_*_clip_id` | `usePhaseBaseClipPicker` | **shipped** | PHASE-CLIP-HYDRATE-1 |
| **library_panel_selection** | CR library multi-select | n/a (stateless) | local only | OK | low |

---

## Shipped in this session (phase_watercolor_cue_geometry)

1. **`phaseWatercolorCuesAuthority.ts`** — parse + merge contract (`PHASE_WATERCOLOR_CUE_AUTHORITY_V1`)
2. **`usePhaseWatercolorCues.ts`** — single mutation API (drop, resize, patch, delete, remap key, hydrate)
3. **`PhaseProducer.tsx`** — delegates all cue state to hook; no `stateSlice.watercolor_cues`
4. **Durability:** `verify_phase_watercolor_cue_authority_durability.sh` + vitest + Playwright `CUE-HYDRATE-1`
5. **Registry row:** `authority_registry.py` → `phase_watercolor_cue_geometry`

### Merge precedence (canonical)

1. Patch in flight → keep local cues  
2. Server returned array (including `[]`) → server wins when idle  
3. Server omitted field → keep local cues  

---

## Recommended Tier D execution order

| Priority | Row | Effort | Notes |
|----------|-----|--------|-------|
| P0 | phase_watercolor_cue_geometry | done | Event_3 repro |
| P1 | phase_script_draft | medium | Promote to `useProtectedPromptField` like BG prompts |
| P1 | phase_stem_cut_geometry | medium | Extract hook mirroring watercolor merge |
| P2 | phase_ambient_preset | small | Optimistic select + merge on refresh |
| P2 | stitch_ambient_bed_selection | medium | Audit StitcherTab refresh paths |
| P3 | storyboard_dialogue_cell | medium | Extend protected-field pattern |
| P3 | phase_base_clip_picker | small | Merge selected id on hydrate omit |

---

## Gates (Tier D)

```bash
bash Production/scripts/verify_operator_edit_surfaces_durability.sh  # full surface matrix
bash Production/scripts/verify_phase_watercolor_cue_authority_durability.sh
bash Production/scripts/verify_storyboard_session_durability.sh  # includes both when wired
```

Playwright: `phase_waveform_playback.spec.ts` → `CUE-HYDRATE-1`

---

## What Tier C did *not* cover (explicit non-goals)

- React component optimistic state merge rules  
- Focus / visibility / rehydrate poll interaction with in-flight edits  
- Visual UX (thin cue markers on long lipsync tracks)  

Those belong to Tier D and operator-edit registry rows above.
