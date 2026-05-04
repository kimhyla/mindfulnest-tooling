# Storyboard v59 — Feature Parity Arc COMPLETE Handoff

**Date:** 2026-05-04
**Status:** v59 Preact client = FEATURE-COMPLETE
**Final session:** S5.5g (this PR)
**Arc closure LD:** `V59_CLIENT_FEATURE_COMPLETE_V1` (id=528, HARD)
**Arc closeout activity log row:** `STORYBOARD_V59_FEATURE_PARITY_COMPLETE` (id=1508)

---

## §1 What just shipped

The v59 Preact client is now feature-complete. Kim composes final modules end-to-end in the v59 client without falling back to the legacy `/stitch_editor` tool. The retirement clock for `/stitch_editor` starts on this PR's merge.

Five sessions across ~3 weeks landed the full feature surface:

| Session | Commit | LDs | Scope |
|---|---|---|---|
| S5.5c+e proper-fix | `1d375de` | 506-510 | Beat Generator + Storyboard buttons + ProjectSelector + Production Map populate |
| Retroactive coverage v1 | `724942d` | `RETROACTIVE_COVERAGE_SPRINT_V1_COMPLETE` | 41 e2e tests across 6 retroactively-untested surfaces |
| S5.5f | `82c3fae` | 512-517 | Phase A/B parity: WaveSurfer + watercolor drag-drop + CuePopover + 3-clip handling + voice stem + ambient preset |
| Wave 1 architectural-fix | `1b40d1b` | 519-521 | MUTATION_CHANNEL_INVARIANT_V1 grep gate + StitcherTab/VideoSelector raw-fetch migration + sidecar fail-loud + requirements.txt |
| **S5.5g (this PR)** | head | **523-528** | **Stitcher SFX/transitions/trims + Production Map multi-event fix** |

**Total verification gates green across the arc:** 87+ Playwright tests across 11 specs, 13 grep-gate invocations, 3 server unit tests, plus per-session functional gates. All on every commit going forward.

---

## §2 What S5.5g specifically delivers

### 2.1 Per-slot SFX cue placement (G3-G6)

- **Per-slot SFX cues** live in `slot.sfx_cues[]` and persist via `stitch_save_job`.
- **Module-level SFX cues** live in `state.module_sfx_cues` and persist via the new `timeline_cue_upsert` MUTATION_ENDPOINT (`/api/timeline/cues`).
- Drag a `lib-sfx` payload onto `stitcher-slot-waveform-{slot}` → per-slot cue at `offset_ms = drop_x / wrapper_width × video_dur_ms`.
- Drag onto `stitcher-module-timeline` (below the slot strip) → module-level cue with `cue_type='sfx'`.
- Click any cue marker → `SfxCuePopover` (volume / fadein_ms / fadeout_ms / Delete).
- Server defaults consumed: volume=0.45, fadein_ms=300, fadeout_ms=1200 (`server.py:14085-14087`).

LD: `STITCHER_SFX_CUE_UI_V1` (id=523, HARD).

### 2.2 Per-boundary transitions with explicit kind + audio_xfade_ms (G7-G8)

Transition shape (Q1+Q3 LOCKED 2026-05-04):

```json
{
  "after_slot": 0,
  "kind": "crossfade" | "cut" | "dissolve",
  "fade_ms": 500,
  "audio_xfade_ms": 500,
  "source_path": "..."
}
```

Server defaults: `kind='crossfade'` if absent (back-compat); `audio_xfade_ms = fade_ms` if absent (audio matches visual).

- **`cut`** — pipeline skips transition synthesis entirely.
- **`crossfade`** — existing `trans_<after_slot>` SFX cue at slot tail; `audio_xfade_ms` controls fadein/fadeout duration.
- **`dissolve` (NEW)** — visual fadeblack via `ffmpeg fade=t=out` on `slot[after_slot]` tail + `fade=t=in` on `slot[after_slot+1]` head; if `audio_xfade_ms > 0` also `afade out/in` across the boundary; pure visual fadeblack with hard audio cut when `audio_xfade_ms = 0`. Cache key includes `fade_ms + audio_xfade_ms` so different windows don't collide. Reference: LD-376 fadeblack pattern.

