# Lessons Learned — Asset Findability Build Session (LD-421/422)

**Date written:** 2026-04-27
**Session work:** 2026-04-26 (Desktop) + parallel terminal CLI execution
**Primary deliverables:** LD-421 ASSET_FINDABILITY_OVERHAUL_V1, LD-422 ASSET_FINDABILITY_BUILD_V1, locked HTML preview pattern (feedback_file_links.md), 8 prod_assets registrations (Event 1 canonical finals + recovered audio + library index), CLAUDE.md Rule 34, Production/specs/asset_findability_overhaul_v1.md, hook-enforce-review-20260503 scheduled task

---

## Context

A 30+ exchange session that started with Kim's frustrated "find the approved X" failures, spanned a 2-Opus diagnostic, a tech-spec build, an HTML-preview-pattern discovery, 4 canonical Event 1 finals registered, lost-audio recovery, terminal CLI handoff, and ended with two follow-up scheduled tasks queued. Multiple judgment calls had to be reversed mid-stream. This document captures the durable lessons — process AND technical — so future sessions don't repeat the failure modes.

---

## Process / Behavioral Lessons

### LL-1. Diagnostic agents can answer the wrong half of the problem

**Situation:** Two parallel Opus diagnostic agents produced thorough root-cause analysis of "find the approved X" failures. Synthesis was clean. But Kim's actual pain wasn't finding APPROVED files (she says "Good enough!" — easy to capture). Her HARD case was finding IN-PROGRESS iterations by distinguishing features ("the one where second half had better lipsync"). The agents optimized for the easy half.

**Lesson:** When receiving a diagnostic brief from sub-agents, verify with the user WHICH HALF of the problem matters most before going deep on synthesis. The agents had no way to know — they answered what was framed.

**Recommendation:** Phase 4 judgment-call gate (per tech-spec skill) should always include a "did we diagnose the right pain?" check, not just "which approach to ship." Add an explicit "what's your worst case?" question to the user before agent dispatch.

---

### LL-2. Alarmist language in operational notes causes user panic

**Situation:** I prefixed a Directus notes field with `PROTECTED_LIBRARY_PHASE_B_MODULE_SOUNDS_20260426`. Kim immediately panicked: "wait wait 'protecting'??? is the rest in danger of deletion???" The word "protecting" implied something needed protecting FROM — i.e., that other things might get deleted. Nothing in the system can delete files; registration is purely additive Directus rows.

**Lesson:** Operational labels (Directus notes prefixes, log markers, file headers) should describe WHAT the row IS, not protective intent. "REGISTERED_" or "INDEXED_" describes the action neutrally. "PROTECTED_" implies threat.

**Recommendation:** Audit existing Directus notes for alarmist prefixes. New convention: `REGISTERED_<scope>_<topic>_<date>` or `INDEXED_<scope>_<topic>_<date>`. Never "PROTECTED" / "SAFE" / "DO_NOT_DELETE" as labels — those words frighten users without conveying real meaning.

---

### LL-3. Test assumptions about user environment instead of arguing from docs

**Situation:** I sent file:// markdown links to media files claiming they should be clickable per Claude Code's system prompt. Kim reported: "nothing happens they dont open." I initially diagnosed it as macOS focus rules. Reality: file:// links don't render as clickable in Kim's chat at all. After multiple failed test rounds, the only verified working pattern is HTML preview page in Safari via Bash `open` + `osascript activate`.

**Lesson:** When the user says "this doesn't work for me," don't argue from theory or system documentation. Build a 2-link test, ask the user to click, observe behavior. The system prompt describes intent; the actual rendered chat is what matters.

**Recommendation:** For any chat-visible affordance (links, buttons, inline media), the verification is "does the user click and see the expected behavior" — not "the docs say this works." Test before locking patterns.

---

### LL-4. Memory rules need to actually be checked, not just exist

