# Storyboard v59 — Post-Redeploy Bug-Fix Spec v1

**Date:** 2026-05-05
**Branch (target):** `claude/post-redeploy-bug-triage` (cut fresh; `claude/video-role-picker` parked)
**Source of bugs:** Browser smoke after redeploying fresh local build to Dropbox/Production/Event_<N>/storyboard_v59_prod.html
**Discipline:** zero-error-qa DS-1..DS-12; tooling-repo two-tree boundary (LD-505); tdd contract-first
**Cursor review:** REQUIRED before terminal handoff

---

## 0. Status of the three bugs

| ID    | Symptom                                                                                                                                                  | Severity | Root cause confirmed via                                                                                          | Fix surface                            |
|-------|----------------------------------------------------------------------------------------------------------------------------------------------------------|----------|-------------------------------------------------------------------------------------------------------------------|----------------------------------------|
| Bug A | Beat Generator "Segment" dropdown stays on prior event/phase after Event/Video scope changes via VideoSelector                                           | HARD     | `BgTab.tsx` useEffect depends on `arcNumber` only; not on `activeScope`/`activeVideoRole`                          | client (BgTab.tsx)                     |
| Bug B | Event_2 intro storyboard renders an unauthored beat (`beat_04`, "MindfulNest! Well don't you know? ...") even though `display_order = []`                | HARD     | `StoryboardTab.tsx:765-775`: when `display_order` is `[]`, falls through to `Object.entries(beats)` (renders all) | client (StoryboardTab.tsx) + data hygiene |
| Bug C | Production Map shows uniform Role=intro and identical counts (Phase A=14, Phase B=1, Storyboard=36, Final concat=0) for ALL M1..M59 rows                 | HARD     | `production_server.py:8429-8472`: `edir = event_dirs[0]` always — every row globs Event_1 only                    | server (production_server.py)          |

Plus two SOFT items folded in:
- **Bug D (CSS):** `.mn-video-selector` has no styling; selector renders raw next to `.mn-event-selector` and looks ugly
- **Bug E (process LD):** No documented "redeploy SPA to Dropbox tree" step; code-merge ≠ user-visible release. Already cost ~1 day of misdiagnosis this weekend.

---

## 1. Bug A — Beat Generator "Segment" dropdown sticky across scope changes

### 1.1 Reproduction

1. Load app at Event_1 / intro (default scope).
2. Switch to Beat Generator tab — observe Segment dropdown shows `event 1 pre — Intro`.
3. Switch event to Event_2 via EventSelector OR switch video via VideoSelector to `resolution`.
4. Switch back to Beat Generator tab.
5. **Observed:** Segment dropdown still shows `event 1 pre — Intro` (or whatever was selected pre-change). Editing/extracting beats here writes to the WRONG event.
6. **Expected:** Segment list re-fetches scoped to current event; default segment matches active scope.

### 1.2 Root cause

`Production/tools/storyboard-v2/src/components/BgTab.tsx`

```tsx
// Line 126-149 (current)
useEffect(() => {
  let cancelled = false;
  (async () => {
    setLoading(true);
    const segRes = await apiGet<BgSegmentsResponse>('bg_segments', { arc_number: String(arcNumber) });
    ...
    if (ctx) {
      setArcNumber(Number(ctx.arc_number) || arcNumber);
      setActiveSegment(`${ctx.event_id}|${ctx.phase}`);
    } else if (segs.length > 0) {
      setActiveSegment(`${segs[0].event_id}|${segs[0].phase}`);
    }
    ...
  })();
  return () => { cancelled = true; };
}, [arcNumber]);                       // <-- ONLY arcNumber; missing scope deps
```

Dependency array is `[arcNumber]`. When `activeScope` or `activeVideoRole` change, the effect does NOT re-run, so `activeSegment` keeps its stale value. The cross-event-edit risk is real because all `pathappPatch(activeScope.value, 'bg_*', { event_id, phase })` calls below pass `event_id` derived from `activeSegment`.

