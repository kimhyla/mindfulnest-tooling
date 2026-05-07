# Session Handoff — 2026-04-17 Late Night (Event 1 / M1 / Tessa)

**Session span:** April 16 evening → April 17 early AM (~8+ hours)
**Purpose:** Resumption-ready handoff if this thread compacts or a new Claude picks up.
**Canonical authority for everything in this doc:** Directus (`prod_locked_decisions`, `prod_preflight_reviews`, `prod_activity_log`). This file is a narrative mirror for fast re-loading context.

---

## TL;DR for resuming Claude

Three things happened today. **(1)** A BLOCKER — "Generate B+C silently fails on beat_02" — triggered a deep diagnosis that found the root cause was `urllib` entering stuck-process state in the long-running server. Fix: swap to `http.client` with fresh connection + SSL context per call. **(2)** That fix exposed more systemic issues (silent-200 failures, in-memory state loss, race conditions, cross-machine concerns) which were all addressed via Tier 1 + Tier 3 resilience + blind-spot passes. **(3)** Production work on Event_1 beats 2/3/5 surfaced a script-drift bug (line_03 Tessa) and a set of UI bugs (trim-end resetting, dialogue edits not persisting, lipsync not re-runnable, drag-drop not patching HTML) — all registered for next build.

**Beats completed: 1-5 on Event_1. Beats 6-11 remaining.** All decisions, preflights, and activity logs are in Directus. See §4-6 below for exact IDs.

---

## 1. What was in scope today

- Debug + fix "Generate B+C silently fails on beat_02"
- Harden the production_server long-running HTTP process against stuck network states, cross-machine usage, silent UX failures
- Build the stitch pipeline design (not yet implemented)
- Production work: regenerate animations + lipsync on beats 2, 3, 5 with corrected scripts and audio
- Governance cascade: update PIPELINE_BRAIN, storyboard-producer governance, TASK_GOVERNANCE_PROTOCOL

**Not in scope (deferred):** Tier 4 stitch implementation; beats 6-11 production; audio-tool UI; Tier 5 build of dialogue/lipsync/image-save bug cluster.

---

## 2. Major accomplishments

### Tier 1 — server resilience (code landed, active after restart)
- `-u` unbuffered stdout on `python3 production_server.py` (eliminates log invisibility)
- `_handle_restart` → `perform_server_restart()` module-level helper, non-daemon thread (UI restart button actually works now)
- `WaveSpeedClient` rewritten to `http.client.HTTPSConnection` + fresh `ssl.create_default_context()` + `OP_NO_TICKET` + `OP_NO_COMPRESSION` + `Connection: close` + explicit `conn.close()` per call (architecturally precludes urllib stuck-state bug)
- `_image_overrides` persists to `production_state.json` `image_overrides` key + async Directus audit
- `_handle_add_options` returns 500 on all-failed / 200 with `partial:true` on mixed
- `/api/animate/status` includes polling/failed options with per-option status/retries/error
- Client HTML checks `new_submitted === 0` as failure state
- `lib/directus.py` rewritten to same fresh-connection pattern

### Tier 3 — recovery + retry (code landed, active after restart)
- `MAX_RETRIES=4` with non-blocking `next_attempt_at_epoch` backoff `[0, 5, 15, 45]s`
- Pre-fail CDN async re-check at retries `{2, 4}` via daemon thread with 10s timeout
- `Production/tools/recover_stuck_tasks.py` — sanctioned manual recovery CLI with idempotency / winner-lock / spend-ledger safeguards
- `Production/RUNBOOKS/recover_stuck_wavespeed_task.md` — runbook (registered as `prod_reference_docs` id=44)

### Tier 3 blind-spot fixes (code landed, active after restart)
- BS1: `prod_locks` Directus collection + cross-machine semaphore wrapping `StateManager.mutate_state` / `add_spend` / `override_budget`. TTL 60s, heartbeat 30s. Fail-closed on Directus unreachable; env `PRODUCTION_SERVER_SINGLE_MACHINE=1` escape hatch.
- BS3: WaveSpeed startup smoke test (5s timeout, non-blocking, differentiated logs for auth/upstream/connectivity)
- BS4: `WaveSpeedClient.download` uses atomic tmp+rename; startup orphan-`*.tmp` sweep
- BS6: fire-and-forget Directus write for image overrides **accepted** (no retry queue built); REVISIT when a second reader of `prod_session_decisions` exists

