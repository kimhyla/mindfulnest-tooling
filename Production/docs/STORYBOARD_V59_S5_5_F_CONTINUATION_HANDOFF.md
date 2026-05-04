# Storyboard v59 — S5.5f Continuation Handoff (after Phase A)

**Date:** 2026-05-04
**Predecessor:** S5.5f Phase A (commit `3f105c0` on `claude/s5_5f`)
**Spec:** `Production/docs/STORYBOARD_V59_S5_5_F_SPEC_v1.md` (incl §19 amendment)
**Preflight:** `prod_preflight_reviews` #203 (task_id `s5_5f-phase-ab-parity-20260504`)
**Activity log:** `prod_activity_log` #1497 (S5_5F_PHASE_A_PREFLIGHT) + #TBD (CHECKPOINT_AT_PHASE_A_DONE)

## §1 Why this checkpoint exists

S5.5f is a ~6-8 hour, ~1500-2000 LOC, 18-gate, 6-LD session. Per the spec's
compaction-aware checkpoint authority + parallel-execution constraints, the
executing session has authority to checkpoint at atomic phase boundaries with
a continuation handoff. This document is that handoff.

Phase A (Pre-flight + dep add + Directus row) is COMPLETE and committed. Phases
B-H remain. The next continuation session picks up at Phase B.

## §2 What's done (Phase A — committed `3f105c0`)

- Worktree confirmed: `~/Projects/mindfulnest-tooling-s5_5f`, branch `claude/s5_5f`
- HEAD descends from `1d375de` (S5.5c+e proper-fix squash on main)
- CI on main verified green (run 25317912167)
- `Production/Event_e2e_fixture/` verified present (intro=3 beats, resolution=0 beats, phase_a/phase_b status pending)
- `npm install wavesurfer.js@7` → `^7.12.6` (103 packages, 0 vulnerabilities)
- `npm run build` clean: 36 modules transformed, dist 120.71 kB
- All canonical specs read in full (S5.5f incl §19, S5.5c+e proper-fix, master overview, Directus reference, zero-error-qa SKILL.md)
- All 13 read-first files inspected (e2e helpers, global-setup/teardown, playwright.config.ts, PhaseProducer.tsx, LibraryPanel.tsx, .github/workflows/playwright_e2e.yml, etc.)
- Backend endpoint surface verified in `production_server.py`:
  - `_handle_phase_b_regen_audio:15121` (Cursor v8 Q5 — writes voice_stem)
  - `_handle_phase_b_mix_audio:15423` (Phase A re-stitch entry)
  - `_auto_assemble_phase_a_stitched:15668` (called from `:15650` inside phase_b_mix_audio)
  - `_handle_v2_module_patch:12908`
  - `_V2_MODULE_ALLOWED_FIELDS` whitelist at `:3660` includes ALL S5.5f target fields:
    - `phase_a_chipper_{flyin,sitting,flyout}_clip_id` (lines 3686-3688)
    - `phase_X_ambient_preset_id` (3669, 3682)
    - `phase_X_watercolor_cues_json` (3675, 3691)
    - `phase_X_stitched_{file,mtime}` (3697-3698)
- `prod_preflight_reviews` #203 written + read-back verified
- `prod_activity_log` #1497 written, FK-linked to preflight via `related_activity_log_id`

## §3 Discoveries that change Phase B-G plans

### §3.1 Server cue animation enum is more restrictive than spec body

**Where:** `production_server.py:3704`
```python
_V2_CUE_ANIMATIONS = frozenset({"fade_in", "slide_in", "gentle_pan"})
```

**Spec §3.4 says** five values: `fade`, `slide_in`, `pulse`, `static`, `procedural_drift`.

**Resolution adopted:** Phase C CuePopover dropdown exposes ONLY the 3 server-allowed
values (`fade_in`, `slide_in`, `gentle_pan`). The spec body describes intent; the
server is source of truth. If Kim wants more animation types later, that's a
separate task to extend the server whitelist + validators.

### §3.2 F17 violations identified pre-implementation

`PhaseProducer.tsx` has TWO `Production/Event_1/` literals, not just one as
implied by F17 spec:

- **Line 95:** `fileUrl()` → ``${SERVER_BASE}/files?path=${encodeURIComponent(`Production/Event_1/${name}`)}``
- **Line 224:** `onExportToStitcher` → `video_path: \`Production/Event_1/${srcFile}\``

Both must be replaced with `activeScope.value.event_id` in Phase B (where we
already touch this file for WaveformTimeline mount).

### §3.3 ambient_preset_list endpoint absent (as Cursor v8 noted)

`grep ambient_preset_list Production/tools/production_server.py` returns 0 hits.
Phase E will add `_handle_phase_b_ambient_preset_list` (~30 LOC) per §3.7 option (b).

### §3.4 Voice stem upload uses misnamed regen_audio endpoint

`_handle_phase_b_regen_audio:15121` writes `phase_{a|b}_voice_stem_*.mp3` per Cursor
v8 Q5. UX text in Phase E should be "Generate stem from script" not "Upload voice
stem" — true file upload is out of scope for this session.

### §3.5 Existing PhaseProducer.tsx structure that informs Phase B-D wiring

- `priorityAudioFile` helper at line 84 already implements lipsync > mixed > stem priority — REUSE
- `selectedBaseClip` state (line 107) handles ONE base clip — must EXTEND for Phase A's 3 clips
- Watercolor list rendering at lines 372-400 uses `window.open` for animate flow — REPLACE with drag-drop in Phase C
- `onMixAudio` at line 198 already calls `pathappPatch(activeScope.value, 'phase_b_mix_audio', { phase })` — perfect for Phase A re-stitch button (Phase D5)
- `audioFile` rendering at lines 291-297 with `<audio controls src={fileUrl(audioFile.name)} />` — REPLACE with `<WaveformTimeline />` in Phase B
- `lipsyncFile` rendering at lines 300-310 — KEEP (lipsync video player is separate from waveform)

## §4 Recipe for next session (Phases B-H)

### Phase B — WaveSurfer integration (F3-F6 TDD)

1. **Write F3-F6 RED tests** in `Production/tools/storyboard-v2/e2e/s5_5f_smoke.spec.ts`. Pattern from `s5_5ce_proper_fix.spec.ts`. Use `Event_e2e_fixture` (NOT `Event_1`). Mock `/api/v2/event-state` to return `phase_b_lipsync_file: 'fixture_lipsync.mp4'` etc., and mock `/files?path=...` to return a tiny valid audio blob.
2. **Build `Production/tools/storyboard-v2/src/components/phase/WaveformTimeline.tsx`** (~250 LOC). WaveSurfer v7 API: `WaveSurfer.create({ container, waveColor, height: 80, normalize: true, barWidth: 2, barGap: 1 })`. On unmount: `ws.destroy()` to avoid WebAudio leaks (Cursor v8 Q1). Cue marker overlay = absolute-positioned divs over the waveform container. Click-to-seek via WaveSurfer's `interact` event.
3. **Mount in `PhaseProducer.tsx`** below script editor (after textarea, replacing the audio player block at lines 291-297). Pass `audioSrc`, `cues` (array from `phase_X_watercolor_cues_json`), `onCueClick`, `onCueDragMove`, `onWaveformClick`.
4. **Fix F17 violations now** (already touching this file): replace `Production/Event_1/${name}` with `${activeScope.value.event_id}/${name}` at line 95 + line 224.
5. **Run tests locally:** `cd Production/tools/storyboard-v2 && STORYBOARD_BASE_URL=http://localhost:5113 npx playwright test e2e/s5_5f_smoke.spec.ts` (port 5113 to avoid retroactive sprint's 5112 + Kim's 5111 dev server). Need to override webServer port via env, OR kill any existing 5111 server first.
6. Tests turn GREEN. Commit `S5.5f Phase B — WaveSurfer integration (F3-F6 green)`. Push.

### Phase C — CuePopover + drag-drop (F7-F9 TDD)