### 1.3 Fix (minimal diff)

```tsx
import { activeScope, activeVideoRole, scopeKey } from '../state/scope';
// ...

// Subscribe the load effect to scope changes too:
const scopeKeyVal = scopeKey(activeScope.value);
const videoRoleVal = activeVideoRole.value;

useEffect(() => {
  let cancelled = false;
  (async () => {
    setLoading(true);
    const segRes = await apiGet<BgSegmentsResponse>(
      'bg_segments', { arc_number: String(arcNumber) }
    );
    if (cancelled) return;
    const segs = segRes.data?.segments ?? [];
    setSegments(segs);

    const stateRes = await apiGet<BgSessionState>('bg_session_state');
    if (cancelled) return;
    const ctx = stateRes.data?.active_context;
    if (ctx) {
      setArcNumber(Number(ctx.arc_number) || arcNumber);
      setActiveSegment(`${ctx.event_id}|${ctx.phase}`);
    } else if (segs.length > 0) {
      setActiveSegment(`${segs[0].event_id}|${segs[0].phase}`);
    }
    setBeats(stateRes.data?.beats ?? []);
    setLoading(false);
  })();
  return () => { cancelled = true; };
}, [arcNumber, scopeKeyVal, videoRoleVal]);   // <-- add scope dependency
```

### 1.4 Test plan (DS-1 contract-first)

- **Unit:** `BgTab.spec.tsx` — mount with scope `M1E1/intro`, capture activeSegment; mutate `activeScope.value` to `M2E1/resolution`, assert effect re-fires and activeSegment resets to scoped value (use `vi.fn()` mocks for `apiGet`).
- **e2e:** `storyboard-v59-bg-scope-sync.spec.ts` — load Event_1, change to Event_2 via EventSelector, switch tab to Beat Generator, assert Segment dropdown reflects Event_2's segments; submit a `bg_extract_beats` and assert request body carries `event_id=2`.
- **Regression:** existing `bg-tab.spec.ts` tests unchanged (arc-number-only re-fetch path still works because dep array still includes arcNumber).

### 1.5 Open question (Cursor review)

`bg_session_state` server endpoint stores `active_context` ONCE per server process, NOT per scope. After Bug A is fixed in client, server may also need to scope `active_context` per `(event_id, video_role)` so two concurrent events don't collide. **Option:** patch in this spec (extends fix) OR defer to follow-up. Default: defer; flag at end of spec. Cursor please confirm.

---

## 2. Bug B — Event_2 intro renders unauthored beat_04 (display_order fallthrough)

### 2.1 Reproduction

1. Load app at Event_2 / intro.
2. Storyboard tab shows 1 beat: `beat_04` "The MindfulNest! ... Well don't you know? ..."
3. Kim confirms she did NOT author this beat in v59. Likely arrived via:
   - Failed "Accept all beats from generator" attempt, or
   - Pre-v3-migration cross-event leak (Kim recalls "in the previous storyboard version, the first beat of event 2 intro video populated into the first beat of event 1")
4. Pre-migration backup `Production/Event_2/.backups/state/20260503T140831Z_pre_videos_migration.json` already contains `beats.beat_04` with that exact text — so it predates weekend work and survived migration.
5. Current v3 state at `Production/Event_2/production_state.json`:
   ```json
   "videos": {
     "intro": {
       "beats": { "beat_04": { "text": "The MindfulNest! ..." } },
       "display_order": []
     }
   }
   ```
   `display_order` is empty `[]` but the beat persists in `beats{}`.

### 2.2 Root cause

`Production/tools/storyboard-v2/src/components/StoryboardTab.tsx:760-781`

