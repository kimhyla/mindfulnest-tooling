# Tech Spec — Operator Session Completion (Phase E)

**Marker:** `OPERATOR_SESSION_COMPLETION_V1`  
**Status:** Shipped (Phase E PR2–PR6)  
**Input:** `OPERATOR_UX_SYMPTOM_MATRIX_v1.md` (149 rows) + `OPERATOR_UX_ROOT_CAUSE_SYNTHESIS_v1.md`  
**Prerequisite:** Tier C disk authority (shipped); Tier D partial (watercolor, script, stem cut)

---

## 1. Problem statement (one line)

Tier C fixed **which disk field wins at export**. Phase E fixes **who owns operator state during an active edit session** and **at Generate-click commit**.

## 2. Three tracks (no row-level patches)

| Track | Meta-root | Open rows | Architecture |
|-------|-----------|----------:|--------------|
| **E1** | RC2 refresh clobber | 14 | `operatorEditMerge.ts` + per-surface hooks + registry |
| **E2** | RC6/RC8/RC1 Generate transaction | 5 | Intent snapshot closure + legacy path removal |
| **E3** | RC3/RC4 time authority | 4 | `waveformTimeAuthority.ts` + REMOUNT-1 |

**Ops (RC10):** 10 infra rows — parallel gates; not Phase E UX architecture.

## 3. Canonical merge rule (E1)

Same as `TECH_SPEC_OPERATOR_EDIT_AUTHORITY_V1.md` — all surfaces use `mergeOperatorFieldOnHydrate` / `mergeOperatorArrayOnHydrate` or `useProtectedPromptField`.

## 4. E1 — Surface completion matrix

| ID | Hook / module | Files | Gate | E2E |
|----|---------------|-------|------|-----|
| D-010 | `usePhaseAmbientPreset` | PhaseProducer | registry `phase_ambient_preset` | AMBIENT-HYDRATE-1 |
| D-016 | `usePhaseBaseClipPicker` | PhaseProducer, BaseClipPicker | `phase_base_clip_picker` | PHASE-CLIP-HYDRATE-1 |
| D-011 | `mergeStitchAmbientBedOnHydrate` | stitchSlotDurableMerge, StitcherTab | `STITCH_AMBIENT_BED_MERGE_V1` | STITCH-AMBIENT-HYDRATE-1 |
| D-012/021 | `useStoryboardDialogueField` | StoryboardTab, storyboardSessionStore | `storyboard_dialogue_cell` | SB-DIALOGUE-HYDRATE-1 |
| D-013 | `useStoryboardTrimFields` | StoryboardTab | `storyboard_beat_trim` | SB-TRIM-HYDRATE-1 |
| D-014/015 | `useBgO3CutSession` | BgTab, BgO3CutOverlay | `bg_beat_o3_cut_overlay` | BG-O3-CUT-HYDRATE-1 |
| D-018 | `mergeBeatsOnSessionHydrate` | bgSessionStore | `bg_beat_o3_gallery_session` | BG-SESSION-TERMINAL-1 |

**Shipped E1 (reference):** D-001..007, D-017, D-019, D-022, D-023, D-024

## 5. E2 — Intent transaction closure

Core module: `o3_generation_intent.py` (shipped). Remaining:

1. Reconcile orphan terminal → `done_with_warning` when `sidecar_persist_ok: false`
2. Submit UI: set poll latch + intent map **before** `refreshState()`
3. Remove pre-commit `heal_beat_dual_prompts` on element-native submit path
4. Gate: `verify_o3_generation_intent_transaction_durability.sh`

## 6. E3 — Waveform Time Authority

Modules:
- `waveformTimeAuthority.ts` — playhead/duration refs, `preserveAcrossRemount()`
- Future: `waveformSeekController.ts` extract (WTA-0)

WTA-1: REMOUNT-1 — preserve playhead across `audioSrc` change  
Gate: `verify_waveform_time_authority.sh`

## 7. Blast radius

| Area | Risk | Mitigation |
|------|------|------------|
| PhaseProducer refreshAll | All phase tabs/events | Scalar hooks only; no full-slice replace for owned fields |
| WaveformTimeline remount | Phase A/B + Stitcher slots | Preserve ms in authority ref; unit + REMOUNT-1 e2e |
| BgTab submit | All beats/events | Latch ordering; pytest intent suite |
| Stitcher ambient | Per-slot save | Mirror SFX merge pattern |
| Storyboard refreshTick | All beats | Merge in storyboardSessionStore onSuccess |

## 8. Verification (multipass — mandatory)

| Pass | Command |
|------|---------|
| M1 | `node --test` operatorEditMerge + waveformTimeAuthority tests |
| M2 | `verify_operator_edit_surfaces_durability.sh` |
| M3 | `verify_waveform_time_authority.sh` |
| M4 | `verify_o3_generation_intent_transaction_durability.sh` |
| M5 | `verify_storyboard_session_durability.sh` |
| M6 | `pytest` O3 intent suite |
| M7 | Playwright `phase_waveform_playback.spec.ts` |
| M8 | `deploy_storyboard_v59.sh` + build-sha curl fleet |

## 9. Done when

- All 21 open matrix rows → **shipped**
- `OPERATOR_UX_SYMPTOM_MATRIX_v1.md` updated
- Deploy build-sha matches HEAD on 5111–5113
- No new grep-only gates without behavioral e2e for E1/E3 surfaces
