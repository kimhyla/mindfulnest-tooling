# Q1 — Part 2: Conditional Opus Reviewer Subagent — Tech Spec v1

**Status:** Spec authored 2026-05-08. DESIGN ONLY — no code, no Directus writes, no edits.
**Authority:** Kim's Q1 directive (state-claim verification stack — Part 2 of 3).
**Pairs with:** Q1 Part 1 (`Production/docs/Q1_PART1_STOP_HOOK_SPEC_v1.md`, LD 579 `Q1_PART1_STOP_HOOK_INSTALLED_V1`).
**Authoring method:** tech-spec dual-Opus pattern (advocate vs counter, internalized; resolution per-decision).

---

## §0. Operating Mode

- DESIGN ONLY. This document specifies the Q1 Part 2 conditional Opus reviewer subagent. No production scripts, no settings.json edits, no hook installs, no Directus rows are written by the act of authoring this spec.
- Multipass authoring: pass 1 drafts §1–§17; pass 2 verifies cross-references and counts; pass 3 stress-tests cost ceiling and recursion guard.
- Per Rule 24: state claims about Q1 Part 1 internals are tagged `[CONFIRMED from <file>:<line>]` where verified inline; un-verified architectural assertions are tagged `[INFERRED]` or `[GUESSED]`.
- HALT triggers: any unresolved cost-model gap; any recursion-guard failure mode I cannot mechanically prevent; any open decision Kim has not signaled on.
- Implementation requires a separate authorized session post-Cursor cross-review (per the v2-hardened handoff).

## §0.1. Scope (vs Q1 Part 1's scope; explicit boundary)

**Q1 Part 1** (already shipped; LD 579) catches state-claim regex patterns at **turn-end** (Stop hook), warn-only, on the assistant's most recent text. It is **silent** when:
- the same turn contains tool_use blocks (Read/Bash/Grep/Glob), OR
- the claim already carries a Rule 24 tag (`[CONFIRMED…]` / `[INFERRED…]` / `[GUESSED]`).

**Q1 Part 2** (this spec) covers exactly the gap Part 1 leaves open: turns that **DID** invoke tool_use AND still contain unverified state claims about infrastructure changes. These are the highest-risk turns — the assistant did real work, then narrated it; the narration may overstate, mis-attribute, or fabricate wiring details that Part 1's tool_use suppression rule lets pass.

**In scope (Part 2):**
- Turns whose tool_use block list includes a write/edit operation against a defined "infrastructure" file path (see §6 trigger criteria).
- After the turn has ended, an Opus reviewer subagent reads the assistant's last message text and the diff/content of the files written, and emits an inline-banner verdict.
- Per-session cost ceiling and per-trigger cost estimate.
- Recursion guard preventing the reviewer from triggering itself.

**Out of scope (Part 2):**
- Turns with no tool_use (already handled by Part 1).
- Turns with tool_use against non-infrastructure files (e.g., editing a storyboard HTML, an arc skeleton, a Phase B audio script — Part 1 stays silent here, but the risk-class for false state claims is much lower).
- Semantic fact-checking of non-state content (e.g., "this is elegant code" — both Part 1 and Part 2 ignore).
- User-message claims (out of scope across all three Q1 parts).
- Tool_result block claims (out of scope across all three Q1 parts).
- Q1 Part 3 (TBD; placeholder for a future layer not specified here).

**Boundary:** if the trigger criteria in §6 fire, Part 2 fires; otherwise Part 1's silence remains the only safety net for that turn. Part 1 is the broad sieve; Part 2 is the targeted deep scan on the highest-risk turns only.

## §1. Background — false state claims; Part 1's tool_use blind spot; cost concerns

**False state claim pattern:** the assistant does work via tool_use (writes a hook, edits a skill, modifies an audit script), then narrates the result with confident wiring language ("Phase 0.7 reads LD 565 and surfaces 'closure approaching'", "the Stop hook now mirrors Step 2.5b") that is **not actually true** — the file write may have produced a slightly different mechanism than the narration claims. This is the LD 565+567 failure pattern called out in DS-22.

**Why Part 1's tool_use suppression isn't enough:** Part 1 was designed warn-only at turn-end. To minimize false positives on legitimate verification turns, it suppresses the warning if **any** tool_use block appears in the turn. The assumption was: "if I called tool_use, I verified." That assumption fails when the tool_use was a *write*, not a *read*. Writing a file proves you wrote *something*; it does not prove that what you wrote matches the narration.

**Why cost is the dominant counter-pressure:** an Opus reviewer subagent is itself an expensive Claude generation. Naïvely firing on every infrastructure turn produces 20–50 spawns per heavy work session. At advocate-side estimated cost (~$0.50–$2 per spawn), that's $10–$100 in agent overhead per session, plus ~30–60 sec latency per spawn. So Part 2 cannot be "fire on every infrastructure turn"; it has to be tightly scoped, hard-capped, and gracefully degradable.

