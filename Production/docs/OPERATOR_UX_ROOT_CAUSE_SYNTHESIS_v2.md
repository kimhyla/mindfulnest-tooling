# Operator UX Root Cause Synthesis v2

**Marker:** `OPERATOR_UX_ROOT_CAUSE_SYNTHESIS_V2`  
**Extends:** `OPERATOR_UX_ROOT_CAUSE_SYNTHESIS_v1.md`, `TECH_SPEC_PHASE_G_INTERACTION_WARM_PATH_V1.md`  
**Date:** 2026-06-27

---

## Phase G meta-roots (RC11–RC14)

Operator-reported Phase B drag-drop failures persisted while gates showed green because four **class-level** gaps were outside v1 taxonomy:

| ID | Name | Definition | Fix (Phase G) |
|----|------|------------|---------------|
| **RC11** | Proof-surface mismatch | Fixture/mock/synthetic proof ≠ live Event_N + real pointer gestures | `phase_g_live_interaction.spec.ts`, `verify_live_fleet_interaction.sh`, FF-014 → :5111–5116 |
| **RC12** | Composite interaction surfaces | Bubble DnD + pointer capture + WaveSurfer canvas — no single drop owner | `INTERACTION_PLATFORM_V1`, `useDropTargetCapture`, `verify_interaction_platform_durability.sh` |
| **RC13** | Catalog/bootstrap invariants | Empty per-event watercolors or stale library session cache | `EVENT_WC_SEED_V1`, `verify_event_catalog_invariants_durability.sh`, Library cache v4 reconcile |
| **RC14** | Cold-path in hot gates | ffmpeg mux bake inside Playwright `beforeAll` (600s budget) | `deploy_mux_warm_g4_pre.sh`, fast-fail live E2E |
| **RC14b** | Milestone vs event stitch contention | g4-pre POST/GET blocked behind `Event_2_stitch` load_job auto-bake; urllib 300s timeout masquerades as generic "timed out" | g4-pre must drain `Event_2_stitch` first; preview timeout 900s |

---

## Symptom → meta-root map (WTA-023..030)

| ID | Meta-root | Layer |
|----|-----------|-------|
| WTA-023 | RC12 | Client drop capture + `draggable={false}` on tiles |
| WTA-024 | RC13 | Library fetch reconcile with `phase_watercolor_list` |
| WTA-025 | RC13 | Server/disk bootstrap on event create + deploy hook |
| WTA-026 | RC12 | Fleet audit of all `makeDropTarget` consumers |
| WTA-027 | RC14 | Warm-path deploy before g.4 Playwright |
| WTA-028 | RC11 | Live `dragTo` on Event_4 :5114 |
| WTA-029 | RC11 | Extended fleet build-sha gate |
| WTA-030 | RC11 | Operator-path proof on Phase B stem mode (not Stitcher-only SEEK-8) |

---

## v1 meta-roots (unchanged)

RC1–RC10 from synthesis v1 remain valid. Phase E session merge (RC2) stays **shipped** for operator edit surfaces.

---

## Maintenance

When adding a drop target → extend G1 grep gate. When adding Event_N port → extend G2 fleet table. When adding cold server work to E2E `beforeAll` → move to deploy warm script (RC14).
