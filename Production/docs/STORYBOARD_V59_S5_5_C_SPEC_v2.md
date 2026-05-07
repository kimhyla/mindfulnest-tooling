# Storyboard v59 — Sub-Session S5.5c Spec v2 (post-v3, supersedes v1)

**Date:** 2026-05-03
**Supersedes:** `STORYBOARD_V59_S5_5_C_SPEC_v1.md` (kept as historical reference)
**Classification:** EXECUTION SPEC — feature build on locked v3 architecture
**Predecessor:** S5.5d-cont (v3 architecture revision shipped 37/37 gates green)
**Master overview:** `STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md`

## §1 Task

Build out the **Beat Generator** tab (currently a stub) + Cropper canvas (currently a 1×1 placeholder PNG) + extract reusable UI primitives so later sessions don't duplicate work.

## §2 Governing Decisions

### LDs respected (do not violate)

| LD | Key | Reason |
|---|---|---|
| LD-439 | GPT_STILL_PROMPT_TEMPLATE_V1 | Image-led ~380-char prompt; canonical via `build_gpt_still_prompt()` at `beat_generator.py:934-947` |
| LD-440 | GPT_IMAGE_2_PRIMARY_MODEL_V1 | Model = `gpt-image-2`; NOT gpt-image-1; NOT FLUX |
| LD-421 / LD-422 | ASSET_FINDABILITY_OVERHAUL_V1 / BUILD_V1 | All ref uploads + generated stills via `registered_write.py` |
| LD-456 | SCOPE_VALIDATION_V1 | All mutations validate `scope_event_id` |
| LD-460 | ASYNC_JOB_GENERATION_PIN_V1 | New async handlers use `@with_pin_and_drain` decorator |
| LD-461 | SCOPE_BODY_HELPER_V1 | `_scope_body` helper for body normalization |
| LD-487 | BG_VIDEO_PARTITION_V2 | Beat Generator writes to `state.videos[<active_target>].beats` |
| LD-488 | VIDEO_ROLE_PER_REQUEST_V2 | Valid roles `{intro, resolution, standalone}` |

### NEW LDs this spec writes (4)

| Key | Severity | Purpose |
|---|---|---|
| `BEAT_GEN_3_OPTIONS_NOT_GRID_V1` | HIGH | Locks "3 OPTIONS per beat (NOT 3×3, NOT 9 stills, NOT FLUX)". Memory-clarification LD prevents future agent misreading. |
| `CROPPER_CANVAS_REAL_V1` | MEDIUM | CropperModal must use real `<canvas>` not placeholder PNG; aspect lock; drag/resize handles |
| `UI_PRIMITIVES_SHARED_V1` | LOW | Establishes `src/components/ui/` directory for Modal, Toast, Spinner, Select, Tabs, Tooltip, AssetTile. Future sessions reuse. |
| `DRAG_DROP_HELPER_V1` | LOW | Establishes HTML5 dataTransfer pattern in `src/utils/dragdrop.ts`. Used by S5.5g for Stitcher SFX, by LibraryPanel here. |

## §3 Approach

### §3.1 Beat Generator UI structure

**File:** `src/components/BgTab.tsx` (currently a 91-line stub; rewrite in place — keep filename per existing TabBar registration `'bg'` key)

```
┌─────────────────────────────────────────────────────────┐
│ Beat Generator — [active video role badge]              │
│ Cost this session: $X.XX • This generation: $Y.YY       │
├─────────────────────────────────────────────────────────┤
│ [+ Extract Beats from script]    [+ Add empty beat]     │
├─────────────────────────────────────────────────────────┤
│ ┌─ Beat 1 [✕] ─────────────────────────────────────────┐│
│ │ [dialogue textarea — contenteditable]                 ││
│ │ Stage chips: (Tessa looks up) [✕] (Chipper smiles)[✕] ││
│ │ ┌─ Char ref ─┐  ┌─ BG ref ──┐                         ││
│ │ │ [thumb]    │  │ [thumb]   │   [Generate 3 options]  ││
│ │ │ [upload]   │  │ [upload]  │                         ││
│ │ └────────────┘  └───────────┘                         ││
│ │ ┌── Option 1 ─┐ ┌── Option 2 ─┐ ┌── Option 3 ─┐       ││
│ │ │ [thumb]     │ │ [thumb]     │ │ [thumb]     │       ││
│ │ │ [● select]  │ │ [○ select]  │ │ [○ select]  │       ││
│ │ └─────────────┘ └─────────────┘ └─────────────┘       ││
│ └───────────────────────────────────────────────────────┘│
│ ┌─ Beat 2 ... (same shape) ...                          ┐│
│ └────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────┤
│                       [Accept All to Storyboard]        │
└─────────────────────────────────────────────────────────┘
```