1. Write F7-F9 RED tests.
2. Build `src/components/phase/CuePopover.tsx` (~150 LOC). Position via `position: fixed` + viewport math (Cursor v8 Q2). Close on outside click. Animation dropdown = ONLY `fade_in`/`slide_in`/`gentle_pan` (server whitelist; see §3.1 above). Modal-confirm Delete (Cursor v8 Q8); Shift+click skip-confirm.
3. Wire WaveformTimeline as drop target for `kind: 'lib-image'` payloads where source tier is watercolor. Default new cue: `{ animation_type: 'fade_in', duration_ms: 3000, volume: 1.0 }`.
4. LibraryPanel watercolor tier tiles already use AssetTile primitive with drag prop forwarding (LibraryPanel.tsx:127-133) — verify no extra wiring needed.
5. Tests GREEN. Commit `S5.5f Phase C — CuePopover + drag-drop (F7-F9 green)`. Push.

### Phase D — Phase A 3-clip handling (F10-F13 TDD)

1. Write F10-F13 RED tests.
2. Build `src/components/phase/BaseClipPicker.tsx` (~120 LOC). Modal with library filter for Phase A clip tier. (S5.5c `Modal` primitive available at `src/components/ui/Modal.tsx`.)
3. Render 3 picker slots (fly-in / sitting / fly-out) ONLY when `phase === 'a'`. Phase B continues to use single `selectedBaseClip` + cedric filter.
4. Each slot wired via `pathappPatch(activeScope.value, 'v2_module_patch', { phase_a_chipper_<position>_clip_id: clipId })`. Whitelist verified (lines 3686-3688).
5. Manual "Re-stitch" button (NOT auto, per Cursor v8 Q9) calls `pathappPatch(activeScope.value, 'phase_b_mix_audio', { phase: 'a' })` — this is the existing `onMixAudio` handler at PhaseProducer.tsx:198.
6. Display total = sum of nominal clip durations (per Cursor v8 Q4 — bake-time post-xfade is server-side responsibility).
7. Tests GREEN. Commit. Push.

### Phase E — Voice stem + ambient preset (F14-F15 TDD)

1. Write F14-F15 RED tests.
2. Add "Generate stem from script" button (NOT file upload) — POST `/api/phase_b/regen_audio` with `{ phase, script: scriptDraft }`.
3. Add `_handle_phase_b_ambient_preset_list` to `production_server.py` (~30 LOC). Filesystem scan of `Production/audio_library/ambient/*.mp3`. Returns `{preset_id, file_size_bytes}`. Wire to GET `/api/phase_b/ambient_preset_list` route.
4. Add ambient preset selector in PhaseProducer (dropdown + volume + loop + fade in/out + Preview-with-bed button). Wire to `pathappPatch(scope, 'v2_module_patch', { phase_X_ambient_preset_id: id })`.
5. Tests GREEN. Commit. Push.

### Phase F — Verification (F1, F2, F16, F17, F18 + workflow extension)

1. F1: `npm run build` clean (final).
2. F2: `/api/health` 200 with fresh server (Rule 29).
3. F16: assert watercolor tile framing (LD-203 brown border + cream mat + white interior + centered art) visible after drag-drop. Likely a CSS class assertion.
4. F17: `grep -n "Production/Event_1/" Production/tools/storyboard-v2/src/components/phase/PhaseProducer.tsx` → expect ZERO. (Already addressed in Phase B per §3.2.)
5. F18: extend `.github/workflows/playwright_e2e.yml` line 89:
   ```yaml
   # BEFORE:
   run: npx playwright test e2e/s5_5ce_proper_fix.spec.ts --reporter=line
   # AFTER:
   run: npx playwright test e2e/s5_5ce_proper_fix.spec.ts e2e/s5_5f_smoke.spec.ts --reporter=line
   ```
   APPEND, NOT replace, NOT glob. Update header comment block (lines 7-12) to reflect both files.
6. Push commit; verify CI run goes green.

### Phase G — 6 NEW LDs (HARD/SOFT per §19.4)

POST via `Production/tools/lib/directus.py.post_item_verified` (Python urllib, Rule 18):

