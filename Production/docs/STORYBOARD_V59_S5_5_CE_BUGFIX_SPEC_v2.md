# Storyboard v59 — S5.5c+e Browser-Smoke Bugfix Spec v2 (Cursor v9 folded)

**Date:** 2026-05-03
**Supersedes:** `STORYBOARD_V59_S5_5_CE_BUGFIX_SPEC_v1.md` (kept as historical reference)
**Classification:** EXECUTION SPEC — bugfix bundle for issues caught by Kim's hands-on browser smoke after S5.5c+e shipped, post Cursor v9 review
**Predecessor:** S5.5c+e (commits `bc12a4d` + `9efaabd`; 31/31 server-side gates green)
**Why v2:** Cursor v9 caught that R4 in v1 was based on a false premise (assumed parser bug; actual issue is data policy). Plus 8 mechanical amendments. Plus 1 release-blocker on LD wording.
**Master overview:** `STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md`

## §1 Task

Fix 4 distinct integration bugs from S5.5c+e + 1 data-policy clarification (was R4) + 1 small feature addition (+ New Event UI + ~30-line server endpoint). 6 things, ~10-12 hours of bounded work in one session.

NONE of these are architectural revisions. They are integration completions + a single data-policy decision Kim made.

## §2 Governing Decisions

### LDs respected

| LD | Reason |
|---|---|
| LD-456 / LD-460 / LD-461 | Standard scope + pin + body helper hygiene |
| LD-184 | Audio preview always-fresh from disk (R1 must not regress; R1 debounce mitigates re-fetch storm) |
| LD-421 / LD-422 | Asset registration via `registered_write.py` |
| LD-486 | Milestone independence (R1 milestone-load fix must respect) |
| LD-494 | TargetVideoSelector visibility per scope |
| `BEAT_GEN_3_OPTIONS_NOT_GRID_V1` (S5.5c) | UI is 1×3 NOT 3×3 — bugfix must not change |
| `UI_PRIMITIVES_SHARED_V1` (S5.5c) | AssetTile primitive used; bugfix EXTENDS its API per Cursor v9 Q3 |
| `DRAG_DROP_HELPER_V1` (S5.5c) | dragdrop.ts payload union exists; this bugfix wires it into components |
| `BEAT_LIFECYCLE_STATE_MACHINE_V1` (S5.5e) | R3 fix must not break |

### NEW LDs this spec writes (2)

| Key | Severity | Purpose |
|---|---|---|
| `S5_5CE_BROWSER_SMOKE_BUGFIX_V1` | MEDIUM | Records 4 integration bugs (R1, R2, R3, R5) caught by browser smoke + their fixes. Captures lesson: "scaffolded with `// future` comments + server-side gates only ≠ shipped." Process-smell fix is Playwright e2e on critical paths (gates H12 + H13). |
| `NEW_EVENT_CREATION_UI_V1` | MEDIUM | "+ New Event" UI flow + new server endpoint `_handle_event_create`. **Endpoint does NOT exist today** (verified by Cursor v9 grep against `production_server.py`); Phase G2 adds it (~30 lines). |

### NEW data policy (was "R4 fix" in v1; reframed per Cursor v9)

`PRODUCTION_MAP_TBD_HONEST_V1` — informational data-policy memo, not an LD:

- GAMEPLAY_SCOPE_v3.md does NOT enumerate per-module creature_name / video_role for arcs 2-9 (verified by Cursor v9 direct file read; arcs 2-9 are narrative summaries only).
- The populate script intentionally hardcodes `creature_name="TBD"` + `video_role="intro"` for M7-M54 by design (`populate_prod_modules_from_gameplay_scope.py:116-140`).
- **Decision (Kim 2026-05-03 post-Cursor-v9):** Show TBD honestly. Don't try to invent creature names or roles for unauthored modules. Production Map = V1 scope plan + authoring-progress checklist.
- M7-M54 stay as TBD until Kim authors each arc. When she does, EITHER she expands GAMEPLAY_SCOPE_v3.md AND re-runs populate, OR a future + New Event flow PATCHes prod_modules with real creature/role at event-creation time.
- This session adds a small UI note in Production Map explaining "TBD = not yet authored" so users (Kim later, terminal Claude in future sessions) understand the rows aren't a bug.

## §3 Approach

### Diagnosis confirmed via direct code inspection 2026-05-03 (Cursor v9 verified)

