# TECH_SPEC — Cross-Pipeline G1–G8 Category Closure v1.1

**Status:** v1.1 — 4-agent debate consensus (2026-07-01); approved for implementation  
**Reviews:** Adversary [c1592b72] · QA/Durability [49a6426e] · Architecture [97a3c576] · E2E [eba024d2] — all **APPROVE WITH CONDITIONS** (incorporated below)  
**Marker:** `CROSS_PIPELINE_G1_G8_CLOSURE_V1`  
**Branch:** `feat/cross-pipeline-g1-g8-closure` from tooling HEAD  
**Parent:** `OPERATOR_UX_SYMPTOM_MATRIX_v1.md` G1–G8 · `FAST_AND_FLAWLESS_DONE_v1.md` FF-028..FF-035  
**Excludes:** `CROP_SAVE_LIBRARY_VISIBILITY_V1` (commit `d9515d3`) — do not re-litigate  

**Hermetic acceptance:** `Event_e2e_fixture` via Playwright webServer **`:5200`**  
**Live acceptance:** Event_4 **`:5114`** — deploy smoke + multipass curl only  

---

## 0. Verified debt (code-audited 2026-07-01)

- Session GET: `compose_session_terminal_view` + `_enrich_beats_job_busy` — **not** unified with `resolve_beat_o3_truth`
- Poll persists truth; session GET is read-only in-memory compose (correct tier — **do not add sidecar writes on GET**)
- `verify_o3_job_truth_durability.sh` voice_fix grep is **warn-only** — must become fail-closed
- G1 e2e: `test.skip` without env; five other G e2e files **absent**
- G8 client: **no** `bg_o3_export_lineage_sig` in `stitchJobMediaHydrate.ts`
- G7 upload: **no** `invalidateLibrarySessionCache` on success
- Matrix G1–G8 marked `shipped` **prematurely** — revert to `in_progress` until Phase 7
- FF-028..035 **not** in `verify_fast_and_flawless_done.sh` pass 3

---

## 1. Category-unlocker

| Item | Value |
|------|-------|
| **Bug category** | Terminal / disk / sidecar / UI disagree after mutations |
| **Category fix** | One read resolver per domain; heal on terminal failed; fail-closed gates |
| **Operator acceptance (Event_4 :5114)** | Generate→fail→prior clip restored · Trim→stitch preview changes |

---

## 2. Execution order

```
Phase 0 — v1.1 spec + matrix in_progress + branch
Phase 1 — G3 truth stack (unblocks G1/G2 reads)
Phase 2 — G1 + G2
Phase 3 — G4
Phase 4 — G5 + G6
Phase 5 — G7
Phase 6 — G8 client lineage + e2e
Phase 7 — FA&F wiring + matrix shipped + meta exit 0
```

**Each phase:** implement → pytest → durability → deploy Event_4 → **build-sha equality assert** → live curl → playwright (if applicable) → **multipass 2×** → commit.

---

## 3. Read vs write split (G3 — binding architecture)

| Lane | Behavior |
|------|----------|
| **Session GET (read)** | `compose_session_terminal_view` → **`resolve_beat_o3_truth(..., orphan_preview=True)`** in-memory merge into beat; `_enrich_beats_job_busy(session_read_only=True)` sets **`job_busy` / `o3_current_job_id` only** — no `observe_and_close_stale`, no `clear_o3_pointer`, no sidecar persist |
| **Poll GET (read + write)** | `_enriched_beat_snapshot_for_o3_poll` → truth → `mutate_sidecar_locked` on delta |
| **Explicit heal (write)** | `close_o3_attempt`, `restore_last_good_*`, startup/shutdown reconcile, `force_reconcile_o3=1`, `_apply_o3_session_terminal_reconcile` |

**Forbidden:** merge full `reconciled_beat` inside `_enrich_beats_job_busy` (breaks `test_o3_session_disk_parity.py` derived-fields contract).  
**Forbidden:** direct `kling_o3_status = approved` outside `kling_stitch_readiness`.

---

## 4. Per-gap authority contracts

### G3 — O3_JOB_TRUTH_STACK_V1 (Phase 1)

