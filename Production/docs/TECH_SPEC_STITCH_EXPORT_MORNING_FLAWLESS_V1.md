# TECH_SPEC — Stitch Export Morning Flawless v1

**Marker:** `STITCH_EXPORT_MORNING_FLAWLESS_V1`  
**Branch:** `fix/canonical-intro-tail-speech-loudnorm` (extend; do not fork)  
**Prerequisite HEAD:** `777fe269` (intro_tail timeline lock + preflight A/V)  
**Goal:** Kim wakes up, clicks Send to Stitcher, gets a clear terminal outcome, and Stitcher shows the cut (or an honest stale state) — every time.  
**Non-goals:** Full Send-to-Stitcher rewrite; interrupting live export workers; toast-only “fixes”; startup job killers.

---

## 0. 4×4 debate consensus (locked)

### Agents

| Role | Verdict |
|------|---------|
| **FOR** | P0: keep-last-video + stale badge; P1: Directus after `done`; thin compose assert. Drop startup reconcile as a driver. Never interrupt live lock holders. |
| **AGAINST** | Do not build architecture theater. PR 112 / `777fe269` already fixed tonight’s A/V class. Drop contract-module merge, compose publish theater, startup reconcile, Directus surgery if fail-soft is enough. Keep-last can “lie” if badge is weak. |
| **Synthesis (locked)** | Kim’s interrupt concern wins: **no startup reconcile workstream**, no kill of live workers. Against “refactor theater”: **no new mega-module**. For morning flawlessness with evidence from Event_6: (1) **stop wiping playable slot video on lineage stale**, (2) **finalize export `done` before Directus** (preserve stays critical), (3) **compose fail-closed assert after timeline lock** (same drift budget as export). Honest stale banner required so keep-last is not a silent lie. |

### Explicit DROP list (do not implement)

| ID | Dropped item | Why |
|----|--------------|-----|
| D1 | Startup `reconcile_stale_running_jobs` call as a project | Already on POST/poll when lock free; startup call risks race narrative and adds no morning value |
| D2 | Interrupting / preempting live exports | Kim veto; lock-aware zombie reconcile is enough |
| D3 | “Single export contract module” rewrite | Preflight already shared; A/V gap closed in `777fe269`; thin assert reuse only |
| D4 | Toast-only durability | Does not fix wipe / lifecycle |
| D5 | Full stack rewrite | Throws away working gates |

### What we are actually trying to achieve

| Operator moment | Required truth |
|-----------------|----------------|
| Click Send | Preflight = same A/V/readiness rules as export (done in `777fe269`) |
| Job runs | Progress may lag; terminal status is authoritative |
| Job succeeds | `done` means Stitcher slot is playable — **not** “Directus finished” |
| Beat Gen changes after export | Stitcher still shows last cut + **STALE** — not empty / “no job” |
| Rebuild intro_tail | Compose cannot publish drift that export will reject |

---

## 1. Category-unlocker

- **Bug category:** (A) Export job lifecycle couples catalog I/O to terminal success; (B) Lineage invalidation deletes presence instead of demoting authority; (C) Compose can still skip a post-lock assert.
- **Category fix:** Done = upsert+preserve+lineage; presence survives stale; compose asserts export drift budget.
- **Fix type:** CATEGORY
- **Plan:** Spec §2–§6 todos → pytest → commit → fleet restart → live proof Event_6.

---

## 2. Workstream A — Directus after terminal `done`

**Invariant:** `finalize_job(..., "done")` runs only after stitch upsert + lineage stamp + preserve succeed. Directus registration must not gate `done`.

### Todos (complete every item)

| ID | Todo | File(s) | Done when |
|----|------|---------|-----------|
| A1 | Split `_post_export_sidecar` so **preserve** stays inside `_run_bg_export_to_stitcher_core` before return `ok` | `server_handlers/kling_o3.py` | Preserve still called under sidecar lock on success path |
| A2 | Remove Directus `register_bg_export_to_directus` + `persist_directus_export_on_sidecar` from the **blocking** path before core returns `ok` | `kling_o3.py` | Core returns `ok` without awaiting Directus |
| A3 | After `finalize_job(..., "done")` in `_execute_bg_export_to_stitcher_job`, best-effort Directus register + sidecar persist; failures → log + warning only | `kling_o3.py` | Exceptions never flip `done` → `failed` |
| A4 | Stop using progress phase `directus` **before** terminal done (optional post-done log only) | `kling_o3.py` | Poll never sticks on `Registering export…` while slot already updated |
| A5 | Core result may include `directus: { deferred: true }` or omit until post-done attach | `kling_o3.py` | Contract documented in test |
| A6 | Unit test: mock Directus hang/raise after upsert; assert `finalize_job` still `done` | `tests/test_bg_export_directus_after_done.py` (new) | pytest green |
| A7 | Update `test_bg_directus_export_register.py` if it assumes Directus inside core before done | that file | pytest green |
| A8 | Durability grep/script: marker `BG_EXPORT_DIRECTUS_AFTER_DONE_V1` present in worker | `kling_o3.py` + optional verify script line | string present |

**Preserve must remain critical** — only Directus moves. If preserve fails, export still fails (unchanged).

---

## 3. Workstream B — Stale slot keeps playable video

**Invariant:** Lineage mismatch demotes authority (`bg_o3_export_stale=true`) but does **not** remove `video_path` / duration / dry path / playback recipe needed to preview the last export.

### Todos