| Root cause | Evidence | Fix scope |
|---|---|---|
| **R1: Scope-change doesn't trigger UI re-fetch** | `BgTab.tsx:126-149` first-load effect deps `[arcNumber]` only — never `activeScope.value.event_id` / `activeTargetVideo.value` / `activeProjectType.value` / `activeMilestoneId.value`. Same pattern in `StoryboardTab.tsx:729-747` (deps `[refreshTick]` only). beatList recomputes from stale state when video changes (lines 760-793) but state was never refetched. Plus `+ New Milestone` Create button doesn't auto-call `/api/milestones/load`. | Effect dep arrays MUST include scope signals (Cursor v9 Q1 + R1-typo correction); add `/api/milestones/load` after Create returns; debounce refetch 200ms; trigger only on event_id/milestone/partition CHANGE not signal twitch. |
| **R2: Drag-drop never wired** | `LibraryPanel.tsx:6` literal comment: `"Tiles are also draggable so future drop"` — flagged as future, never finished. AssetTile primitive doesn't forward drag props. | Extend `AssetTile` API to forward `draggable` / `onDragStart` / `onDragEnd` / `data-testid` (Cursor v9 Q3); wire in LibraryPanel; add `onDrop` + `onDragOver` to BgTab beat option slots, char/BG ref slots, CropperModal canvas. Visual cue via `classList.toggle('is-drag-over')` (Cursor v9 Q4 — NOT invalid `[draghover]` selector). |
| **R3: bg_accept_option 400** | Server `_handle_bg_accept_option` expects `{beat_id, option_key}` (`production_server.py:9046`). `BgTab.tsx:293-296` already sends `option_key` correctly per Cursor v9. **Real failure mode:** if `opt.key` is missing/falsy, client's `BeatGenCard:597` only fires onAccept when truthy → button no-op (no error toast). The 400 toast Kim saw means an option WITHOUT key was somehow accepted. | Audit option construction path; ensure every option has `key` field at creation. Add gate H8.1: option without `key` → radio button DISABLED with tooltip; do not silently no-op. |
| **R4 (REFRAMED per Cursor v9): Data policy, not parser bug** | `populate_prod_modules_from_gameplay_scope.py:116-140` ALREADY hardcodes TBD + intro for M7-M54 by design. `GAMEPLAY_SCOPE_v3.md` doesn't enumerate per-module data for arcs 2-9. | NO populate script change. Add UI note in Production Map explaining TBD rows. Update `populate_prod_modules_from_gameplay_scope.py` `creature_name` placeholder from bare "TBD" to `"M{n} — TBD"` for slightly more friendly readability. NO 53-row PATCH. |
| **R5: Library thumbnails too big** | LibraryPanel CSS sizing makes 53 tiles need scrolling. Cursor v9 caught H10 ("all tiles visible") was unmeetable on 1280px viewport. | CSS: tile width ≤ 80px, library rail height = 600px, scroll allowed for overflow (measurable bounds, not "all visible"). |

### NEW: + New Event UI flow (Cursor v9 Q7 confirmed endpoint missing)

Cursor v9 grepped `production_server.py` — `_handle_event_create` and `/api/event/create` route do NOT exist. Phase G2 ADDS the server endpoint (~30 lines). Spec previously said "verify and add if missing" — now confirmed missing; this is locked in.

