# Tech Spec — Operator Edit Authority v1

**Marker:** `OPERATOR_EDIT_AUTHORITY_V1`  
**Scope:** All storyboard tabs × all events × all beats where an operator edits in-memory state that must survive focus/visibility/poll refresh until server ack.  
**Complements:** `STORYBOARD_AUTHORITY_REGISTRY_V1` (server/export truth — Tier C).

---

## Problem class

> Server persistence is correct, but **client hydration replaces the entire local slice** while the operator is still editing — or omits a field on partial GET — wiping geometry, drafts, or selections.

Tier C proved disk truth. Tier D / this spec proves **client edit-session truth** across every tab.

---

## Canonical merge rule (all surfaces)

Implemented in `operatorEditMerge.ts`:

| Precedence | Condition | Winner |
|------------|-----------|--------|
| 1 | `patchInFlight` | **local** |
| 2 | Server returned field (incl. explicit empty) | **server** (when idle) |
| 3 | Server omitted field | **local** (if present) |
| 4 | Protected edit registry (focused/dirty/saving) | **local** (beats only) |

Specializations wrap this primitive; they do not invent new precedence rules.

---

## Surface matrix (every operator edit path)

### Beat Gen — per beat_id, all events/milestones

| ID | UI | Server write | Client owner | Status |
|----|-----|--------------|--------------|--------|
| `bg_beat_prompt_field` | O3 prompt textarea | beat patch / sidecar | `useProtectedPromptField` + `promptEditRegistry` | **shipped** |
| `bg_beat_ref_boxes` | Char/bg ref pickers | assign_image / ref patch | `preserveRefBoxesOnServerBeatMerge` | **shipped** |
| `bg_beat_o3_gallery_poll` | Gallery slots on poll | terminal.json / sidecar | `applyO3GalleryFieldsFromPoll` | **shipped** |
| `bg_beat_dialogue` | Beat plan dialogue cells | beat_update_text | contenteditable uncontrolled + pathappPatch | partial |
| `bg_beat_trim_handles` | Trim front/back | beat trim fields | hydration useEffect (LD-756) | partial |

**Store:** `bgSessionStore.ts` — session refresh calls `applyPromptEditsToBeats` + `preserveRefBoxesOnServerBeatMerge` for **every beat in partition**.

### Phase A / B — per event_id (module scope)

| ID | UI | Server write | Client owner | Status |
|----|-----|--------------|--------------|--------|
| `phase_watercolor_cue_geometry` | Waveform cue blocks | `phase_*_watercolor_cues_json` | `usePhaseWatercolorCues` | **shipped** |
| `phase_script_draft` | Script textarea | `phase_*_script` | `useProtectedPromptField` | **in progress** |
| `phase_stem_cut_geometry` | Amber cut rectangle | `phase_*_voice_stem_cut_*_s` | `usePhaseStemCut` | **in progress** |
| `phase_ambient_preset` | Preset `<select>` | `phase_*_ambient_preset_id` | `usePhaseAmbientPreset` | planned |
| `phase_base_clip_picker` | Arlo/Cedric clip | `phase_*_*_clip_id` | merge on hydrate omit | planned |

**Scope:** Same hooks serve Event_1…Event_N; keyed by `scope.event_id` + phase.

### Stitcher — per job / slot

| ID | UI | Server write | Client owner | Status |
|----|-----|--------------|--------------|--------|
| `stitch_sfx_cue_geometry` | SFX waveform blocks | `stitch_save_job` slot `sfx_cues` | `mergeStitchJobSlotsClientPatch` | **shipped** |
| `stitch_slot_durable_fields` | video_path, dur, ambient | load_job / save | `mergeStitchSlotClientPatch` | **shipped** |
| `stitch_ambient_bed_selection` | Ambient per slot | slot `ambient_bed` | local snapshot on save refresh | partial |

### Storyboard — per beat (resolution/full)

| ID | UI | Server write | Client owner | Status |
|----|-----|--------------|--------------|--------|
| `storyboard_dialogue_cell` | Dialogue contenteditable | beat_update_text | uncontrolled DOM (no poll clobber) | partial |
| `storyboard_beat_trim` | Trim UI | beat trim | LD-756 hydration | partial |

---

## Enforcement

| Layer | Artifact |
|-------|----------|
| Merge primitive | `operatorEditMerge.ts` |
| Machine index | `authority_registry.py` — `OPERATOR_EDIT_SURFACES` tuple |
| Durability | `verify_operator_edit_surfaces_durability.sh` |
| Session deploy | wired into `verify_storyboard_session_durability.sh` |
| E2E | per-surface Playwright in existing spec files |

---

## Non-goals

- Server-side authority (Tier C — already shipped)
- Visual UX (thin cue markers on long timelines) — separate UX pass
