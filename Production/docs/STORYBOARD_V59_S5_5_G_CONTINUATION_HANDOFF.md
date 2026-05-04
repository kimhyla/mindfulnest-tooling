# Storyboard v59 — S5.5g Continuation Handoff (Phase B-I)

**Date:** 2026-05-04
**Branch:** `claude/s5_5g` — Phase A committed; Phase B-I pending fresh session
**Phase A audit:** `Production/docs/STORYBOARD_V59_S5_5_G_PHASE_A_AUDIT.md` — **READ THIS FIRST**
**Spec:** `Production/docs/STORYBOARD_V59_S5_5_G_SPEC_v1.md`
**Master overview:** `Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md`
**Predecessor session handoff:** `Production/docs/STORYBOARD_V59_S5_5_F_CONTINUATION_HANDOFF.md`

---

## §1 What Phase A delivered (this session)

1. ✅ Local main pulled to `1b40d1b` (Wave 1 merged into origin/main)
2. ✅ Branch `claude/s5_5g` created from main; `1b40d1b` confirmed in HEAD
3. ✅ CI on main is green (last 4 runs)
4. ✅ MUTATION_CHANNEL_INVARIANT_V1 grep gate is green (G13 PASS)
5. ✅ /stitch_editor job JSON shape audited — full server contract documented
6. ✅ Transition defaults audited — fade_ms=500 confirmed; dissolve confirmed as NEW work
7. ✅ Per-slot trim backend pattern **decided and locked** — extend `stitch_save_job` body with `trim_in_ms`/`trim_out_ms`
8. ✅ Production Map multi-event bug located at `server.py:8537-8544`
9. ✅ Wave 1 raw-fetch migration verified — StitcherTab is 100% pathappPatch-clean
10. ✅ prod_preflight_reviews row written: id=205, task_id=`s5_5g-stitcher-parity-final-20260504`, approved_to_proceed=true
11. ✅ Phase A audit doc + this handoff doc + preflight script committed

**No implementation code in Phase A.** No new tests. No new components. No PR. By design.

---

## §2 Pre-conditions verified — what the next session can rely on

| Pre-condition | State |
|---|---|
| Branch exists | `claude/s5_5g` local + (after Phase A push) `origin/claude/s5_5g` |
| Cut from | `main@1b40d1b` (Wave 1 merge — see git log) |
| Source paths | All under `Production/tools/storyboard-v2/` (use `cd Production/tools/storyboard-v2` for npm/playwright commands; bare `src/...` paths inside spec body refer here) |
| `production_server.py` location | `Production/tools/production_server.py` (16,639 lines) — NOT at repo root |
| Fixture | `Production/Event_e2e_fixture/` — usable; **immutable for Event_1 / Event_2 per spec §7**; **add `Event_e2e_fixture_2/` or stubs allowed for Phase E §3.6 testing** |
| Preflight row | id=205 in Directus prod_preflight_reviews — link Phase B-I activity_log rows to it via `details.task_id` (LD-262 audit-trail FK convention) |
| Untracked working-tree files | `.claude/` (IDE state) + `Production/Event_e2e_fixture/storyboard_v59_prod.L.json` (sidecar test side-effect from Wave 1 AF.3.1). Confirmed by Kim as out-of-scope. **Do not commit; do not delete.** |

---

## §3 Decisions locked in Phase A — do not re-litigate

### §3.1 Stitcher job JSON wire format — snake_case throughout

Full schema in audit doc §3. Key invariants:

- Slot fields: `video_path`, `video_dur_ms`, `ambient_bed_path`, `ambient_vol`, `sfx_cues[]`
- SFX cue fields: `id`, `source_path`, `name`, `offset_ms`, `volume`, `fadein_ms`, `fadeout_ms`
- Transition fields: `after_slot`, `source_path`, `audio_name`, `fade_ms`
- v59 client constructs snake_case directly in PathappPatch body — no camelCase conversion layer

### §3.2 Per-slot trim backend — extend stitch_save_job (NOT new endpoint)

- New slot fields: `trim_in_ms` (default 0) and `trim_out_ms` (null = end of clip)
- Pipeline extension goes in `_stitch_normalize_slot` (called from `_stitch_build_pipeline:14908`)
- Cache key MUST include trim fingerprint or LRU collisions
- See audit doc §5 for full implementation sketch

### §3.3 Transition kinds — explicit `kind` field + dual audio behavior (Kim Q1+Q3 LOCKED 2026-05-04)