### Animation duration auto-infer (code landed, active after restart)
- `_find_beat_audio(event_dir, beat_key, audio_override=None)` shared helper (reused by lipsync + animation)
- `_infer_animation_duration(audio_path) -> (int, str)` returns 5 or 10 seconds; raises `ValueError` for audio > 10s
- `_handle_add_options` + `_handle_animate` both call it; audio > 10s → 400 with "split or edit script" hint
- `Production/scripts/audit_beat_durations.py` — read-only audit (verdicts: OK/STALE_5s/UNDER_TRIM/OVER_LONG/NO_AUDIO/NO_CLIP/UNSELECTED/AUDIO_OVER_KLING)

### Dialogue auto-save (code landed, active after restart)
- `POST /api/beat/update_text` — updates state JSON + patches storyboard HTML `L[]` entry's `t:` field atomically (tmp+rename + `_storyboard_write_lock`)
- `_async_log_text_update` fire-and-forget Directus audit
- Client: `onblur` handler on contenteditable textarea POSTs; shows ✓ saved / ⚠ TTS stale indicator
- Builder source `build_storyboard.py` + live storyboard HTML both updated
- **CRITICAL** HTML write race + tmp-collision fixed via threading.Lock + pid+uuid-suffixed tmp path
- **HIGH** `</script>` injection in user text mitigated via `.replace("</", "<\\/")` in escape chain

### Governance cascade + Rule 20 compliance
- 6 missed CONFIDENT decisions backfilled (see §4) — they had been mid-session verdicts not registered at moment-of-decision
- 4 project docs updated (`PIPELINE_BRAIN_v1.md §19`, `STORYBOARD_PIPELINE_LESSONS_LEARNED_April16_2026.md §7.1 RESOLVED + §8 + §9`, `storyboard-producer_governance.md` Stitch Pipeline Decisions, `TASK_GOVERNANCE_PROTOCOL.md` new categories)
- Superseded the bad decision 147 (skeleton-as-ship-source) with correct 150 (skeleton-as-outline)

### Production: beats 2, 3, 5
- **Beat_02:** recovered B+C from CDN (WaveSpeed API was timing out but clips had completed on CloudFront). 3 options ready, Option B selected, lipsync completed.
- **Beat_03:** script drift fixed ("It's OK" removed from the dialogue per canonical intent), TTS regenerated via ElevenLabs v3 / Jessica voice, lipsync re-run. Option B selected. `beat_03_lipsync.mp4` is the current winner.
- **Beat_05:** audio trimmed (10.16s → 9.883s via ffmpeg, 0.2s from start preserving tail), 10s Kling animations regenerated on `tessa_initial_4x3` image, Option B selected, lipsync completed (`beat_05_lipsync.mp4` 999 KB).

---

## 3. Directus preflight rows (all from today)

| id | task_id | scope |
|---|---|---|
| 9 | tier1-prod-server-fixes-20260416-204301 | Tier 1 resilience (B1/B2/B3 + HIGH findings) |
| 12 | tier3-recovery-resilience-20260416-213744 | Tier 3 retry + recovery tool + runbook |
| 14 | tier3-blindspot-fixes-20260416-221031 | BS1/BS3/BS4 + BS6 accept |
| 17 | tier1-duration-audio-match-20260416-231826 | Duration auto-infer + audit tool |
| 18 | arc-skeleton-cascade-event1-20260417-002620 | Script drift cascade (decision corrected) |
| 19 | dialogue-autosave-build-20260417-010651 | `/api/beat/update_text` feature |

---

## 4. Locked decisions registered today (full set, 21 decisions)

