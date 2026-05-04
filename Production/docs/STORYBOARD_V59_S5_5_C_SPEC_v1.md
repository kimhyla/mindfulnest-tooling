# Storyboard v59 — Sub-Session S5.5c Spec v1

**Date authored:** 2026-05-03
**Author:** Desktop Claude (parallel to S5.5a2 execution)
**Classification:** EXECUTION SPEC — feature build on locked architecture
**NOT tech-spec-skill scope:** architecture is locked (LD-439, LD-440, prior-session research); only UX details require design here

## §1 Task

Build the **Beat Generator** tab in `Production/tools/storyboard-v2/` (the v59
Preact + signals + TS app). This tab is the storyboard-side authoring surface
for generating per-beat stills via the GPT pipeline.

Scope is **Option B+** as Kim confirmed (the essentials she needs, no GPT mode
toggle, no 9-stills-per-beat, no FLUX path):

- **Per-beat character ref + BG ref upload slots** (1 char + 1 BG per beat,
  port from `patch_storyboard_v42.py`)
- **3-option GPT grid generation** per beat (3 gpt-image-2 calls per LD-440,
  image-led ~380-char prompt per LD-439, varied via seed)
- **Dialogue editor with stage-direction extraction chip** (regex
  `\(([^)]{4,50})\)`, max 2 chips per beat, appended to prompt as
  `Stage direction: <chip>`)
- **Add/delete beats** (additive to `videos.<role>.beats` partition)
- **Cost display** (per-generation cost + session running total)
- **Accept All** button (locks current selections, advances pipeline_stage)

The tab MUST respect the new `videos.{intro|phase_a|phase_b|win}` partition
landed by S5.5a2. Beat Generator operates on whichever video role is currently
active per the VideoSelector (built in S5.5b).

## §2 Architecture (already locked — citing, not deciding)

These decisions are **not up for re-debate** in S5.5c. Cite them in the
implementation; do not deviate.

| Decision | Source | Notes |
|---|---|---|
| Image gen model = `gpt-image-2` | LD-440 | NOT gpt-image-1; NOT Flux |
| Prompt template = image-led ~380 chars | LD-439 | NOT 1152-char species-anchor (superseded) |
| Build prompt via `build_gpt_still_prompt()` | `beat_generator.py:934-947` | Single source of truth — call it, don't reimplement |
| 1 char ref + 1 BG ref per beat | Session memory + Kim 2026-05-02 | NOT 3×3 grid; NOT separate per-character stills |
| Stage-direction extraction regex | Spec v2 §1 + prior research | `\(([^)]{4,50})\)`, max 2 |
| Beat partition shape | S5.5a2 | `state.videos.<role>.beats[beat_id]` |
| Per-beat ref upload backend | `production_server.py` (existing endpoints, UI port only) | Verify endpoint names in Phase A; do NOT rebuild |
| Asset findability | LD-421 / LD-422 | All ref uploads + generated stills go through `registered_write.py`; iteration_notes captured per beat |
| Mutation channel | spec v3.1 + S5.5a1 | All state writes via `pathappPatch(scope, field, value)` with `scope_video_role` per LD-474 |
| Cost source | gpt-image-2 published pricing | Compute client-side from per-call cost × call count |

## §3 Implementation Detail

### §3.1 New tab structure

**File:** `Production/tools/storyboard-v2/src/tabs/BeatGeneratorTab.tsx`

Pattern: same as existing tab files (PhaseATab, PhaseBTab, etc.) — Preact
component reading from scope-keyed signal stores, mutating via `pathappPatch`.

Top-level layout:

```
┌─────────────────────────────────────────────────────────┐
│ Beat Generator — [active video role badge]              │
│ Cost this session: $X.XX • This generation: $Y.YY       │
├─────────────────────────────────────────────────────────┤
│ ┌─ Beat 1 ─────────────────────────────────────────────┐│
│ │ [dialogue textarea]                                   ││
│ │ Chips: (Tessa looking up) [×]  (Chipper smiles) [×]   ││
│ │ ┌─ Char ref ─┐  ┌─ BG ref ──┐                         ││
│ │ │ [thumb]    │  │ [thumb]   │   [Generate 3 options] ││
│ │ │ [upload]   │  │ [upload]  │                         ││
│ │ └────────────┘  └───────────┘                         ││
│ │ ┌── Option 1 ─┐ ┌── Option 2 ─┐ ┌── Option 3 ─┐       ││
│ │ │ [thumb]     │ │ [thumb]     │ │ [thumb]     │       ││
│ │ │ [select]    │ │ [select]    │ │ [select]    │       ││
│ │ └─────────────┘ └─────────────┘ └─────────────┘       ││
│ │                                              [delete] ││
│ └───────────────────────────────────────────────────────┘│
│ ┌─ Beat 2 ─ ... (same shape) ...                       ┐│
│ └───────────────────────────────────────────────────────┘│
│ [+ Add Beat]                                             │
│                                                          │
│                                       [Accept All ▶]    │
└─────────────────────────────────────────────────────────┘
```