| | |
|--|--|
| **Authority module** | `o3_job_truth.py` → `resolve_beat_o3_truth` |
| **Read priority** | terminal JSON > disk > sidecar > UI latch |
| **Registry** | Add `o3_job_truth_stack`; delegate `o3_job_busy` read to `truth["operator_busy"]` |

**Deliverables:**
1. `compose_session_terminal_view` delegates to truth resolver (retire parallel `reconcile_beat_terminal_disk` loop)
2. `_enrich_beats_job_busy` read-only path: busy fields only
3. `test_o3_job_truth_matrix.py` — 12 parametrized cases; ≥4 without mocking `beat_o3_operator_busy`
4. `o3_job_truth_read_allowlist.txt` + fail-closed ripgrep in durability script
5. Live curl: session GET == poll for beat 15 failed-redo class

**Regression pytest (every Phase 1 commit):**
`test_bg_session_fast_get.py`, `test_milestone_o3_job_busy.py`, `test_o3_session_disk_parity.py`, `test_o3_session_tier_architecture.py`

---

### G1 — O3_FAILED_REDO_HEAL_V1 (Phase 2)

| | |
|--|--|
| **Write/heal** | `restore_last_good_o3_delivery_after_failed_attempt` via truth stack (no duplicate heal) |
| **E2e** | `o3_failed_redo_restores_prior_clip.spec.ts` — **fixture :5200**, seed in `beforeAll`, **no test.skip** |
| **Assert** | session GET + poll + approved + video_path (not poll-only) |
| **Marker** | `O3-FAILED-REDO-1` |

---

### G2 — O3_SUBPROCESS_LIFECYCLE_V1 (Phase 2)

| | |
|--|--|
| **Write** | `finalize_live_o3_jobs_before_shutdown` → terminal `cancelled`; startup reconcile → `failed` + G1 heal |
| **UI** | `BgPollCoordinator`: recoverable toast when `video_path_exists`; error when must-regenerate |
| **E2e** | `o3_restart_survival.spec.ts` — health poll after restart; **serial**; respect 30s throttle |
| **Pytest** | `test_o3_subprocess_lifecycle.py` (required — grep-only insufficient) |
| **Marker** | `O3-RESTART-SURVIVAL-1` |
| **Rule** | Drain via `/api/admin/drain_start` before intentional restart mid-job |

---

### G4 — SIDECAR_SQLITE_AUTHORITY_V1 (Phase 3)

| | |
|--|--|
| **Authority** | extend `sqlite_sidecar_authority` — `beatgen_store` + `mutate_sidecar_locked` only |
| **Stress** | `test_sidecar_concurrent_stress.py` (temp SQLite only, never Event_4 live) |
| **Lock** | Document poll default `lock_timeout_s=5.0` — do **not** reduce to 500ms without evidence |
| **E2e** | none (pytest + grep) |

---

### G5 — LIBRARY_SCOPE_ROOT_PARITY_V1 (Phase 4)

| | |
|--|--|
| **Authority** | `cropper._resolve_cr_library_scope` → `ctx.library_event_dir` |
| **Pytest** | `test_cr_library_milestone_scope_parity.py` (primary proof) |
| **E2e** | `library_scope_parity.spec.ts` — scope keys on mutations (thin) |
| **Marker** | `LIBRARY-SCOPE-PARITY-1` |

---

### G6 — DIRECTUS_HAS_CROP_DISK_FALLBACK_V1 (Phase 4)

| | |
|--|--|
| **Authority** | `_enrich_has_crop_from_disk` after Directus (10s budget) |
| **E2e** | `directus_has_crop_disk_fallback.spec.ts` — disk seed + `has_crop_source: disk_stem_match` |
| **Marker** | `DIRECTUS-HAS-CROP-1` |

---

### G7 — LIBRARY_CLIENT_CACHE_COHERENCE_V1 (Phase 5)

| | |
|--|--|
| **Authority** | `libraryCachePolicy.ts` |
| **Wire** | crop + **upload** + delete → invalidate + optimistic merge |
| **Gate** | grep upload handler for `invalidateLibrarySessionCache` |
| **E2e** | `library_cache_coherence.spec.ts` — count changes without hard refresh |
| **Marker** | `LIBRARY-CACHE-COHERENCE-1` |

