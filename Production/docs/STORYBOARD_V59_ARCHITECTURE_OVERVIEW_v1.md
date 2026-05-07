# Storyboard v59 — Architecture Overview (How the New Storyboard Works)

**Date:** 2026-05-04
**Audience:** Future sessions (Claude or Kim) needing to understand the v59 storyboard tool's structure end-to-end without re-reading 4 PRs of source.
**Companion:** `STORYBOARD_V59_LESSONS_LEARNED_v1.md` (the "why these decisions" doc)
**Source of truth for code:** `kimhyla/mindfulnest-tooling` GitHub repo at HEAD of `main` (currently `1b40d1b` post-Wave-1; will advance with each subsequent merge)
**Source of truth for state:** `Production/Event_<N>/production_state.json` (per-event) + Directus `prod_*` collections (provenance + governance)

## §1 Where everything lives

### §1.1 Two trees

The v59 storyboard tool exists in **two synchronized but distinct trees**:

| Tree | Path | Purpose | Has GitHub remote? |
|---|---|---|---|
| **Dropbox tree** (canonical) | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` | Authoring, docs, state files, media, governance | NO (Dropbox sync only) |
| **Tooling repo tree** (CI-bound) | `/Users/kimberlysmith/Projects/mindfulnest-tooling/` | Code that ships through CI; subset boundary defined in LD-505 | YES — `kimhyla/mindfulnest-tooling` (PRIVATE) |

**Boundary rule (LD-505):**
- **Tooling repo CANONICAL for:** `Production/tools/storyboard-v2/`, `Production/tools/{production_server.py, ffmpeg_utils.py, lipsync_sender.py, kling_startend_pipeline.py}`, `Production/lib/`, `Production/scripts/`, `Production/Event_e2e_fixture/`, `Production/docs/` (snapshot — see below)
- **Dropbox CANONICAL for:** all other `Production/` content (Event_*/, Magic/, Milestones/, Backgrounds/, Character_Assets/, etc.), `Production/docs/` (live), all root-level docs (master tech spec, lessons learned, etc.)
- **Sync:** boundary files have edits in tooling repo (where CI runs); Dropbox copy is a deprecated mirror not actively edited; Production/docs/ in tooling repo is a one-time snapshot from `b582f44` and may lag behind Dropbox

### §1.2 Production tree layout (Dropbox + boundary subset)

```
Production/
├── tools/
│   ├── storyboard-v2/                  ← CANONICAL CLIENT (tooling repo)
│   │   ├── src/
│   │   │   ├── api/
│   │   │   │   ├── client.ts           ← pathappPatch implementation
│   │   │   │   └── endpoints.ts        ← MUTATION_ENDPOINTS catalog
│   │   │   ├── components/
│   │   │   │   ├── BgTab.tsx           ← Beat Generator
│   │   │   │   ├── StoryboardTab.tsx   ← beat list + lifecycle
│   │   │   │   ├── StitcherTab.tsx     ← module assembly (S5.5g extends)
│   │   │   │   ├── ProjectSelector.tsx ← event/milestone scope picker
│   │   │   │   ├── EventSelector.tsx   ← (legacy; being absorbed by ProjectSelector)
│   │   │   │   ├── VideoSelector.tsx   ← intro/resolution/standalone partition
│   │   │   │   ├── ScopeBoundary.tsx   ← scope-aware mount/unmount
│   │   │   │   ├── LibraryPanel.tsx    ← drag-drop source for cues + assets
│   │   │   │   ├── ProductionMapTab.tsx← V1 module enumeration view
│   │   │   │   ├── TabBar.tsx          ← top-level navigation
│   │   │   │   ├── phase/              ← Phase A/B Producer (S5.5f)
│   │   │   │   │   ├── PhaseProducer.tsx
│   │   │   │   │   ├── WaveformTimeline.tsx  ← WaveSurfer v7 mount
│   │   │   │   │   ├── CuePopover.tsx        ← cue inspector (REUSED in S5.5g)
│   │   │   │   │   └── BaseClipPicker.tsx    ← Phase A 3-clip picker
│   │   │   │   └── ui/                 ← shared primitives (S5.5c)
│   │   │   │       ├── AssetTile.tsx
│   │   │   │       ├── Modal.tsx
│   │   │   │       ├── Toast.tsx
│   │   │   │       └── Spinner.tsx
│   │   │   ├── state/
│   │   │   │   ├── scope.ts            ← @preact/signals for scope (active event,
│   │   │   │   │                          milestone, target_video, video_role)
│   │   │   │   └── ...
│   │   │   ├── utils/
│   │   │   │   ├── dragdrop.ts         ← drag-drop payload helpers (S5.5c)
│   │   │   │   └── ...
│   │   │   ├── app.css
│   │   │   └── index.css               ← CSS variables (--ui-library-tile-size, etc.)
│   │   ├── e2e/
│   │   │   ├── helpers.ts              ← shared Playwright helpers
│   │   │   ├── s5_5ce_proper_fix.spec.ts        ← 13 R-bug tests (PR #1)
│   │   │   ├── retroactive_s1_beat_lifecycle.spec.ts
│   │   │   ├── retroactive_s2_pathapp_patch.spec.ts
│   │   │   ├── retroactive_s3_storyboard_refresh.spec.ts
│   │   │   ├── retroactive_s4_magic_compositor.spec.ts
│   │   │   ├── retroactive_s5_library_rendering.spec.ts
│   │   │   ├── retroactive_s6_scope_boundary.spec.ts  ← 41 retroactive tests (PR #2)
│   │   │   ├── s5_5f_smoke.spec.ts     ← 18 F-gates (PR #3)
│   │   │   ├── architectural_fix.spec.ts  ← 9 AF tests (PR #4)
│   │   │   ├── smoke.spec.ts           ← deferred (needs full Event_1 fixture)
│   │   │   ├── behavioral-parity.spec.ts  ← deferred
│   │   │   ├── rollback.spec.ts        ← deferred
│   │   │   └── touchpoint-a.spec.ts    ← deferred
│   │   ├── playwright.config.ts        ← Chromium, port 5111, webServer config
│   │   ├── package.json
│   │   └── package-lock.json
│   ├── production_server.py            ← Python HTTP server (~16k lines)
│   ├── ffmpeg_utils.py
│   ├── lipsync_sender.py
│   ├── kling_startend_pipeline.py
│   └── requirements.txt                ← runtime deps (PyYAML, Pillow) — Wave 1
├── lib/
│   ├── atomic_json_write.py            ← Windows/Dropbox-safe JSON writes (LD-368)
│   ├── credential_store.py             ← Doppler-first secrets resolution
│   ├── directus.py                     ← try_post_or_queue with read-back
│   ├── directus_admin_client.py        ← DirectusAdminClient + auth refresh
│   └── wavespeed_poll_client.py
├── scripts/
│   ├── populate_prod_modules_from_gameplay_scope.py
│   └── ... (one-shot maintenance scripts)
├── Event_e2e_fixture/                  ← test fixture per LD §17 (proper-fix)
│   └── production_state.json + sidecar files
├── Event_1/, Event_2/, ...             ← live event data (Dropbox-only)
├── docs/                               ← all specs + handoffs + reference docs
├── DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md
├── API_KEYS_MASTER.md                  ← legacy fallback (gitignored, NEVER pushed)
└── github_actions/                     ← workflow source (mirrored to .github/workflows/)
.github/workflows/                       ← CI workflows (only at repo root in tooling repo)
└── playwright_e2e.yml                  ← MANDATORY e2e gate (LD-507/508)
.git/                                   ← repo metadata
```

## §2 Component architecture (TypeScript / Preact client)

### §2.1 Tab structure (top-level UI)

The v59 client is a single-page Preact app (Vite-bundled, ~173 KB minified / ~51 KB gzipped). Tabs:

| Tab | Component | Purpose |
|---|---|---|
| Beat Generator | `BgTab.tsx` | Generate beats from Tessa script; option construction; magic invocation |
| Storyboard | `StoryboardTab.tsx` | Beat list with lifecycle controls (regen, lock, finalize, send for lipsync, preview, magic) |
| Phase A/B | `PhaseProducer.tsx` | Per-phase video assembly (Phase A: 3-clip; Phase B: single base clip + watercolor cues) |
| Stitcher | `StitcherTab.tsx` | Final module assembly (4 slots: intro / Phase A / Phase B / resolution); SFX cues + transitions + per-slot trims (S5.5g extends) |
| Production Map | `ProductionMapTab.tsx` | V1 module enumeration; M1-M59 row table with creature_name + status |
| Project | `ProjectSelector.tsx` | Top-level scope picker: event, milestone, target_video, video_role |

`TabBar.tsx` wraps these with `ScopeBoundary` so each tab gets unmounted/remounted when scope changes (clean state per scope).

### §2.2 State management — signals

State lives in `src/state/scope.ts` (and similar files) using `@preact/signals`. Key signals:

```typescript
activeScope: Signal<Scope>  // {event_id, milestone_id, beat_id?, ...}
activeTargetVideo: Signal<'intro' | 'resolution' | 'standalone' | null>
activeProjectType: Signal<'event' | 'milestone' | null>
activeMilestoneId: Signal<string | null>
activeVideoRole: Signal<string | null>  // alias for scope_video_role
```

Components subscribe via `signal.value` in render functions; mutations update signals via `signal.value = ...`. Components automatically re-render when their signals change.

`ScopeBoundary` watches the active scope signal and unmounts/remounts children on scope change — guarantees no stale data leaks across scope switches.

### §2.3 Mutation channel — pathappPatch (LD-519)

**ALL state mutations go through `pathappPatch()` at `src/api/client.ts:175`:**

```typescript
export async function pathappPatch<T = unknown>(
  scope: Scope,
  endpoint: MutationEndpoint,  // keyof typeof MUTATION_ENDPOINTS
  body: Record<string, unknown> = {},
  opts: PatchOptions = {},
): Promise<ApiResult<T>>
```

What it does:
1. **M1 snapshot** (fire-and-forget): POST `MUTATION_ENDPOINTS.state_snapshot` with `{event_id}` before every non-snapshot mutation
2. **Resolve URL:** `MUTATION_ENDPOINTS[endpoint]` → real mutation endpoint (e.g., `/api/stitch_editor/preview`)
3. **Auto-inject scope keys** in body via `scopeKeyFor(endpoint)`:
   - BG endpoints (in `BG_MUTATION_ENDPOINTS` set): `scope_event_id`
   - All others: `event_id`
   - Plus always: `scope_target_video`, `scope_video_role`, optional `scope_milestone_id`
4. **POST** to the resolved URL with auto-injected body
5. **Handle 409** (scope_mismatch, LD-456) → emit `mn:scope-mismatch` event, return `ok=false`
6. **Handle 423** (event_changed_mid_job, LD-458/460) → re-hydrate scope from active signals + retry once
7. **Handle 4xx/5xx** → propagate as `ok=false` with error message

**`MUTATION_ENDPOINTS` catalog at `src/api/endpoints.ts:49-107`** — typed object mapping endpoint keys to URLs. Currently includes (post-PR #4 + Wave 1 + S5.5f):
- BG: `bg_set_option`, `bg_accept_option`, `bg_finalize`, `bg_unlock`, `bg_accept_lib_image`, etc.
- Stitcher: `stitch_save_job`, `stitch_loudnorm`, `stitch_preview` (Wave 1), `stitch_bake` (Wave 1)
- Video: `video_set_active`, `video_create`
- Module: `v2_module_patch` (S5.5f Phase C)
- Snapshot: `state_snapshot`
- Event: `event_load` (READ — not a mutation; bypasses pathappPatch)
- ... (full catalog in endpoints.ts)

**Structural enforcement (LD-519):** `.github/workflows/playwright_e2e.yml` includes a mandatory grep CI gate that fails the build if `fetch(MUTATION_ENDPOINTS.*)` or `fetch(/api/{stitch_editor,video}/...)` appears outside `src/api/` (where `pathappPatch` legitimately uses MUTATION_ENDPOINTS internally). Two-step gate: blocking (fails on new violations) + strict (continue-on-error, surfaces the 4 known-deferred event_load violations #50-53 every CI run as warning).

### §2.4 Drag-drop — payload helpers (LD `DRAG_DROP_HELPER_V1`)

`src/utils/dragdrop.ts` provides:

```typescript
setDragData(event: DragEvent, payload: DragPayload): void
getDragData(event: DragEvent): DragPayload | null
```

`DragPayload` is a discriminated union: `{kind: 'lib-image', lib_key, tier}` | `{kind: 'watercolor', lib_key, ...}` | `{kind: 'sfx', lib_key, ...}` | etc.

Drag SOURCES (LibraryPanel tiles for various tiers — character ref, BG, watercolor, SFX). Drag TARGETS (BgTab beat option slots, char/BG ref slots, CropperModal canvas, PhaseProducer waveform, StitcherTab slot waveforms, etc.). Drop handlers route via `pathappPatch` with the appropriate endpoint key + scope-key auto-injection.

CSS class `is-drag-over` (NOT `[draghover]`) applied via `onDragOver`/`onDragLeave` for visual cue.

## §3 Server architecture (Python)

### §3.1 production_server.py (~16k lines)

`Production/tools/production_server.py` is the Python HTTP server backing all client mutations. Architecture:

- **stdlib + minimal deps** (Pillow, PyYAML; per `Production/tools/requirements.txt` from Wave 1)
- **Routes via `_handle_*` methods** on the server class
- **Each handler:** parse body → validate scope → execute → write state → return JSON
- **Scope guard:** most mutation handlers wrap `@with_pin_and_drain('<action>', track_sync=...)` to coordinate concurrent edits via Directus locks (LD `DIRECTUS_LOCK_*`)
- **State persistence:** `Production/Event_<N>/production_state.json` (per-event) — atomic write via `lib.atomic_json_write` (LD-368)
- **Sidecar files:** `Production/Event_<N>/production_state.L.json` etc. — secondary indexes; Wave 1 fixed silent TypeError + added isinstance guard at line 3885 (LD-520)

### §3.2 Imports + sys.path

`production_server.py:54-58`:
```python
sys.path.insert(0, os.path.dirname(__file__))  # Production/tools/
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # Production/
```

Imports:
- `lib.atomic_json_write` (Production/lib)
- Sibling tools modules: `ffmpeg_utils`, `lipsync_sender`, `kling_startend_pipeline` (Production/tools/)

Tooling repo replicates the `Production/tools/` and `Production/lib/` layout so the imports resolve correctly in CI.

### §3.3 Env vars

Server reads (selected — see `Production/lib/credential_store.py` for full list):
- `DIRECTUS_URL`, `DIRECTUS_ADMIN_EMAIL`, `DIRECTUS_ADMIN_PASSWORD` (auth + lock client)
- `WAVESPEED_API_KEY`, `ELEVENLABS_API_KEY`, `EVOLINK_API_KEY`, `BFL_API_KEY`, `OPENAI_API_KEY` (vendor APIs)
- `MINDFULNEST_T1_ENABLED` (default "1"), `PRODUCTION_SERVER_SINGLE_MACHINE` (default off), `MINDFULNEST_WRITE_PATH`

Resolution order (per `credential_store.py`):
1. Env var (Doppler-managed in CI)
2. Fallback: parse `Production/API_KEYS_MASTER.md` from Dropbox (local Mac dev only — never available in CI)

Wave 1 fix-loud LD-520 mandates that any caught exception in write paths logs + raises (or fails the request); never silent print.

### §3.4 Endpoints used by v59 client

Selected endpoints (full inventory in production_server.py):

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | server liveness probe (Rule 29) |
| `/api/state/snapshot` | POST | M1 snapshot (pre-mutation) |
| `/api/event/load` | POST | load event scope (READ — not mutation; raw fetch allowed) |
| `/api/event/create` | POST | create new event (NEW per LD-510) |
| `/api/milestones/load` | POST | load milestone scope |
| `/api/bg/...` | POST | beat generation + option mgmt |
| `/api/stitch_editor/preview` | POST | preview stitched output |
| `/api/stitch_editor/bake` | POST | bake final MP4 |
| `/api/stitch_editor/job` | POST | save/load job |
| `/api/stitch_editor/jobs` | GET | list jobs (READ) |
| `/api/stitch_editor/loudnorm` | POST | loudness normalization |
| `/api/timeline/cues` | POST | cue create / DELETE for delete |
| `/api/v2/module/patch` | POST | unified module field patch (S5.5f) |
| `/api/video/set_active` | POST | switch active video partition |
| `/api/video/create` | POST | create new target_video |
| `/api/scene/assemble` | POST | Stage 2 orchestration (LD-490) |
| `/api/phase_b/regen_audio` | POST | voice stem generation (misnamed; LD-Cursor v8 Q5) |
| `/api/phase_b/mix_audio` | POST | full Phase B mix |
| `/api/phase_b/ambient_preset_list` | GET | ambient preset list (NEW S5.5f Phase E) |
| `/api/cr/library` | GET | library tiles |
| `/api/magic/run`, `/api/magic/resolve_bg` | POST | magic compositor |
| `/api/production_map` | GET | V1 module enumeration |

## §4 CI architecture

### §4.1 Workflow (`.github/workflows/playwright_e2e.yml`)

Triggers: push to `main` / `claude/*` / `feature/*`; pull_request to `main`.

Jobs (single `e2e` job):
1. checkout
2. setup-node@v4 (Node 20)
3. setup-python@v5 (Python 3.9)
4. Fail-fast secrets preflight (assert DIRECTUS_* env vars set)
5. `pip install -r Production/tools/requirements.txt` (LD-521 — Wave 1)
6. `npm ci` in `Production/tools/storyboard-v2`
7. `npm run build` (TS check + Vite build)
8. `npx playwright install --with-deps chromium`
9. **Mutation channel invariant grep gate** (LD-519 — Wave 1): blocking step + strict step (continue-on-error)
10. `npx playwright test` against the explicit spec list (post-Wave-1 = 9 specs; post-S5.5g = 10 specs)
11. Upload test artifacts on failure

Spec list explicit (NO globs — would silently include deferred scaffold). Threshold: when list >15 specs, migrate to project/tag-based grouping in playwright.config.ts (S5.5g §19.6.1).

### §4.2 Test count by surface

Post-Wave-1, the suite runs **81 tests across 9 spec files**:

| Spec | Tests | Source |
|---|---|---|
| s5_5ce_proper_fix.spec.ts | 13 | PR #1 (R1.1-R5 + +NewEvent) |
| retroactive_s1_beat_lifecycle.spec.ts | 8 | PR #2 |
| retroactive_s2_pathapp_patch.spec.ts | 6 | PR #2 |
| retroactive_s3_storyboard_refresh.spec.ts | 4 | PR #2 |
| retroactive_s4_magic_compositor.spec.ts | 8 | PR #2 |
| retroactive_s5_library_rendering.spec.ts | 7 | PR #2 |
| retroactive_s6_scope_boundary.spec.ts | 8 | PR #2 |
| s5_5f_smoke.spec.ts | 18 | PR #3 (F3-F18) |
| architectural_fix.spec.ts | 9 | PR #4 (AF.1.1-AF.2.4 + AF.3.1) |

Post-S5.5g this becomes 10 specs (+ s5_5g_smoke.spec.ts).

### §4.3 Fixture pinning (LD §17 from proper-fix)

Tests use `Production/Event_e2e_fixture/` ONLY, never live `Event_1/` or `Event_2/`. Setup: Playwright `globalSetup` copies fixture to a temp location; tests run against the temp copy. Teardown: removes temp + any test-created artifacts.

If a test legitimately needs different fixture state, create `Event_e2e_fixture_v2/` rather than mutating v1. Versioned fixtures preserve reproducibility.

### §4.4 Flake governance (LD §16 from proper-fix)

- **Critical-path tests** (R1-R5 + +NewEvent + S5.5f F-gates + AF.* + s5_5g G-gates) NEVER quarantined. Diagnose root cause + fix.
- **Non-critical** tests flaking 2× in 7 days without code change → quarantine via `test.fixme(...)` with comment block + `prod_activity_log` `TEST_QUARANTINED` row.
- **Retry discipline:** `retries: 1` in CI mode (single retry for transient infra), `retries: 0` locally (see flake immediately).

## §5 Locked decisions index (the 17 LDs that codify v59 architecture)

Cross-reference: full text in Directus `prod_locked_decisions`. Severities per HARD/SOFT enum migration 2026-05-04.

### §5.1 Tooling repo + boundary (LD-505)
- **TOOLING_REPO_CREATED_V1** (HARD): Repo URL + working tree path + subset boundary defining what's canonical-in-tooling vs canonical-in-Dropbox.

### §5.2 Proper-fix family (LD-506-510, PR #1)
- **S5_5CE_PROPER_FIX_V1** (HARD): Combined TDD bugfix for 5 R-bugs + +NewEvent + 3 process structural changes
- **MANDATORY_E2E_GATE_V1** (HARD): Every functional spec gate must have Playwright e2e test
- **CI_PLAYWRIGHT_ON_COMMIT_V1** (HARD): GitHub Actions runs Playwright on every commit; CI status required
- **BROWSER_SMOKE_REDEFINED_V1** (SOFT): Browser smoke = subjective UX only, NOT "does anything work" (automated via e2e)
- **NEW_EVENT_CREATION_UI_V1** (SOFT): + New Event modal + `_handle_event_create` server endpoint

### §5.3 Retroactive coverage (LD-511, PR #2)
- **RETROACTIVE_COVERAGE_SPRINT_V1_COMPLETE** (SOFT): 41 e2e tests across 6 surfaces; 4 prod_blockers found

### §5.4 S5.5f Phase A/B parity family (LD-512-517, PR #3)
- **WAVESURFER_TIMELINE_INTEGRATION_V1** (HARD): WaveSurfer v7 timeline in PhaseProducer; reused in S5.5g for SFX
- **WATERCOLOR_DRAG_DROP_TIMELINE_V1** (HARD): Drag watercolor → drop on timeline → cue created
- **CUE_POPOVER_INSPECTOR_V1** (HARD): CuePopover for cue inspection; reused in S5.5g for SFX cues
- **PHASE_A_THREE_CLIP_HANDLING_V1** (HARD): Phase A renders 3 clip slots (fly-in / sitting / fly-out)
- **VOICE_STEM_UPLOAD_UI_V1** (SOFT): Generate-stem-from-script button (uses misnamed regen_audio endpoint)
- **AMBIENT_PRESET_SELECTOR_INPRODUCER_V1** (SOFT): Ambient preset selector inside producer + new server endpoint

### §5.5 App architecture foundation (LD-518)
- **MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_DISCIPLINE_V1** (HARD): All MindfulNest app-side repos must have 5 load-bearing pieces (CI from commit 1; test-with-feature template; structural enforcement; schema contracts; observability) before feature 1. Master tech spec §14.13 + v6.2 changelog point here.

### §5.6 Wave 1 architectural fix family (LD-519-521, PR #4)
- **MUTATION_CHANNEL_INVARIANT_V1** (HARD): Mandatory grep CI gate enforcing pathappPatch on raw mutation patterns in src/components+state+utils
- **SERVER_SILENT_FAILURE_FAIL_LOUD_V1** (HARD): Server caught-exception write paths log+raise/fail-request, never silent print
- **PRODUCTION_TOOLING_REQUIREMENTS_TXT_V1** (SOFT): Production/tools/requirements.txt is canonical runtime dep list

## §6 The four flows (end-to-end behavior)

### §6.1 Flow A — Create a beat from a Tessa script line

1. User opens Beat Generator tab (BgTab)
2. Active scope has event_id (e.g., Event_1) + target_video (e.g., intro)
3. User clicks "Generate beats" → `pathappPatch(scope, 'bg_generate', body)` → server submits 3 GPT calls with varied seed → 3 OPTIONS returned (NOT 9 stills; per LD `BEAT_GEN_3_OPTIONS_NOT_GRID_V1`)
4. User reviews 3 options; clicks radio on a chosen option → `pathappPatch(scope, 'bg_accept_option', {beat_id, option_key})` → server updates `state.beats[i].chosen_option`
5. User clicks "Lock beat" → `pathappPatch(scope, 'bg_finalize', {beat_id})` → server writes `state.beats[i].final` block
6. Beat appears in Storyboard tab as "locked" (lifecycle state derived client-side from `beat.final` block presence)

### §6.2 Flow B — Compose a Phase A/B video

1. User opens Phase A or Phase B tab (PhaseProducer with phase = 'a' or 'b')
2. Phase B: pick base clip from BaseClipPicker; click "Generate stem from script" → POST `/api/phase_b/regen_audio` → voice stem written to `state.phase_b.voice_stem_file`
3. WaveformTimeline mounts WaveSurfer v7 with auto-selected source (lipsync if available, else mixed_audio, else voice_stem)
4. User drags watercolor tile from LibraryPanel → drops on waveform at time X → `pathappPatch(scope, 'v2_module_patch', {phase_b_watercolor_cues_json: [...new...]})` → cue marker renders
5. User clicks cue marker → CuePopover opens → adjusts animation_type / duration / volume → save via pathappPatch
6. Phase A: 3 clip slots (fly-in / sitting / fly-out); user picks each via BaseClipPicker; click "Re-stitch" → `pathappPatch(scope, 'phase_a_mix_audio')` → server's `_auto_assemble_phase_a_stitched` produces stitched MP4
7. Phase A stitched_file or Phase B mixed_file appears in Stitcher slot

### §6.3 Flow C — Stitcher final module assembly (S5.5g extends)

1. User opens Stitcher tab (StitcherTab)
2. 4 slots populated: intro scene + Phase A stitched + Phase B lipsync + resolution scene (with their respective audio sources)
3. User drags SFX tile from LibraryPanel → drops on slot waveform at time X → `pathappPatch(scope, 'timeline_cue_create', {slot, cue_type: 'sfx', source_path, offset_ms, volume, fadein_ms, fadeout_ms})` → cue stored in `slot.sfx_cues`
4. User selects per-boundary transition (crossfade / cut / dissolve) → save via `pathappPatch(scope, 'stitch_save_job', {transitions: [...]})` (post-S5.5g)
5. User adjusts per-slot trim handles → save trim_in_ms / trim_out_ms via stitch_save_job (post-S5.5g)
6. User clicks "Bake final MP4" → POST `/api/stitch_editor/bake` (via pathappPatch with `stitch_bake` key per Wave 1) → server runs `/api/scene/assemble` (LD-490) → ONE atomic MP4 written to module's final location

### §6.4 Flow D — Production Map navigation

1. User opens Production Map tab
2. GET `/api/production_map` → server returns ≥ 59 rows (M1-M59 from `prod_modules` + GAMEPLAY_SCOPE_v3.md per LD-357 V1 frozen)
3. Each row: m_number + creature_name + status indicators (intro asset / phase_a / phase_b / resolution / final)
4. User clicks cell → navigates to scope (event_id derived from m_number per S5.5g convention `m_number → Event_<N>`)
5. Active scope updates → ScopeBoundary unmounts/remounts other tabs

## §7 Known issues + deferred work

### §7.1 Open prod_blockers (#50-53)
- ProjectSelector × 2, EventSelector × 1, ProductionMapTab × 1: raw `fetch` to `event_load` bypassing pathappPatch. Logged by Wave 1 grep gate; deferred to Sprint D / Wave 3 per scope guard. Strict-warning step surfaces them every CI run.

### §7.2 /stitch_editor retirement
Per S5.5g §19.11.1 (locked 2026-05-04): once S5.5g ships + merges, daily metric audit cadence starts. N=14 consecutive days zero-hits + zero-unblocker-reports + zero-open-blockers → deprecate at day 15 (return 410 Gone) → delete at day 45.

### §7.3 Sprint E (Wave 4) — server audit recommended near-term
Audit silent-failure pattern beyond F-SVR-001 (greppable: `[*] write failed`, `[*] error` etc.); pathappPatch envelope acceptance on all server mutation handlers; pre-write state snapshot consistency; concurrency / drain protocol coverage. ~4 hr session.

### §7.4 Other deferred sprints (Sprints B/C/D/F)
Per `STORYBOARD_V59_DEFERRED_RETROACTIVE_COVERAGE_BACKLOG.md` — opportunistic, scheduled by trigger conditions in §6 of that doc.

### §7.5 Voice stem endpoint misnamed
`/api/phase_b/regen_audio` actually writes voice_stem files (despite the name). Cursor v8 Q5 clarification. Renaming is out of scope (would break existing integrations).

### §7.6 Master overview in tooling repo is stale
`~/Projects/mindfulnest-tooling/Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md` is a one-time snapshot from `b582f44` and lags behind the Dropbox canonical. Resync at convenience (low priority).

## §8 Operational runbook

### §8.1 Run the v59 client locally
```bash
cd ~/Projects/mindfulnest-tooling/Production/tools/storyboard-v2
npm install                  # one-time
npm run build                # build dist
npm run dev                  # vite dev server
# In another terminal:
cd ~/Projects/mindfulnest-tooling
python3 Production/tools/production_server.py \
  --event-dir Production/Event_1 \
  --storyboard storyboard_v59_prod.html \
  --event-id Event_1
# Open http://localhost:5111
```

### §8.2 Run e2e tests locally
```bash
cd ~/Projects/mindfulnest-tooling
# Set env vars (Doppler exports as DIRECTUS_ADMIN_*; server needs bare DIRECTUS_*)
eval "$(doppler secrets download --project mindfulnest --config dev --no-file --format env)"
export DIRECTUS_EMAIL="$DIRECTUS_ADMIN_EMAIL"
export DIRECTUS_PASSWORD="$DIRECTUS_ADMIN_PASSWORD"
export PRODUCTION_SERVER_SINGLE_MACHINE=1
# Kill any running Event_1 dev server first (port 5111 conflict)
pkill -f "production_server.py.*Event_1"
# Run
cd Production/tools/storyboard-v2
npx playwright test
```

### §8.3 Add a new e2e spec to CI
1. Write spec at `Production/tools/storyboard-v2/e2e/<name>.spec.ts`
2. Edit `.github/workflows/playwright_e2e.yml` line ~95 (the `npx playwright test` command)
3. APPEND the new spec file to the explicit list (NOT replace, NOT use a glob)
4. Update workflow header comment with new file in the per-session inclusion list
5. Commit + push → CI verifies

### §8.4 Check spec count vs maintainability threshold
```bash
cd ~/Projects/mindfulnest-tooling/Production/tools/storyboard-v2
ls e2e/*.spec.ts | wc -l
```
If >15, migrate to Playwright project/tag-based grouping per S5.5g §19.6.1.

### §8.5 Verify mutation channel invariant grep gate
```bash
cd ~/Projects/mindfulnest-tooling
bash Production/scripts/verify_mutation_channel_invariant_gate.sh
# Expected: "G13 PASS"
```

### §8.6 Reset Event_1/Event_2 from contamination
The fixture pinning rule (proper-fix §17) prevents tests from mutating live event data. If a test pollution incident still occurs:
```bash
cd ~/Projects/mindfulnest-tooling
git checkout Production/Event_1/production_state.json  # restore from HEAD
# OR pull from Dropbox if HEAD is also dirty
cp "<dropbox>/Production/Event_1/production_state.json" Production/Event_1/
```

## §9 References

- **Specs (Dropbox `Production/docs/`):**
  - `STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md` — v3 architecture revision
  - `STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md` — session table + cross-cuts
  - `STORYBOARD_V59_S5_5_C_SPEC_v2.md` + `_E_SPEC_v1.md` — Beat Generator + Storyboard buttons
  - `STORYBOARD_V59_S5_5_CE_PROPER_FIX_SPEC_v1.md` — proper-fix (PR #1)
  - `STORYBOARD_V59_RETROACTIVE_COVERAGE_SPEC_v1.md` — retroactive sprint v1 (PR #2)
  - `STORYBOARD_V59_S5_5_F_SPEC_v1.md` — Phase A/B parity (PR #3)
  - `STORYBOARD_V59_ARCHITECTURAL_FIX_SPEC_v1.md` — Wave 1 (PR #4)
  - `STORYBOARD_V59_S5_5_G_SPEC_v1.md` — Stitcher final assembly (in flight Phase A complete)
  - `STORYBOARD_V59_COMPREHENSIVE_RETROACTIVE_COVERAGE_PLAN_v1.md` — 6-wave program plan
  - `STORYBOARD_V59_DEFERRED_RETROACTIVE_COVERAGE_BACKLOG.md` — what's queued + triggers
  - `MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_SPEC_v1.md` — app foundation discipline
- **Master tech spec (Dropbox root):** `MINDFULNEST_MASTER_TECHNICAL_SPEC_v6.md`
- **Lessons learned (companion):** `STORYBOARD_V59_LESSONS_LEARNED_v1.md`
- **Schema reference:** `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md`
- **CLAUDE.md** (project root) — Rules 19, 26, 29, 35, 36 most relevant
- **Auto-memory:** `.auto-memory/MEMORY.md` index → per-session digests

## §10 Post-S5.5g delta (FEATURE-COMPLETE state as of 2026-05-04 22:38 UTC)

S5.5g shipped via PR #5 squash-merged as `d11e573` on `kimhyla/mindfulnest-tooling`. v59 client is now FEATURE-COMPLETE. This section captures the deltas from §1-§9 above.

### §10.1 New components (S5.5g)

Three new TSX components in `src/components/`:

- **`StitcherSlotWaveform.tsx`** — per-slot mini-waveform inside StitcherTab. Drag SFX tile from LibraryPanel → drop on slot waveform at time X → cue created at offset_ms = drop_x / width × video_dur_ms. Click cue marker → `SfxCuePopover` opens.
- **`SfxCuePopover.tsx`** — cue inspector for SFX cues (volume / fadein_ms / fadeout_ms / Delete). Reuses CuePopover pattern from S5.5f for watercolor cues; same UI shape, different persistence target (`slot.sfx_cues` for per-slot, `state.module_sfx_cues` for module-level).
- **`StitcherTransitionSelector.tsx`** — per-boundary transition selector with explicit `kind: "crossfade" | "cut" | "dissolve"` (Q3 LOCKED) + `audio_xfade_ms` field (Q1 LOCKED — supports BOTH visual-only AND visual+audio dissolve). Renders between adjacent slot pairs.

### §10.2 New endpoint (S5.5g)

`MUTATION_ENDPOINTS` extended in `src/api/endpoints.ts`:

- **`timeline_cue_upsert`** → POST `/api/timeline/cues` (used by both per-slot SFX cues and module-level cues; routes through `pathappPatch` with auto-injected scope keys)

### §10.3 Server changes (S5.5g)

`production_server.py` gained:

- **`_stitch_apply_dissolve_tail` + `_stitch_apply_dissolve_head`** helpers — apply ffmpeg `fade=t=out:st=...:d=fade_ms/1000` to tail of slot[N] + `fade=t=in:st=0:d=fade_ms/1000` to head of slot[N+1]; if `audio_xfade_ms > 0`, also apply `afade` audio crossfade. If `audio_xfade_ms == 0`, pure visual fadeblack with hard audio cut. Implements LD-376 fadeblack pattern at the boundary level.
- **`_stitch_normalize_slot` extended** — accepts `trim_in_ms` / `trim_out_ms` in stitch_save_job body; pre-trims each slot via ffmpeg `-ss` / `-t` BEFORE concat; cache key includes trim fingerprint so re-bake re-uses cached trims when unchanged.
- **`_handle_production_map` fix at `:8537`** — convention-based `Event_{m_num}` mapping (e.g., M5 → `Event_5/`) replaces the previous `event_dirs[0]` always-Event_1 bug. M-modules now navigate to their correct event scope.

### §10.4 Test count update

Post-S5.5g, the e2e suite runs **91+ tests across 10 spec files** (was 81 tests / 9 specs post-Wave-1):

- Existing 9 specs (s5_5ce_proper_fix, retroactive_s1-s6, s5_5f_smoke, architectural_fix) — unchanged
- NEW: **`s5_5g_smoke.spec.ts`** (G3-G13 functional behavior gates per §19.2.1 canonical numbering) — ~10 tests covering SFX cue placement (G3-G6), transitions (G7-G8), trims (G9-G10), Production Map (G12-G13), grep gate verify (G14)

CI workflow extended per §19.6 — APPEND, no glob. Spec count = 10; well under §19.6.1 maintainability threshold of 15. When count exceeds 15, migrate to Playwright project/tag-based grouping.

### §10.5 LDs added (S5.5g)

6 NEW LDs landed in `prod_locked_decisions`:

- LD-523 `STITCHER_SFX_CUE_UI_V1` (HARD)
- LD-524 `STITCHER_TRANSITIONS_V1` (HARD)
- LD-525 `STITCHER_PER_SLOT_TRIMS_V1` (HARD)
- LD-526 `STITCHER_RAW_FETCH_MIGRATED_V1` (HARD; verified clean post-Wave-1)
- LD-527 `PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1` (SOFT)
- LD-528 `V59_CLIENT_FEATURE_COMPLETE_V1` (HARD; closure LD)

Cumulative LD count from this weekend (505-528): **24 NEW LDs** codifying tooling repo + proper-fix + retroactive + S5.5f + Wave 1 + S5.5g + foundation discipline + skill update.

### §10.6 /stitch_editor retirement clock — STARTED

Per §19.11.1 retirement metric, the clock starts on PR #5 merge (2026-05-04 22:38 UTC). Audit cadence:

- **Day 1-14:** daily `prod_activity_log` row `STITCH_EDITOR_RETIREMENT_METRIC_DAY_<N>` capturing zero-hits in server logs + zero unblocker reports + zero open blockers. Continued zero across all 14 days → Day 15 deprecation.
- **Day 15:** mark `/stitch_editor` route handlers as DEPRECATED (return HTTP 410 Gone with redirect message to v59 Stitcher tab).
- **Day 16-44:** continued zero-criteria observation.
- **Day 45:** if zero-hits continued, DELETE the `/stitch_editor` route handlers + supporting code. Write LD `STITCH_EDITOR_RETIRED_V1` (HARD) capturing the audit chain.
- **Reset on use:** if any criterion fails (one hit, one unblocker, one open blocker referencing `/stitch_editor` as workaround), reset N counter to 0 and continue running v59 in parallel.

### §10.7 Known limitations carried forward

- **Phase E test coverage gap (LL-41):** route-level mocking in e2e tests does NOT exercise server-side `_handle_production_map` logic. Sprint E (server audit) closes this.
- **4 prod_blockers #50-53 (event_load violations):** ProjectSelector × 2, EventSelector, ProductionMapTab raw `fetch()` to event_load. Sanctioned by Wave 1 grep gate allowlist; surface as warnings every CI run; deferred to Sprint D / Wave 3.
- **F14 transient flake observation:** single occurrence during S5.5g Phase B RED; treated as transient. Watch list — if recurs, diagnose root cause per DS-4.
- **Module-level SFX cue rendering + delete:** drop creates a module cue today; reading + deleting existing module cues from `state.module_sfx_cues` was not in S5.5g G6 scope. Scope-extension follow-up.
- **Visual scrubber for trims:** current UX is numeric inputs in seconds; spec mentioned drag handles, deferred per Cursor v8 Q9. UX polish.
- **`/api/phase_b/regen_audio` misnamed:** writes voice_stem files despite the name; Cursor v8 Q5 clarification. Renaming out of scope (would break existing integrations).

### §10.8 Forward direction

After /stitch_editor retires (Day 45+), the tooling repo's storyboard codebase is at its v1 stable state. Forward direction:

1. **Operational use** — Kim composes modules in v59 daily.
2. **Sprint D / Wave 3** — opportunistic per backlog triggers; closes blockers #50-53.
3. **Sprint E (server audit)** — recommended near-term; closes LL-41 server-side coverage gap.
4. **MindfulNest app foundation work per LD-518** — when Kim is ready to start app development. The 5 load-bearing pieces (CI from commit 1, test-with-feature, structural enforcement, schema contracts, observability) are codified + ready.

---

**End of Architecture Overview v1 (post-S5.5g feature-complete state).**

This document now captures the v59 storyboard tool as of `d11e573` (post-S5.5g merge — FEATURE-COMPLETE). Update post Sprint E / Sprint D ships if those land; update post-app-foundation work to reflect cross-tool architecture.
