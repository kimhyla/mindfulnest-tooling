# HANDOFF — Q1 Part 2 Conditional Opus Reviewer Subagent — Implementation

**Header**

- **Title:** Q1 Part 2 — Conditional Opus Reviewer Subagent — Implementation
- **Target session:** Terminal CLI (autonomous-mode authorized for documented work only; HALT gates per DS-26 still active)
- **Source spec:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md` — Dropbox-rooted (canonical root #1)
- **Source session:** gallant-bouman-804b4f worktree (this handoff authored from worktree; implementation runs against canonical roots, NOT inside `.claude/worktrees/`)
- **Estimated time:** 5-7 hours machine + ~1.5 hours Kim review
- **Authority:** Cursor verdict on v2 review handoff = AUTHORIZE_IMPLEMENTATION on `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v2.md`; LD 579 `Q1_PART1_STOP_HOOK_INSTALLED_V1` (Part 1 prerequisite); LD `GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1` (id=578); LD `WORKTREE_CONFUSION_PREVENTION_V1` (DS-27 v2 dual-canonical).
- **Authoring template:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — Dropbox-rooted (canonical root #1)
- **Self-classification:** ARCHITECTURAL (governance-class change; introduces first subagent-spawn hook in MindfulNest hook surface; per spec §2 "No existing subagent-spawn mechanism in MindfulNest hooks").
- **Confidence:** [CONFIRMED from spec authoring trail; spec v1 line ranges verified read 2026-05-08]

---

## §1 Mission

Implement the Q1 Part 2 conditional Opus reviewer subagent per the locked tech spec — a `Stop`-event hook that, when the most recent assistant turn (a) wrote to an "infrastructure" file (allow-list in spec §6) AND (b) the assistant text contains state-claim regex matches, spawns an Opus reviewer subagent via `claude -p` headless mode, parses the reviewer's structured JSON verdict, and renders an inline stderr banner with PASS/WARN/FAIL findings. Hard cap 7 spawns/session; 4-layer recursion guard; warn-only failure mode (mirrors Part 1). Phases A-G per spec §11; multipass per file edit; dual-canonical absolute-path discipline; activity-log row at go-live.

---

## §2 Scope

**Changes in scope (this implementation session):**

1. **Phase A — spawn-mechanism validation** — author standalone test script under `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/q1_part2_spawn_smoke.py` (NEW) that calls `claude -p "<prompt>" --output-format json` from a Python parent, parses the response, verifies env-var inheritance, and confirms cost/token fields are present. [INFERRED — Claude Code SDK headless JSON shape is implementation-time discovery per spec §11 Phase A.]
2. **Phase B — hook script scaffolding** — author `~/.claude/hooks/stop_conditional_opus_reviewer.py` (NEW) implementing the L0-L5 trigger logic from spec §3.2; dry-run mode (no spawn yet, emits "would spawn" stderr lines).
3. **Phase C — settings.json wiring** — append second hook to `~/.claude/settings.json` Stop array (peer to Q1 Part 1's `stop_state_claim_scan.py`); backup file produced first as `~/.claude/settings.json.backup_q1_part2_<ISO>`.
4. **Phase D — prompt template + spawn invocation** — wire actual `claude -p` spawn with the §7 prompt template; capture stdout JSON; render stderr banner per spec §9; write secondary log file `~/.claude/state/q1_part2_session_<session_id>.log`.
5. **Phase E — cost monitor + session log** — counter file `~/.claude/state/q1_part2_spawns_<session_id>.txt` (single integer, atomic increment); soft alert at 5/7; hard cap at 7; ceiling-reached stderr line on 8th trigger.
6. **Phase F — recursion guard validation** — synthetic-recursion fixtures testing each of the 4 guards in isolation per spec §10 + §16.4 fixtures F18-F21.
7. **Phase G — kill-switch + LD authoring** — document `MN_Q1_PART2_NO_CAP=1` env override + settings.json removal procedure per spec §15; POST `prod_locked_decisions` row `Q1_PART2_INSTALLED_V1` documenting the design lock + linking spec.
8. **Activity log POST** — `prod_activity_log` row `Q1_PART2_CONDITIONAL_REVIEWER_LIVE` documenting go-live.

**Out of scope (do NOT touch in this session):**

- Q1 Part 1 hook (`~/.claude/hooks/stop_state_claim_scan.py`) — stays unchanged per spec §3.1. Part 2 is registered SECOND in the Stop array; Part 1 runs first.
- Q1 Part 3 — explicitly deferred per spec §0.1; structured-output schema is a future Q1 layer, NOT this implementation.
- Directus-write triggers (Bash POST to prod_locked_decisions) — explicitly deferred to v2 amendment per spec §6.2.
- `prod_blockers` auto-write for FAIL verdicts — explicitly deferred to v2 amendment per spec §3.4 / §12 open decision #1.
- Schema changes to `prod_locked_decisions` / `prod_activity_log` / `prod_blockers` — none required.
- Modifying DS-22 SAVE-time scan logic — Part 2 is purely additive (mirrors Part 1's relationship to DS-22).
- Touching the main RN app CI/CD (per memory `project_main_app_cicd_greenfield_lock.md`) — Q1 Part 2 is a Stop-hook subagent, not CI/CD; no overlap. [CONFIRMED from spec §13 gate 6.]
- Editing files inside `.claude/worktrees/<name>/` — DS-27 v2 dual-canonical hard rule.

---

## §3 Pre-flight (verify before starting Phase A)

### §3.1 Files to read first (anchored citations per HANDOFF_TEMPLATE_v2 anti-pattern #7)

| Anchor target | v2 anchored check |
|---------------|-------------------|
| Spec end-to-end | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md`. Capture line ranges for §3 Proposed Design, §6 Trigger Criteria, §7 Reviewer Prompt Template, §8 Cost Model, §10 Recursion Guard, §11 Implementation Phases, §13 Pre-Implementation Gates, §16 Testing Plan. Quote one verbatim sentence from each section to prove the read happened. |
| Cursor verdict on v2 review | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v2.md`. Anchor: `## Step 3 — After Cursor responds` heading. Capture line range. Confirm verdict block contains `AUTHORIZE_IMPLEMENTATION` (or AMEND_V2 with v2 spec authored AND re-authorized). |
| HANDOFF_TEMPLATE_v2 structure | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md`. Anchor: `## Required structure` heading. Capture line range. Quote the 7 required sections list verbatim. |
| Q1 Part 1 hook (the precedent) | Read `~/.claude/hooks/stop_state_claim_scan.py`. Anchor: the Stop-event entrypoint function (typically `def main():` or top-level `if __name__ == '__main__':`). Capture line range. Quote the regex pattern + tool_use suppression check verbatim. This is the precedent Part 2 mirrors and registers AFTER. [CONFIRMED reference from spec §2 lines 54-58.] |
| Q1 Part 1 spec | Read `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/Q1_PART1_STOP_HOOK_SPEC_v1.md`. Anchor: §"Output mechanism" heading. Capture line range. Confirm Part 1's stderr banner format — Part 2 mirrors this format per spec §9. |
| settings.json current Stop wiring | Read `~/.claude/settings.json`. Anchor: `"Stop"` key under `"hooks"`. Capture line range. Quote the existing Stop-array entry verbatim. Phase C will APPEND to this array, not replace. |
| Step 2.5b regex (the canonical) | Read `~/.claude/skills/mn-context/SKILL.md`. Anchor: `## Step 2.5b` heading. Capture line range. Quote the regex line verbatim. Part 2's L4 trigger uses this same regex. [CONFIRMED reference from spec §2 lines 60-61, §3.2 L4 row.] |