```tsx
const beatList = useMemo(() => {
  if (!state) return [];
  const role = activeTargetVideo.value;
  const partition = state.videos?.[role];
  if (partition?.beats && Object.keys(partition.beats).length > 0) {
    const order = partition.display_order ?? [];
    if (order.length > 0) {
      return order
        .filter((bid) => partition.beats?.[bid])
        .map((beat_id) => ({ beat_id, ...partition.beats![beat_id] }));
    }
    // ⚠️ FALLTHROUGH: when display_order is [], renders ALL beats.
    return Object.entries(partition.beats)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([beat_id, b]) => ({ beat_id, ...b }));
  }
  ...
});
```

`display_order = []` falls through to render-all-keys-in-`beats`. Two semantically distinct situations collapse together:
- "I have never set display_order on this partition" (pre-migration legacy) — rendering all is the legacy fallback we want
- "I have explicitly emptied display_order; only `beats[]` rows exist as orphans/cache" (current Event_2 state) — rendering should show 0 beats

### 2.3 Fix (minimal diff, two-part)

**Part 1 — client renderer (StoryboardTab.tsx):** Distinguish "absent" vs "explicitly empty":

```tsx
if (partition?.beats && Object.keys(partition.beats).length > 0) {
  // Honor display_order strictly when it's present (even if []).
  // display_order == [] means "no beats to render"; only fall through to
  // Object.entries() when display_order is genuinely missing (undefined).
  if (partition.display_order !== undefined) {
    return partition.display_order
      .filter((bid) => partition.beats?.[bid])
      .map((beat_id) => ({ beat_id, ...partition.beats![beat_id] }));
  }
  // Legacy pre-display_order partitions: sorted by beat_id.
  return Object.entries(partition.beats)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([beat_id, b]) => ({ beat_id, ...b }));
}
```

This preserves backward compat (legacy state shapes with no `display_order` key keep working) while honoring explicit `[]` as "no beats".

**Part 2 — server hygiene (production_server.py):** When `display_order` is mutated, prune `beats{}` of any keys not in `display_order`. Prevents orphan accumulation in storage. (Cursor: confirm whether this should be lock-step in this fix or a follow-up; safer to do now.)

**Part 3 — one-shot data cleanup (script, not committed to repo flow):**

A migration script `Production/scripts/clean_orphan_beats_v3.py` to walk all `Production/Event_*/production_state.json` (and `Production/Milestones/*/state.json`) and remove `videos.<role>.beats[bid]` rows whose key is not in `videos.<role>.display_order`. Dry-run by default; `--apply` to commit. Atomic via `production_state` mutation channel. Logs orphans removed for audit.

### 2.4 Test plan (DS-1 + DS-7)

- **Unit:** `StoryboardTab.spec.tsx` — three cases: `display_order = ['beat_01','beat_02']` → 2 beats; `display_order = []` → 0 beats; `display_order = undefined` (legacy) → all beats sorted.
- **e2e:** `storyboard-v59-display-order-empty.spec.ts` — fixture with `beats: { beat_04: ... }, display_order: []` → assert renders "No beats in this event yet."
- **DS-7 retroactive:** Add unit fixture loading actual current `Production/Event_2/production_state.json` shape; assert beat_04 is NOT rendered. (Per "verify against actual code/state" feedback memory.)
- **Cleanup script test:** golden run on a fixture state; assert orphan removed and `display_order` untouched.

### 2.5 Severity rationale

HARD — silently surfaces stale/leaked beats to the user; breaks "what you see is what's authored" expectation; can cascade if Kim hits "Accept all beats into storyboard" while orphans exist.

---

## 3. Bug C — Production Map: every row shows Event_1 data

### 3.1 Reproduction

1. Load Production Map tab.
2. **Observed:** All rows M1..M59 show:
   - Role = `intro` (uniform)
   - Phase A = 14 / Phase B = 1 / Storyboard = 36 / Final concat = 0 (uniform)
3. **Expected:** Each module's row reflects ITS event_dir's artifacts AND its `prod_modules.video_role` value (intro vs resolution vs standalone).

### 3.2 Root cause

`Production/tools/production_server.py:8429-8472` (`_handle_production_map`):