Active (19):
- **129** `EXP_BACKOFF_POLL_RETRY` — MAX_RETRIES=4 backoff `[0,5,15,45]s`, non-blocking via `next_attempt_at_epoch`
- **130** `PRE_FAIL_CDN_RECHECK` — async CDN probe at retries {2,4}, 10s timeout
- **131** `CDN_RECOVERY_TOOL_PRIMARY` — `recover_stuck_tasks.py` is sanctioned recovery
- **132** `CROSS_MACHINE_DIRECTUS_LOCK` — `prod_locks` semaphore, TTL 60s
- **133** `WAVESPEED_STARTUP_SMOKE_TEST` — 5s startup connectivity probe
- **134** `ATOMIC_DOWNLOAD_TMP_RENAME` — tmp+rename in `WaveSpeedClient.download`
- **135** `BS6_ACCEPT_DIRECTUS_AUDIT_GAPS` — fire-and-forget accepted; no retry queue
- **137** `POLL_CLIENT_ROOT_CAUSE_HTTP_CLIENT` — swap urllib → http.client fresh-conn
- **138** `IMAGE_OVERRIDE_DURABILITY_HYBRID` — disk + async Directus
- **139** `STITCH_ARCHITECTURE_MULTI_STAGE` — two-stage finalize + concat (NOT YET BUILT)
- **140** `STITCH_WORKFLOW_PREVIEW_THEN_COMMIT` — Preview button → edit-in-storyboard → Commit (NOT YET BUILT)
- **141** `STITCH_BUTTON_LOCATION_STORYBOARD_OVERLAY` — buttons in prod overlay not separate page (NOT YET BUILT)
- **142** `WINDOWS_WORK_MACHINE_SECONDARY_DEV_ENV` — Windows supported via Claude Code CLI
- **144** `ANIMATION_DURATION_MATCHES_AUDIO` — auto-infer 5/10s from audio
- **145** `AUDIT_BEAT_DURATIONS_TOOL` — `Production/scripts/audit_beat_durations.py`
- **150** `SKELETON_IS_OUTLINE_NOT_SHIP_SOURCE` — arc skeleton is upstream outline only
- **151** `DIALOGUE_EDITS_MUST_PERSIST` — `/api/beat/update_text` endpoint BUILT; active after server restart
- **153** `LIPSYNC_UI_MUST_SUPPORT_RERUN` — auto-invalidate lipsync when selected_option changes (NOT YET BUILT)
- **154** `ASSIGN_IMAGE_MUST_PATCH_STORYBOARD_HTML` — drag-drop must also patch HTML L[] `i:` field (NOT YET BUILT)
- **155** `TRIM_END_SELECTED_VIDEO_ONLY` — trim-end metadata listener only updates from selected video (PATH B FIX LANDED)

Superseded (1):
- ~~**147** `ARC_SKELETON_IS_CANONICAL_DIALOGUE_SOURCE`~~ → superseded by **150**

---

## 5. Files modified today

### Server / tooling
- `Production/tools/production_server.py` — massive: StateManager (fcntl + atomic + spend ledger), WaveSpeedClient rewrite, PollingThread retry/backoff, `_pre_fail_cdn_check`, `perform_server_restart`, `_async_log_image_override`, `_async_log_text_update`, `_handle_beat_update_text`, `_find_beat_audio`, `_infer_animation_duration`, cross-machine lock wrappers, smoke test, orphan-tmp cleanup
- `Production/tools/lib/directus.py` — `_fresh_https_request` helper, rewrote `authenticate` + `_request`
- `Production/tools/build_storyboard.py` — dialogue auto-save emit pattern (future rebuilds)
- `Production/tools/patch_delay_trim.py` — `data.new_submitted===0` check + partial handling + trim-end selected-video-only fix
- `Production/start_production_server.command` — `-u` flag
- `Production/tools/recover_stuck_tasks.py` — **NEW** (CDN recovery CLI)
- `Production/scripts/audit_beat_durations.py` — **NEW** (audit tool)

### Storyboard (live + source)
- `Production/Event_1/storyboard_v37_prod.html` — multiple Path B patches: `add_options` client check, polling-option placeholders (no broken `<video src="undefined">`), dialogue auto-save on blur + save indicator, beat_03 text drift removed, beat_05 L[] `i:` patched, trim-end metadata listener selected-video-only

### Governance + reference docs
- `Production/PIPELINE_BRAIN_v1.md` — added §19 Recent Decisions (all 13 from today) + duration-fix entry
- `Production/STORYBOARD_PIPELINE_LESSONS_LEARNED_April16_2026.md` — §7.1 RESOLVED with actual root cause + new §8 + §9
- `Production/governance/storyboard-producer_governance.md` — Stitch Pipeline Decisions section
- `Production/TASK_GOVERNANCE_PROTOCOL.md` — 3 new task categories, 3 new failure-prevention rows, new locked-decisions list
- `Production/RUNBOOKS/recover_stuck_wavespeed_task.md` — **NEW** (registered `prod_reference_docs` id=44)

### Harness settings
- `.claude/settings.json` — added read-only Bash + Chrome MCP allowlist to eliminate permission-prompt spam

---

## 6. Per-beat Event_1 state snapshot (at handoff time)

**updated_at: 2026-04-17T06:18:27 UTC**

