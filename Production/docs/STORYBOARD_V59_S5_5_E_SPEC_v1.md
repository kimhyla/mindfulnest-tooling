# Storyboard v59 — Sub-Session S5.5e Spec v1

**Date:** 2026-05-03
**Classification:** EXECUTION SPEC — feature build on locked v3 architecture + S5.5c primitives
**Predecessor:** S5.5c (Beat Generator UI + Cropper canvas + shared UI primitives)
**Master overview:** `STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md`

## §1 Task

Wire the Storyboard tab's beat-level production controls (regen audio, animate, lipsync, preview, use-as-final, etc.) + extend EventSelector to ProjectSelector with milestone listing + populate `prod_modules` Directus from `GAMEPLAY_SCOPE_v3.md` so Production Map shows all V1 modules.

After this session: Kim can take beats from Beat Generator (S5.5c) → process them through TTS / animation / lipsync via the Storyboard tab → and switch between Events and Milestones via ProjectSelector.

## §2 Governing Decisions

### LDs respected (do not violate)

| LD | Key | Reason |
|---|---|---|
| LD-181 | TTS_AUTO_REGEN_ON_TEXT_EDIT | Regen Audio button companion behavior; stale-TTS flag drives UX |
| LD-184 | PREVIEW_BEAT_AUDIO_FRESH_STREAM | Preview reads `/api/beat/audio/<beat_id>` always-fresh stream |
| LD-357 | V1_SCOPE_FROZEN_10_ARCS_59_MODULES | Source of truth for module roster |
| LD-456 / LD-460 / LD-461 | scope + pin + body helper | Standard mutation hygiene |
| LD-465 | PRODUCTION_MAP_V1 | Production Map endpoint contract |
| LD-467 | MULTI_EVENT_SELECTOR_V1 | EventSelector → ProjectSelector extension |
| LD-486 | MILESTONE_STANDALONE_INDEPENDENT_V1 | Milestones live at `Production/Milestones/<id>/state.json` |
| LD-487 / LD-488 | BG_VIDEO_PARTITION_V2 / VIDEO_ROLE_PER_REQUEST_V2 | Active partition routing |
| LD-494 | TARGET_VIDEO_SELECTOR_V1 | VideoSelector visibility per scope |

### NEW LDs this spec writes (5)

| Key | Severity | Purpose |
|---|---|---|
| `BEAT_BUTTONS_PORT_V1` | HIGH | Defines the canonical button row per beat: [Regen Audio] [Preview] [Animate] [Lipsync] [Use as Final]. Button visibility conditional on beat state per existing legacy storyboard pattern. |
| `PROJECT_SELECTOR_V1` | HIGH | EventSelector → ProjectSelector with grouped Events + Milestones; "+ New Milestone" CTA opens validation modal. |
| `PROD_MODULES_GAMEPLAY_SCOPE_SOURCE_V1` | HIGH | `prod_modules` Directus is mirrored from `GAMEPLAY_SCOPE_v3.md` (canonical V1 scope authority). One-shot importer script; re-runnable. |
| `BEAT_LIFECYCLE_STATE_MACHINE_V1` | MEDIUM | Beat state transitions: `draft → audio_generated → animated → lipsync_pending → final`. Buttons gate on transitions. |
| `STORYBOARD_RAW_FETCH_MIGRATED_V1` | LOW | Migrate `StoryboardTab.tsx ~L328+ (SendOutButton fetch block)` raw fetch (export buttons) to `pathappPatch`. Cursor v7 cleanup item. |

## §3 Approach

### §3.1 Storyboard tab beat button row

**File:** `src/components/StoryboardTab.tsx` — extend `BeatCard` (currently lines 95-204).

Per-beat button row (visibility conditional on beat state):

```
┌─ #N beat_NN [SPEAKER] [stale TTS] ──────── last save TS ┐
│ [dialogue contenteditable]                              │
│                                                         │
│ ┌─ Phase 1 (animation options) ────────────────────────┐│
│ │ [option 1] [option 2] [option 3]    [+ Add options]  ││
│ │ Selected: option 2  [Use as Final]                   ││
│ └──────────────────────────────────────────────────────┘│
│                                                         │
│ Audio: [Preview ▶] [Regen Audio]  Magic: [Still] [Video]│
│ Pipeline: [Animate] [Lipsync]  Direct: [Use as Final]   │
│ Trim: [in: 0.0s] [out: full]    Delay: [0.0s]           │
└─────────────────────────────────────────────────────────┘
```

