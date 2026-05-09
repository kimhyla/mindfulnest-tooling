# Handoff v2 — Cursor Cross-Review of Q1 Part 2 Conditional Opus Reviewer Tech Spec

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08
**Spec under review:** `Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md`
**Pairs with:** Q1 Part 1 spec at `Production/docs/Q1_PART1_STOP_HOOK_SPEC_v1.md` (already shipped, LD 579); Part 1 hook at `~/.claude/hooks/stop_state_claim_scan.py`.

---

## Step 0 — Preflight (do FIRST, before any analysis)

Before reading or critiquing the spec, run these checks and emit the results inline at the top of your response:

1. **Spec file exists:** `ls -la "Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md"` — capture size and mtime.
2. **Spec hash:** `shasum "Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md"` — capture hex digest.
3. **Quote spec header:** read first 30 lines verbatim and quote them inline as proof you read the actual file (not stale cache, not hallucinated).
4. **Companion files exist:** `ls -la "Production/docs/Q1_PART1_STOP_HOOK_SPEC_v1.md" "~/.claude/hooks/stop_state_claim_scan.py" "~/.claude/settings.json"` — capture sizes.

If any preflight fails, **HALT and report**. Do not proceed.

---

## Step 1 — Open the project in Cursor

`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`

Open `Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md` in the editor. Open Cursor Composer or chat.

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md. It proposes a conditional Opus reviewer subagent that fires on a Stop hook when the most recent assistant turn (a) wrote to an "infrastructure" file (allow-list in §6) AND (b) the assistant text contains state-claim regex matches. The reviewer reads the assistant text and the written files, returns a structured JSON verdict, and the parent hook renders an inline stderr banner. Hard cap: 7 spawns/session. Worst-case cost: ~$6/session.

Background context (informational only — do NOT let this anchor your scrutiny):
The spec was authored via dual-Opus debate (advocate vs counter, internalized; per-decision resolution). It builds on Q1 Part 1 (stop_state_claim_scan.py, already shipped 2026-05-07, LD 579), which catches the same regex at turn-end but stays silent when tool_use is present in the same turn. Treat the dual-Opus outcome as background, not as a judgment. Apply your full independent scrutiny regardless of prior debate outcome.

PREFLIGHT (do first, emit inline):
1. Confirm spec file exists; capture size + mtime.
2. shasum the spec; capture digest.
3. Quote first 30 lines of the spec verbatim.
4. Confirm companion files exist (Q1 Part 1 spec, ~/.claude/hooks/stop_state_claim_scan.py, ~/.claude/settings.json).
If preflight fails, HALT and report.

ANALYSIS REQUIREMENTS:

Every concern you raise MUST be in this format:
| # | Concern (one sentence) | Severity (CRITICAL/HIGH/MED/LOW) | Evidence (file + line ranges quoted) | Suggested mitigation | Blocker (Y/N) |

"Severity" rubric:
- CRITICAL = ship-blocker; spec must not advance to implementation
- HIGH = revise spec before implementation
- MED = address in v2 amendment OR document as known-deferred
- LOW = nice-to-have, optional

"Blocker" rubric:
- Y = Kim should NOT authorize implementation until this is resolved
- N = informational; documented and proceed acceptable

REQUIRED ANALYSIS TASKS:

A. RECURSION GUARD (the highest-stakes design element)
   - The spec specifies 4 layered guards in §10 (env var, output sentinel, SDK flag, ps chain depth). Independently assess: can ALL FOUR fail simultaneously under any realistic scenario? Walk through each guard's failure mode in detail.
   - The spec marks the SDK --no-hooks flag as [INFERRED] — what happens if no such flag exists in Claude Code? Does the design still hold?
   - Test fixture F21 admits "all guards bypassed" is residual risk. Is this acceptable? What additional guards are cheap to add?

B. COST MODEL VERIFICATION
   - The spec claims $0.18 typical / $0.86 worst-case per spawn (§8.1) using "Opus 4.7 reference rates" but tags rate as [INFERRED]. Independently look up Opus 4.x pricing and verify the math.
   - 7 spawns × $0.86 = $6.02 worst case. Is the 7-cap defensible? Is it too low (forces frequent overrides) or too high (cost slippage)?
   - Spec assumes typical session = 2-3 spawns. Is that realistic given §6 trigger criteria? Walk through a representative heavy infrastructure session and count probable triggers.
   - Are there cost components missing from §8.1 (e.g., system prompt overhead per `claude -p`, retries on rate-limit)?