UI: `StitcherTransitionSelector` × 3 between the 4 slots. LD: `STITCHER_TRANSITIONS_V1` (id=524, HARD).

### 2.3 Per-slot trims via `stitch_save_job` extension (G9-G10)

New slot fields `trim_in_ms` (default 0, inclusive) + `trim_out_ms` (null = full clip).

Persisted via `stitch_save_job` extension (NOT new endpoint per audit doc §5 — single mutation surface reuses scope guard + pin check + state lock from existing handler).

Server-side: `_stitch_normalize_slot` accepts `trim_in_ms / trim_out_ms`; cache key includes `t<in>-<out|end>` suffix; pre-trim via `ffmpeg -ss / -t` before `normalize_for_concat`. Validation: `trim_in_ms >= 0`; `trim_out_ms is null OR > trim_in_ms` (else 400).

UI: numeric inputs in seconds per slot (Cursor v8 Q9 deferred keyboard nudge). LD: `STITCHER_PER_SLOT_TRIMS_V1` (id=525, HARD).

### 2.4 Production Map multi-event mapping fix (G12-G13)

`production_server.py:_handle_production_map` now maps `m_number → Event_<N>` directory by on-disk convention:

```python
m_num = m.get("m_number")
candidate = production_root / f"Event_{m_num}"
edir = candidate if candidate.is_dir() else None
```

Replaces the prior bug where every module reported `event_dirs[0]` (typically `Event_1`). No Directus schema migration (audit doc §6 + Cursor v8 Q4 — derived from naming convention; column added only if editor overrides become necessary).

UI side required no change: `ProductionMapTab.tsx` already used `m.event_dir` from the response — the bug was always server-side. LD: `PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1` (id=527, SOFT).

### 2.5 StitcherTab pathappPatch-clean (verification only — Phase F per §19.10)

Wave 1 architectural-fix already migrated all StitcherTab mutations to `pathappPatch`. S5.5g verifies the gate stays green and adds the `timeline_cue_upsert` MUTATION_ENDPOINT for the new module-level cue path — also `pathappPatch`-routed. ProductionMapTab `event_load` remains a sanctioned exception per the gate's allowlist (blocker #53, deferred to Sprint D / Wave 3 per Cursor R6).

LD: `STITCHER_RAW_FETCH_MIGRATED_V1` (id=526, HARD).

---

## §3 `/stitch_editor` retirement clock — operational protocol per spec §19.11.1

The retirement of the legacy `/stitch_editor` route is metric-based, NOT calendar-based. Concrete criterion as of this PR's merge:

### 3.1 Daily metric audit (cron or weekly Kim-manual)

Each day after merge, log a `prod_activity_log` row `STITCH_EDITOR_RETIREMENT_METRIC_DAY_<N>` with:

| Field | Source | Pass criterion |
|---|---|---|
| `hits_in_server_logs` | `production_server.py` access log grep for `/stitch_editor*` | **0** |
| `unblocker_reports` | `prod_activity_log` rows + PR comments mentioning fallback to `/stitch_editor` | **0** |
| `open_blockers_referencing_stitch_editor` | `prod_blockers` query | **0** |

Any non-zero result resets `N` to 0 and logs the reason.

### 3.2 Decision points

- **Day N+1 (15 days post-merge with all criteria met):** Mark `/stitch_editor` route handlers as DEPRECATED in `production_server.py` — return HTTP 410 Gone with redirect message to v59 Stitcher tab. Continue daily audits.
- **Day N+30 (45 days post-merge):** If zero hits / zero unblockers continue, DELETE the `/stitch_editor` route handlers + supporting code. Write `STITCH_EDITOR_RETIRED_V1` LD (HARD) capturing the audit chain.
- **Reset condition:** ANY criterion fails (one hit, one unblocker, one open blocker) → reset `N` counter to 0 and continue running v59 in parallel.

### 3.3 Activation

The clock starts when this PR merges to `main`. The first daily audit row should land within 24 hours of merge.

---

## §4 Files touched in S5.5g

### NEW

