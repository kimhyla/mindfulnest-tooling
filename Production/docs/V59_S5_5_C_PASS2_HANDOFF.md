# V59 Phase A (S5.5c-pass2) — Fresh Terminal Handoff

**For:** Fresh Claude Code terminal session
**Spec:** `Production/docs/V59_FEATURES_BUILD_SPEC_v1.md` — produced by tech-spec skill (dual-Opus research + debate + Kim §13 LOCKED decisions + §13c audit folded in); Cursor v8 reviewed with REVISE-BEFORE-SHIP, fixes folded in; Cursor v9 confirmation pass returned SHIP (chat-only artifact, not recorded in spec)
**Phase:** A of E (Beat Generator polish + Cropper fixes + Library primitives)
**Classification:** Tier A (Routine)
**Estimated work:** ~120 min

---

## Pre-paste checklist (Kim)

- [ ] `Production/docs/V59_FEATURES_BUILD_SPEC_v1.md` exists (Cursor v9 SHIP confirmed)
- [ ] Server fresh post-S5.5b (`lsof -ti:5111` returns PID; `ps -p <PID> -o lstart` shows recent start time)
- [ ] State.json files at v3 shape (post-architecture revision)
- [ ] Fresh terminal window, fresh `claude` session, no prior context

---

## Paste this into the fresh terminal:

