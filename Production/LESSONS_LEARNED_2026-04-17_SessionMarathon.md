# Lessons Learned — 2026-04-17 Session Marathon

**Session context:** 8+ hour session, April 16 evening → April 17 AM. Started as "debug why Generate B+C silently fails on beat_02" and expanded into full Tier 1 resilience + Tier 3 recovery + blind-spot remediation + script-drift investigation + dialogue autosave + beat-2/3/5 production.

**Companion docs:**
- `SESSION_HANDOFF_2026-04-17_LateNight.md` — operational resumption guide
- This file — architectural and process lessons

---

## META-LESSONS (the ones worth internalizing)

### L1. The "server state vs. HTML file snapshot" divergence is a SYSTEMIC bug class, not four separate bugs.

Four decisions were registered today that all have the same root pattern:
- **151** `DIALOGUE_EDITS_MUST_PERSIST` — contenteditable text changes don't save
- **153** `LIPSYNC_UI_MUST_SUPPORT_RERUN` — button locks to "Done" when source changes
- **154** `ASSIGN_IMAGE_MUST_PATCH_STORYBOARD_HTML` — drag-drop doesn't patch HTML L[] `i:`
- **155** `TRIM_END_SELECTED_VIDEO_ONLY` — listener re-reads stale HTML and resets user's trim

All four trace to: **server state has current truth, HTML file has stale snapshot, UI reads HTML not server → user's edits ghost back.**

**The architectural fix** (scheduled as Tier 5): a helper `patch_storyboard_field(beat_id, field, value)` that every `mutate_state` touching a field-visible-in-storyboard calls. One function, 5-10 call sites, closes all four decisions at once. ~100 LOC.

**Lesson:** when you see multiple bugs with the same shape, STOP fixing them one-at-a-time and look for the systemic pattern. Tier 5 is now a single coherent build instead of four separate ones.

### L2. Rule 20 (Automatic Decision Capture) requires moment-of-decision registration, not end-of-phase batching.

I batched decisions at the end of big work chunks (Tier 1, Tier 3). Missed 6 CONFIDENT verdicts from mid-debate (Q1 root-cause pick, Q3 disk-primary, Q4a multi-stage, Q4b button location, preview→commit workflow, Windows dev machine). Kim caught it: "have these been getting properly filed away?"

**Fix (behavioral):** any response where a verdict is stated should include a one-line "Registered: DECISION_KEY" footer. Then proceed to the next part of the task. Silent register is part of the same turn, not a separate pass.

**Lesson:** institutional memory is only as durable as the moment of capture. Defer capture → lose some. Backfill works but smells.

### L3. Initial agent recommendations are starting points. Kim's domain knowledge consistently improved verdicts.

Three pivotal pushbacks this session:
1. **Q2 recovery tooling** — I initially picked runbook-only based on "once per quarter" frequency. Kim asked me to verify actual frequency. Grepped project, found documented **30% failure rate**. Flipped verdict to "build the tool."
2. **Q3 Windows cross-machine** — I initially picked disk-primary. Kim revealed she wants to work from her Windows machine. Flipped to dual-write + Directus semaphore.
3. **Skeleton-as-ship-source** — I initially proposed reverse-cascading storyboard back to arc skeleton. Kim asked "why?" I traced downstream readers — skeleton is upstream-only. Flipped the framing.

**Lesson:** when the user pushes back with a "why" or a domain observation, take it seriously. Re-examine the premise, don't just defend.

### L4. Preserve-before-change is a MANDATORY reflex, not an optional courtesy.