**The architectural tension:** broad scope catches more false claims but blows the cost budget; narrow scope keeps cost bounded but lets some false claims slip. The §3 design resolves this via a layered trigger model + per-session ceiling + warn-only failure mode (mirror Part 1's "ship the message anyway" decision).

## §2. Existing landscape — Part 1 implementation, hook surfaces, DS-22 SAVE-time scan

**Part 1 implementation** (`~/.claude/hooks/stop_state_claim_scan.py`, `~/.claude/settings.json` Stop hook):
- Reads `~/.claude/projects/<project>/<session_id>.jsonl` bottom-up to extract the last assistant turn.
- Runs the canonical Step 2.5b regex (verbatim from `mn-context/SKILL.md` line 296).
- Suppresses if `[CONFIRMED|INFERRED|GUESSED` in same turn OR if any tool_use block in same turn.
- Emits ANSI banner to stderr; exits 0 always; never blocks. [CONFIRMED from `~/.claude/hooks/stop_state_claim_scan.py:121–148` read 2026-05-08]

**DS-22 SAVE-time scan** (`mn-context/SKILL.md` Step 2.5b):
- Same regex pattern; runs at SAVE time (Phase 7 closeout), HALTs the SAVE if unverified claim found, requires explicit waiver to checkpoint.unverified_claims_waived[]. [CONFIRMED from `mn-context/SKILL.md:291–319`]

**Claude Code hook surfaces** (used by existing settings.json):
- `PreToolUse` — fires before a tool_use, can block. Used by MindfulNest's `preflight_hook.py`, `docx_confirmation_hook.py`, `deny_bash_governed_write.py`. [CONFIRMED from `~/.claude/settings.json:7–34`]
- `PostToolUse` — fires after a tool_use completes; receives `tool_name`, `tool_input`, `tool_response`. Used by `session_event_logger.py`. [CONFIRMED from `~/.claude/settings.json:35–45`]
- `SessionStart` — fires at session boot. Used for audit kickoff, CLAUDE.md mirror, lock-decision cache rebuild. [CONFIRMED from `~/.claude/settings.json:46–71`]
- `PreCompact` — fires before context compaction. Used by `precompact_save_trigger.py`. [CONFIRMED from `~/.claude/settings.json:72–80`]
- `Stop` — fires at turn end, no `tool_name` payload. Used by Q1 Part 1. [CONFIRMED from `~/.claude/settings.json:82–91`]

**Other relevant infrastructure:**
- `Production/scripts/weekly_preflight_audit.py` — running on SessionStart; cited as an "infrastructure" file in §6.
- `Production/scripts/preflight_hook.py` — PreToolUse Write|Edit gate for governed files.
- `prod_locked_decisions` Directus table — LD writes are a governed operation; LD 579 already documents Part 1.

**No existing subagent-spawn mechanism in MindfulNest hooks:** every existing hook is a single-shot Python script. The Q1 Part 2 design will introduce the first hook that spawns a separate Claude Code generation. This is a new pattern; §11 phases include validating the spawn mechanism in isolation before wiring to Stop. [INFERRED — verified by absence of subagent-spawn calls in `~/.claude/settings.json` 2026-05-08]

## §3. Proposed design — trigger criteria, file-path matching, cost ceiling, output, recursion guard

### 3.1. High-level architecture

A new hook script `~/.claude/hooks/stop_conditional_opus_reviewer.py` runs on the same `Stop` event as Q1 Part 1, but **after** Part 1 (registered second in the settings.json Stop array). It:

1. **Decides whether to fire** by inspecting the last turn's tool_use blocks against the §6 trigger criteria.
2. **If trigger fires:** spawns an Opus reviewer subagent via the Claude Code SDK headless mode (`claude -p "<prompt>" --output-format json`), passing the standardized review prompt template (§7) plus the assistant's last message text and the changed-file paths.
3. **Receives the reviewer's verdict** (PASS / WARN / FAIL with bullet-pointed findings).
4. **Renders the verdict** as an ANSI banner to stderr (mirrors Part 1's output channel).
5. **Always exits 0; never blocks** (mirrors Part 1's failure mode — the message has already shipped).

### 3.2. Trigger model (layered)

| Layer | Test | If false |
|---|---|---|
| L0 | `stop_hook_active` flag is false (not a re-entrant Stop) | exit 0, no spawn |
| L1 | session-cap counter is below ceiling (default 7 spawns/session) | emit "ceiling reached" stderr line, exit 0 |
| L2 | last turn contains ≥1 tool_use block of type Write OR Edit | exit 0, no spawn |
| L3 | tool_use's `file_path` matches an "infrastructure" path pattern (§6) | exit 0, no spawn |
| L4 | last turn's assistant text contains ≥1 state-claim regex match (canonical Step 2.5b pattern) | exit 0, no spawn |
| L5 | last turn does NOT contain the recursion-guard sentinel (§10) | exit 0, no spawn (this is the Part 2 reviewer's own emission) |

If all L0–L5 pass, **spawn**. The conjunction is intentionally narrow — Part 2 should fire on perhaps 1–5 turns per heavy infrastructure session, not 20+.

### 3.3. Cost ceiling (concrete)

- **Per-session hard cap:** 7 spawns. After the 7th, all subsequent triggers are no-op (stderr line: `[Q1-PART2] session cap reached (7/7); skipping further reviewer spawns`).
- **Pre-cap soft alert:** at spawn 5/7, emit a stderr warning line: `[Q1-PART2] cost notice — 5 of 7 reviewer spawns used this session`.
- **Per-trigger cost estimate (rendered in banner):** ~$0.50–$2 (Opus subagent, ~5–15K tokens output). Source: §8 cost model derivation.
- **Per-session worst-case spend:** 7 × $2 = $14/session ceiling. Typical session: 1–3 spawns × ~$1 = $1–$3.
- **Counter persistence:** `~/.claude/state/q1_part2_spawns_<session_id>.txt` — single integer line, incremented atomically. File auto-cleared at session end via SessionStart hook (deferred to implementation; for now the file accumulates harmlessly per-session).

### 3.4. Output mechanism (inline stderr banner)

Mirrors Part 1's stderr ANSI banner (consistency principle). The banner contains:
- Header: `[Q1-PART2 OPUS REVIEWER] <verdict>` (verdict is one of `PASS`, `WARN`, `FAIL`).
- Trigger evidence: file paths that matched §6, regex matches that fired L4.
- Reviewer findings (verbatim from the Opus subagent's structured-output JSON).
- Spawn cost: actual token usage (input/output) and estimated USD if API returned billing info; else "estimate ~$X (see §8)".
- Session counter: `(spawn N/7 used this session)`.

Stdout left empty (Claude Code interprets stdout as hook directive — mirror Part 1 §7 rationale).

### 3.5. Recursion guard

The reviewer subagent runs in a separate `claude -p` headless invocation with its own session_id. To prevent infinite recursion:

1. **Sentinel injection (primary guard):** the spawn command sets the env var `Q1_PART2_REVIEWER_ACTIVE=1`. The Stop hook script's L0 check tests for this env; if set, exits 0 immediately without spawning.
2. **Subagent prompt sentinel (defense-in-depth):** the standardized prompt template (§7) instructs the reviewer to NOT use state-claim language patterns in its own output and to start its response with the literal sentinel string `<!-- Q1_PART2_REVIEWER_OUTPUT_SENTINEL_DO_NOT_TRIGGER -->`. Part 1's regex never matches this sentinel; Part 2's L5 check for the sentinel ensures even if Part 2 were somehow invoked on a reviewer-emitted transcript, it would no-op.
3. **Subagent invocation flag:** spawn with `--no-hooks` (Claude Code SDK flag if present) OR a settings.local.json override that disables Stop hooks for the subagent. [INFERRED — Claude Code SDK headless flag set is implementation-time discovery; the spec mandates the env var as the primary mechanism since env vars are guaranteed inheritable.]
4. **Process-tree depth limit:** the hook script reads its own `os.getppid()` chain via `ps`; if Claude Code's parent chain shows we're already inside a `claude -p` invocation, exit 0. [INFERRED — implementation-time validation needed for ps-based chain detection on macOS/Linux.]

The four guards are layered; even if one fails the others catch the recursion. §10 specifies the precise mechanism.

## §4. Dual-Opus debate (verbatim)

### 4.1. Round 1 — Trigger scope

**Advocate:** Trigger on every turn that writes to any file under `~/.claude/skills/`, `Production/scripts/`, `Production/lib/`, `~/.claude/hooks/`, `~/.claude/settings.json`, `Production/github_actions/`, or any `.md` under `Production/docs/` matching `*_SPEC_v*.md` / `LD*.md`. Plus any Directus write to `prod_locked_decisions`. Cast wide because the cost of a missed false claim on infrastructure compounds (it gets cited in future LDs as established truth).

**Counter:** That set is too broad. `Production/scripts/` includes >100 files including one-off migration helpers nobody depends on. Casting wide blows the 7-spawn cap on the first heavy session. Narrow to a handpicked critical infrastructure list: hooks, settings.json, the audit scripts, the skill `SKILL.md` files, `weekly_preflight_audit.py`, and LD authoring docs in `Production/docs/`. Roughly 30 files total.

**Resolution:** narrow list. §6 specifies the exact paths. Cast wide produced too many spawns on test sessions per the cost model. Adding more paths is a non-breaking spec amendment if the list proves under-inclusive. Removing paths under cost pressure is harder once installed.

### 4.2. Round 2 — Output mechanism

**Advocate:** stderr banner inline, mirror Part 1. Kim already reads stderr; consistency is its own value. Banner shows verdict + findings + spawn cost.

**Counter:** stderr is ephemeral. If Kim is doing 4 hours of work and the banner scrolls off, she loses the verdict. Append to a session log file `~/.claude/state/q1_part2_session_<id>.log` so findings are recoverable. Optionally also a Directus row for high-severity FAIL verdicts so they survive the session.

**Resolution:** both. Stderr banner is primary (immediate visibility, mirrors Part 1). Session log file is secondary (recoverability). Directus row is a Phase-D follow-up (out of v1 scope; tracked as open decision §12).

### 4.3. Round 3 — Failure mode (what if reviewer finds a false claim AFTER message shipped?)

**Advocate:** banner makes Kim aware. She corrects in next turn. Same model as Part 1.

**Counter:** that's fine for low-severity verdicts. For a CRITICAL FAIL ("the wiring claim is mechanically wrong; the file Claude wrote does not actually do what was claimed"), the bad LD/spec/hook is now in the codebase. The next session may cite it as truth. Need a louder signal — e.g., a `prod_blockers` row auto-written, or a `STATE_CLAIM_FAIL` activity_log row.

**Resolution:** v1 = stderr banner only (parity with Part 1, simplest mechanism). v2 amendment can add `prod_blockers` auto-write for FAIL verdicts. Tracked as open decision §12.

### 4.4. Round 4 — Cost ceiling enforcement

**Advocate:** soft alerts only ("you've used 5 of 7 spawns"). Don't actually block at the cap — Kim might want the 8th spawn precisely because she's deep in infrastructure.

**Counter:** soft caps that don't enforce are no caps. Kim's stated concern is cost overruns. Hard cap. If she hits it, she can override with `MN_Q1_PART2_NO_CAP=1` env per session.

**Resolution:** hard cap with explicit env override. Mirrors DS-21 / DS-20 / DS-22 override pattern (env var + audit row).

### 4.5. Round 5 — Recursion guard (cheaper alternative?)

**Counter:** spawning Opus per turn is expensive. Cheaper alternative: a structured-output schema in Claude Code itself ("when assistant output contains state-claim patterns plus tool_use writes, require the assistant to inline a verification proof block in the same turn"). No subagent needed.

**Advocate:** that's a different feature — it requires modifying Claude Code's response harness, which is not a user-controllable change. Q1 Part 2 has to live in user space (hooks). The structured-output schema is a Q1 Part 3 candidate but not a substitute for Part 2.

**Resolution:** Part 2 stays as the conditional Opus reviewer subagent. The structured-output idea is logged as Q1 Part 3 candidate (out of scope for this spec).

### 4.6. Round 6 — Reviewer's own state claims

**Counter:** the reviewer subagent will, by nature, make state claims about whether the assistant's claims were verified. If those reviewer claims are themselves wrong, Part 2 amplifies the problem.

**Advocate:** the reviewer's standardized prompt (§7) forces it to **quote evidence inline** for every PASS verdict (i.e., quote the file content that proves the claim) and to use Rule 24 tags (`[CONFIRMED from <file>:<line>]`) for every assertion. No bare claims allowed. Hard-coded into the prompt template.

**Resolution:** prompt template enforces evidence-quoting; recursion guard prevents Part 2 from triggering on the reviewer's own output (§10). Acceptable residual risk: a reviewer who fabricates a quoted line. This is a model-quality concern, not a Part 2 design flaw.

## §5. Resolution + decision criteria

| Decision | Resolution | Rationale |
|---|---|---|
| Trigger scope | Narrow handpicked path list (§6) | Cost ceiling pressure; expand later if under-inclusive |
| Output | stderr banner + session log file | Immediate + recoverable; Directus row is v2 |
| Failure mode | warn-only, exit 0 | Parity with Part 1; CRITICAL FAIL → blocker is v2 amendment |
| Cost cap | Hard cap at 7 spawns/session, env-override | Mirrors DS-20/21/22 override pattern |
| Recursion guard | 4 layered guards (env + sentinel + flag + ps depth) | Defense-in-depth |
| Reviewer claims | Prompt mandates quoted evidence + Rule 24 tags | Reduces but does not eliminate residual risk |

**Decision criteria for each:**
- Cost: must be predictable bounded ($14/session worst case).
- Latency: 30–60 sec per spawn is acceptable post-turn (turn already shipped; banner is delayed feedback).
- False positive rate: estimate ≤10% on triggered turns (acceptable; banner is warn-only).
- False negative rate: any infrastructure turn whose path is not in §6 list is a missed scan; mitigation = quarterly review of §6 list against new infrastructure.
- Recursion: must be mechanically impossible (multiple guards, not one).

## §6. Trigger criteria spec — which paths/operations match?

### 6.1. Infrastructure file path patterns (allow-list, exact match)

The hook fires L3 trigger only if the last turn's Write|Edit tool_use `file_path` matches **at least one** of:

```
~/.claude/hooks/*.py
~/.claude/settings.json
~/.claude/settings.local.json
**/.claude/skills/*/SKILL.md
**/CLAUDE.md
**/Production/scripts/preflight_hook.py
**/Production/scripts/weekly_preflight_audit.py
**/Production/scripts/session_event_logger.py
**/Production/scripts/precompact_save_trigger.py
**/Production/scripts/deny_bash_governed_write.py
**/Production/scripts/lock_decision.py
**/Production/scripts/registered_write.py
**/Production/lib/directus.py
**/Production/lib/preflight.py
**/Production/github_actions/*.yml
**/Production/github_actions/*.yaml
**/Production/docs/*_SPEC_v*.md
**/Production/docs/MINDFULNEST_PROFESSIONAL_SETUP_ROADMAP_v*.md
**/Production/docs/*LD*.md
**/firestore.rules
**/firestore.indexes.json
```

Path matching uses `fnmatch.fnmatch` (Python stdlib glob semantics, `**` recursive). Exact pattern set is stored in a constant `INFRASTRUCTURE_PATH_PATTERNS` at top of the hook script for easy review.

### 6.2. Directus operations (out of scope for v1)

Bash tool_use that POSTs to `/items/prod_locked_decisions` (LD writes) or `/items/prod_reference_docs` would also be a candidate trigger, but Bash tool_use payloads do not expose structured `file_path` semantics — detecting a Directus write requires regex-scanning the Bash command string. Defer to v2 amendment. Tracked as open decision §12.

### 6.3. Negative tests (false-trigger prevention)

The trigger MUST NOT fire on:
- Edits to storyboard HTML files (`Production/Storyboards/**/*.html`) — high-volume, lower state-claim risk.
- Edits to arc skeletons (`Production/Arc Skeletons/*.md`) — narrative content, not infrastructure.
- Edits to Phase B scripts, Phase A designs, audio production files — all under `Production/Modules/` or `Production/Audio/`.
- Edits to `Production/docs/HANDOFF_*.md` (handoffs are throwaway operational docs).
- Edits to `Production/docs/SESSION_*.md` (session logs).
- Edits to `Production/_previews/**/*.html` (preview templates).
- Edits to `.auto-memory/*.md` (memory files).
- Read-only tool_use (Read, Grep, Glob, no Write|Edit) — already excluded by L2.

### 6.4. Test fixtures (planted in implementation phase)

| Fixture | Expected behavior |
|---|---|
| Edit to `~/.claude/hooks/stop_state_claim_scan.py` + state-claim text | TRIGGER — spawn reviewer |
| Edit to `Production/Storyboards/M1E1.html` + state-claim text | NO TRIGGER — path not in allow-list |
| Edit to `~/.claude/skills/zero-error-qa/SKILL.md` + state-claim text + `[CONFIRMED…]` tag | NO TRIGGER (L4 fails — tag suppresses regex match per Step 2.5b semantics) |
| Edit to `Production/lib/directus.py` + state-claim text + no tag | TRIGGER |
| Read to `Production/lib/directus.py` (no Write) + state-claim text | NO TRIGGER (L2 fails) |
| Edit to `~/.claude/settings.json` from inside a `claude -p` reviewer subagent | NO TRIGGER (L0 — env var sentinel) |
| 8th infrastructure write in same session | NO TRIGGER (L1 — cap reached) |

## §7. Reviewer subagent prompt template

The Stop hook spawns the subagent via:

```bash
Q1_PART2_REVIEWER_ACTIVE=1 claude -p "$(cat <<'EOF'
<!-- Q1_PART2_REVIEWER_OUTPUT_SENTINEL_DO_NOT_TRIGGER -->

You are an adversarial state-claim verifier. You have ONE job: independently
verify every state claim in the assistant's last message against the actual
files that were written in that turn.

CONTEXT
Assistant's last message text (verbatim):
<<<ASSISTANT_TEXT>>>

Files written in last turn:
<<<FILE_PATHS>>>

INSTRUCTIONS
1. Identify every state claim in the assistant text. State claims match this
   pattern (case-insensitive):
   \b(is|are|will be|gets?|gates?|surfaces?|fires?|runs?|executes?|reads?|
   writes?|cross-references?|hooks? into|enforces?|prevents?|catches?)\s+
   (wired|fired|surfaced|read|written|enforced|mechanically|automatically|
   by the [a-z\s]+|on [a-z\s]+|when [a-z\s]+|via [a-z\s]+|through [a-z\s]+)
2. For each state claim, Read the relevant written file(s) and find the
   line(s) that prove or disprove the claim.
3. For every assertion you make, use Rule 24 format:
   [CONFIRMED from <file>:<line>] — quote the line(s) verbatim, OR
   [DISCONFIRMED — file says <quoted line>; claim says <quoted phrase>], OR
   [INSUFFICIENT EVIDENCE — file does not contain affirming or contradicting text].
4. Do NOT use state-claim language patterns yourself (start with the sentinel
   line; verb forms like "this hook fires when X" trigger Q1 Part 1's regex).

OUTPUT FORMAT (strict JSON to stdout)
{
  "verdict": "PASS" | "WARN" | "FAIL",
  "claims": [
    {
      "claim": "<verbatim quoted phrase from assistant text>",
      "evidence": "<quoted file:line proof>",
      "rule24_tag": "CONFIRMED" | "DISCONFIRMED" | "INSUFFICIENT_EVIDENCE",
      "notes": "<optional one-line justification>"
    }
  ],
  "summary": "<one-sentence verdict explanation>",
  "spawn_cost_estimate_usd": <float>
}

VERDICT RULES
- PASS: every claim CONFIRMED.
- WARN: ≥1 claim INSUFFICIENT_EVIDENCE; no DISCONFIRMED.
- FAIL: ≥1 claim DISCONFIRMED.

CONSTRAINTS
- Do NOT call any tools other than Read.
- Do NOT write any files.
- Do NOT make Directus calls.
- Do NOT use the Bash tool.
- Stay under 15K output tokens.
- If the assistant text contains zero state-claim regex matches, output
  {"verdict":"PASS","claims":[],"summary":"no state claims to verify"}.
EOF
)" --output-format json --max-turns 1
```

**Key design choices in the prompt:**
- Sentinel as the first line ensures the reviewer's output never triggers Q1 Part 1's regex (the sentinel suppresses) AND never triggers Q1 Part 2's L5 (the sentinel is the L5 marker).
- Read-only tool restriction prevents the reviewer from making Directus writes, file edits, or Bash side effects.
- Strict JSON output makes parsing deterministic; the Stop hook script `json.loads()` the response.
- Token cap (~15K output) bounds spawn cost.
- `--max-turns 1` prevents the reviewer from looping (single-shot review, no follow-ups).

## §8. Cost model — per-trigger cost estimate; per-session ceiling; alert if exceeded

### 8.1. Per-trigger cost derivation

| Component | Tokens (typical) | Tokens (worst case) | Notes |
|---|---|---|---|
| System prompt | ~1,500 | ~1,500 | Standard Claude Code system prompt |
| Reviewer prompt template | ~500 | ~500 | §7 template, fixed |
| Assistant text input | ~500 | ~5,000 | Last message text; Part 1 caps at 500 KB |
| File contents (Read calls) | ~2,000 | ~10,000 | Up to 3 files at ~3K tokens each |
| Reviewer reasoning | ~1,000 | ~5,000 | Internal reasoning before output |
| Reviewer JSON output | ~500 | ~3,000 | Strict JSON, bounded by §7 token cap |
| **Total input** | ~4,500 | ~17,000 | |
| **Total output** | ~1,500 | ~8,000 | |

**Cost calculation (Opus 4.7 reference rates):**
- Input: ~$15/MTok → 4,500 tokens = $0.07; 17,000 tokens = $0.26
- Output: ~$75/MTok → 1,500 tokens = $0.11; 8,000 tokens = $0.60
- **Per-trigger total:** ~$0.18 typical; ~$0.86 worst case.

[INFERRED — Opus 4.7 1M-context token rates may differ; the spec uses Opus 4 rates as conservative estimate. Implementation phase will verify against `claude --version` model card or pricing table.]

### 8.2. Session ceiling math

- Hard cap: 7 spawns/session.
- Typical: 2–3 spawns × $0.18 = **$0.36–$0.54/session typical.**
- Worst case: 7 spawns × $0.86 = **$6.02/session worst case.**

This is well below the advocate-side $10–$100/session estimate that motivated the cost concern, because:
1. Trigger criteria (§6) are narrow — most infrastructure work is bursty and produces 1–3 triggers per session, not 20–50.
2. Hard cap at 7 enforces a ceiling regardless of trigger volume.
3. Per-trigger output cap (~15K) bounds the largest spend.

### 8.3. Cost monitoring

- The hook script reads `--output-format json` response which (per Claude Code SDK) includes `total_cost_usd` and `total_tokens` fields. [INFERRED — verified at implementation time against actual `claude -p` JSON output.]
- Each spawn appends a line to `~/.claude/state/q1_part2_session_<id>.log` with: timestamp, file paths, verdict, tokens used, USD cost.
- At session end (Stop hook with `stop_hook_active=true`, OR PreCompact), the log can be tail'd to compute session total.

### 8.4. Override

`MN_Q1_PART2_NO_CAP=1` env var disables the L1 ceiling check. Mirrors DS-20/21/22 override pattern. Setting this requires a `Q1_PART2_CAP_BYPASSED` activity_log row in Directus per the existing override discipline (enforced at Phase 7 closeout, not in the hook itself).

## §9. Output mechanism — inline banner via stderr (mirror Part 1)

**Channel:** stderr only. Stdout left empty (Claude Code parses stdout as systemMessage / hook directive).

**Banner template:**

```
\033[33m======================================================================\033[0m
\033[1;31m[Q1-PART2 OPUS REVIEWER] Verdict: <PASS|WARN|FAIL>\033[0m
\033[33m======================================================================\033[0m
Source:        stop-hook (Q1 Part 2, conditional Opus reviewer)
Trigger paths: <comma-separated list of files that matched §6>
Regex matches: <count> (Step 2.5b pattern)
Spawn cost:    ~$<X.XX> (input <N> tok, output <M> tok)
Session usage: <N>/7 spawns used

Findings:
  1. CLAIM: "<verbatim claim>"
     [CONFIRMED|DISCONFIRMED|INSUFFICIENT_EVIDENCE] from <file>:<line>
     "<quoted evidence>"
  2. ...

Summary: <reviewer's one-sentence summary>

This is a WARN-ONLY scan. Turn already shipped. Re-verify in the next turn if FAIL.
\033[33m======================================================================\033[0m
```

Plaintext fallback when `NO_COLOR` env set or stderr is not a TTY (mirrors Part 1).

**Secondary log file:** every spawn (regardless of verdict) appends a single JSON line to `~/.claude/state/q1_part2_session_<session_id>.log` with the full reviewer JSON response. This is the recoverability layer (Round 2 resolution).

**No Directus row in v1** (Round 3 resolution; v2 amendment for FAIL verdicts only).

## §10. Recursion guard — reviewer must NOT trigger itself

Four layered guards:

### 10.1. Env var sentinel (primary, hard guard)

The Stop hook spawns the subagent with `Q1_PART2_REVIEWER_ACTIVE=1` in the environment. The hook's L0 check is:

```python
if os.environ.get("Q1_PART2_REVIEWER_ACTIVE") == "1":
    return 0  # we are inside a reviewer subagent; never spawn another
```

Since env vars are inherited by child processes, any `claude -p` spawned by the reviewer (which is ruled out by §7 prompt constraints anyway) would also see the var and refuse to spawn. This is the primary mechanism.

### 10.2. Output sentinel (defense-in-depth)

The reviewer's prompt mandates the first line of its response be:

```
<!-- Q1_PART2_REVIEWER_OUTPUT_SENTINEL_DO_NOT_TRIGGER -->
```

The Stop hook's L5 check:

```python
if "<!-- Q1_PART2_REVIEWER_OUTPUT_SENTINEL_DO_NOT_TRIGGER -->" in last_assistant_text:
    return 0  # this is reviewer output; do not analyze
```

This catches the case where for some reason the env var was not inherited (e.g., a settings.local.json override stripped it).

### 10.3. Subagent invocation flag (defense-in-depth)

Spawn `claude -p` with the documented Claude Code SDK flag that disables hooks for the subagent invocation. [INFERRED — the spec mandates the env var as primary because env-based mechanisms are guaranteed; the SDK flag is a hardening additive once verified. Implementation phase confirms the exact flag name; if no flag exists, the env-based and sentinel guards are sufficient.]

### 10.4. Process-tree depth limit (final backstop)

The hook reads its parent process chain via `ps -p $$ -o ppid=` and walks up to a configurable depth (default 5). If any ancestor process command-line contains `claude -p`, exit 0 immediately.

```python
import subprocess
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

**Why four guards, not one:** any single guard can fail in ways the design cannot fully predict (env var stripped by a wrapper, sentinel removed by a model error, SDK flag absent or renamed, ps tree obscured by nohup/setsid). Four guards layered means **all** must fail simultaneously for recursion to occur — a vanishingly low joint probability.

**Recursion-guard test fixture:** in implementation, plant a synthetic transcript where the assistant text begins with the sentinel and the env var is set; assert the hook exits 0 with no spawn.

## §11. Implementation phases

This is DESIGN-ONLY. Implementation will follow in a separate authorized session post-Cursor cross-review. Phase order:

| Phase | Scope | Deliverable | Gate |
|---|---|---|---|
| A | Spawn-mechanism validation in isolation | A standalone test script that calls `claude -p "<prompt>" --output-format json` from a Python parent and parses the response | Verify `--output-format json` shape matches §7 expectations; verify env var inheritance; verify cost fields present |
| B | Hook script scaffolding | `~/.claude/hooks/stop_conditional_opus_reviewer.py` with L0–L5 trigger logic; no spawn yet (dry-run mode emits "would spawn" lines to stderr) | Trigger logic correctness verified against §6.4 fixtures |
| C | Settings.json wiring | Append second hook to `Stop` array (peer to Part 1); backup settings.json | Diff vs backup shows only Stop array additive; existing keys bytewise unchanged |
| D | Prompt template + spawn invocation | Wire actual `claude -p` spawn with §7 template; capture stdout JSON; render banner | One end-to-end test: synthetic infrastructure edit + state claim → assert reviewer spawn produced JSON verdict |
| E | Cost monitor + session log | Counter file, soft alert at 5/7, hard cap at 7; session log file appends | Counter increments correctly; ceiling hit emits ceiling-reached stderr line |
| F | Recursion guard validation | All 4 guards tested against synthetic recursion attempts | Verify each guard alone catches recursion; verify joint failure requires all 4 to bypass |
| G | Kill-switch | Document `MN_Q1_PART2_NO_CAP` env override; document settings.json removal procedure | Removal procedure restores pre-Part-2 settings.json bytewise |

**No production rollout** until all 7 phases gate-pass. Multipass + Phase 7 closeout per zero-error-qa applies.

## §12. Open decisions

| # | Decision | Default | Resolution path |
|---|---|---|---|
| 1 | Should FAIL verdicts auto-write a `prod_blockers` row? | No (v1) | v2 amendment after first 10 spawns observed; Kim review |
| 2 | Should Directus writes (Bash POST to prod_locked_decisions) trigger Part 2? | No (v1) | v2 amendment; needs Bash command-string regex design |
| 3 | Should the cap be 7, 10, or 5? | 7 | Calibrate after first session of real usage; adjustable via env `MN_Q1_PART2_CAP=N` (deferred to v2) |
| 4 | Is Opus 4.7 the right reviewer model, or should it be Sonnet for cost? | Opus 4.7 | Trade-off: Sonnet is ~5× cheaper but may miss subtle false claims; Opus matches the parent agent's class. Re-evaluate after 30 days of usage data. |
| 5 | Should the prompt template be versioned in a separate file rather than inline in the hook script? | Inline (v1) | If template grows >100 lines or Kim wants to A/B test, factor to `~/.claude/hooks/q1_part2_prompt_template.md` |
| 6 | Should there be a Cursor cross-review of every reviewer FAIL verdict? | No (v1) | Out of scope; meta-review-of-meta-review escalates cost |
| 7 | Should the reviewer have access to Directus reads? | No (v1) | Adding Directus reads would let the reviewer verify "LD 565 is read by Phase 0.7" claims directly. Trade-off: more verification power vs more spawn cost + more attack surface. v2 candidate. |
| 8 | Should Q1 Part 3 be specced now? | No | Part 3 (e.g., the structured-output schema mentioned in §4.5) is independent of Part 2; spec it after Part 2 has 30 days of operational data. |

## §13. Pre-implementation gates

Per zero-error-qa Phase 0:
1. Cursor cross-review of this spec (handoff at `Production/docs/HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508.md`).
2. Cursor verdict must be `AUTHORIZE_IMPLEMENTATION` or `AMEND_V2` (not `PAUSE_FOR_REDEBATE`).
3. If `AMEND_V2`, author v2 of this spec addressing each blocker; re-run Cursor cross-review on v2.
4. Once authorized, `lock_decision.py` writes LD `Q1_PART2_CONDITIONAL_REVIEWER_DESIGN_LOCKED_V1` with this spec as the `reference_doc`.
5. `prod_preflight_reviews` row written for the implementation session per Rule 19.
6. Phase 0 Step 1.5 attribute-class scan: this spec touches `~/.claude/hooks/`, `~/.claude/settings.json`, and `Production/docs/*_SPEC_v*.md` — confirm Q1 Part 2 install does NOT touch the main RN app CI/CD (per memory rule `project_main_app_cicd_greenfield_lock.md`). [CONFIRMED — Q1 Part 2 is a Stop-hook subagent, not CI/CD; no overlap.]
7. Phase 0 Step 2 HALT-gate scan: this spec proposes a hard cost cap; `MN_Q1_PART2_NO_CAP=1` is the override; mirrors existing DS-20/21/22 override pattern; no NEW HALT mechanism needed.

## §14. Risk assessment

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| Recursion (reviewer triggers itself) | Low | High | 4-layer guard (§10) |
| Cost overrun (>$14/session) | Low | Med | Hard cap at 7 (§3.3, §8) |
| False positive (reviewer flags valid claim as DISCONFIRMED) | Med | Low | Warn-only banner; Kim resolves in next turn |
| False negative (real false claim not in §6 path list) | Med | Med | Quarterly review of §6 path list; user-amendable constant |
| Subagent latency degrades UX | Med | Low | Spawn happens post-turn; banner is delayed feedback, not blocking |
| `claude -p` SDK semantics change in future Claude Code release | Low | Med | Spec mandates verify-at-implementation; pin Claude Code version in roadmap |
| Reviewer fabricates evidence quotes | Low | High | Prompt mandates `[CONFIRMED from <file>:<line>]`; mitigation residual; Kim spot-checks |
| Settings.json corruption on install | Low | High | Backup + JSON-validate on every write (mirrors Part 1 §4 procedure) |
| Session log file growth unbounded | Low | Low | Append-only; rotated at SessionStart hook (deferred); session-scoped paths cap blast radius |
| Prompt-injection via assistant text | Low | High | Reviewer is read-only and tool-restricted; sentinel + structured JSON output limit blast radius |

## §15. Rollback procedure

If the hook misfires or causes problems:

**Surgical removal** (preserves Part 1 + other hooks):
```bash
python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.claude/settings.json'
d = json.loads(p.read_text())
d['hooks']['Stop'] = [d['hooks']['Stop'][0]]  # keep only Part 1 (first entry)
p.write_text(json.dumps(d, indent=2))
"
```

**Backup restore** (clean rollback to pre-Part-2 state):
```bash
cp ~/.claude/settings.json.backup_q1_part2_<ISO> ~/.claude/settings.json
```

**One-line disable** (no settings.json edit):
```bash
mv ~/.claude/hooks/stop_conditional_opus_reviewer.py ~/.claude/hooks/stop_conditional_opus_reviewer.py.disabled
```
The settings.json invocation will fail at OS level (file not found), Python will return non-zero on the missing path → but `command` is bash, which exits non-zero → Claude Code logs the error and continues. [INFERRED — verify at implementation; if non-zero exit causes issues, prefer the surgical removal path.]

**Kill-switch env var** (per-session override of the cap, NOT a disable):
```bash
export MN_Q1_PART2_NO_CAP=1
```
This is intended for high-volume infrastructure sessions; not a disable. To actually skip the hook, use settings.json removal.

## §16. Testing plan — synthetic test scenarios

All run as fixtures in Phase D (implementation), no production data touched.

### 16.1. Trigger fixtures (positive path)

| Fixture | Setup | Expected |
|---|---|---|
| F1 — hook edit + claim | Plant transcript: assistant text "the new hook is wired by the Stop event" + tool_use Edit `~/.claude/hooks/test.py` | TRIGGER → reviewer spawned, banner emitted |
| F2 — settings.json edit + claim | Plant: text "the gate fires when X" + Edit `~/.claude/settings.json` | TRIGGER |
| F3 — SKILL.md edit + claim | Plant: text "DS-22 is enforced mechanically" + Edit `mn-context/SKILL.md` | TRIGGER |
| F4 — multi-file edit | Plant: text with claims + 3 Edit calls (1 infra, 2 storyboard) | TRIGGER (infra path matches L3) |

### 16.2. No-trigger fixtures (negative path)

| Fixture | Setup | Expected |
|---|---|---|
| F5 — no infra path | Plant: claim text + Edit `Production/Storyboards/M1E1.html` | NO TRIGGER (L3 fails) |
| F6 — Read-only turn | Plant: claim text + Read `Production/lib/directus.py` (no Write/Edit) | NO TRIGGER (L2 fails) |
| F7 — tagged claim | Plant: "X is wired [CONFIRMED from file:42]" + infra Edit | NO TRIGGER (L4 — regex match suppressed by tag, mirroring Part 1) |
| F8 — no claim text | Plant: benign text + infra Edit | NO TRIGGER (L4 fails) |
| F9 — re-entrant | Set `Q1_PART2_REVIEWER_ACTIVE=1` env; plant trigger fixture F1 | NO TRIGGER (L0 — env var sentinel) |
| F10 — output sentinel present | Plant: text starts with reviewer sentinel + infra Edit | NO TRIGGER (L5 — sentinel) |
| F11 — cap reached | Pre-set counter file to 7; plant fixture F1 | NO TRIGGER (L1 — cap; emit ceiling-reached stderr) |

### 16.3. Subagent fixtures (when L0–L5 all pass)

| Fixture | Setup | Expected |
|---|---|---|
| F12 — PASS verdict | Reviewer is given an assistant text whose claims are all true vs the file written | Banner shows PASS, claims listed with CONFIRMED tags |
| F13 — FAIL verdict | Reviewer given text whose claim is false vs the file (e.g., "the hook fires on PreToolUse" but the file actually wires Stop) | Banner shows FAIL, claim listed with DISCONFIRMED + quoted evidence |
| F14 — INSUFFICIENT_EVIDENCE verdict | Reviewer given text whose claim references a file/line not in the written set | Banner shows WARN, claim listed with INSUFFICIENT_EVIDENCE |
| F15 — malformed reviewer JSON | Reviewer returns non-JSON text (e.g., refused or hit token cap mid-output) | Hook script falls back to "[Q1-PART2] reviewer returned malformed JSON; raw output: <first 500 chars>"; exits 0 |
| F16 — reviewer timeout | Reviewer takes >60 sec | Hook timeout at 90 sec → kill subprocess; emit "[Q1-PART2] reviewer timed out at 90s; verdict unknown"; exits 0 |
| F17 — reviewer cost >$2 | Reviewer JSON returns `total_cost_usd > 2.0` | Banner shows actual cost; emit "[Q1-PART2] WARNING — single spawn exceeded $2 estimate" |

### 16.4. Recursion guard fixtures

| Fixture | Setup | Expected |
|---|---|---|
| F18 — guard 1 only | Set env var; clear sentinel; clear ps chain | NO SPAWN |
| F19 — guard 2 only | Plant sentinel in text; clear env; clear ps chain | NO SPAWN |
| F20 — guard 4 only | Run inside a `claude -p` parent (mock via fake ps output); clear env; clear sentinel | NO SPAWN |
| F21 — all guards bypassed | Clear all 3 + force ps chain to look clean | SPAWN (this is the failure mode the design accepts as residual risk; documented in §14) |

### 16.5. Cost-model verification

| Fixture | Setup | Expected |
|---|---|---|
| F22 — typical cost | Run F12 (PASS verdict) on a small file | Tokens within ±20% of §8.1 typical estimates; cost ~$0.18 |
| F23 — worst-case cost | Run F12 on largest file in `~/.claude/hooks/` (or synthetic 10K-token file) | Tokens within §8.1 worst-case bounds; cost ≤$1 |
| F24 — session ceiling math | Run F1 7 times in same session | First 4 silent spawn; spawn 5 emits cost-notice line; spawn 7 emits "ceiling reached"; spawn 8 (F1 again) NO SPAWN |

## §17. Reference index

- **Q1 Part 1 spec:** `Production/docs/Q1_PART1_STOP_HOOK_SPEC_v1.md`
- **Q1 Part 1 hook implementation:** `~/.claude/hooks/stop_state_claim_scan.py`
- **Q1 Part 1 LD:** `Q1_PART1_STOP_HOOK_INSTALLED_V1` (LD 579)
- **DS-22 (state-claim mechanical gate):** `.claude/skills/zero-error-qa/SKILL.md` lines 213–242
- **Step 2.5b (canonical regex):** `.claude/skills/mn-context/SKILL.md` lines 291–319
- **Settings.json (current Stop wiring):** `~/.claude/settings.json` lines 82–91
- **Existing hook patterns:** `Production/scripts/preflight_hook.py`, `Production/scripts/precompact_save_trigger.py`, `Production/scripts/session_event_logger.py`
- **Override pattern reference (DS-20/21/22):** `.claude/skills/zero-error-qa/SKILL.md` lines 172–242
- **Cursor cross-review handoff (v2-hardened):** `Production/docs/HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508.md`
- **v2-hardened handoff template precedent:** `Production/docs/HANDOFF_CURSOR_REVIEW_PERIODIC_SPEC_20260508_v2.md`
- **MindfulNest greenfield CI/CD lock memory:** `project_main_app_cicd_greenfield_lock.md` (confirms Q1 Part 2 ≠ CI/CD)
- **Memory tail:** `Session 2026-05-08 03:02 UTC — V59 Storyboard Foundation Sprint`

---

**End of spec.**
