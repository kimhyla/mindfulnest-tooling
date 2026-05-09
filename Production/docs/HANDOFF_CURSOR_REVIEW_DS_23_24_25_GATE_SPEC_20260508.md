# Handoff — Cursor Cross-Review of DS-23/24/25 Mechanical Gate Tech Spec v1

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session, 2026-05-08
**Spec under review:** `Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md`
**Companion files (read for context only):**
- `.claude/skills/zero-error-qa/SKILL.md` (~107.8 KB; DS-23 lines 244–272, DS-24 274–302, DS-25 304–336, DS-22 213–242, Phase 7.5 Step 6/7 lines 1313–1335)
- `.claude/skills/mn-context/SKILL.md` (Step 2.5 + 2.5b mechanical-gate template, lines 251–321)
- `Production/scripts/git_hooks/pre-commit` (161 lines; tooling-repo pre-commit, source for §7.1.1)
- `mindfulnest-tooling/.github/workflows/codeql.yml` (52 lines)
- `mindfulnest-tooling/.github/workflows/ai_review.yml` (71 lines)
- `mindfulnest-tooling/.github/workflows/smoke.yml` (30 lines)
- `MindfulNest/.github/workflows/legacy-file-gate.yml` (78 lines; single-job blocking-gate pattern reference)

---

## What this handoff requests

The spec proposes converting DS-23 (post-fix pattern sweep), DS-24 (audit copy source before copy), and DS-25 (adjacent risk sweep after CodeQL triage) from **discipline-only rules** into **mechanical CI/local-hook gates** that BLOCK commits and PR merges when violated. The three rules currently exist in `.claude/skills/zero-error-qa/SKILL.md` with `ENFORCEMENT IS DISCIPLINE-ONLY for now` markers; the spec retires those markers and lands the mechanical enforcement.

Your job: independently verify the spec's design decisions, look for new-blocker concerns, and emit a STRICT gate verdict.

This handoff uses **v2-hardened format** — concise mode authorized when no blockers found; full mode required when any blocker found. Default to full mode if uncertain.

---

## Step 0 — Preflight (do FIRST, before any analysis)

Run these checks and emit results inline. **HALT and report if any preflight fails.**