```python
for m in modules or []:
    event_dirs = sorted(
        p for p in production_root.iterdir()
        if p.is_dir() and p.name.startswith("Event_") and "_" not in p.name[len("Event_"):]
    )
    edir = event_dirs[0] if event_dirs else None  # ⚠️ always Event_1
    ...
    if edir:
        phase_a = list(edir.glob("phase_a_stitched_*.mp4"))         # always Event_1's
        phase_b = list(edir.glob("phase_b_lipsync_*.mp4"))           # always Event_1's
        intro_or_resolution = list(edir.glob("storyboard_v*_prod.html"))
        final_concat = list(edir.glob(f"M{m.get('m_number')}_*_final.mp4"))
        ...
```

The comment in the file says: `"Take the first event dir (Event_1) as the canonical for now; multi-event would map M-number → event in S4."` — known incomplete shortcut. S4 work was never done.

The `Role` column rendering shows `m.get('video_role')` which is a Directus `prod_modules` field. If every module row in Directus has `video_role='intro'`, that explains the uniform Role column too. **Verify** before implementing fix:

```bash
curl -sH "Authorization: Bearer $DIRECTUS_TOKEN" \
  "$DIRECTUS_URL/items/prod_modules?fields=id,m_number,creature_name,video_role&sort=m_number&limit=100" | jq '.data | group_by(.video_role) | map({role: .[0].video_role, count: length})'
```

If all rows have `video_role='intro'`, fix needs an additional Directus data step (or we should DERIVE role from on-disk artifacts per Cursor R3 guidance from picker spec).

### 3.3 Fix (server, two parts)

**Part 1 — M-number → event_dir mapping:**

Need a deterministic mapping from `m_number` to `Event_<N>` directory. Two options:

- **Option A (preferred, schema-light):** Add `event_dir` (or `event_number`) field to `prod_modules` Directus collection. Server reads it directly. Migration: backfill via a one-shot script that maps M# to Event# per the canonical Storyline doc.
- **Option B (no schema change):** Convention — `m_number N maps to Event_N` for the Arc 1 events Kim is currently producing. Hardcode the map server-side. Brittle but immediate.

Default: **Option A.** Aligns with PRODUCTION_MAP_V1's "S4: multi-event support" note. Cursor please confirm.

**Part 2 — Role column DERIVED from on-disk artifacts (per Cursor R3 picker-spec guidance):**

Per the Video Role Picker spec Cursor review (R3), Production Map should DERIVE per-role columns from on-disk artifacts rather than reading `prod_modules.video_role` (which is intent metadata, not state). For each event_dir, scan:

- `<edir>/intro/scene_intro_*.mp4` → intro role status
- `<edir>/resolution/scene_resolution_*.mp4` → resolution role status