**Button visibility rules** (per `BEAT_LIFECYCLE_STATE_MACHINE_V1`):

| Beat state | Visible buttons |
|---|---|
| `draft` (no audio yet) | Regen Audio, Magic Still |
| `audio_generated` (TTS done, no animation) | Preview, Regen Audio, Animate, Use as Final, Magic Still |
| `animated` (3 options, no selection) | Preview, Regen Audio, Magic Video, Add options |
| `selected` (option chosen, no lipsync) | Preview, Lipsync, Use as Final, Magic Video |
| `lipsync_pending` (in flight) | Preview (loading), Lipsync (disabled "in progress") |
| `final` (lipsync complete OR use-as-final) | Preview, Magic Video, Re-Lipsync (advanced) |

**State derivation (Cursor v8 fix):** read `beat.audio_file_present`, `beat.phase_1.options.length`, `beat.phase_1.selected_option`, `beat.lipsync.status`, **`beat.final` (block presence)**. NO new state fields needed; all backend fields exist. The `beat.final` block is what `_handle_use_as_final` writes (`production_server.py:10733-10748`); shape is `{source: "raw_option", source_option, file, approved_at}`. There is NO `beat.use_as_final` boolean; presence of `beat.final` IS the "final" signal.

### §3.2 Backend endpoints used (existing per Agent A audit; NO new backend)

| Endpoint | Purpose |
|---|---|
| `POST /api/beat/regenerate_audio` | TTS regen (ElevenLabs) |
| `POST /api/tts` | Direct TTS call |
| `GET /api/beat/audio/<beat_id>` | Preview audio stream (LD-184 fresh-from-disk) |
| `POST /api/animate` | 3 Kling animation options/beat |
| `POST /api/animate/redo` | Redo animation if all 3 unsuitable |
| `GET /api/animate/status` | Poll animation completion |
| `POST /api/select` | Select 1 of 3 animation options |
| `POST /api/beat/add_options` | Pull more animation options |
| `POST /api/lipsync` | Send for ByteDance lipsync |
| `GET /api/lipsync/status` | Poll lipsync completion |
| `POST /api/beat/use_as_final` | No-lipsync path (Spec A) |
| `POST /api/beat/delay` | Insert audio delay (lead-in silence) |
| `POST /api/beat/trim` | Set in/out trim points |
| `POST /api/inject-image` | Drag-drop library image to beat slot |
| `POST /api/assign-image` | Set beat's primary still |

### §3.3 ProjectSelector

**File:** `src/components/EventSelector.tsx` → renamed `src/components/ProjectSelector.tsx`. Update import in `app.tsx`.

UI:

```
┌─ Project ────────────────────────┐
│ Event_1 (current) ▼              │
└──────────────────────────────────┘

When dropdown open:
┌─────────────────────────────────┐
│ ── Events ──                    │
│ ✓ Event_1                       │
│   Event_2                       │
│   + New Event                   │
│ ── Milestones ──                │
│   Milestone: magic_intro_video  │
│   Milestone: stone_celebration  │
│   + New Milestone               │
└─────────────────────────────────┘
```

**Behavior:**
- On select Event: POST `/api/event/load` (existing); set `activeProjectType = 'event'`; set `activeMilestoneId = null`
- On select Milestone: POST `/api/milestones/load` (v3-added); set `activeProjectType = 'milestone'`; set `activeMilestoneId = <id>`
- "+ New Milestone": open Modal (S5.5c primitive) with `milestone_id` regex validation `^[a-z0-9][a-z0-9_-]{2,63}$`, reserved word check, label input
- Update URL via History API: `?event=<id>` OR `?milestone=<id>`
- Data source: GET `/api/project/list` (v3-added)
- VideoSelector / TargetVideoSelector visibility cascade per LD-494: hidden in milestone scope (already wired via `activeProjectType` signal in v3)

### §3.4 Production Map data populate