### §3.2 State shape (additive to S5.5a2 partition)

`state.videos.<role>.beats[beat_id]` gains four sub-fields (additive — no
migration needed beyond a2's lift):

```jsonc
{
  "beat_01": {
    "dialogue": "...",          // existing
    "image_path": "...",        // existing
    "refs": {                   // NEW
      "char": "Production/Event_1/_refs/beat_01_char.png",
      "bg":   "Production/Event_1/_refs/beat_01_bg.png"
    },
    "gen_options": [            // NEW — 3 most recent generations
      { "id": "opt_1714...", "image_path": "...", "cost": 0.04, "seed": 11 },
      { "id": "opt_1714...", "image_path": "...", "cost": 0.04, "seed": 22 },
      { "id": "opt_1714...", "image_path": "...", "cost": 0.04, "seed": 33 }
    ],
    "selected_option_id": "opt_1714...",   // NEW — which option is live
    "stage_directions": [       // NEW — extracted chips, persisted
      "Tessa looking up",
      "Chipper smiles"
    ]
  }
}
```

Reads via `state.get_beats(video_role)`. Writes via
`state.mutate_video_state(video_role, lambda partition: ...)`.
NEVER read `state.active_video` for partition selection (LD-474).

### §3.3 Backend endpoints

**Phase A first task: AUDIT existing endpoints in `production_server.py`** —
do NOT assume their exact names. Per session memory ("Server endpoints exist.
UI port only"), the following are believed to exist; CONFIRM each:

- `POST /api/beat_gen/upload_ref` — body: `{scope, beat_id, ref_type:
  "char"|"bg", image_b64}`. Writes to `Production/Event_<N>/_refs/` via
  `registered_write.py`. Updates `state.videos.<role>.beats[beat_id].refs.<type>`.
- `POST /api/beat_gen/generate` — body: `{scope, beat_id, count: 3}`. Reads
  beat refs + dialogue + stage_directions from partition. Calls
  `build_gpt_still_prompt()` from `beat_generator.py`. Submits 3
  gpt-image-2 calls (varied seed). Writes outputs via `registered_write.py`.
  Updates `gen_options` array.
- `POST /api/beat_gen/select_option` — body: `{scope, beat_id, option_id}`.
  Updates `selected_option_id`. Mirrors `image_path` to selected option's
  path so downstream pipeline reads continue to work.
- `POST /api/beat_gen/add_beat` — body: `{scope, after_beat_id}`. Inserts
  new empty beat. Returns new beat_id.
- `POST /api/beat_gen/delete_beat` — body: `{scope, beat_id, confirm: true}`.
  Deletes from partition. Hard-delete with confirm flag (no soft-delete).
- `POST /api/beat_gen/accept_all` — body: `{scope}`. Validates every beat
  has a `selected_option_id`. Advances `pipeline_stage` per existing logic.

**For any endpoint that does NOT exist:** add it. Pattern matches existing
storyboard endpoints — `_assert_event_scope`, `_check_event_pin` for async,
LD-460 pin pattern, LD-474 `scope_video_role` propagation.

**Stage-direction extraction (server-side helper):**

```python
import re
STAGE_DIR_RE = re.compile(r'\(([^)]{4,50})\)')

def extract_stage_directions(dialogue: str, max_n: int = 2) -> list[str]:
    return [m.strip() for m in STAGE_DIR_RE.findall(dialogue)][:max_n]
```

Lives in `production_server.py` near other beat-gen helpers. Stage directions
persist to `state.videos.<role>.beats[beat_id].stage_directions` for editing.

### §3.4 UX details (the actual design decisions for this session)

**3-option grid selection:**
- Click an option thumbnail → that option becomes `selected_option_id`
- Selected option highlighted with teal border (matches v59 selection style)
- Unselected options remain visible in iteration history per LD-421 (always
  registered, never deleted)
- Re-clicking "Generate 3 options" replaces `gen_options` array with new
  generation (old options stay registered in Directus per LD-421;
  `iteration_notes` field on the asset row captures Kim's verbatim
  rejection reason if she provides one)

**Per-beat ref upload:**
- Click empty ref slot → file picker (`<input type=file accept="image/*">`)
- Selected file uploaded via `POST /api/beat_gen/upload_ref` (base64 in body
  to avoid multipart/form-data plumbing)
- Slot updates with thumbnail preview after server confirms
- Re-clicking thumbnail allows replacement (file picker again)
- Right-click thumbnail → context menu: "Remove ref"
- Thumbnail max 80px on long edge in UI; full file at original resolution
  on disk

**Cost display:**
- Per-generation: shown as transient toast for 4 seconds after each
  `/generate` returns
- Session running total: persistent header strip, accumulates from
  each `/generate` cost (returned in response body)
- Cost source: `cost` field returned by `/generate` per option; sum to
  3 calls per generation (typical $0.04 × 3 = $0.12 per generation
  at gpt-image-2 standard tier — confirm in Phase A against
  `Production/API_KEYS_MASTER.md` cost notes)

**Accept All semantics:**
- Validates: every beat has a `selected_option_id` (warn modal if any
  unset, with list of unset beat_ids)
- Confirm modal: "Lock in N selections and advance pipeline_stage?"
- On confirm: POSTs `/api/beat_gen/accept_all` → server advances
  `pipeline_stage` (existing pipeline logic) and writes
  `prod_activity_log` row `BEAT_GEN_ACCEPT_ALL` with full selection map
- After acceptance: tab enters "locked" mode — Generate buttons disabled,
  upload slots disabled, only re-edit possible via explicit "Re-open
  for edit" button (which decrements pipeline_stage with confirm)

**Add/delete beats:**
- "+ Add Beat" inserts after the last beat (most common case). For
  insert-at-position, right-click any beat → "Insert beat after"
- Delete: small "×" button at top-right of beat card. Click → confirm
  modal "Delete beat <id>? This cannot be undone."
- Both operations update `videos.<role>.beats` immediately via
  `pathappPatch`

**Dialogue editor + stage-direction chips:**
- Plain `<textarea>` for dialogue
- After textarea, render extracted stage directions as chips:
  `[(Tessa looking up) ×]`
- Chip × removes the chip AND removes the corresponding `(...)` from
  the dialogue text
- Manually typing `(new direction)` in the textarea triggers re-extraction
  on blur — chip appears
- Chips persisted to `stage_directions` field; passed to GPT as
  `Stage direction: X` lines appended to the image-led prompt
- Edit chip text via right-click → "Edit chip" (replaces the
  parenthesized text in the dialogue + the chip text together)

### §3.5 v58 → v59 port references

The patterns for ref upload + 3-option grid exist in v58 land. Port from:

- **Per-beat ref upload UI:** `patch_storyboard_v42.py` — Char Ref + BG
  Ref slot pattern. Read this file FIRST in Phase A to extract the layout
  + click handlers, then re-implement in TSX.
- **3-option grid logic:** `Production/tools/beat_generator.py` — has the
  generation logic; the v58 storyboard's beat-gen tab calls it via
  `production_server.py` proxy. Read the existing v58 storyboard HTML to
  see how options are rendered + selected.
- **Stage-direction extraction:** Already exists in `beat_generator.py`
  per session memory; verify the regex matches the spec (`{4,50}` length
  bounds, max 2).

**Do NOT reinvent these patterns.** Port faithfully; deviate only where
v58 had a bug or where the v59 partition shape forces a structural change.

## §4 Implementation Phases

### Phase A — Backend audit + extension (~30 min)

1. `grep -nE 'beat_gen|/api/beat' Production/tools/production_server.py`
   to enumerate existing endpoints
2. For each endpoint listed in §3.3: confirm exists (note path + handler
   function name) OR mark as TO ADD
3. For TO ADD endpoints: implement using existing patterns
   (`_assert_event_scope`, `_check_event_pin`, LD-474 `scope_video_role`)
4. Add `extract_stage_directions()` helper if not already present
5. `python3 -m py_compile Production/tools/production_server.py` clean
6. Restart server; confirm `/api/health` returns 200

### Phase B — TSX tab build (~60 min)

1. Create `Production/tools/storyboard-v2/src/tabs/BeatGeneratorTab.tsx`
   following pattern of existing tab files
2. Wire into the tab router (likely `App.tsx` or similar — confirm during
   exploration)
3. Implement components in this order (each a separate commit-worthy unit):
   - Beat card skeleton (dialogue textarea, beat header, delete button)
   - Stage-direction chips (extraction on blur, chip × handler)
   - Per-beat ref upload slots (file picker, base64 upload, thumbnail)
   - 3-option grid (generate button, option thumbs, select handler)
   - Cost display (header strip + per-gen toast)
   - Add Beat / Delete Beat
   - Accept All flow (validation, confirm modal, locked-mode UI)
4. Smoke test in dev server (`npm run dev` from
   `Production/tools/storyboard-v2/`) against running production_server

### Phase C — Asset registration verification (~15 min)

Per LD-421 / LD-422 (Asset Findability):

1. All ref uploads → `registered_write.py` → `prod_assets` row created
2. All generated stills → `registered_write.py` → `prod_assets` rows
3. `iteration_notes` field captured at production-time on every generation
4. Verify via `find_asset.py` query — recent generations must surface

### Phase D — Verification gates (~15 min)

1. ✅ `python3 -m py_compile Production/tools/production_server.py`
2. ✅ `cd Production/tools/storyboard-v2 && npm run build` (no TS errors)
3. ✅ Server restart; `/api/health` 200
4. ✅ All 6 endpoints in §3.3 respond with expected shape (curl probes)
5. ✅ Dev server loads BeatGeneratorTab; smoke test:
   - Upload char ref to beat_01 → thumbnail appears
   - Upload BG ref to beat_01 → thumbnail appears
   - Type `(Tessa smiles)` in dialogue → chip appears
   - Click "Generate 3 options" → 3 thumbs appear, cost toast shows
   - Click option 2 → option 2 highlighted, `selected_option_id` updates
   - Click "+ Add Beat" → empty beat appears
   - Click "×" on new beat → confirm → beat removed
   - Click "Accept All" with one unset beat → warn modal lists it
   - Set the beat → click "Accept All" → confirm → pipeline_stage advances
6. ✅ `find_asset.py` query returns the 3 generated stills + 2 refs
7. ✅ `prod_activity_log` row `S5_5C_COMPLETE` written
8. ✅ S5.5b handoff stub or S6 prep handoff written (depending on order)

### Phase E — LD registrations

1. New LD `BEAT_GEN_TAB_V1` — locks the tab contract:
   `decision_text` includes the state shape additions (refs, gen_options,
   selected_option_id, stage_directions), endpoint contracts,
   selection-and-acceptance flow
2. Verify via `try_post_or_queue` read-back

## §5 Files Created / Modified

**Created:**
- `Production/tools/storyboard-v2/src/tabs/BeatGeneratorTab.tsx` (NEW,
  ~400 lines target)
- (Possibly) new endpoint handlers in `production_server.py` (additive,
  see Phase A audit)

**Modified:**
- `Production/tools/storyboard-v2/src/App.tsx` (or wherever tab routing
  lives) — register new tab
- `production_server.py` — `extract_stage_directions()` helper if not
  already present; new endpoints if Phase A audit identifies gaps

**State shape:** additive to `videos.<role>.beats[beat_id]` — 4 new
sub-fields. NO migration required (existing partition tolerates
absent sub-fields; defaults are empty refs / empty gen_options /
null selected_option_id / empty stage_directions).

## §6 Directus Writes Required

**`prod_assets` (via `registered_write.py`):**
- 1 row per ref upload (char + bg per beat)
- 3 rows per generation (one per option)
- `iteration_notes` captured at write time
- `parent_asset_id` linking refs → generations (refs become parents
  for the gen options that used them)

**`prod_locked_decisions` (via `try_post_or_queue`):**
- 1 new LD: `BEAT_GEN_TAB_V1`

**`prod_activity_log` (via `try_post_or_queue`):**
- Phase A complete: `S5_5C_PHASE_A_COMPLETE`
- Phase B complete: `S5_5C_PHASE_B_COMPLETE`
- Phase D verification pass: `S5_5C_COMPLETE`
- Per-beat acceptance (when Kim hits Accept All): `BEAT_GEN_ACCEPT_ALL`
  with full selection map in `details` JSON

**`prod_preflight_reviews` (via `try_post_or_queue`):**
- 1 row at session start, `task_type=feature`,
  `approved_to_proceed=true`, references this spec

## §7 Error Cases and Handling

| Failure | Handling |
|---|---|
| GPT call returns 4xx (bad prompt, content policy) | Surface error toast with reason; mark option as failed; cost still counted (API charges per call) |
| GPT call returns 5xx / timeout | Auto-retry once with same seed; if second failure, surface error toast and skip that option (1 or 2 options instead of 3 is acceptable) |
| Ref upload >2MB | Resize to ≤1280 long-edge before upload (matches Rule 6.2 delivery tier) |
| Ref upload corrupt/non-image | Reject client-side via `accept="image/*"` + magic-byte check server-side; toast error |
| Beat partition write race (two clients) | Per LD-465 state isolation lock — second writer's `pathappPatch` 409s with current version; client refreshes and retries |
| Accept All with no beats | Disable button (validation: `beats.length > 0`) |
| Delete the only beat | Allow it (Kim might want to start fresh); next "Generate" disabled until Add Beat used |
| Network failure during upload | Toast error; ref slot reverts to empty; no partial state |
| Stage-direction regex matches >2 | Take first 2 only (per spec); silently drop excess |

**No silent failures.** Every error path either succeeds, retries, or
surfaces a toast. Per Rule 19.

## §8 Verification

Done when all 8 gates from §4 Phase D pass + 1 LD registered + 4
activity log rows written. Proof artifacts:

- `git diff` showing TSX file + any backend additions
- `npm run build` output (no errors)
- `curl` probes for all 6 endpoints
- Screenshot of working tab in dev server (Kim hands-on smoke)
- Directus row IDs for the 1 LD + 4 activity log rows

## §9 Rollback

- TSX file is purely additive — delete the file + un-register from
  tab router; v59 returns to pre-S5.5c state with zero residue
- Backend endpoint additions: revert via git
- State shape additions: backwards compatible (consumers tolerate
  absent sub-fields), so no rollback needed unless a beat's
  `selected_option_id` was set and downstream code depends on
  it — in that case, clear the field via direct state edit
- Directus writes: PATCH the LD to `status='superseded'` and
  the activity log rows are append-only (no rollback semantics
  needed)

## §10 Out of Scope (V1 Beat Generator)

Things explicitly NOT in S5.5c (defer to future sub-sessions or
post-cutover work):

- GPT mode toggle (Kim cut this — only gpt-image-2 path)
- 9-stills-per-beat / 3×3 grid (cut per Kim 2026-05-02)
- FLUX Kontext path (LD-440 locked gpt-image-2 only for Beat Generator)
- Bulk operations (multi-beat select-and-generate, etc.)
- History/diff UI for prior generations (data is in Directus per
  LD-421; no in-tool UI for browsing it in V1)
- Real-time collaboration (per-event isolation lock prevents
  concurrent editing — single editor at a time)
- Voice-driven dialogue editing
- Image editing within the tab (uploads + generates only; editing
  happens in external tools)
- Animation hooks ("Animate this" stays on watercolors per S5
  scope; not on Beat Generator stills)

## §11 Dependencies on Prior Sessions

**Hard dependency on S5.5a2:**
- `state.videos.<role>.beats` partition must exist (a2 provides)
- `state.get_beats(role)` and `state.mutate_video_state(role, ...)`
  helpers must work (a1 wrote them, a2 makes them load-bearing)
- `body['scope_video_role']` propagation through scope guards
  (a2 extends)
- LD-474 (VIDEO_ROLE_PER_REQUEST_V1) enforcement (a2 lands)

**Soft dependency on S5.5b:**
- VideoSelector UI (b builds it). S5.5c can ship before b; in
  the absence of VideoSelector, default to `intro` for the
  active video role and add a temporary inline dropdown in the
  Beat Generator tab as a placeholder. b will replace that with
  the global selector.

**Independent of:**
- S5.5b bug fixes (Bug 1-4, Bug 6) — orthogonal surfaces
- S6 parallel-run — c just needs to ship before parallel-run
  starts

## §12 Notes for the Executing Session

- Read this spec FULLY before any edit
- Spec v2 (S5.5a1) is the structural template for how to organize
  phases + verification; mirror that pattern
- Per S5.5a1's clean execution: where prompt and spec disagree,
  spec wins
- Per Rule 35: every Directus write consults
  `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` BEFORE
  payload composition; uses `try_post_or_queue` from
  `Production/lib/directus.py`; reads back to confirm
- Per Rule 36: any new Path B-style patches in storyboard-v2 must
  follow §36.1 invariant constraints (prefer `querySelectorAll`,
  document `// INVARIANTS:`, etc.) — though most of this work is
  TSX (compiled), not Path B HTML patches
- Per Rule 19: no shortcuts. If the audit in Phase A finds gaps,
  build them properly; do not stub
- Per `feedback_file_links.md`: any Kim-facing previews go through
  the HTML-page-in-Safari pattern, NOT file:// links

---

**End of S5.5c spec v1.** Author S5.5c handoff after S5.5b lands and
prerequisites are confirmed. The handoff will wrap this spec with
the operating-mode preamble + cold-start guardrails (same pattern
as S5.5a1 and S5.5a2 handoffs).