| Beat | phase_1 | sel | options | lipsync | notes |
|---|---|---|---|---|---|
| beat_01 | completed | 1 | 1 (A only) | — | Stage direction, no TTS |
| beat_02 | completed | 2 (B) | 3 (A + B=3.3MB + C=5.0MB) | completed (beat_02_lipsync.mp4) | Recovered via CDN |
| beat_03 | completed | 2 (B) | 3 (A + B=3.8MB + C=3.7MB) | completed (beat_03_lipsync.mp4) | Script drift fixed, TTS regen'd on "I'm fine. I fell. I hurt my shell a little." (removed "It's OK"). Voice: Jessica v3. image_override: `tessa_initial_4x3` |
| beat_04 | completed | 1 (A) | 1 (A only, 2.3MB) | completed (beat_04_lipsync.mp4) | Guide Bird "Oh... What happened?" (line_04) |
| beat_05 | completed | 2 (B) | 3 (A=2.0MB + B=5.9MB + C=4.3MB) | completed (beat_05_lipsync.mp4) | Audio trimmed 10.16s→9.883s (0.2s off start). 10s Kling. image_override: `tessa_initial_4x3` |
| beat_06 | completed | 1 (A) | 3 (A=2.4MB + B + C) | — | **Needs lipsync** |
| beat_07 | completed | 1 (A) | 1 (A only, 2.6MB) | — | **Needs lipsync** |
| beat_08 | completed | 1 (A) | 1 (A only, 2.2MB) | — | **Needs lipsync** |
| beat_09 | completed | 1 (A) | 1 (A only, 2.0MB) | — | **Needs lipsync** |
| beat_10 | completed | 1 (A) | 1 (A only, 2.0MB) | **FAILED** | lipsync submit error — needs retry |
| beat_11 | completed | 3 (C) | 3 | — | **Needs lipsync** |

**image_overrides:** `beat_03: tessa_initial_4x3, beat_05: tessa_initial_4x3`

---

## 7. Open work (next-session priorities)

### Immediate (beat production)
1. Lipsync **beats 6, 7, 8, 9, 11** — dialogue text unchanged, audio files should be in place, selected_option already picked. Just need to hit "Send for Lip Sync" on each.
2. Retry lipsync on **beat_10** (currently status=failed).
3. Decide what to do about **beat_11 Option C** — current selection. Verify it's the right pick visually before lipsync.
4. Verify **beat_05 new lipsync quality** — did "I should have been more careful" finally lipsync correctly with the trimmed audio + 10s clip?

### Tier 5 build (UI persistence cluster — same pattern, ~200 LOC total)
- **id=153** `LIPSYNC_UI_MUST_SUPPORT_RERUN` — auto-invalidate or warn when `selected_option` changes from the source clip used by current lipsync
- **id=154** `ASSIGN_IMAGE_MUST_PATCH_STORYBOARD_HTML` — drag-drop POST should also patch `L[i].i` in HTML (same pattern as `/api/beat/update_text`)
- Bonus: add a visible "saved ✓" indicator on drag-drop like the dialogue one

### Tier 4 build (stitch pipeline — designed, NOT YET BUILT)
- `id=139/140/141` — Preview Scene + Commit Final buttons, `/api/beat/finalize` + `/api/scene/assemble` endpoints, `phase_2` state schema, ffmpeg concat
- ~350 LOC; deferred until all 11 beats lipsynced first

### Governance follow-ups
- Fix beat_10 lipsync failure (check `last_error` field for the task)
- Audit script `--strict` should run before any stitch to block STALE_5s beats
- Fifth-grade-reading pass on any scripts changed today to ensure clinical voice integrity

---

## 8. Meta-observations / lessons learned

1. **Rule 20 (Automatic Decision Capture) works only if Claude applies it at moment-of-decision.** I batched decisions at the end of big work chunks and missed 6 CONFIDENT verdicts mid-session. Kim caught it. Going forward: silent-register at the exact response where the decision is made, with a one-line footer.

2. **Storyboard bugs cluster around "server state vs. HTML file divergence."** `DIALOGUE_EDITS_MUST_PERSIST` (151), `LIPSYNC_UI_MUST_SUPPORT_RERUN` (153), `ASSIGN_IMAGE_MUST_PATCH_STORYBOARD_HTML` (154), `TRIM_END_SELECTED_VIDEO_ONLY` (155) are all variants of: the server has current state but the HTML-embedded UI state is stale. **Root architectural need:** server-side mutations should automatically patch the HTML's inline data (L[] entries) wherever the HTML caches what state holds.