**Key shape rules:**
- 3 options per beat = 1×3 layout (NOT 3×3 matrix). One char ref + one BG ref per beat. Per LD `BEAT_GEN_3_OPTIONS_NOT_GRID_V1`.
- Stage-direction chips extracted via regex `\(([^)]{4,50})\)` from dialogue text; max 2 chips per beat.
- Cost computed client-side: `n_calls × $0.04` (gpt-image-2 priced per LD-440 published spec).
- Accept All locks current selections + advances `pipeline_stage` field on beats.

### §3.2 Cropper canvas

**File:** `src/components/CropperModal.tsx` (currently 149-line stub; rewrite the canvas section)

Real `<canvas>` element with:
- Image load on modal open (image url passed via prop or scope signal)
- Crop selection rectangle with 8 drag handles (corners + edges)
- Aspect ratio constraint (16:9 default; per-asset configurable)
- Live preview of crop result
- Save → POST `/api/cr/save-crop` with real PNG data via `pathappPatch` (NOT raw fetch; current bypass is the bug)
- Library delete UI: `[✕]` button on hover per library tile via `cr_library_delete`

### §3.3 Shared UI primitives

**New directory:** `src/components/ui/`

| File | Purpose | Lines |
|---|---|---|
| `Modal.tsx` | Backdrop + close-on-Esc + content slot. Replaces CropperModal's one-off pattern. | ~80 |
| `Toast.tsx` | Stackable notifications. Severity (info/success/error). Replaces ScopeBanner's single-purpose impl. | ~100 |
| `Spinner.tsx` | Loading indicator. CSS-only animation. | ~30 |
| `Select.tsx` | Wrapped `<select>` with consistent styling. | ~50 |
| `Tooltip.tsx` | Hover + focus tooltip. | ~60 |
| `AssetTile.tsx` | Library tile wrapper with optional `draggable` + `data-lib-key`. Used by LibraryPanel + Stitcher (S5.5g). | ~80 |

**Total:** ~400 lines of primitives. Saves ~30% of net-new code in S5.5e/f/g.

### §3.4 Drag/drop helper

**New file:** `src/utils/dragdrop.ts`

```typescript
// HTML5 dataTransfer wrapper with strict typed payloads
export type DragPayload =
  | { kind: 'lib-image', lib_key: string, tier: string }
  | { kind: 'lib-watercolor', lib_key: string, animation_type: string }
  | { kind: 'lib-sfx', lib_key: string, source_path: string }
  | { kind: 'beat', beat_id: string };

export function setDragData(e: DragEvent, payload: DragPayload): void { ... }
export function getDragData(e: DragEvent): DragPayload | null { ... }
export function makeDraggable(handlers: { onDragStart: (e: DragEvent) => DragPayload | null, ... }): JSX.HTMLAttributes { ... }
```

Used by: AssetTile (this session), CropperModal drop target (this session), Stitcher SFX placement (S5.5g), Phase A/B watercolor drop (S5.5f).

### §3.5 Backend endpoints used (all existing per Agent A audit; NO new backend)