```
═══════════════════════════════════════════════════════════════════
You are executing Phase A (S5.5c-pass2) of the v59 Features Build
per Production/docs/V59_FEATURES_BUILD_SPEC_v1.md.

CONTEXT: Spec v1 was authored 2026-05-06 via tech-spec skill (dual-Opus
research + debate + Kim §13 LOCKED decisions + Agent B symbol-level
trace). Cursor v8 review surfaced 1 release-blocker + 8 amends, all
folded in. Cursor v9 confirmed SHIP — all 13 verification targets
present. Spec is execution-ready.

This is the FIRST of 5 atomic sequential sessions (A → B → C → D → E).

PRE-EXECUTION (per spec §14, do EVERY box BEFORE any edit):

[ ] Read Production/docs/V59_FEATURES_BUILD_SPEC_v1.md §0 fully
    (Mandatory Operating Mode for Executing Sessions)
[ ] Load zero-error-qa skill (governs Phase 0 + DS-1 through DS-19)
[ ] Phase 0 classification: Tier A (Routine; per-bug fixes + additive
    UI primitives + Library primitives; no contract changes)
[ ] Spawn 0 advocate+counter agents per Tier A (no Phase 0 architectural
    review needed; spec already locked)
[ ] Write prod_preflight_reviews row via try_post_or_queue (Rule 35)
    BEFORE any edit; reference predecessor preflight id=201
    (s5_5ce-proper-fix-20260503-tooling-tree — topical predecessor)
    + this spec
    (BS4 fix: name predecessor explicitly rather than "most recent")
[ ] LD existence preflight (per spec §0.1 Cursor v8 Q9): Phase A
    introduces 2 new LDs (LIBRARY_TIER_FILTER_V1 + BG_ACCEPT_BEATS_
    ACTIVITY_LOG_V1) — no AMEND/SUPERSEDE in this phase, so query gate
    is N/A but document the N/A in preflight row
[ ] Rule 36 applicability gate: Phase A is mostly TSX work; no Path B
    HTML patches expected. Document as N/A in preflight row.
[ ] Read source files cited in spec §4 Phase A FRESH (not from memory):
    - Production/tools/storyboard-v2/src/components/BgTab.tsx
    - Production/tools/storyboard-v2/src/components/CropperCanvas.tsx
    - Production/tools/storyboard-v2/src/components/CropperModal.tsx
    - Production/tools/storyboard-v2/src/components/LibraryPanel.tsx
    - Production/tools/production_server.py:9227-9311 (bg_accept_beats)
    - Production/tools/production_server.py:10008-10173 (cropper save +
      upload — for BG-22 + C-9 registered_write refactor)
[ ] Verify Library tier filter has correct prod_assets schema field
    (Rule 35: consult Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md
    for the asset-type discriminator field)
[ ] Confirm endpoints catalog (no invented endpoint names): grep
    Production/tools/storyboard-v2/src/api/endpoints.ts MUTATION_ENDPOINTS
[ ] Server staleness baseline: lsof -ti:5111 + ps -p <PID> -o lstart +
    stat Production/tools/production_server.py mtime

PHASE A SCOPE (per spec §4 Phase A):

A1 — Beat Generator polish (~45 min):
  - BG-9: Replace window.confirm() at BgTab.tsx:289 with Modal primitive
  - BG-17: CSS class .mn-bg-ref-thumb {max-width:80px; max-height:80px;
    object-fit:cover} applied to <img> at BgTab.tsx:704
  - BG-22: Refactor production_server.py:10067-10083 to call
    registered_write.register_asset(...) with iteration_notes +
    parent_asset_id
  - BG-34/35: Warn modal listing unset beat_ids when Accept All clicked
    incomplete + Confirm modal "Lock in N selections..."
  - BG-37: Add try_post_or_queue("prod_activity_log", {action:
    "BEAT_GEN_ACCEPT_ALL", details: {selection_map, event_id, target}})
    in _handle_bg_accept_beats at production_server.py:9227-9316
    (BS2 verified: function head L9227, ends L9316; +5 from prior cite)
  - BG-5/8/18: Add visible buttons for Edit chip / Insert beat after /
    Remove ref (NOT right-click — Kim 2026-05-06 lock)

A2 — Cropper fixes (~15 min):
  - C-9: Refactor cropper save in production_server.py:10067-10083 to
    use registered_write.register_asset (related to BG-22 — same handler)
  - Verify aspect-ratio lock at 4:3 in CropperCanvas.tsx:216-271 — if
    not present, ADD aspect lock to crop-rect resize logic. Min size
    600px short side per Rule 6 / C-8 (already WIRED).
  - C-11: DROP from inventory (no keyboard shortcuts per Q4 lock)

A3 — Library primitives (~60 min):
  - CC-15: WIRED already; verify only
  - CC-16: Add drop target on Storyboard image holders (PREP for
    Phase B SB-14). Define mn-storyboard-image-drop-zone CSS class +
    onDrop handler accepting lib-image payload
  - CC-17: Library tier filter dropdown
    - Tier values: images, ambient, sfx, transitions, watercolors
    - **TIER MAPPING (Kim 2026-05-06 LOCKED Option A — client-side
      mapping, no schema change). prod_assets has NO `tier` field;
      use this client-side map:**
      - `images` → `asset_type IN ('image', 'still_delivery',
        'still_master', 'beat_scene')`
      - `ambient` → `asset_type='audio' AND tags CONTAINS 'ambient'`
      - `sfx` → `asset_type='sfx'`
      - `transitions` → `tags CONTAINS 'transition'`
      - `watercolors` → `tags CONTAINS 'watercolor'` OR `asset_name
        CONTAINS 'watercolor'`
    - Implementation: define `TIER_TO_FILTER_MAP` constant in v59
      client config; LibraryPanel uses the map to construct query
      params; server-side filter accepts asset_type list + tags
      contains
    - Default tier = images
    - Persist tier selection in localStorage
    - Log new LD: `LIBRARY_TIER_FILTER_V1` decision_text MUST capture
      this 5-tier mapping verbatim (no schema change; client-side
      filter only)
  - CC-18: Library search box
    - Substring match on file_name + iteration_notes
    - Debounced 300ms
    - Combined with tier filter
  - CC-19: Library item preview
    - Hover trigger after 500ms
    - Image: 320px max preview
    - Audio: plays inline
    - Video: muted preview
    - Click sticky-pins until clicked elsewhere

ESCAPE HATCHES (per spec §0.8 + Phase A specific):

Standing (any phase):
- Cursor v8/v9 review flagged release-blocker → STOP
- Layer 6 smoke fails (input variation → no output variation) → STOP
- Schema drift detected → STOP
- LD AMEND/SUPERSEDE not found at expected key → STOP (N/A this phase)
- Handler refactor breaks py_compile → STOP, revert via git
- Client refactor breaks npm build → STOP, revert
- Phase A surfaces architectural issue → STOP, invoke tech-spec
- Rule 26 Opus escalation triggered → STOP, escalate
- Test fixtures don't match current state → STOP
- Discovery that prior phase work was incomplete → STOP

Phase A specific (per spec §4 Phase A):
- BG-22 / C-9 registered_write refactor breaks find_asset.py queries
  → STOP, surface
- Library tier filter (CC-17) — if prod_assets schema doesn't have a
  tier-discriminator field, surface to Kim BEFORE guessing the field
  name (Rule 35)
- Library item preview (CC-19) — if hover/click doesn't render
  audio/video correctly, defer to follow-up rather than ship broken

VERIFICATION GATES (per spec §4 Phase A — all must PASS before COMPLETE):

A-1: python3 -m py_compile Production/tools/production_server.py clean
A-2: cd Production/tools/storyboard-v2 && npm run build clean
A-3: Server restart + /api/health 200; PID lstart > .py mtime (Rule 29)
A-4: BG-22 smoke: upload ref → find_asset.py query returns row with
     iteration_notes populated (Layer 4 side-effect capture)
A-5: BG-37 smoke: Accept All → prod_activity_log row BEAT_GEN_ACCEPT_ALL
     with selection_map (Rule 18)
A-6: BG-34/35 smoke: Accept All with 1 unset beat → warn modal lists
     that beat (conditional render)
A-7: CC-17 smoke: switch tier from images → sfx → asset list filters
     meaningfully (Layer 6 — vary input → output changes)
A-8: CC-18 smoke: type "tessa" in search → list narrows to tessa-named
     items (Layer 6)
A-9: CC-19 smoke: hover image library item → preview opens after 500ms
     (Kim hands-on browser smoke; document as DEFERRED if not testable
     in terminal)
A-10: Activity log row S5_5C_PASS2_COMPLETE with full gate summary +
      any spec-vs-reality deviations (per spec §0.9)
A-11: 2 new LDs registered: LIBRARY_TIER_FILTER_V1 +
      BG_ACCEPT_BEATS_ACTIVITY_LOG_V1 — try_post_or_queue read-back
      confirmed (Rule 35)

END-OF-PHASE CHECKLIST (per spec §14):

[ ] All 11 smoke gates above PASS (A-1 through A-11)
[ ] py_compile + npm run build clean
[ ] Server restart + /api/health 200; PID lstart > .py mtime (Rule 29)
[ ] All Directus writes verified via try_post_or_queue read-back
[ ] LD query snapshot present (N/A this phase — no AMEND/SUPERSEDE)
[ ] Rule 36 audit run/skipped with reason documented (N/A — TSX work)
[ ] Explicit evidence artifact links/IDs for each gate captured in
    phase artifacts (file paths, output excerpts, activity_log row IDs)
[ ] "Unresolved inferred claims = 0" check: every [INFERRED — verify]
    annotation per Rule 24 resolved or deferred-with-reason
[ ] Activity log row S5_5C_PASS2_COMPLETE written
[ ] Independent tail-end verifier subagent run; verdict captured
    (per spec §0.6 — recommended pattern, proven in a1/a2/b)
[ ] Browser smoke checklist drafted for Kim hands-on (CC-19 hover
    preview specifically — Kim verifies in browser)
[ ] Phase B handoff stub written:
    Production/docs/V59_S5_5_E_PASS2_HANDOFF.md

ESCAPE-HATCH SURFACE FORMAT (when STOP fires):

Per spec §0.9 deviation logging — write prod_activity_log row
S5_5C_PASS2_DEVIATION_<id> with details: {spec_says, reality_is,
resolution, approved_by}. Surface to Kim with specific reason.
Don't silently substitute.

DEFERRED ITEMS (per spec §10 Out of Scope):

- BG-10 reorder beats (defer to Phase B if needed; otherwise drop)
- BG-11 group beats (DEFER per Kim 2026-05-06)
- BG-16 click-to-upload (SKIP per Kim — drag-drop sufficient)
- BG-38/39 locked mode + re-open (DEFER per Kim — current behavior fine)
- C-11 keyboard shortcuts (SKIP per Q4 LOCKED)

═══ Begin ═══

Run Phase 0 pre-flight now per spec §0.1. Tier A: minimal Phase 0,
write preflight row, skip 4+4 agent spawn (not needed Tier A). Then
execute A1 → A2 → A3 in order. Provide proof of successful execution
after each sub-phase. Report back when all 11 verification gates pass.
═══════════════════════════════════════════════════════════════════
```

---

## Notes for Kim (post-paste)

**Browser smoke gates** — A-9 (CC-19 hover preview) needs your hands-on browser verification. Terminal will defer it as expected per spec §0.10.

**After Phase A reports COMPLETE:**
- 2 new LDs registered + activity log row + Phase B handoff stub written
- You browser-smoke A-9 (CC-19 preview) — confirm or flag
- Then paste Phase B handoff (will exist at `Production/docs/V59_S5_5_E_PASS2_HANDOFF.md`)

**4 phases remain after A:** B → C → D → E. C is the critical one (PB-2 RELEASE-BLOCKER preflight + standardized_assets prep).

---

**End of Phase A handoff.**
