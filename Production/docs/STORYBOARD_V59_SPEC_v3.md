# Technical Spec: Storyboard v59 — Path C Greenfield Rewrite (v3)
**Date:** 2026-05-02
**Produced by:** tech-spec skill (v2 + Cursor cross-review v2 findings)
**Status:** Awaiting Cursor cross-review v3 before Session 1.5 execution
**Supersedes:** `STORYBOARD_V59_SPEC_v2.md`. v1 superseded by v2; v2 superseded by this.

---

## Changelog v2 → v3

| Section | Change |
|---|---|
| §3.4 | Fixed prose vs implementation mismatch — `_assert_event_scope` reads `body['event_id']`; v59 client sends `scope_event_id`; BG handlers map `{event_id: body.get("scope_event_id")}`. Spec contract now matches code |
| §3.5.1 NEW | Async job completion rule — capture `(generation, event_dir_path)` at enqueue; validate generation before terminal `mutate_state`; on mismatch discard + log + return 409 to poller. Closes Cursor v2's biggest remaining hole |
| §3.6 | Added footnote requiring grep-proof of v58 `.L.json` hydration before Session 1.5 |
| §4 S1.5 | Handler count revised UP — ~40 NEW guards (not 16); estimate up to 4-6 hours; `_handle_v2_event_state` marked "verify only" (URL validation already exists at L9405+) |
| §12 | Expanded handler matrix — added timeline endpoints, v2_module_patch, budget_override, cr_library_delete, all mutating BG POSTs, lipsync handlers, beat operations |
| §10 | Added: line-number drift in §12 acceptable; future audit script generates the matrix from grep |

---

## 1. Task

(Same as v2.)