**One-shot script:** `Production/scripts/populate_prod_modules_from_gameplay_scope.py` (~150 lines)

**Behavior:**
1. Read `GAMEPLAY_SCOPE_v3.md` (canonical V1 scope per LD-357 frozen)
2. Parse module entries: extract `m_number`, `arc_id`, `colloquial_name` (creature), `video_role`, `stone_id`
3. Query existing `prod_modules` rows; build set of existing `m_number` values
4. For each parsed module not in existing set: POST to `prod_modules` via `try_post_or_queue` (Rule 35)
5. For existing modules: PATCH only if `colloquial_name` or `arc_id` differs (avoid clobbering manual edits)
6. Read-back per Rule 35: confirm all 59 rows present
7. Idempotent: re-runnable without duplication

**Modes:** `--dry-run` (default), `--apply` (writes), `--validate` (verifies all 59 rows exist).

After script runs: Production Map renders all 59 modules across 10 arcs (currently shows only 6 per browser smoke).

### §3.5 Raw fetch migration (Cursor v7 cleanup)

`StoryboardTab.tsx ~L328+ (SendOutButton fetch block)` currently does:
```ts
fetch(`http://localhost:5111/api/export?role=${role}&event_id=${activeScope.value.event_id}`, {...})
```

This bypasses `pathappPatch` (no auto-injection, no 409/423 handling). Migrate to:
```ts
await pathappPatch(activeScope.value, 'scene_assemble', { scope_target_video: role, fade_between_beats_ms: 0 });
```

(The endpoint `/api/export` is now HTTP 410 per v3 anyway; this should already be using `/api/scene/assemble`. Verify.)

## §4 Implementation Phases

### Phase A — Pre-flight + GAMEPLAY_SCOPE parser

**A1.** Read master overview, this spec, S5.5c COMPLETE activity log, v3 spec §3.4 (ProjectSelector design).

**A2.** Read `GAMEPLAY_SCOPE_v3.md` to understand parsing target. Identify section structure (likely Markdown tables or YAML frontmatter per memory entry).

**A3.** Write `Production/scripts/populate_prod_modules_from_gameplay_scope.py` per §3.4. Run `--dry-run` against current Directus state; verify parses correctly + identifies 53 missing modules.

**A4.** Run `--apply` mode. Read-back verify 59 rows in `prod_modules`. Write `prod_activity_log` row.

**A5.** Browser smoke (Phase E gate): Production Map renders 59 rows.

### Phase B — ProjectSelector

**B1.** Rename `EventSelector.tsx` → `ProjectSelector.tsx`. Update import in `app.tsx` + any other callers.

**B2.** Add grouped optgroup rendering: Events, Milestones, "+ New Event", "+ New Milestone".

**B3.** Wire Milestone selection to `/api/milestones/load`; update `activeProjectType` + `activeMilestoneId` signals.

**B4.** Wire "+ New Milestone" to Modal primitive (S5.5c) with regex-validated input + label.

**B5.** Update URL parsing on app boot to read `?event=<id>` OR `?milestone=<id>` and call appropriate load endpoint.

**B6.** Verify TargetVideoSelector hides in milestone scope (existing wiring; just verify).

**B7.** `npm run build` clean.

### Phase C — Storyboard beat button row

**C1.** Extend `BeatCard` in `StoryboardTab.tsx` to render the button row per §3.1.

**C2.** Implement state-machine derivation (lines ~150-200 of new code): infer current state from beat fields.

**C3.** Wire each button:
- Regen Audio → `pathappPatch(scope, 'beat_regenerate_audio', {beat_id, voice_profile_id?})`
- Preview → `<audio>` element with `src={apiUrl('beat_audio', {beat_id})}` + LD-184 fresh stream + Range support
- Animate → `pathappPatch(scope, 'animate', {beat_id})` + Toast "Submitted" + spinner on beat
- Animate poll → setInterval 5s GET `/api/animate/status` until done; refresh beat options on completion
- Select option → `pathappPatch(scope, 'select', {beat_id, option_index})`
- Add options → `pathappPatch(scope, 'beat_add_options', {beat_id})`
- Lipsync → `pathappPatch(scope, 'lipsync', {beat_id})` + Toast + spinner
- Lipsync poll → similar to Animate poll
- Use as Final → `pathappPatch(scope, 'beat_use_as_final', {beat_id})`
- Trim → 2 number inputs + `pathappPatch(scope, 'beat_trim', {beat_id, trim_in, trim_out})`
- Delay → number input + `pathappPatch(scope, 'beat_delay', {beat_id, delay_seconds})`

**C4.** Add `data-testid` per button: `beat-N-regen-audio`, `beat-N-animate`, etc.

**C5.** Migrate `StoryboardTab.tsx ~L328+ (SendOutButton fetch block)` raw fetch (export) to `pathappPatch` per §3.5.

**C6.** Add new endpoint URLs to `src/api/endpoints.ts` per §3.2 list. Add to `BG_MUTATION_ENDPOINTS` set if expecting `scope_event_id`.

**C7.** Implement audio Preview component using `<audio src={url} controls>`. New file `src/components/BeatAudioPreview.tsx`.

**C8.** `npm run build` clean.

### Phase D — Verification (14 gates)

**D1.** `npm run build` clean.
**D2.** Server `/api/health` 200; Rule 29.
**D3.** **Production Map probe:** GET `/api/production_map` returns ≥ 59 rows. Browser shows full 10-arc table.
**D4.** **ProjectSelector probe:** GET `/api/project/list` returns events + milestones grouped. Dropdown renders both groups.
**D5.** **Milestone load probe:** click milestone → `/api/milestones/load` POSTs → state.scope_type === 'milestone' → TargetVideoSelector hidden.
**D6.** **+ New Milestone probe:** modal opens, regex validation rejects `_BAD`/`event_x`/uppercase, accepts `valid_id`.
**D7.** **Regen Audio probe:** click button → `/api/beat/regenerate_audio` POSTs → audio file updated → stale-TTS chip clears.
**D8.** **Preview probe:** click Preview → `<audio>` plays from `/api/beat/audio/<beat_id>` → freshness verified (modify text + Preview returns NEW audio per LD-184).
**D9.** **Animate probe:** click Animate → status polls → 3 options appear in beat after completion. Test on a single beat.
**D10.** **Select probe:** click option radio → `/api/select` POST → option marked selected.
**D11.** **Lipsync probe:** with selected option, click Lipsync → status polls → `lipsync.status` transitions.
**D12.** **Use as Final probe:** click Use as Final → `/api/beat/use_as_final` POST → `beat.final` block written (with `source`, `source_option`, `file`, `approved_at`). Cursor v8 corrected: NOT a `beat.use_as_final` flag.
**D13.** **Raw fetch migration (expanded per Cursor v8 Q9):** `StoryboardTab.tsx ~L328+` (Send Out as MP4) now goes through `pathappPatch`. Plus grep gate: `grep -rE "fetch\(\\\${SERVER_BASE}|fetch\(\\\`http" src/components/` returns ZERO hits in StoryboardTab + ProductionMapTab paths owned by THIS session. (Stitcher migrations stay scoped to S5.5g — see §10.) Verify via Network tab that auto-injected scope fields are present in mutation requests.
**D14.** **Beat lifecycle state machine:** all button visibility transitions match table in §3.1.

### Phase E — LD writes

**E1.** Write 5 NEW LDs via `try_post_or_queue`:
- `BEAT_BUTTONS_PORT_V1` (HIGH)
- `PROJECT_SELECTOR_V1` (HIGH)
- `PROD_MODULES_GAMEPLAY_SCOPE_SOURCE_V1` (HIGH)
- `BEAT_LIFECYCLE_STATE_MACHINE_V1` (MEDIUM)
- `STORYBOARD_RAW_FETCH_MIGRATED_V1` (LOW)

### Phase F — Closeout

**F1.** `prod_activity_log` row `S5_5E_COMPLETE` with full 14-gate summary.

**F2.** Write S5.5f handoff stub at `Production/docs/STORYBOARD_V59_S5_5_F_HANDOFF.md`.

**F3.** Update master overview's table.

**F4.** Tail-end verifier subagent.

**F5.** Git commit: `S5.5e — Storyboard buttons + ProjectSelector + Production Map data (14 gates green)`.

## §5 Files Created / Modified

### Created
- `Production/scripts/populate_prod_modules_from_gameplay_scope.py` (~150 lines)
- `src/components/BeatAudioPreview.tsx` (~50 lines)
- `Production/docs/STORYBOARD_V59_S5_5_F_HANDOFF.md`

### Modified
- `src/components/EventSelector.tsx` → renamed `ProjectSelector.tsx`
- `src/components/StoryboardTab.tsx` (BeatCard extension; raw fetch migration)
- `src/api/endpoints.ts` (add ~12 beat-lifecycle endpoint URLs)
- `src/app.tsx` (URL parsing for ?event= / ?milestone=; ProjectSelector import)
- `src/state/scope.ts` (verify activeMilestoneId routing — no changes expected)

### Modified (Directus)
- `prod_modules`: 53 new rows (M7 through M59)

## §6 Directus Writes Required

### `prod_locked_decisions`
- POST 5 NEW LDs

### `prod_modules`
- ~53 new rows from GAMEPLAY_SCOPE_v3.md import

### `prod_activity_log`
- `S5_5E_PHASE_A_PROD_MODULES_POPULATED`
- `S5_5E_PHASE_B_PROJECT_SELECTOR`
- `S5_5E_PHASE_C_STORYBOARD_BUTTONS`
- `S5_5E_PHASE_D_VERIFICATION_PASS`
- `S5_5E_PHASE_E_LDS_REGISTERED`
- `S5_5E_COMPLETE`

### `prod_preflight_reviews`
- 1 row at session start; references S5.5c preflight as predecessor

### `prod_assets` (during D7-D12)
- TTS regen creates `tts_audio` rows
- Animation creates `pre_lipsync` rows
- Lipsync creates `lipsync_clip` rows
- All via existing flows

## §7 Error Cases and Handling

| Failure | Handling |
|---|---|
| GAMEPLAY_SCOPE_v3.md parse fails (unexpected format) | Abort import; report to Kim; do NOT POST partial data |
| `prod_modules` import duplicate `m_number` collision | Skip + log; PATCH only if `colloquial_name` differs |
| Milestone with invalid `milestone_id` | Modal shows inline regex error before POST |
| Animate timeout (>5 min) | Status poll continues; show "still processing" Toast; no auto-cancel |
| Lipsync timeout (>10 min) | Same; ByteDance can take time |
| Preview audio 404 | Show error Toast; don't break button row |
| Use as Final on beat without selected option | Button disabled (state machine) |
| Multiple polls running for same beat | Cancel prior poll on new submission |
| Raw fetch migration breaks Send Out as MP4 | Test E13 catches this; rollback via git checkout |
| ProjectSelector list refresh stale (new milestone created in another tab) | Manual refresh; defer auto-refresh to S6 |

## §8 Verification

Done when 14 gates green + 5 LDs + 53 prod_modules rows + activity_log + browser smoke deferred.

## §9 Rollback

- Storyboard buttons: `git checkout -- src/components/StoryboardTab.tsx`
- ProjectSelector: `git checkout -- src/components/{EventSelector,ProjectSelector}.tsx app.tsx`
- prod_modules: PATCH new rows to `is_active=false` (don't delete; preserves audit trail)

## §10 Out of Scope

- Voice profile management UI (LD-462; defer to S6)
- Phase A/B feature parity → S5.5f
- Stitcher SFX/transitions/trims → S5.5g
- Multi-event mapping in Production Map (currently uses Event_1 as canonical for all modules per `_handle_production_map`:8434) — defer to S5.5g
- Auto-refresh ProjectSelector on milestone create-in-another-tab — defer
- Animation cancel button — defer

## §11 Dependencies

**Hard dependencies on S5.5c:**
- `Modal` primitive (used by + New Milestone modal)
- `Toast` primitive (used everywhere)
- `Spinner` primitive (used in animate/lipsync polls)

**Hard dependencies on v3 (S5.5d-cont):**
- v3 endpoints (`/api/milestones/{list,create,load}`, `/api/project/list`)
- Scope signals (`activeProjectType`, `activeMilestoneId`)
- VideoSelector v3 update

## §12 Notes for the Executing Session

- ALL backend endpoints in §3.2 EXIST. No new server work. If a button doesn't work, the bug is in the wiring, not the endpoint.
- The raw fetch at `StoryboardTab.tsx ~L328+ (SendOutButton fetch block)` was flagged by Cursor v7. Migrating it during this session is correct — don't defer.
- 53 new `prod_modules` rows is the target. Verify via Directus dashboard or via `find_asset.py` after import.
- ProjectSelector rename: search the entire `src/` tree for `EventSelector` references; update all imports. TabBar doesn't reference it (TabBar is for tabs, ProjectSelector is in the header bar).
- Animate/Lipsync polls: use `setInterval` cleared on component unmount. NOT setTimeout chains (memory leak risk).
- Test E8 (Preview freshness) is critical for LD-184 compliance. Modify a beat's text → click Preview → audio MUST be the new TTS, not cached.
- The button row layout on small screens (Kim sometimes uses laptop): test at 1280px viewport. Wrap rows if needed.

## §13 Cursor Review Checklist

1. Beat lifecycle state machine — are the 6 states (`draft → audio_generated → animated → selected → lipsync_pending → final`) the right granularity? Missing any transitions?
2. Button visibility table in §3.1 — does this match the legacy storyboard's behavior, or are there cases the legacy handled differently?
3. ProjectSelector "+ New Milestone" modal — should it reuse Modal primitive (S5.5c) or be inline?
4. GAMEPLAY_SCOPE_v3.md parser — what's the format? Markdown tables? YAML frontmatter? Need to verify before Phase A.
5. Idempotency of `populate_prod_modules` script — what's the safe re-run behavior?
6. Animate poll interval (5s) — is this the right cadence vs server load?
7. Lipsync timeout policy — what does the legacy code do at 10 min? Cancel? Continue? Surface?
8. URL parsing on app boot: order of precedence between `?event=` and `?milestone=` if both present?
9. Cursor v8 verified: StitcherTab raw-fetch sites (~L70, 88-89, 123, 149, 191) + ProductionMapTab raw-fetch (event_load ~L114-118) are SCOPED TO S5.5g (this session migrates only Send Out). Confirm split is correct; or move ProductionMapTab event_load migration here since ProductionMap is touched in this session for data populate.
10. Multi-event mapping in Production Map (deferred to S5.5g) — risk of confusion if Production Map shows 59 modules but cell-click routes all to Event_1?

Append findings as §14.

---

## §14 Cursor v8 findings folded (audit trail)

| Finding | Resolution |
|---|---|
| Q1 lifecycle uses wrong field name `beat.use_as_final` | FIXED — derive from `beat.final` block presence (server writes this at `production_server.py:10733-10748`) |
| Q2 legacy mapping doc | AMENDED — Phase A deliverable: "legacy HTML button → endpoint → v59 testid" mapping table |
| Q4 GAMEPLAY_SCOPE_v3.md parser contract | AMENDED — Phase A2 dry-run gate "parses N modules == 59" |
| Q6 poll intervals | AMENDED — animate poll 5s; GPT batch poll 10s (longer-running); document distinct |
| Q7 lipsync timeout | AMENDED — match server constants in `_handle_lipsync_*` and legacy `build_storyboard.py` |
| Q8 URL precedence | AMENDED — milestone wins if both `?event=` AND `?milestone=`; ScopeBoundary error-toasts the conflict |
| Q9 raw-fetch scope | AMENDED — this session: Send Out (StoryboardTab); S5.5g: Stitcher + ProductionMapTab event_load. Optional: move ProductionMapTab event_load here since this session touches the file anyway. |
| Q10 multi-event nav defer | AMENDED — Phase D gates assert row count + table render only; "click-to-correct-event" gate moves to S5.5g per Cursor v8 Q10 |
| Beyond #1 line ref `:310` was wrong | FIXED — `~L328+` SendOutButton fetch block (verified) |
| Beyond #2 prod_modules baseline count | NEW GATE — Phase A4: `--dry-run` first reports current row count baseline before `--apply` |

Total gates now: 14 (no change; Q9 expansion folds into existing D13).

**End of S5.5e spec v1 (Cursor v8 folded).**