Today's preserved-winners accumulation:
- `beat_02_option2_new_22-53-01.mp4` (first B regen, CDN-recovered)
- `beat_03_lipsync_v2_MUCH_BETTER_preserved_20260416-230732.mp4` (first lipsync with "much better" tone)
- `beat_03_lipsync_option_B_good_tone_missed_ItsOK_20260416-235714.mp4` (second lipsync, missed word)
- `line_03_tessa_pre_ItsOK_removal_20260417-005918.mp3` (TTS before drift fix)
- `line_05_tessa_ORIGINAL_10.16s_20260417-013140.mp3` (original pre-trim)
- `line_05_tessa_END_TRIM_REJECTED_20260417-013513.mp3` (Kim's rejected trim)
- `beat_05_lipsync_optB_missed_more_careful_*.mp4` (tonight's latest)
- Plus 20+ `production_state.json.bak_*` files at every mutation boundary

**Every "this is probably fine" change preserved the before-state.** Saved us three times when Kim said "undo" or "restore that." Cost: a few MB of disk. Benefit: no lost creative work across an 8-hour session.

**Lesson:** in creative-production contexts, the cost of a backup is trivial relative to the cost of re-doing creative work. Default to preserve.

### L5. `os.execv` preserves PID but replaces process image.

Confusing signal while debugging restarts. The PID (37473) stayed constant across "restart server" clicks → I briefly suspected the restart wasn't working. Reality: `os.execv` is designed to replace the process image in-place, keeping the same OS PID. The correct verification is **endpoint behavior**, not `ps` output:
- Old code: `/api/beat/update_text` → 404 not found
- New code: `/api/beat/update_text` → structured 400 with {error: missing...}

**Lesson:** when debugging restart-exec patterns, verify at the behavior layer (endpoints, symbols, constants) not at the process layer (PID, start-time).

### L6. WaveSpeed has documented ~30% transient failure rate. The CDN-pull recovery pattern must be treated as ROUTINE, not exceptional.

3 CDN-pull recoveries today:
- beat_02 (22:53 UTC) — server polls timed out, CDN had completed clips
- beat_03 (00:05 UTC) — same pattern
- beat_05 (02:07 UTC) — same pattern

The pre-fail CDN check (decision 130) catches many automatically. The `recover_stuck_tasks.py` tool (decision 131) catches the rest. **Without these, this session would have required re-submission 3× wasted ~$1.50.** With them, recovery is ~10 seconds.

**Lesson:** upstream vendor reliability should inform tool design, not just fault-handling. If 30% of requests transiently fail, recovery is a first-class workflow, not a last-resort runbook.

### L7. Contenteditable edits are browser-memory only by default.

Caused hours of confusion. Kim edited beat_03 dialogue, hard-refreshed, saw her edit reverted. No error, no indication — just data loss.

**Fix built today** (decision 151): `/api/beat/update_text` + on-blur auto-save + patch HTML atomically.

**Lesson:** any user-facing "edit in place" affordance MUST have an explicit save path. "It'll save when you hit export" is not sufficient UX — users expect edit-is-save by default on web forms.

### L8. Adversarial review catches 1-3 HIGH findings per architectural batch.

Quantified today:
- Tier 1 Phase 3: 1 CRITICAL + 1 HIGH + 2 MEDIUM + 3 LOW → 3 addressed inline
- Tier 3 Phase 3: 1 CRITICAL + 1 HIGH + MEDIUM findings → 2 fixed inline
- Blind-spot Phase 3: 1 CRITICAL + 1 HIGH → both fixed
- Duration-fix Phase 3: 1 HIGH + 2 MEDIUM → 2 fixed inline
- Dialogue-autosave Phase 3: 1 CRITICAL + 1 HIGH → both fixed

**Without adversarial review, we would have shipped:** HTML write race (opens drag-drop conflict window), `</script>` injection (security breach), `_handle_animate` unfixed (Generate B+C only, missing all-beats submit), stale `text_modified_after_tts` flag (never cleared), audit-tool `NO_CLIP` misleading verdict, duration schedule too aggressive.

**Lesson:** zero-error-qa Phase 3 is NOT overhead, it's insurance. Consistently pays.

### L9. "One more bug will be quick" always hides the systemic issue.

The lipsync UI re-run problem hit 4 times today (beat_02, beat_03, beat_05 twice). Each time I treated it as an isolated manual fix. Only on the 4th hit did I register the decision (153) as a proper future build.

**Fix going forward:** when you see the SAME class of bug twice, classify it as systemic on the second occurrence, not the fourth. Register the decision, prioritize the build.

### L10. Arc skeleton vs storyboard: both are first-class, but they're different classes.

Skeleton is **outline** (upstream, seed). Storyboard is **ship** (downstream, canonical). Decision 150 `SKELETON_IS_OUTLINE_NOT_SHIP_SOURCE` captures this.

**Implication for other pairs of canonical documents:** check which direction the authority flows. It's usually not bidirectional.

---

## WHAT I'D DO DIFFERENTLY NEXT SESSION

1. **Build Tier 5 FIRST thing.** All 4 UI persistence bugs (151, 153, 154, 155) + the common helper = one coherent ~100-LOC build. Prevents 3+ hours of manual workaround dances in future production sessions.

2. **Register decisions at moment-of-verdict.** Not at end-of-phase. One-line footer per turn.

3. **Before dispatching agents, pre-approve read-only patterns.** `.claude/settings.json` tweaks should happen in the first 30 seconds of agent-heavy work, not 20 minutes in after Kim complains about clicks.

4. **Preserve-before-change is automatic.** Every state mutation that's non-trivial → backup first, no exceptions, no "this is probably fine."

5. **Test server endpoints, not PIDs, to verify restarts.** Save time debugging.

6. **When WaveSpeed timeouts cluster, pre-emptively check CDN** before doing anything else. Don't wait for MAX_RETRIES to exhaust.

7. **When Kim pushes back, re-examine the premise.** Her "why does it matter?" questions consistently exposed architectural assumptions worth revisiting.

8. **Use QuickTime for audio review via the standard `open -a` path, per the locked decision.** Do NOT auto-play; let Kim drive comparison.

---

## TIER 5 DESIGN (proposed, not yet built)

**Goal:** eliminate the "server state vs HTML snapshot" bug class.

**Implementation:**

```python
# Production/tools/production_server.py  — new helper

def patch_storyboard_beat_field(storyboard_path, beat_id, field, new_value):
    """Atomically update L[] entry's field for beat_id.

    field ∈ {'t', 'i', 's', 'a', 'p', 'g'}  — matches the L[] entry keys
    new_value: string

    Uses the same _storyboard_write_lock and tmp+rename pattern as
    _handle_beat_update_text. Single source of truth for all HTML
    patching operations (dialogue, image, speaker, pause, etc.)."""
    with app._storyboard_write_lock:
        html = storyboard_path.read_text(encoding="utf-8")
        beat_num = int(beat_id.split("_")[1])
        marker = f'a:"line_{beat_num:02d}"'
        # ... same logic as _handle_beat_update_text ...
        # Rewrite field:"value" portion of the enclosing {...} entry
```

**Call sites to add:**
- `_handle_assign_image` — patch `i:` field (fixes 154)
- (future) `_handle_select` — could patch selected marker, though UI derives this client-side

**For 151 (already built):** `_handle_beat_update_text` ALREADY uses this pattern — extract the common logic into the helper.

**For 153 (lipsync UI rerun):** different shape — requires invalidating lipsync state when `selected_option` changes. Implementation: hook `_handle_select` to check if selected clip differs from `lipsync.source_clip`; if so, set `beat.lipsync_source_changed=True` flag. Client shows "🔁 Re-run Lip Sync" button when flag is true.

**For 155 (already built):** trim-end listener check already shipped today; no further work.

**Total estimated scope:** ~80-120 LOC across 3 files. One Phase 0 preflight, 2-agent adversarial review, ~1 hour with full rigor.

---

## SUMMARY

This session closed **19 active locked decisions**, fixed **3 BLOCKERs + 6+ HIGH bugs**, built **2 new tools** (recovery CLI + audit), refactored **2 major modules** (StateManager + WaveSpeedClient), cascaded **4 governance docs**, produced **3 beats of lipsynced output** (2, 3, 5), and queued **4 coherent bug fixes** for the next Tier 5 build.

The session's signature experience: **recurring bugs that felt like regressions turned out to be the same architectural bug hit from four different angles.** The next session should prioritize fixing that one architectural pattern to close all four in one build.