**Operating mode (per Kim's Q1/Q2 confirmation):** Single-user, one-version-at-a-time. Kim only ever works in the latest version. Server is pinned to ONE storyboard via `--storyboard` flag at any moment.

---

## 2. Governing Decisions

(Same as v2.)

---

## 3. Approach

### 3.1 Frontend rewrite scope is bounded

Same as v2.

### 3.2 Mutation channel vs read channel

Same as v2. (`pathappPatch` for writes, `apiGet` for reads, WaveSurfer's internal `<audio>` exempt as a stream.)

### 3.3 Single mutation channel implementation

Same as v2.

### 3.4 Scope tokens — CORRECTED contract

Every signal store is keyed by `{event_id, beat_id, version}`. Every server request includes a scope payload. The server's `_assert_event_scope` function (defined at `production_server.py:4364`) reads `body['event_id']` (with URL query string fallback) and compares against `self.app.event_dir.name`.

**v59 client convention vs server function:**
- v59 client sends `scope_event_id` in every mutation body (matches the existing BG handler convention introduced by LD-456)
- For BG handlers (`_handle_bg_*`), the server maps the v59 client's `scope_event_id` → `event_id` parameter at the call site:
  ```python
  if not self._assert_event_scope({"event_id": body.get("scope_event_id")}, allow_missing=True):
      return
  ```
- For non-BG handlers (`_handle_assign_image`, `_handle_v2_patch`, `_handle_phase_b_*`, etc.), the v59 client sends `event_id` directly OR the server maps `scope_event_id` → `event_id` — pick one convention per handler family and document inline
- The function itself remains untouched; only call sites change

**`allow_missing` policy:**
- All existing 13 LD-456 guards: keep `allow_missing=True` (legacy v58 client compat)
- All NEW ~40 guards added in Session 1.5: also `allow_missing=True` initially
- v59 client ALWAYS sends scope (verified via Playwright) — so v59 path always validates
- **Earlier flip (NEW per Cursor v2 #2):** flip `allow_missing=False` on `_handle_v2_patch`, `_handle_assign_image`, `_handle_beat_update_text` once v59 ships and v58 is retired (Session 4-5, not Session 5)
- Remaining handlers: flip in Session 5 cutover

### 3.5 `/api/event/load` concurrency model

(Same as v2.)

### 3.5.1 Async job completion rule (NEW per Cursor v2 — closes the biggest remaining hole)

Background threads (lipsync, magic compositor, ffmpeg jobs, FLUX submissions, ElevenLabs generations) can take 30 seconds to several minutes. If `/api/event/load` fires during a long job, the job's terminal `mutate_state` could attach output to the wrong event. Mechanism:

**At job enqueue:**
```python
job["pinned_generation"] = self.app.event_generation
job["pinned_event_dir"] = Path(self.app.event_dir)  # captured by value
```

**At terminal mutate_state (or registering output, or appending to state.beats[]):**
```python
if self.app.event_generation != job["pinned_generation"]:
    log_warning(f"Job {job_id} discarded — event changed mid-flight ({job['pinned_event_dir'].name} → {self.app.event_dir.name})")
    job["status"] = "discarded_event_changed"
    # Files at pinned_event_dir/ are NOT deleted — they're orphaned but recoverable
    # Polling client (if any) gets HTTP 409 with discarded status
    return
# Generation matches — safe to mutate
self.app.state.mutate_state(...)
```

**Recovery path:** orphaned files at the pinned event_dir can be re-attached via a manual one-shot script if Kim notices a missing output. They're not lost — they just didn't get registered to state.

**Applies to:** `_handle_lipsync_submit` background thread, `_handle_magic_submit_path` background thread, `_handle_phase_b_lipsync` (synchronous but long), `_handle_phase_b_mix_audio` (ffmpeg), `_handle_bg_assemble_group`, `_handle_bg_run_local_animation`, `_handle_stitch_bake`, any future async job.

**Implementation in Session 1.5:** add the `pinned_generation`/`pinned_event_dir` fields to job dicts; add the validation-before-terminal-mutate at every async completion. Estimate: +30-60 minutes on top of the synchronous guard work.

### 3.6 Persistence contract (state.json + sidecar; HTML conditional)

(Same as v2.)

**Footnote (NEW per Cursor v2):** Before claiming "v58 hydrates from `.L.json` on render," verify with one grep against `Production/Event_1/storyboard_v58_prod.html`:
```
grep -n "L.json\|/api/v2/storyboard/L\|/api/v2/sidecar" Production/Event_1/storyboard_v58_prod.html
```
If hits found → confirms hydration path → §3.6's "v58 sees v59 writes after rollback" claim holds. If no hits → spec must be updated to either (a) require v59 to ALSO patch v58-shape HTML inline as a fallback, or (b) document the rollback as "data preserved on disk but v58 won't see it without manual intervention."

This grep is part of Session 1.5 verification gate (§8).

### 3.7 v58/v59 split-brain rules (per Kim's Q1)

(Same as v2.)

### 3.8 Phase A and Phase B producers in scope

(Same as v2.)

### 3.9 "Animate this" bridge — v59-only (per Kim's Q2)

(Same as v2.)

### 3.10 Production Map

(Same as v2.)

---

## 4. Implementation Steps

### Session 1 — DONE (commit 23812d9)
(Same as v2.)

### Session 1.5 — Server scope guards (~40 NEW handlers) + concurrency lock + async job rule + persistence contract + new endpoints (~4-6 hours, revised UP from 3-4)

1. Open `prod_preflight_reviews` row.
2. Register `STORYBOARD_V59_SPEC_V1` (rev3) + `EVENT_LOAD_GENERATION_LOCK_V1` + `UNIVERSAL_AUTOSAVE_V1` + `ASYNC_JOB_GENERATION_PIN_V1` (NEW per §3.5.1) LDs.
3. **Verify §3.6 grep proof** — run `grep -n "L.json\|/api/v2/storyboard/L\|/api/v2/sidecar" Production/Event_1/storyboard_v58_prod.html`. If empty, halt and surface to Kim before proceeding.
4. **Add scope guards to ~40 currently-unguarded handlers** (NOT 16 — that was v2's undercount). Use `_assert_event_scope({"event_id": body.get("scope_event_id") or body.get("event_id")}, allow_missing=True)` pattern.

   **Critical priority (HIGH severity for cross-event corruption):**
   - `_handle_v2_patch` @9010 — canonical write path; HIGHEST priority
   - `_handle_v2_module_patch` @9456 — module-level state
   - `_handle_v2_event_state` @9405 — **VERIFY ONLY** (URL validation already exists per code at L9405+); just confirm + add to test suite
   - `_handle_v2_sidecar` @9349
   - `_handle_v2_beat_create` @9160
   - `_handle_v2_beat_swap_to_a` @9535

   **State + file mutating:**
   - `_handle_select` @8849
   - `_handle_animate` @7705
   - `_handle_add_options` @7936
   - `_handle_redo` @7886
   - `_handle_use_as_final` @7368
   - `_handle_beat_delay` @8944
   - `_handle_beat_trim` @8967
   - `_handle_export` @8901
   - `_handle_preview_stitched` @9696
   - `_handle_budget_override` @9000

   **Phase A/B (all currently unguarded):**
   - `_handle_phase_b_regen_audio` @11557
   - `_handle_phase_b_mix_audio` @11829
   - `_handle_phase_b_lipsync` @12237
   - `_handle_phase_b_preview` @12419

   **BG mutating handlers (~13 of 22 total):**
   - `_handle_bg_delete_beat` @5720
   - `_handle_bg_submit_flux` @5809
   - `_handle_bg_submit_gpt_batch` @5846
   - `_handle_bg_accept_option` @5925
   - `_handle_bg_accept_lib_image` @5957
   - `_handle_bg_add_beat` @6003
   - `_handle_bg_create_group` @6053
   - `_handle_bg_delete_group` @6073
   - `_handle_bg_update_group` @6086
   - `_handle_bg_assemble_group` @6101
   - `_handle_bg_run_local_animation` @6155
   - `_handle_bg_update_beat_anim_method` @6230
   - `_handle_bg_accept_local_animation` @6250

   **Timeline (4 mutating):**
   - `_handle_timeline_cue_upsert` @10513
   - `_handle_timeline_delete_cue` @10558
   - `_handle_timeline_bake` @10577
   - `_handle_timeline_preview_with_sfx` @10602

   **Magic + Lipsync + Stitch:**
   - `_handle_magic_submit_path` @4798
   - `_handle_lipsync_submit` @6818 (was TODO in v2; now confirmed needs guard)
   - `_handle_lipsync_submit_legacy` @7159
   - `_handle_stitch_save_job` @10907
   - `_handle_stitch_bake` @11396

   **Destructive disk:**
   - `_handle_cr_library_delete` @5335

5. **Audit `_handle_bg_reorder_beats` segment_index inconsistency** (L5486). Flag as latent bug; do NOT fix in this scope; add tracking entry to `prod_blockers`.

6. **Add `/api/event/load` concurrency mechanism** per §3.5 — same as v2.

7. **Apply async job completion rule (§3.5.1)** to all background-thread handlers:
   - `_handle_lipsync_submit` (and `_legacy`)
   - `_handle_magic_submit_path`
   - `_handle_phase_b_lipsync`
   - `_handle_phase_b_mix_audio`
   - `_handle_bg_assemble_group`
   - `_handle_bg_run_local_animation`
   - `_handle_stitch_bake`
   - `_handle_bg_submit_flux`
   - `_handle_bg_submit_gpt_batch`
   At enqueue: capture `(generation, event_dir_path)` in job dict. At terminal mutate_state: validate, discard + log + 409 on mismatch.

8. **Make HTML-patching conditional** on filename pattern in `_handle_assign_image:6276`, `_handle_beat_update_text:8276`, `_handle_inject_image:6393`. (Same as v2.)

9. **v59 client ALWAYS writes `.L.json` sidecar** on every mutation that touches dialogue/image fields. (Same as v2.)

10. Add `POST /api/state/snapshot` and `POST /api/event/load` endpoints. (Same as v2.)

11. **DROP M6 isolation lock** (UA-based) — superseded by `--storyboard` flag pinning per Kim's Q1.

12. Wire v59 client's `pathappPatch` to (a) call `/api/state/snapshot` before mutation, (b) include `scope_event_id` AND/OR `event_id` per handler convention, (c) handle 423 by re-hydrating + retry-prompt, (d) handle 409 (scope mismatch) with red banner + reload prompt.

13. **Verification (CORRECTED — uses `scope_event_id` AND `event_id` correctly per §3.4):**
    - ✅ `curl -X POST http://localhost:5111/api/bg/accept-beats -H "Content-Type: application/json" -d '{"scope_event_id":"Event_2","beats":[],"segment":0}'` returns HTTP 409
    - ✅ `curl -X POST http://localhost:5111/api/v2/beat/beat_01/patch -H "Content-Type: application/json" -d '{"event_id":"Event_2","field":"text","value":"x"}'` returns HTTP 409
    - ✅ `curl http://localhost:5111/api/v2/event/Event_2/state` returns HTTP 409 (URL validation already exists at L9405+; verify it fires)
    - ✅ `curl -X POST http://localhost:5111/api/state/snapshot -H "Content-Type: application/json" -d '{"event_id":"Event_1"}'` returns snapshot path + sha256
    - ✅ `curl -X POST http://localhost:5111/api/event/load -H "Content-Type: application/json" -d '{"arc_number":1,"event_id":"Event_1","module_id":"M1"}'` returns active event + new generation number
    - ✅ Concurrency proof: spawn 2 parallel `/api/event/load` calls + verify generation counter is sequential (not interleaved)
    - ✅ **Async job test (NEW per §3.5.1):** trigger a `_handle_phase_b_lipsync`; while it's processing, fire `/api/event/load`; verify the lipsync's terminal `mutate_state` is rejected with discard log + 409 to poller
    - ✅ NEW negative test: `curl -X POST http://localhost:5111/api/bg/accept-beats -d '{"beats":[]}'` (NO scope_event_id) returns 200 (legacy compat) — confirms `allow_missing=True` working as documented
    - ✅ Session 1 Playwright smoke still green
    - ✅ Manual: dialogue edit in v59 → reload → persists; flag-flip to v58 → visible (via state.json hydration); flag-flip to v59 → still there

### Sessions 2 / 2.5 / 2.7 / 2.9 / 3 / 3.5 / 4 / 5

(Same as v2.)

---

## 5. Files Created / Modified

(Same as v2 except:)

| Path | Action | Why |
|---|---|---|
| `Production/tools/production_server.py` | Modify (~150-300 lines, revised UP from 80-200) | ~40 new scope guards + concurrency lock + async job pinning + 7 new endpoints + HTML-patch conditional |

---

## 6. Directus Writes Required

(Same as v2 + add `ASYNC_JOB_GENERATION_PIN_V1` LD.)

---

## 7. Error Cases and Handling

(Same as v2 + NEW row:)

| Failure | Detection | Response |
|---|---|---|
| Async job's terminal `mutate_state` runs after event switch | Validation at job completion checks `pinned_generation != self.app.event_generation` | Discard mutate; log warning; mark job `discarded_event_changed`; orphan file at `pinned_event_dir` (not deleted, recoverable); poller gets HTTP 409 |

---

## 8. Verification

(Same as v2 with the corrected curls + new async job test in step 13 above.)

---

## 9. Rollback

(Same as v2.)

---

## 10. Out of Scope (V1)

(Same as v2 + NEW:)

- **§12 line numbers as canonical reference** — line numbers drift; treat appendix as approximate; future enhancement is a generated audit script (`Production/scripts/handler_scope_audit.py`) that re-derives the matrix from grep.
- **Manual recovery of orphaned async job outputs** — when async job is discarded due to event switch, files remain at `pinned_event_dir` but unregistered. Future enhancement: `Production/scripts/recover_orphaned_jobs.py` script.

---

## 11. Cursor Cross-Review Questions (v3)

The v2 spec already had Cursor v2 review (HIGH findings folded into this v3). New questions for Cursor v3:

1. **Async job rule completeness (§3.5.1):** does the rule handle ALL async paths, or are there async patterns I missed? Specifically: are there cases where `mutate_state` happens INSIDE a callback that doesn't have access to the original job dict? Are there async paths that DON'T go through `mutate_state` but still write under `event_dir` (e.g., directly writing files)?

2. **Handler matrix completeness v3:** with ~40 handlers now listed, did I still miss any? Specifically check: every `def _handle_*` that contains `mutate_state` OR `event_dir` write. (80 `mutate_state` references in file — but some are within already-listed handlers as multiple call sites.)

3. **`_handle_storyboard_switch` exclusion:** confirmed correct (it intentionally switches storyboard files within the same event)?

4. **Earlier `allow_missing=False` flip (§3.4):** is the proposed staging right (flip 3 critical handlers in Session 4-5; rest in Session 5 cutover)? Is there a handler I should flip even earlier (e.g., in Session 3 once v59 is ahead of v58 in features)?

5. **§3.6 grep proof requirement:** is there a stronger verification than grep (e.g., a Playwright test that writes via v59, flips to v58, asserts the value appears)?

6. **`scope_event_id` vs `event_id` convention per handler family:** is there value in standardizing one or the other across ALL handlers, or is the dual convention pragmatic given existing BG code?

7. **Async job orphan recovery:** is the "orphan files, recover manually" stance acceptable, or should the spec require automatic re-registration when generation matches again?

---

## 12. Handler Matrix Appendix (v3 — expanded per Cursor v2)

Every `_handle_*` that touches `mutate_state` or writes under `event_dir`. Status reflects code as of grep on 2026-05-02. **Line numbers approximate; will drift.**

### ✅ Already guarded (LD-456 — DO NOT re-add)

| Handler | Line | Notes |
|---|---|---|
| `_handle_assign_image` | ~6492 | Make HTML-patch conditional on filename in S1.5 |
| `_handle_beat_update_text` | ~8528 | Make HTML-patch conditional |
| `_handle_inject_image` | ~6626 | Make HTML-patch conditional |
| `_handle_cr_save_crop` | ~6338 | None |
| `_handle_bg_set_active_context` | ~5520 | None |
| `_handle_bg_extract_beats` | ~5553 | None |
| `_handle_bg_inject_beats` | ~5597 | None |
| `_handle_bg_update_beat` | ~5668 | None |
| `_handle_bg_reorder_beats` | ~5700 | Flag latent segment_index bug |
| `_handle_bg_accept_beats` | ~5752 | None |
| `_handle_v2_event_state` (URL) | ~9405 | **VERIFY ONLY** — URL validation already exists per code at L9405-9450; just confirm + add Playwright assertion |

### ❌ Needs guard added in Session 1.5 (~40 handlers)

#### Critical priority (highest cross-event corruption risk)
| Handler | Line | Why critical |
|---|---|---|
| `_handle_v2_patch` | ~9010 | Canonical write path; ALL beat patches route here |
| `_handle_v2_module_patch` | ~9456 | Module-level state mutations |
| `_handle_v2_sidecar` | ~9349 | Serves event-scoped sidecar |
| `_handle_v2_beat_create` | ~9160 | Creates new beats |
| `_handle_v2_beat_swap_to_a` | ~9535 | Swaps beat options |

#### State + file mutating
| Handler | Line |
|---|---|
| `_handle_select` | ~8849 |
| `_handle_animate` | ~7705 |
| `_handle_add_options` | ~7936 |
| `_handle_redo` | ~7886 |
| `_handle_use_as_final` | ~7368 |
| `_handle_beat_delay` | ~8944 |
| `_handle_beat_trim` | ~8967 |
| `_handle_export` | ~8901 |
| `_handle_preview_stitched` | ~9696 |
| `_handle_budget_override` | ~9000 |
| `_handle_cr_library_delete` | ~5335 (destructive) |

#### Phase A/B (all currently unguarded)
| Handler | Line |
|---|---|
| `_handle_phase_b_regen_audio` | ~11557 |
| `_handle_phase_b_mix_audio` | ~11829 |
| `_handle_phase_b_lipsync` | ~12237 |
| `_handle_phase_b_preview` | ~12419 |

#### BG mutating (13 of 22 total handlers — others are reads/polls)
| Handler | Line |
|---|---|
| `_handle_bg_delete_beat` | ~5720 |
| `_handle_bg_submit_flux` | ~5809 |
| `_handle_bg_submit_gpt_batch` | ~5846 |
| `_handle_bg_accept_option` | ~5925 |
| `_handle_bg_accept_lib_image` | ~5957 |
| `_handle_bg_add_beat` | ~6003 |
| `_handle_bg_create_group` | ~6053 |
| `_handle_bg_delete_group` | ~6073 |
| `_handle_bg_update_group` | ~6086 |
| `_handle_bg_assemble_group` | ~6101 |
| `_handle_bg_run_local_animation` | ~6155 |
| `_handle_bg_update_beat_anim_method` | ~6230 |
| `_handle_bg_accept_local_animation` | ~6250 |

#### Timeline (4 mutating)
| Handler | Line |
|---|---|
| `_handle_timeline_cue_upsert` | ~10513 |
| `_handle_timeline_delete_cue` | ~10558 |
| `_handle_timeline_bake` | ~10577 |
| `_handle_timeline_preview_with_sfx` | ~10602 |

#### Magic + Lipsync + Stitch
| Handler | Line |
|---|---|
| `_handle_magic_submit_path` | ~4798 |
| `_handle_lipsync_submit` | ~6818 |
| `_handle_lipsync_submit_legacy` | ~7159 |
| `_handle_stitch_save_job` | ~10907 |
| `_handle_stitch_bake` | ~11396 |

### ⚠️ Async-completion handlers (need both scope guard AND §3.5.1 generation pinning)

| Handler | Line | Async job dict |
|---|---|---|
| `_handle_lipsync_submit` | ~6818 | `_LIPSYNC_JOBS` |
| `_handle_lipsync_submit_legacy` | ~7159 | `_LIPSYNC_JOBS` |
| `_handle_magic_submit_path` | ~4798 | `_MAGIC_JOBS` |
| `_handle_phase_b_lipsync` | ~12237 | (synchronous but long; pin captured at entry) |
| `_handle_phase_b_mix_audio` | ~11829 | (synchronous ffmpeg) |
| `_handle_bg_assemble_group` | ~6101 | `_ASSEMBLE_JOBS` |
| `_handle_bg_run_local_animation` | ~6155 | (background) |
| `_handle_bg_submit_flux` | ~5809 | `_FLUX_JOBS` |
| `_handle_bg_submit_gpt_batch` | ~5846 | `_GPT_JOBS` |
| `_handle_stitch_bake` | ~11396 | (synchronous fcntl-locked) |

### ➖ Read-only or special — no guard needed

| Handler | Line | Why |
|---|---|---|
| `_handle_storyboard_switch` | ~7258 | Intentional cross-storyboard (not cross-event) |
| `_handle_voice_profile_get` | ~11701 | Read-only |
| `_handle_voice_profile_update` | ~11745 | Cross-event safe (Chipper id=2 only) |
| `_handle_files_serve` | ~6063 | Static file |
| `_handle_state` (read) | various | Read-only |
| `_handle_bg_segments` | ~5129 | Read-only (returns list) |
| `_handle_bg_session_state` | ~5137 | Read-only |
| `_handle_bg_poll_*` | various | Read-only (job polling) |
| `_handle_bg_groups` | ~5991 | Read-only |
| `_handle_bg_stills` | ~6276 | Read-only (file serve) |
| `_handle_timeline_audio` | ~10175 | Read-only |
| `_handle_timeline_sfx_library` | ~10462 | Read-only |
| `_handle_timeline_open_in_quicktime` | ~10583 | Read-only (no state mutation) |

**Total: 11 already guarded + ~40 to add + 11 read-only/special = 62 handlers reviewed.** The ~40-handler add is the bulk of Session 1.5 server work.

**Note:** `mutate_state` appears 80 times in the file — many are multiple call sites within a single handler (e.g., `_handle_v2_patch` mutates state for multiple field types in branch logic). Per-handler count (62 reviewed) is the correct denominator, not per-mutation-call count.

---

**End of spec v3. Awaiting Cursor cross-review v3.**