### §3.2 Conditions to verify

1. Confirm Cursor verdict on the Q1 Part 2 spec is `AUTHORIZE_IMPLEMENTATION` (or `AMEND_V2` followed by an authorized v2). Source: Cursor review handoff at `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v2.md` final-report block OR `prod_activity_log` row `CURSOR_REVIEW_PASSED_Q1_PART2_SPEC` OR `prod_locked_decisions` notes citing the verdict. [CONFIRMED — handoff v2 § "Step 3 — After Cursor responds" branches on the verdict; agent must verify before proceeding.]
2. Confirm Q1 Part 1 is live: `ls -la ~/.claude/hooks/stop_state_claim_scan.py` returns a non-empty file. Verify Part 1's entry exists in `~/.claude/settings.json` Stop array. [CONFIRMED reference: LD 579 `Q1_PART1_STOP_HOOK_INSTALLED_V1`, spec §2 lines 54-58.]
3. Confirm Kim's explicit approval (this session) for Q1 Part 2 implementation. Evidence: chat-message quote OR `prod_locked_decisions` notes containing "Q1 Part 2 implementation approved by Kim YYYY-MM-DD" OR a `Q1_PART2_IMPLEMENTATION_APPROVED` row in `prod_activity_log`. The implementation MUST NOT begin without this evidence.
4. Confirm both canonical roots are reachable:
   - `ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/"` (canonical root #1 — Mindfulnest project)
   - `ls -la "/Users/kimberlysmith/Projects/"` (canonical root #2 — tooling repos / future RN app)
   - `ls -la ~/.claude/` (global Claude config — outside-canonical-but-allowed exception per HANDOFF_TEMPLATE_v2 §"Operational consequence").
5. Confirm Directus reachable via `try_post_or_queue` smoke (post-and-rollback pattern, NOT a no-op).
6. Confirm `claude -p` headless invocation is available on this machine: `which claude && claude --version`. If absent, Phase A blocks until Kim installs Claude Code CLI in a path the hook can resolve. [INFERRED — `claude -p` availability is a prerequisite per spec §11 Phase A.]

---

## §4 HALT gates

**Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.

Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

### Gates (must all be MET before Phase A begins)

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|------------------|-----------------|-------------|
| 1 | Does the Q1 Part 2 spec v2 exist and is it readable? (Or v1 if no AMEND_V2 was triggered.) | `ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md"` returns size > 0 AND mtime is plausible. If a v2 was authored after Cursor AMEND_V2, that file MUST exist instead. | File exists, size > 20 KB, readable. | Write `HALTED_AWAITING_AUTHORIZATION` row citing this gate; write halt-report to `Production/docs/HALT_AWAITING_AUTHORIZATION_<DATE>.md`; surface to Kim |
| 2 | Has Cursor reviewed the spec and emitted `AUTHORIZE_IMPLEMENTATION`? | Final-report block at the bottom of `HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v2.md` (anchor: `## Step 3 — After Cursor responds`) OR a `CURSOR_REVIEW_PASSED_Q1_PART2_SPEC` row in `prod_activity_log` OR `prod_locked_decisions` notes for `Q1_PART2_INSTALLED_V1` (predecessor draft) | At least one such artifact dated >= 2026-05-08 with verdict text containing `AUTHORIZE_IMPLEMENTATION`. AMEND_V2 verdict requires v2 spec authored AND re-reviewed AND re-authorized — stale AMEND_V2 fails this gate. | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface |
| 3 | Is Q1 Part 1 (Stop hook) live and registered in settings.json? | `ls -la ~/.claude/hooks/stop_state_claim_scan.py` returns non-empty file AND `~/.claude/settings.json` Stop array contains an entry referencing this script. | Both checks pass. LD 579 `Q1_PART1_STOP_HOOK_INSTALLED_V1` exists in `prod_locked_decisions`. | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface. (Part 2 is layered ON TOP of Part 1 and presumes Part 1 is the broad sieve. Without Part 1, Part 2's "fills the gap Part 1 leaves" rationale collapses per spec §0.1.) |
| 4 | Has Kim explicitly approved Q1 Part 2 implementation in THIS session? | Chat-message quote in current session OR `prod_locked_decisions` notes for `Q1_PART2_INSTALLED_V1` / draft thereof containing "implementation approved by Kim YYYY-MM-DD" OR a `Q1_PART2_IMPLEMENTATION_APPROVED` row in `prod_activity_log` dated `>= today`. | Kim's "yes proceed with Q1 Part 2 implementation" captured. Blanket prior autonomous-mode authorization is NOT sufficient — this is a NEW change touching `~/.claude/settings.json` and a first-of-its-kind subagent-spawn surface, requiring fresh consent. | Write `HALTED_AWAITING_AUTHORIZATION` row citing this gate; write halt-report; surface to Kim with explicit prompt: "Q1 Part 2 implementation requires fresh approval; was the autonomous-mode session intended to include Q1 Part 2 install?" |
| 5 | Are spec §13 pre-implementation gates 1-7 explicitly approved? | Spec §13 itself OR `prod_locked_decisions` notes citing the gates approved date OR a `PRE_IMPLEMENTATION_GATES_APPROVED_Q1_PART2` row in `prod_activity_log` | All 7 gates have explicit Kim-approved evidence (chat quote OR LD note OR activity-log row). Gate #6 of spec §13 (CI/CD greenfield-lock cross-check) MUST be confirmed: Q1 Part 2 does NOT touch main RN app CI/CD. | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface |

If ANY gate fails:
1. Do NOT execute Phase A.
2. Write the `HALTED_AWAITING_AUTHORIZATION` row to `prod_activity_log` with `notes` enumerating which gates failed and citing the evidence search performed.
3. Author the halt-report doc.
4. Emit the Phase 0 Step 2 declaration: `HALT gate scan for HANDOFF_Q1_PART2_IMPLEMENTATION_20260508.md: 5 gate(s) detected, <met> met, <not_met> not met. HALTED.` (per DS-26 §6.1 declaration-format tightening).
5. Surface to Kim and stop.

---

## §5 Sequence

### Phase A — Spawn-mechanism validation in isolation (per spec §11 Phase A)

**Deliverable:** standalone smoke script `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/q1_part2_spawn_smoke.py` (NEW) that:
1. Calls `claude -p "<minimal-test-prompt>" --output-format json` from a Python parent process via `subprocess.run(...)`.
2. Captures stdout, parses as JSON, asserts the response shape contains the fields the hook will rely on (`total_cost_usd`, `total_tokens` or equivalents — verified at implementation time per spec §11 Phase A gate).
3. Sets `Q1_PART2_REVIEWER_ACTIVE=1` in the spawned env and confirms the child process inherits the var (env-leakage test for the §10.1 primary recursion guard).
4. Tests `--max-turns 1` flag behavior to confirm the subagent terminates after a single response (per spec §7 prompt's `--max-turns 1` constraint).
5. Returns a verbatim PASS/FAIL line + token+cost summary that Phase D will rely on for cost-model calibration.

**Steps:**
1. `ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/"` — verify directory exists. Confirm canonical root #1.
2. `which claude && claude --version` — verify Claude Code CLI resolvable from the same shell the hook will execute under. If absent, HALT (this is a Phase A blocking precondition).
3. Author the smoke script with the 5 checks above. Do NOT integrate with the hook in this phase — Phase A is isolation only.
4. Run the smoke script with a benign prompt (e.g., `"Reply with a single word: pong"`); capture stdout JSON verbatim.
5. Multipass: re-Read the smoke script. Confirm no Directus calls, no file writes other than ephemeral stdout capture.

**Per-step verification:**
- The JSON shape contains keys for token counts and cost (or documented absence triggers a [INFERRED → CONFIRMED] note in the proof report).
- Env var inheritance verified by spawning a child that reads `os.environ.get("Q1_PART2_REVIEWER_ACTIVE")` and prints it.
- `--max-turns 1` produces exactly one response and exits.

**Audit-checklist gate at phase-end:**
- [ ] Smoke script exists at the absolute Dropbox-rooted path.
- [ ] `claude -p` JSON shape verified; cost/token field presence confirmed (or documented gap).
- [ ] Env var inheritance confirmed for primary recursion guard mechanism.
- [ ] `--max-turns 1` behavior confirmed.
- [ ] Per Rule 24 confidence tags throughout the smoke script's inline comments.

### Phase B — Hook script scaffolding (per spec §11 Phase B)

**Deliverable:** `~/.claude/hooks/stop_conditional_opus_reviewer.py` (NEW). Implements L0-L5 trigger logic from spec §3.2 in dry-run mode (no actual `claude -p` spawn yet — emits `[Q1-PART2] would spawn (dry-run)` stderr line when all gates pass).

**Steps:**
1. `ls -la ~/.claude/hooks/` — verify directory exists. (Note: `~/.claude/hooks/` is global Claude config — outside-canonical-but-allowed per HANDOFF_TEMPLATE_v2 exception list.)
2. Author the hook script implementing per spec §3.2:
   - L0: `Q1_PART2_REVIEWER_ACTIVE` env-var sentinel check (exit 0 if set).
   - L1: session-cap counter check (read `~/.claude/state/q1_part2_spawns_<session_id>.txt`; exit 0 if >= 7; if `MN_Q1_PART2_NO_CAP=1` is set, skip this check and emit override-acknowledged stderr line).
   - L2: last-turn tool_use parse — read `~/.claude/projects/<project>/<session_id>.jsonl` bottom-up (mirror Part 1's read pattern per spec §2 lines 54-58); confirm at least one Write or Edit tool_use block; exit 0 if absent.
   - L3: `file_path` matching against the §6.1 `INFRASTRUCTURE_PATH_PATTERNS` constant (encoded verbatim from spec §6.1 lines 207-228); use `fnmatch.fnmatch` with `**` recursive semantics; exit 0 if no match.
   - L4: assistant-text regex match using the canonical Step 2.5b pattern (mirror Part 1's regex per spec §2; suppress on `[CONFIRMED|INFERRED|GUESSED` tag presence in same turn — same as Part 1); exit 0 if no match.
   - L5: assistant-text contains the recursion-guard sentinel `<!-- Q1_PART2_REVIEWER_OUTPUT_SENTINEL_DO_NOT_TRIGGER -->` (per spec §10.2); exit 0 if present.
3. In Phase B, replace the actual spawn with: `print("[Q1-PART2] would spawn (dry-run)", file=sys.stderr)` and exit 0. Phase D wires the real spawn.
4. Encode the `INFRASTRUCTURE_PATH_PATTERNS` constant verbatim from spec §6.1 lines 207-228 — copy the path list AS-IS, do not paraphrase or compress.
5. Encode the negative-test path-list (spec §6.3) as documentation comments inside the script for future reviewers.
6. Multipass: re-Read the script. Confirm L0-L5 ordering matches spec §3.2 table. Confirm the path list is byte-identical to spec §6.1.

**Per-step verification:**
- Each of L0-L5 has its own unit-testable function.
- Script never imports or calls Directus client (Phase B is read-only Layer 1).
- All `os.path` operations use absolute paths or `pathlib.Path.home() / ".claude/..."` (DS-27 v2 dual-canonical compliant for global Claude config).

**Audit-checklist gate at phase-end:**
- [ ] Hook script exists at `~/.claude/hooks/stop_conditional_opus_reviewer.py`.
- [ ] L0-L5 trigger logic implemented per spec §3.2 verbatim.
- [ ] `INFRASTRUCTURE_PATH_PATTERNS` constant byte-identical to spec §6.1.
- [ ] Dry-run mode emits "would spawn" line; no actual `claude -p` invocation.
- [ ] Synthetic fixture: hand-craft a transcript matching spec §6.4 fixture F1 (hook edit + state claim) → assert hook emits "would spawn" line.
- [ ] Synthetic fixture: hand-craft a transcript matching spec §6.4 fixture F5 (storyboard edit) → assert hook exits 0 silently.

### Phase C — Settings.json wiring (per spec §11 Phase C)

**Deliverable:** `~/.claude/settings.json` Stop array contains a SECOND entry pointing to `stop_conditional_opus_reviewer.py`. Backup file `~/.claude/settings.json.backup_q1_part2_<ISO>` produced before edit. Diff vs backup shows ONLY Stop array additive change; no other keys touched.

**Steps:**
1. `cp ~/.claude/settings.json ~/.claude/settings.json.backup_q1_part2_$(date -u +%Y%m%dT%H%M%SZ)` — produce backup. Verify backup file size matches original.
2. Read `~/.claude/settings.json`. Anchor: `"Stop"` key under `"hooks"`. Capture current line range and current array contents verbatim.
3. Edit: append a NEW entry to the Stop array. The new entry mirrors the structure of Part 1's entry (same `matcher` semantics; same shell-`command` pattern). The new `command` invokes `stop_conditional_opus_reviewer.py` (use the same path style as Part 1 — typically a `python3 ~/.claude/hooks/<script>.py`-style invocation).
4. Validate JSON: `python3 -c "import json,pathlib; json.loads(pathlib.Path.home().joinpath('.claude/settings.json').read_text())"` — must parse without error.
5. Diff vs backup: `diff ~/.claude/settings.json.backup_q1_part2_<ISO> ~/.claude/settings.json` — output MUST show only Stop-array additive change.
6. Multipass: re-Read settings.json end-to-end. Confirm all other keys unchanged (PreToolUse, PostToolUse, SessionStart, PreCompact arrays all bytewise-identical to backup).

**Per-step verification:**
- JSON parses cleanly post-edit.
- Stop array length increased by exactly 1.
- Part 1's entry remains FIRST in Stop array (per spec §3.1: Part 1 runs before Part 2).
- Order matters per Cursor v2 review Task F — confirm Part 1 emits its banner BEFORE Part 2 emits its banner.

**Audit-checklist gate at phase-end:**
- [ ] Backup file exists with `.backup_q1_part2_<ISO>` suffix.
- [ ] Diff shows additive-only Stop change.
- [ ] JSON validates.
- [ ] Part 1 entry still first; Part 2 entry second.
- [ ] No collateral edits to other hook arrays.

### Phase D — Prompt template + spawn invocation (per spec §11 Phase D)

**Deliverable:** Phase B's dry-run mode replaced with actual `claude -p` spawn invocation, using the spec §7 prompt template. Captures stdout JSON; renders banner per spec §9; appends to session log file. End-to-end test: synthetic infrastructure edit + state claim → assert reviewer spawn produced JSON verdict + banner emitted.

**Steps:**
1. Encode the §7 prompt template verbatim into the hook script as a Python multi-line string constant `REVIEWER_PROMPT_TEMPLATE`. The template includes the `<!-- Q1_PART2_REVIEWER_OUTPUT_SENTINEL_DO_NOT_TRIGGER -->` first line (per spec §10.2 + §7 lines 266) AND the strict-JSON output schema (per spec §7 lines 296-308).
2. Substitute `<<<ASSISTANT_TEXT>>>` and `<<<FILE_PATHS>>>` placeholders with the parsed turn data. Use safe string substitution (NOT `format()` or f-strings — assistant text may contain `{` characters).
3. Spawn via `subprocess.run([...], env={"Q1_PART2_REVIEWER_ACTIVE": "1", **os.environ}, ...)` with the constructed prompt. Capture stdout. Apply 90-second timeout (per spec §16.3 fixture F16).
4. Parse stdout as JSON. On parse failure, fall back to `[Q1-PART2] reviewer returned malformed JSON; raw output: <first 500 chars>` stderr line and exit 0 (per spec §16.3 fixture F15).
5. Render banner per spec §9 template (verbatim). Use ANSI escape codes by default; plaintext fallback when `NO_COLOR` env set or stderr is not a TTY (mirrors Part 1).
6. Append a JSON line to `~/.claude/state/q1_part2_session_<session_id>.log` with the full reviewer JSON response (per spec §3.4 + §9 secondary log).
7. End-to-end test: hand-craft a transcript fixture (spec §16.3 fixture F12 — PASS verdict on a small file); run the hook against it; verify banner emitted with PASS verdict + claims listed + spawn cost shown.

**Per-step verification:**
- Prompt template byte-identical to spec §7.
- Sentinel is the FIRST line of the prompt content (recursion guard L5 self-protection).
- Spawn timeout = 90 sec.
- Malformed JSON fallback works.
- Banner format matches spec §9 verbatim.

**Audit-checklist gate at phase-end:**
- [ ] Real spawn replaces dry-run mode.
- [ ] §7 template encoded verbatim.
- [ ] End-to-end test produces PASS verdict + banner on synthetic fixture F12.
- [ ] Malformed-JSON fallback fires correctly on synthetic F15.
- [ ] Timeout fallback fires correctly on synthetic F16.
- [ ] Session log file appended with verbatim reviewer JSON.

### Phase E — Cost monitor + session log (per spec §11 Phase E + §3.3 + §8)

**Deliverable:** Counter file `~/.claude/state/q1_part2_spawns_<session_id>.txt` (single integer line); soft alert at 5/7; hard cap at 7; ceiling-reached stderr line on 8th trigger; per-spawn cost line appended to session log per spec §8.3.

**Steps:**
1. Implement counter read/write with atomic-increment pattern (file lock or write-then-rename). Address Cursor v2 review Task G race-condition concern: if two concurrent sessions in same project somehow share counter state, atomic-rename prevents lost increments. (Spec uses session_id in filename, so concurrent sessions get separate counters by default; the atomic-rename is belt-and-suspenders.)
2. Implement soft alert: when counter increments to 5, emit `[Q1-PART2] cost notice — 5 of 7 reviewer spawns used this session` to stderr (per spec §3.3 line 105).
3. Implement hard cap: when counter would increment to 8, emit `[Q1-PART2] session cap reached (7/7); skipping further reviewer spawns` and exit 0 without spawning (per spec §3.3 line 104).
4. Implement override: if `MN_Q1_PART2_NO_CAP=1` is set, skip cap check; emit `[Q1-PART2] cap bypass acknowledged via MN_Q1_PART2_NO_CAP=1` to stderr; record audit-row requirement (the actual `Q1_PART2_CAP_BYPASSED` row write is enforced at Phase 7 closeout, not in the hook itself — per spec §8.4).
5. Append per-spawn line to session log: timestamp, file paths matched, verdict, tokens used, USD cost (parsed from reviewer JSON `total_cost_usd` field if present; else "estimate ~$X (see spec §8)" fallback per spec §3.4 line 116).
6. Test fixtures: §16.5 cost-model fixtures F22 (typical cost), F23 (worst-case cost), F24 (session ceiling math — run F1 7 times, assert 5/7 alert, assert 7/7 ceiling-reached on 8th).

**Per-step verification:**
- Counter file path uses session_id (separates concurrent-session counters).
- Atomic increment pattern prevents lost writes.
- 5/7 alert + 7/7 cap fire at correct boundaries.
- Override env var skips cap.

**Audit-checklist gate at phase-end:**
- [ ] Counter file at `~/.claude/state/q1_part2_spawns_<session_id>.txt` increments correctly.
- [ ] Soft alert at 5; hard cap at 7; 8th call no-op.
- [ ] Override env var bypass works + emits acknowledgment.
- [ ] Session log file appended per spawn with verbatim cost data.
- [ ] §16.5 fixtures F22/F23/F24 all pass.

### Phase F — Recursion guard validation (per spec §11 Phase F + §10 + §16.4 fixtures F18-F21)

**Deliverable:** All 4 recursion guards (env var sentinel L0; output sentinel L5; SDK invocation flag L0+; ps-chain depth limit) tested against synthetic recursion attempts. Verify each guard alone catches recursion; verify joint failure requires all 4 to bypass.

**Steps:**
1. Implement guard 4 (ps-chain depth limit) per spec §10.4 verbatim:
   ```python
   import subprocess, os
   def _is_inside_headless_claude(max_depth=5):
       pid = os.getpid()
       for _ in range(max_depth):
           try:
               ppid = int(subprocess.check_output(["ps", "-p", str(pid), "-o", "ppid="]).strip())
               if ppid <= 1: return False
               cmd = subprocess.check_output(["ps", "-p", str(ppid), "-o", "command="]).decode()
               if "claude -p" in cmd or "claude --print" in cmd: return True
               pid = ppid
           except Exception:
               return False
       return False
   ```
   This is canonical from spec §10.4 lines 451-464; encode verbatim.
2. Confirm guard 3 (SDK `--no-hooks` flag): research the actual flag at implementation time; if it exists, add it to the spawn command. If it does not exist, the guard reduces to env+sentinel+ps (still 3 layers — acceptable per spec §10.3 lines 444-445 [INFERRED]).
3. Synthetic fixture F18 — guard 1 only: set `Q1_PART2_REVIEWER_ACTIVE=1`; clear sentinel from text; clear ps chain. Assert NO SPAWN.
4. Synthetic fixture F19 — guard 2 only: plant sentinel in assistant text; clear env; clear ps chain. Assert NO SPAWN.
5. Synthetic fixture F20 — guard 4 only: run inside a `claude -p` parent (mock via fake ps output); clear env; clear sentinel. Assert NO SPAWN.
6. Synthetic fixture F21 — all guards bypassed: clear all 3 mechanical guards + force ps chain to look clean. Assert SPAWN. (This is the failure mode spec §14 documents as residual risk; documenting the test confirms the design's joint-failure assumption is reproducible.)

**Per-step verification:**
- Each of F18, F19, F20 individually catches recursion.
- F21 confirms ALL 4 must fail simultaneously for recursion to occur (per spec §10 line 467 + Cursor v2 review Task A numeric trigger).

**Audit-checklist gate at phase-end:**
- [ ] Guard 4 ps-chain implementation byte-identical to spec §10.4.
- [ ] All 4 guards individually validated against synthetic fixtures.
- [ ] Joint-failure scenario F21 reproducible (confirms residual-risk assumption matches design).
- [ ] Per Cursor v2 review Task A: joint-failure probability documented in proof report; if your evidenced estimate exceeds 1-in-10,000 spawns under realistic load OR ≥3-of-4-fail scenario constructible during testing, HALT and surface — additional guards required. (Per spec residual-risk acceptance threshold is 1-in-10k.)

### Phase G — Kill-switch + LD authoring (per spec §11 Phase G + §15)

**Deliverable:** documented removal procedure (surgical removal + backup restore + one-line disable from spec §15); LD `Q1_PART2_INSTALLED_V1` POST'd to `prod_locked_decisions`; `prod_activity_log` row `Q1_PART2_CONDITIONAL_REVIEWER_LIVE` POST'd. Kill-switch env override `MN_Q1_PART2_NO_CAP=1` documented.

**Steps:**
1. Author a removal-procedure snippet block in the proof report (per spec §15) — three options:
   - Surgical removal (preserves Part 1): `python3 -c "import json, pathlib; p = pathlib.Path.home() / '.claude/settings.json'; d = json.loads(p.read_text()); d['hooks']['Stop'] = [d['hooks']['Stop'][0]]; p.write_text(json.dumps(d, indent=2))"`
   - Backup restore: `cp ~/.claude/settings.json.backup_q1_part2_<ISO> ~/.claude/settings.json`
   - One-line disable: `mv ~/.claude/hooks/stop_conditional_opus_reviewer.py ~/.claude/hooks/stop_conditional_opus_reviewer.py.disabled`
2. POST `prod_activity_log` row with `action=Q1_PART2_CONDITIONAL_REVIEWER_LIVE` and `notes` containing: spec path, handoff path (this file), Phase F test-pass summary, settings.json backup path, recursion-guard joint-failure probability documented from Phase F, cost-model calibration from Phase A.
3. POST `prod_locked_decisions` row `Q1_PART2_INSTALLED_V1` with `decision_text` summarizing the implementation + linking the spec + linking this handoff. Severity: HARD (governance-class mechanical layer; first subagent-spawn surface in MindfulNest hooks). task_category: governance OR canonical existing per Directus enum schema (verify via `/fields` per memory `feedback_directus_schema_canonical.md` — read live schema before write per Rule 35 task_description gotcha from `feedback_directus_schema_canonical.md` and S5.5 memory tail).
4. Read-back per Rule 35: re-fetch BOTH rows; confirm body matches the POST request; capture row IDs.
5. Per-Rule-24 confidence tags throughout the POST bodies (CONFIRMED for items verified at implementation; INFERRED for items derived from spec without independent verification; GUESSED is FORBIDDEN at this gate — every claim must be at least INFERRED).

**Per-step verification:**
- Removal procedure verified by running surgical-removal in a sandbox + restoring (ephemeral test, do NOT actually remove the live install).
- Activity-log row + LD row both written and read-back-verified.
- Confidence tags present throughout.

**Audit-checklist gate at phase-end:**
- [ ] Removal procedure documented + sandbox-tested (without affecting live install).
- [ ] LD `Q1_PART2_INSTALLED_V1` posted; row id captured; read-back confirms body.
- [ ] Activity-log row posted; row id captured; read-back confirms body.
- [ ] Kill-switch env var `MN_Q1_PART2_NO_CAP=1` documented in proof report.
- [ ] Per Rule 24: every factual claim in the report tagged.

---

## §6 Hard rules

- **Per Rule 35 (read-back-after-write):** every Directus PATCH/POST MUST be followed by a re-fetch of the row, with the response body verbatim captured in the proof report. Applies to: `prod_activity_log` POSTs (Phase G), `prod_locked_decisions` POSTs (Phase G). Per memory tail `Session 2026-05-08 03:02 UTC` and `feedback_directus_schema_canonical.md`, also verify `task_description` field IS populated where REQUIRED by current schema (silent migration risk).
- **Multipass per file edit:** every Edit MUST be followed by a re-Read of the same file. Confirm intended change AND no collateral edits. Applies to: `~/.claude/settings.json` (Phase C), `~/.claude/hooks/stop_conditional_opus_reviewer.py` (Phases B + D + E + F), all script edits.
- **Rule 24 confidence tags:** every factual claim in the proof report tagged CONFIRMED / INFERRED / GUESSED. CONFIRMED requires file:line citation. GUESSED is forbidden at gate-pass time — every claim must be at minimum INFERRED.
- **DS-19 Standing Escape Hatches** active throughout — fire on any internal symptom (something feels off, ambiguous, or contradictory). The first-of-its-kind subagent-spawn surface is unprecedented in MindfulNest hooks; treat any unexpected behavior at Phase A or D as DS-19 trigger, not "push through."
- **DS-26 Gate-Check Discipline:** the §4 HALT gates above are explicit. If ANY fails mid-execution (e.g., Cursor verdict found inconsistent with what was claimed; Q1 Part 1 found missing partway through), STOP and surface. Autonomous mode does NOT bypass.
- **DS-13 Layer 6 smoke:** Phases B/D/E/F's synthetic fixtures (§16 from spec) ARE the Layer 6 smoke (input variation → output variation, NOT just compile/parse). Per memory `feedback_six_layer_feature_verification.md`: UI shell + 200 response is NOT done; subagent spawn + JSON parse + banner render + log-file append IS the six-layer test.
- **DS-27 absolute-path discipline (refactored 2026-05-08 v2 dual-canonical):** All filesystem-touching commands MUST use absolute paths anchored to one of the two canonical roots: (1) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (primary — Mindfulnest project — used for `Production/scripts/q1_part2_spawn_smoke.py` Phase A) OR (2) `/Users/kimberlysmith/Projects/` (secondary — tooling repos / RN app — NOT touched by this implementation). `~/.claude/` is global Claude config — explicitly allowed for `~/.claude/hooks/`, `~/.claude/settings.json`, `~/.claude/state/`, `~/.claude/skills/` per HANDOFF_TEMPLATE_v2 §"Operational consequence" exception list. Do NOT operate inside `.claude/worktrees/` subdirectories under either canonical root. Verify paths with `ls -la <absolute-path>` before edits. Paths outside both canonical roots (e.g., `/tmp`, `~/Desktop/`) require explicit Kim authorization.
- **Companion path discipline (HANDOFF_TEMPLATE_v2 §0.3):** Every reference in this handoff uses absolute paths with canonical-root tags. Probe `ls -la` for each at authoring time. Compliant: spec, Cursor handoff, template, sibling impl handoff all Dropbox-rooted (canonical root #1); `~/.claude/` paths tagged as global-config exception.
- **Anchored citation discipline (HANDOFF_TEMPLATE_v2):** every Read pre-flight evidence requirement uses anchored section/header + snippet match, not absolute line number alone. See §3.1 for the citation table.
- **Concise→full escalation:** N/A for implementation handoffs (no concise verdict mode). Documented N/A explicitly per template requirement.
- **Numeric AMEND_V2 thresholds:** N/A for implementation handoffs (no AUTHORIZE/AMEND verdict semantics). Documented N/A explicitly per template requirement. EXCEPTION: Cursor v2 review Task A's joint-failure probability threshold (1-in-10k) and Task B's cost thresholds ($10/session worst, $3/session typical) carry forward into Phase F + Phase G test-pass criteria — if Phase F testing reproduces a ≥3-of-4-guard-failure scenario OR Phase A cost calibration shows worst-case > $10/session OR typical > $3/session, HALT and surface (the spec is wrong; design needs revision).
- **Cost ceiling explicit:** 7 spawns/session HARD cap per spec §3.3 / §8.2. Soft alert at 5/7 (stderr `[Q1-PART2] cost notice — 5 of 7 reviewer spawns used this session`). Hard cap at 7/7 (stderr `[Q1-PART2] session cap reached (7/7); skipping further reviewer spawns`). Override `MN_Q1_PART2_NO_CAP=1` mirrors DS-20/21/22 override pattern + audit-row requirement.
- **4-layer recursion guard documented (per spec §10):**
  - L0.1 Env-var sentinel (`Q1_PART2_REVIEWER_ACTIVE=1`) — primary, hard guard.
  - L5 Output sentinel (`<!-- Q1_PART2_REVIEWER_OUTPUT_SENTINEL_DO_NOT_TRIGGER -->`) — defense-in-depth.
  - L0+ SDK invocation flag (`--no-hooks` if exists; [INFERRED] at spec time, verified at Phase D implementation).
  - L0++ Process-tree depth limit via `ps` (max_depth=5) — final backstop.
  - All 4 must fail simultaneously for recursion (spec §10 line 467); design accepts joint-failure as residual risk per §14 / fixture F21.
- **DS-22 SAVE-time scan:** complementary mechanism per spec §2 lines 60-61. Q1 Part 2 does NOT modify DS-22 (Step 2.5b in mn-context SKILL.md); Part 2 layers AFTER turn-end while DS-22 layers at SAVE-time. No conflict.
- **DS-23 sweeps for security-adjacent files:** N/A — Q1 Part 2 does NOT touch `production_server.py` or other security-adjacent files (per spec §0.1 and §13 gate 6). Confirmed by §6.1 path allow-list.
- **DS-3 fixture pinning:** Phase B/D/E/F fixtures MUST be pinned (not regenerated each run); fixtures live under `Production/tests/fixtures/q1_part2/` (Dropbox-rooted, canonical root #1) and are version-controlled.
- **Greenfield CI/CD lock cross-check:** per memory `project_main_app_cicd_greenfield_lock.md`, this implementation does NOT touch `MindfulNest/.github/workflows/`, `mindfulnest-ios`, or any App Store / TestFlight / EAS / Expo / Maestro surface. Confirmed by spec §13 gate 6.

---

## §7 Final proof report structure

**Path:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/Q1_PART2_IMPLEMENTATION_REPORT_<YYYYMMDD>.md`

The report MUST contain, in order:

1. **HALT gate scan results** — per-gate state (MET / NOT MET / N/A) for §4 gates 1-5 with evidence cited. Phase 0 Step 2 declaration in spec form: `HALT gate scan for HANDOFF_Q1_PART2_IMPLEMENTATION_20260508.md: 5 gate(s) detected, <M> met, <K> not met.` (per DS-26 §6.1 declaration-format).
2. **Per-phase diff (verbatim)** — Phases A, B, C, D, E, F, G code/data changes. Phase C MUST include the full diff of `~/.claude/settings.json` vs the backup file.
3. **Per-phase audit-checklist results** — gate state at phase-end (PASS / NEEDS_FIX / SKIPPED) per §5 gates.
4. **Phase A cost calibration output** — verbatim JSON output from the Phase A smoke spawn; token counts; USD cost. Confirm or correct spec §8.1 estimates ($0.18 typical / $0.86 worst-case). If actual exceeds spec estimate by >50%, HALT per Cursor v2 review Task B numeric threshold.
5. **Phase F recursion-guard test results** — verbatim output from F18, F19, F20, F21 fixtures. Joint-failure probability estimate per Cursor v2 review Task A. If estimate > 1-in-10,000 OR ≥3-of-4-fail scenario reproducible, HALT.
6. **Directus writes** — full POST/PATCH bodies + read-back proofs:
   - `prod_activity_log` POST `Q1_PART2_CONDITIONAL_REVIEWER_LIVE` with row id captured (Phase G).
   - `prod_locked_decisions` POST `Q1_PART2_INSTALLED_V1` with row id captured (Phase G).
7. **Confidence tags per Rule 24** — every claim tagged CONFIRMED / INFERRED / GUESSED. CONFIRMED requires file:line citation. GUESSED forbidden at gate-pass.
8. **Self-classification** — ARCHITECTURAL.
9. **Limitations** — what wasn't covered:
   - v2 amendments (FAIL-verdict prod_blockers row, Bash command-string regex for Directus writes, settings.json variant trigger) explicitly out of scope per spec §12.
   - Q1 Part 3 (structured-output schema candidate) deferred per spec §0.1.
   - 30-day cost-model recalibration deferred per spec §12 #4.
   - First-spawn cost variance untested at scale (Phase A is a single-shot calibration).
10. **Cross-skill drift** — does this require parallel updates to:
    - mn-context: NO (Step 2.5b unchanged; Q1 Part 2 layers AFTER turn-end, not at SAVE-time).
    - zero-error-qa: NO (DS-22 unchanged; Q1 Part 2 is a hook-side mechanism).
    - tech-spec: NO.
    - dashboard-gate: NO.
    - HANDOFF_TEMPLATE_v2: NO (template ready as-is).
    - settings.json: YES (Phase C wires the new hook).

---

## §8 Rollback per phase

| Phase | Rollback procedure | Cost |
|-------|--------------------|------|
| A | Remove `Production/scripts/q1_part2_spawn_smoke.py`. Smoke script is isolated; no dependencies. | Low — single file delete. |
| B | Remove `~/.claude/hooks/stop_conditional_opus_reviewer.py`. Hook script not yet wired in settings.json (Phase C). | Low. |
| C | Restore `~/.claude/settings.json` from `~/.claude/settings.json.backup_q1_part2_<ISO>`. Stop array reverts to Part-1-only. Q1 Part 1 unaffected. | Low — single file restore. |
| D | Revert hook script to Phase B dry-run mode (replace spawn block with `print("[Q1-PART2] would spawn (dry-run)")`). Settings.json wiring stays; hook continues firing but no actual subagent spawn. | Low. |
| E | Revert counter file logic. Without cap, hook spawns unconditionally on every L0-L5 pass — re-introduces cost-overrun risk. Revert is the explicit emergency stop. | Low. |
| F | Phase F is test-only; rollback = remove fixture files under `Production/tests/fixtures/q1_part2/`. | Low. |
| G | PATCH `prod_locked_decisions` row `Q1_PART2_INSTALLED_V1` to `status=superseded` with `notes` documenting rollback rationale. POST follow-up `prod_activity_log` row `Q1_PART2_ROLLED_BACK` with rationale. | Medium — Directus operations + audit trail. |

**Full-spec rollback** (per spec §15 surgical removal): preserves Q1 Part 1 + other hooks intact. Three options documented:
1. Surgical removal: `python3 -c "import json, pathlib; p = pathlib.Path.home() / '.claude/settings.json'; d = json.loads(p.read_text()); d['hooks']['Stop'] = [d['hooks']['Stop'][0]]; p.write_text(json.dumps(d, indent=2))"`
2. Backup restore: `cp ~/.claude/settings.json.backup_q1_part2_<ISO> ~/.claude/settings.json`
3. One-line disable: `mv ~/.claude/hooks/stop_conditional_opus_reviewer.py ~/.claude/hooks/stop_conditional_opus_reviewer.py.disabled`

Total cost ~5-10 minutes. Q1 Part 1 (LD 579) and DS-22 SAVE-time scan are independent; rollback does NOT affect them.

**Per spec §14 + §15:** if Phase D produces unmanageable false-positive volume OR cost-overrun beyond spec §8.2 worst-case ($6.02/session), rollback Phases C-E. Phases A + B test-script + dry-run can stay (they are low-risk artifacts). Phase G follow-up writes `Q1_PART2_ROLLED_BACK` row. v2 spec amendment becomes the next attempt with revised trigger criteria or cost model.

---

## §9 Reference index

- **Spec:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md` — Dropbox-rooted (canonical root #1)
- **Cursor review handoff (v2):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v2.md` — Dropbox-rooted (canonical root #1)
- **Authoring template:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — Dropbox-rooted (canonical root #1)
- **Sibling impl handoff (DS-26):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_DS26_IMPLEMENTATION_20260508.md` — Dropbox-rooted (canonical root #1) — pattern reference
- **Q1 Part 1 spec (the precedent):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/Q1_PART1_STOP_HOOK_SPEC_v1.md` — Dropbox-rooted (canonical root #1)
- **Q1 Part 1 hook implementation:** `~/.claude/hooks/stop_state_claim_scan.py` — global Claude config (outside-canonical exception)
- **Q1 Part 1 LD:** `Q1_PART1_STOP_HOOK_INSTALLED_V1` (LD 579) — Directus `prod_locked_decisions`
- **DS-22 (state-claim mechanical gate):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md` (anchor: `## DS-22`) — Dropbox-rooted (canonical root #1)
- **Step 2.5b (canonical regex):** `~/.claude/skills/mn-context/SKILL.md` (anchor: `## Step 2.5b`) — global Claude config (outside-canonical exception)
- **Settings.json (current Stop wiring):** `~/.claude/settings.json` (anchor: `"Stop"` key) — global Claude config (outside-canonical exception)
- **Existing hook patterns (precedents for hook script style):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/preflight_hook.py`, `precompact_save_trigger.py`, `session_event_logger.py` — all Dropbox-rooted (canonical root #1)
- **Override pattern reference (DS-20/21/22):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md` — Dropbox-rooted (canonical root #1)
- **Authority LDs:** `GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1` (id=578) for HALT discipline; `WORKTREE_CONFUSION_PREVENTION_V1` for DS-27 dual-canonical; `Q1_PART1_STOP_HOOK_INSTALLED_V1` (LD 579) for Part 1 prerequisite; `Q1_PART2_INSTALLED_V1` (TO BE CREATED at Phase G) for this implementation.
- **Memory tail:** `Session 2026-05-08 03:02 UTC — V59 Storyboard Foundation Sprint` (DS-26 + Stream B+F lessons; gap-fix terminal session ongoing in parallel)
- **Memory rules cited:** `project_main_app_cicd_greenfield_lock.md` (greenfield lock — Q1 Part 2 confirmed NOT touching CI/CD); `feedback_directus_schema_canonical.md` (live-schema verification before Directus writes); `feedback_six_layer_feature_verification.md` (Layer 6 smoke discipline)
- **Cross-skill drift surfaces:** none required (mn-context unchanged; zero-error-qa unchanged; tech-spec unchanged; dashboard-gate unchanged)
- **CLAUDE.md rules cited:** Rule 19 (no path open for error), Rule 24 (confidence tags), Rule 35 (read-back-after-write)

---

**End of handoff.**