- `Production/tools/storyboard-v2/e2e/s5_5g_smoke.spec.ts` — G3-G13 functional behavior gates
- `Production/tools/storyboard-v2/src/components/StitcherSlotWaveform.tsx` — per-slot drop target + cue markers
- `Production/tools/storyboard-v2/src/components/StitcherTransitionSelector.tsx` — kind dropdown + audio_xfade_ms input
- `Production/tools/storyboard-v2/src/components/phase/SfxCuePopover.tsx` — SFX cue inspector
- `Production/scripts/s5_5g_phase_a_preflight.py` — Phase A preflight row writer (id=205)
- `Production/scripts/s5_5g_phase_h_lds.py` — Phase H LD writer (ids 523-528)
- `Production/scripts/s5_5g_phase_i_closeout.py` — Phase I activity_log writer (ids 1507-1508)
- `Production/docs/STORYBOARD_V59_S5_5_G_PHASE_A_AUDIT.md` — Phase A audit report
- `Production/docs/STORYBOARD_V59_S5_5_G_CONTINUATION_HANDOFF.md` — Phase A → B-I handoff
- `Production/docs/STORYBOARD_V59_FEATURE_PARITY_COMPLETE_HANDOFF.md` — this file

### MODIFIED

- `Production/tools/storyboard-v2/src/components/StitcherTab.tsx` — extended with per-slot SFX waveform + transitions + trims + module-level cue strip + popover state
- `Production/tools/storyboard-v2/src/api/endpoints.ts` — added `timeline_cue_upsert: /api/timeline/cues`
- `Production/tools/storyboard-v2/src/app.css` — new component classes
- `Production/tools/production_server.py` —
  - `_stitch_normalize_slot` accepts `trim_in_ms / trim_out_ms` + cache fingerprint
  - `_stitch_apply_dissolve_tail` / `_head` for visual + audio dissolve
  - `_stitch_build_pipeline` branches on `transition.kind` (`cut` / `crossfade` / `dissolve`); validates trim values
  - `_handle_production_map` uses `f"Event_{m_num}"` convention-based mapping
- `.github/workflows/playwright_e2e.yml` — appended `e2e/s5_5g_smoke.spec.ts` to test command (now 11 specs; below §19.6.1 maintainability threshold of 15)

### DROPBOX TREE (closeout doc updates per scope guard)

- `Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md` — status table updated; v59 client = FEATURE-COMPLETE

---

## §5 Forward work (post-merge)

1. **Daily retirement metric audit** per §3 above.
2. **Sprint D / Wave 3 — comprehensive mutation channel.** Closes `prod_blockers` #50-53 (ProjectSelector × 2, EventSelector, ProductionMapTab `event_load` raw-fetch migrations) per Cursor R6 / spec §19.10 deferral.
3. **MindfulNest app foundation work** per `MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_SPEC_v1.md` + LD-518 `MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_DISCIPLINE_V1` (HARD). The 5 load-bearing discipline pieces (CI from commit 1; test-with-feature spec template; structural enforcement; schema contracts; observability + silent-failure detection) are now ready to drive app-side repos (iOS, Therapist Dashboard, Parent Dashboard, Functions).
4. **`/stitch_editor` retirement** per §3 — DEPRECATED at day 15 post-merge, DELETED at day 45 if criteria continue.

---

## §6 References

- Spec: `Production/docs/STORYBOARD_V59_S5_5_G_SPEC_v1.md` (Cursor v8 + v11 §19 + v12 R1-R5 fold approved 2026-05-04)
- Master overview: `Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md`
- Phase A audit: `Production/docs/STORYBOARD_V59_S5_5_G_PHASE_A_AUDIT.md`
- Continuation handoff: `Production/docs/STORYBOARD_V59_S5_5_G_CONTINUATION_HANDOFF.md`
- Preflight row: Directus `prod_preflight_reviews` id=205
- LDs: 523-528 (`STITCHER_*`, `PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1`, `V59_CLIENT_FEATURE_COMPLETE_V1`)
- Activity logs: 1507 (`S5_5G_COMPLETE`), 1508 (`STORYBOARD_V59_FEATURE_PARITY_COMPLETE`)
- Wave 1 grep gate script: `Production/scripts/verify_mutation_channel_invariant_gate.sh`
- CI workflow: `.github/workflows/playwright_e2e.yml`

---

**End of v59 feature parity arc.** Forward work: app foundation per LD-518.