3. **WaveSpeed API timeouts are frequent** (documented ~30% of "failed" jobs actually complete on CDN). The CDN-pull recovery pattern saved the session three times (beat_02, beat_03, beat_05). `CDN_RECOVERY_TOOL_PRIMARY` (131) + the pre-fail CDN check (130) are now the durable answer.

4. **Arc skeleton is an outline, NOT a ship-text record.** Don't reverse-cascade storyboard content back to the skeleton. Skeleton seeds production; storyboard and state are ship-source.

5. **`os.execv` preserves PID but replaces code.** The "PID unchanged" signal was misleading during debugging — a successful restart keeps the same PID. Check for new endpoints responding instead.

6. **The 10.16s audio for beat_05 Tessa line needed trimming via ffmpeg from the START (not end) to preserve "more careful" tail.** Kim's acoustic ear caught that the end-trim clipped her performance. Start-trim (0.2s leading silence) was the right answer.

7. **Contenteditable edits in the storyboard are browser-memory only until an explicit save.** This caused confusion when Kim "edited" dialogue, refreshed, and saw her edit reverted. Decision 151 `DIALOGUE_EDITS_MUST_PERSIST` closes this (already BUILT but needs server restart).

---

## 9. Resumption instructions (for next Claude picking this up)

1. **Read this doc first.** All context compressed here.
2. **Verify server code matches decisions.** `python3 Production/tools/production_server.py --smoke-test` or check `/api/beat/update_text` returns a structured error (new code) vs 404 (old code).
3. **Check state.json `updated_at`.** If more than a day old, Kim may have resumed on a different machine.
4. **Query Directus** `prod_preflight_reviews` last 3 rows to catch what was most recently approved.
5. **Query Directus** `prod_locked_decisions` for `date_locked='2026-04-17'` to see today's decisions.
6. **Load preflight skill.** Before ANY edit to governed files, run zero-error-qa Phase 0.
7. **Default to: keep pushing on beats 6-11 production.** Kim's workflow per §7 above.

Any deviation from the above — stop and ask Kim for direction.

---

## 10. Key file paths quick-reference

```
Server:
  Production/tools/production_server.py        — main server (today: 100+ edits)
  Production/tools/lib/directus.py             — fresh-conn rewritten
  Production/tools/recover_stuck_tasks.py      — CDN recovery CLI (new)
  Production/start_production_server.command   — launcher (-u flag added)

Audit + tools:
  Production/scripts/audit_beat_durations.py   — new audit (verdicts table)

Storyboard (live + source):
  Production/Event_1/storyboard_v37_prod.html  — Path B patched extensively
  Production/tools/build_storyboard.py         — source, future rebuilds
  Production/tools/patch_delay_trim.py         — trim controls source

State + backups:
  Production/Event_1/production_state.json                    — live state
  Production/Event_1/production_state.json.bak_*              — many backups
  Production/Event_1/preserved_winners/*.mp4                  — "good-before-change" preserves
  Production/Event_1/story_scene_tts_v2/line_03_tessa*.mp3    — new TTS for beat_03
  Production/Event_1/story_scene_tts_v2/line_05_tessa_trimmed.mp3 — 9.883s start-trimmed
  Production/Event_1/animation_clips/beat_0*_option_*.mp4     — all clips

Governance:
  Production/PIPELINE_BRAIN_v1.md              — §19 added
  Production/STORYBOARD_PIPELINE_LESSONS_LEARNED_April16_2026.md — §7.1 resolved + §8 §9
  Production/governance/storyboard-producer_governance.md     — Stitch decisions
  Production/TASK_GOVERNANCE_PROTOCOL.md       — new categories
  Production/RUNBOOKS/recover_stuck_wavespeed_task.md         — new runbook (id=44)

Directus (canonical):
  prod_locked_decisions ids 129-155 (see §4)
  prod_preflight_reviews ids 9, 12, 14, 17, 18, 19 (see §3)
  prod_activity_log ids 98-107+ — linking all the above
  prod_reference_docs id=44 (runbook), id=13 (PIPELINE_BRAIN v1)
  prod_locks (new collection for cross-machine semaphore)
  prod_voice_profiles id=3 (Tessa / Jessica voice)
```

---

## 11. Full Session Chronology (expanded detail per Kim's ask)

This section captures the FULL arc of the conversation, not just code deliverables. Every inflection point, every architectural decision, every Kim-pushback that shaped outcomes.