**Transition shape:**
```json
{
  "kind": "crossfade" | "cut" | "dissolve",
  "fade_ms": 500,           // visual fadeblack duration (used by dissolve; ignored by cut)
  "audio_xfade_ms": 500,    // 0 = visual only, non-zero = audio crossfade duration
  "source_path": "..."      // optional crossfade audio cue path (existing field)
}
```

- Add `kind: "crossfade" | "cut" | "dissolve"` on transition shape (Q3 — explicit field; NOT inferred from source_path emptiness)
- Server defaults `kind="crossfade"` when absent (backward compat)
- Server defaults `audio_xfade_ms = fade_ms` when absent (audio matches visual unless explicitly overridden)
- `cut` — pipeline skips transition synthesis (existing path: empty `source_path` already skipped at server.py:14927); `fade_ms` and `audio_xfade_ms` ignored
- `crossfade` — existing `trans_<after_slot>` SFX cue synthesis path (server.py:14920-14938); `audio_xfade_ms` controls the SFX fade duration
- **`dissolve` — NEW** (Q1 LOCKED — supports BOTH visual-only AND visual+audio):
  - Apply video fadeblack at boundary via ffmpeg fade filters; reference LD-376 (Phase A fadeblack pattern)
  - If `audio_xfade_ms > 0`: ALSO crossfade audio across the boundary at the specified duration (visual + audio dissolve)
  - If `audio_xfade_ms == 0`: pure visual fadeblack with hard audio cut
  - Default: `audio_xfade_ms = fade_ms` (audio matches visual)
  - Server cost: ~5-10 LOC at server.py:14920-14938 (transition synthesis branch on `kind`); UI cost: 1 numeric field or "Audio dissolve" checkbox in CuePopover

### §3.4 Production Map fix — convention-based m_number → Event_<N>

```python
candidate = production_root / f"Event_{m_num}"
edir = candidate if (candidate.is_dir() and m_num) else None
```

No Directus schema migration. See audit doc §6.

### §3.5 Phase F is verification only

§19.10 amendment supersedes original Phase F1-F3. Wave 1 already migrated StitcherTab. ProductionMapTab.tsx:128 event_load is sanctioned by grep-gate allowlist — out of scope. Phase F = G14 grep-gate run + verification table; do **not** edit StitcherTab raw-fetch code.

### §3.6 Spec line-number drift

Use the table in audit doc §2 for current `production_server.py` line numbers — spec's numbers are stale.

### §3.7 Preflight schema — drop 4 fields

`prod_preflight_reviews` does NOT accept: `classification`, `advocates_count`, `counters_count`, `date_reviewed`. Use `task_type` for classification. See audit doc §8.

---

## §4 Phase B-I work remaining

### Phase B — Per-slot SFX cue placement + G3-G6 (TDD red→green)

| Gate | Spec §19.2.1 | Description |
|---|---|---|
| G3 | RED | New e2e in `e2e/s5_5g_smoke.spec.ts` — drag SFX from LibraryPanel onto slot waveform → cue appears with offset_ms = drop x-position × slot_duration |
| G4 | GREEN | StitcherTab extended: per-slot `WaveformTimeline` reused from S5.5f; drop handler computes offset; POST `pathappPatch('stitch_save_job', {…, slots: [...with sfx_cues...]})` |
| G5 | GREEN | CuePopover (reuse from S5.5f) opens on cue marker click; volume / fadein_ms / fadeout_ms / Delete |
| G6 | GREEN | Module-level cue drop on timeline below slots → POST `/api/timeline/cues` (separate state from job) |

**Files to touch:**
- `src/components/StitcherTab.tsx` (extend from current 310 lines)
- `e2e/s5_5g_smoke.spec.ts` (new spec — pattern from `e2e/s5_5f_smoke.spec.ts`)
- `src/api/endpoints.ts` — add `timeline_cue_upsert: '/api/timeline/cues'` to MUTATION_ENDPOINTS

**Components to reuse (DO NOT re-implement):**
- `src/components/phase/WaveformTimeline.tsx` (S5.5f) — full-featured waveform with cue markers
- `src/components/phase/CuePopover.tsx` (S5.5f) — cue editor popover
- `src/components/LibraryPanel.tsx` — SFX tier exists per S5.5f tier filter
- `pathappPatch` from `src/api/client.ts`

### Phase C — Per-boundary transitions + G7-G8

| Gate | Description |
|---|---|
| G7 | Transition selector renders between adjacent slot pairs; selecting "crossfade" / "cut" / "dissolve" updates job.transitions[].kind |
| G8 | Bake honors transition kind: crossfade & cut work via existing pipeline; dissolve adds fadeblack via NEW pipeline branch |

