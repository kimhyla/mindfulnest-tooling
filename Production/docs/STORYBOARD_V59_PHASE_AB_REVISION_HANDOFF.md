# V59 Phase A/B Architecture Revision — Fresh-Terminal Handoff (v3)

**For:** Fresh Claude Code terminal session
**Predecessor:** Desktop tech-spec session 2026-05-03 (v1 → v2 → v3 cycles)
**Spec:** `Production/docs/STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md` (v1 + v2 superseded)
**Lessons:** `LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md`
**Status when authored:** v3 spec complete; Cursor v6 + v7 findings folded; Kim's 4 locked decisions all in v3; ready for atomic single-session execution

**Locked decisions (all baked into v3):**
1. **Decision 1 = A:** Build Option A export pipeline (`/api/beat/finalize` + `/api/scene/assemble` with `finalize_args_hash` cache + per-beat `beat_scene` assets)
2. **Decision 2 = B:** Supersede LD-473 + LD-474 (vs amend)
3. **Decision 3 = re-bake:** LD-284 strict spec; align live `lib/ffmpeg_stitch.py` to LD; LD itself unchanged
4. **Decision 4 = A:** Drain timeout policy = pre-flight enumeration with explicit abort. No auto-timeout for thread-tracked jobs. 60s polling fallback only for sync residue.

---

## Pre-paste checklist (Kim)

- [ ] v3 spec confirmed on disk: `Production/docs/STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md`
- [ ] (Optional) Cursor v8 cross-review of v3 spec — spec §13 has 10 questions. Skip unless you want another pass.
- [ ] Server fresh post-S5.5b (PID start time > production_server.py mtime)
- [ ] State.json files at v2 shape (post-S5.5a2 + S5.5b)
- [ ] No GPT/magic/assemble jobs currently running (the drain pre-flight will refuse to proceed if any are active)
- [ ] Fresh terminal window, fresh `claude` session, no prior context

If any unchecked: do NOT paste yet.

---

## Paste this into the fresh terminal:

