# TECH_SPEC_PHASE_G_INTERACTION_WARM_PATH_V1

**Marker:** `PHASE_G_INTERACTION_WARM_PATH_V1`  
**Extends:** `OPERATOR_UX_ROOT_CAUSE_SYNTHESIS_v1.md`, `TECH_SPEC_WAVEFORM_TIME_AUTHORITY_v1.md`, `TECH_SPEC_STITCH_LIVE_E2E_MILESTONE_V1.md`  
**Status:** Implementation spec — Fast-and-Flawless V3 completion

## Problem

Operator-reported failures (Phase B drag-drop dead, g.4 deploy timeout, library watercolors 0/83) persisted while durability gates showed **shipped** because:

| Meta-root | ID | Failure mode |
|-----------|-----|--------------|
| Proof-surface mismatch | RC11 | Fixture/mock/synthetic proof ≠ live Event_N + real gestures |
| Composite interaction surfaces | RC12 | Bubble DnD + pointer capture + WaveSurfer canvas + overlays — no single owner |
| Catalog / bootstrap invariants | RC13 | Per-event data empty or client cache stale vs server |
| Cold-path work in hot gates | RC14 | ffmpeg mux bake inside Playwright `beforeAll` (600s budget) |

Patches (SEEK-8, `draggable={false}`, watercolor seed) fixed **instances** without closing the **classes**.

## Goals

1. **G1 — Interaction Platform (RC12):** One capture-layer contract for all HTML5 drop targets; no native `<img>` drag hijack on any tile.
2. **G2 — Live Proof Fleet (RC11):** Dedicated ports Event_0–6 build-sha + operator-path browser proof (real drag, not `dispatchEvent`).
3. **G3 — Catalog Invariants (RC13):** Fleet watercolor/stitch/library parity; cache invalidation on count mismatch.
4. **G4 — Warm-Path Deploy (RC14):** `(g.4-pre)` pre-bakes milestone mux **before** Playwright; live E2E only asserts warm hash.
5. **G5 — Meta-gate:** `FAST_AND_FLAWLESS_DONE_V3`, synthesis RC11–RC14, symptom matrix honest status.

## Non-goals

- WTA-0 full `waveformSeekController.ts` extract (future refactor).
- Auto-bake mux on every stitch save (rejected in STITCH_LIVE_E2E spec).
- Kid-facing MindfulNest app changes.

---

## G1 — Interaction Platform

### Contract: `INTERACTION_PLATFORM_V1`

| Rule | Implementation |
|------|----------------|
| DROP-CAPTURE-1 | All drop surfaces call `bindDropTargetCapture(el, handlers)` — never bubble-only `onDrop` on parents with child canvases |
| DROP-IMG-1 | All draggable tiles: `<img draggable={false}>`; payload only from tile `onDragStart` |
| DROP-HOOK-1 | `useDropTargetCapture(ref, handlers, deps)` in `src/hooks/useDropTargetCapture.ts` |

### Surfaces (must bind capture)

- `WaveformTimeline.tsx` ✓
- `StitcherTab.tsx` — slot waveform + module strip
- `BgTab.tsx` — beat option / ref drop targets
- `StoryboardTab.tsx` — end frame + option slots
- `CropperModal.tsx` — canvas drop

### Gates

- `verify_interaction_platform_durability.sh` — grep all consumers + AssetTile img + DROP-WC-2 e2e
- Playwright: `DROP-WC-2` (canvas child drop), future `DROP-CAPTURE-AUDIT-1` grep in CI

---

## G2 — Live Proof Fleet

### Contract: `LIVE_FLEET_PROOF_V1`

| Port | Event | Proof |
|------|-------|-------|
| 5111 | Event_1 | build-sha + hydrate |
| 5112 | Event_2 | build-sha + g.4 assert |
| 5113 | Event_3 | build-sha + hydrate |
| 5114 | Event_4 | build-sha + **Phase B dragTo watercolor** |
| 5115 | Event_5 | build-sha + catalog ≥1 watercolor |
| 5116 | Event_6 | build-sha + catalog ≥1 watercolor |

### E2E

- `e2e/phase_g_interaction_live.spec.ts` — `--config playwright.live.config.ts`
- `DROP-WC-LIVE-1` — Event_4 Phase B: tile.dragTo(waveform) → `data-cue-count=1`
- `LIB-WC-LIVE-1` — library watercolors filter count > 0 when API has rows

### Gate

- `verify_live_fleet_interaction.sh` — curl fleet + optional Playwright when servers up

---

## G3 — Catalog Invariants

### Contract: `EVENT_CATALOG_INVARIANTS_V1`

On deploy (all Event_* under Production/):

1. `library/watercolors/` non-empty OR explicit bootstrap from template (`seed_event_watercolors_if_empty`).
2. `GET /api/phase/watercolor_list` count == cr_library watercolor tier count.
3. Library client cache key `mn.library.items.v4` + invalidate when server watercolor count ≠ cached watercolor rows after fetch.

### Scripts

- `bootstrap_event_watercolors.py` — fleet (existing)
- `verify_event_catalog_invariants_durability.sh` — HTTP + disk per Event_1..6

Deploy hook: run bootstrap + catalog verify after fanout.

---

## G4 — Warm-Path Deploy

### Contract: `DEPLOY_MUX_WARM_G4_PRE_V1`

**Before** `verify_stitch_sfx_playback_truth_live_e2e.sh`:

1. `GET /api/stitch_editor/job/Event_2_stitch` (300s max) — drain load_job queue.
2. `POST /api/stitch_editor/preview` for milestone standalone if `mux_preview_hash` missing (same body as E2E bootstrap).
3. Poll `GET job` until `standalone.mux_preview_hash` ≥ 8 hex chars (600s max).
4. Write marker: `Production/.deploy_mux_warm/Event_2_milestone.ok` with hash + timestamp.

**Playwright `beforeAll`:** If hash present → skip bake; else fail fast with message "run deploy_mux_warm_g4_pre.sh".

### Gate

- `verify_deploy_warm_path_durability.sh` — script exists; E2E does not POST preview when marker fresh

---

## G5 — Meta-gate

- `FAST_AND_FLAWLESS_DONE_v1.md` → V3 rows FF-015..FF-018
- `OPERATOR_UX_ROOT_CAUSE_SYNTHESIS_v2.md` — RC11–RC14
- `OPERATOR_UX_SYMPTOM_MATRIX_v1.md` — WTA-023..030 rows
- `verify_fast_and_flawless_done.sh` — runs G1–G4 sub-gates

---

## Dependency order

```
G4-pre script + E2E fast-fail
  → G1 interaction hook + fleet audit
  → G3 catalog bootstrap + cache + deploy hook
  → G2 live fleet E2E + visual proof
  → G5 meta-gate + full deploy + multipass QA
```

---

## Proof of done

| Step | Proof artifact |
|------|----------------|
| G1 | `verify_interaction_platform_durability.sh` exit 0; DROP-WC-2 green |
| G3 | `verify_event_catalog_invariants_durability.sh` exit 0 on :5114 |
| G4 | `.deploy_mux_warm/Event_2_milestone.ok` exists; g.4 beforeAll < 60s |
| G2 | Browser screenshot: Event_4 Phase B cue on waveform after dragTo |
| G5 | `verify_fast_and_flawless_done.sh` exit 0 (or documented skip if no servers) |
| Ship | `build-sha` = git HEAD on :5111–5114; commit on feature branch |

---

## Maintenance

When adding a new drop target or draggable tile, extend G1 grep gate and `useDropTargetCapture`. When adding Event_N port, extend G2 fleet table.
