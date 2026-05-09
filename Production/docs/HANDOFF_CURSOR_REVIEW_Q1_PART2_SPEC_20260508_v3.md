# Handoff v3 — Cursor Cross-Review of Q1 Part 2 Conditional Opus Reviewer Tech Spec v1

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08
**Spec under review:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md` (44,437 bytes; 628 lines; sha256 `02b134f76cf7ea618e90701d3dd13f68c33e9ab92bb9a19ab6ece5869d8154aa`).

**Supersedes:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v2.md` (preserved as historical baseline; do NOT edit in place). v2 was authored in this same session and shipped 3 v2-amendments (anchored-section preflight, concise→full escalation, numeric AMEND_V2 thresholds on Tasks A + B). Cursor batch audit on 2026-05-08 returned PASS on amendments A/B/C but flagged 4 HANDOFF_TEMPLATE_v2 compliance gaps:
- **Gap D:** v2 used relative paths in companion-files block (Production/docs/...) instead of dual-canonical absolute paths.
- **Gap E:** v2 lacked canonical-root tag format (`— Dropbox-rooted (canonical root #1)`).
- **Gap F:** v2 lacked the `## HALT gates` section + autonomous-mode reminder verbatim block.
- **Gap G:** v2 lacked `## Hard rules` + `## Final report` sections per HANDOFF_TEMPLATE_v2 mandate.

**v3 driver:** v3 closes gaps D + E + F + G. The v1/v2 design surface (Cursor v1 returned `AUTHORIZE_IMPLEMENTATION` on the spec design; v2 hardened the prompt; v2 surface remains valid) is preserved; v3 is structural compliance only — every analysis task and every numeric threshold is preserved with the same verdict semantics, augmented with 6 tasks total to reflect the full scope of a fresh-spec review (Q1 Part 2 introduces the FIRST subagent-spawn surface in MindfulNest hooks; broader scrutiny is appropriate).

**Companion files (absolute paths per HANDOFF_TEMPLATE_v2 §0.3 dual-canonical):**

- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md` — Dropbox-rooted (canonical root #1; **spec under review**); sha256 `02b134f76cf7ea618e90701d3dd13f68c33e9ab92bb9a19ab6ece5869d8154aa`; 44,437 bytes; 628 lines.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508.md` — Dropbox-rooted (canonical root #1; v1 review handoff — historical baseline; do NOT modify); sha256 `50b3a2832a090bf03759f593d4419b2632c43cd18defae9892bc6a3e25097ea4`; 9,507 bytes.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v2.md` — Dropbox-rooted (canonical root #1; v2 review handoff — historical baseline that THIS v3 supersedes; do NOT modify); sha256 `aa8e7e1827265a25e26ffe895b7c52ed7fb716c92f9b7899f3fe23cca29e1d1c`; 17,462 bytes.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` — Dropbox-rooted (canonical root #1; **structural template** — v3 mirrors its compliance pattern); sha256 `6c583183e528e1e737b7c86d360b20149e0019393f9669bc4bdead70289deb97`.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — Dropbox-rooted (canonical root #1; v2 template — this handoff conforms to it); sha256 `35dc0e202fc47f28a887bdcf07b32eb627fdd8dbc19a7b509b04873c6606f4a2`.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_Q1_PART2_IMPLEMENTATION_20260508.md` — Dropbox-rooted (canonical root #1; downstream implementation handoff — review-only; this v3 handoff does not modify it).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/Q1_PART1_STOP_HOOK_SPEC_v1.md` — Dropbox-rooted (canonical root #1; Q1 Part 1 spec — pairs with Part 2; reference only).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/stop_state_claim_scan.py` — Dropbox-rooted (canonical root #1; Q1 Part 1 implementation source-of-truth in project tree if mirrored). NOTE: live hook is at `~/.claude/hooks/stop_state_claim_scan.py` (global Claude config exception path — see below).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — Dropbox-rooted (canonical root #1; live-probed schema reference for `prod_activity_log` writes by this handoff and any downstream impl).
- `~/.claude/hooks/stop_state_claim_scan.py` — global Claude config (exception path per HANDOFF_TEMPLATE_v2 §"Absolute-path filesystem discipline"; outside both canonical roots; permitted for global Claude config); 6,522 bytes; mtime 2026-05-08 17:46. Q1 Part 1's installed hook script — Cursor reads this for §3.1 ordering analysis.
- `~/.claude/settings.json` — global Claude config (exception path); 5,413 bytes; mtime 2026-05-08 16:01. Stop-array configuration — Cursor reads this for hook ordering + recursion-guard interaction.

---

## §0.1 — Why this v3 review exists

v2 spec's design surface received `AUTHORIZE_IMPLEMENTATION` from Cursor v1 review and was hardened in v2 with 3 v2-amendments. Cursor's batch audit on 2026-05-08 (covering Q1 Part 2 v2 + DS-23/24/25 v2 + DS-26 v2 + PERIODIC v2 review handoffs) found that those v2-amendments addressed the recurring 3 review-rigor findings BUT v2 itself was authored before HANDOFF_TEMPLATE_v2 §0.3 dual-canonical companion-path discipline shipped. The same template-level pattern applied to PERIODIC v2 (which spawned PERIODIC v3 earlier this session) applies here.

v3 closes:
1. **Companion-files block** — all paths absolute + canonical-root tagged (HANDOFF_TEMPLATE_v2 §0.3 mandate).
2. **HALT gates section** — explicit `## HALT gates` heading + autonomous-mode reminder verbatim + 5 enumerated gates (HANDOFF_TEMPLATE_v2 §"HALT gates" mandate).
3. **Hard rules section** — explicit Rule 35 / Rule 24 / DS-13 Layer 6 / DS-26 / DS-27 / DS-28 / DS-29 bullets.
4. **Final report section** — explicit final-report path + required sections enumeration.
5. **Probe A anti-drift fix** — pure anchor+snippet stale-cache check (NOT "first 20 lines" / "lines 1-20" framing). PERIODIC v3 was flagged PARTIAL on probe A by Cursor's audit earlier this session for residual fixed-line framing; this v3 avoids that drift.

The spec's design surface (cost model, recursion guard, trigger criteria, prompt template, banner mechanism, phase plan) is preserved verbatim; v3 review re-runs the full 6-task analysis with the same verdict semantics as v2, structurally compliant with HANDOFF_TEMPLATE_v2.

---

## §0.2 — What you DON'T need to do

- Do NOT have Cursor edit the v1 spec or v2 handoff. Verdict-only.
- Do NOT have Cursor implement Q1 Part 2. Implementation handoff is at `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_Q1_PART2_IMPLEMENTATION_20260508.md`; this handoff is review-only.
- Do NOT paste sensitive info; spec contains no credentials.
- Do NOT spawn a separate dual-Opus debate; the spec was authored via internalized dual-Opus pattern and that authoring outcome is background, not anchoring evidence.
- Do NOT re-review v1 + v2 review-handoff *form* for pedagogical compliance; v2's 3-amendment surface remains valid — v3 only restructures the wrapper to HANDOFF_TEMPLATE_v2 spec.

---

## HALT gates

**Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.

Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|-----------------|----------------|-------------|
| 1 | Has spec sha256 been confirmed match `02b134f76cf7ea618e90701d3dd13f68c33e9ab92bb9a19ab6ece5869d8154aa`? | `shasum -a 256` of spec absolute path | Hash matches verbatim | HALT — author drift; surface to Kim |
| 2 | Has spec title-line anchor + §0 Operating Mode header anchor been read into context? | Locate the spec's H1 line by header anchor (`# Q1 — Part 2: Conditional Opus Reviewer Subagent — Tech Spec v1`); capture the line range it occupies; quote verbatim. ALSO locate `## §0. Operating Mode` header; quote the line + the next 2-3 lines verbatim. | Reviewer emits both anchored quotes with current line ranges | HALT and report which anchor failed |
| 3 | Has spec §6 trigger criteria header been read into context? | Locate `## §6. Trigger criteria spec` (or `## §6` as fallback) header; quote the §6.1 path-allow-list opening line verbatim with current line range. | Reviewer emits header + allow-list opening verbatim | HALT and report which anchor failed |
| 4 | Has spec §10 recursion guard header been read into context? | Locate `## §10. Recursion guard` (or `## §10` as fallback) header; quote the 4-guard enumeration opening verbatim with current line range. | Reviewer emits header + 4-guard opening verbatim | HALT and report which anchor failed |
| 5 | Has spec §8.1 cost model row been read into context? | Locate `### 8.1.` (or `## §8.1` as fallback) cost-model header; quote the per-spawn cost claim (`~$0.18 typical; ~$0.86 worst case`) verbatim with current line range. | Reviewer emits header + cost claim verbatim | HALT and report which anchor failed |

If all 5 gates are MET, proceed to Step 0 preflight; if ANY gate fails, HALT and write a halt-report at `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v3_HALT_REPORT.md` enumerating which gate failed and why.

---

## Step 0 — Preflight (do FIRST, before any analysis) — anchored discipline (anti-drift fix)

Mandatory actions, emit inline:

1. **`ls -la` spec absolute path:**
   ```sh
   ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md"
   ```
   Expected: file exists, size 44,437 bytes, mtime 2026-05-08 08:43 PT (or later if minor in-place edits land).

2. **`shasum -a 256` spec:**
   ```sh
   shasum -a 256 "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md"
   ```
   Expected output: `02b134f76cf7ea618e90701d3dd13f68c33e9ab92bb9a19ab6ece5869d8154aa  <path>`. **HALT if hash differs — author drift detected; surface to Kim before proceeding.**

3. **Anchor+snippet stale-cache probe (anti-drift fix replacing fixed-line framing):**
   - **Anchor A1 — spec title line:** Locate the spec's H1 by header anchor `# Q1 — Part 2: Conditional Opus Reviewer Subagent — Tech Spec v1`; capture the line range it occupies (single-line H1; expect line 1); quote the H1 + the next non-blank line (status/authority block) verbatim. **Identity check is anchor-based (header text match), not line-number-based.**
   - **Anchor A2 — §0 Operating Mode header:** Locate `## §0. Operating Mode` header; capture the line range; quote the header line + the next 2-3 lines verbatim as stale-cache proof. Identity check via header text.
   - **Anchor A3 — §0.1 Scope changelog/boundary:** Locate `## §0.1. Scope (vs Q1 Part 1's scope; explicit boundary)` header; capture the line range; quote the header + the first bullet of the in-scope/out-of-scope distinction verbatim.

   Each anchor probe captures a line range as evidence, but the IDENTITY check is header-text-match (NOT "lines 1-20" / "first 20 lines" framing). This pattern passes anchored-citation discipline cleanly without the residual fixed-line drift that PERIODIC v3 was flagged on.

4. **Companion-file integrity (anchored — header/snippet ONLY):**
   - (a) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v2.md` — anchor `# Handoff v2 — Cursor Cross-Review of Q1 Part 2 Conditional Opus Reviewer Tech Spec` (first line); capture the v2 §0.1 Changelog table (3 rows: amendment #1 + #2 + #3) verbatim. Confirms v2 baseline.
   - (b) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — anchor `## v2 NEW — Companion path discipline` heading; capture the §0.3 mandate paragraph verbatim. Confirms template authority for v3 restructure.
   - (c) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` — anchor `# Handoff v6 — Cursor Cross-Review of Schema Vocab Migration Tech Spec v6` (first line); capture the `Companion files (absolute paths per HANDOFF_TEMPLATE_v2 §0.3 dual-canonical):` block. Confirms structural template precedent.
   - (d) `~/.claude/hooks/stop_state_claim_scan.py` — anchor `# Q1 Part 1` or comparable header in the script; capture the L4-equivalent regex check + tool_use suppression check verbatim. Confirms Q1 Part 1 wiring matches spec §2 claim.
   - (e) `~/.claude/settings.json` — anchor `"Stop"` JSON key; capture the Stop hook array verbatim. Confirms hook ordering claim in spec §3.1.

If preflight 1-3 fails, HALT and report. If 4 fails for any sub-item, document inline; if all 5 sub-items fail, HALT.

---

## Step 1 — Open the project in Cursor

Project root: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`. Open `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md`.

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md. It proposes a conditional Opus reviewer subagent that fires on a Stop hook when the most recent assistant turn (a) wrote to an "infrastructure" file (allow-list in §6) AND (b) the assistant text contains state-claim regex matches. The reviewer reads the assistant text and the written files, returns a structured JSON verdict, and the parent hook renders an inline stderr banner. Hard cap: 7 spawns/session. Worst-case cost claim: ~$6.02/session.

This is the v3 review handoff. Cursor v1 returned AUTHORIZE_IMPLEMENTATION on the spec design with 3 hardening points (anchored-section preflight, concise→full escalation, numeric AMEND_V2 thresholds). v2 incorporated those 3 fixes. v3 restructures the v2 review handoff to HANDOFF_TEMPLATE_v2 §0.3 dual-canonical compliance + adds a 6th analysis task (D — anti-fakery defense) reflecting the broader scrutiny appropriate for the FIRST subagent-spawn surface in MindfulNest hooks.

Apply your full independent scrutiny on the v1 spec. The v1 spec design is preserved verbatim across v1+v2+v3 review handoffs.

PREFLIGHT (do first, emit inline) — anchored discipline:
1. Confirm spec file exists; capture size + mtime + shasum.
   Expected sha256: 02b134f76cf7ea618e90701d3dd13f68c33e9ab92bb9a19ab6ece5869d8154aa
   HALT if mismatch — author drift.
2. Anchor+snippet stale-cache probe (NOT "first 20 lines"):
   (A1) Locate spec H1 by header anchor `# Q1 — Part 2: Conditional Opus Reviewer Subagent — Tech Spec v1`; capture the line range; quote H1 + next non-blank line verbatim.
   (A2) Locate `## §0. Operating Mode` header; capture line range; quote header + next 2-3 lines verbatim.
   (A3) Locate `## §0.1. Scope (vs Q1 Part 1's scope; explicit boundary)` header; capture line range; quote header + first in-scope/out-of-scope bullet verbatim.
3. Companion-file integrity (anchored header/snippet only):
   (a) `Production/docs/HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v2.md` — anchor `# Handoff v2`; quote v2 §0.1 Changelog table (3 rows) verbatim.
   (b) `Production/docs/HANDOFF_TEMPLATE_v2.md` — anchor `## v2 NEW — Companion path discipline`; quote the mandate paragraph verbatim.
   (c) `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` — anchor first line; quote Companion-files block.
   (d) `~/.claude/hooks/stop_state_claim_scan.py` — anchor regex/tool_use suppression block; quote verbatim.
   (e) `~/.claude/settings.json` — anchor `"Stop"` key; quote Stop hook array verbatim.
4. Spec anchor capture (deeper section probes per HALT gate enumeration):
   (i) Locate `## §6. Trigger criteria spec` header; quote §6.1 path-allow-list opening line verbatim with line range.
   (ii) Locate `## §10. Recursion guard` header; quote 4-guard enumeration opening verbatim with line range.
   (iii) Locate `### 8.1.` (or `## §8.1`) cost-model header; quote per-spawn cost claim ($0.18 typical / $0.86 worst-case) verbatim with line range.
If preflight 1-3 fails, HALT and report.

CONCISE→FULL ESCALATION RULE (mandatory verbatim per HANDOFF_TEMPLATE_v2):
> If any required section cannot be evidenced, full mode is mandatory.

Operational definition of "cannot be evidenced": could not read spec; could not reproduce an anchor (header/snippet match in actual file content); the §6 / §10 / §8.1 / §7 / §11 surface is missing or ambiguous; reviewer's evidence is "I think" or "probably" rather than a quoted citation; reviewer skipped a question to save tokens. Document WHICH area was under-evidenced in full-mode output.

ANALYSIS REQUIREMENTS (citation table format):
| # | Concern | Severity (CRITICAL/HIGH/MED/LOW) | Evidence (anchored citation: section header + snippet match, NOT line numbers alone) | Suggested mitigation | Blocker (Y/N) |

REQUIRED ANALYSIS TASKS (6 tasks; numeric thresholds on A + B + C + D):

A. TRIGGER CRITERIA REVIEW (§6 path allow-list + L0-L5 trigger model + §6.3 negative tests)
   Confirm:
   (a) §6.1 lists ~20 path patterns; enumerate every infrastructure-touching write op you can think of in a typical MindfulNest session and verify the list catches each. Identify any over-inclusion (paths that produce nuisance triggers).
   (b) §6.2 explicitly defers Directus writes (Bash POST to prod_locked_decisions / prod_reference_docs) to v2 amendment. Is that the right call, or is it a critical gap (LD writes are governance-class state changes; missing them lets fabricated-LD-content false claims slip)?
   (c) §6.3 negative-test list — sufficient? What false-trigger paths should be added (e.g., `Production/Modules/`, `.auto-memory/`, `Production/_previews/`)?
   (d) L0-L5 trigger model — conjunction is intentionally narrow. Walk through one realistic infrastructure session and count probable triggers. Is the spec's "1-5 triggers per heavy session" claim defensible?

   Edge cases to flag (independent scrutiny):
   - **Glob `**/Production/scripts/*.py` not in §6.1** — only 7 specific scripts are listed by name; any new infrastructure script added to `Production/scripts/` is silently exempt until §6.1 amended. Is the quarterly-review mitigation in §5 adequate, or does this need a broader glob with explicit exclusions?
   - **`Production/lib/` glob coverage** — §6.1 lists `Production/lib/directus.py` + `Production/lib/preflight.py`; what if a new `Production/lib/<X>.py` ships? Same exemption-by-default issue.
   - **Settings.local.json not in §6.1** — `~/.claude/settings.json` is listed but `~/.claude/settings.local.json` is also; is local-overlay settings.json a meaningful infrastructure surface?
   - **Symlink resolution** — if a path is a symlink (e.g., `~/.claude/skills/zero-error-qa/SKILL.md` → some Dropbox file), does fnmatch match the symlink path or the resolved target? Spec doesn't address; could cause false-negative.

   NUMERIC THRESHOLD: if Cursor identifies a trigger condition in §6 that would produce > 50% false-positive rate on a representative heavy infrastructure session (e.g., a path pattern that matches every routine doc edit), verdict MUST be AMEND_V2 on Task A. Auto-authorize is forbidden under that condition.

B. COST MODEL REVIEW (§8 derivation + 7-cap + per-trigger cost estimate; spec claims [INFERRED] on Opus 4.x rates)
   Confirm:
   (a) Spec §8.1 claims $0.18 typical / $0.86 worst-case per spawn using "Opus 4.7 reference rates" ([INFERRED] tag — implementation-time verification deferred). Independently look up Opus 4.7 / Opus 4 1M-context pricing and verify the math (input tokens × input rate + output tokens × output rate).
   (b) 7 spawns × $0.86 = $6.02 worst case. Is the 7-cap defensible? Is it too low (forces frequent overrides) or too high (cost slippage)?
   (c) §8.1 token budget table: input ~4,500 typical / ~17,000 worst, output ~1,500 typical / ~8,000 worst. Realistic, or are there missing components (system-prompt overhead per `claude -p` invocation, Read-tool-call overhead per file read, retry contingency on rate-limit)?
   (d) §8.4 override mechanism (`MN_Q1_PART2_NO_CAP=1`) — adequate? Or does it need a per-session limit (e.g., max-cap-bypass-per-day)?

   Edge cases to flag (independent scrutiny):
   - **1M-context pricing** — Claude Code's Opus 4.7 1M-context tier may have different rates than standard Opus. Spec doesn't specify which tier the reviewer subagent uses. Could under-estimate cost.
   - **Retry-on-rate-limit cost** — spec doesn't mention retries. Real-world `claude -p` invocations sometimes hit rate limits and retry; could 2x-3x the per-trigger cost.
   - **Multiple Read calls in reviewer** — §7 prompt allows the reviewer to Read the file(s) written. Each Read is itself a tool_use that incurs token cost. Spec budgets ~2,000 tokens for "File contents (Read calls)" but doesn't account for the Read tool_use schema overhead.

   NUMERIC THRESHOLD: if Cursor's independently-computed worst-case-per-spawn > $10 OR independently-computed typical-session > $3, verdict MUST be AMEND_V2 on Task B. Auto-authorize is forbidden under either condition. Show the computation: prompt-token overhead per spawn, output-token estimate, retry contingency, and Opus 4.x reference rates with citation.

C. RECURSION GUARD JOINT-FAILURE PROBABILITY (§10 four-layer guard model)
   Confirm:
   (a) §10.1 env var sentinel (`Q1_PART2_REVIEWER_ACTIVE=1`) — primary, hard guard. Walk through: env vars ARE inherited by child processes by default. Could a settings.local.json override strip it?
   (b) §10.2 output sentinel (`<!-- Q1_PART2_REVIEWER_OUTPUT_SENTINEL_DO_NOT_TRIGGER -->`) — defense-in-depth. Could the model omit the sentinel under token-cap pressure or refusal mode?
   (c) §10.3 SDK `--no-hooks` flag — tagged [INFERRED]; what if no such flag exists in Claude Code SDK?
   (d) §10.4 ps-chain depth limit (default 5) — what if the parent chain is obscured by `nohup` / `setsid` / `tmux` / job-control wrapping?
   (e) Test fixture F21 admits "all 4 guards bypassed" is residual risk. Acceptable?

   Edge cases to flag (independent scrutiny):
   - **Concurrent recursion** — if two infrastructure-write sessions fire simultaneously and both spawn reviewers, do their env-var sentinels conflict? (Likely no — each child process has its own env — but spec doesn't analyze.)
   - **macOS vs Linux ps semantics** — `ps -p $$ -o ppid=` may behave differently on macOS vs Linux (BSD vs GNU ps); §10.4 doesn't specify which.
   - **Crash recovery** — if the reviewer subagent crashes mid-spawn, does the env-var sentinel remain set in the parent's process tree? Could cause stale-state-block on next legitimate spawn.

   NUMERIC THRESHOLD: if Cursor's evidenced estimate of joint-failure probability across all 4 guards > 1-in-10,000 spawns under realistic load, OR if Cursor can construct a concrete scenario where ≥ 3 of 4 guards fail simultaneously, verdict MUST be AMEND_V2 on Task C. Auto-authorize is forbidden under either condition. Document probability estimate + scenarios considered.

D. ANTI-FAKERY DEFENSE (reviewer prompt §7 "evidence-quoting + Rule 24 tags" + verdict-format JSON output)
   Confirm:
   (a) §7 prompt mandates the reviewer use Rule 24 tags (`[CONFIRMED from <file>:<line>]` / `[DISCONFIRMED — file says X; claim says Y]` / `[INSUFFICIENT EVIDENCE — file does not contain affirming or contradicting text]`). Adequate to prevent the reviewer from fabricating evidence?
   (b) §7 mandates strict JSON output to stdout. What's the failure mode if the reviewer returns prose / refuses / hits token cap mid-output? Spec F15 covers "malformed reviewer JSON" → fall back to "[Q1-PART2] reviewer returned malformed JSON; raw output: <first 500 chars>"; exits 0. Adequate?
   (c) §7 read-only constraint (no Bash, no Write, no Directus calls). Adequate to prevent the reviewer from being prompt-injected into making side-effect writes?

   Edge cases to flag (independent scrutiny):
   - **Fabricated quoted line** — the reviewer might emit `[CONFIRMED from settings.json:42]` with a verbatim "quote" that isn't actually in the file. The spec marks this as "model-quality concern, not Part 2 design flaw" (§4.6). Is that classification correct, or does it warrant an additional verification layer (e.g., the parent hook re-reads the cited file:line and compares)?
   - **Adversarial assistant text** — what if the assistant text includes Markdown/HTML that, when interpolated into the reviewer prompt, breaks out of the prompt template (escapes the heredoc, or includes a closing `EOF`)? Spec doesn't analyze prompt-injection vectors against the §7 heredoc.
   - **Sentinel omission under token cap** — what if the reviewer hits token cap before emitting the sentinel? §10.2's L5 check would then NOT short-circuit — but L0 (env var) would still hold. Is L0 actually inherited reliably?

   NUMERIC THRESHOLD: if a fabricated bypass succeeds with ≤ 5 lines of fake reviewer output AND no detectable internal contradiction (e.g., a reviewer that fabricates `[CONFIRMED from <file>:<line>]` with a false quoted line that happens to match no real file content), verdict MUST be AMEND_V2 on Task D. Auto-authorize is forbidden under that condition.

E. HARD CAP CALIBRATION (7 spawns/session — is this the right number?)
   Confirm:
   (a) §3.3 / §8.2 specify hard cap at 7. Soft alert at 5. Is 7 the right number?
   (b) §12 open decision #3 acknowledges the cap is calibration-pending. Is "calibrate after first session of real usage" adequate, or should the cap start lower (e.g., 5) and ratchet up?
   (c) Per-session hard cap interacts with the override mechanism (MN_Q1_PART2_NO_CAP=1). Is the override discoverable? Is there friction (e.g., explicit Kim-approved row required) before the override fires?
   (d) §3.4 banner shows session counter `(spawn N/7 used this session)`. Adequate visibility?

   Edge cases to flag (independent scrutiny):
   - **Daily multi-session aggregation** — Kim might run 3 heavy sessions in one day, each hitting the 7-cap. That's 21 spawns × $0.86 = $18.06 worst-case daily. Is daily aggregation tracked anywhere?
   - **Cap-hit during deep work** — if Kim is mid-flow on Phase F refactor and hits cap, the spawn-9 silence may mask a real false claim. Is the `MN_Q1_PART2_NO_CAP=1` override discoverable enough to recover gracefully?

   NUMERIC THRESHOLD: descriptive evaluation. If Cursor identifies a cap-related risk that would produce > $25 worst-case daily under realistic Kim workflow, verdict MUST be AMEND_V2 on Task E.

F. SEQUENCING REVIEW (§11 Phases A-G — dependency graph + ordering risk)
   Confirm:
   (a) Build a dependency graph: A spawn-mechanism-validation produces prerequisites for B hook-script-scaffolding produces prerequisites for C settings.json-wiring produces prerequisites for D prompt-template-and-spawn-invocation produces prerequisites for E cost-monitor-and-session-log produces prerequisites for F recursion-guard-validation produces prerequisites for G kill-switch. Is the graph correct? Is any phase mis-ordered?
   (b) Identify any phase where reversing the order creates risk.
   (c) Identify any phases that could parallelize without breaking dependencies.

   Edge cases to flag (independent scrutiny):
   - **Phase F (recursion-guard-validation) AFTER Phase D (spawn-invocation)** — is there a window where D's spawn could fire during F's validation? Should F precede D for safety?
   - **Phase B dry-run mode** — Phase B emits "would spawn" lines without actually spawning. Is this adequate isolation?
   - **Phase G kill-switch** — is the kill-switch in place BEFORE Phase D's first real spawn? §15 rollback procedure exists; does Phase G mandate testing the rollback BEFORE the first production spawn?

   NUMERIC THRESHOLD: descriptive evaluation. If Cursor identifies a phase ordering that would expose Kim to production-level risk before kill-switch is verified working, verdict MUST be AMEND_V2 on Task F.

VERDICT FORMAT (mandatory, pick exactly ONE):
- AUTHORIZE_IMPLEMENTATION — spec is sound; Phase A may proceed per implementation handoff at `Production/docs/HANDOFF_Q1_PART2_IMPLEMENTATION_20260508.md`.
- AUTHORIZE_PHASE_0_ONLY — spec is sound BUT cost-model verification cannot be completed by Cursor from its environment (Opus 4.x rates not independently confirmable); authorize Phase A (spawn-mechanism validation in isolation) only, with risk acceptance for Phases B-G review post-Phase A artifacts.
- AMEND_V2 — spec has a defect on one or more of the 6 tasks; specify the defect AND the required v2 fix in concrete numeric terms.
- PAUSE_FOR_REDEBATE — spec has a fundamental design issue requiring fresh dual-Opus or expanded review.

Required output:
1. Preflight evidence (sha256 + 3 anchored stale-cache probes A1-A3 + 5 anchored companion-file quotes + 3 spec deeper-section anchor captures).
2. Analysis table (per task A, B, C, D, E, F) with severity, evidence (anchored citation), mitigation, blocker Y/N.
3. Recursion-guard joint-failure scenario walkthrough (per Task C numeric threshold).
4. Cost-model verification table (per Task B numeric threshold).
5. Phase dependency graph (per Task F).
6. Verdict (one of the four above).
7. Limitations + cross-skill drift if any.
```

---

## Step 3 — After Cursor responds

Save Cursor's verbatim response to `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v3.md`.

Verdict-driven next steps:

- **`AUTHORIZE_IMPLEMENTATION`** → dispatch implementation via terminal CLI per `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_Q1_PART2_IMPLEMENTATION_20260508.md`. Phases A-G run sequentially with per-phase gates.
- **`AUTHORIZE_PHASE_0_ONLY`** → dispatch Phase A (spawn-mechanism-validation in isolation) only, with risk acceptance; Phases B-G follow after Phase A artifact review.
- **`AMEND_V2`** → author `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v2.md` addressing the blocker(s); preserve v1 spec as historical baseline; re-run THIS handoff against v2 spec (rename + bump version refs + re-anchor).
- **`PAUSE_FOR_REDEBATE`** → halt; bring findings back to Claude Code; spawn fresh dual-Opus debate; do NOT proceed to implementation.

---

## Hard rules

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST (applies to handoff author logging this handoff to `prod_activity_log`; applies to Cursor reviewer if they touch Directus during analysis — they should not).
- **Multipass:** re-Read v1 spec after this handoff is authored (handoff author discipline; Cursor reviewer also re-reads if a HALT gate fires).
- **Rule 24:** confidence tags throughout (CONFIRMED / INFERRED / GUESSED).
- **DS-13 Layer 6:** input variation (read v2 review handoff as template + v1 spec) → output variation (this handoff differs structurally to comply with HANDOFF_TEMPLATE_v2 §0.3; design-surface analysis preserved).
- **DS-19** (Standing Escape Hatches) and **DS-26** (Gate-Check Discipline) are always active — fire on any of their trigger conditions. Autonomous mode does not bypass HALT gates.
- **DS-26 explicit:** "Autonomous mode does not bypass HALT gates. If a HALT gate fires mid-execution (e.g., gate evidence found inconsistent), STOP and surface."
- **DS-27 explicit (HARD rule, dual-canonical):** All filesystem-touching commands MUST use absolute paths anchored to one of the two canonical roots: (1) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (primary — Mindfulnest project) OR (2) `/Users/kimberlysmith/Projects/` (secondary — tooling repos, MindfulNest RN app, related repos). Do NOT operate inside `.claude/worktrees/` subdirectories under either root unless explicitly authorized. Verify paths with `ls -la <absolute-path>` before edits. Paths outside both canonical roots (e.g., `~/.claude/`) require explicit authorization rationale stated inline (this handoff's authorization rationale: `~/.claude/hooks/` and `~/.claude/settings.json` are global Claude config, exception per HANDOFF_TEMPLATE_v2).
- **DS-28 dependency-order:** preflight steps 1-4 verified before Step 1; Step 1 before Step 2; Step 2 before Step 3.
- **DS-29 source tagging:** every claim in this handoff and Cursor's response MUST be tagged as (my probe) / (agent claim) / (unverified). The reviewer's analysis section quotes EVERY citation as anchored section/snippet match.
- **JSON-column gotcha:** the activity-log POST below uses `details` as a dict (live `prod_activity_log.details` IS a JSON column — distinct from `prod_blockers` which has NO `details` field).
- **LD-597 anti-confusion (NO `task_description`):** activity-log POST payload MUST NOT include a `task_description` key. The schema for `prod_activity_log` does NOT define `task_description`; passing it triggers Directus 400 errors.
- **Companion path discipline (HANDOFF_TEMPLATE_v2 §0.3):** every companion file in this handoff is listed with absolute path + canonical-root tag; verified via `ls -la` at authoring time.
- **Anchored citation:** every preflight evidence requirement uses anchored section/header + snippet match, not absolute line number alone. The probe A1/A2/A3 design uses pure anchor+snippet identity (NOT "first 20 lines" / "lines 1-20" framing) per the anti-drift fix.
- **Concise→full escalation (mandatory):** "If any required section cannot be evidenced, full mode is mandatory." (Verbatim in Step 2 prompt.)
- **Numeric AMEND_V2 thresholds (mandatory):** Tasks A, B, C, D have explicit numeric triggers; Tasks E, F are descriptive evaluations with their own thresholds.

---

## Final report — required structure

Path: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/CURSOR_REVIEW_Q1_PART2_SPEC_REPORT_20260508_v3.md`

Required sections:

1. **HALT gate scan results** — 5 gates (sha256 match, spec-title-anchor, §6 anchor, §10 anchor, §8.1 anchor) with per-gate state at session start (MET / NOT MET / N/A) with anchored evidence cited. If any gate was NOT MET, the report is a halt-report and the rest of the sections are N/A.
2. **Cursor verdict verbatim** (one of the four verdict options).
3. **Per-task summary** — A, B, C, D, E, F, each with verdict + anchored evidence + numeric-threshold result where applicable.
4. **Recursion-guard joint-failure scenario walkthrough** (per Task C).
5. **Cost-model verification table** (per Task B).
6. **Phase dependency graph** (per Task F).
7. **Confidence tags per Rule 24.**
8. **Self-classification** — REVIEW (v3-scope; structural-compliance refresh of v2; spec-design analysis re-runs at full breadth).
9. **Limitations** — what wasn't covered (Opus 4.x 1M-context pricing if not independently verifiable; live `claude -p --output-format json` schema if not testable from Cursor environment).
10. **Cross-skill drift** — does the v3 handoff structure require parallel updates to weekly_preflight_audit.py, zero-error-qa SKILL.md DS-29, or HANDOFF_TEMPLATE_v2 itself?

---

## Cross-references

- **Q1 Part 1 spec:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/Q1_PART1_STOP_HOOK_SPEC_v1.md`
- **Q1 Part 1 hook implementation:** `~/.claude/hooks/stop_state_claim_scan.py`
- **Q1 Part 1 LD:** `Q1_PART1_STOP_HOOK_INSTALLED_V1` (LD 579) [INFERRED — live Directus probe failed from current environment; LD id confirmed via session memory + spec §17 reference]
- **Q1 Part 2 LDs (existing):** LD-589 + LD-594 (cited in spec §17; live probe failed) [INFERRED]
- **Q1 Part 2 implementation handoff:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_Q1_PART2_IMPLEMENTATION_20260508.md`
- **HANDOFF_TEMPLATE_v2:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — this handoff conforms.
- **Schema-ref doc:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — `prod_activity_log` schema authority for the v3 LD + activity-log POST below.
- **Structural template precedent:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` — v3 mirrors its compliance pattern.
- **PERIODIC v3 anti-drift precedent:** Cursor's audit on PERIODIC v3 (this session, earlier) flagged probe A PARTIAL for residual fixed-line framing. v3 here uses pure anchor+snippet stale-cache check to avoid that drift.
- **DS-22 (state-claim mechanical gate):** `.claude/skills/zero-error-qa/SKILL.md` lines 213-242
- **Step 2.5b (canonical regex):** `.claude/skills/mn-context/SKILL.md` lines 291-319
- **Override pattern reference (DS-20/21/22):** `.claude/skills/zero-error-qa/SKILL.md` lines 172-242
- **MindfulNest greenfield CI/CD lock memory:** `project_main_app_cicd_greenfield_lock.md` (confirms Q1 Part 2 ≠ CI/CD)

---

## §12 — Change log

- **v1** — 2026-05-08 — initial Cursor cross-review handoff for v1 spec. Author: Claude Opus 4.7 (1M context), session `gallant-bouman-804b4f`. Cursor returned AUTHORIZE_IMPLEMENTATION with 3 hardening points.
- **v2** — 2026-05-08 — incorporated Cursor's 3 hardening points (anchored-section preflight, concise→full escalation, numeric AMEND_V2 thresholds). Same session.
- **v3** — 2026-05-08 — restructures v2 to HANDOFF_TEMPLATE_v2 §0.3 dual-canonical compliance: (D) absolute companion paths, (E) canonical-root tag format, (F) HALT gates section + autonomous-mode reminder verbatim, (G) Hard rules + Final report sections per template mandate. Probe A redesigned as pure anchor+snippet stale-cache check (NOT "first 20 lines" / "lines 1-20" framing) per PERIODIC v3 anti-drift precedent. Analysis tasks expanded from 4 (v2: A recursion guard, B cost model, C trigger criteria, D-G prompt/output/interaction/sequencing) to 6 (v3: A trigger criteria, B cost model, C recursion guard, D anti-fakery, E hard cap, F sequencing) with explicit numeric thresholds on A + B + C + D and descriptive thresholds on E + F. Author: Claude Opus 4.7 (1M context), session `gallant-bouman-804b4f`, same day.
- Future revisions: append to versioning table; do not rewrite v1 or v2 in place.

---

*End of HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v3.md.*
