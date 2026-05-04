# Storyboard v59 — S5.5f Handoff

**Date:** 2026-05-03
**Predecessor:** S5.5e (Storyboard buttons + ProjectSelector + Production Map data — 14/14 gates green)
**Master overview:** `STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md`
**Spec:** `STORYBOARD_V59_S5_5_F_SPEC_v1.md` (NEW — to be authored)
**Status:** PENDING — write spec before execution. Per `feedback_handoff_authoring_timing.md`,
this handoff is a STUB only; complete S5.5f spec is authored when S5.5e ships clean and
patterns from c+e have settled.

---

## §1 What S5.5f covers (per master overview §6)

Phase A/B feature parity for the v59 client. Work that exists in legacy
`build_storyboard.py` but was never ported to the Preact rewrite:

1. **WaveSurfer.js v7 waveform display** (per LD-472)
2. **Watercolor library drag-drop onto timeline** (currently opens new tab via `/magic`)
3. **Cue popover** (animation type / duration / Delete) per LD-470 procedural watercolor
4. **Voice stem upload UI** (no `<input type="file">` anywhere in PhaseProducer)
5. **Ambient preset selector inside producer** (currently only in Stitcher slots)
6. **Phase A 3-clip handling** (fly-in / sitting / fly-out — currently only handles ONE base clip)

## §2 Predecessor state (S5.5c + S5.5e shipped 2026-05-03)

Code primitives now available for S5.5f to reuse:

- `src/components/ui/Modal.tsx` — for cue popover (single-modal stack invariant)
- `src/components/ui/Toast.tsx` — for "Watercolor placed", "Voice stem uploaded" feedback
- `src/components/ui/Spinner.tsx` — for watermark/normalize/render in-flight indicators
- `src/components/ui/AssetTile.tsx` — for watercolor library tiles + draggable Phase A clips
- `src/utils/dragdrop.ts` — typed `DragPayload` union; `lib-watercolor` kind already declared
- `src/components/BeatAudioPreview.tsx` — fresh-stream audio pattern (LD-184) reusable for Phase B preview

API endpoints catalog (`endpoints.ts`) extended in S5.5c — verify before S5.5f:

- Phase B endpoints (`phase_b_regen_audio`, `phase_b_mix_audio`, `phase_b_lipsync`) live since S4 v3.1
- `/api/canonical_stitch` does NOT exist (Cursor v8 caught this — see master overview §11);
  S5.5f §3.5 should implement Phase A stitch via `_handle_phase_b_mix_audio` which calls
  `_auto_assemble_phase_a_stitched` internally
- `/api/phase_b/ambient_preset_list` does NOT exist (Cursor v8); S5.5f §3.7 must implement
  filesystem scan endpoint OR static preset list

## §3 Things to read first (in order)

1. `STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md` (cross-cutting context)
2. `STORYBOARD_V59_S5_5_F_SPEC_v1.md` (when authored)
3. v3 spec architecture (`STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md`) — §3.1-3.4 for state shape
4. Predecessor activity_log row `S5_5E_COMPLETE` (Directus `prod_activity_log`)
5. S5.5c LDs 496-499 + S5.5e LDs 500-504 (Directus `prod_locked_decisions`) — reuse-aware design

## §4 Out of scope (defer to S5.5g or S6+)

- Stitcher SFX cue placement / transitions / per-slot trims (S5.5g)
- StitcherTab + ProductionMapTab raw-fetch migration (S5.5g)
- Multi-event mapping in Production Map (S5.5g)
- Voice profile management UI (LD-462; defer to S6)

## §5 Phase 0 obligations

Standard preflight per master overview §9 — write `prod_preflight_reviews` row referencing
S5.5e's preflight as immediate predecessor. Run `try_post_or_queue` per Rule 35.

## §6 Browser smoke (Phase 6.6)

S5.5c + S5.5e Phase 6.6 deferred to Kim hands-on (Chrome MCP not connected in CLI). When
Kim runs browser smoke for S5.5f, she should also confirm S5.5c + S5.5e end-to-end:

- Beat Generator: extract → 3 options → accept → cost display
- Cropper: open modal → drag rect → save → real PNG bytes
- ProjectSelector: dropdown groups Events/Milestones; + New Milestone modal regex
- Storyboard buttons: state-machine visibility per beat lifecycle
- Production Map: 59 modules render across 10 arcs
- Send Out as MP4: still works after raw-fetch migration

If any S5.5c/e gate fails on browser smoke, surface in S5.5f Phase 0 and address before new work.

---

**End of S5.5f handoff stub.** Write spec next session.