### 11.1 Opening: the BLOCKER bug
Kim reported: "Generate B+C silently fails on beat 2." Button shows "Submitting..." then reverts. No visible error. Spent initial ~30 min in Plan mode producing a debug plan (`/Users/kimberlysmith/.claude/plans/debug-why-generate-b-c-bright-sifakis.md`) predicting silent-200 from `_handle_add_options`. Plan was WRONG about root cause — real problem was deeper. This is lesson #1: **initial plan predictions can miss the actual root cause; live-debugging with logs is essential.**

### 11.2 Permission-prompt flood + the less-permission-prompts skill
Kim was clicking permission dialogs "every 5 seconds" as Round 1 agents spawned Bash calls. I paused agent dispatch, invoked `less-permission-prompts` skill, wrote `.claude/settings.json` with read-only Bash + Chrome MCP allowlist. Lesson: **any multi-agent batch should pre-approve read-only patterns before dispatch.**

### 11.3 The 4-agent Round 1 error scan
Kim approved the rigor. Dispatched 4 parallel Explore agents:
- Wide error scan across pipeline
- Find existing storyboard governance
- Find stitching/assembly infrastructure
- Directus schema audit

Results shaped the entire rest of the session. Key findings: 3 BLOCKERs (unbuffered stdout, daemon-thread restart, in-memory image overrides), 4 Two-Write Rule violations, no stitch endpoint existed, storyboard-producer governance was stale, `/api/animate/status` filtered out polling/failed options.

### 11.4 The Q1-Q5 debate (10 agents, 5 pairs of advocate + counter)
Kim picked "tighter way" — 10 agents on 5 contested topics. Verdicts registered (decisions 129-142, 137-142 backfilled):
- **Q1 (poll stuck-state):** Counter wins — fix urllib via http.client swap. Plus small watchdog defense-in-depth.
- **Q2 (recovery):** Counter wins initially (runbook), REVISED after frequency data (30% failure rate documented) → build the tool. Kim caught my bad estimate.
- **Q3 (image override):** Hybrid — disk primary + Directus async. Kim's cross-machine intent (Windows work) changed my verdict mid-session.
- **Q4a (stitch architecture):** Counter wins — multi-stage preview + commit. Kim added "edit after viewing preview, go back to storyboard" which solidified the design.
- **Q4b (stitch button location):** Advocate wins — in storyboard overlay per Kim's explicit "links to the appropriate portion of the storyboard section."

**Lesson:** initial agent recommendations are starting points. Kim's pushback on Q2 frequency estimate was crucial — I had underestimated WaveSpeed failure rate by 100x.

### 11.5 Tier 1 + Tier 3 implementation
Built Tier 1 blocker fixes, then Tier 3 resilience, then blind-spot remediation. Each phase had its own preflight row + 4+4 or reduced agent preflight. Adversarial reviews caught real issues:
- Tier 1 Phase 3: `_handle_animate` had the same bug as `_handle_add_options` (only the latter was initially fixed); C2 SSL OP_NO_TICKET missing; C4 CRITICAL race on HTML write.
- Tier 3 Phase 3: duration schedule too aggressive ([10,20,40,80,160]s → reduced to [5,15,45]s); state concurrency race; false-positive risks in recovery tool; pre-fail check blocking poller thread.
- Blind-spot Phase 3: audit duplicated `_find_beat_audio` (extracted), audio > 10s must raise not truncate, `text_modified_after_tts` flag never cleared, UNSELECTED verdict missing in audit.

**Lesson:** adversarial agents catch real bugs at ~1-3 HIGH findings per architectural batch. The ~20% overhead of running them is consistently worth it.

### 11.6 Terminal identification + restart button saga
Kim asked which of her Terminal windows to close. I used `ps -p PID -o ppid` to trace the parent → `start_production_server.command`. She closed it. Later: restart button failed ("Timed out — double-click .command file" toast). Diagnosis: `_do_restart` was a daemon thread, dying before `os.execv` ran. Fix landed.

Later still: Kim clicked Restart Server button after new code loaded — BUT the server PID stayed the same (37473). Initially confusing: did it actually restart? Answer: YES. `os.execv` **preserves PID but replaces process image**. The endpoint test (`/api/beat/update_text` returned structured error vs 404) proved new code was loaded.

**Lesson:** `os.execv` preservation of PID is a counter-intuitive signal when debugging restarts. Check endpoint behavior, not PID, to verify restart.