Either replace the `video_role` column with TWO columns (Intro / Resolution status) OR pivot rows so each (M#, role) is its own row. Cursor please confirm which UX is right.

### 3.4 Test plan

- **Unit (Python):** `test_production_map_endpoint.py` — fixture with multiple event_dirs (Event_1 + Event_2), assert each row's `event_dir` matches its m_number.
- **e2e:** `storyboard-v59-production-map.spec.ts` — load map, assert at least 2 distinct values in Role column AND in `event_dir`.
- **DS-7 retroactive:** confirm the actual current Directus `prod_modules` data set returns sensible roles (manual smoke).

### 3.5 Severity rationale

HARD — Production Map is currently misleading. Kim flagged it explicitly: "production map still seems to think it knows the future... randomly goes thru 15 modules." Trust in the dashboard is broken; fixing the mapping restores its purpose.

---

## 4. Bug D — CSS for `.mn-video-selector` (cosmetic)

### 4.1 Symptom

The video selector renders functional but unstyled, sitting raw next to the styled `.mn-event-selector`. Mismatched font/spacing.

### 4.2 Fix

`Production/tools/storyboard-v2/src/app.css` — add sibling rules mirroring `.mn-event-selector`:

```css
.mn-video-selector {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 12px;
}
.mn-video-selector-label {
  color: var(--text-dim);
  font-size: 11px;
  font-family: var(--mono);
}
.mn-video-select {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 3px 8px;
  border-radius: 3px;
  font-size: 12px;
  font-family: inherit;
}
```

Note: The select element already has class `mn-video-select` per VideoSelector.tsx:161; just need the rule. Severity SOFT.

---

## 5. Bug E — STORYBOARD_DEPLOY_PROCESS_V1 LD (process gap)

### 5.1 Symptom

Server reads from Dropbox tree's `Production/Event_<N>/storyboard_v59_prod.html`. Code merges to tooling repo do NOT update that file. Result: Kim ran on a May 3 build for two days post-merge while the new VideoSelector + ProjectSelector + Beat Gen plumbing landed in code.

### 5.2 LD (proposed, SOFT)

**STORYBOARD_DEPLOY_PROCESS_V1 — Local SPA build must be deployed to Dropbox tree before browser smoke.**

Decision text (draft):

> After any merge that touches `Production/tools/storyboard-v2/src/`, the developer MUST:
>
> 1. `cd Production/tools/storyboard-v2 && npm run build`
> 2. `cp dist/index.html "<Dropbox>/Production/Event_1/storyboard_v59_prod.html"`
> 3. Repeat for every active `Event_<N>/` directory (currently Event_1, Event_2)
> 4. Sha256 the destination and verify size > 100 KB (post-VideoSelector baseline ~182 KB)
> 5. Commit the new sha256 sidecar (`storyboard_v59_prod.html.sha256`) to the Dropbox tree
>
> A `Production/scripts/deploy_storyboard_v59.sh` wrapper SHOULD automate this. Until then, the manual checklist is mandatory before declaring a merge "shipped" or running browser smoke.
>
> Browser smoke that fails BEFORE this step is invalid — debug only AFTER deploy is verified.

**Severity:** SOFT (process)
**Scope:** storyboard_v59
**Enforcement:** documentation; optional pre-commit grep CI gate.

### 5.3 Optional Phase 2 — auto-deploy on merge

GitHub Action that runs `npm run build` and pushes `dist/index.html` to a Dropbox release path; or a local pre-push hook. Defer to a separate session.

---

## 6. Atomic execution plan

### 6.1 Order (sequential commits, all on `claude/post-redeploy-bug-triage`)

1. **C1** — Bug A fix (BgTab.tsx dep array) + unit test + e2e
2. **C2** — Bug B fix (StoryboardTab.tsx `display_order !== undefined` distinction) + unit + e2e + retroactive fixture
3. **C3** — Bug B server hygiene (prune orphan beats on display_order mutation in production_server.py) + Python unit test
4. **C4** — Bug B cleanup script (`Production/scripts/clean_orphan_beats_v3.py`) + dry-run on fixtures + golden test
5. **C5** — Bug C fix (M-number → event_dir mapping in `_handle_production_map`) + Python unit + e2e
6. **C6** — Bug C role column (depends on Cursor R-row decision: per-role columns vs DERIVED single column)
7. **C7** — Bug D CSS for `.mn-video-selector` + visual smoke
8. **C8** — Bug E LD STORYBOARD_DEPLOY_PROCESS_V1 written to `prod_locked_decisions` (Directus); deploy script `Production/scripts/deploy_storyboard_v59.sh` (optional Phase 2 separate)

After C8: `npm run build` + redeploy to Dropbox tree per C8's own LD, browser smoke at `http://localhost:5111/`, run cleanup script (`--apply`) on Event_2 to evict orphan beat_04, mn-context SAVE.

### 6.2 LDs to file

- (HARD) **DISPLAY_ORDER_STRICT_V1** — empty `display_order` means render zero beats; only undefined falls through to legacy sorted-keys path
- (HARD) **PRODUCTION_MAP_PER_MODULE_EVENT_DIR_V1** — every row globs ITS OWN event_dir, not Event_1 universally
- (SOFT) **BG_TAB_SCOPE_SYNC_V1** — BgTab segment context re-syncs on activeScope OR activeVideoRole change
- (SOFT) **STORYBOARD_DEPLOY_PROCESS_V1** — local build must be redeployed to Dropbox tree post-merge (see §5.2)
- (SOFT, conditional) **PRODUCTION_MAP_PER_ROLE_COLUMNS_V1** OR **PRODUCTION_MAP_ROLE_DERIVED_V1** depending on Cursor R-row outcome on §3.3 Part 2

### 6.3 Tests added (gross count target)

- 4 unit (BgTab dep, StoryboardTab three cases, server prune helper)
- 4 e2e (bg-scope-sync, display-order-empty, production-map-multi-event, video-selector-styled)
- 1 retroactive (DS-7) using actual Event_2 state fixture
- 1 cleanup-script golden

= ~10 tests, brings v59 e2e count from 91 → ~99.

### 6.4 Discipline-standards alignment (per .claude/skills/zero-error-qa/SKILL.md)

- DS-1 Contract-first: every fix has unit + e2e drafted BEFORE patch
- DS-2 Boundary: scope-key auto-injection still enforced; BgTab fix relies on existing scope plumbing, doesn't bypass it
- DS-7 Retroactive: real Event_2 state file shipped as fixture
- DS-12 Severity: every LD tagged HARD/SOFT explicitly above

---

## 7. Cursor review checklist (paste this section into Cursor verbatim)

Cursor — please review this spec end-to-end. Specifically:

**R1 (Bug A scope):** Should the fix also patch the server's `bg_session_state` to scope `active_context` per `(event_id, video_role)` so multi-tab/multi-event don't collide? OR is server-side single-context fine because Kim is single-user? **Default proposal:** defer to follow-up; flag in this spec.

**R2 (Bug B Part 2 timing):** Should server-side prune (orphan removal on display_order mutation) ship in this fix or as a separate hardening session? **Default:** ship in this fix; orphan accumulation is the same root cause.

**R3 (Bug B cleanup script safety):** The script mutates production_state.json across all events. Confirm dry-run-first + atomic write through mutation channel + audit log are sufficient. Any additional safeguard needed (e.g., Directus row in prod_activity_log for each evicted beat)?

**R4 (Bug C Part 1 schema vs convention):** Option A (add `event_dir` field to `prod_modules`) vs Option B (M# = Event#). A is cleaner; B is faster. Recommend?

**R5 (Bug C Part 2 UX):** Per-role columns (5 cols: M, Creature, Phase A, Phase B, Intro, Resolution, Final concat) vs pivot rows (each (M, role) its own row, doubling row count) vs single Role column DERIVED from on-disk presence. Which is right for the Production Map?

**R6 (LD canonicalization):** Are the four+1 LD names in §6.2 right, or should some collapse? E.g., DISPLAY_ORDER_STRICT_V1 + cleanup script — one LD or two?

**R7 (Atomic execution):** Is the 8-commit sequence in §6.1 too granular? Acceptable to bundle C2+C3+C4 (all Bug B) into one PR-equivalent commit?

**R8 (Cross-spec consistency):** This spec touches surfaces that overlap with `STORYBOARD_V59_VIDEO_ROLE_PICKER_SPEC_v1.md` (per-role columns Cursor R3). Confirm no contradiction; if there is, which one wins?

---

## 8. Open questions for Kim (after Cursor)

1. Should the orphan beat_04 in Event_2 intro be auto-deleted by the cleanup script (with audit log), OR should Kim manually decide whether to keep/move/delete it?
2. Does Production Map already have an "active" filter (only show modules currently in production)? If yes, that filter alone might mask Bug C until the underlying counts mismatch. Worth verifying.
3. After bug fixes ship, should the rebuilt SPA + redeploy + browser-smoke be a single chained command? Or is the explicit pause Kim wants?

---

**END SPEC v1**