---

### G8 — BG_O3_STITCH_EXPORT_LINEAGE_V1 (Phase 6)

| | |
|--|--|
| **Server** | `bg_o3_stitch_invalidation.py` (exists) |
| **Client** | `stitchJobMediaHydrate.ts` — `BG_O3_EXPORT_LINEAGE_HYDRATE_V1` marker |
| **Gate** | new `verify_bg_o3_stitch_lineage_client_durability.sh` (not trim-only FF-019) |
| **E2e** | `trim_then_export_shows_new_clip.spec.ts` — lineage sig / preview URL change |
| **Marker** | `TRIM-EXPORT-LINEAGE-1` |

---

## 5. FA&F closure (Phase 7)

1. New **`verify_cross_pipeline_g1_g8_closure_durability.sh`** (meta — mirrors operator-export closure)
2. **Pass 3:** explicit FF-028..035 scripts
3. **Pass 2b:** fail if G1–G8 matrix `partial|spec-only|in_progress` (Phase 7 only)
4. **Pass 4:** add markers O3-FAILED-REDO-1, O3-RESTART-SURVIVAL-1, LIBRARY-SCOPE-PARITY-1, DIRECTUS-HAS-CROP-1, LIBRARY-CACHE-COHERENCE-1, TRIM-EXPORT-LINEAGE-1
5. **Pass 6b:** run six cross-pipeline e2e files; **fail on any test.skip**
6. **Pass 9:** `MN_FAF_REQUIRE_LIVE=1` on Phase 7 — fail if :5114 down or build-sha mismatch
7. **Phase 7 commit:** matrix G1–G8 → `shipped`; **`MN_ALLOW_DIRTY_DEPLOY` forbidden**

---

## 6. Multipass template (fail-closed)

```bash
HEAD=$(git rev-parse --short HEAD)
MN_ALLOW_DIRTY_DEPLOY=1 bash Production/scripts/deploy_storyboard_v59.sh --event Event_4
SERVED=$(curl -sf http://localhost:5114/ | sed -n 's/.*name="build-sha" content="\([^"]*\)".*/\1/p')
test "$SERVED" = "$HEAD" || exit 1
curl -sf http://localhost:5114/api/event/current | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('event_id')=='Event_4'"
# Phase-specific curl + playwright
# Repeat entire block 2× without code changes
```

---

## 7. Blast radius

| Risk | Mitigation |
|------|------------|
| Dual O3 reconcile | Single resolver; compose delegates; enrich busy-only on GET |
| FA&F false green | pass 6b + fail-closed grep; no warn-only gates |
| Restart e2e kills webServer | fixture :5200 + health poll + serial |
| G8 client stale preview | separate client lineage gate |
| Perf | batch sidecar read; no persist on GET |
| Regression | `test_bg_session_fast_get` + `test_milestone_o3_job_busy` every phase |

---

## 8. Registry additions (Phase 1 + 7)

Add to `authority_registry.py`: `o3_job_truth_stack`, `o3_failed_redo_heal`, `o3_subprocess_lifecycle`, `cr_library_milestone_scope`, `directus_has_crop_disk_fallback`, `library_client_cache_coherence`, `bg_o3_stitch_export_lineage`.

---

## 9. Rollback

- Matrix stays `in_progress` until Phase 7 single commit
- Phase N e2e fail after deploy → revert phase commit; re-multipass prior phase
- Do not mark shipped without pass 6b green

---

## 10. Implementation checklist

- [x] Phase 0: 4-agent debate → v1.1
- [ ] Phase 1: G3 compose→truth + 12-test matrix + fail-closed grep
- [ ] Phase 2: G1 e2e unskipped + G2 toast + restart e2e + pytest
- [ ] Phase 3: G4 concurrent stress
- [ ] Phase 4: G5 pytest + G6 e2e
- [ ] Phase 5: G7 upload wiring + e2e
- [ ] Phase 6: G8 client hydrate + e2e
- [ ] Phase 7: FA&F + matrix shipped + exit 0