| ID | Todo | File(s) | Done when |
|----|------|---------|-----------|
| B1 | In `invalidate_stitch_slot_for_bg_o3_selection_change` wipe path: keep `video_path`, `video_dur_ms`, `beat_boundaries`, `dry_export_path`, `playback_recipe_version`; set `superseded_bg_export_video_path` to previous path; set `bg_o3_export_stale` + reason; do **not** clear playable fields | `bg_o3_stitch_invalidation.py` | Code review + test |
| B2 | Still clear **mux-only** caches that would imply fresh mix (`mux_preview_hash` etc.) via existing artifact clear **or** selective clear — must not blank the video | same + `stitch_media_artifacts` | Preview still has `video_path` |
| B3 | Same keep-video policy in `invalidate_stitch_slot_if_export_lineage_stale` when it would clear video | `bg_o3_stitch_invalidation.py` | Test |
| B4 | Marker `STITCH_SLOT_STALE_KEEP_VIDEO_V1` | `bg_o3_stitch_invalidation.py` | present |
| B5 | Rewrite `test_invalidate_clears_resolution_slot_video` → `test_invalidate_marks_stale_keeps_video` | `tests/test_bg_o3_stitch_invalidation.py` | asserts `video_path` retained + stale true |
| B6 | Add TS fields on `StitchSlot`: `bg_o3_export_stale?`, `bg_o3_export_stale_reason?`, `superseded_bg_export_video_path?` | `storyboard-v2` types | compiles |
| B7 | Stitcher UI: when focused/viewer slot (or any loaded slot) has `bg_o3_export_stale`, show undismissable banner: `Stale export — Beat Gen changed since this cut. Send to Stitcher again.` | `StitcherTab.tsx` | `data-testid="stitcher-slot-stale-banner"` |
| B8 | Banner must not claim the cut is the latest Send | copy review in spec | wording locked above |
| B9 | Successful `stamp_bg_o3_export_lineage_on_slot` already clears stale — confirm + test remains | existing test | green |
| B10 | Client marker `data-stitch-slot-stale-keep-video={STITCH_SLOT_STALE_KEEP_VIDEO_V1}` on stitcher pane | `StitcherTab.tsx` | present |

---

## 4. Workstream C — Compose publish assert (thin)

**Invariant:** After `lock_intro_tail_av_to_video_timeline`, drift ≤ `STITCH_EXPORT_CUMULATIVE_AV_MAX_DRIFT_S` (0.05) or compose fails loud.

### Todos

| ID | Todo | File(s) | Done when |
|----|------|---------|-----------|
| C1 | After lock in `apply_intro_tail_speech_loudnorm`, measure A/V drift; `fail(...)` if > budget | `teleport_intro_kit.py` | fail path exists |
| C2 | Prefer importing budget constant from `credentials_lib.ffmpeg_stitch` **or** duplicate 0.05 with comment pointing at export gate (kit already avoids heavy stitch imports — document choice) | `teleport_intro_kit.py` | comment + same numeric budget |
| C3 | Test: loudnorm output drift ≤ 0.05 (already) + assert fail helper if drift forced | `tests/test_intro_tail_speech_loudnorm.py` | green |
| C4 | Marker `INTRO_TAIL_COMPOSE_AV_PUBLISH_GATE_V1` | `teleport_intro_kit.py` | present |

---

## 5. Workstream D — Docs / registry / operator

| ID | Todo | Done when |
|----|------|-----------|
| D1 | This tech spec committed | file on branch |
| D2 | If `authority_registry.py` gets a new concept row, matching `STORYBOARD_AUTHORITY_REGISTRY_v1.md` row same commit | N/A unless added |
| D3 | Update PR 112 body to reference this spec + markers | `gh pr edit` |

---

## 6. Workstream E — Full QA proof (mandatory)

| ID | Todo | Done when |
|----|------|-----------|
| E1 | `pytest` : invalidation, loudnorm, directus-after-done, preflight, export job truth (relevant set) | all green |
| E2 | Commit all fix files on feature branch **before** deploy/restart | clean source tree |
| E3 | Fleet restart `:5111–5116` (Python handlers) | HTTP 200 |
| E4 | Confirm served tooling imports markers (grep running code path / file mtime) | markers visible in checkout HEAD |
| E5 | Event_6: GET preflight `ready=true` | curl proof |
| E6 | Event_6: if no export in flight, optional short proof — or unit+prior live export + invalidate unit proof | documented |
| E7 | Multipass: run invalidate unit twice; run directus-after-done test twice | 2× green |
| E8 | Report Full QA block to Kim | final message |

---

## 7. Out of scope (explicit)

- Changing A/V drift numeric budgets
- Reworking four-files / trim / readiness gates
- Directus reliability / Dropbox deadlock root fix (separate)
- Rewriting Stitcher job bootstrap / soft-refresh
- Milestone-only stitch jobs (follow same invalidation helpers; covered by shared Python)

---

## 8. Acceptance (morning flawless)

1. Send to Stitcher reaches `done` even if Directus deadlocks.  
2. After Beat Gen selection change that invalidates lineage, Stitcher still shows last MP4 + stale banner.  
3. Rebuilding intro_tail via loudnorm cannot leave drift > export budget without compose failure.  
4. No code path interrupts a live export holding `export.lock`.  
5. Existing solutions (async jobs, preflight, four-files, trim, A/V lock `777fe269`) remain.

---

## 9. Implementation order

1. Spec commit-ready (this file)  
2. Workstream A (Directus)  
3. Workstream B (stale keep + UI)  
4. Workstream C (compose assert)  
5. Tests E1 → commit E2 → fleet E3 → proofs E4–E8  