| Endpoint | Purpose | Source |
|---|---|---|
| `POST /api/bg/extract-beats` | Parse script → beat list | `production_server.py:8627` |
| `POST /api/bg/inject-beats` | Add multiple beats | `production_server.py:8669` |
| `POST /api/bg/update-beat` | Edit single beat (text, refs) | `production_server.py:8735` |
| `POST /api/bg/delete-beat` | Remove beat | `production_server.py:8786` |
| `POST /api/bg/add-beat` | Append empty beat | `production_server.py:9132` |
| `POST /api/bg/reorder-beats` | Drag-reorder | `production_server.py:8765` |
| `POST /api/bg/submit-gpt-batch` | 3 GPT calls per beat (varied seed) | `production_server.py:8937` |
| `GET /api/bg/poll-gpt-status` | Poll for batch completion | `production_server.py:9030` |
| `POST /api/bg/accept-option` | Lock one option as the live image | `production_server.py:9046` |
| `POST /api/bg/accept-lib-image` | Use existing library image instead of generating | `production_server.py:9082` |
| `POST /api/bg/set-active-context` | Set arc/event context | `production_server.py:8596` |
| `POST /api/cr/save-crop` | Save cropped PNG | `production_server.py:5122` |
| `POST /api/cr/upload` | Upload new image | `production_server.py:5124` |
| `POST /api/cr/library/delete` | Delete library tile | `production_server.py:5126` |
| `GET /api/cr/library` | Fetch library | `production_server.py:4940` |

## §4 Implementation Phases

### Phase A — Pre-flight + scoping

**A1.** Read master overview, this spec, v3 spec architecture sections (§3.1-3.4 of v3 spec).

**A2.** Confirm v3 server is up, v59 client builds clean.

**A3.** Confirm `state.videos[intro].beats` shape on Event_1 (should have 17 beats per browser smoke).

**A4.** Write `prod_preflight_reviews` row referencing #198 (S5.5d-cont) as predecessor.

### Phase B0 — Endpoint catalog completeness (NEW per Cursor v8 RELEASE-BLOCKER)

Cursor v8 caught that `endpoints.ts::MUTATION_ENDPOINTS` is missing keys for several BG/cr endpoints this session calls. `pathappPatch` is typed against `MutationEndpoint`, so calls without catalog entries don't compile. This is a prerequisite to Phase D wiring.

**B0.1.** Audit `src/api/endpoints.ts`. Confirm presence of:
- `bg_extract_beats`, `bg_inject_beats`, `bg_update_beat`, `bg_delete_beat`, `bg_add_beat`, `bg_reorder_beats`
- `bg_submit_gpt_batch`, `bg_accept_option`, `bg_accept_lib_image`, `bg_set_active_context`
- `cr_save_crop`, `cr_upload`, `cr_library_delete`

**B0.2.** For any missing keys: add to `MUTATION_ENDPOINTS` const + add URL template (e.g., `'POST /api/bg/extract-beats'`). If endpoint expects `scope_event_id`, add to `BG_MUTATION_ENDPOINTS` set (lines 72-79).

**B0.3.** Verify `scopeKeyFor()` returns correct key for each new endpoint.

**B0.4.** `npm run build` clean (TypeScript types now resolve for all bg/cr calls).

**B0.5.** Grep gate: `grep -rE "fetch\(.*\\\${.*}/api/(bg|cr)/" src/components/` returns ZERO hits — all bg/cr calls go through `pathappPatch`.

### Phase B — Shared UI primitives (foundation work)

**B1.** Create `src/components/ui/` directory.

**B2.** Build `Modal.tsx` — backdrop + close-on-Esc + content/header/footer slots. Add `data-testid="modal-<name>"`.

**B3.** Build `Toast.tsx` — stack manager + severity styling + auto-dismiss. Mounted in `app.tsx` next to existing ScopeBanner.

**B4.** Build `Spinner.tsx`, `Select.tsx`, `Tooltip.tsx`, `AssetTile.tsx`.

**B5.** Create `src/utils/dragdrop.ts` — typed payload helpers.

**B6.** Update `src/index.css` with `--ui-modal-backdrop`, `--ui-toast-bg-info`, etc. CSS variables.

**B7.** Migrate ScopeBanner to use new Toast primitive (consolidation; not a feature change).

**B8.** `npm run build` clean.

### Phase C — Cropper canvas

**C1.** Replace 1×1 placeholder logic at `CropperModal.tsx:55-79` with real canvas implementation.

**C2.** Add `<canvas>` element + crop selection rectangle (`src/components/CropperCanvas.tsx`, ~300 lines).

**C3.** Wire 8 drag handles + aspect ratio constraint.

