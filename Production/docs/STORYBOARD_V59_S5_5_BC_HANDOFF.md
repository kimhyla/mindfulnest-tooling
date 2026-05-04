# S5.5b + S5.5c Combined Terminal Handoff — v59 Storyboard Rewrite

**Date authored:** 2026-05-03 (parallel to S5.5a2 execution)
**For:** Fresh terminal Claude Code session, AFTER S5.5a2 reports clean
**Order within session:** S5.5b FIRST, then S5.5c
**Hard gate:** all 13 b verification gates must pass before c starts
**Escape hatch:** if b surfaces any surprise not anticipated by spec,
STOP and surface to Kim — c is parked, awaiting separate session

---

## Pre-paste checklist (Kim does this BEFORE pasting)

- [ ] S5.5a2 has reported `S5_5A2_COMPLETE` with all 13 verification gates
      passed
- [ ] `Production/Event_*/production_state.json` files are at `version=v2`
      with `videos.{intro|phase_a|phase_b|win}` partitions present
- [ ] Server is running fresh post-a2 (Rule 29 fresh)
- [ ] Fresh terminal window, fresh `claude` session, no prior context

If any are unchecked: do NOT paste this yet. Get a2 to clean state first.

---

## Paste this into the fresh terminal:

```
═══════════════════════════════════════════════════════════════════
You are continuing the v59 storyboard rewrite. This combined
session executes Sub-Sessions S5.5b (bug fixes + VideoSelector +
GET /api/event/current) and S5.5c (Beat Generator UI build) in
sequence. S5.5a1 + S5.5a2 (foundation + atomic migration + handler
refactor) shipped clean — full state.json migration applied to v2
shape; ~30 handlers refactored to videos.<role> partition; scope
token includes scope_video_role; LD-473/474/475 enforced.

OPERATING MODE FOR THIS SESSION (mandatory):

- Load the zero-error-qa skill and apply it through every phase.
- Phase 0 pre-flight is mandatory. Classify the task explicitly:
  TWO sub-tasks within one session, both EXECUTION (not
  architectural research). S5.5b is bug-fix sweep + 1 endpoint
  + 1 UI component (Tier B). S5.5c is feature build on locked
  architecture (Tier B). Spawn appropriate advocate+counter
  agents per Rule 19 (Cursor v5 + spec authoring may serve as
  architectural-review exemption per LD-124 — same pattern S5.5a1
  and S5.5a2 used; document the exemption regardless). Write the
  prod_preflight_reviews row via try_post_or_queue BEFORE any
  edit; confirm via read-back.
- Do not rely on memory or guess. Read every file you reference.
  Re-read at each phase boundary. If you find yourself reasoning
  from "what I recall," stop and re-read instead.
- Multipass checks at every step: after each edit, verify the
  edit landed (read it back), verify the surrounding code still
  parses (py_compile, npm run build), verify no unintended
  changes. Confirm execution all the way to the tail end of every
  phase before advancing.
- Provide proof of successful execution after each phase and at
  the end: file diffs, verification gate output, server restart
  confirmation, Directus write read-back, activity log entry IDs.
- Where the prompt and the specs differ, the SPECS are source of
  truth (same protocol as S5.5a1 + S5.5a2).

EXECUTION ORDER (strict):

PART 1 — Execute S5.5b in full (Phases A–E)
PART 2 — HARD GATE: all 13 b verification gates pass
PART 3 — Execute S5.5c in full (Phases A–E)

If any S5.5b gate fails or Phase A surfaces a surprise not
anticipated by the spec: STOP after S5.5b. Write the S5.5c
handoff stub for next session. Do NOT begin S5.5c work.

ESCAPE HATCH (when to stop and surface to Kim):

- Bug-status audit (b Phase A) surfaces a bug whose Cursor v5
  root cause no longer matches current behavior — STOP, surface
- A bug fix breaks an unrelated test — STOP, surface
- VideoSelector POST fails on every role (a2 helper broken) —
  STOP, surface
- Endpoint audit in c Phase A finds a backend gap that requires
  new architecture — STOP, surface
- Anything else that triggers Rule 26 Opus Escalation (cross-
  system architectural decision, conflicting authorities,
  repeated frustration signal, etc.) — STOP, surface

Read these FIRST, in order:

1. Production/docs/STORYBOARD_V59_S5_5_B_SPEC_v1.md
   — executable spec for PART 1. Source of truth for b.
2. Production/docs/STORYBOARD_V59_S5_5_C_SPEC_v1.md
   — executable spec for PART 3. Source of truth for c.
3. Production/docs/STORYBOARD_V59_S5_5_A2_HANDOFF.md
   — what S5.5a2 left on disk (pre-conditions for both b and c)
4. Production/docs/STORYBOARD_V59_S5_5_A1_SPEC_v2.md
   — original architectural spec (s5.5a1 lineage)
5. Production/docs/STORYBOARD_V59_SPEC_v3_1.md
   — canonical architecture (Sessions 1.5-5 lineage)
6. CLAUDE.md Rules 19, 26, 27, 29, 35, 36
   — no-shortcuts, Opus escalation, delete obsolete workarounds,
   server staleness check, Directus schema verification, patch
   invariant persistence

═══ PART 1 — S5.5b ═══

Scope (per S5.5b spec §1):

IN SCOPE:
- Bug 1: storyboard image scrambling on event swap
- Bug 2: stitcher persistence/shape mismatch
- Bug 3: magic POST scope_video_role plumbing
- Bug 4: EventSelector page reload doesn't propagate to ScopeBoundary
- Bug 6: stitch job persistence
- New endpoint: GET /api/event/current
- New endpoint: POST /api/video/set_active
- New component: VideoSelector (Preact TSX in
  Production/tools/storyboard-v2/)

OUT OF SCOPE (deferred):
- WaveSurfer.js timeline (LD-472) — Session 6
- Beat Generator UI — that's PART 2
- Stitch job retry logic — V2
- Per-event-per-video Playwright matrix expansion — defer

Critical for b:

1. Phase A (bug-status audit) is BLOCKING. Several bugs may
   already be resolved by a1+a2. DO NOT patch what's not
   reproducing. Write the audit table to
   Production/docs/STORYBOARD_V59_S5_5_B_BUG_STATUS.md before
   any fix.
2. Where the bug audit shows current behavior diverges from
   Cursor v5 root cause, surface to Kim — do not silently
   substitute another fix.
3. Bug 4 fix should land BOTH approaches: GET /api/event/current
   endpoint AND ?event= URL navigation in EventSelector. Belt +
   suspenders per spec §3 Bug 4.
4. VideoSelector reads state.active_video as DISPLAY HINT only;
   partition selection in mutating handlers MUST come from
   body['scope_video_role'] (LD-474, never violated).
5. Server staleness check before any "test it" — Rule 29.

S5.5b verification gates (all 13 must pass before PART 2 starts):

1. ✅ Bug status table written + reviewed
2. ✅ All STILL REPRODUCES bugs marked RESOLVED in
   prod_activity_log via BUG_FIX_<bug_id> rows
3. ✅ python3 -m py_compile Production/tools/production_server.py
4. ✅ cd Production/tools/storyboard-v2 && npm run build clean
5. ✅ Server restart; /api/health 200
6. ✅ GET /api/event/current returns expected shape (200 with
   loaded event; 200 with {event_id: null} on cold boot)
7. ✅ POST /api/video/set_active accepts valid roles + 400s on
   invalid
8. ✅ Smoke test: load Event_1 → switch to phase_a video role
   → tabs show phase_a partition data → switch to phase_b →
   tabs update → switch event to Event_2 → state preserved
   per-event
9. ✅ Bug 1 retest: Event_1 → Event_2 → Event_1 storyboard
   images intact, no cross-event contamination
10. ✅ Bug 4 retest: EventSelector change → page reload →
    ScopeBoundary picks up new event correctly
11. ✅ Stitch job persistence: initiate stitch job → restart
    server → tab on reload shows the job in correct state (Bug 6)
12. ✅ prod_activity_log row S5_5B_COMPLETE with full gate
    summary
13. ✅ 2 new LDs registered (VIDEO_SELECTOR_V1 +
    EVENT_CURRENT_ENDPOINT_V1) + LD-474 PATCHed; read-back
    confirmed

═══ HARD GATE ═══

Confirm all 13 above pass with proof artifacts. If yes, proceed
to PART 2. If no, STOP — write S5.5c handoff stub for next
session, do NOT begin c work, surface to Kim.

═══ PART 2 — S5.5c ═══

Scope (per S5.5c spec §1):

IN SCOPE (Option B+ per Kim's confirmation):
- New tab: BeatGeneratorTab.tsx in
  Production/tools/storyboard-v2/src/tabs/
- Per-beat character ref + BG ref upload slots (1 char + 1 BG
  per beat, port from patch_storyboard_v42.py)
- 3-option GPT grid generation per beat (gpt-image-2 per LD-440,
  image-led ~380-char prompt per LD-439, 3 calls varied via seed)
- Dialogue editor with stage-direction extraction chips (regex
  \(([^)]{4,50})\), max 2)
- Add/delete beats
- Cost display (per-gen toast + session running total)
- Accept All button (validates all beats selected, advances
  pipeline_stage, locks tab)

OUT OF SCOPE:
- GPT mode toggle — cut per Kim
- 9-stills-per-beat / 3×3 grid — cut per Kim 2026-05-02
- FLUX Kontext path — cut (LD-440 locks gpt-image-2 only for
  Beat Generator)
- Bulk operations (multi-beat select-and-generate)
- History/diff UI for prior generations
- Image editing within the tab
- Animation hooks ("Animate this" stays on watercolors)

Critical for c:

1. Phase A is a backend audit FIRST. Per session memory:
   "Server endpoints exist. UI port only." But VERIFY each of
   the 6 endpoints listed in spec §3.3. For any TO ADD endpoint:
   build using existing patterns (_assert_event_scope,
   _check_event_pin, LD-474 scope_video_role propagation).
2. Use the canonical prompt builder build_gpt_still_prompt() at
   beat_generator.py:934-947. DO NOT reimplement the prompt.
3. State shape additions are ADDITIVE to videos.<role>.beats[
   beat_id] — 4 new sub-fields (refs, gen_options,
   selected_option_id, stage_directions). Backwards compatible
   with absent fields. NO migration required.
4. All ref uploads + generated stills go through
   registered_write.py per LD-421 / LD-422; iteration_notes
   captured at production-time.
5. VideoSelector from PART 1 is a hard dependency — Beat
   Generator tab respects active video role from VideoSelector.
   If PART 1 stopped before VideoSelector built, PART 2 cannot
   proceed (escape hatch fires).

S5.5c verification gates (all 8 must pass at end):

1. ✅ python3 -m py_compile Production/tools/production_server.py
2. ✅ cd Production/tools/storyboard-v2 && npm run build (no TS
   errors)
3. ✅ Server restart; /api/health 200
4. ✅ All 6 endpoints in spec §3.3 respond with expected shape
   (curl probes)
5. ✅ Dev server loads BeatGeneratorTab; full smoke test per
   spec §4 Phase D step 5 (upload refs → type stage direction
   → generate 3 → select → add beat → delete → accept all)
6. ✅ find_asset.py query returns the generated stills + refs
7. ✅ prod_activity_log row S5_5C_COMPLETE written
8. ✅ S5.5b/c COMBINED handoff to S6 prep written

═══ END-OF-SESSION DELIVERABLES ═══

If both PART 1 and PART 2 ship clean:

- Final activity_log row: S5_5BC_COMBINED_COMPLETE with full
  21-gate summary (13 b + 8 c)
- Handoff stub for S6 (parallel-run on Event_2 + cutover): write
  to Production/docs/STORYBOARD_V59_S6_HANDOFF.md
- Summary report to Kim: which bugs were already resolved by
  a1+a2, which fixes shipped, what VideoSelector + Beat
  Generator look like, any deviations from specs (with
  justification)

If PART 1 shipped but PART 2 stopped per escape hatch:

- Final activity_log row: S5_5B_COMPLETE_C_DEFERRED
- Handoff for c rewrite: update
  Production/docs/STORYBOARD_V59_S5_5_C_HANDOFF.md (NEW) with
  current state + reason for deferral
- Surface to Kim with specific reason

═══ Begin ═══

Run Phase 0 pre-flight now via zero-error-qa. Then execute PART 1
S5.5b spec Phases A–E in order. Provide proof of successful
execution after each phase. At hard gate, list all 13 b gates
with status. If green, proceed to PART 2 S5.5c spec Phases A–E.
Report back when all 21 verification gates pass.
═══════════════════════════════════════════════════════════════════
```

---

## After this session

Per the spec lineage, this completes S5.5 (a1 ✓, a2 ✓ when terminal
returns, b + c ✓ when this session returns). Next is **S6** — Kim's
parallel-run module on Event_2 + cutover decision. S6 needs no
handoff from Desktop; it's hands-on testing work.