- `WAVESURFER_TIMELINE_INTEGRATION_V1` — **HARD** — task_category=`tech_stack`, scope_domain=`production`, enforcement_type=`test`
- `WATERCOLOR_DRAG_DROP_TIMELINE_V1` — **HARD** — task_category=`storyboard`, scope_domain=`production`, enforcement_type=`test`
- `CUE_POPOVER_INSPECTOR_V1` — **HARD** — task_category=`storyboard`, scope_domain=`production`, enforcement_type=`test`
- `PHASE_A_THREE_CLIP_HANDLING_V1` — **HARD** — task_category=`phase_a`, scope_domain=`production`, enforcement_type=`code_invariant`
- `VOICE_STEM_UPLOAD_UI_V1` — **SOFT** — task_category=`audio`, scope_domain=`production`, enforcement_type=`awareness_only`
- `AMBIENT_PRESET_SELECTOR_INPRODUCER_V1` — **SOFT** — task_category=`audio`, scope_domain=`production`, enforcement_type=`awareness_only`

Each LD body includes `task_id` in `notes` per zero-error-qa Step 8.

Field constraints (varchar caps):
- decision_key ≤ 100, decision_name ≤ 200, source_document ≤ 200, severity ≤ 10
- Provenance chain → `notes` (text, no cap), short label → `source_document`

### Phase H — Closeout

1. `prod_activity_log` row `S5_5F_COMPLETE` with 18-gate summary.
2. Update `Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md` §3 table — flip S5.5f row from PENDING to COMPLETE with commit SHA + LD ids + CI run id.
3. Tail-end verifier subagent (regression check on S5.5c+e's 13 e2e tests still green).
4. Single squashable commit (per §8.8) OR one final closeout commit if intermediate phase commits taken.
5. `gh pr create` — body must note: "May conflict with PR from claude/retroactive-coverage-sprint on e2e/helpers.ts and src/components/LibraryPanel.tsx; whichever merges second rebases."

## §5 Tactical reminders

- **Local Playwright port:** `STORYBOARD_BASE_URL=http://localhost:5113` to avoid retroactive's 5112 + Kim's 5111 dev. Server spawn port is set in `playwright.config.ts:webServer.command` — env-var override only, do NOT commit port changes.
- **Tests use `Event_e2e_fixture`** (NOT Event_1/Event_2). Existing `helpers.ts:EVENT_ID = 'Event_1'` is from old scaffold (deferred); s5_5f_smoke.spec.ts should not import it. Pattern from `s5_5ce_proper_fix.spec.ts` line 16: `const FIXTURE_EVENT = 'Event_e2e_fixture';`.
- **Critical-path tests NEVER quarantined** (§19.5 inheriting proper-fix §16). Diagnose root cause + fix.
- **All Directus writes via `try_post_or_queue` or `post_item_verified` with read-back** (Rule 35). Embed `task_id` in `details.task_id` AND PATCH back-link via `related_activity_log_id`.
- **Server staleness check (Rule 29):** if `production_server.py` modified, restart before any probe.
- **No coordination with retroactive-coverage-sprint** — they merge-rebase later. Stay in this worktree only.

## §6 Escape hatches that did NOT trigger this checkpoint

This is a CLEAN PHASE-A-DONE checkpoint per spec authority — no escape hatch fired:
- pwd / branch / HEAD all correct
- WaveSurfer install succeeded
- All F-gate fixture data exists (per S5.5c+e Event_e2e_fixture preserved on main)
- CI on main green
- No state-shape / architectural smell discovered (cue animation enum mismatch is a UX/policy point, not architectural)
- No attempt to modify retroactive's worktree
- No Rule 26 escalation triggers

## §7 Resume command for next session

```bash
cd ~/Projects/mindfulnest-tooling-s5_5f
git status   # should be clean on claude/s5_5f at 3f105c0
git log --oneline -3
# then start with Phase B per §4 above
```

Or kick off in a fresh Claude Code session with the prompt:

> Resume S5.5f at Phase B per
> `Production/docs/STORYBOARD_V59_S5_5_F_CONTINUATION_HANDOFF.md` §4. Worktree
> already at `~/Projects/mindfulnest-tooling-s5_5f`, branch `claude/s5_5f`,
> HEAD `3f105c0`. preflight #203, activity #1497. Continue TDD-ordered through
> Phase H per spec §19 amendments folded.

---

**End of S5.5f Continuation Handoff (after Phase A — 2026-05-04).**
