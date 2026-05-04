# V59 S5.5c + S5.5e — Combined Fresh-Terminal Handoff

**For:** Fresh Claude Code terminal session
**Predecessor:** S5.5d-cont (v3 architecture revision shipped 37/37 gates green)
**Specs:**
- `Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md` (master overview)
- `Production/docs/STORYBOARD_V59_S5_5_C_SPEC_v2.md` (S5.5c — Cursor v8 folded)
- `Production/docs/STORYBOARD_V59_S5_5_E_SPEC_v1.md` (S5.5e — Cursor v8 folded)
**Status when authored:** All 5 v59 feature parity docs Cursor v6/v7/v8 reviewed. S5.5c and S5.5e are tightly coupled (e uses c's primitives); combining into one session is the pragmatic choice.

---

## Pre-paste checklist (Kim)

- [ ] Master overview confirmed on disk (~229 lines)
- [ ] S5.5c spec v2 confirmed on disk (~391 lines, ends at §14 Cursor v8 audit trail)
- [ ] S5.5e spec v1 confirmed on disk (~388 lines, ends at §14 Cursor v8 audit trail)
- [ ] (Optional) Cursor v9 cross-review run if you want one more pass; otherwise skip
- [ ] Server fresh post-S5.5d-cont (PID start time > production_server.py mtime)
- [ ] State.json files at v3 shape
- [ ] No GPT/magic/assemble jobs currently running (check via `GET /api/admin/inflight_count`)
- [ ] Fresh terminal window, fresh `claude` session, no prior context
- [ ] cd to project root: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files`

---

## Paste this into the fresh terminal:

```
═══════════════════════════════════════════════════════════════════
You are executing a COMBINED session: S5.5c (Beat Generator + Cropper
+ shared UI primitives) AND S5.5e (Storyboard buttons + ProjectSelector
+ Production Map data) per the v59 feature parity spec arc.

CONTEXT: v3 architecture revision shipped 2026-05-03 over S5.5d +
S5.5d-cont (37/37 gates green; 12 new LDs; 2 supersedes). Browser
smoke surfaced ~3,100-4,400 LOC of v59 Preact client feature gaps —
buttons + UIs that exist as backend endpoints but were never ported.
The plan is 4 sequential bounded sessions: c → e → f → g. This session
combines c + e because they're tightly coupled (e uses c's primitives)
and total scope (~31 gates) is comparable to v3's atomic landing.

LOCKED DECISIONS (do NOT re-debate):
1. v3 architecture is final. These specs build on top of v3.
2. Beat Generator = 3 OPTIONS per beat (NOT 3×3 matrix, NOT 9 stills,
   NOT FLUX). The "grid" is UI layout (1×3), not a matrix. Per
   `BEAT_GEN_3_OPTIONS_NOT_GRID_V1`.
3. Phase B IS Cedric lipsynced (LD-149/196/348). Memory was outdated.
4. Production Map sources from GAMEPLAY_SCOPE_v3.md (V1 scope frozen
   per LD-357: 10 arcs / 59 modules / 6 creatures / 7 stones).
5. v59 Stitcher tab is canonical (S5.5g concern; informational here).
6. Magic compositor cross-platform = OUT of scope.

CURSOR v6 + v7 + v8 ALL FOLDED into v3 spec + master overview + 4
session specs. v3 §14/§15 has v6/v7 audit trails. Each session spec
has §14 Cursor v8 audit trail. No outstanding review work.

OPERATING MODE FOR THIS COMBINED SESSION (mandatory):

- Load the zero-error-qa skill and apply it through every phase.
- Phase 0 pre-flight is mandatory. Classify the task explicitly:
  COMBINED FEATURE BUILD (~31 gates, ~1100 LOC TS new, ~150 LOC
  Python new for one populate script + one ambient_preset_list scan
  endpoint if needed). Spawn appropriate advocate+counter agents per
  Rule 19 (the tech-spec dual-Opus research already happened in
  Desktop on 2026-05-03; reference it as architectural-review
  exemption per LD-124). Write the prod_preflight_reviews row via
  try_post_or_queue BEFORE any edit; reference S5.5d-cont preflight
  #198 as immediate predecessor; confirm via read-back.
- Do not rely on memory or guess. Read every file you reference.
  Re-read at each phase boundary. If reasoning from "what I recall,"
  stop and re-read instead.
