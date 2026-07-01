# Session closure — ambient loop, O3 gallery, stitch preview (2026-07-01)

Audit trail for the conversation that shipped Post–FA&F V3 (`389b2ba`) plus the follow-on stitch preview guard commit.

---

## Bugs caught

### FF-026 — Ambient bed harsh restart every ~2s (`STITCH_AMBIENT_SINGLE_SEAM_V1` regression)

| Era | Symptom | Root cause |
|-----|---------|------------|
| Pre-`9baf4fe` | Soft loop ~0:25, harsh restart ~0:27 | Full ~27s tile with body+glue concat → 2 seams per bed period |
| `SINGLE_SEAM_V1` | Harsh restart every ~2s | Tile was **only** the 2.5s crossfade; `aloop` repeated every ~2.5s |
| **`FULL_PERIOD_TILE_V2`** | Target: one soft seam per ~27s period | `pre` (~24.5s body) + `wrap` (2.5s tri crossfade) → full-period tile → `aloop` |

**Spec:** `TECH_SPEC_STITCH_AMBIENT_FULL_PERIOD_TILE_V2.md`

### O3 Apply Cut — `video_path not in beat O3 options`

- Sidecar stored Dropbox paths; client sent stale `/Users/kimberlysmith/Project Files/` alias.
- Path **was** present under canonical Dropbox path in options.
- **Fix:** `o3_video_paths_equivalent`, `_canonicalize_req_o3_video_path`, `commit_o3_gallery_mutation` on all persist paths; client Apply Cut uses **slot index only** (no stale `videoPath`).

### Stitch preview clobbered all slot videos with intro (`STITCH_PREVIEW_SLOT_GEOMETRY_GUARD_V1`)

- **Symptom:** Event_4 Stitcher showed `intro_kling_o3_20260629T190620Z.mp4` on intro, phase_a, phase_b, and resolution.
- **Root cause 1:** `_hydrated_preview_slot_dict` returned **first list item** (always intro) when pipeline body had multi-slot list.
- **Root cause 2:** `_persist_stitch_preview_slot_geometry` wrote `video_path` / `video_dur_ms` from that wrong hydrated slot onto the target slot during `POST /api/stitch_editor/preview`.
- **Trigger:** Batch preview rebuild QA for ambient V2 (not the ffmpeg loop code itself).
- **Note:** Resolution was briefly correct after Send to Stitcher (14:10) then clobbered before phase_a/b batch (14:18–14:47 window); full four-slot intro clone happened during 15:09–15:14 preview batch.

---

## Process / architecture changes

| Change | Where |
|--------|--------|
| Full-period ambient tile + sig cache-bust | `stitch_ambient_loop.py`, `stitchConstants.ts`, `authority_registry.py` |
| O3 gallery commit-on-mutation durability | `o3_gallery_option_identity.py`, `background.py`, `beat_generator.py` |
| Export truth closure (FF-022..027) | `TECH_SPEC_OPERATOR_EXPORT_TRUTH_CLOSURE_V1.md`, trim/timeline authority tests |
| Scene assemble `display_order` guard | `beat_generator.py`, `test_scene_assemble_display_order.py` |
| Preview single-slot hydrate (`slot_preview`) | `stitch_editor.py` — hydrate only requested slot |
| Preview geometry persist excludes video lineage | `stitch_editor.py` — no `video_path` / `video_dur_ms` overwrite |
| Multipass verify scripts | `verify_stitch_ambient_durability.sh`, `verify_operator_export_truth_closure_durability.sh`, `verify_o3_gallery_option_identity_durability.sh`, export trim/timeline scripts |

---

## Actions taken (operator / runtime — not in git)

| Action | Detail |
|--------|--------|
| Deploy ambient + bundle to Dropbox | `stitch_ambient_loop.py`, `dist/index.html` → canonical path; Event_1–6 fanout |
| All six dedicated servers verified | Ports 5111–5116 serving `build-sha f817b0c` / merged into `389b2ba` |
| Event_4 ambient preview batch | Rebuilt mux/ambient caches (later found to have triggered slot clobber pre-guard) |
| Event_4 stitch state restore | From snapshot `20260701T141829Z`: phase_a, phase_b, resolution videos + per-slot ambient beds |
| Event_0 HTML fanout | Intentionally excluded by deploy script (milestone); not a regression |

**Runtime restore source (Event_4 correct slot truth):**

| Slot | Video | Ambient bed |
|------|-------|-------------|
| intro | `intro_kling_o3_20260629T190620Z.mp4` | Intro video ambient bed |
| phase_a | `phase_a_lipsync_20260629-165620.mp4` | ambient bed pretty option2 |
| phase_b | `phase_b_hum_v2_take_b_20260629-190853.mp4` | ambient bed pretty option |
| resolution | `resolution_kling_o3_20260701T140524Z.mp4` | ambien bed pretty option4 |

---

## Commits

| Commit | Contents |
|--------|----------|
| `389b2ba` | Post–FA&F V3: ambient V2, O3 gallery, export truth, display_order, tests, verify scripts |
| *(this commit)* | Preview slot geometry guard + test + this closure doc |

---

## QA confirmation (multipass)

- `verify_stitch_ambient_durability.sh` — OK
- `verify_operator_export_truth_closure_durability.sh` — OK
- `test_stitch_ambient_loop*.py` — 17+13 passed
- Server/client `ambient_loop_sig_token()` parity — OK
- Dropbox sha256 parity (loop py, bundle, constants) — OK
- `test_stitch_preview_slot_geometry_guard.py` — 3 passed (post-guard)

---

## Operator guidance

1. **Final kid-facing MP4s** — unchanged; stitch preview cache is separate.
2. **V2 ambient** — applies automatically on next stitch preview/export when sig drifts; no mass rebuild across events required.
3. **After preview guard deploy** — safe to Review individual slots; do **not** bulk-preview all slots on old server code.
4. **If all slots show intro again** — check `stitch_editor_state.json` or restore from `.production_snapshots/`; re-export from Beat Gen Send to Stitcher if needed.