### 11.7 Ongoing WaveSpeed API instability
Hit timeouts 4+ times across the session. Each time:
1. Poll fails in long-running server
2. Fresh subprocess sometimes works (Tier 1 fix is architectural, not a guarantee during upstream outage)
3. BUT CDN is separately reachable → CDN-pull recovery pattern works

Recovered tasks from CDN 3 times today:
- beat_02 Options B+C (task IDs 96f27bae..., 1794ed4b...) — early in session
- beat_03 Options B+C (task IDs 2c09..., 4839...) — mid-session
- beat_05 Options B+C (task IDs 5dce..., ce20...) — late session

**Lesson:** WaveSpeed API has documented ~30% transient failure rate. Always check CDN before accepting a "failed" task as lost.

### 11.8 Script drift discovery (the beat_03 "It's OK" incident)
Kim noticed beat_03 lipsync had good tone but didn't lipsync the words "It's OK." Her intuition: "we DID remove 'It's OK' from the script at some point, and then you accidentally left it in." I researched: arc skeleton (`Arc Skeletons/ARC_01_SKELETON_FINAL.md`) said *"I'm sorry. I'm Tessa. I'm from Dragonshell. It's not my best day."* Storyboard said *"It's OK. I'm fine. I fell. I hurt my shell a little."* Genuine drift — Kim remembered correctly.

Initial cascade audit found 5 MAJOR divergences between skeleton and storyboard. I proposed Option A (full cascade). Kim pushed back: **"why do we need the dialogue in the skeleton to match what we produce via the pipeline? can't the skeleton just stay as a dialogue basis and I expand out from there every time?"**

That question reshaped the architecture. Traced every downstream consumer of the skeleton — NONE reads it for ship-text. Skeleton is upstream-only (intake-briefer, storyboard-seeding). So reverse-cascading was WRONG.

Result: decision 147 superseded by 150 `SKELETON_IS_OUTLINE_NOT_SHIP_SOURCE`. One true drift fix (beat_03 text), zero reverse-cascades of Kim's intentional 11-beat expansion.

**Lesson:** architectural assumptions should be validated against actual downstream readers. Kim's clinical instinct ("why does this matter?") was the right pressure test.

### 11.9 TTS regeneration for line_03
ElevenLabs API call with:
- Voice: Jessica (ID `cgSgspJ2msm6clMCkdW9`)
- Model: `eleven_v3`
- Stability: 0.5, similarity_boost: 0.8, style: 0.3, speaker_boost: true
- Cost: ~$0.50

Registered Tessa voice profile in `prod_voice_profiles` (id=3) since only Myrrhin + Guide Bird existed before. **Lesson:** every new character voice should get a Directus profile entry at first use.

### 11.10 Contenteditable edits ephemeral — `DIALOGUE_EDITS_MUST_PERSIST` build
Kim edited beat_03 dialogue in the textarea, hard-refreshed, saw her edit reverted. **Contenteditable changes are browser-memory only until an explicit save.** The "Export Selections" only captures animation selections, not dialogue text.

Built `/api/beat/update_text`:
- Persists to `production_state.json`
- Atomically patches the HTML file's L[] entry (tmp+rename, unique suffix per-PID+UUID, threading.Lock around write)
- `</script>` injection escape (CRITICAL security fix from Phase 3 review)
- Client: on-blur POST, visible save indicator
- Fire-and-forget Directus audit

Code ready; activates after server restart.

### 11.11 Audio trim for beat_05 (10.16s → 9.883s)
Kim wanted the ORIGINAL audio preserved because end-trim clipped her performance. Pivoted to **start-trim** (0.2s leading silence drop). Lossless mp3 stream copy via ffmpeg `-c copy -ss 0.2`. Kim A/B-tested in QuickTime. Approved.

**Lesson:** for creative audio trims, end-trim is the obvious default but start-trim often preserves more performance. Let Kim listen before committing.

### 11.12 Trim-end UI bug (late-session discovery)
Kim: "it keeps returning the end trim to 5.0s every few seconds." Root cause: `attachVideoListeners` attached metadata-loaded handler to ALL option videos. Option A (5s legacy) loaded → clamped `_beatTrims[ri].end = 5.04`. Option B (10s new) loaded → `if (end > dur)` check was false for `5.04 > 10.04` → no update. Every 15s pollStatus re-render re-fired the listener and reset to Option A's duration.

Fix: check `v === selVid` before updating — only selected video's metadata drives dur/max/trim_end. Decision 155.

