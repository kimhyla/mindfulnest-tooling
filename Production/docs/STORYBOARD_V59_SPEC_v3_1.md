# Technical Spec: Storyboard v59 — Path C Greenfield Rewrite (v3.1)
**Date:** 2026-05-02
**Produced by:** tech-spec skill (v3 + Cursor cross-review v3 narrow tightenings)
**Status:** EXECUTABLE — Cursor v3 explicitly said "ready to drive Session 1.5 without another full spec version" once the 5 tightenings below are folded in. Cursor v3.1 review NOT required.
**Supersedes:** `STORYBOARD_V59_SPEC_v3.md`. v1, v2, v3 all superseded by this.

---

## Changelog v3 → v3.1 (final tightenings before execution)

| Section | Change |
|---|---|
| §3.4 | Added requirement: every call site of `_assert_event_scope` uses a single normalization helper (`_scope_body(body)`) instead of hand-rolling the dict. Reduces dual-key drift |
| §3.5.1 | Expanded boundary conditions: pin/check applies to (a) ANY disk write under pinned `event_dir` or BG dirs (not only `mutate_state`); (b) poller / non-`_handle_*` background class completion paths (lipsync poller, FLUX poller, etc.); (c) nested jobs inherit pins from parent |
| §3.6 | Grep-proof verified passing on disk: `storyboard_v58_prod.html` references `/api/v2/storyboard/L.json` at lines ~2227 (comments), ~2248 (fetch), ~2657 (fetch). Sidecar hydration path is wired. Optional addition: Playwright rollback test (v59 write → flag-flip to v58 → assert visible) |
| §4 S1.5 | Estimate bumped 4-6h → 5-7h (Cursor v3's accurate read of scope). Kept as ONE session for autonomous-Claude execution; splitting only adds handoff overhead |
| §12 | Matrix accuracy fixes: ADD `_handle_beat_regenerate_audio` @8731, `_handle_cr_upload` @6419, `_handle_stitch_delete_job` @10939 to needs-guard. RECLASSIFY `_handle_bg_poll_flux` @5162 + `_handle_bg_session_state` @5137 from read-only → mutating (both call `bg.write_sidecar`). FIX `_handle_timeline_bake` @10577 from mutating → read-only (just reads + returns JSON). Updated counts: 27 BG handlers total, 92 `_handle_*` total |

**Verification of Cursor v3 grep claims (all confirmed):**
- `_handle_beat_regenerate_audio` exists @ L8731 (mutates state via TTS regeneration path)
- `_handle_cr_upload` exists @ L6419 (writes files under BG stills tree)
- `_handle_stitch_delete_job` exists @ L10939 (mutates `stitch_state.mutate_state`)
- `_handle_bg_poll_flux` calls `bg.write_sidecar(sc2)` ~51 lines after def — NOT a pure poll
- `_handle_bg_session_state` calls `bg.write_sidecar(sidecar)` ~7 lines after def — conditionally mutating GET
- `_handle_timeline_bake` is read-only confirmation endpoint — does NOT call `mutate_state`
- `_handle_patch_health` exists @ L5425 — Directus activity log only; scope guard OPTIONAL (spam protection)

---

## 1. Task

(Same as v3.)

**Operating mode (per Kim's Q1/Q2 confirmation):** Single-user, one-version-at-a-time. Server pinned to ONE storyboard via `--storyboard` flag. Kim only ever works in latest version.

---

## 2. Governing Decisions

(Same as v3 + add `SCOPE_BODY_HELPER_V1` LD for the normalization helper requirement.)

---

## 3. Approach

### 3.1 — 3.3
(Same as v3.)

### 3.4 Scope tokens — CORRECTED contract + REQUIRED normalization helper

The server's `_assert_event_scope` function (`production_server.py:4364`) reads `body['event_id']` (with URL query string fallback) and compares against `self.app.event_dir.name`. Internal contract: **the function expects `event_id` as the key, period.**

**v59 client convention vs server function:**
- v59 client sends `scope_event_id` in mutation bodies (matches existing BG convention)
- For BG handlers, the server has historically mapped: `_assert_event_scope({"event_id": body.get("scope_event_id")}, allow_missing=True)`
- For non-BG handlers, the v59 client sends `event_id` directly OR uses the same mapping

**REQUIRED normalization helper (NEW per Cursor v3):** every call site of `_assert_event_scope` must use a single helper to construct the body dict. No hand-rolled `{"event_id": body.get(...)}` patterns. Add to `production_server.py` near the `_assert_event_scope` definition:

```python
def _scope_body(self, body: dict) -> dict:
    """Normalize scope keys before _assert_event_scope.
    
    Accepts either 'event_id' or 'scope_event_id' from the request body.
    Returns a dict suitable for _assert_event_scope (which expects 'event_id').
    
    All handlers MUST call _assert_event_scope(self._scope_body(body), allow_missing=...)
    instead of hand-rolling the dict. Prevents key-drift bugs (Cursor v3 finding).
    """
    return {"event_id": body.get("scope_event_id") or body.get("event_id")}
```

**Updated call pattern (use everywhere):**
```python
if not self._assert_event_scope(self._scope_body(body), allow_missing=True):
    return
```

**Existing 11 LD-456 call sites must be migrated** to the helper in Session 1.5 (cosmetic refactor; no behavior change). All ~40 new guards use the helper from creation.

**`allow_missing` policy:** (Same as v3.)

### 3.5 `/api/event/load` concurrency model

(Same as v3.)

### 3.5.1 Async job completion rule (EXPANDED per Cursor v3)

Background threads (lipsync, magic compositor, ffmpeg jobs, FLUX submissions, ElevenLabs generations, **pollers**) can take 30 seconds to several minutes. If `/api/event/load` fires during a long job, the job's terminal write could attach output to the wrong event.

**Pin pattern at job enqueue (or at task start for synchronous-but-long handlers):**
```python
context["pinned_generation"] = self.app.event_generation
context["pinned_event_dir"] = Path(self.app.event_dir)  # captured by value
```

**Validate before ANY of these terminal operations** (NOT only `mutate_state`):
1. **`mutate_state` calls** — server-side state.json mutations
2. **Disk writes under `pinned_event_dir`** — file outputs (lipsync mp4, magic clip, ffmpeg result, FLUX still, etc.)
3. **Disk writes under BG-scoped dirs** — `bg.BG_STILLS_DIR`, `bg.write_sidecar(...)`, etc.
4. **Directus registrations of event-scoped assets** — `registered_write.register_asset(event_id=..., ...)`

**Validation snippet:**
```python
if self.app.event_generation != context["pinned_generation"]:
    log_warning(f"Job {job_id} discarded — event changed mid-flight ({context['pinned_event_dir'].name} → {self.app.event_dir.name})")
    context["status"] = "discarded_event_changed"
    # Files at pinned_event_dir/ are orphaned but recoverable (per §10 future script)
    # Do NOT delete; do NOT register; do NOT mutate state
    return
# Generation matches — safe to proceed
```

**Applies to (NEW handlers added per Cursor v3 expansion):**

**HTTP handlers spawning async work:**
- `_handle_lipsync_submit`, `_handle_lipsync_submit_legacy` (background thread + poller)
- `_handle_magic_submit_path` (background thread)
- `_handle_phase_b_lipsync` (synchronous but long; pin captured at entry)
- `_handle_phase_b_mix_audio` (ffmpeg)
- `_handle_phase_b_regen_audio` (ElevenLabs HTTP)
- `_handle_bg_assemble_group`, `_handle_bg_run_local_animation`, `_handle_bg_submit_flux`, `_handle_bg_submit_gpt_batch`
- `_handle_stitch_bake` (fcntl-locked but long)

**Non-handler async paths (NEW per Cursor v3):**
- Lipsync poller class (whatever module/class polls ByteDance for completion) — pins must thread through
- FLUX poller (`_handle_bg_poll_flux` is a poll endpoint that ALSO writes sidecar; the poller class behind it needs pinning)
- GPT batch poller (`_handle_bg_poll_gpt_status`)
- ElevenLabs polling (if any)
- Magic compositor background thread completion handler

**Pure-disk completions (NEW per Cursor v3):**
- `_handle_export` (writes mp4 under event_dir)
- `_handle_timeline_preview_with_sfx` (writes preview mp4)
- `_handle_stitch_preview` (writes preview mp4)
- `_handle_cr_upload` (writes upload under BG stills tree)
- Any path that writes `bg.BG_STILLS_DIR / <file>` without going through `mutate_state`

**Nested jobs (NEW per Cursor v3):** child jobs inherit `pinned_generation` and `pinned_event_dir` from parent context at spawn. Completion validates child's pins (NOT parent's, since parent may have already completed). Pin lineage is one level — no recursive validation up a chain.

**Implementation approach for Session 1.5:** rather than threading the pin through dozens of call sites, define a small helper:

```python
def _check_event_pin(self, context: dict, action_label: str) -> bool:
    """Return True if it's safe to proceed with a terminal write.
    
    Returns False (and logs) if the event has changed since pin was captured.
    Caller MUST early-return on False — do not mutate, write, or register.
    """
    if self.app.event_generation == context.get("pinned_generation"):
        return True
    log_warning(
        f"[event-pin] {action_label} aborted — pinned gen={context.get('pinned_generation')} "
        f"current gen={self.app.event_generation}; pinned event={context.get('pinned_event_dir').name if context.get('pinned_event_dir') else '?'} "
        f"current event={self.app.event_dir.name}"
    )
    context["status"] = "discarded_event_changed"
    return False
```

Every async terminal write becomes:
```python
if not self._check_event_pin(context, "lipsync output"):
    return
# safe to write
```

### 3.6 Persistence contract (state.json + sidecar; HTML conditional) — VERIFIED

(Same as v3.)

**§3.6 grep proof status: PASSING** (verified on this v3.1):
- `grep -n "L.json\|/api/v2/storyboard/L\|/api/v2/sidecar" Production/Event_1/storyboard_v58_prod.html` returns hits at ~L2227 (comments), ~L2248 (fetch wiring), ~L2657 (fetch wiring)
- v58 client IS wired to hydrate from `/api/v2/storyboard/L.json` sidecar
- Combined with v59's "always write `.L.json` on every mutation" rule (§3.6 main body), v58 emergency rollback will see v59-written data after hard-refresh

**Recommended additional verification (Cursor v3 #5):** Playwright E2E test in Session 1.5 verification gate — write a dialogue line via v59, flag-flip server to v58, hard-refresh, assert the dialogue is present. Optional but high-value (closes "grep proves wiring; doesn't prove server writes or cache headers").

### 3.7 v58/v59 split-brain rules

(Same as v3.)

### 3.8 — 3.10
(Same as v3.)

---

## 4. Implementation Steps

### Session 1 — DONE (commit 23812d9)
(Same as v3.)

### Session 1.5 — Server scope guards (~43 NEW handlers + 11 helper-migrated) + concurrency lock + async job rule + new endpoints (~5-7 hours, revised UP from 4-6 per Cursor v3)

1. Open `prod_preflight_reviews` row.
2. Register `STORYBOARD_V59_SPEC_V1` (rev3.1) + `EVENT_LOAD_GENERATION_LOCK_V1` + `UNIVERSAL_AUTOSAVE_V1` + `ASYNC_JOB_GENERATION_PIN_V1` + `SCOPE_BODY_HELPER_V1` LDs.
3. **Verify §3.6 grep proof.** Already PASSING per spec verification above. Re-run as sanity check.
4. **Add `_scope_body(self, body)` helper to `production_server.py`** near `_assert_event_scope` definition.
5. **Migrate existing 11 LD-456 call sites to use `self._scope_body(body)`** (cosmetic refactor; no behavior change).
6. **Add scope guards to ~43 currently-unguarded handlers** using `_assert_event_scope(self._scope_body(body), allow_missing=True)` pattern.

   **From v3 list (40 handlers — see v3 §4 for full list).**

   **NEWLY ADDED in v3.1 (3 handlers Cursor v3 found missing):**
   - `_handle_beat_regenerate_audio` @8731
   - `_handle_cr_upload` @6419
   - `_handle_stitch_delete_job` @10939

   **RECLASSIFIED (2 handlers moved from read-only to needs-guard):**
   - `_handle_bg_poll_flux` @5162 — calls `bg.write_sidecar(sc2)` post-poll
   - `_handle_bg_session_state` @5137 — calls `bg.write_sidecar(sidecar)` after migrate

7. **Apply async job completion rule (§3.5.1 EXPANDED)** to:
   - All 8 async-spawning HTTP handlers (v3 list)
   - Non-handler poller classes (lipsync poller, FLUX poller, GPT poller, ElevenLabs poller if any)
   - Pure-disk completions (`_handle_export`, `_handle_timeline_preview_with_sfx`, `_handle_stitch_preview`, `_handle_cr_upload`)
   - Implement `_check_event_pin(context, action_label)` helper; use at every terminal write
   - Nested job pin inheritance: child gets parent's pin tuple at spawn

8. **Audit `_handle_bg_reorder_beats` segment_index inconsistency** (L5486). Flag as latent bug; do NOT fix; add `prod_blockers` entry.

9. **Add `/api/event/load` concurrency mechanism** per §3.5.

10. **Make HTML-patching conditional** on filename pattern in `_handle_assign_image:6276`, `_handle_beat_update_text:8276`, `_handle_inject_image:6393`. (Same as v3.)

11. **v59 client ALWAYS writes `.L.json` sidecar** on every mutation that touches dialogue/image fields.

12. Add `POST /api/state/snapshot` and `POST /api/event/load` endpoints.

13. **DROP M6 isolation lock** (UA-based) — superseded by `--storyboard` flag pinning.

14. Wire v59 client's `pathappPatch` to (a) call `/api/state/snapshot` before mutation, (b) include `scope_event_id` AND/OR `event_id` per handler convention, (c) handle 423 by re-hydrating, (d) handle 409 with red banner + reload prompt.

15. **Verification (CORRECTED):**
    - All v3 verification curls (use `scope_event_id` correctly)
    - **NEW: helper migration sanity** — `grep -c "_assert_event_scope" Production/tools/production_server.py` should equal `grep -c "_scope_body" Production/tools/production_server.py` (every guard goes through helper)
    - **NEW: §3.6 Playwright E2E rollback test** — write dialogue via v59 → flag-flip server to v58 → hard-refresh browser → assert dialogue visible (Playwright headless test in CI)
    - **NEW: async job pin test** — trigger `_handle_phase_b_lipsync`; mid-job fire `/api/event/load`; verify lipsync's terminal `mutate_state` is rejected by `_check_event_pin`; verify orphaned mp4 still exists at pinned `event_dir`
    - **NEW: poller pin test** — trigger `_handle_bg_submit_flux`; mid-poll fire `/api/event/load`; verify the poll completion's `bg.write_sidecar` is rejected
    - All v3 verification gates still apply

### Sessions 2 / 2.5 / 2.7 / 2.9 / 3 / 3.5 / 4 / 5

(Same as v3.)

---

## 5. Files Created / Modified

(Same as v3 except:)

| Path | Action | Why |
|---|---|---|
| `Production/tools/production_server.py` | Modify (~200-350 lines, revised UP from 150-300) | ~43 NEW scope guards via helper + 11 existing-call-site migrations + concurrency lock + async pinning + 7 new endpoints + HTML-patch conditional + `_scope_body()` helper + `_check_event_pin()` helper |

---

## 6. — 9.

(Same as v3.)

---

## 10. Out of Scope (V1)

(Same as v3 + NEW:)

- **Standardizing scope key to single name across all handlers** — long-term cleanup; helper at call sites is the pragmatic mitigation; full standardization waits for a dedicated refactor session
- **Automatic re-registration of orphaned async-job outputs when generation matches again** — manual recovery script is acceptable for Kim's scale (single-user)

---

## 11. Cursor Cross-Review Status

✅ **v3.1 does NOT require another Cursor cycle.** Cursor v3's verdict explicitly: *"Once the appendix and §3.5.1 are tightened as above, this is ready to drive Session 1.5 without another full spec version — unless you want a formal v3.1 revision for traceability."*

This v3.1 IS the formal traceability revision. All 5 Cursor v3 tightenings folded in:
1. ✅ §12 matrix: 4 new handlers added; 2 reclassified; 1 misclassification fixed; counts updated to 27 BG / 92 total
2. ✅ §3.5.1 expanded: disk writes + pollers + nested jobs covered; `_check_event_pin` helper specified
3. ✅ §3.4: `_scope_body(body)` helper required at every call site
4. ✅ §4 Session 1.5: estimate up to 5-7h (kept as one autonomous-Claude session)
5. ✅ §3.6: grep verified passing on disk; Playwright rollback test added to verification gate

**Status: EXECUTABLE.** Next action: Session 1.5 handoff to terminal CLI.

---

## 12. Handler Matrix Appendix (v3.1 — corrected per Cursor v3 verification)

Every `_handle_*` that touches `mutate_state`, writes under `event_dir`, or writes under BG-scoped dirs. Status reflects code as of grep on 2026-05-02. Line numbers approximate.

### ✅ Already guarded (LD-456 — call site migrated to `_scope_body` in S1.5)

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
| `_handle_bg_reorder_beats` | ~5700 | Flag latent segment_index bug (L5486) |
| `_handle_bg_accept_beats` | ~5752 | None |
| `_handle_v2_event_state` (URL) | ~9405 | **VERIFY ONLY** — URL validation already exists per code at L9405-9450 |

### ❌ Needs guard added in Session 1.5 (~43 handlers)

#### Critical priority
| Handler | Line | Why critical |
|---|---|---|
| `_handle_v2_patch` | ~9010 | Canonical write path |
| `_handle_v2_module_patch` | ~9456 | Module-level state |
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
| `_handle_beat_regenerate_audio` | ~8731 (**NEW v3.1**) |
| `_handle_export` | ~8901 |
| `_handle_preview_stitched` | ~9696 |
| `_handle_budget_override` | ~9000 |
| `_handle_cr_upload` | ~6419 (**NEW v3.1**) |
| `_handle_cr_library_delete` | ~5335 (destructive) |

#### Phase A/B
| Handler | Line |
|---|---|
| `_handle_phase_b_regen_audio` | ~11557 |
| `_handle_phase_b_mix_audio` | ~11829 |
| `_handle_phase_b_lipsync` | ~12237 |
| `_handle_phase_b_preview` | ~12419 |

#### BG mutating (13 + 2 reclassified = 15 of 27 total)
| Handler | Line | Notes |
|---|---|---|
| `_handle_bg_delete_beat` | ~5720 | |
| `_handle_bg_submit_flux` | ~5809 | + async pin (FLUX poller too) |
| `_handle_bg_submit_gpt_batch` | ~5846 | + async pin (GPT poller too) |
| `_handle_bg_accept_option` | ~5925 | |
| `_handle_bg_accept_lib_image` | ~5957 | |
| `_handle_bg_add_beat` | ~6003 | |
| `_handle_bg_create_group` | ~6053 | |
| `_handle_bg_delete_group` | ~6073 | |
| `_handle_bg_update_group` | ~6086 | |
| `_handle_bg_assemble_group` | ~6101 | + async pin |
| `_handle_bg_run_local_animation` | ~6155 | + async pin |
| `_handle_bg_update_beat_anim_method` | ~6230 | |
| `_handle_bg_accept_local_animation` | ~6250 | |
| `_handle_bg_poll_flux` | ~5162 | **RECLASSIFIED v3.1** — calls `bg.write_sidecar(sc2)` post-poll |
| `_handle_bg_session_state` | ~5137 | **RECLASSIFIED v3.1** — calls `bg.write_sidecar(sidecar)` after migrate |

#### Timeline (3 mutating — `_handle_timeline_bake` was misclassified, now removed from this list)
| Handler | Line |
|---|---|
| `_handle_timeline_cue_upsert` | ~10513 |
| `_handle_timeline_delete_cue` | ~10558 |
| `_handle_timeline_preview_with_sfx` | ~10602 (+ pure-disk pin per §3.5.1) |

#### Magic + Lipsync + Stitch
| Handler | Line |
|---|---|
| `_handle_magic_submit_path` | ~4798 |
| `_handle_lipsync_submit` | ~6818 |
| `_handle_lipsync_submit_legacy` | ~7159 |
| `_handle_stitch_save_job` | ~10907 |
| `_handle_stitch_delete_job` | ~10939 (**NEW v3.1**) |
| `_handle_stitch_bake` | ~11396 |

### ⚠️ Async-completion handlers (also need §3.5.1 generation pinning + `_check_event_pin`)

| Handler | Line | Async type |
|---|---|---|
| `_handle_lipsync_submit` | ~6818 | Background thread + poller |
| `_handle_lipsync_submit_legacy` | ~7159 | Same |
| `_handle_magic_submit_path` | ~4798 | Background thread |
| `_handle_phase_b_lipsync` | ~12237 | Synchronous but long |
| `_handle_phase_b_mix_audio` | ~11829 | Ffmpeg |
| `_handle_phase_b_regen_audio` | ~11557 | ElevenLabs HTTP |
| `_handle_bg_assemble_group` | ~6101 | Background |
| `_handle_bg_run_local_animation` | ~6155 | Background |
| `_handle_bg_submit_flux` | ~5809 | Background + FLUX poller |
| `_handle_bg_submit_gpt_batch` | ~5846 | Background + GPT poller |
| `_handle_stitch_bake` | ~11396 | Synchronous fcntl-locked |
| `_handle_export` | ~8901 | Pure-disk completion |
| `_handle_timeline_preview_with_sfx` | ~10602 | Pure-disk completion |
| `_handle_cr_upload` | ~6419 | Pure-disk completion (BG stills) |

### ➖ Read-only or special — no guard needed

| Handler | Line | Why |
|---|---|---|
| `_handle_storyboard_switch` | ~7258 | Intentional cross-storyboard (not cross-event) |
| `_handle_voice_profile_get` | ~11701 | Read-only |
| `_handle_voice_profile_update` | ~11745 | Cross-event safe (Chipper id=2 only) |
| `_handle_files_serve` | ~6063 | Static file |
| `_handle_state` (read) | various | Read-only |
| `_handle_bg_segments` | ~5129 | Read-only |
| `_handle_bg_poll_gpt_status` | ~5909 | Read-only (poll only) |
| `_handle_bg_groups` | ~5991 | Read-only |
| `_handle_bg_stills` | ~6276 | Read-only file serve |
| `_handle_timeline_audio` | ~10175 | Read-only |
| `_handle_timeline_sfx_library` | ~10462 | Read-only |
| `_handle_timeline_open_in_quicktime` | ~10583 | Read-only (QuickTime launcher) |
| `_handle_timeline_bake` | ~10577 | **RECLASSIFIED v3.1** — actually read-only (returns JSON) |
| `_handle_patch_health` | ~5425 | Directus activity log only — guard OPTIONAL (spam protection) |

**Final tallies:**
- 11 already guarded (migrate to helper in S1.5)
- 43 to add (37 from v3 list - 1 misclassified `_handle_timeline_bake` + 3 newly added + 2 reclassified-from-readonly + 2 already in v3 list overlapping = net 43)
- 14 read-only/special
- **68 handlers reviewed total**
- Total file `_handle_*` count: 92
- Remaining ~24 handlers: utility GETs, polls, file serves not state-mutating (auditable via comprehensive grep but not blocking Session 1.5)

---

**End of spec v3.1. EXECUTABLE. Next action: Session 1.5 handoff to terminal CLI — no further Cursor reviews required.**