```
═══════════════════════════════════════════════════════════════════
You are executing the v59 Storyboard Phase A/B Architecture Revision
per the v3 spec (Cursor v6 + v7 reviews folded; all 4 of Kim's locked
decisions baked in).

CONTEXT: S5.5a1, S5.5a2, S5.5b shipped clean over 2026-05-03 (~110 min
total terminal time, all gates + bonus verifier subagents passed).
Browser smoke 2026-05-03 surfaced architectural design gap. Tech-spec
dual-Opus debate produced v1. Cursor v6 caught 2 release-blockers + 9
amendments → v2. Cursor v7 caught 2 NEW release-blockers (Stage 2
pipeline didn't actually crossfade; drain protocol vs daemon threads)
+ 12 amendments → v3. v3 is source of truth; v1 + v2 are historical
reference only.

This session executes the v3 revision atomically in a single terminal
session per Q3=A directive.

OPERATING MODE FOR THIS SESSION (mandatory):

- Load the zero-error-qa skill and apply it through every phase.
- Phase 0 pre-flight is mandatory. Classify the task explicitly:
  ARCHITECTURAL revision (state shape change + ~6 server handler
  reverts + 9 NEW endpoints + ~12 client file changes + 2 new client
  tab files + 12 new LDs + 5 amendments + 2 supersedes + 2 PATCHes
  + 1 code-spec alignment of lib/ffmpeg_stitch.py + 1 decorator
  refactor wrapping 14 sync handlers + 4 thread-spawning handlers).
  Spawn appropriate advocate+counter agents per Rule 19 (the tech-spec
  dual-Opus research already happened in Desktop on 2026-05-03 over
  three cycles; reference it as architectural-review exemption per
  LD-124, same pattern S5.5a1/a2 used). Write the prod_preflight_reviews
  row via try_post_or_queue BEFORE any edit; reference preflight #196
  (S5.5b) as immediate predecessor; confirm via read-back.
- Do not rely on memory or guess. Read every file you reference.
  Re-read at each phase boundary. If reasoning from "what I recall,"
  stop and re-read instead.
- Multipass checks at every step: after each edit, read it back,
  py_compile / npm run build, verify no unintended changes. Confirm
  execution all the way to the tail end of every phase before
  advancing.
- Provide proof of successful execution after each phase: file diffs,
  verification gate output, server restart confirmation, Directus
  write read-back, activity log entry IDs.
- Where the prompt and the spec differ, the SPEC v3 is source of truth.
  Where the spec and Cursor v8 findings differ (if Kim ran v8), Cursor
  v8 findings win (Kim incorporates them before paste).

CURSOR V6 + V7 STATUS:

ALREADY INCORPORATED into v3 spec. v3 §14 has the v6 audit trail; §15
has the v7 audit trail. No outstanding v6 or v7 work remains.

[CURSOR V8 NOTES — fill in if Kim ran another review pass]:
None at time of handoff authoring (v8 review optional per Kim).

EXECUTION ORDER (atomic, single session):

Per v3 spec §4 Phases A through G, in order:
- Phase A: Pre-flight + reverse migration script with tightened
  is_already_migrated() 7-field invariant (read-only / dry-run)
- Phase B0: Pre-revert win literal audit — verify exactly 5 server
  + 1 client actual-role win literals
- Phase B (B1-B19): Symbol-based handler reverts + win literal rename
  + delete obsolete partition init code per Rule 27 +
  _handle_use_as_final role parameterization + 9 NEW endpoints
  (4 milestones + 3 admin/drain + 2 export pipeline) + decorator
  @with_pin_and_drain wrapping 14 sync handlers + 4 thread-spawning
  handlers + DELETE old _handle_export + B16 codec alignment
  (lib/ffmpeg_stitch.py to LD-284 strict) + B17 app._sync_inflight
  registry + B18 py_compile + B19 restart
- Phase C: Drain protocol pre-apply (drain_start → enumerate
  inflight_count → ABORT with explicit list if non-empty;
  60s polling for sync residue fail-closed) → migration apply
  → drain_end
- Phase D: v59 client restructure (12+ files + 2 new tabs +
  activeTargetVideo resolves to 'standalone' in milestone scope)
- Phase E: Verification (37 gates — adds E33 codec alignment,
  E34 milestone scene/assemble, E35 xfade parity vs preview-stitched,
  E36 re-send distinct row, E37 drain-during-active-job)
- Phase F: 12 new LDs + 2 supersedes (LD-473, LD-474) + 5 amendments
  + 2 PATCHes (LD-139, LD-460); LD-284 NOT PATCHed (code aligned
  to LD-284 strict spec instead per Phase B16)
- Phase G: Closeout (activity log + S6 handoff stub + final tail-end
  verifier subagent + register v3 spec + lessons in prod_reference_docs;
  PATCH v1 + v2 specs to is_current=false)

ESCAPE HATCH (when to STOP and surface to Kim):

- Cursor v8 notes section non-empty and conflicts with v3 — STOP
- Reverse migration script dry-run reveals state.json shape doesn't
  match expected v2 — STOP
- Migration key collision (top-level phase_a_<key> already present
  with different value than videos.phase_a.<key>) — STOP
- Drain pre-flight returns inflight_count > 0 — ABORT migration
  (do NOT proceed); show the list to Kim with format:
    [gpt] gpt-stills:<id> (3/9)
    [magic] magic:<scene_key> (rendering_video)
    [assemble] assemble:group=<gid>
    [lipsync] lipsync:intro:beat_03 (polling)
    [sync] _handle_stitch_bake
  Kim waits or kills, retries.
- Drain 60s sync residue timeout — STOP; abort migration; surface
  active list
- Handler revert breaks py_compile — STOP
- Phase D client restructure surfaces TS errors — STOP
- LD-412 phase_boundaries doesn't accept "resolution" — STOP
- /api/beat/finalize cache miss + ffmpeg fails on E17 — STOP
- /api/scene/assemble SIZE_BUDGET violation on E18 — STOP
- ffmpeg_stitch.py codec alignment edit (B16) produces py_compile
  failure or unexpected NORMALIZATION_RECIPE_HASH — STOP
- E35 xfade parity gate FAILS (scene/assemble parts list differs
  from preview-stitched parts list for same input) — STOP, surface;
  this signals the Stage 2 pipeline didn't correctly mirror
  preview-stitched (Cursor v7 Beyond #1 fix incomplete)
- @with_pin_and_drain decorator application breaks any handler
  contract — STOP, surface (especially: don't apply track_sync=True
  to read-only/poll endpoints; they MUST stay responsive during drain)
- Anything triggering Rule 26 Opus Escalation — STOP
- Browser smoke gate E19 cannot be self-tested — DEFER to Kim
  hands-on; do NOT mark session COMPLETE until Kim confirms

Read these FIRST, in order:

1. Production/docs/STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md
   — executable spec for THIS session. SOURCE OF TRUTH. Read FULLY.
   §14 has Cursor v6 audit trail; §15 has Cursor v7 audit trail;
   §13 has the optional Cursor v8 checklist (skip unless Kim ran v8).
2. LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md
   — 25 lessons from prior sessions
3. Production/docs/STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v2.md
   — historical reference ONLY (v3 supersedes)
4. Production/docs/STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v1.md
   — historical reference ONLY (v3 supersedes)
5. Production/docs/STORYBOARD_V59_S5_5_B_HANDOFF.md
   — what S5.5b shipped (current pre-revision state)
6. Production/docs/STORYBOARD_V59_S5_5_A2_HANDOFF.md
   — what S5.5a2 shipped
7. Production/docs/STORYBOARD_V59_S5_5_A1_SPEC_v2.md
   — original architectural spec (with conceptual oversight)
8. Production/docs/STORYBOARD_V59_SPEC_v3_1.md
   — canonical architecture
9. CLAUDE.md Rules 19, 26, 27, 29, 35, 36
10. Production/scripts/migrate_state_to_videos_partition.py
    — original migration script
11. Production/tools/lib/ffmpeg_stitch.py
    — canonical primitives. v3 Stage 2 uses ALL of:
      - normalize_for_concat (line 237)
      - trim_normalized (line 317)
      - trim_body (line 338)
      - render_xfade_pair (line 454)
      - concat_with_xfade_clips (line 510, stream-copy concat at end)
      - resolve_pair_fades (line 701)
      - compute_fade_clamp_per_pair (line 722)
      - compute_cache_hash (line 624) — TEMPLATE for compute_finalize_args_hash
12. Production/tools/registered_write.py
    — asset registration; v3 ADDs scene_concat_mp4 to
    _ACCEPTED_ASSET_TYPES (line 42-61)
13. Production/tools/production_server.py
    — must-read before B16: lines 11862-12210 (_handle_preview_stitched
    is the orchestration template Stage 2 mirrors)

═══ Scope Summary (from v3 spec §1) ═══

IN SCOPE:
1. Reverse migration: lift state.videos.phase_a/b back to top-level
2. Server handler reverts: SYMBOL-based — includes
   _auto_assemble_phase_a_stitched and StateManager._init_files
3. Naming: rename videos.win → videos.resolution, with explicit
   Phase B0 win-literal audit
4. Tab restructure: Phase A and Phase B as top-level tabs;
   production-order tabs
5. Milestone (standalone) concept: Production/Milestones/<id>/state.json
6. TargetVideoSelector: rename + restrict to {intro, resolution};
   milestone scope → 'standalone' (NOT null)
7. ProjectSelector: extends EventSelector with milestones
8. NEW EXPORT PIPELINE (v3 Stage 2 mirrors _handle_preview_stitched):
   - POST /api/beat/finalize with finalize_args_hash cache
     (excludes fade_after_ms + pause_after_ms — Stage 2 concerns)
   - POST /api/scene/assemble with pairwise render_xfade_pair +
     trim_body + interleaved parts list + stream-copy concat
   - Wires pause_after_ms (currently dead metadata) via silent
     black filler clips at LD-284 codec recipe
   - Per-beat MP4s registered as 'beat_scene' assets
   - Concat MP4 registered as 'scene_concat_mp4' asset type
   - DELETE old _handle_export per Rule 27 (replaced with HTTP 410)
9. NEW DRAIN PROTOCOL (derives from existing registries; NO new
   parallel registry):
   - Existing _GPT_JOBS, _MAGIC_JOBS, _ASSEMBLE_JOBS = thread-tracked
   - app._sync_inflight: set[str] (NEW, lock-protected) for sync
     handlers
   - State-scan for lipsync (special case — lives in state.beats)
   - Decorator @with_pin_and_drain replaces 17 boilerplate sites
   - Pre-flight enumeration: drain_start → if inflight_count > 0,
     ABORT with explicit list; otherwise 60s sync residue poll
10. Bonus fix: _handle_use_as_final role parameterization
11. LD-284 CODE ALIGNMENT: edit lib/ffmpeg_stitch.py:47-59 to
    -preset slow + setsar=1:1 + -g 48
12. LD work: 12 new + 2 supersedes + 5 amendments + 2 PATCHes;
    LD-284 NOT PATCHed (code aligned instead)

OUT OF SCOPE:
- WaveSurfer.js timeline (LD-472)
- Beat Generator UI build (S5.5c)
- Per-event-per-target Playwright matrix expansion
- Stitcher 1-slot UI polish
- Phase A/B history/diff UI
- Multiple milestones per single milestone scope
- Long-term pinned_video_role enforcement
- Job registry leak fix (LRU/TTL) — documented smell, deferred
- _handle_bg_submit_flux thread-ification — deferred

═══ Critical constraints (do NOT violate) ═══

1. Atomic landing: migration + handler reverts + client restructure
   + new endpoints + decorator + codec align ALL ship in same session
2. Snapshot before mutation: per-event state.json snapshotted to
   .backups/state/<TS>_pre_phase_revision.json BEFORE any write
3. _VALID_VIDEO_ROLES becomes {intro, resolution, standalone}
4. Component preservation per LD-421/422 + STORYBOARD_SEND_OUT_PROVENANCE_V1:
   beat MP4s registered as 'beat_scene'. Re-send creates new
   scene_concat_mp4 row alongside, doesn't destroy sources.
   Provenance lives in iteration_notes + source_beat_asset_ids list,
   NOT parent_asset_id (which stays null).
5. Server staleness check (Rule 29) before any "test it"
6. Rule 35: every Directus write consults schema reference;
   uses try_post_or_queue with read-back
7. Rule 27: delete OLD videos.phase_a/b partition init code AND
   v1 _handle_export JSON-manifest writer (lines 10999-11069)
8. registered_write.py is at Production/tools/registered_write.py
   (NOT scripts/)
9. **Stage 2 MUST mirror _handle_preview_stitched** at
   production_server.py:11862-12210. Do NOT mirror
   _handle_canonical_stitch (it has cumulative-offset xfade drift).
   The misnamed concat_with_xfade_clips IS used at the end as
   stream-copy concat of an interleaved parts list
   [body_0, pair_01, body_1, pair_12, body_2, ..., body_N].
10. **Drain protocol does NOT invent a parallel registry.** Derives
    from existing _GPT_JOBS / _MAGIC_JOBS / _ASSEMBLE_JOBS +
    app._sync_inflight + state-scan for lipsync.
11. **Drain pre-flight ABORTS migration if inflight_count > 0**
    (Decision 4 = Option A). No auto-timeout for thread-tracked jobs.
    60s sync residue poll only.
12. **@with_pin_and_drain decorator** wraps 14 drain-critical sync
    handlers (track_sync=True) + 4 thread-spawning handlers
    (track_sync=False). NOT applied to read-only/poll endpoints
    — they MUST stay responsive during drain.
13. **pause_after_ms wiring is NEW in v3.** Insert silent black filler
    clips between body and pair clips at LD-284 codec recipe.
    Without this, the field stays orphaned (current code's behavior).
14. LD-284 RE-BAKE locked: code in lib/ffmpeg_stitch.py:47-59 MUST be
    aligned to -preset slow + setsar=1:1 + -g 48. LD-284 itself NOT
    PATCHed. NORMALIZATION_RECIPE_HASH bumps; cache invalidates;
    next /api/scene/assemble re-bakes from source. If you discover
    any divergence between code post-edit and LD-284 text, STOP.

═══ Verification gates (all 37 from v3 spec §4 Phase E) ═══

See v3 spec §4 Phase E for complete list. Summary:
- E1-E4: Migration validate, py_compile, npm build, server restart
- E5-E12: Endpoint shape probes (event/current, video/list,
  video/set_active, video/create, milestones/create incl. invalid-id
  400, milestones/load, project/list)
- E13-E16: State shape probes (Event_1 + Event_2; functional probes
  for phase_a/phase_b top-level reads/writes)
- E17-E18: PIPELINE PROBES (beat/finalize cache hit/miss,
  scene/assemble end-to-end with completed_mp4_path write)
- E19: Browser smoke (DEFERRED to Kim hands-on) — ONLY browser
  gate; E25 is tab structure audit (different)
- E20-E25: LD-474 audit + cache-clear log + Bug 1 retest +
  snapshots sha256 + _VALID_VIDEO_ROLES audit + tab structure +
  win-literal grep
- E26-E27: COMPONENT PRESERVATION (Cursor R5)
- E28: DRAIN PROTOCOL (Cursor Q9)
- E29: ROLE-LITERAL GREP (Cursor Q9)
- E30-E32: Stitcher mode auto-detect + find_asset.py preserved +
  activity log row written
- E33: CODEC ALIGNMENT — verify ffmpeg_stitch.py:47-59 has
  -preset slow + setsar=1:1 + -g 48 + new NORMALIZATION_RECIPE_HASH
- E34: NEW v3 — milestone scene/assemble end-to-end
- E35: NEW v3 — XFADE PARITY: scene/assemble parts list IDENTICAL
  (by sha256 per part) to preview-stitched for same input
- E36: NEW v3 — re-send produces distinct scene_concat_mp4 row
  with different assemble_hash
- E37: NEW v3 — drain rejects new work (503) while threaded job
  runs; resumes after drain_end

═══ End-of-session deliverables ═══

If Phase G ships clean:
- Final activity_log row: S5_5D_PHASE_AB_REVISION_COMPLETE with
  full 37-gate summary + Cursor v6/v7/v8 incorporation notes +
  NORMALIZATION_RECIPE_HASH old/new
- Handoff stub for S6: Production/docs/STORYBOARD_V59_S6_HANDOFF.md
- Update Production/docs/STORYBOARD_V59_S5_5_C_HANDOFF.md
- Summary report to Kim

If escape hatch fires:
- Document state at point of stop in prod_activity_log
- Surface to Kim with specific reason + decision request

═══ Directus registration tasks (Phase 0, before any edit) ═══

Use try_post_or_queue per Rule 35; consult schema reference doc.

1. Production/docs/STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md
   doc_category: spec
   has_locked_decisions: true
   is_current: true
   doc_title: "Storyboard v59 Phase A/B Architecture Revision Spec v3"

2. LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md
   doc_category: lessons_learned
   has_locked_decisions: false
   is_current: true
   doc_title: "Lessons Learned 2026-05-03 v59 Architecture Revision"

3. PATCH STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v2.md (if registered)
   → is_current: false
   doc_title: "Storyboard v59 Phase A/B Architecture Revision Spec v2
   (SUPERSEDED by v3)"

4. PATCH STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v1.md (if registered)
   → is_current: false
   doc_title: "Storyboard v59 Phase A/B Architecture Revision Spec v1
   (SUPERSEDED by v3)"

═══ Begin ═══

Run Phase 0 pre-flight now via zero-error-qa. Register the 2 reference
docs (and PATCH v1 + v2 to is_current=false). Then execute v3 spec §4
Phases A through G in order. Provide proof of successful execution
after each phase. Report back when all 37 verification gates pass +
Phase G closeout complete.
═══════════════════════════════════════════════════════════════════
```