**Server-side new work:** add `kind` recognition in `_stitch_build_pipeline:14920-14938`; for `kind="dissolve"`, apply ffmpeg `fade=t=out:st=…:d=fade_ms/1000` to slot[after_slot] tail and `fade=t=in:st=0:d=fade_ms/1000` to slot[after_slot+1] head BEFORE concat. Reference LD-376 for Phase A fadeblack reference implementation.

**Open question for Kim:** is `dissolve` audio-aware (i.e., still a crossfade audio cue + visual fadeblack) OR pure visual fadeblack (no audio xfade)? Spec §3.3 is ambiguous. **Default assumption: visual fadeblack + crossfade audio (treats source_path the same as crossfade).** Surface to Kim before Phase C green.

### Phase D — Per-slot trims + G9-G10

| Gate | Description |
|---|---|
| G9 | Trim handles render on slot scrubber; drag updates trim_in_ms / trim_out_ms; pathappPatch saves to job |
| G10 | Bake honors trim — pipeline outputs only [trim_in_ms, trim_out_ms] window of source mp4 |

**Server-side new work:** extend `_stitch_normalize_slot` per audit doc §5 (ffmpeg `-ss`/`-to` pre-trim, cache-key bumped).

### Phase E — Production Map fixes + G12-G13

| Gate | Description |
|---|---|
| G12 | Per-row `event_dir` differs across modules in fixture (requires 2-event fixture additions) |
| G13 | Cell click loads correct event_dir via existing event_load flow |

**Server-side fix:** server.py:8537-8544 per audit doc §6.

### Phase F — Verification only (G14)

Run grep gate. Confirm green. Add row to verification table. Done.

### Phase G — Cross-cutting (G1, G2, G11, G15, G16)

| Gate | Description |
|---|---|
| G1 | Smoke: app boots, Stitcher tab renders, no console.error |
| G2 | Scope guard fires on cross-event mutation attempt (HTTP 409) |
| G11 | Bake-with-everything integration: 4 slots × per-slot SFX × transitions × trims → final MP4 plays end-to-end |
| G15 | Full 81+1 Playwright suite green |
| G16 | Retirement-decision protocol documented in PR description per §19.11.1 (N=14 days zero hits in /stitch_editor logs + zero unblocker reports + zero open blockers; daily metric audit rows in prod_activity_log) |

**Workflow extension (§19.6):** APPEND `e2e/s5_5g_smoke.spec.ts` to existing 10-spec list in `.github/workflows/playwright_e2e.yml`. Becomes 11. Below the §19.6.1 maintainability trigger threshold of 15.

### Phase H — 5 NEW LDs + closure LD (per §19.4)

| LD key | Severity | Decision_text core |
|---|---|---|
| `STITCHER_SFX_CUE_UI_V1` | **HARD** | Per-slot drag-drop SFX cue placement; CuePopover edit; module-level cues separate path |
| `STITCHER_TRANSITIONS_V1` | **HARD** | crossfade/cut/dissolve selector per boundary; dissolve adds video fadeblack via LD-376 pattern |
| `STITCHER_PER_SLOT_TRIMS_V1` | **HARD** | trim_in_ms/trim_out_ms on slot shape; pipeline ffmpeg pre-trim; trim fingerprint in cache key |
| `STITCHER_RAW_FETCH_MIGRATED_V1` | **HARD** | Verification LD (Wave 1 already did the migration) — confirms StitcherTab is 100% pathappPatch-clean per §19.10 |
| `PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1` | **SOFT** | Fix m_number→Event_<N> mapping at server.py:8537-8544 |
| `V59_CLIENT_FEATURE_COMPLETE_V1` | **HARD** (closure) | v59 Stitcher feature parity with /stitch_editor; retirement clock starts; metric per §19.11.1 |

**Severity reminder:** spec §19.4 amended ALL 5 NEW LDs from HIGH/MEDIUM to HARD/SOFT (post-2026-05-04 schema migration). Reference: `DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` Enum migration note 2026-05-04.

### Phase I — Final closeout (§19.11)

1. activity_log row `S5_5G_COMPLETE` + activity_log row `STORYBOARD_V59_FEATURE_PARITY_COMPLETE`
2. Update master overview status table at `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md` — mark all 4 sessions + Wave 1 + S5.5g as COMPLETE; v59 client = FEATURE-COMPLETE
3. Write `Production/docs/STORYBOARD_V59_FEATURE_PARITY_COMPLETE_HANDOFF.md` summarizing all 4 sessions + Wave 1 + retirement protocol
4. Spawn tail-end verifier subagent (cross-session integration, since this is the final session)
5. Single git commit + push to `origin/claude/s5_5g`
6. `gh pr create` with PR description containing the §19.11.1 retirement metric protocol verbatim (so daily audit cadence is unambiguous post-merge)