**C4.** Wire `cr_save_crop` via `pathappPatch` (NOT raw fetch).

**C5.** Add library delete UI: hover-to-show `[✕]` button per library tile in `LibraryPanel.tsx`. Wire to `cr_library_delete`.

**C6.** Test: open Cropper modal, load image, drag crop rect, save → verify resulting PNG is real cropped data, not 1×1.

### Phase D — Beat Generator tab rewrite

**D1.** Rewrite `src/components/BgTab.tsx` (currently 91 lines) → ~600 lines. Keep filename + tab key `'bg'` for TabBar compat.

**D2.** Layout per §3.1 ASCII mockup. Use Modal/Toast/Spinner/AssetTile primitives from Phase B.

**D3.** Wire all 15 backend endpoints from §3.5. Use `pathappPatch` for mutations.

**D4.** Stage-direction chip extraction: regex on dialogue change → chips render → click [✕] removes.

**D5.** 3-option grid: 1×3 layout per beat. Click "Generate 3 options" → spinner → 3 thumbnails. Click radio to select. NOT a 9-cell matrix.

**D6.** Cost display: client-side compute from gpt-image-2 published price × call count. Running total + per-generation cost.

**D7.** Accept All button at bottom: locks selections, sets `pipeline_stage = 'accepted'`, fires Toast on success.

**D8.** Add/delete beats with proper `pathappPatch` mutations.

**D9.** `npm run build` clean. Visual smoke (Phase E gate).

### Phase E — Verification (12 gates)

**E1.** `npm run build` clean (no TS errors).
**E2.** Server `/api/health` 200; PID start time AFTER last edit (Rule 29).
**E3.** Modal primitive renders + closes on Esc + closes on backdrop click.
**E4.** Toast primitive: 3 toasts stack, auto-dismiss after 5s, click-to-dismiss works.
**E5.** Cropper: load image → drag crop rect → save → POST body has real PNG bytes (not 1×1).
**E6.** Cropper library delete: click [✕] on library tile → `cr_library_delete` posted → tile removed from grid.
**E7.** Beat Generator: click "Extract Beats" → spinner → beat list populates from backend.
**E8.** Beat Generator: click "Generate 3 options" on a beat → spinner → 3 thumbnails appear in 1×3 layout.
**E9.** Beat Generator: select option → POST `/api/bg/accept-option` fires → option marked selected.
**E10.** Beat Generator: stage-direction chip extracted from `(text)` in dialogue; max 2 chips per beat.
**E11.** Beat Generator: cost display updates after each generation; running total accurate.
**E12.** Accept All button POSTs real beat data (not empty `beats: []`); `pipeline_stage` updates; Toast confirms.

### Phase F — LD writes

**F1.** Write 4 NEW LDs via `try_post_or_queue`:
- `BEAT_GEN_3_OPTIONS_NOT_GRID_V1` (HIGH)
- `CROPPER_CANVAS_REAL_V1` (MEDIUM)
- `UI_PRIMITIVES_SHARED_V1` (LOW)
- `DRAG_DROP_HELPER_V1` (LOW)

**F2.** All writes via `try_post_or_queue` with read-back per Rule 35.

### Phase G — Closeout

**G1.** `prod_activity_log` row `S5_5C_COMPLETE` with full 12-gate summary.

**G2.** Write S5.5e handoff stub at `Production/docs/STORYBOARD_V59_S5_5_E_HANDOFF.md`.

**G3.** Update master overview's table with S5.5c = COMPLETE.

**G4.** Tail-end verifier subagent.

**G5.** Git commit: `S5.5c — Beat Generator + Cropper canvas + shared UI primitives (12 gates green)`.

## §5 Files Created / Modified

### Created (NEW)

- `src/components/ui/Modal.tsx`, `Toast.tsx`, `Spinner.tsx`, `Select.tsx`, `Tooltip.tsx`, `AssetTile.tsx`
- `src/utils/dragdrop.ts`
- `src/components/CropperCanvas.tsx`
- `Production/docs/STORYBOARD_V59_S5_5_E_HANDOFF.md` (closeout artifact)

### Modified