---

## Notes for Kim (post-paste)

**Browser smoke gate (E19 ONLY):** Terminal will defer to your hands-on. E25 is tab-structure audit, not browser smoke (Cursor v7 typo fix). Do this after terminal reports done:
1. Load Event_1 → see ProjectSelector + TargetVideoSelector + 6 tabs in production order (BG → Cropper → SB → Phase B → Phase A → Stitcher)
2. Switch TargetVideoSelector to "resolution" → Storyboard + Beat Generator update
3. Click Phase A tab → see Phase A producer
4. Click Phase B tab → see Phase B producer
5. Click "Send Out as MP4" in Storyboard → progress UI showing finalize+assemble cache stats → toast with asset_id (look for cache_hits + cache_misses breakdown — if you've tested previously in Kim's earlier work, finalize_hits should be high; if first run, all misses)
6. Click Stitcher → see 4-slot module mode with intro slot showing the new MP4 path
7. Switch ProjectSelector to "+ New Milestone" → enter milestone_id (lowercase, alphanumeric, 3-64 chars) → milestone scope loaded → Phase A/B disabled; Stitcher 1-slot; BG + Storyboard against `videos.standalone.beats`
8. Switch back to Event_1 → state preserved per scope

**LD-284 codec drift — RE-BAKE to strict spec (Kim 2026-05-03):** v3 ALIGNS `lib/ffmpeg_stitch.py:47-59` to LD-284's strict text (`-preset slow`, `setsar=1:1`, `-g 48`) in Phase B16. LD-284 itself is unchanged. `NORMALIZATION_RECIPE_HASH` auto-bumps; every existing `*_normalized.mp4` becomes stale; next `/api/scene/assemble` re-encodes per beat from source (~3–5 sec/beat at `-preset slow`). Source clips untouched. Better video quality + spec conformance going forward.

**Drain pre-flight is the new "are you ready?" gate.** When the migration script runs Phase C0, it will call `GET /api/admin/inflight_count` and refuse to proceed if any GPT batch / magic job / assemble job / lipsync polling / sync handler is in flight. You'll see a clear list of what's blocking. Wait or kill, retry. This means before the terminal session paste, ideally close other browser windows / cancel any running stills generation / let any in-flight Phase B mix finish.

**`pause_after_ms` becomes real in v3.** Currently this field is dead metadata in beat state (set but never used). v3 wires it via silent black filler clips inserted between body and pair clips. If you have non-zero pause_after_ms values on existing beats from prior testing, the first re-send after v3 lands will produce a longer/paused output. If that's unexpected, set those values to 0 before re-sending.

**Cursor v8 (optional):** v3 spec §13 has 10 questions. Skip unless you want another pass — v6 + v7 findings already folded.

**S5.5c (Beat Generator) follow-up:** Terminal will write the updated handoff to `STORYBOARD_V59_S5_5_C_HANDOFF.md` as part of Phase G.

**S6 (parallel-run + cutover):** This revision MUST land before S6 starts.

---

**End of handoff (v3).**