**Lesson:** when multiple variant-duration clips coexist in a beat, every "video listener" needs to know which is the active one. Don't naively iterate all.

### 11.13 Diagnostic test accidentally overwrote beat_05 image
While debugging drag-drop I ran a curl POST to `/api/assign-image` with `tessa_closeup_4x3` — to verify server-side flow works. That overwrote Kim's actual pick (`tessa_initial_4x3`). She noticed. I restored.

**Lesson:** NEVER use live state as a test fixture without explicit user consent. Always restore after.

### 11.14 Rule 20 backfill (6 missed decisions)
Kim caught that I was batching `prod_locked_decisions` registrations at end of big work chunks instead of moment-of-decision. Backfilled 6 missing verdicts (137-142). Registered `SKELETON_IS_OUTLINE_NOT_SHIP_SOURCE` 150 (correcting earlier mis-framed 147).

**Lesson:** Rule 20 CONFIDENT registration must happen **in the response where the verdict is first issued**, not at phase boundaries. Include a "Registered: KEY" footer on that same turn.

### 11.15 Cross-machine BS1 consequences: failing closed
Kim's Windows-machine intent drove BS1 (Directus semaphore + fail-closed). But the tradeoff: every `mutate_state` now takes 2-3s due to Directus round-trip. Noticed as "slow drag-drop" in the UI. Mitigation: env-var `PRODUCTION_SERVER_SINGLE_MACHINE=1` escape hatch for offline/single-machine speed.

**Lesson:** cross-machine safety has a ~3s/mutation latency cost. Worth it for correctness; escape hatch documented for offline work.

### 11.16 The 4+4 agent adversarial review pattern worked but with diminishing returns
Ran ~40+ agents across the session. By Tier 3 blind-spots, the pattern had locked in. Agents consistently caught 1-3 HIGH/CRITICAL issues per architectural batch. **But** we also hit cases where a 4+4 wasn't needed (e.g., duration fix — 1+1 would have sufficed). Rule 19/Phase 0 "when in doubt, classify as architectural" forced over-rigor.

**Lesson:** trust Phase 0 classification as a floor, not a ceiling. If scope is truly narrow, a smaller agent pass is legitimate with explicit justification.

---

## 12. The meta-pattern of today's bugs

Every UI bug today followed the same shape:

**"Server has current state; HTML file on disk has stale snapshot of state; UI reads from the HTML snapshot instead of fresh server state."**

- `DIALOGUE_EDITS_MUST_PERSIST` (151): contenteditable → server knows, HTML doesn't
- `LIPSYNC_UI_MUST_SUPPORT_RERUN` (153): selected_option changes → server knows, lipsync state flag doesn't update
- `ASSIGN_IMAGE_MUST_PATCH_STORYBOARD_HTML` (154): drag-drop → server overrides, HTML L[] i: doesn't
- `TRIM_END_SELECTED_VIDEO_ONLY` (155): pollStatus re-render → re-reads stale HTML → resets user's trim_end

**The architectural fix (for future build):** every `StateManager.mutate_state` call that updates a field visible in the storyboard HTML should ALSO call a new `patch_storyboard_field(beat_id, field, value)` helper that updates the L[] entry. Then hard-refreshes always show truth.

Scope: ~100 LOC (one helper + 5-10 call sites). Would close 4 decisions (151, 153, 154, 155) simultaneously. Candidate name: `STORYBOARD_HTML_AUTO_PATCH_HELPER`. Proposed for next session's Tier 5 build.

---

## 13. Session-end status

**Kim's morale:** exhausted but progressing. Session went ~8 hours. Main energy drains: WaveSpeed outages (3×), drag-drop UX confusion (2×), trim-end bug, lipsync-rerun UX friction (3× — beats 2, 3, 5).

**Claude's accuracy:** caught most bugs on first review; missed Rule 20 backfill and was wrong about Q2 frequency (corrected by Kim). Good adversarial review discipline throughout.

**What's saved and restorable:**
- Every file modification logged to `prod_activity_log`
- Every decision in `prod_locked_decisions` with supersede chain intact
- Preserved winners directory holds every pre-change MP3/MP4
- State.json has many `.bak_*` files tagged by what-was-about-to-change
- Three new Directus collections populated (`prod_locks`, `prod_voice_profiles` entry, `prod_reference_docs` entries)

**Next-session entry point:** see §9 (Resumption Instructions). Default: lipsync beats 6-11.