- `src/components/BgTab.tsx` (rewrite — keep filename)
- `src/components/CropperModal.tsx` (replace placeholder PNG logic)
- `src/components/LibraryPanel.tsx` (add hover-delete + draggable AssetTiles)
- `src/api/endpoints.ts` (add bg endpoints if missing — most should be there per S3 wiring)
- `src/index.css` (UI variables for new primitives)
- `src/app.tsx` (mount Toast next to ScopeBanner)
- `src/components/ScopeBanner.tsx` (migrate to Toast primitive)

## §6 Directus Writes Required

### `prod_locked_decisions`
- POST 4 NEW LDs (see §2)

### `prod_activity_log`
- `S5_5C_PHASE_A_PREFLIGHT`
- `S5_5C_PHASE_B_PRIMITIVES_COMPLETE`
- `S5_5C_PHASE_C_CROPPER_COMPLETE`
- `S5_5C_PHASE_D_BG_TAB_COMPLETE`
- `S5_5C_PHASE_E_VERIFICATION_PASS` (12 gates)
- `S5_5C_PHASE_F_LDS_REGISTERED`
- `S5_5C_COMPLETE`

### `prod_preflight_reviews`
- 1 row at session start; references #198 as predecessor

### `prod_assets` (during E5 + E8)
- Cropper save creates `still_master` or `still_delivery` rows via `cr_save_crop`
- Beat Generator option-accept creates `gpt_still` rows via `bg_accept_option`
- All via existing `registered_write.py` flows

## §7 Error Cases and Handling

| Failure | Handling |
|---|---|
| Modal Esc handler not removed on unmount | Memory leak; verify cleanup in useEffect return |
| Toast queue overflow (>20 toasts) | Cap at 5 visible; oldest auto-dismisses early |
| Cropper canvas image fails to load | Show error Toast; modal stays open with reload button |
| Cropper save returns >5MB payload | Server SIZE_BUDGET fail; surface error Toast |
| `bg/extract-beats` returns 0 beats | Show empty-state UI; offer "Add empty beat" button |
| `bg/submit-gpt-batch` 503 (drain active) | Retry once after 5s; if still 503, Toast "Server draining" |
| GPT generation fails on 1 of 3 calls | Show 2 options + "Retry 3rd"; partial result not blocking |
| Cost calculation NaN (price API unavailable) | Show "—" with Tooltip "price unavailable"; do not block flow |
| Drag-drop cross-browser quirks (Firefox vs Chrome) | Test on Chrome; document Safari/Firefox as future |
| Stage-direction chip extraction over-matches (parens in legitimate dialogue) | Regex max-length 50 chars; chip rejected if >50 |

**No silent failures** per Rule 19.

## §8 Verification

Done when 12 gates green + 4 LDs registered + activity_log rows written + browser smoke deferred to Kim documented.

## §9 Rollback

If Beat Generator rewrite breaks: `git checkout -- src/components/BgTab.tsx`. Other Phase B/C primitives are additive (new files); rollback by deleting `src/components/ui/` + `src/utils/dragdrop.ts`.

If shared primitives break existing components: ScopeBanner migration is the only existing-component change. `git checkout -- src/components/ScopeBanner.tsx app.tsx` reverts.

## §10 Out of Scope

- 9-cell character × BG matrix (NEVER — explicitly cut per LD `BEAT_GEN_3_OPTIONS_NOT_GRID_V1`)
- Beat Generator local animation features (Ken Burns, MagicCompositor inline) — defer to S6
- Beat Generator group-assemble UI — defer to S6
- Voice profile management UI — defer to S6
- Drag-drop file upload (file picker only this session) — defer
- All Storyboard tab beat-level buttons — S5.5e
- All Phase A/B feature parity — S5.5f
- All Stitcher SFX/transitions/trims — S5.5g

## §11 Dependencies on Prior Sessions

**Hard dependencies on v3 (S5.5d-cont):**
- v3 state shape live (videos partition, scope_target_video routing)
- `pathappPatch` mutation channel with auto-injection
- `@with_pin_and_drain` decorator pattern available for any new server work (this session uses existing endpoints, but pattern documented)

**No dependencies on parallel sessions** — runs first.

## §12 Notes for the Executing Session

