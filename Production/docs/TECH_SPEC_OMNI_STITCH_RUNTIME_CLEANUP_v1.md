# Tech Spec — Omni/Stitch Runtime Cleanup v1

**Date:** 2026-06-26  
**Branch:** `fix/build-sha-drift-banner`  
**Goal:** Close four remaining gap classes (legacy stitch naming, stale-bundle toast siblings, sidecar runtime audit, browser proof) without re-litigating shipped Omni/Stitch code.

---

## Scope

| Step | Type | What |
|------|------|------|
| 1 | **Code (category)** | Purge legacy milestone stitch jobs from global `stitch_editor_state.json`; reject wrong-name `load_job` before 4-slot event hydrate |
| 2 | **Code (category)** | Route all BG mutation error toasts through `formatMutationError` (returns empty on `CLIENT_BUNDLE_STALE`) |
| 3 | **Runtime (data)** | Audit milestone sidecar prompts + busy fields; heal only when dry-run proves pollution |
| 4 | **Operator + browser** | Hard refresh; milestone Stitcher + BG smoke on `:5112` |

**Out of scope:** Reinstating Avatar Pro on Beat Gen (blocked by `67c5bdc` + launchd); Phase B Avatar Pro; session GET performance refactor.

---

## Step 1 — Legacy stitch job purge

### Reproduce (mandatory before edit)

```bash
# Global state contains wrong-name job (disk)
python3 -c "import json; d=json.load(open('.../Production/tools/stitch_editor_state.json')); print(d['jobs']['milestone1_arc1_stitch']['slots'].keys())"
# → intro, phase_a, phase_b, resolution

curl -s http://localhost:5112/api/stitch_editor/job/milestone1_arc1_stitch | jq '.job.slots | keys'
# → ["intro","phase_a","phase_b","resolution"]

curl -s http://localhost:5112/api/stitch_editor/job/milestone_milestone1_arc1_stitch | jq '.job.slots | keys'
# → ["standalone"]
```

### Root cause

Naming evolved to `milestone_{id}_stitch` + milestone-local `stitch_state.json`. Legacy `{id}_stitch` (e.g. `milestone1_arc1_stitch`) persisted in **global** store. `is_milestone_stitch_job_name()` returns false → `handle_stitch_load_job` treats it as event job → `hydrate_stitch_canonical_slots_from_disk` fills 4 event slots.

### Category fix

1. `legacy_milestone_id_from_stitch_job_name(name)` — detect `{milestoneId}_stitch` where `milestoneId` is not `Event_N`.
2. `purge_legacy_milestone_stitch_jobs_from_global(h)` — remove all legacy keys from global store (idempotent).
3. `handle_stitch_load_job` — if legacy name: purge global copy; return **409** `LEGACY_STITCH_JOB_NAME` with hint `milestone_{id}_stitch` (never event hydrate).
4. Call global purge once per load of any canonical milestone job (belt-and-suspenders).

### Blast radius

| Surface | Risk | Mitigation |
|---------|------|------------|
| Event jobs `Event_N_stitch` | Must not purge | Explicit exclude `^Event_\d+_stitch$` |
| Canonical `milestone_{id}_stitch` | Must not reject | `is_milestone_stitch_job_name` unchanged |
| Milestone disk store | Separate file | Unaffected |
| UI | Uses `stitchJobNameForScope` | Already correct |

### Tests

Extend `test_milestone_stitch_job_isolation.py`: legacy name detection; normalize still strips event slots.

### Proof after deploy

- Global JSON: no `milestone1_arc1_stitch` key
- Wrong-name API → 409 + hint
- Correct-name API → standalone + mux
- Browser Stitcher tab → Standalone slot

---

## Step 2 — Stale-bundle toast siblings

### Reproduce

Stale tab (`build-sha` old): mutation returns `CLIENT_BUNDLE_STALE` before HTTP. Handlers that toast raw `result.error`:

- `bg-delete-error` (~1311)
- `bg-submit-error` (~1975)
- `bg-still-clip-error` (~1758)
- `bg-set-context` (~1011)

Ref-drop fixed in `3e63eb6`; save uses `formatMutationError` + stale guard.

### Category fix

Use `formatMutationError(result, label)` for all four; skip toast when message is empty (stale → banner only).

### Blast radius

Only changes error **surfacing** when bundle stale; no mutation or server change.

### Tests

Extend `test_build_sha_drift_banner.py` grep gates for delete/submit/still-clip/set-context blocks.

---

## Step 3 — Runtime sidecar audit (not new code)

### Prompt audit

Scan `Milestones/milestone1_arc1/beat_generator_sidecar.json` speak beats for:

- Positive Avatar poison markers (`TRIPOD LOCK`, `kling_o3_avatar_pro`, etc.)
- Unexpected `avatar_pro` mode fields

Compare newest `*.bak_omni_*` backup if rewrite suspected. **Do not auto-rewrite** unless poison markers found on beats that should be Omni.

### Busy-field audit

```bash
python3 Production/scripts/heal_milestone_speak_beats_omni.py --dry-run
```

If `busy_fields_cleared > 0`: run heal once (after audit logged). Kim is not using Beat Gen Avatar — re-pollution risk is low if `MN_BEATGEN_AVATAR_DISABLED=1` stays pinned.

### Avatar on Beat Gen

**Not forbidden by sidecar** — blocked by code + launchd. Sidecar pollution was from **interrupted Avatar/O3 jobs writing ephemeral fields to durable JSON**, not from “Avatar exists in codebase.” With Avatar disabled on Beat Gen, re-pollution requires bypassing guards.

---

## Step 4 — Browser proof

**URL:** `http://localhost:5112/?video=intro&milestone=milestone1_arc1`

Checklist:

- Header `build-sha` = git HEAD
- Beat Gen: ≥11 beats, no disk I/O error
- Stitcher: Standalone slot, unified playback marker
- Hard refresh repeat
- Dedicated port 409 on wrong event/load

---

## Deploy / durability

1. Mirror tooling → Dropbox (`verify_tooling_dropbox_parity.py` exit 0)
2. `deploy_storyboard_v59.sh --event Event_2` or restart API
3. `verify_beatgen_deploy_smoke.sh 5112`
4. `verify_stitcher_lockin_20260528.py`

---

## Commit

Single commit on `fix/build-sha-drift-banner` with steps 1–2 code + tests; steps 3–4 evidence in QA report.