**Situation:** `feedback_file_links.md` existed since session 919cdad0 (months ago) saying "always use file:// absolute URLs for local files." During the file-link investigation, I belatedly realized I had ignored this rule for the entire session. The rule was wrong (file:// doesn't work) AND I hadn't been following it. Two failures: stale rule + ignored rule.

**Lesson:** Memory rules must be re-verified at session start AND when the topic surfaces. Don't lean on training intuition for things that have explicit memory rules. When a topic touched by a memory rule comes up, re-read the rule — don't assume what it says.

**Recommendation:** Strengthen `feedback_file_links.md` (DONE — verified pattern locked: HTML preview page in Safari only, NEVER file:// in chat). Add a session-start check: "any memory file mentioning the current topic — re-read first."

---

### LL-5. "Defer until demand surfaces" is wrong when demand is already happening

**Situation:** After agreeing to direction-only LD-421, I recommended deferring the build until storyboard work created concrete usage demand. Kim pushed back: "even with storyboard there are lots of times when i have to ask you to do stuff on the side and that should also work, i just lost a whole weekend on it." The demand was already constant; my "wait for demand" framing was tone-deaf.

**Lesson:** "Defer until validated need" is a real principle, but it doesn't apply when the user has already reported active recurring pain. The pain IS the validation. Recommending defer in that context dismisses the user's reported experience.

**Recommendation:** Before recommending defer, ask: "what's been the cost of NOT having this in the last 7-30 days?" If the answer is concrete (a lost weekend, repeated failures, time burn), defer is the wrong call.

---

### LL-6. Don't dismiss existing user infrastructure

**Situation:** Kim asked me to schedule a 7-day reminder. I started down the /schedule (RemoteTrigger) path, then flagged that remote agents can't access local files. Spent multiple turns explaining limitations. Kim said "look at this weekly preflight thin in my left hand column" — she ALREADY had local scheduled tasks running fine via `mcp__scheduled-tasks__*`. I'd missed her existing setup entirely.

**Lesson:** When the user says "I do this all the time," check their existing setup BEFORE proposing alternatives. The infrastructure they already have is a strong signal of what's available and what works.

**Recommendation:** When proposing automation/scheduling/integration, first run `list_scheduled_tasks` (or equivalent inventory) and visually inspect the user's sidebar / dashboard. Match patterns to existing setup; don't introduce new mechanisms when working ones exist.

---

### LL-7. Cross-platform requirements must be EXPLICIT in task prompts

**Situation:** Spawned a task chip to wire visible-magic to registered_write.py. The chip prompt referenced LD-327/LD-367 (cross-platform locked decisions) but didn't EXPLICITLY say "must work on both Mac and Windows." Kim caught it: "why are we doing the visible magic thing locally? it would be better if visible magic works from either computer." I had to spawn a NEW chip with explicit cross-platform language and instruct her to dismiss the first.

**Lesson:** When work output runs on multiple machines / multiple environments, that requirement must be HARD-stated in the task prompt, not implied via locked-decision references. Trusting governance to enforce implicitly fails when the executing agent reads the prompt at face value.

**Recommendation:** Any spawned task / scheduled task / spec that produces multi-environment artifacts must include a "MUST WORK ON: <list of environments>" section near the top. Spell out specific path conventions, env vars, platform branches.

---

### LL-8. Phantom Directus collections fail silently in production

**Situation:** The visible-magic skill has been writing to `prod_magic_clips` collection — which DOES NOT EXIST in Directus. Every magic render Kim has made silently failed to register. The `production_server.py` magic render endpoint also writes to non-schema fields (`kind=`, `session_date=`, `activity_type=`) that get silently dropped. Both failures persisted for unknown duration without surfacing.

**Lesson:** Any code path that POSTs to a Directus collection should validate collection existence at first-use, not assume. Schema-mismatched fields fail silently (Directus accepts the row and drops unknown fields). Without a "registered count vs. expected count" audit, these failures stay invisible.

**Recommendation:**
- Add a startup check to skills that write to Directus: GET /collections + verify named collection exists; emit clear error if not.
- registered_write.py should validate field names against the live schema (cache TTL'd) before POST.
- Weekly audit should compare prod_assets row count to skill-emitted "registration attempted" count and surface drift.

---

### LL-9. State changes mid-session need explicit external-handoff updates

**Situation:** Phase B canonical changed from id=41 to id=47 AFTER the terminal CLI handoff prompt was already pasted. The terminal CLI session would have followed the original prompt's reference to id=41 and missed the supersession. I had to provide a separate update message for Kim to paste.

**Lesson:** Long sessions with external dependencies (terminal CLI, scheduled tasks, spawned chips, in-flight remote agents) accumulate state changes that don't propagate automatically. Any state change that affects an in-flight external process needs an explicit delta message.

**Recommendation:** When a state change happens mid-session (a new asset id, a superseded row, a refined scope), check: "does any external process I've already triggered need to know about this?" If yes, generate an update message immediately rather than waiting for the user to ask.

---

### LL-10. Backfill scope is a Kim decision, not a derived spec output

**Situation:** Initial spec scoped backfill at "register all 1,400+ disk files in Event_1 with auto-classification." Kim reframed mid-build: "we don't need all the rejected assets. what we need is the component parts for all the videos that we finalize." Backfill collapsed from 1,400 files to ~5-8 finals. Then she narrowed further: "dont even worry about including the component parts in the back-view sweep. they can be included in the future. right now we will JUST look for the finalized videos." Final scope: 4 finals + lost SFX + library index = 6 rows.

**Lesson:** Backfill scope (what to register from existing chaos) is a stakeholder decision about what they care about finding later. The spec can propose; the user must confirm scope. Don't assume "register everything" is the right answer just because it's technically possible.

**Recommendation:** Any backfill spec must include explicit "Kim choose scope" gate before execution. Default proposal can be aggressive (register everything) but the actual scope is set by stakeholder, not spec. Never auto-execute backfill without user-confirmed scope.

---

## Technical / Architecture Lessons

### LL-11. Schema gaps cause silent state loss at scale

**Situation:** prod_assets had 9 fields. `status` was a fixed Postgres enum without 'approved' as a value. Result: 34/34 rows had `status='pending'` even after Kim verbally approved them. Her verdicts lived as freeform text in `notes` (14/34 rows). No structured way to filter for "approved canonical" — every "find the approved X" query had to text-search notes, which broke down when iteration counts grew.

**Lesson:** When a state transition has no structured field, the state WILL be lost. The schema is the contract; freeform notes are the loss vector.

**Recommendation:** Audit every Directus collection for state transitions captured in notes/text rather than typed fields. Promote to enum/boolean/timestamp when found. Specifically: kim_verdict, kim_approved_at, is_current, supersedes — all must be first-class fields.

---

### LL-12. Two-Write Rule needs a wrapper to be enforced

**Situation:** All previous "register asset + log activity" calls were ad-hoc Python in skill bodies. Each skill wrote both calls separately; many skipped the activity log; some wrote to wrong collections (LL-8). Drift was inevitable because enforcement was behavioral, not structural.

**Lesson:** Behavioral discipline (every author remembers the second write) cannot be sustained across 30+ skills and a year of code drift. Enforcement requires:
- A wrapper library that does both writes atomically
- A hook that intercepts direct writes that bypass the wrapper
- A compliance gate that validates skills import the wrapper
- A periodic audit that catches drift

**Recommendation:** registered_write.py is the wrapper (BUILT in this session). Hook A intercepts direct writes (BUILT). Compliance Gate Check 6 validates wrapper import (BUILT). Weekly audit extension (PARTIAL — needs Production/scripts/weekly_preflight_audit.py extension to scan for direct urllib POSTs outside wrapper).

---

### LL-13. 6.2% disk-to-Directus match rate quantifies the chaos

**Situation:** Walked Production/Event_1/ — 2,485 media files / 1,503 unique basenames. Cross-referenced against Directus prod_assets/prod_visual_assets/prod_audio_assets — 93/1,503 basename matches (6.2%). The asymmetry (lots of disk orphans, ~0 ghost rows) proved the problem is missing writes, not stale writes.

**Lesson:** Always measure the gap before designing the fix. Disk-to-Directus match rate is the canonical "asset findability gap" metric. Asymmetry direction tells you whether to fix writes (orphans → missing writes) vs. cleanup (ghosts → stale writes).

**Recommendation:** Add a quarterly "asset orphan rate" measurement to the weekly_preflight_audit. If disk-orphan rate exceeds 50% in any production directory, surface as a CRITICAL blocker — that means the wrapper is being bypassed somewhere.

---

### LL-14. Sub-agent sandboxed paths leak into the registry

**Situation:** rows 70-71 of prod_visual_assets have `file_path = /sessions/brave-optimistic-tesla/mnt/Claude Mindfulnest Project Files/...`. These are container paths from a sub-agent run that no longer resolve on Kim's Mac. Pollution from sandbox environments leaking into the canonical registry.

**Lesson:** Sub-agents run in sandboxed paths; their writes can pollute the parent registry if path validation isn't done at the wrapper level.

**Recommendation:** registered_write.py validates `file_path.startswith(PROJECT_ROOT)` and rejects sandboxed paths with clear error (BUILT into the spec). Backfill cleanup task: query prod_visual_assets for `file_path` containing `/sessions/` and clean up.

---

### LL-15. Local vs. remote scheduled tasks are easy to confuse

**Situation:** Kim has a "Weekly preflight" routine in her sidebar — created via `mcp__scheduled-tasks__create_scheduled_task` (LOCAL, runs in her Claude Code session on her Mac). I almost created a /schedule remote agent (RemoteTrigger, runs in Anthropic cloud) for the hook log review — would have failed because remote can't access ~/.claude/. Both mechanisms appear in the same "Routines" sidebar; same UI, different infrastructure.

**Lesson:** Two scheduling mechanisms exist:
- **`/schedule` → RemoteTrigger** → Anthropic cloud, NO local file access, NO local env vars
- **`mcp__scheduled-tasks__*`** → Local Claude Code session, FULL local file access, runs on user's machine

**Recommendation:** Decision tree:
- Task needs local file/env/process access → `mcp__scheduled-tasks__*`
- Task is git/Directus/cloud-only → `/schedule` remote agent
- Both appear in the same sidebar; check `list_scheduled_tasks` AND `RemoteTrigger {action: list}` to inventory both.

---

### LL-16. HTML preview is the ONLY chat-visible file-show pattern

**Situation:** After multiple failed file:// link tests, the verified working pattern is:
1. Write `_preview_*.html` to `Production/_previews/` with inline `<video controls>`, `<audio controls>`, `<img>` tags
2. Bash `open <path>` + `osascript -e 'tell application "Safari" to activate'`
3. ALWAYS include a markdown link to the HTML file in chat (relative path + absolute path fallback)

**Lesson:** This pattern works because Safari handles file:// from same-parent directory reliably; relative paths in `<source src="../Event_1/foo.mp4">` resolve correctly; the `osascript activate` brings the browser to foreground.

**Recommendation:** Locked as feedback_file_links.md. Use for any multi-file review (3+ files). For single files, Bash `open -a "QuickTime Player" + osascript activate` works. NEVER bare file:// markdown links in chat — they fail silently.

---

## LDs Created This Session

| LD | Severity | Status | Summary |
|---|---|---|---|
| LD-421 ASSET_FINDABILITY_OVERHAUL_V1 | HIGH | active | Direction lock + amended (iteration_notes refinement, build approval) |
| LD-422 ASSET_FINDABILITY_BUILD_V1 | HIGH | active | Build execution lock (terminal CLI session) |
| LD-423 (parallel) | — | — | Stitch Editor build (separate parallel work) |

## Action Items / Forward-Looking

1. **Wire visible-magic to registered_write.py** — task chip queued (cross-platform variant). Highest priority remaining work; closes 70%→100% gap on asset findability for the magic workflow.
2. **Hook enforce review 2026-05-03** — local scheduled task fires automatically; recommends FLIP/TUNE/WAIT/BROKEN.
3. **Phase A no-bed identification** — open thread; HTML preview at Production/_previews/phase_a_no_bed_candidates_20260426.html awaits Kim's listen-through.
4. **Resolution v6 audio re-mix** — Kim picks ambient bed from Phase B Sounds folder (id=46) + magic SFX (id=44) → audio-producer mix → register as v6_with_audio successor.
5. **Wire remaining 7 dark/partial skills** — scene-to-production, elevenlabs-tts, magic_compositor.py, video-producer audit, audio-producer audit, storyboard-producer audit, module-json-builder. Tech-spec recommended for each.
6. **Compliance Gate Check 6 audit** — extend weekly_preflight_audit.py to scan SKILL.md files for direct urllib POSTs outside the wrapper.
7. **Sandboxed path cleanup** — query prod_visual_assets for `/sessions/` paths; clean up rows 70-71 and similar.
8. **Quarterly asset orphan rate measurement** — add to weekly audit; surface CRITICAL if disk-orphan rate >50% in any production directory.

## Files Referenced

- `Production/specs/asset_findability_overhaul_v1.md` — full spec
- `Production/_previews/preview_test_20260426.html` — locked HTML preview template
- `Production/_previews/canonical_finals_event1_v2_20260426.html` — Kim's confirmation preview
- `.auto-memory/feedback_file_links.md` — locked HTML preview pattern rule
- `.auto-memory/project_asset_findability_overhaul.md` — project memory for LD-421
- `.auto-memory/session_20260426_2028.md` — full session digest
- `Production/scripts/asset_findability_hook.py` — Hook A (terminal CLI built)
- `Production/scripts/asset_lookup_hook.py` — Hook B (terminal CLI built)
- `Production/tools/registered_write.py` — wrapper library (terminal CLI built)
- `Production/tools/find_asset.py` — find tool (terminal CLI built)

---

**End of Lessons Learned — 2026-04-27**

Reference: `prod_locked_decisions` LD-421, LD-422; `prod_activity_log` ids 1305, 1306, 1319-1322, 1340, 1341, 1345; `prod_assets` ids 40-48 (Event 1 canonical set + recovered audio + library index).