Server `_handle_event_create` adds:
- `POST /api/event/create` body `{event_id, event_label?}`
- Validates `event_id` regex `^[A-Z][A-Za-z0-9_]{2,63}$` (capital-leading by convention vs milestones lowercase)
- Reserved word check: cannot start with `Test_`, `_`, `Tmp_`
- Uniqueness: case-insensitive collision returns HTTP 409
- Creates `Production/Event_<id>/` directory + `production_state.json` scaffold via StateManager v3 seed (DON'T invent partial JSON; reuse `_init_files` v3 path)
- Wraps with `@with_pin_and_drain('event_create', track_sync=False)`
- Returns `{ok, event_id, event_dir}` or 409 on collision

Client wires:
- `ProjectSelector.tsx` "+ New Event" entry → Modal (S5.5c primitive) with regex-validated event_id input + label input.
- On Create success → auto-call `/api/event/load` with the new event_id (mirrors milestone fix in R1).

## §4 Implementation Phases

### Phase A — Pre-flight + diagnosis confirmation

**A1.** Read this spec + master overview + S5.5c v2 + S5.5e v1 + bugfix v1 (historical reference).

**A2.** `prod_preflight_reviews` row referencing S5.5c+e preflight #199 as predecessor.

**A3.** Confirm bug reproduction in browser smoke per `STORYBOARD_V59_S5_5_CE_HANDOFF.md` Notes-for-Kim section. Capture before-state.

**A4.** Inspect (Cursor v9 confirmed; spec lists for terminal-Claude continuity):
- `BgTab.tsx:126-149` — first-load effect dep array `[arcNumber]` ONLY
- `BgTab.tsx:152, 477` — other effect dep arrays
- `StoryboardTab.tsx:729-747` — fetch effect dep array `[refreshTick]` ONLY
- `LibraryPanel.tsx` — confirm zero `draggable` + zero `onDragStart`
- `BgTab.tsx:293-296` — confirm `option_key` body shape
- `BgTab.tsx:BeatGenCard:597` — `onAccept(opt.key)` truthy guard
- `production_server.py` — verify `_handle_event_create` ABSENT (Cursor v9 confirmed; this re-confirms)
- `playwright.config.ts:16-17` — confirm `baseURL: http://localhost:5111`, no `webServer:` config

### Phase B — R1 fix: scope-change re-fetch (with debounce)

**B1.** `BgTab.tsx` line 126-149 first-load effect: change deps to include scope signals via explicit `.value` reads inside the effect body AND in the deps array:
```typescript
useEffect(() => {
  const eventId = activeScope.value.event_id;
  const targetVideo = activeTargetVideo.value;
  const projectType = activeProjectType.value;
  const milestoneId = activeMilestoneId.value;
  const arcId = arcNumber;
  // ... fetch logic
}, [arcNumber, activeScope.value.event_id, activeTargetVideo.value, activeProjectType.value, activeMilestoneId.value]);
```

**B2.** Same pattern for `BgTab.tsx:152, 477` if those effects are scope-dependent.

**B3.** `StoryboardTab.tsx:729-747` — add scope signal `.value` reads to dep array. Bump `refreshTick` from a scope-watch effect (so existing `refreshTick` semantics stay; just ensure the bump fires on scope change).

**B4.** **Debounce per Cursor v9 amendment:** wrap fetch dispatch in 200ms debounce so rapid signal twitches (e.g., user dragging dropdown) don't fire multiple fetches. Use `setTimeout` cleared on cleanup OR a small `useDebouncedValue` helper.

**B5.** **Refetch trigger filter:** only refetch when `event_id` / `milestone_id` / `partition_key (target video)` actually CHANGES. Compare prev value via `useRef`; skip refetch if all equal.

**B6.** `ProjectSelector.tsx` — after `+ New Milestone` Create POST returns ok: auto-call `/api/milestones/load` with the new id; await success. UI scope updates via R1's effect-deps fix.

**B7.** Same auto-load pattern for + New Event (Phase G).

### Phase C — R2 fix: drag-drop wiring (AssetTile API extension)

**C1.** `src/components/ui/AssetTile.tsx` — extend props interface to include:
```typescript
interface AssetTileProps {
  // existing props...
  draggable?: boolean;
  onDragStart?: (e: DragEvent) => void;
  onDragEnd?: (e: DragEvent) => void;
  'data-testid'?: string;
  // ... or accept {...rest} pass-through to outer div
}
```

**C2.** `LibraryPanel.tsx` — render each library item via `<AssetTile draggable={true} onDragStart={(e) => setDragData(e, {kind: 'lib-image', lib_key: it.key, tier: it.tier})} data-testid={`library-tile-${it.key}`}>`. Use `dragdrop.ts` payload helper.

**C3.** `BgTab.tsx` beat option slots (3 per beat) — add drop handlers:
```typescript
onDragOver={(e) => { e.preventDefault(); (e.currentTarget as HTMLElement).classList.add('is-drag-over'); }}
onDragLeave={(e) => (e.currentTarget as HTMLElement).classList.remove('is-drag-over')}
onDrop={async (e) => {
  e.preventDefault();
  (e.currentTarget as HTMLElement).classList.remove('is-drag-over');
  const payload = getDragData(e);
  if (payload?.kind !== 'lib-image') return;
  // Server contract per production_server.py:9082-9097 (Cursor v10 corrected):
  // expects { beat_id, key, filename, abs_path, slot_index }
  // Map drag payload's `lib_key` → server's `key`; resolve filename + abs_path
  // from library metadata (existing pattern in LibraryPanel response shape);
  // slot_index is which option slot (0/1/2) the user dropped onto.
  const lib_meta = libItemByKey(payload.lib_key); // existing helper from LibraryPanel
  await pathappPatch(activeScope.value, 'bg_accept_lib_image', {
    beat_id,
    key: payload.lib_key,
    filename: lib_meta.filename,
    abs_path: lib_meta.abs_path,
    slot_index: option_slot_index, // 0/1/2 for option slots
  });
}}
```
(Server expects `{key, filename, abs_path, slot_index}` per `production_server.py:9083+`; verify exact field names in Phase A audit + match.)

**C4.** `BgTab.tsx` char ref + BG ref slots — same drop handler pattern; calls `bg_update_beat` with `{char_ref_key}` or `{bg_ref_key}` (verify field names).

**C5.** `CropperModal.tsx` — add drop target on canvas area. On drop with `kind: 'lib-image'`, set source image from library URL + load into canvas.

**C6.** CSS scoped: `.mn-drop-target.is-drag-over { outline: 2px dashed var(--accent); background: var(--accent-bg-light); }` — proper class-based, not invalid `[draghover]` attribute selector (Cursor v9 Q4).

**C7.** Verify dragdrop.ts payload helper handles all 3 payload kinds (lib-image, lib-watercolor — used in S5.5f, lib-sfx — used in S5.5g; this session only wires lib-image).

### Phase D — R3 fix: option_key validation

**D1.** Audit BgTab option construction (where do `phase_1.options[i]` objects come from? GPT batch result, sidecar, etc.). Verify `key` field is always populated.

**D2.** If `key` field missing on some option paths: trace upstream. Either:
- Server doesn't set it (server-side fix needed; surface to Kim if so)
- Client constructs option object client-side without setting it (client-side fix; set deterministic key at construction)

**D3.** Add gate per Cursor v9 Q5: BeatGenCard radio button DISABLED if `opt.key` falsy + tooltip "Option missing key — regenerate beat". Don't silently no-op.

**D4.** Test: click radio on every option in a beat → POST returns 200 → option marked selected → no Lock failed toast.

### Phase E — R4 (data policy, not code fix)

**E1.** Update `populate_prod_modules_from_gameplay_scope.py` placeholder for arcs 2-9 modules:
- `creature_name`: `"M{n} — TBD"` instead of bare `"TBD"`
- `video_role`: stays `"intro"` (default for unauthored)
- Add comment block in script explaining this is intentional per `PRODUCTION_MAP_TBD_HONEST_V1` policy

**E2.** Re-run script `--apply` (PATCHes M7-M54 creature_name to friendlier label only; M1-M6 unchanged; total ~48 PATCHes).

**E3.** `ProductionMapTab.tsx` — add UI note above table:
```
M7-M54 are V1 scope placeholders — author them by creating an Event for each module.
Once authored, run populate script to update creature_name from the doc.
```

**E4.** No 53-row creature_name PATCH. No `_handle_production_map` change. Multi-event mapping fix STAYS deferred to S5.5g.

### Phase F — R5 fix: library thumbnail sizing (measurable bounds per Cursor v9)

**F1.** `src/index.css` (or LibraryPanel-scoped CSS) — define CSS variables:
- `--ui-library-tile-size: 80px` (max tile width)
- `--ui-library-rail-height: 600px` (max rail height; scroll for overflow)

**F2.** `LibraryPanel.tsx` — apply variables to tile and container.

**F3.** Verify on 1280px viewport: tile width ≤ 80px; rail height = 600px; scroll appears when tile count exceeds visible.

### Phase G — + New Event UI (server + client)

**G1.** Verify endpoint absent (Cursor v9 confirmed; re-confirm in case latest commit added it).

**G2.** Add `_handle_event_create` to `production_server.py` (~30 lines):
- Route at `/api/event/create`
- Validates regex `^[A-Z][A-Za-z0-9_]{2,63}$`
- Reserved word check
- Case-insensitive uniqueness check vs existing `Production/Event_*` dirs
- Creates dir + state.json via `StateManager._init_files` v3 path (DO NOT invent partial JSON)
- `@with_pin_and_drain('event_create', track_sync=False)` (server-side Python decorator, not TS)
- Returns `{ok, event_id, event_dir}` or 409

**G3.** `ProjectSelector.tsx` — add "+ New Event" entry; on click, opens Modal (S5.5c primitive).

**G4.** Modal: regex-validated `event_id` input + optional `event_label`.

**G5.** On Create success: auto-call `/api/event/load` with new id (mirrors R1 milestone-load fix).

**G6.** Verify: + New Event opens modal → enter `Event_3` → Create → server creates dir + state.json → UI loads new scope → empty intro/resolution partitions visible.

### Phase H — Verification (14 gates per Cursor v9 amendments)

**H1.** `npm run build` clean.
**H2.** Server `/api/health` 200; PID start time AFTER server edits (Rule 29).
**H3.** **R1 probe:** switch Video from intro to resolution on Event_2 → beats list clears (resolution is empty). Switch back to Event_1 intro → 17 beats reappear.
**H4.** **R1 probe:** + New Milestone Create → UI auto-loads milestone scope; scope chip shows milestone id.
**H5.** **R2 probe:** drag library tile → drop on beat option slot → POST `bg_accept_lib_image` → option set; visual `is-drag-over` cue appeared during drag.
**H6.** **R2 probe:** drag library tile → drop on char ref slot → ref set.
**H7.** **R2 probe:** open Cropper → drag library tile onto canvas → image loads as source.
**H8.** **R3 probe:** click radio on a beat option → POST `bg_accept_option` returns 200; no Lock failed toast.
**H8.1.** **(NEW per Cursor v9 Q5)** Synthesize a beat option with falsy `key`; verify radio button is DISABLED with tooltip; no silent no-op.
**H9.** **R4 probe:** Production Map shows M7-M54 as `M{n} — TBD` (friendlier than bare TBD); UI note explains "TBD = not yet authored." NO 53 creature_name PATCHes.
**H10.** **(REWORKED per Cursor v9)** Library tiles ≤ 80px width; rail height = 600px on 1280px viewport. Scroll allowed for overflow.
**H11.** **+ New Event probe:** + New Event modal opens; reserved-word `Test_X` rejected; valid `Event_3` accepted; Create → server creates Event_3/ + v3-shape state.json; UI auto-loads.
**H12.** **Playwright bugfix smoke:** write `e2e/s5_5ce_bugfix_smoke.spec.ts` covering H3, H5, H8, H8.1, H9, H11. Configure `playwright.config.ts` `webServer:` field per Cursor v10 canonical path: spawn `python3 Production/tools/production_server.py --event-dir Production/Event_1 --storyboard storyboard_v59_prod.html --event-id Event_1` on port 5111 BEFORE running tests. The dist/ static is built via `npm run build` as a separate pre-test step (NOT a Vite dev server — avoid port conflicts with 5111). Tests load `http://localhost:5111/storyboard-v2/` IF the server serves it, OR via `file://...dist/index.html` IF that's the working path (verify in Phase A based on which routes Kim's been using). `cd Production/tools/storyboard-v2 && npm run build && npx playwright test e2e/s5_5ce_bugfix_smoke.spec.ts` exits 0.
**H13.** **(NEW per Cursor v9 Q9)** Subset regression of S5.5c+e gates: `npm run build` clean (already H1; this gate confirms STILL clean post-fix), `python3 -m py_compile Production/tools/production_server.py` clean, `populate_prod_modules_from_gameplay_scope.py --validate` exit 0. Doesn't replicate all 31 gates but covers the build/compile invariants that would catch most regressions.
**H14.** Tail-end verifier subagent — focused on regression check (none of S5.5c+e's 31 originally-passing gates are now broken).

### Phase I — LD writes

**I1.** Write 2 NEW LDs: `S5_5CE_BROWSER_SMOKE_BUGFIX_V1`, `NEW_EVENT_CREATION_UI_V1`.

### Phase J — Closeout

**J1.** `prod_activity_log` row `S5_5CE_BUGFIX_COMPLETE` with full 14-gate summary + the 5 root-cause diagnosis (R1, R2, R3, R4 reframed, R5).

**J2.** Update master overview status table with bugfix-shipped note.

**J3.** Tail-end verifier subagent (H14).

**J4.** Git commit: `S5.5c+e bugfix v2 — scope refresh + drag-drop + accept-option key + populate friendlier TBD + thumbnails + New Event UI + server endpoint (14 gates green; Cursor v9 reviewed)`.

## §5 Files Created / Modified

### Created
- `Production/tools/storyboard-v2/e2e/s5_5ce_bugfix_smoke.spec.ts` (Playwright tests for H12)

### Modified
- `Production/tools/storyboard-v2/src/components/ui/AssetTile.tsx` (drag prop forwarding API)
- `Production/tools/storyboard-v2/src/components/LibraryPanel.tsx` (drag handlers via AssetTile)
- `Production/tools/storyboard-v2/src/components/BgTab.tsx` (effect deps + drop handlers + option_key gate)
- `Production/tools/storyboard-v2/src/components/StoryboardTab.tsx` (effect deps)
- `Production/tools/storyboard-v2/src/components/CropperModal.tsx` (drop target + source from library)
- `Production/tools/storyboard-v2/src/components/ProjectSelector.tsx` (auto-load milestone after Create + + New Event entry)
- `Production/tools/storyboard-v2/src/components/ProductionMapTab.tsx` (UI note about TBD policy)
- `Production/tools/storyboard-v2/src/index.css` (drop-target classes + library tile sizing variables)
- `Production/tools/storyboard-v2/playwright.config.ts` (webServer config OR STORYBOARD_BASE_URL env var support)
- `Production/scripts/populate_prod_modules_from_gameplay_scope.py` (placeholder cosmetic fix only — `"M{n} — TBD"`)
- `Production/tools/production_server.py` (~30 lines: `_handle_event_create` per Phase G2)

### Modified (Directus)
- `prod_modules`: 48 cosmetic PATCHes (M7-M54 `creature_name` from `"TBD"` to `"M{n} — TBD"`); NO video_role changes; NO creature_name guesses

## §6 Directus Writes

- `prod_locked_decisions`: 2 NEW LDs
- `prod_modules`: ~48 cosmetic PATCHes (M7-M54)
- `prod_activity_log`: phase rows + COMPLETE
- `prod_preflight_reviews`: 1 row at session start

## §7 Error Cases

| Failure | Handling |
|---|---|
| `_handle_event_create` server addition exceeds 50 lines (out of scope) | Surface to Kim before adding; defer + New Event to a separate session if scope balloons |
| R1 fix surfaces deeper signal-architecture issue | STOP; this would be the architectural smell described to Kim. Surface for rethink. |
| R2 drag-drop breaks Safari (different dataTransfer behavior) | Document; require Chromium for now; add to S5.5f/g browser matrix |
| R3 fix reveals option_key not always set by server | Server-side fix needed; surface as scope expansion; H8.1 catches via UI gate but root issue is upstream |
| R4 cosmetic PATCH fails (Directus PATCH_ALLOWED restriction) | NO action needed: `creature_name` already in `PATCH_ALLOWED` (`populate_prod_modules_from_gameplay_scope.py:164`). Cursor v10 verified. |
| Playwright H12 can't run (server not started, dev server config wrong) | Phase H configures `webServer:`; if still broken, fall back to documented manual `npm run dev` + `npx playwright test` chain in Phase H notes |
| H13 regression catches a broken S5.5c+e gate | STOP; root-cause the regression before shipping bugfix; this means the bugfix itself broke something |

## §8 Verification

Done when 14 gates green + 2 LDs + 48 cosmetic PATCHes + Playwright passing + browser smoke 7 steps green per `STORYBOARD_V59_S5_5_CE_HANDOFF.md`.

## §9 Rollback

- Client fixes: `git checkout -- src/components/`, `src/index.css`, `playwright.config.ts`
- Populate script cosmetic fix: re-run with original placeholder OR PATCH 48 rows back to bare "TBD" via Directus
- Server endpoint added: `git checkout -- production_server.py`; PATCH any created Event_<N>/ dir to /tmp or delete (manual cleanup)
- LDs: PATCH to `status='superseded'`

## §10 Out of Scope (defer)

- Production Map multi-event mapping (deferred to S5.5g per spec)
- Voice profile UI (S6)
- Phase A/B feature parity (S5.5f)
- Stitcher SFX/transitions/trims (S5.5g)
- Drag-drop on Safari (Chromium-only this session)
- "+ New Module" UI concept — events are the granularity per V1 scope; New Event covers the use case
- **Authoring per-module data for arcs 2-9** (creature names, roles, stones) — this is content authoring work, not a code task; happens organically as Kim authors each arc
- **Server-side option_key construction fix** if root cause is server (defer to follow-up; H8.1 client-side gate catches symptom)

## §11 Dependencies

**On v3:** state shape, scope signals, pathappPatch, Modal/Toast/Spinner/AssetTile/dragdrop primitives.
**On S5.5c+e:** all of it. This is the bugfix.
**On Cursor v9 review:** spec was REVISE-BEFORE-SHIP; this v2 folds findings.

## §12 Notes for the Executing Session

- **PRIORITY: R1 first.** All other bugs are easier to test once scope-refresh works. R3 in particular may LOOK fixed in a stale-scope view — re-test after R1 ships.
- **Cursor v9 caught the spec's R4 was wrong.** v1 said "fix the parser"; v2 reframes as data policy. Don't try to populate creature names for arcs 2-9 — that data isn't in the doc.
- **The "future drop" comment in LibraryPanel.tsx:6** is the smoking gun for R2. Spec said drag-drop was wired; comment in committed code says "future." Process smell named honestly per Cursor v9 Q10.
- **Don't expand scope.** Cursor v9 reviewed v1 for completeness; if a deeper bug surfaces beyond the 5 root causes, surface to Kim. Don't quietly add fix #6.
- **+ New Event** server endpoint genuinely doesn't exist (Cursor v9 verified). Phase G2 ADDS it — this is acknowledged scope, not "investigate then maybe add."
- **Playwright `webServer:` config is mandatory** per Cursor v9 Q8; tests can't run against unstarted server. Use `npm run dev` (Vite preview) OR document env var bypass.
- **H10 reworked** per Cursor v9 — measurable bounds (tile ≤ 80px, rail = 600px) not "all visible."
- **R1 debounce 200ms** prevents fetch storm on rapid scope twitches per Cursor v9 amendment.
- **H8.1 option_key gate** prevents the silent no-op failure mode Cursor v9 surfaced.
- **H13 regression gate** is partial (build + compile + script validate); not full S5.5c+e re-run but catches most regressions.
- Per Rule 29: server staleness check before any "test it now" if production_server.py modified.
- Per Rule 35: every Directus write via try_post_or_queue with read-back.
- Per Rule 19: no shortcuts.

## §13 Cursor v10 Review Checklist (focused; mostly verifies v9 fixes landed)

Send Cursor v10 this v2 spec + the following 8 questions:

1. R1 effect-deps fix (§4 B1-B5): is the explicit `.value` reads + dep array pattern correct for Preact signals? Or should we use `useSignalEffect` from `@preact/signals` directly?

2. R1 debounce 200ms (§4 B4): is 200ms the right window, or should it be longer for cross-event swap (which legitimately takes longer to render)?

3. R2 AssetTile API extension (§4 C1): is `{...rest}` pass-through cleaner than explicit prop forwarding, given strict TS `exactOptionalPropertyTypes`?

4. R2 drop handler bg_accept_lib_image body shape (§4 C3): server expects `{key, filename, abs_path, slot_index}` per `production_server.py:9083+` — verify our payload construction matches exactly.

5. R3 H8.1 option_key gate (§4 D3): tooltip "Option missing key — regenerate beat" — is this the right UX, or should we hide the option entirely?

6. R4 cosmetic PATCH: Cursor v10 verified `creature_name` already in PATCH_ALLOWED. No allowlist change needed.

7. + New Event server endpoint (§4 G2): regex `^[A-Z][A-Za-z0-9_]{2,63}$` aligns with existing `Event_1` / `Event_2` pattern. Reserved words list (`Test_`, `_`, `Tmp_`) — anything else to add?

8. Playwright `webServer:` config (§4 H12): `npm run dev` is Vite preview at default port; does that conflict with our 5111 production_server.py? Is there a clean way to spin up BOTH for the e2e tests, or should tests assume server is running externally?

Append findings as §15.

---

## §14 Cursor v9 findings folded into v2 (audit trail)

| Finding | Resolution in v2 |
|---|---|
| Q1 R1 useEffect vs Preact signals pattern | §4 B1-B5: explicit `.value` reads in dep arrays + signals listed; debounce 200ms; refetch only on event_id/milestone CHANGE |
| Q2 milestone create auto-load (client vs fused API) | §4 B6: client auto-call after Create returns (preferred) |
| Q3 AssetTile API extension | §4 C1: forward draggable/onDragStart/onDragEnd/data-testid |
| Q4 drag-hover styling | §4 C6: `classList.toggle('is-drag-over')` + scoped CSS class — NOT invalid `[draghover]` selector |
| Q5 option_key residual failure mode | §4 D3 + H8.1: gate option must have key before accept enabled; tooltip if missing |
| Q6 GAMEPLAY_SCOPE_v3.md format report | R4 REFRAMED — doc doesn't have per-module data for arcs 2-9; cosmetic fix only |
| Q7 _handle_event_create absent | LD `NEW_EVENT_CREATION_UI_V1` no longer claims endpoint exists; Phase G2 ADDS it explicitly |
| Q8 Playwright webServer config | §4 H12: webServer config required OR documented STORYBOARD_BASE_URL env var |
| Q9 12 gates not enough; need regression | §4 H13 NEW: subset regression of build + compile + script validate |
| Q10 architectural smell honest answer | Documented in §3 R4 reframe + §12 notes: "process smell — 'future' comments + server-only gates" addressed via H12+H13 Playwright/CI coverage |
| Beyond §13 §3 R1 typo "must NOT include" | §3 R1 row corrected to "currently omit; MUST include" |
| Beyond §13 LD wording false claim | LD wording fixed; endpoint absence acknowledged |
| Beyond §13 R4 diagnosis wrong | R4 entirely reframed as data policy decision |
| Beyond §13 H10 unmeetable | H10 reworked to measurable bounds |
| Beyond §13 R1 refetch debouncing | §4 B4: 200ms debounce + change-only trigger |

---

## §15 Cursor v10 findings folded (audit trail)

| Finding | Resolution |
|---|---|
| RELEASE-BLOCKER: `colloquial_name` field name was wrong | FIXED — global find/replace to `creature_name` per `populate_prod_modules_from_gameplay_scope.py:164` PATCH_ALLOWED + `ProductionMapTab.tsx:25-26,105` rendering |
| RELEASE-BLOCKER: §4 C3 drag-drop body shape wrong | FIXED — rewrote to match server contract `{beat_id, key, filename, abs_path, slot_index}` per `production_server.py:9082-9097` |
| §7 error row about PATCH_ALLOWED | UPDATED — `creature_name` already in PATCH_ALLOWED; no allowlist change needed |
| Q6 review question about PATCH_ALLOWED | UPDATED — Cursor v10 verified |
| H12 Playwright bootstrap (Vite vs 5111 port conflict risk) | FIXED — canonical path: spawn production_server.py on 5111 + `npm run build` pre-test step; tests load via 5111 OR file:// (verify which route Kim uses). NO Vite dev server (avoids port conflicts). |
| Q1 R1 useEffect deps + useSignalEffect | KEEP (already approved by v10 with note) |
| Q2 debounce 200ms | KEEP (approved with note: don't apply to explicit post-event/load-returned path) |
| Q3 AssetTile `{...rest}` vs explicit | KEEP (approved; either pattern works) |
| Q5 H8.1 disable + tooltip vs hide | KEEP (approved) |
| Q7 reserved words | OPTIONAL ADDITION — could add `archive`, `tmp`, `system` for parity with milestones; not blocking |
| Q10 process smell — Cursor's verdict | "Still no single architectural rot — remaining issue is spec↔code naming drift, exactly what H12/H13 + tighter snippets prevent. Fix the doc and ship." This v3 set of edits IS the fix-the-doc step. Process structural fix (Option 3 per Kim 2026-05-03) becomes a SEPARATE spec (CI Playwright + master overview + lessons-learned). |
| Beyond §13: gate count (14) | KEEP — Cursor confirmed proportionate |
| Beyond §13: TBD churn vs UI-note-only | DEFER decision to terminal; if Kim wants zero Directus churn, drop the 48 PATCHes and keep UI note only |

**Total v3 changes from v2:** 5 mechanical fixes (creature_name × 6 occurrences + drag-drop body + PATCH_ALLOWED note × 2 + Playwright bootstrap canonical path) + this §15 audit trail.

---

**End of S5.5c+e bugfix spec v2 (Cursor v10 fixes folded).**

This is now ready for terminal handoff. Cursor v10 verdict: REVISE BEFORE SHIP, blockers fixed in this revision. No v11 review needed unless substantive new edits are added.

The "process structural fix" Kim asked for (Option 3) is captured as a SEPARATE spec to be authored next: CI Playwright + master overview §6 amendment + lessons-learned LL entry. That spec depends on this bugfix's Playwright tests (H12) as initial CI coverage; ships AFTER bugfix.
