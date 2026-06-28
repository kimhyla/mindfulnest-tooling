# Tech Spec — Omni/Stitch Runtime Cleanup v2

**Date:** 2026-06-26  
**Branch:** `fix/build-sha-drift-banner`  
**Depends on:** v1 shipped in `009ef9f` (legacy stitch purge + partial stale-bundle toast sweep)

---

## Scope (dependency order)

| # | Category | Fix |
|---|----------|-----|
| 1 | Migrate heal order | Run `_migrate_skip_beat_canonical` **before** `heal_avatar_pro_poisoned_o3_prompt` in `_migrate_sidecar` |
| 2 | Stale-bundle toast sweep | Route remaining BG + Storyboard mutation errors through `formatMutationError`; skip toast when empty |
| 3 | Session GET job truth | Remove `reconcile_stuck_o3_voice_beats` sidecar lock from session GET; clear terminal pointers in-memory in `_enrich_beats_job_busy` |
| 4 | Full QA | pytest → deploy → API → browser on `:5112` → commit |

**Out of scope:** Avatar Pro reinstatement; Phase B Avatar; full session GET architecture rewrite.

---

## 1 — Migrate heal order

### Root cause

`_migrate_sidecar` calls `heal_avatar_pro_poisoned_o3_prompt` before `_migrate_skip_beat_canonical`. Operator-owned beats (`o3_prompt_box_law`, stored Kling prompt, active O3 job) can be rewritten during migrate even though later canonical heals are skipped.

### Category fix

Swap order in both beat loops (humanize + reference align). Add contract test: box-law beat with poison marker must not be healed during migrate.

---

## 2 — Stale-bundle toast sweep

### Remaining raw paths

**BgTab:** `bg-accept-all-error` (~2724)  
**StoryboardTab:** `beat-*-error`, Regen Audio, Animate, sb-delete, sb-add (+ speaker/parenthetical/kim-done/image-assign for parity)

### Category fix

Import `formatMutationError`; wrap every `pathappPatch` failure toast; `if (msg) pushToast(...)`.

### Tests

Extend `test_build_sha_drift_banner.py` grep gates for accept-all + Storyboard sources.

---

## 3 — Session GET job truth + slowness

### Root cause

Session GET holds sidecar lock via `mutate_sidecar_locked(reconcile_stuck_o3_voice_beats)` on every poll — contradicts `test_o3_session_tier_architecture` and slows GET under Dropbox sync.

Stale `o3_current_job_id` on beats when terminal is `done`/`failed` makes `job_busy` false in contract but UI still shows pointer until sidecar persist.

### Category fix

1. **Remove** stuck reconcile persist from session GET (startup / force_reconcile / poll paths retain heal).
2. In `_enrich_beats_job_busy`, call `clear_o3_pointer_if_terminal(beat, ev)` in-memory per event dir **before** `_resolve_beat_job_busy_for_session` — response reflects terminal truth without sidecar write.

---

## Proof gates

- `pytest` relevant suites green
- `verify_beatgen_deploy_smoke.sh 5112` OK
- Session GET: no `mutate_sidecar_locked` + `reconcile_stuck` in handler
- Stale tab: banner only, no misleading action toast
- build-sha = commit HEAD on `:5112`
