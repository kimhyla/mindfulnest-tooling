# Stitch Module Final — Single-Pass Bake + Footer Preview — Spec v1

**Status:** CANONICAL (2026-06-21)  
**Scope:** Module bake (`module_pipeline=true`) + Stitcher footer viewer

---

## Target (one sentence)

**Stitch → one 800k encode → gate → pin `M{N}_event_{N}_final.mp4`** — no master archive; optional debug composite only when explicitly enabled later.

---

## Delivery contract (unchanged)

`MODULE_FINAL_LEAN_DELIVERY_V1`: 800k target, 960k cap, ≤80 MB, 1280×720, kid-facing canonical only.

---

## Bake pipeline

1. `_stitch_build_pipeline()` — slots, dissolves, boundary SFX (unchanged)  
2. `encode_module_final_lean(stitch_temp, exports/…_final.mp4)` — **only** kid-facing encode  
3. Gate bitrate + size on **final file only**  
4. `finalize_stitch_bake(..., delivery_profile="module_final_lean")`  
5. `pin_canonical_module(..., delivery_profile="module_final_lean")` — copy-remux only, never CRF heal  

**Removed:** `*_master.mp4`, `master_archive` phase, master fields in job result, pre-lean LD-296 gates.

---

## Stitcher UI

- Footer **persistent shell** always visible (`stitcher-bake-preview-shell`)  
- `<video preload="none">` loads `GET /api/stitch_editor/module_final` when `job.bake_path` set  
- Cache-bust `?v=` revision counter after successful bake  

---

## Acceptance

- Default bake writes no `*_master.mp4`  
- Job `done` → canonical ≤960k, ≤80 MB  
- Footer player plays module final on `:5112` after bake  
- `pin_canonical_module` does not inflate lean file (delivery_profile required)  

---

## Known content issues (Event 2 — separate from bake shape)

| Issue | Cause | Fix |
|-------|-------|-----|
| Intro whiteout too long | Assembled intro predates 4s `trim_back` on mirror beat — duration 175.846s vs ~171.8s expected | **Re-send intro to Stitcher** from Beat Gen (export uses `_kling_o3_export_clip_path`) |
| Phase A clicks ~2.12s | Ambient bed does **not** loop (bed 140s > slot 22s); clicks are **phase_a_stitched** dialogue/track joins | Phase export audio concat category (follow-up) |