C. TRIGGER CRITERIA SOUNDNESS (§6)
   - The §6 path allow-list has ~20 patterns. Enumerate every infrastructure-touching write op you can think of in a typical MindfulNest session. Does the list miss any? Does it over-include any?
   - §6.2 defers Directus writes to v2. Is that the right call, or does it leave a critical gap (LD writes are governance-class state changes)?
   - Negative tests in §6.3 — are they sufficient? What false-trigger paths should be added?

D. REVIEWER PROMPT TEMPLATE (§7)
   - The prompt restricts the reviewer to Read-only tools. What if the reviewer needs Bash to run grep across files? What if it needs Glob? Is read-only enough for the §6 file types?
   - The prompt mandates strict JSON output. What's the failure mode if the reviewer returns prose instead of JSON? (Spec F15 covers this, but adversarially: can a fabricated state claim manipulate the reviewer into bypassing JSON format?)
   - The prompt sentinel is the L5 recursion guard. What if the model omits the sentinel (token cap, refusal, hallucination)?

E. BANNER + LOG OUTPUT (§9)
   - Stderr banner is ephemeral. Session log file is recoverability. Is `~/.claude/state/q1_part2_session_<id>.log` rotation strategy adequate (spec defers rotation)?
   - For FAIL verdicts, spec defers Directus prod_blockers row to v2. Is "warn-only banner" enough for a CRITICAL FAIL where the assistant just wrote a wrong wiring claim into an LD?

F. INTERACTION WITH Q1 PART 1
   - Both hooks fire on Stop. Order matters: Part 1 runs first (per spec §3.1). What happens if Part 2 emits its banner BEFORE Part 1 emits its banner? Could one suppress the other in stderr buffering?
   - Are there scenarios where BOTH Part 1 AND Part 2 should fire (vs. spec's implication that Part 2 is for Part-1's-blind-spot)?

G. RISKS NOT IN §14
   - Race conditions on counter file (atomic-increment risk on concurrent sessions in same project)?
   - Dropbox sync of session log files (the project root is a Dropbox dir; would session logs sync and conflict)?
   - Subagent spawn while Kim's main session is mid-tool_use (does Stop fire during a tool_use turn or only after)?

H. SEQUENCING (Phases A-G in §11)
   - Build a dependency graph: which phase produces prerequisites for which? Write the graph inline.
   - Identify any phase where the spec's ordering creates risk if reversed.
   - Identify any phases that could parallelize without breaking dependencies.

REQUIRED OUTPUT:

1. Preflight evidence (size, mtime, shasum, first 30 lines quoted, companion-file confirmations)
2. Concerns table (mandatory citation format above)
3. Recursion-guard joint-failure scenario walkthrough (one paragraph per guard, plus a "what if all 4 fail" scenario)
4. Cost-model verification table (spec's claim vs your computed claim, per row of §8.1)
5. Phase dependency graph
6. Final gate decision in STRICT form (pick exactly one):

   **AUTHORIZE_IMPLEMENTATION**: spec is sound; Kim can advance to a separate implementation handoff session.
   **AMEND_V2**: spec needs revision; list specific blocker concerns that must be addressed.
   **PAUSE_FOR_REDEBATE**: spec has fundamental design issues; recommend fresh dual-Opus or expanded review.

7. If AMEND_V2 or PAUSE: provide the specific blocker list.
```

---

## Step 3 — After Cursor responds

If verdict is **AUTHORIZE_IMPLEMENTATION**:
- Bring the verdict back to Claude Code.
- Author the implementation handoff (`Production/docs/HANDOFF_Q1_PART2_IMPLEMENTATION_<DATE>.md`) per §11 phases.
- Spawn a Terminal CLI session for the implementation work.

If verdict is **AMEND_V2**:
- Bring the blocker list back to Claude Code.
- Author `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v2.md` addressing each blocker.
- Re-run this Cursor cross-review on v2 with the same gate format.

If verdict is **PAUSE_FOR_REDEBATE**:
- Bring the findings back to Claude Code.
- Spawn fresh dual-Opus debate or expanded review session.
- Do NOT advance to implementation.

---

## Why this v2-hardened format

This handoff mirrors `HANDOFF_CURSOR_REVIEW_PERIODIC_SPEC_20260508_v2.md` which incorporated 6 meta-fixes from Cursor's own review of v1: mandatory citation format, preflight block, source-of-truth/companion-file confirmation, removed framing bias, strict gate-decision format, sequencing/dependency-graph requirement. All 6 fixes are applied above. Q1 Part 2's recursion guard and cost model are the highest-stakes design elements, so the analysis tasks weight them heavily (Tasks A and B).

---

## What you DON'T need to do

- Don't have Cursor edit the spec (review-only)
- Don't have Cursor implement anything (separate Terminal CLI handoff)
- Don't paste sensitive info; spec contains no credentials