1. **Spec exists:** `ls -la "Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md"` — capture size + mtime.
2. **Spec hash:** `shasum "Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md"` — capture digest.
3. **Companion file existence + size:** for each of the 7 companion files listed in the header, run `ls -la <path>` and capture size + mtime. If any is missing, HALT.
4. **First-N-lines quote (proof of fresh read):**
   - Quote the spec's `§0 Operating Mode Declaration` paragraph verbatim (the bullet list under `## §0`).
   - Quote `.claude/skills/zero-error-qa/SKILL.md` line 268 verbatim (the PR #8 CRIT-1 example failure mode line).
   - Quote `Production/scripts/git_hooks/pre-commit` lines 32-35 verbatim (the existing override pattern).

If any quote cannot be reproduced verbatim, HALT and report which file failed the read.

---

## Step 1 — Open the project in Cursor

`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`

Open `Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md` in the editor. Open Cursor Composer or chat.

Recommended additional editor tabs (read-only context):
- `.claude/skills/zero-error-qa/SKILL.md`
- `.claude/skills/mn-context/SKILL.md`
- `Production/scripts/git_hooks/pre-commit`
- `mindfulnest-tooling/.github/workflows/codeql.yml`
- `MindfulNest/.github/workflows/legacy-file-gate.yml`

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md. It proposes converting DS-23 (post-fix pattern sweep), DS-24 (audit copy source), and DS-25 (adjacent risk sweep after CodeQL triage) from DISCIPLINE-ONLY rules to MECHANICAL gates blocking commits + PR merges.

The spec uses dual-Opus advocate/counter pattern (§4) with a clean resolution (§4.5). It mirrors the DS-22 + Step 2.5b mechanical-gate pattern that already lives in mn-context/SKILL.md. The three rules originate from PR #8's CRIT-1, CRIT-2, CRIT-3 incidents.

Your task: verify the design decisions are sound and the spec doesn't introduce new blockers.

CONCISE MODE AUTHORIZED:
If you find ZERO blocker concerns:
- Preflight evidence (5 lines max)
- 1 paragraph confirming the §3 design + §4 resolution + §11 risk model are sound, no new blockers
- Verdict: AUTHORIZE_IMPLEMENTATION
- (Optional) ≤3 LOW-severity nice-to-haves in brief bullets

FULL MODE REQUIRED IF ANY BLOCKER FOUND:
- Citation tables with severity (CRITICAL/HIGH/MED/LOW) + blocker tag (Y/N)
- Per-section analysis: which sections of the spec contain the blocker?
- New-blocker search (Q-NEW-1, Q-NEW-2, Q-NEW-3 below)
- Strict gate verdict: AMEND_V2 or PAUSE_FOR_REDEBATE

Default to full mode if uncertain.

PREFLIGHT (do first, emit inline regardless of mode):
1. Confirm `Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md` exists; capture size + mtime.
2. shasum the spec; capture digest.
3. Confirm 7 companion files exist (listed in handoff header); capture size + mtime each.
4. Quote spec §0 Operating Mode bullets verbatim.
5. Quote zero-error-qa SKILL.md line 268 verbatim.
6. Quote tooling pre-commit lines 32-35 verbatim.
If any preflight fails, HALT and report.

PER-SECTION VERIFICATION (cover at minimum):

V1 (HIGH — design coherence):
- §3.1 gate-location table: do the three rule placements (DS-23/24 dual-surface, DS-25 CI-only) defend against the failure modes described in §1.1?
- §3.2 check semantics summary: are the per-rule pass/fail conditions internally consistent with §6 acceptance criteria + §7 per-rule semantics?
- §3.3 FP defense argument: is the "marker presence vs content quality" split-of-concerns load-bearing? Could the gate fail safely when the marker is present but the content is fabricated?

V2 (HIGH — debate quality):
- §4.1 Advocate's strongest evidence: PR #8's CRIT-1 was authored AND shipped under cover of a partial fix. Does the proposed mechanical gate ACTUALLY prevent that failure mode, or is it cosmetic?
- §4.2 Counter's strongest critique: bypass-mechanism abuse risk (#4). Does §11.2's mitigation chain (audit row mandatory + weekly threshold + 30-day FP audit + sunset clause) credibly address it?
- §4.3 Advocate's response on DS-24 handler-shape regex being broad: is the proposed override-comment pattern (`# DS-24: authored from scratch`) workable, or does it just push the false-positive cost onto every new-handler commit?
- §4.5 Resolution: did the debate resolve cleanly, or are there residual disagreements masquerading as agreement?

V3 (HIGH — implementation phase ordering):
- §8 Phase A→G ordering: does pre-commit-then-CI-then-bypass-wiring prevent partial-deploy states (e.g., pre-commit gates fire but no audit-row writer exists yet)?
- §8 Phase F SKILL.md amend: should the SKILL amend ship BEFORE or AFTER the gates are live? Spec proposes AFTER (Phase F follows A-D). Is that the right order?
- §8 Phase G 30-day audit: is the calendar-task lock at G7 actually wired to fire, or is "30 days from now" the same anti-pattern as `feedback_time_estimates.md` warns against?

V4 (MED — semantics specificity):
- §7.1.1 sentinel-file approach (`.ds23_sweep`): is this discoverable to a fresh-clone developer? Does §11.3's mitigation chain (hook header + RUNBOOK + failing-gate output) cover it?
- §7.1.2 marker regex `^Swept .+ for `<PATTERN>`:` — is the regex robust to whitespace variations, multi-line block parsing, etc.?
- §7.2.1 handler-shape regex (def _handle_, function handle, const handle): is this complete coverage for tooling-repo? What about Express-style middleware functions, async generators, decorator-wrapped handlers?
- §7.3.1 workflow_run race condition: does the proposed `workflow_run` after CodeQL + duplicate `pull_request` trigger actually resolve all timing concerns? Could a force-push between CodeQL completion and DS-25 fire produce a stale alert list?

V5 (MED — bypass / governance):
- §11.2 weekly preflight threshold (>3 bypasses/7-day window OR rationale <50 chars): are these thresholds calibrated, or guess-work? Is there prior-art bypass data to anchor against?
- §11.5 schema-drift risk: is G5's verification (query Directus `/fields`) enough, or does it need a synthetic-write probe to confirm enum acceptance?
- §10 G1-G10 pre-implementation gates: are all 10 gates actually orthogonal, or are some redundant?

V6 (LOW — completeness):
- §13 testing plan: do the 6 synthetic PRs cover both happy-path AND failure-path for all 3 rules? Are any gate-bypass-abuse paths tested (ADV1-ADV4 in §13.3)?
- §14 reference index: is anything cited in the spec body that does NOT appear in §14? Or anything in §14 not cited in the body?
- §15 confidence sweep: are all `[ASSUMED]` items (FP-rate estimates) clearly bounded by Phase G's empirical check?

NEW-BLOCKER SEARCH:
- Q-NEW-1: Did this spec introduce any NEW blocker (HIGH or CRITICAL) — i.e., a design decision that would actively damage the codebase or the doctrinal stack? Examples to look for: gate that blocks legitimate workflows; bypass mechanism that creates a side-channel attack; phase ordering that produces unmergeable states.
- Q-NEW-2: Are any of the spec's amendments/decisions superficial — i.e., they LOOK like they address the dual-Opus debate concerns but actually don't change behavior? Look at §4.5 vs §3 + §7.
- Q-NEW-3: Did the spec break anything from existing state — e.g., did it propose changes to `Production/scripts/git_hooks/pre-commit` that would conflict with the existing watch-list gate (lines 104-160)? Did it propose a CI workflow trigger that conflicts with the existing CodeQL or AI Review workflows?

REQUIRED OUTPUT (concise OR full mode):

Concise mode output:
1. Preflight evidence (5 lines max)
2. 1 paragraph: "spec §3+§4+§11 sound; no new blockers identified. Specifically [brief recap of what was checked]."
3. Verdict: AUTHORIZE_IMPLEMENTATION
4. (Optional) ≤3 LOW-severity nice-to-haves in bullets

Full mode output:
1. Preflight evidence
2. Per-section table (mandatory citation format with severity + blocker tag): one row per V1-V6 verification, verdict on whether the section is sound (SOUND / PARTIAL / NOT_SOUND).
3. New-blocker analysis (Q-NEW-1, Q-NEW-2, Q-NEW-3)
4. Final gate verdict in STRICT form (pick exactly one):
   AUTHORIZE_IMPLEMENTATION: spec §3+§4+§11 are sound, no new blockers; advance to implementation handoff.
   AMEND_V2: spec has remaining issues; list specific blockers with severity + spec §refs.
   PAUSE_FOR_REDEBATE: fundamental design issues; recommend fresh dual-Opus.
5. If AMEND_V2: list specific blocker concerns with severity + citations.
```

---

## Step 3 — After Cursor responds

If verdict is **AUTHORIZE_IMPLEMENTATION**:
- Author the implementation handoff at `Production/docs/HANDOFF_DS_23_24_25_GATE_IMPLEMENTATION_<date>.md`.
- The implementation handoff mirrors §8 Phase A-G ordering with G1-G10 pre-implementation gates as HALT preconditions.
- Spawn a Terminal CLI session.

If verdict is **AMEND_V2**:
- Bring the blocker list back to Claude Code.
- Author `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md` addressing each blocker (mirror v1 numbering, add §0.1 changelog).
- Re-run this Cursor cross-review on v2.

If verdict is **PAUSE_FOR_REDEBATE**:
- Bring findings back to Claude Code.
- Spawn fresh dual-Opus debate.
- Do NOT advance to implementation.

---

## Specific questions Kim wants Cursor to answer regardless of verdict

1. **DS-24 false-positive rate.** The spec estimates 30-50% FP for DS-24 because the handler-shape regex is broad. Is that acceptable? Should DS-24 be deferred until AST-similarity is implemented (per §5.2 OD)? Or is the override-comment pattern enough?
2. **Sentinel files (`.ds23_sweep`, `.ds24_audit`).** Is this the right pattern, or would `prepare-commit-msg` injection be cleaner despite §7.1.1's stated rejections (squash-merges, `-m` mode)?
3. **DS-25 race condition.** Is `workflow_run` after CodeQL + duplicate `pull_request` trigger sufficient, or could a force-push between CodeQL completion + DS-25 fire produce a stale alert list?
4. **Bypass thresholds (§11.2).** Are >3 bypasses/7-day OR rationale <50 chars sane numbers, or arbitrary?
5. **Phase ordering (§8).** Should Phase F (SKILL.md amend) ship before A-D (gate code), or after? Spec proposes after.

---

## What you DON'T need to do

- Don't have Cursor edit the spec.
- Don't have Cursor implement anything.
- Don't re-litigate the underlying DS-23/24/25 rule definitions — those are locked per LD 580 and are out of scope per §0.1 #3.
- Don't review DS-26 mechanical gating (different blocker row, different spec eventually).

---

## Why this handoff is structured this way

This handoff descends from `HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_v2_20260508.md` (v2-hardened format). It includes:

- **Mandatory preflight** (Step 0) with size + shasum + first-N-lines quote — proof-of-fresh-read prevents Cursor from reviewing a cached or stale view of the spec.
- **Mandatory citation format** with severity (CRITICAL/HIGH/MED/LOW) + blocker tag (Y/N) — same standard as the v2 PATCH_FORWARD handoff.
- **Strict gate verdict** (AUTHORIZE_IMPLEMENTATION / AMEND_V2 / PAUSE_FOR_REDEBATE) — no ambiguous "looks fine" responses; one of three exact tokens.
- **Concise mode authorized for no-blocker reviews** (per Cursor LOW #6 from the prior PATCH_FORWARD round) — reduces reviewer overhead when nothing's wrong.
- **Per-section verification (V1-V6)** with explicit dimensions to check — design coherence, debate quality, phase ordering, semantics specificity, bypass/governance, completeness.
- **New-blocker search (Q-NEW-1/2/3)** — guards against the spec introducing fresh issues while addressing existing ones.

Full mode remains required when blockers ARE found. This preserves rigor where it matters; reduces friction where it doesn't.

---

*End of HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508.md.*