**Per spec §7 escape hatch and per Kim's Phase A authorization: gh pr create is allowed in Phase I, NOT before.**

---

## §5 Operating reminders for the next session

- **Path-prefix shorthand:** spec body uses `src/components/X.tsx` to mean `Production/tools/storyboard-v2/src/components/X.tsx`. `cd Production/tools/storyboard-v2` for npm/playwright/vite commands.
- **CI workflow location:** `.github/workflows/playwright_e2e.yml` — extend by APPENDING the new spec name. Do not use globs (per spec §19.6).
- **Fixture rule:** never mutate `Event_1` or `Event_2` (spec §7); `Event_e2e_fixture/` mutations + new `Event_e2e_fixture_2/` allowed.
- **MUTATION_CHANNEL_INVARIANT_V1 grep gate:** every new mutation must use `pathappPatch`. Reads (GET) are exempt. Allowlist additions require explicit Kim approval.
- **`try_post_or_queue` for Directus:** every Phase H LD + Phase I activity_log uses this helper (lib/directus.py:351). It writes live or queues offline; never raises. Do read-back via `DirectusAdminClient.get_item` after.
- **`task_id` audit chain:** every Phase B-I Directus write must include `details.task_id = "s5_5g-stitcher-parity-final-20260504"` so the weekly preflight audit FK-joins it to row id=205.
- **Rule 19/26/29/35/36:** spec governance. Rule 29 server staleness — restart `production_server.py` after edits BEFORE running probe tests. Rule 35 try_post_or_queue + read-back. Rule 36 patch-invariant.
- **Phase 1.5/3.5/6.5 fire** because the diff crosses JS↔Python boundary on /api/stitch_editor/job + /api/timeline/cues + /api/scene/assemble.
- **Browser smoke (LD-509):** subjective UX only — "feels right?" — Kim runs after the 11-spec Playwright suite is green.

---

## §6 Q1-Q3 RESOLVED (Kim 2026-05-04 — locked answers)

All 3 Phase A open questions answered by Kim post-Phase-A. Folded into §3.3 + §3.6 + §3 above. Recap:

1. **Q1 — Dissolve transition audio behavior:** ✅ RESOLVED — supports BOTH options via `audio_xfade_ms` field on transition shape. Default `audio_xfade_ms = fade_ms` (audio crossfade matches visual fadeblack). `audio_xfade_ms = 0` → pure visual fadeblack with hard audio cut. `audio_xfade_ms > 0` → both visual + audio dissolve. Server adds ~5-10 LOC at server.py:14920-14938; UI adds 1 numeric field or "Audio dissolve" checkbox in CuePopover. See §3.3 for the full transition shape.
2. **Q2 — Spec line-number drift:** ✅ RESOLVED — accept audit doc §2 as canonical for the Phase B-I session. Spec body stays as historical reference; do NOT amend spec body in Phase I closeout (would be churn for nothing). See §3.6.
3. **Q3 — dissolve `kind` shape:** ✅ RESOLVED — explicit `kind` field on transition shape (NOT inferred from source_path/fade_ms). Future-proof for new transition types. See §3.3.

These 3 answers are LOCKED in §3 above. Phase B-I terminal proceeds with them as decisions, not pending questions.

---

## §7 Phase A commit summary

Single commit on `claude/s5_5g`. Will push to `origin/claude/s5_5g`. NO PR.

```
V59 S5.5g Phase A — pre-flight + /stitch_editor audit + branch setup

- Pull main to 1b40d1b (Wave 1 merged via origin/main)
- Branch claude/s5_5g cut from main
- /stitch_editor job JSON shape, transition defaults, trim backend
  pattern audited; decisions locked in audit doc
- Production Map multi-event bug located at server.py:8537-8544
- Wave 1 raw-fetch migration verified (StitcherTab clean,
  G13 grep gate PASS)
- prod_preflight_reviews row id=205 written + read-back
  (task_id=s5_5g-stitcher-parity-final-20260504)
- Phase A audit doc + continuation handoff committed
- Phase B-I deferred to fresh session per Kim checkpoint authority

Refs: STORYBOARD_V59_S5_5_G_SPEC_v1.md (Cursor v8/v11/v12 approved),
      preflight id=205, branch cut from 1b40d1b
```
