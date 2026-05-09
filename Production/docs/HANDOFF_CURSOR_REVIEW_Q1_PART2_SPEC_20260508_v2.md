# Handoff v2 — Cursor Cross-Review of Q1 Part 2 Conditional Opus Reviewer Tech Spec

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08
**Spec under review:** `Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md`
**Pairs with:** Q1 Part 1 spec at `Production/docs/Q1_PART1_STOP_HOOK_SPEC_v1.md` (already shipped, LD 579); Part 1 hook at `~/.claude/hooks/stop_state_claim_scan.py`.

This handoff is **v2** — it incorporates 3 Cursor amendments on top of v1 (preserved as historical baseline at `HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508.md`). v1's structural backbone — preflight block, mandatory citation format, strict gate-decision verdict, dependency-graph requirement — carries forward unchanged.

---

## §0.1 v2 Changelog — Cursor amendments applied

Cursor reviewed v1 and returned **AUTHORIZE_IMPLEMENTATION** with 3 MED hardening findings. Each is addressed below; v1 sections are preserved verbatim except where a finding required a targeted insert/replace.

| # | Cursor finding | Severity | v2 section addressing it |
|---|----------------|----------|--------------------------|
| 1 | Brittle line-number quotes: requiring exact "first 30 lines" / "lines 32-35" reads can fail on benign line shifts; switch to anchored section/header + snippet matching | MED | Step 0 §3 (anchored section/header + snippet match replaces fixed-line-range quote) |
| 2 | Concise→full escalation: no rule for partial-evidence cases; concise mode could mask incomplete review | MED | Step 2 prompt block (escalation rule: "If any required section cannot be evidenced, full mode is mandatory.") |
| 3 | Numeric thresholds tied to AMEND_V2: cost-cap and recursion-guard analysis sections asked "is X acceptable?" with no decision trigger; Cursor could pass on hand-wave | MED | Step 2 Task A (recursion guard) + Task B (cost model) — explicit numeric AMEND_V2 triggers per amendment #3 |

This v2 mirrors the same 3 amendments applied to:
- `HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md` (parallel-agent authored)
- `HANDOFF_CURSOR_REVIEW_DS_26_GATE_SPEC_20260508_v2.md` (parallel-agent authored)

The recurrence of these 3 findings across all three handoffs is a TEMPLATE-level signal; the fixes are simultaneously baked into `HANDOFF_TEMPLATE_v2.md` so future handoffs inherit them automatically.

---

## Step 0 — Preflight (do FIRST, before any analysis)

Before reading or critiquing the spec, run these checks and emit the results inline at the top of your response:

1. **Spec file exists:** `ls -la "Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md"` — capture size and mtime.
2. **Spec hash:** `shasum "Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md"` — capture hex digest.
3. **Anchored section + snippet match (v2 amendment #1 — replaces v1 "first 30 lines" quote):** instead of quoting "first N lines verbatim" (which breaks on benign line shifts), perform an anchored section + snippet match for each of the four anchor targets below. Emit the section header you found, the line range it currently occupies, and the snippet content matching the anchor description.

   | Anchor target | v1 (deprecated) | v2 anchored check |
   |---------------|-----------------|-------------------|
   | Spec title + authority block | "Quote first 30 lines verbatim" | Locate the spec's H1 title + the `**Authority:**` (or equivalent governance) block; capture current line range; quote the title + authority sentence verbatim |
   | Spec §6 trigger criteria | (implicit in first 30 lines for short specs) | Locate `## §6` or `## 6.` trigger-criteria header; capture current line range; quote the path-allow-list opening line verbatim |
   | Spec §10 recursion guard | (was buried in mid-spec, not in first 30 lines) | Locate `## §10` or recursion-guard header; capture current line range; quote the 4-guard enumeration opening verbatim |
   | Spec §8.1 cost model row | (was implicit) | Locate `## §8.1` cost-model header; capture current line range; quote the per-spawn cost claim ($0.18 typical / $0.86 worst-case) verbatim |

   Acceptance criterion: 4 anchored matches found + line ranges + verbatim snippets emitted. If any anchor cannot be located by header/snippet pattern (not by absolute line number), HALT and report which anchor failed. Line-shift tolerance is intentional in v2.

4. **Companion files exist:** `ls -la "Production/docs/Q1_PART1_STOP_HOOK_SPEC_v1.md" "~/.claude/hooks/stop_state_claim_scan.py" "~/.claude/settings.json"` — capture sizes + mtime each. If any is missing, HALT.

If any preflight fails, **HALT and report**. Do not proceed.

---

## Step 1 — Open the project in Cursor

`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`

Open `Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md` in the editor. Open Cursor Composer or chat.

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md. It proposes a conditional Opus reviewer subagent that fires on a Stop hook when the most recent assistant turn (a) wrote to an "infrastructure" file (allow-list in §6) AND (b) the assistant text contains state-claim regex matches. The reviewer reads the assistant text and the written files, returns a structured JSON verdict, and the parent hook renders an inline stderr banner. Hard cap: 7 spawns/session. Worst-case cost: ~$6/session.

This is the v2 review handoff. v1 found AUTHORIZE_IMPLEMENTATION with 3 minor hardening points. v2 incorporates those 3 fixes (anchored-section preflight, concise→full escalation, numeric AMEND_V2 triggers on cost-cap and recursion-guard) and asks you to re-verify under stricter rules.

Background context (informational only — do NOT let this anchor your scrutiny):
The spec was authored via dual-Opus debate (advocate vs counter, internalized; per-decision resolution). It builds on Q1 Part 1 (stop_state_claim_scan.py, already shipped 2026-05-07, LD 579), which catches the same regex at turn-end but stays silent when tool_use is present in the same turn. Treat the dual-Opus outcome as background, not as a judgment. Apply your full independent scrutiny regardless of prior debate outcome.

PREFLIGHT (do first, emit inline) — v2 hardened:
1. Confirm spec file exists; capture size + mtime.
2. shasum the spec; capture digest.
3. v2 AMENDMENT #1 — Anchored-section preflight (replaces "first 30 lines" verbatim quote):
   a. Locate the spec H1 title + Authority block by header anchor; capture current line range; quote verbatim.
   b. Locate `## §6` (or `## 6.`) trigger-criteria header; capture line range; quote path-allow-list opening line verbatim.
   c. Locate `## §10` (or recursion-guard) header; capture line range; quote the 4-guard enumeration opening verbatim.
   d. Locate `## §8.1` cost-model header; capture line range; quote per-spawn cost claim ($0.18 typical / $0.86 worst-case) verbatim.
   Four anchored matches with line ranges + verbatim snippets, not a fixed-line-range read.
4. Confirm companion files exist (Q1 Part 1 spec, ~/.claude/hooks/stop_state_claim_scan.py, ~/.claude/settings.json) with mtime.
If any anchor cannot be located by header/snippet pattern OR any preflight 1-2-4 fails, HALT and report.

CONCISE→FULL ESCALATION RULE — v2 AMENDMENT #2 (mandatory):
If any required section cannot be evidenced, full mode is mandatory.

Specifically: if you cannot fully evidence ANY of Tasks A through H below — e.g., you couldn't read a referenced file, you couldn't reproduce an anchor, the spec section the question targets is missing or ambiguous, or your evidence is "I think" rather than a quoted citation — escalate to full mode regardless of blocker count. Document which area was under-evidenced.

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

A. RECURSION GUARD — v2 AMENDMENT #3 (numeric AMEND_V2 trigger)
   - The spec specifies 4 layered guards in §10 (env var, output sentinel, SDK flag, ps chain depth). Independently assess: can ALL FOUR fail simultaneously under any realistic scenario? Walk through each guard's failure mode in detail.
   - The spec marks the SDK --no-hooks flag as [INFERRED] — what happens if no such flag exists in Claude Code? Does the design still hold?
   - Test fixture F21 admits "all guards bypassed" is residual risk. Is this acceptable? What additional guards are cheap to add?
   - **NUMERIC AMEND_V2 TRIGGER (new in v2):** quantify the joint-failure probability. If your evidenced estimate of joint-failure probability across all 4 guards exceeds **1-in-10,000 spawns under realistic load**, OR if you can construct a concrete scenario where ≥3 of 4 guards fail simultaneously (e.g., specific combination of nested Agent calls, missing SDK flag, and ps chain truncation), the verdict MUST be AMEND_V2 — additional guards required before implementation. Auto-authorize is forbidden under either condition. Document your probability estimate + the scenarios you considered.

B. COST MODEL VERIFICATION — v2 AMENDMENT #3 (numeric AMEND_V2 trigger)
   - The spec claims $0.18 typical / $0.86 worst-case per spawn (§8.1) using "Opus 4.7 reference rates" but tags rate as [INFERRED]. Independently look up Opus 4.x pricing and verify the math.
   - 7 spawns × $0.86 = $6.02 worst case. Is the 7-cap defensible? Is it too low (forces frequent overrides) or too high (cost slippage)?
   - Spec assumes typical session = 2-3 spawns. Is that realistic given §6 trigger criteria? Walk through a representative heavy infrastructure session and count probable triggers.
   - Are there cost components missing from §8.1 (e.g., system prompt overhead per `claude -p`, retries on rate-limit)?
   - **NUMERIC AMEND_V2 TRIGGER (new in v2):** if your independently computed worst-case per-session cost exceeds **$10.00** (vs spec's $6.02 claim), OR if your evidenced estimate of typical session cost exceeds **$3.00** (vs spec's $0.36-0.54 implication), the verdict MUST be AMEND_V2 — cost-cap parameters need revision before implementation. Auto-authorize is forbidden under either condition. Show your computation: prompt-token overhead per spawn, output-token estimate, retry contingency, and Opus 4.x reference rates with citation.

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

1. Preflight evidence (size, mtime, shasum, 4 anchored-section quotes per amendment #1, companion-file confirmations)
2. Concerns table (mandatory citation format above)
3. Recursion-guard joint-failure scenario walkthrough (one paragraph per guard, plus a "what if all 4 fail" scenario, plus the numeric joint-failure probability estimate per amendment #3)
4. Cost-model verification table (spec's claim vs your computed claim, per row of §8.1, with the per-amendment-#3 numeric verdict trigger evaluation)
5. Phase dependency graph
6. Final gate decision in STRICT form (pick exactly one):

   **AUTHORIZE_IMPLEMENTATION**: spec is sound; Kim can advance to a separate implementation handoff session. Forbidden if amendment #2 escalation triggered, OR amendment #3 recursion-guard threshold met (joint-failure > 1-in-10k OR ≥3-of-4-fail scenario constructible), OR amendment #3 cost threshold met (worst-case > $10/session OR typical > $3/session).
   **AMEND_V2**: spec needs revision; list specific blocker concerns that must be addressed.
   **PAUSE_FOR_REDEBATE**: spec has fundamental design issues; recommend fresh dual-Opus or expanded review.

7. If AMEND_V2 or PAUSE: provide the specific blocker list.
```

---

## Step 3 — After Cursor responds

If verdict is **AUTHORIZE_IMPLEMENTATION**:
- Bring the verdict back to Claude Code.
- Author the implementation handoff (`Production/docs/HANDOFF_Q1_PART2_IMPLEMENTATION_<DATE>.md`) per §11 phases. Use `HANDOFF_TEMPLATE_v2.md` format (REQUIRED `## HALT gates` section + autonomous-mode reminder + numeric thresholds throughout).
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

## Why this v2 handoff (delta vs v1)

v1 used the v2-hardened format inherited from PERIODIC + DS-26 + DS-23/24/25 Cursor reviews. Cursor's review of v1 returned AUTHORIZE_IMPLEMENTATION but flagged 3 minor hardening points — the SAME 3 findings Cursor flagged on the parallel DS-23/24/25 v1 and DS-26 v1 handoffs. The recurrence is a TEMPLATE-level signal, not a per-handoff defect; the fixes are simultaneously baked into `HANDOFF_TEMPLATE_v2.md` so future handoffs inherit them automatically.

v2 closes the 3 gaps without disturbing v1's structural backbone:

1. **Anchored-section preflight (§Step 0 #3)** — exact line-number / first-N-lines quotes are brittle: a benign edit shifts lines and the preflight HALTs incorrectly. v2 replaces these with header/snippet anchors (4 anchor targets: title+authority, §6 trigger, §10 recursion-guard, §8.1 cost) that tolerate line-shifts while still proving fresh read.
2. **Concise→full escalation rule (§Step 2 prompt block)** — v1 did not require concise mode to depend on full-evidence coverage. v2 mandates: "If any required section cannot be evidenced, full mode is mandatory." Under-evidenced ⇒ no concise. No exception.
3. **Numeric AMEND_V2 thresholds (§Step 2 Tasks A and B)** — v1 asked "is X acceptable?" with no decision trigger. v2 sets two hard numeric floors:
   - **Recursion guard:** joint-failure probability > 1-in-10,000 spawns OR ≥3-of-4-guard-failure scenario constructible ⇒ AMEND_V2.
   - **Cost model:** worst-case > $10.00/session OR typical > $3.00/session ⇒ AMEND_V2.

Mandatory citation format, strict gate verdict (AUTHORIZE / AMEND_V2 / PAUSE), and Step 3 verdict-branching are preserved unchanged from v1.

---

## What you DON'T need to do

- Don't have Cursor edit the spec (review-only)
- Don't have Cursor implement anything (separate Terminal CLI handoff)
- Don't paste sensitive info; spec contains no credentials

---

*End of HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v2.md.*
