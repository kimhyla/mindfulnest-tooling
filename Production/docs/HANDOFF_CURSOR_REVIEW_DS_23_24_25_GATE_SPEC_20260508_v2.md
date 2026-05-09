# Handoff v2 — Cursor Cross-Review of DS-23/24/25 Mechanical Gate Tech Spec

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session, 2026-05-08
**Spec under review:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md`
**Companion files (read for context only) — ABSOLUTE PATHS per DS-27 v2 dual-canonical (refactored 2026-05-08; AMEND_V2 path fix applied 2026-05-08 §0.2):**
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md` (~118.7 KB; DS-23 lines 244–272, DS-24 274–302, DS-25 304–336, DS-22 213–242, Phase 7.5 Step 6/7 lines 1313–1335) — Dropbox-rooted (canonical root #1)
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/mn-context/SKILL.md` (Step 2.5 + 2.5b mechanical-gate template, lines 251–321) — Dropbox-rooted (canonical root #1)
- `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit` (160 lines; tooling-repo pre-commit, source for §7.1.1) — Projects-rooted (canonical root #2; tooling repo)
- `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml` (52 lines) — Projects-rooted (canonical root #2; tooling repo)
- `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/ai_review.yml` (71 lines) — Projects-rooted (canonical root #2; tooling repo)
- `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/smoke.yml` (30 lines) — Projects-rooted (canonical root #2; tooling repo)
- `/Users/kimberlysmith/Projects/MindfulNest/.github/workflows/legacy-file-gate.yml` (78 lines; single-job blocking-gate pattern reference) — Projects-rooted (canonical root #2; RN app)

**Path note (v2.1 amendment, 2026-05-08):** Original v2 listed companion paths as Dropbox-relative (e.g., `mindfulnest-tooling/.github/workflows/codeql.yml`). Cursor's AMEND_V2 verdict surfaced that those paths only resolve under `/Users/kimberlysmith/Projects/`, not under the Dropbox root — preflight HALTed on "missing files" because the resolver was checking the wrong canonical root. The list above is now anchored to the correct canonical root for each file (Dropbox root for `.claude/skills/...`, Projects root for the tooling repo + RN app workflows + the pre-commit hook). Authority: DS-27 v2 dual-canonical refactor (2026-05-08) + LD #584 amendment (2026-05-08) + HANDOFF_TEMPLATE_v2.md "Companion path discipline" section.

This handoff is **v2** — it incorporates 3 Cursor amendments on top of v1 (preserved as historical baseline at `HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508.md`). v1's per-section verification structure (V1-V6), new-blocker search (Q-NEW-1/2/3), strict gate verdict, and dual-mode (concise/full) carry forward unchanged.

A v2.1 amendment (in-place, 2026-05-08) addresses Cursor's AMEND_V2 verdict on companion-path resolution; see §0.2 below.

---

## §0.1 v2 Changelog — Cursor amendments applied

Cursor's review of v1 returned **AUTHORIZE_IMPLEMENTATION with minor hardening** and surfaced 3 findings. Each is addressed below; v1 sections are preserved verbatim except where a finding required a targeted insert/replace.

| # | Cursor finding | Severity | v2 section addressing it |
|---|----------------|----------|--------------------------|
| 1 | Brittle line-number quotes: requiring exact line N can fail on benign line shifts | MED | Step 0 §4 (anchored section/header + snippet match replaces exact line-number quote) |
| 2 | Concise-mode escalation: concise allowed when no blockers, but no rule for partial-evidence cases | MED | Step 2 prompt block (escalation rule: any required area not fully evidenced ⇒ force full mode) |
| 3 | DS-24 FP-rate threshold: asks 30-50% acceptable, no decision trigger tied to verdict | MED | Specific question §1 + Step 2 prompt (gate trigger: estimated FP > 50% with override burden > 8 hr/week ⇒ AMEND_V2) |

---

## §0.2 v2.1 Changelog — Cursor AMEND_V2 path fix applied (2026-05-08)

After v2 shipped (with anchored-citation + concise-escalation + DS-24 FP-rate amendments above), Cursor's review of v2 returned **AMEND_V2** verdict citing dual-canonical-paths confusion: v2 listed companion files as Dropbox-relative (e.g., `mindfulnest-tooling/.github/workflows/codeql.yml`), but those paths only resolve under `/Users/kimberlysmith/Projects/mindfulnest-tooling/`, not under the Dropbox root. Step 0 preflight HALTed on "files missing" because the resolver was checking the wrong canonical root.

| # | Cursor finding | Severity | v2.1 section addressing it |
|---|----------------|----------|----------------------------|
| 4 | Dual-canonical-paths confusion: v2 companion paths assumed single Dropbox root, but tooling repo + RN app live under `/Users/kimberlysmith/Projects/` (per DS-27 v2 dual-canonical refactor) | HIGH | Header companion-files block (absolute paths per canonical root) + Step 0 preflight #3 (absolute-path probe per file) + Step 2 prompt PREFLIGHT block (absolute paths in companion list) |

**v2.1 in-place amendment, not v2.1 file:** the historical-baseline preservation rule applies to v1 (preserved separately at `HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508.md`); v2 is amended in-place because the path bug renders the un-amended v2 un-runnable (preflight always HALTs). The §0.1 changelog above remains the v2 amendment record; this §0.2 documents the v2.1 surgical path fix.

**Verified path resolutions (each via `ls -la <absolute-path>` 2026-05-08):**

| Companion file | Canonical root | Verified location |
|----------------|----------------|-------------------|
| zero-error-qa SKILL.md | Dropbox (root #1) | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md` (118754 bytes) |
| mn-context SKILL.md | Dropbox (root #1) | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/mn-context/SKILL.md` (28963 bytes) |
| pre-commit hook | Projects (root #2) | `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit` (7562 bytes, 160 lines) |
| codeql.yml | Projects (root #2) | `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml` (1374 bytes) |
| ai_review.yml | Projects (root #2) | `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/ai_review.yml` (2236 bytes) |
| smoke.yml | Projects (root #2) | `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/smoke.yml` (822 bytes) |
| legacy-file-gate.yml | Projects (root #2) | `/Users/kimberlysmith/Projects/MindfulNest/.github/workflows/legacy-file-gate.yml` (3128 bytes) |

The pre-commit hook lives at `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit` (the tooling repo contains its own `Production/` subdirectory; do NOT confuse with the Mindfulnest Dropbox `Production/` tree). v2's claim "Production/scripts/git_hooks/pre-commit (161 lines)" was off-by-one and root-misaligned: the actual file is 160 lines and lives in the tooling repo, not the Dropbox tree.

**Why this surfaced:** the v2 handoff was authored before the DS-27 v2 dual-canonical refactor that broadened the absolute-path discipline from "Dropbox-only" to "Dropbox + Projects". Pre-refactor authoring conflated the tooling repo's path layout with the Dropbox tree's. Post-refactor, the rule is explicit and `HANDOFF_TEMPLATE_v2.md` "Companion path discipline" section codifies the verification step (resolve canonical root BEFORE listing path; verify via `ls -la <absolute-path>`).

---

## What this handoff requests

The spec proposes converting DS-23 (post-fix pattern sweep), DS-24 (audit copy source before copy), and DS-25 (adjacent risk sweep after CodeQL triage) from **discipline-only rules** into **mechanical CI/local-hook gates** that BLOCK commits and PR merges when violated. The three rules currently exist in `.claude/skills/zero-error-qa/SKILL.md` with `ENFORCEMENT IS DISCIPLINE-ONLY for now` markers; the spec retires those markers and lands the mechanical enforcement.

Your job: independently verify the spec's design decisions, look for new-blocker concerns, and emit a STRICT gate verdict.

This handoff uses **v2-hardened format** — concise mode authorized when no blockers found; full mode required when any blocker found OR when any required analysis area cannot be fully evidenced (v2 amendment #2). Default to full mode if uncertain.

---

## Step 0 — Preflight (do FIRST, before any analysis)

Run these checks and emit results inline. **HALT and report if any preflight fails.**

1. **Spec exists:** `ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md"` — capture size + mtime.
2. **Spec hash:** `shasum "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md"` — capture digest.
3. **Companion file existence + size (v2.1 — ABSOLUTE paths per DS-27 dual-canonical):** for each of the 7 companion files listed in the header, run `ls -la <absolute-path>` and capture size + mtime. Use the absolute paths verbatim from the header — do NOT assume Dropbox root for paths starting with `mindfulnest-tooling/...` or `MindfulNest/...`; those resolve under `/Users/kimberlysmith/Projects/`. If any companion file is missing, HALT.

   Probe commands (copy-paste, all 7 files):
   ```
   ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md"
   ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/mn-context/SKILL.md"
   ls -la "/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit"
   ls -la "/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml"
   ls -la "/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/ai_review.yml"
   ls -la "/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/smoke.yml"
   ls -la "/Users/kimberlysmith/Projects/MindfulNest/.github/workflows/legacy-file-gate.yml"
   ```
4. **Anchored-section + snippet match (v2 amendment #1 — replaces v1 exact-line-number quotes):** instead of quoting "line N verbatim" (which breaks on benign line shifts), perform an anchored section + snippet match for each of the three v1 quote requirements. Emit the section header you found, the line range it currently occupies, and the snippet content matching the v1 description.

   | Anchor target | v1 (deprecated) | v2 anchored check |
   |---------------|-----------------|-------------------|
   | Spec §0 Operating Mode | "Quote §0 Operating Mode bullets verbatim" | Locate the `§0 Operating Mode Declaration` header in the spec; capture current line range; quote the bullet list under that header verbatim |
   | zero-error-qa DS-23 PR #8 CRIT-1 example | "Quote line 268 verbatim" | Locate the DS-23 section (header anchor: `## DS-23` or section listing PR #8 CRIT-1 as failure-mode example); capture current line range; quote the PR #8 CRIT-1 example sentence verbatim |
   | tooling pre-commit override pattern | "Quote lines 32-35 verbatim" | Locate the existing override-pattern block in `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit` (anchor: `BYPASS=` or `OVERRIDE=` or `--no-verify` handling, whichever matches the existing pattern); capture current line range; quote the matched block verbatim |

   Acceptance criterion: 3 anchored matches found + line ranges + verbatim snippets emitted. If any anchor cannot be located by header/snippet pattern (not by absolute line number), HALT and report which anchor failed. Line-shift tolerance is intentional in v2.

If any preflight fails, HALT and report.

---

## Step 1 — Open the project(s) in Cursor (v2.1 dual-canonical)

This handoff spans BOTH canonical roots per DS-27 v2 dual-canonical refactor:

- **Primary (Mindfulnest project):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`
- **Secondary (tooling repo + RN app):** `/Users/kimberlysmith/Projects/mindfulnest-tooling/` and `/Users/kimberlysmith/Projects/MindfulNest/`

Open the spec file at `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md` in the editor. Open Cursor Composer or chat.

Recommended additional editor tabs (read-only context — absolute paths per DS-27):
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md`
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/mn-context/SKILL.md`
- `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit`
- `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml`
- `/Users/kimberlysmith/Projects/MindfulNest/.github/workflows/legacy-file-gate.yml`

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md. It proposes converting DS-23 (post-fix pattern sweep), DS-24 (audit copy source), and DS-25 (adjacent risk sweep after CodeQL triage) from DISCIPLINE-ONLY rules to MECHANICAL gates blocking commits + PR merges.

The spec uses dual-Opus advocate/counter pattern (§4) with a clean resolution (§4.5). It mirrors the DS-22 + Step 2.5b mechanical-gate pattern that already lives in mn-context/SKILL.md. The three rules originate from PR #8's CRIT-1, CRIT-2, CRIT-3 incidents.

This is the v2 review handoff. v1 found AUTHORIZE_IMPLEMENTATION with 3 minor hardening points. v2 incorporates those 3 fixes (anchored-section preflight, concise-mode escalation, DS-24 FP-rate gate trigger) and asks you to re-verify under stricter rules.

Your task: verify the design decisions are sound and the spec doesn't introduce new blockers.

CONCISE MODE AUTHORIZED — v2 AMENDMENT #2 (escalation rule):
If you find ZERO blocker concerns AND every V1-V6 required analysis area is fully evidenced:
- Preflight evidence (5 lines max, anchored-section format per amendment #1)
- 1 paragraph confirming the §3 design + §4 resolution + §11 risk model are sound, no new blockers
- Verdict: AUTHORIZE_IMPLEMENTATION
- (Optional) ≤3 LOW-severity nice-to-haves in brief bullets

ESCALATION TRIGGER (new in v2): if ANY required analysis area in V1-V6 cannot be fully evidenced — e.g., you couldn't read a referenced file, you couldn't reproduce an anchor, the spec section the question targets is missing or ambiguous, or your evidence is "I think" rather than a quoted citation — concise mode is REVOKED. Force full mode and document which area was under-evidenced.

FULL MODE REQUIRED IF ANY BLOCKER FOUND OR ANY V1-V6 AREA UNDER-EVIDENCED:
- Citation tables with severity (CRITICAL/HIGH/MED/LOW) + blocker tag (Y/N)
- Per-section analysis: which sections of the spec contain the blocker?
- New-blocker search (Q-NEW-1, Q-NEW-2, Q-NEW-3 below)
- Strict gate verdict: AMEND_V2 or PAUSE_FOR_REDEBATE

Default to full mode if uncertain.

PREFLIGHT (do first, emit inline regardless of mode) — v2 hardened + v2.1 absolute paths:
1. Confirm `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md` exists; capture size + mtime.
2. shasum the spec; capture digest.
3. Confirm 7 companion files exist using ABSOLUTE paths (per v2.1 §0.2 amendment — paths span both canonical roots, Dropbox + Projects). Run each `ls -la` verbatim:
   - `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md` (Dropbox root)
   - `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/mn-context/SKILL.md` (Dropbox root)
   - `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit` (Projects root — tooling repo)
   - `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml` (Projects root — tooling repo)
   - `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/ai_review.yml` (Projects root — tooling repo)
   - `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/smoke.yml` (Projects root — tooling repo)
   - `/Users/kimberlysmith/Projects/MindfulNest/.github/workflows/legacy-file-gate.yml` (Projects root — RN app)
   Capture size + mtime for each. If any is missing, HALT.
4. v2 AMENDMENT #1 — Anchored-section preflight (replaces exact-line-number quotes):
   a. Locate spec `§0 Operating Mode Declaration` header; capture current line range; quote bullets verbatim.
   b. Locate zero-error-qa DS-23 PR #8 CRIT-1 example by section anchor; capture current line range; quote sentence verbatim.
   c. Locate tooling pre-commit override pattern block by content anchor (BYPASS/OVERRIDE/--no-verify) in `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit`; capture current line range; quote block verbatim.
   Three anchored matches with line ranges + verbatim snippets, not three exact-line-number reads.
If any anchor cannot be located by header/snippet pattern, HALT and report.

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

DS-24 FP-RATE GATE TRIGGER — v2 AMENDMENT #3:
The spec estimates DS-24 FP rate at 30-50% (handler-shape regex is broad). v2 sets a hard verdict trigger:
- If your evidenced FP-rate estimate > 50% AND the override-burden estimate > 8 hours/week (Kim time, not CI time), the verdict MUST be AMEND_V2 — defer DS-24 mechanical gating until AST-similarity (per §5.2 OD) lands. Auto-authorize is forbidden under that condition.
- If FP-rate ≤ 50% OR override-burden ≤ 8 hr/week, the override-comment pattern (`# DS-24: authored from scratch`) may be accepted; document the burden estimate and the assumptions.
- If you cannot evidence either number, that area is "under-evidenced" per amendment #2 ⇒ force full mode and surface as a blocker.

REQUIRED OUTPUT (concise OR full mode):

Concise mode output (only if all V1-V6 fully evidenced AND DS-24 FP-rate ≤50% / override ≤8 hr/week):
1. Preflight evidence (5 lines max, anchored-section format)
2. 1 paragraph: "spec §3+§4+§11 sound; no new blockers identified. Specifically [brief recap of what was checked]."
3. Verdict: AUTHORIZE_IMPLEMENTATION
4. (Optional) ≤3 LOW-severity nice-to-haves in bullets

Full mode output (any blocker, any under-evidenced area, OR DS-24 FP-rate > 50% with override > 8 hr/week):
1. Preflight evidence (anchored-section format per amendment #1)
2. Per-section table (mandatory citation format with severity + blocker tag): one row per V1-V6 verification, verdict on whether the section is sound (SOUND / PARTIAL / NOT_SOUND).
3. New-blocker analysis (Q-NEW-1, Q-NEW-2, Q-NEW-3)
4. DS-24 FP-rate evidence: numeric estimate + override-burden estimate + assumptions (per amendment #3)
5. Final gate verdict in STRICT form (pick exactly one):
   AUTHORIZE_IMPLEMENTATION: spec §3+§4+§11 are sound, no new blockers, all V1-V6 evidenced, DS-24 FP gate trigger NOT met; advance to implementation handoff.
   AMEND_V2: spec has remaining issues; list specific blockers with severity + spec §refs. (Required if amendment #3 trigger met.)
   PAUSE_FOR_REDEBATE: fundamental design issues; recommend fresh dual-Opus.
6. If AMEND_V2: list specific blocker concerns with severity + citations.
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

1. **DS-24 false-positive rate (v2 hardened with amendment #3 gate trigger).** The spec estimates 30-50% FP for DS-24 because the handler-shape regex is broad. v2 ties this to a verdict gate: if your evidenced estimate exceeds **FP > 50% AND override-burden > 8 hr/week**, the verdict MUST be AMEND_V2 — defer DS-24 mechanical gating until AST-similarity (per §5.2 OD) lands. Below that threshold, the override-comment pattern is acceptable; document the burden estimate.
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

## Why this v2 handoff (delta vs v1)

v1 returned AUTHORIZE_IMPLEMENTATION but flagged 3 minor hardening points. v2 closes those gaps without disturbing v1's structural backbone:

1. **Anchored-section preflight (§Step 0 #4)** — exact line-number quotes (`line 268`, `lines 32-35`) are brittle: a benign edit shifts the line and the preflight HALTs incorrectly. v2 replaces these with header/snippet anchors that tolerate line-shifts while still proving fresh read.
2. **Concise-mode escalation (§Step 2 prompt block)** — v1 allowed concise mode whenever no blockers were found, but did not require concise to also depend on full-evidence coverage of V1-V6. v2 adds: if any required analysis area cannot be fully evidenced (un-readable file, un-locatable anchor, "I think" rather than quoted citation), concise mode is revoked and full mode forced.
3. **DS-24 FP-rate gate trigger (§Specific question 1 + §Step 2 prompt)** — v1 asked whether 30-50% FP is acceptable but did not tie the answer to a verdict. v2 sets a hard floor: estimated FP > 50% AND override-burden > 8 hr/week ⇒ AMEND_V2. Below that ⇒ override-comment pattern accepted with documented burden estimate.

Per-section verification (V1-V6), new-blocker search (Q-NEW-1/2/3), strict verdict format (AUTHORIZE / AMEND_V2 / PAUSE), dual-mode (concise/full), and Step 3 verdict-branching are preserved unchanged from v1.

---

## Why this handoff is structured this way (preserved from v1)

This handoff descends from `HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_v2_20260508.md` (v2-hardened format). It includes:

- **Mandatory preflight** (Step 0) with size + shasum + anchored-section quotes (v2: replaces v1 line-number quotes) — proof-of-fresh-read prevents Cursor from reviewing a cached or stale view of the spec while tolerating benign line-shifts.
- **Mandatory citation format** with severity (CRITICAL/HIGH/MED/LOW) + blocker tag (Y/N) — same standard as the v2 PATCH_FORWARD handoff.
- **Strict gate verdict** (AUTHORIZE_IMPLEMENTATION / AMEND_V2 / PAUSE_FOR_REDEBATE) — no ambiguous "looks fine" responses; one of three exact tokens.
- **Concise mode authorized for no-blocker reviews with full evidence** (v2: escalation rule added — under-evidenced area forces full mode) — reduces reviewer overhead when nothing's wrong without letting concise mode mask incomplete review.
- **Per-section verification (V1-V6)** with explicit dimensions to check — design coherence, debate quality, phase ordering, semantics specificity, bypass/governance, completeness.
- **New-blocker search (Q-NEW-1/2/3)** — guards against the spec introducing fresh issues while addressing existing ones.
- **DS-24 FP-rate verdict gate (v2 amendment #3)** — ties the long-discussed FP-rate question to a binary AUTHORIZE/AMEND outcome.

Full mode remains required when blockers ARE found OR when any V1-V6 area is under-evidenced. This preserves rigor where it matters; reduces friction where it doesn't.

---

*End of HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md.*