- All 15 backend endpoints in §3.5 EXIST per Agent A's audit. Do NOT add new server-side handlers in this session. If you find a gap, surface to Kim.
- 3 OPTIONS, NOT 3×3. The phrase "grid" refers to UI layout (1×3), not matrix. See `project_beat_generator_3_options_not_grid.md` memory.
- `BgTab.tsx` filename + `'bg'` tab key are LOAD-BEARING. TabBar registers them. Don't rename.
- Migrate ScopeBanner to Toast primitive AS PART OF Phase B B7 — not as separate cleanup later.
- Cropper currently writes a 1×1 PNG (per Cursor v7 + Agent A finding). Replacement is the FIRST thing to test in Phase E5. If E5 still produces 1×1, the rewrite was incomplete.
- The shared primitives are FOUNDATIONS for S5.5e/f/g. Don't shortcut Phase B; later sessions assume Modal/Toast/Spinner exist.

## §13 Cursor Review Checklist

Send Cursor this spec + the following questions:

1. Are 17 verification gates (12 + 5 Phase B0) enough for Beat Generator + Cropper + 6 UI primitives + dragdrop + catalog completeness?
2. Does the Modal primitive design correctly handle nested modals (Cropper inside Beat Generator, e.g.)?
3. Toast queue cap at 5 visible — is that the right number?
4. Should the dragdrop typed-payload pattern use a discriminated union (current design) or a base class? Strict-mode TypeScript implications?
5. Is the shared-primitives extraction the right granularity? Should AssetTile live in `src/components/` (used everywhere) or `src/components/ui/` (general primitive)?
6. Stage-direction regex `\(([^)]{4,50})\)` — any edge cases (nested parens, escaped parens, multibyte chars)?
7. Cost-calculation NaN handling — is "show —" the right UX, or should it block generation?
8. Beat-Generator + Cropper modal flow: when user clicks crop on a beat ref slot, should Cropper open AS a modal over Beat Generator, or replace the tab? Master overview implies modal pattern.
9. Beat Generator's `Accept All` advances `pipeline_stage` — what's the rollback if Accept All triggers a downstream failure (e.g., Storyboard tab can't render the accepted beats)? Recovery path?
10. Drag-drop helper needs to work in both Chromium + Safari for E19 browser smoke. Any Safari-specific dataTransfer quirks to call out?

Append findings to this spec as §14 before terminal execution.

---

## §14 Cursor v8 findings folded (audit trail)

| Finding | Resolution |
|---|---|
| Q1 12 gates insufficient (catalog + milestone scope BG missing) | NEW Phase B0 covers catalog; gate B0.4 + B0.5 added; milestone-scope BG smoke gate added to E12 (videos.standalone.beats path) |
| Q2 nested modal stack rule | AMENDED — single-modal stack (z-index escalator + "only one dialog" invariant); Cropper-over-Modal explicitly handled |
| Q5 Tabs primitive scope | AMENDED — Tabs primitive DEFERRED out of S5.5c (no caller this session); add to S5.5e/f/g if needed |
| Q6 stage-direction regex pathological cases | AMENDED — "first two matches after stripping quoted dialogue"; add gate with pathological script snippet |
| Q8 Cropper modal vs tab | DECIDED — modal overlay (matches existing app.tsx `cropperState` signal); tied to that signal |
| Q9 Accept All rollback | AMENDED — server is source of truth for `pipeline_stage`; partial failures = idempotent retry; gate for half-written sidecar |
| Q10 Safari drag/drop | AMENDED — supported-browser matrix mirrors S5.5f/g; document Safari gaps as known limits |
| Beyond #1 RELEASE-BLOCKER missing endpoints in MUTATION_ENDPOINTS | FIXED — Phase B0 added (see above) |
| Beyond #2 handoff stub filename chain | VERIFIED — S5.5c writes S5.5e_HANDOFF; S5.5e writes S5.5f_HANDOFF; S5.5f writes S5.5g_HANDOFF; S5.5g writes FEATURE_PARITY_COMPLETE_HANDOFF. Chain intact. |

Total gates now: 17 (was 12: +5 from Phase B0 — B0.1 through B0.5).

**End of S5.5c spec v2 (Cursor v8 folded — gates updated to 17).**