- Multipass checks at every step: after each edit, read it back,
  npm run build clean, verify no unintended changes. Confirm
  execution all the way to the tail end of every phase before
  advancing.
- Provide proof of successful execution after each phase: file diffs,
  verification gate output, server restart confirmation, Directus
  write read-back, activity log entry IDs.
- Where the prompt and the spec differ, the SPECS are source of truth.

═══ CRITICAL: COMPACTION-AWARE CHECKPOINT AUTHORITY ═══

This combined session is ~31 gates / ~1100 LOC. That is approximately
the size of v3's atomic landing (which required mid-session checkpoint).
You have EXPLICIT AUTHORITY to write a clean checkpoint handoff and
STOP at the boundary between S5.5c and S5.5e if context is approaching
limits.

The natural checkpoint is: AFTER S5.5c Phase G completes (closeout +
S5_5C_COMPLETE activity log row + git commit) AND BEFORE S5.5e
Phase A begins. At that boundary:
  - All S5.5c files are committed and on disk
  - 17 S5.5c gates green
  - 4 S5.5c LDs registered
  - npm run build clean
  - Server may or may not have been restarted (UI primitives don't
    require restart; Phase B0 catalog work definitely doesn't)

If you choose to halt at that boundary:
  - Write S5.5e continuation handoff at
    `Production/docs/STORYBOARD_V59_S5_5_E_HANDOFF.md` (NOT a "cont"
    handoff — S5.5e was always a separate session in the plan)
  - Write prod_activity_log row `S5_5C_E_CHECKPOINT_AT_C_DONE` noting
    S5.5c shipped clean and S5.5e deferred to fresh session
  - Surface to Kim with explicit reason (context-window or any other
    blocker)

If context is FINE through S5.5c and you have headroom, continue
straight into S5.5e Phase A without checkpoint.

═══ EXECUTION ORDER ═══

S5.5c (Beat Generator + Cropper + shared UI primitives), 17 gates:

- Phase A: Pre-flight (read master overview, S5.5c spec, S5.5e spec,
  v3 spec architecture sections)
- Phase B0 (NEW per Cursor v8): endpoint catalog completeness — extend
  MUTATION_ENDPOINTS / BG_MUTATION_ENDPOINTS / scopeKeyFor for every
  BG/cr POST this session calls; grep gate against raw fetches in
  components
- Phase B: Shared UI primitives — Modal, Toast, Spinner, Select,
  Tooltip, AssetTile in src/components/ui/; src/utils/dragdrop.ts;
  migrate ScopeBanner to Toast
- Phase C: Cropper canvas — replace 1×1 placeholder PNG with real
  canvas + drag handles + aspect lock + library delete UI
- Phase D: Beat Generator tab rewrite — BgTab.tsx 91 → ~600 lines;
  3-options grid (1×3, NOT 3×3); stage-direction chip extraction;
  cost display; Accept All wiring
- Phase E: Verification (17 gates: B0×5 + E×12)
- Phase F: 4 NEW LDs — BEAT_GEN_3_OPTIONS_NOT_GRID_V1,
  CROPPER_CANVAS_REAL_V1, UI_PRIMITIVES_SHARED_V1, DRAG_DROP_HELPER_V1
- Phase G: Closeout (S5_5C_COMPLETE activity log + git commit)

== checkpoint boundary (optional halt point) ==

S5.5e (Storyboard buttons + ProjectSelector + Production Map data),
14 gates:

- Phase A: Pre-flight + GAMEPLAY_SCOPE parser
  - Write Production/scripts/populate_prod_modules_from_gameplay_scope.py
  - --dry-run baseline count, --apply, --validate
  - 53 new prod_modules rows
- Phase B: ProjectSelector — rename EventSelector.tsx →
  ProjectSelector.tsx; grouped Events + Milestones with "+ New
  Milestone"; URL parsing for ?event= / ?milestone=
- Phase C: Storyboard beat button row — regen_audio, preview, animate,
  select, lipsync, use_as_final, beat_delay, beat_trim, inject_image,
  assign_image; state-machine derivation; raw fetch migration for
  Send Out (~L328+); BeatAudioPreview component
- Phase D: Verification (14 gates)
- Phase E: 5 NEW LDs — BEAT_BUTTONS_PORT_V1, PROJECT_SELECTOR_V1,
  PROD_MODULES_GAMEPLAY_SCOPE_SOURCE_V1,
  BEAT_LIFECYCLE_STATE_MACHINE_V1, STORYBOARD_RAW_FETCH_MIGRATED_V1
- Phase F: Closeout (S5_5E_COMPLETE activity log + S5.5f handoff stub
  + git commit)

═══ ESCAPE HATCH (when to STOP and surface) ═══

S5.5c-specific:
- Phase B0 reveals MUTATION_ENDPOINTS catalog incompatibilities with
  pathappPatch typing — STOP, surface
- Cropper canvas implementation hits aspect-ratio math bugs that need
  Kim design input — STOP, surface
- Beat Generator GPT batch endpoint returns shape that doesn't match
  the 3-option spec — STOP, surface (likely backend bug needing fix)
- Modal nested-stack edge case that conflicts with cropperState
  signal — STOP, surface

S5.5e-specific:
- GAMEPLAY_SCOPE_v3.md format unparseable (regex/YAML/markdown
  mismatch with what spec assumes) — STOP, surface; Kim needs to
  confirm format
- prod_modules write fails (schema mismatch, column missing) — STOP,
  surface
- Animation poll endpoint returns format the lifecycle state machine
  doesn't anticipate — STOP, surface
- Send Out raw-fetch migration breaks scene assemble downstream —
  STOP, surface; revert via git checkout

Cross-cutting:
- Compaction approaching at S5.5c/e boundary — write checkpoint
  handoff per CRITICAL section above; STOP cleanly
- Anything triggering Rule 26 Opus Escalation — STOP
- Browser smoke gates cannot be self-tested — DEFER to Kim hands-on;
  do NOT mark session COMPLETE until Kim confirms

═══ READ FIRST, in order ═══

1. Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md
   — bundle context. §11 has Cursor v8 audit trail.
2. Production/docs/STORYBOARD_V59_S5_5_C_SPEC_v2.md
   — S5.5c spec. Read FULLY. §14 has Cursor v8 audit trail. Note
   Phase B0 (NEW) for catalog completeness.
3. Production/docs/STORYBOARD_V59_S5_5_E_SPEC_v1.md
   — S5.5e spec. Read FULLY. §14 has Cursor v8 audit trail. Note
   beat.final (NOT beat.use_as_final) state derivation per Cursor v8
   correction.
4. Production/docs/STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md
   — v3 spec for architecture context. §14/§15 has v6/v7 audit trails.
5. Production/docs/STORYBOARD_V59_S5_5_C_SPEC_v1.md
   — historical reference (v2 supersedes); read only if v2 references
   v1 sections
6. CLAUDE.md Rules 19, 26, 27, 29, 35, 36
7. Production/tools/storyboard-v2/src/api/endpoints.ts
   — current MUTATION_ENDPOINTS catalog; Phase B0 will extend
8. Production/tools/storyboard-v2/src/components/BgTab.tsx
   — current 91-line stub; Phase D rewrites in place
9. Production/tools/storyboard-v2/src/components/StoryboardTab.tsx
   — extends in S5.5e Phase C; raw fetch at ~L328+ (SendOutButton)
10. Production/tools/storyboard-v2/src/components/CropperModal.tsx
    — current 149-line shell; Phase C extends with real canvas
11. Production/tools/production_server.py around line 8627
    (`_handle_bg_extract_beats`) and adjacent BG handlers
12. GAMEPLAY_SCOPE_v3.md (project root) — Phase A2 of S5.5e parses

═══ Scope Summary (combined c + e) ═══

IN SCOPE — S5.5c:
1. Phase B0 (NEW): extend endpoints.ts MUTATION_ENDPOINTS for all
   bg/cr endpoints called this session
2. Shared UI primitives: Modal, Toast, Spinner, Select, Tooltip,
   AssetTile in src/components/ui/
3. Drag-drop helper at src/utils/dragdrop.ts (typed payload union)
4. Cropper canvas: real <canvas>, 8 drag handles, aspect lock, library
   delete UI
5. Beat Generator UI rewrite: 3-options grid (1×3 NOT 3×3),
   stage-direction chips, cost display, Accept All
6. ScopeBanner migration to Toast primitive

IN SCOPE — S5.5e:
1. populate_prod_modules_from_gameplay_scope.py (~150 lines Python)
   - Parses GAMEPLAY_SCOPE_v3.md (canonical V1 scope)
   - POSTs 53 missing prod_modules rows via try_post_or_queue
   - Idempotent: --dry-run / --apply / --validate
2. EventSelector → ProjectSelector rename + grouped optgroups
   (Events / Milestones / + New Milestone)
3. + New Milestone modal with regex validation
4. Storyboard tab beat-level button row:
   - Regen Audio, Preview, Animate, Animate poll, Select option,
     Add options, Lipsync, Lipsync poll, Use as Final, Beat Delay,
     Beat Trim, Inject image, Assign image
5. State-machine derivation from beat.final block presence (NOT
   beat.use_as_final per Cursor v8 fix)
6. Raw fetch migration: StoryboardTab.tsx ~L328+ SendOutButton →
   pathappPatch
7. BeatAudioPreview component using <audio src> with LD-184 fresh
   stream

OUT OF SCOPE (defer to S5.5f / S5.5g / S6):
- Phase A/B feature parity (WaveSurfer, watercolor drag-drop,
  cue popovers, Phase A 3-clip) → S5.5f
- Stitcher SFX/transitions/trims → S5.5g
- StitcherTab + ProductionMapTab raw-fetch migration → S5.5g
  (this session migrates only Send Out)
- Multi-event mapping fix → S5.5g
- Voice profile UI → S6
- Tabs primitive (no caller in c/e) → defer to f/g if needed

═══ CRITICAL CONSTRAINTS ═══

1. Mutation channel: every state write via pathappPatch from
   src/api/client.ts:170. NEVER raw fetch. Phase B0 ensures catalog
   completeness; downstream phases assume types resolve.
2. Asset registration per LD-421/422: every new media write through
   registered_write.register_asset(...). Never raw POST.
3. Strict TypeScript: exactOptionalPropertyTypes=true. New optional
   fields use conditional-spread.
4. Test IDs: every interactive element gets data-testid="<noun>-<context>".
5. `@with_pin_and_drain` decorator (Cursor v8 corrected) is
   server-side PYTHON ONLY in `production_server.py`. There is NO
   TypeScript equivalent. This session does no new heavy server
   handlers, but if you find yourself reaching for it in TS, stop —
   the master overview §6 was clarified.
6. 3 OPTIONS per beat, NOT 3×3 matrix. UI layout is 1×3.
7. beat.final block is the "is final?" signal (Cursor v8 corrected).
   NOT beat.use_as_final boolean.
8. Send Out raw fetch migration target line: ~L328+
   (SendOutButton fetch block in StoryboardTab.tsx). NOT :310.
9. ProjectSelector hides milestone scope path: TargetVideoSelector
   (renamed from VideoSelector text-only — file is still named
   VideoSelector.tsx) auto-resolves to 'standalone' via existing
   v3 wiring.
10. GAMEPLAY_SCOPE_v3.md is canonical V1 scope authority per LD-357.
    populate script mirrors it; never invents.
11. Server staleness check (Rule 29) before any "test it" if any
    Python edits made (likely none in c; possibly 1 small endpoint
    in e for ambient_preset_list — that's actually deferred to S5.5f
    per Cursor v8; verify in spec).
12. Rule 35: every Directus write via try_post_or_queue with read-back.
13. Rule 27: delete the OLD BgTab.tsx stub content; do not leave
    placeholder cards labeled "(S3 polish)".

═══ VERIFICATION GATES (combined: 17 + 14 = 31) ═══

S5.5c: see spec §4 Phase E. Highlights:
- B0.1-B0.5: catalog completeness probes
- E1-E12: build clean + Modal/Toast/Cropper/Beat Gen functional probes
- Beat Generator gates: 3-options layout (1×3), stage chips,
  cost display, Accept All non-empty body

S5.5e: see spec §4 Phase D. Highlights:
- D1-D14: build clean + Production Map ≥ 59 rows + ProjectSelector
  with milestones + each beat-level button functional probe
- D8 Preview freshness probe per LD-184 (modify text → Preview
  returns NEW audio)
- D13 raw-fetch migration verified via Network tab

═══ END-OF-SESSION DELIVERABLES ═══

If both S5.5c and S5.5e ship clean (all 31 gates):
- Final activity_log rows: S5_5C_COMPLETE + S5_5E_COMPLETE
- Handoff stub for S5.5f at
  Production/docs/STORYBOARD_V59_S5_5_F_HANDOFF.md
- Master overview table updated (S5.5c + S5.5e = COMPLETE)
- Tail-end verifier subagent (covers cross-session: c primitives
  used by e correctly)
- Browser smoke deferred to Kim with combined walkthrough
- Two git commits (one per session) OR one combined commit per Kim
  preference (default: TWO — preserves session boundaries)

If checkpoint at S5.5c/e boundary:
- S5_5C_COMPLETE activity log row
- S5.5e handoff at STORYBOARD_V59_S5_5_E_HANDOFF.md (write fresh,
  reference S5.5e spec)
- prod_activity_log row S5_5C_E_CHECKPOINT_AT_C_DONE noting deferral
- One git commit (S5.5c only)
- Surface to Kim with reason (compaction or other blocker)

If escape hatch fires mid-session:
- Document state at point of stop in prod_activity_log
- Surface to Kim with specific reason + decision request

═══ DIRECTUS REGISTRATION (Phase 0, before any edit) ═══

Use try_post_or_queue per Rule 35; consult schema reference doc.

prod_preflight_reviews:
- 1 row at session start: task_id="s5_5ce-combined-20260503",
  task_type=feature_build, approved_to_proceed=true,
  related_activity_log_id=<TBD after Phase 0 first activity row>;
  references S5.5d-cont preflight #198 as immediate predecessor

prod_reference_docs (verify all 5 already registered from prior
sessions; PATCH is_current as needed):
- Master overview, S5.5c v2 spec, S5.5e v1 spec — should already be
  current=true from prior session work; verify

═══ Begin ═══

Run Phase 0 pre-flight now via zero-error-qa. Register the
prod_preflight_reviews row + initial prod_activity_log row. Then
execute S5.5c spec §4 Phases A through G in order, then (if not
checkpointing) S5.5e spec §4 Phases A through F in order. Provide
proof of successful execution after each phase. Report back when
all 31 gates pass + both Phase G/F closeouts complete OR a clean
checkpoint is written at the c/e boundary.
═══════════════════════════════════════════════════════════════════
```

---

## Notes for Kim (post-paste)

**Browser smoke (deferred to Kim):**

After terminal reports done, exercise the v59 client at
`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tools/storyboard-v2/dist/index.html`:

S5.5c smoke (~5 min):
1. Beat Generator tab: Extract Beats → spinner → beat list. Click "Generate 3 options" on a beat → 3 thumbnails appear in 1×3 layout (NOT 9 cells). Select option → marked. Stage-direction chips render from `(text)` patterns. Cost display updates.
2. Cropper modal: open → load image → drag rect → save. Verify the resulting PNG is REAL cropped data (not 1×1 placeholder). Hover library tile → [✕] delete button appears.
3. Toast primitive: trigger 3 toasts → stack visible → auto-dismiss after 5s.

S5.5e smoke (~5 min):
1. Production Map tab: see all 59 V1 modules across 10 arcs (currently shows only M1-M6).
2. ProjectSelector dropdown: see Events grouped + Milestones grouped + "+ New Milestone" CTA.
3. + New Milestone modal: enter `_BAD` → rejected. Enter `valid_id` → accepted; milestone scope loads; TargetVideoSelector hidden; Phase A/B tabs disabled.
4. Storyboard tab beat row: per-beat buttons render conditionally per state machine. Click Regen Audio → audio file refreshes. Click Preview → fresh `<audio>` plays. Modify text + Preview → NEW audio (LD-184 freshness). Animate (test on one beat) → status polls → 3 options. Select option → marked. Lipsync → status polls. Use as Final → `beat.final` block written.

**Cursor v9 (optional):** Skipped per recommendation. v6/v7/v8 already caught the structural gaps. v9 would mostly nitpick.

**Compaction-aware checkpoint:** If terminal halts at S5.5c/e boundary, you'll get a fresh handoff for S5.5e at `Production/docs/STORYBOARD_V59_S5_5_E_HANDOFF.md`. Same paste pattern; smaller scope (just S5.5e).

**S5.5f handoff stub** is written at session-end if both c and e ship. That's the next session in the arc (Phase A/B feature parity).

**Two git commits expected** (one per session) preserving boundaries — same pattern as S5.5d + S5.5d-cont.

---

**End of S5.5c+e combined handoff.**
