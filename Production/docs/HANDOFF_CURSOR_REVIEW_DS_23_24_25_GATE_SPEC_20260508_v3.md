# Handoff v3 — Cursor Cross-Review of DS-23/24/25 Mechanical Gate Tech Spec (HANDOFF_TEMPLATE_v2-compliant rewrite)

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08
**Spec under review:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md` (file path `..._v2.md`; **content version is v3** per the §0.1 changelog inside; size 37,834 bytes; mtime 2026-05-08 12:01:58; sha256 `52b227fe8f6d4f233cab82c6bbed22d6f5b30d3b7d130d0aecd00e24ee4a2024`).

**Predecessor (v2-content baseline, file path `..._v1.md`, retained as historical):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md` (size 68,981 bytes; mtime 2026-05-08 08:46:47; sha256 `5101e94faea15a542e40de194f4467419912536dfebdc01af35586a7db4c0917`). Do NOT delete or modify; needed for diff comparison of the §7.3.1 trigger-model fix.

**Supersedes:** `Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md` (preserved as historical baseline; do NOT edit in place). The v2 handoff returned `AMEND_V2` from Cursor (1 HIGH Q-NEW-1 + 4 MED), which drove the v3 SPEC content (the §7.3.1 trigger-model split + 4 MED amendments). This handoff (v3) reviews the v3 SPEC content. **Why this v3 handoff replaces the prior v3 handoff filed earlier today (12:04 mtime):** the prior v3 handoff drifted from `HANDOFF_TEMPLATE_v2`. Cursor batch audit 2026-05-08 surfaced: A PASS, B PARTIAL (escalation logic present but missing the verbatim concise→full clause), C PASS, D PASS, E PASS, F MISSING (no HALT gates section), G MISSING (no Hard rules + Final report sections). This rewrite closes B/F/G. The v3 spec content is unchanged.

**Companion files (absolute paths per HANDOFF_TEMPLATE_v2 §0.3 dual-canonical):**
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md` — Dropbox-rooted (canonical root #1; **spec under review**; content version v3); sha256 `52b227fe8f6d4f233cab82c6bbed22d6f5b30d3b7d130d0aecd00e24ee4a2024`.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md` — Dropbox-rooted (canonical root #1; **v2-content historical baseline**, the file v3 supersedes; sha256 `5101e94faea15a542e40de194f4467419912536dfebdc01af35586a7db4c0917`).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_V3_AMENDMENT_REPORT_20260508.md` — Dropbox-rooted (canonical root #1; v3 amendment proof report — verbatim §7.3.1 v2-buggy YAML + verbatim §7.3.1.A/B v3 corrected YAML + per-finding resolution table).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508.md` — Dropbox-rooted (canonical root #1; **v1 prior review handoff** — historical baseline; v1 spec review).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md` — Dropbox-rooted (canonical root #1; **v2 prior review handoff** — historical baseline; v2 review returned AMEND_V2 driving v3-content amendments).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` — Dropbox-rooted (canonical root #1; **structural template** for this rewrite — anchored citations, concise→full escalation, numeric AMEND_V3 thresholds, dual-canonical absolute paths, companion path discipline).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — Dropbox-rooted (canonical root #1; this handoff conforms to v2 template).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md` — Dropbox-rooted (canonical root #1; **DS-23/24/25 source rule definitions** + DS-19 + DS-26 + DS-27 + DS-28 + DS-29 doctrine).
- `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit` — Projects-rooted (canonical root #2; tooling repo pre-commit hook; size 7,562 bytes; mtime 2026-05-07 20:34).
- `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml` — Projects-rooted (canonical root #2; tooling repo; size 1,374 bytes; mtime 2026-05-07 16:13; the workflow §7.3.1.B chains off via `workflow_run`).
- `/Users/kimberlysmith/Projects/MindfulNest/.github/workflows/legacy-file-gate.yml` — Projects-rooted (canonical root #2; RN app; size 3,128 bytes; mtime 2026-05-07 20:53; example of file-existence GHA blocking gate cited in spec §2).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_DS23_24_25_IMPLEMENTATION_20260508.md` — Dropbox-rooted (canonical root #1; downstream implementation handoff that consumes the AUTHORIZE_IMPLEMENTATION verdict).

---

## What you're doing

Independently cross-review the v3 content of DS-23/24/25 Mechanical Gate Tech Spec (file at `..._v2.md` path) and emit a verdict (AUTHORIZE_IMPLEMENTATION / AUTHORIZE_PHASE_0_ONLY / AMEND_V2 / PAUSE_FOR_REDEBATE). v3 is a 5-amendment fix-set over v2 content (1 HIGH Q-NEW-1 trigger-model fix + 4 MED non-blockers V3/V4/V5/V6). v2 content is OUT OF SCOPE except where amendments preserve verbatim sections that must still hold. The trigger-model split (§7.3.1.A `on: pull_request` primary + §7.3.1.B `on: workflow_run` secondary using `gh api` queries) is the central object of review.

---

## §0.1 — Why this v3 review exists

Cursor's earlier review of v2 content returned **AMEND_V2** with 1 HIGH (Q-NEW-1: §7.3.1's `on: workflow_run` workflow read `github.event.pull_request.body` + `.number` directly — those fields are NOT reliably populated under `workflow_run` per documented GitHub Actions event payload semantics) plus 4 MED non-blockers (V3 phase ordering, V4 sentinel ergonomics, V5 thresholds, V6 path discipline). The v3 SPEC closes those gaps via:

1. §7.3.1 split into §7.3.1.A primary (`on: pull_request`, canonical, reads `github.event.pull_request.body` + `.number` reliably) and §7.3.1.B optional secondary (`on: workflow_run`, queries PR explicitly via `gh api /repos/.../commits/<head_sha>/pulls` and `gh pr view --json body`; zero `${{ github.event.pull_request.* }}` interpolations inside §7.3.1.B's YAML body).
2. §8 Phase E.5 inserted (SKILL.md amend lands same-day as Phase D, closing the stale-doc window).
3. §11.3 `MN_FRESH=1` env-var pathway for fresh contributors (warning-not-fail behavior + `DS_FRESH_CONTRIBUTOR_BYPASS` activity row).
4. §11.2 thresholds re-tagged `[INFERRED — calibrate after Phase G 30-day audit]` with explicit Phase G recalibration directive.
5. §14.6 absolute-path / shorthand audit table (path-discipline closure).

This v3 review verifies the 5 amendments are sound AND no NEW blockers were introduced. v2-baseline preserved-verbatim sections are out of scope unless an amendment broke them (Q-NEW-3 covers that).

---

## §0.2 — What you DON'T need to do

- Do NOT re-litigate v2 baseline preserved-verbatim sections (§1, §2, §3.1-§3.3, §4, §5, §6, §9, §10, §13.1-§13.3) UNLESS Q-NEW-3 surfaces a v3 amendment breaking one of them.
- Do NOT re-litigate the underlying DS-23/24/25 rule definitions — locked under LD 580 and out of scope per spec §0.2.
- Do NOT review DS-26 mechanical gating — different blocker row, different spec, different handoff.
- Do NOT have Cursor edit v3. Verdict-only.
- Do NOT have Cursor implement the gates. Implementation handoff is at `Production/docs/HANDOFF_DS23_24_25_IMPLEMENTATION_20260508.md`; this handoff is review-only.

---

## HALT gates

**Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.

Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

### Gates (must all be MET before Step 1 begins)

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|------------------|-----------------|-------------|
| 1 | Has the v3 spec sha256 been confirmed match `52b227fe8f6d4f233cab82c6bbed22d6f5b30d3b7d130d0aecd00e24ee4a2024`? | `shasum -a 256` of v3 spec absolute path (`..._v2.md`) | Hash matches verbatim | HALT — author drift; surface to Kim before any analysis |
| 2 | Has the v2-content historical baseline (`..._v1.md`) been confirmed preserved + unmodified during v3 authoring? | `ls -la` + `shasum -a 256` of `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md` | Hash matches `5101e94faea15a542e40de194f4467419912536dfebdc01af35586a7db4c0917` AND mtime predates v3 spec mtime (2026-05-08 12:01:58) | HALT — baseline drift; surface to Kim |
| 3 | Has v3 spec §0.1 v3 Changelog anchor been read into context? | Anchor: locate `### §0.1 v3 Changelog — Cursor AMEND_V2 amendments applied` header in v3 spec; capture line range; quote the Q-NEW-1 row of the changelog table verbatim | Reviewer emits the §0.1 changelog-table Q-NEW-1 row verbatim, including the "DS-25 workflow example is event-model inconsistent" finding text and the "§7.3.1 trigger model fix" resolution column | HALT and report which anchor failed |
| 4 | Has v3 spec §7.3.1.A + §7.3.1.B trigger-model anchors been read into context? | Anchor #1: locate `### §7.3.1.A` (or content anchor `Primary trigger — pull_request (canonical)` or `# DS-25 Adjacent Risk Sweep Gate — primary trigger (canonical)` comment line); Anchor #2: locate `### §7.3.1.B` (or content anchor `Optional secondary trigger — workflow_run` or `# DS-25 Adjacent Risk Sweep Gate — secondary trigger (chained after CodeQL)` comment line) | Reviewer emits BOTH YAML blocks with line ranges, AND emits the `gh api /repos/${{ github.repository }}/commits/${HEAD_SHA}/pulls` line from §7.3.1.B as proof the secondary trigger uses `gh api` queries (not `github.event.pull_request.*` field reads) | HALT and report which anchor failed |
| 5 | Has v3 spec Phase E.5 + §11.3 MN_FRESH + §11.2 [INFERRED] tags + §14.6 audit-table anchors been read into context? | Anchor #1: `### **§Phase E.5 — SKILL.md amend publication (NEW in v3 — addresses MED V3)**` (in §8); Anchor #2: `### §11.3 New-developer friction (v3 amended — MED V4)`; Anchor #3: `### §11.2 Bypass mechanism abuse risk (v3 amended — MED #4)`; Anchor #4: `### §14.6 v3 NEW — Absolute-path / shorthand audit (addresses MED V6)` | Reviewer emits all 4 anchors verbatim with line ranges and snippet match | HALT and report which anchor failed |

---

## Step 0 — Preflight (do FIRST, before any analysis) — anchored discipline

Mandatory actions, emit inline:

1. **`ls -la` + `shasum -a 256` v3 spec absolute path:**
   ```sh
   ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md"
   shasum -a 256 "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md"
   ```
   Expected: file exists; size 37,834 bytes; mtime 2026-05-08 12:01:58; sha256 `52b227fe8f6d4f233cab82c6bbed22d6f5b30d3b7d130d0aecd00e24ee4a2024`. **HALT if hash differs — author drift detected; surface to Kim before proceeding.**

2. **`ls -la` + `shasum -a 256` v2-content baseline (`..._v1.md`):**
   ```sh
   ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md"
   shasum -a 256 "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md"
   ```
   Expected: file exists; size 68,981 bytes; mtime 2026-05-08 08:46:47 (predates v3 spec mtime); sha256 `5101e94faea15a542e40de194f4467419912536dfebdc01af35586a7db4c0917`. **HALT if hash differs OR mtime postdates v3 spec mtime — baseline drift; surface to Kim.**

3. **Anchor+snippet stale-cache check (NOT fixed-line "first 20 lines" framing):**
   - Anchor (a): the v3 spec **title line** anchor — locate `# DS-23 / DS-24 / DS-25 Mechanical Gate Tech Spec v3` (must be the document's first non-blank line); quote verbatim; capture line number.
   - Anchor (b): the v3 spec **§0 Operating Mode header** anchor — locate `## §0 Operating Mode Declaration (per zero-error-qa §0)`; quote the header verbatim; capture current line range; quote the **Mode** bullet + **Tier** bullet snippet under the header.
   - Anchor (c): the v3 spec **§0.1 changelog-table header** anchor — locate `### §0.1 v3 Changelog — Cursor AMEND_V2 amendments applied`; quote the header verbatim; capture line range; quote the table-header row (`| # | Cursor finding | Severity | v3 section addressing it |`).
   Acceptance: 3 anchored matches found + line ranges + verbatim snippets emitted. The identity check is **anchor-text-based**, NOT line-number-based — line shifts do not fail this check; missing anchor text does fail it. **HALT if any anchor is missing.**

4. **Companion-file integrity (anchored — header/snippet ONLY):**
   - (a) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_V3_AMENDMENT_REPORT_20260508.md` — anchor `# DS-23/24/25 v3 Amendment Proof Report` (first line); ALSO anchor `## §2 Verbatim §7.3.1 v3 (the corrected YAML — both patterns)`; quote the §2 header + the first 5 lines of the §7.3.1.A YAML block (the canonical-comment block) to confirm the proof-report's §7.3.1.A YAML matches the v3 spec's §7.3.1.A YAML.
   - (b) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md` — anchor `# Handoff v2 — Cursor Cross-Review of DS-23/24/25 Mechanical Gate Tech Spec` (first line) OR similar `# Handoff v2` first line; confirm the v2 prior-review-handoff context exists (this is the handoff that drove the AMEND_V2 verdict + v3 SPEC content).
   - (c) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md` — anchor `### DS-23` heading (post-fix sweep doctrine); ALSO anchor `### DS-24` heading; ALSO anchor `### DS-25` heading; quote the rule-name + first paragraph under each anchor as snippet match. (Confirms the rule-source backbone v3 is mechanizing.)
   - (d) `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml` — anchor `name: ` first line + `on:` block; quote the trigger configuration to confirm CodeQL is the upstream workflow that §7.3.1.B chains via `workflow_run`.
   - (e) `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit` — anchor by content marker (one of `BYPASS=`, `OVERRIDE=`, `--no-verify`, `MN_SKIP=`, whichever exists in the existing pre-commit hook); capture current line range; quote the matched override-pattern block verbatim (this is the existing override-pattern v3 builds on).
   - (f) `/Users/kimberlysmith/Projects/MindfulNest/.github/workflows/legacy-file-gate.yml` — anchor `name: ` first line + first `runs-on:` line; confirm the file-existence GHA blocking-gate example referenced in spec §2 exists.

If preflight 1-3 fails, HALT and report. If 4 fails for any companion file, document inline; if 4 fails for ≥2 companion files, HALT and report.

---

## Step 1 — Open the project(s) in Cursor

- **Primary (Mindfulnest project):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`
- **Secondary (tooling repo + RN app):** `/Users/kimberlysmith/Projects/mindfulnest-tooling/` and `/Users/kimberlysmith/Projects/MindfulNest/`

Open the v3 spec file at `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md` in the editor. Open the v2-content baseline at `..._v1.md` in a SECOND tab so the trigger-model diff (v2 §7.3.1 vs v3 §7.3.1.A/B) is visible side-by-side.

Recommended additional editor tabs:
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_V3_AMENDMENT_REPORT_20260508.md`
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md`
- `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml`
- `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit`
- `/Users/kimberlysmith/Projects/MindfulNest/.github/workflows/legacy-file-gate.yml`

---

## Step 2 — Paste this prompt into Cursor

```
I have a v3-amended tech spec at:
/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md
(file path `..._v2.md`; CONTENT version is v3 per §0.1 changelog inside)

The v2-content baseline (file path `..._v1.md`) is preserved unchanged for diff comparison:
/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md

v2 received your earlier AMEND_V2 verdict citing 1 HIGH (Q-NEW-1: §7.3.1's `on: workflow_run` workflow read `github.event.pull_request.*` fields directly — fields NOT reliably populated under workflow_run) plus 4 MED non-blockers (V3 phase ordering, V4 sentinel ergonomics, V5 thresholds, V6 path discipline). Your task: re-review only v3's 5 amendments and verify (a) the trigger-model fix is sound, (b) the 4 MED amendments are correctly applied, (c) no new blockers introduced. v2-baseline preserved-verbatim sections are OUT OF SCOPE unless Q-NEW-3 surfaces an amendment break.

Background context (informational only):
- v3 §7.3.1 splits into §7.3.1.A primary `on: pull_request` (canonical event model — payload fields populate reliably) and §7.3.1.B optional secondary `on: workflow_run` (queries PR via `gh api /repos/.../commits/<head_sha>/pulls` then `gh pr view --json body`; zero `${{ github.event.pull_request.* }}` interpolations inside §7.3.1.B's YAML body). Both share the same `ds_25_check` status check name (branch protection enumerates one).
- v3 §8 Phase E.5 inserts SKILL.md amend publication same-day as Phase D (was Phase F in v2; collapses stale-doc window from "weeks" to "same-day").
- v3 §11.3 introduces `MN_FRESH=1` env-var pathway: contributors with <30 days of git-author commits in tooling repo get warning-not-fail behavior + `DS_FRESH_CONTRIBUTOR_BYPASS` activity row; sunset after 30 days OR 5 commits.
- v3 §11.2 re-tags thresholds (>3 bypasses/7d, <50 chars rationale) `[INFERRED — calibrate after Phase G 30-day audit]`; §8 Phase G has explicit recalibration directive.
- v3 §14.6 adds absolute-path / shorthand audit table: confirms intra-Dropbox paths use Dropbox-rooted form (Dropbox = spec's anchor); paths to Projects-rooted files (tooling repo + RN app) use absolute form.

Authority: LD `DS_23_24_25_MECHANICAL_GATE_SPEC_V3_AMEND_V2_FIXES_V1` (v3 SPEC authority); LD `HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_V3_TEMPLATE_COMPLIANT_V1` (this handoff's authority).

Apply your full independent scrutiny on v3-scope changes only. v2-baseline design surface is locked except where a v3 amendment touches it (Q-NEW-3).

PREFLIGHT (do first, emit inline) — anchored discipline:
1. Confirm spec v3 file exists; capture size + mtime + shasum.
   Expected sha256: 52b227fe8f6d4f233cab82c6bbed22d6f5b30d3b7d130d0aecd00e24ee4a2024
   HALT if mismatch — author drift.
2. Confirm v2-content baseline (`..._v1.md`) preserved unmodified; capture size + mtime + shasum.
   Expected sha256: 5101e94faea15a542e40de194f4467419912536dfebdc01af35586a7db4c0917
   Expected mtime: predates v3 spec mtime (2026-05-08 12:01:58).
   HALT if hash mismatch OR mtime postdates v3 spec.
3. Anchor+snippet stale-cache check (NOT fixed-line "first 20 lines" framing):
   (a) Title-line anchor: locate "# DS-23 / DS-24 / DS-25 Mechanical Gate Tech Spec v3" (must be document's first non-blank line); quote verbatim with line number.
   (b) §0 anchor: locate "## §0 Operating Mode Declaration (per zero-error-qa §0)"; quote header + Mode/Tier bullet snippet underneath; capture line range.
   (c) §0.1 changelog anchor: locate "### §0.1 v3 Changelog — Cursor AMEND_V2 amendments applied"; quote header + table-header row; capture line range.
4. Companion-file integrity (anchored header/snippet only):
   (a) `Production/docs/DS_23_24_25_V3_AMENDMENT_REPORT_20260508.md` — anchor "# DS-23/24/25 v3 Amendment Proof Report" + "## §2 Verbatim §7.3.1 v3 (the corrected YAML — both patterns)"; quote first 5 lines of §7.3.1.A YAML block.
   (b) `Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md` — anchor first-line `# Handoff v2 — Cursor Cross-Review of DS-23/24/25 Mechanical Gate Tech Spec` (or near-equivalent v2 handoff title); confirm v2 prior-review context exists.
   (c) `.claude/skills/zero-error-qa/SKILL.md` — anchors `### DS-23`, `### DS-24`, `### DS-25`; quote rule-name + first paragraph under each.
   (d) `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml` — anchor `name:` first line + `on:` trigger block; quote.
   (e) `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit` — anchor by content marker (one of `BYPASS=`, `OVERRIDE=`, `--no-verify`, `MN_SKIP=`); capture line range; quote matched block verbatim.
   (f) `/Users/kimberlysmith/Projects/MindfulNest/.github/workflows/legacy-file-gate.yml` — anchor `name:` first line + first `runs-on:`; confirm exists.
5. v3-specific anchor capture:
   (i) Locate `### §7.3.1.A` header (or "Primary trigger — pull_request (canonical)" or `# DS-25 Adjacent Risk Sweep Gate — primary trigger (canonical)` comment line); quote the `on: pull_request` YAML block + the `BODY="${{ github.event.pull_request.body }}"` line + the `PR_NUMBER="${{ github.event.pull_request.number }}"` line as proof of canonical pull_request payload usage.
   (ii) Locate `### §7.3.1.B` header (or "Optional secondary trigger — workflow_run" or `# DS-25 Adjacent Risk Sweep Gate — secondary trigger (chained after CodeQL)` comment line); quote the `on: workflow_run` YAML block + the `gh api /repos/${{ github.repository }}/commits/${HEAD_SHA}/pulls` line + the `gh pr view "$PR_NUMBER" --json body` line as proof of `gh api` query usage; ALSO grep the §7.3.1.B YAML body for `${{ github.event.pull_request.` interpolations and confirm zero matches.
   (iii) Locate `### **§Phase E.5 — SKILL.md amend publication (NEW in v3 — addresses MED V3)**` in §8; quote the phase block verbatim with line range.
   (iv) Locate `### §11.3 New-developer friction (v3 amended — MED V4)`; quote the `MN_FRESH=1` mechanism description verbatim.
   (v) Locate `### §11.2 Bypass mechanism abuse risk (v3 amended — MED #4)`; quote the threshold-recalibration `[INFERRED — calibrate after Phase G 30-day audit]` tags verbatim.
   (vi) Locate `### §14.6 v3 NEW — Absolute-path / shorthand audit (addresses MED V6)`; quote the audit-table header + first 3 rows verbatim.
If preflight 1-3 fails, HALT and report.

CONCISE→FULL ESCALATION RULE (mandatory verbatim per HANDOFF_TEMPLATE_v2):
> If any required section cannot be evidenced, full mode is mandatory.

Operational definition of "cannot be evidenced": could not read v3 spec; could not reproduce a v3-scope anchor (header/snippet match in actual file content); the §7.3.1.A / §7.3.1.B / Phase E.5 / §11.3 / §11.2 / §14.6 surface is missing or ambiguous; reviewer's evidence is "I think" or "probably" rather than a quoted citation; reviewer skipped a question to save tokens. Document WHICH area was under-evidenced in full-mode output.

ANALYSIS REQUIREMENTS (citation table format):
| # | Concern | Severity (CRITICAL/HIGH/MED/LOW) | Evidence (anchored citation: section header + snippet match, NOT line numbers alone) | Suggested mitigation | Blocker (Y/N) |

REQUIRED ANALYSIS TASKS (v3-scope only — 5 fixes + 3 new-blocker queries):

A. TRIGGER CRITERIA REVIEW (DS-23 + DS-24 + DS-25 mechanical detectability)
   The spec proposes mechanical CI gates that detect missing sweeps after security/correctness fixes. Verify:
   (a) DS-23 (post-fix pattern sweep): mechanical detection from PR diff alone — is the gate's trigger criterion (e.g., file-pattern hot-zone match, or sentinel `// DS-23-SWEEP-OK` audit marker per §11.3) reliable, or does it depend on side-channel inputs (e.g., commit-message metadata, prior `prod_blockers` rows) that may be missing/stale?
   (b) DS-24 (audit copy source before copy): does §7.2's gate semantics correctly fire on copy-source patterns (multi-file copy from a designated reference + sweep marker absent)?
   (c) DS-25 (adjacent risk sweep after CodeQL triage): under §7.3.1.A `pull_request` primary, does the gate reliably detect "PR touches a file that has an open CodeQL alert" via `gh api code-scanning/alerts` + `gh pr view --json files` enumeration?
   (d) §7.3.1.B `workflow_run` secondary: does `gh api /repos/.../commits/<head_sha>/pulls` reliably return the PR number for the upstream commit? Edge cases: head_sha in multiple PRs (rebase-merge artifacts, target-branch retargeting), fork PRs, force-pushed branches.

   NUMERIC THRESHOLD: if Cursor estimates the COMBINED false-positive rate across DS-23 + DS-24 + DS-25 on real PRs as > 50% (i.e., >50% of PRs that fail the gate are not actual DS-rule violations), verdict MUST be AMEND_V2. Show your computation: per-rule FP rate, weighted by per-rule trigger frequency, with assumptions stated. Per-rule FP rates referenced in spec §11.1 are [INFERRED] per v2 baseline; verify v3 did not invalidate them.

B. COVERAGE REVIEW (mechanical detectability from PR diff alone)
   For each of {DS-23, DS-24, DS-25}, verify the gate's trigger logic depends ONLY on PR diff content (file paths + line ranges + change pattern) plus a small set of out-of-band inputs (CodeQL alert list for DS-25; commit-author identity for §11.3 MN_FRESH; `prod_blockers` row IDs for retirement). The gate must NOT depend on inputs that are unavailable at gate-evaluation time.

   Specific concerns:
   (a) DS-23 sentinel-marker pattern: does the gate require an inline `// DS-23-SWEEP-OK: <hot-zone>` marker in the PR diff, OR a `prod_activity_log` row referenced by row-id, OR both? If both, what happens when one is present and the other absent?
   (b) DS-24 audit-row reference: does the gate require a `DS_24_COPY_SOURCE_AUDIT` activity-row reference in the PR body? If so, can the gate verify the row exists at gate-evaluation time (Directus is cross-network), or does it accept the row-id at face value (allowing false references)?
   (c) DS-25 sweep-block in PR body: §7.3.1.A reads `BODY="${{ github.event.pull_request.body }}"` and greps for `Adjacent risk sweep on .+ after CodeQL triage`; the BLOCK length check rejects placeholders (<100 chars). Is the 100-char threshold robust, or can a determined bypasser pad with whitespace/comments?

   NUMERIC THRESHOLD: if Cursor identifies any of {DS-23, DS-24, DS-25} sweep types where the trigger logic requires an input UNAVAILABLE at gate-evaluation time (i.e., the gate cannot mechanically evaluate "missing sweep" without external state), verdict MUST be AMEND_V2 on Task B with the unavailable-input named.

C. CI INTEGRATION REVIEW — workflow_run vs pull_request triggers (the central HIGH fix)
   The v2 §7.3.1 buggy YAML used `on: workflow_run` AND read `github.event.pull_request.body` + `.number` directly — under workflow_run, those fields are NOT reliably populated. v3 splits into §7.3.1.A (primary `on: pull_request`, canonical) + §7.3.1.B (optional secondary `on: workflow_run`, queries PR via `gh api`).

   Verify:
   (a) §7.3.1.A `on: pull_request` types `[opened, edited, synchronize, reopened]` correctly triggers on PR-body edits + branch-rebase resyncs + reopens. Confirm `github.event.pull_request.body` + `.number` + `.base.ref` populate reliably under this trigger per GHA documented event payload.
   (b) §7.3.1.B `on: workflow_run` `if: github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.event == 'pull_request'` correctly gates on CodeQL success AND filters to PR-event-driven CodeQL runs (not branch-push CodeQL runs).
   (c) §7.3.1.B `gh api /repos/${{ github.repository }}/commits/${HEAD_SHA}/pulls` resolves PR number from head_sha — is this the correct GHA-recommended pattern for workflow_run-chained workflows? Edge cases: head_sha in multiple PRs (return `.[0].number` may pick wrong one), fork PRs (head_sha is in the fork's commit graph; may not resolve correctly), force-pushed branches (older head_sha may not match any PR).
   (d) §7.3.1.B uses `gh pr view "$PR_NUMBER" --json body` for body fetch, NOT `github.event.pull_request.body`. Confirm zero `${{ github.event.pull_request.* }}` interpolations in §7.3.1.B's YAML body.
   (e) Both §7.3.1.A and §7.3.1.B use the same `ds_25_check` (or equivalent) status check name? If yes, branch protection only needs one. If no, branch protection needs both — surface this as a deployment risk.

   NUMERIC THRESHOLD: if the §7.3.1.B `gh api commits/<sha>/pulls` query has a documented edge case (fork PR, multi-PR head_sha, force-push) where it returns the WRONG PR number AND v3's mitigation (the `if [[ -z "$PR_NUMBER" ]]` empty-check + `exit 0`) is insufficient (e.g., returns a wrong-but-non-empty number), verdict MUST be AMEND_V2 on Task C.

D. OVERRIDE-BURDEN REVIEW (Kim-time cost of false-positive overrides)
   The spec proposes override mechanisms: §11.3 `MN_FRESH=1` for fresh contributors (warning-not-fail), §11.2 bypass (`--no-verify` + `MN_SKIP=` + audit-row reference). False positives produce override-comment burden. Verify:
   (a) Estimate the override-comment burden: per-week estimate of (false-positive PR count) × (Kim time per override review) for the steady-state Phase F+ regime.
   (b) Does §11.2's threshold of `>3 bypasses / 7-day window` correctly catch abuse without producing false-alarm noise on legitimate-bypass-heavy weeks?
   (c) Does §11.3 `MN_FRESH=1` 30-day-or-5-commits sunset reasonably bound the warning-not-fail window?
   (d) Does §14.6's path-discipline audit table capture all shorthand → absolute-path miscalibrations?

   NUMERIC THRESHOLD: if Cursor estimates the override-comment burden > 8 hr/week of Kim time (post-Phase-D steady state), verdict MUST be AMEND_V2 on Task D. Show your computation: estimated FP-triggered PRs per week, mean Kim review time per override, with assumptions stated.

E. SEQUENCING REVIEW (implementation phase ordering)
   §8 Phase A (pre-commit hook extension) → Phase B (CI workflow `ds_23_24_25_gate.yml`) → Phase C (PR template) → Phase D (bypass mechanism) → Phase E (weekly preflight audit) → Phase E.5 (NEW: SKILL.md amend, same-day as Phase D) → Phase F (blocker-row retirement + manual-review commentary update) → Phase G (30-day FP audit checkpoint).

   Verify:
   (a) Does Phase E.5 inserting SKILL flip same-day as Phase D actually close the stale-doc window? Or does it create a NEW race condition with Phase F (e.g., gates live + SKILL flip live, but Phase F blocker-row retirement lags)?
   (b) Does §12 rollback-per-phase table cover Phase E.5? If Phase D is reverted, does the SKILL.md re-flip happen automatically or is it a separate manual revert?
   (c) Does Phase G recalibration directive correctly reference §11.2 [INFERRED] thresholds for re-tagging?
   (d) Does the §13 testing plan (specifically §13.4 + §13.5 v3 NEW Trigger-model regression test) cover the §7.3.1.A primary AND §7.3.1.B secondary in unit + integration + adversarial layers?

   NUMERIC THRESHOLD: descriptive evaluation. If Cursor identifies a phase-ordering issue that creates a new race condition OR uncovered rollback path, verdict MUST be AMEND_V2 on Task E.

Q-NEW-1 NEW-BLOCKER SEARCH (the central v3 question, reframed):
Does the v3 §7.3.1.A/B trigger-model fix ACTUALLY solve the v2 HIGH blocker?
- §7.3.1.A: under `on: pull_request`, are `github.event.pull_request.body` + `.number` reliably populated per GHA docs? (Per docs: YES.)
- §7.3.1.B: are there ZERO `${{ github.event.pull_request.* }}` interpolations in §7.3.1.B's YAML body? (Confirm via grep.)

Q-NEW-2 NEW-BLOCKER SEARCH (did v3 introduce any new design issue?):
- §11.3 `MN_FRESH=1` sock-puppet bypass vector: can a contributor open branches under multiple author identities to keep getting MN_FRESH treatment? Mitigation?
- §8 Phase E.5 introducing a new race with Phase F (blocker-row retirement lag)?
- §7.3.1.B `gh api commits/<sha>/pulls` returning the WRONG PR number for fork PRs or multi-PR head_sha?

Q-NEW-3 NEW-BLOCKER SEARCH (are v2-preserved-verbatim sections still load-bearing under v3?):
- §3.1 Three rules, three surfaces; §3.2 Check semantics summary; §3.3 Why the regex is loose (FP defense): do these still hold under §7.3.1.A/B split? Specifically, does the "marker presence vs content quality" split (§3.3) survive the canonical/secondary trigger split?
- §6 Acceptance Criteria: does it still cover both §7.3.1.A and §7.3.1.B paths?
- §13.1-§13.3 Testing Plan: do unit/integration/adversarial layers cover both trigger paths, or only the v2 single-trigger path?

VERDICT FORMAT (mandatory, pick exactly ONE):
- AUTHORIZE_IMPLEMENTATION — v3 is sound; Phases A→E.5→E→F→G may proceed; v3's 5 amendments are verified; Q-NEW-1/2/3 returned no blockers.
- AUTHORIZE_PHASE_0_ONLY — v3 is sound BUT live state cannot be verified by Cursor from its environment (e.g., CodeQL alert list unreachable; Directus rows unreachable); authorize Phase A pre-commit-hook-extension dry-run only with risk acceptance for Phases B+C+D+E+F+G review post-Phase-A artifacts.
- AMEND_V2 — v3 has a defect in one of its 5 amendments OR a new blocker surfaced via Q-NEW-1/2/3; specify the defect AND the required v4 fix in concrete numeric terms (which §7.3.1 line, which §8 phase, which §11 threshold, which §14.6 audit row).
- PAUSE_FOR_REDEBATE — v3 has a fundamental issue requiring dual-Opus or expanded review.

Required output:
1. Preflight evidence (sha256 + 3-anchor stale-cache check + 6 anchored companion-file quotes + 6 v3-anchor captures).
2. Analysis table (per task A, B, C, D, E + Q-NEW-1, Q-NEW-2, Q-NEW-3) with severity, evidence (anchored citation), mitigation, blocker Y/N.
3. Verdict (one of the four above).
4. Limitations + cross-skill drift if any.
```

---

## Step 3 — After Cursor responds

Save Cursor's verbatim response to `Production/docs/CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v3.md`.

Verdict-driven next steps:

- **`AUTHORIZE_IMPLEMENTATION`** → dispatch implementation via Terminal CLI per `Production/docs/HANDOFF_DS23_24_25_IMPLEMENTATION_20260508.md`. Phases A→E.5→E→F→G may proceed in spec-defined order with G1-G10 pre-implementation gates as HALT preconditions.
- **`AUTHORIZE_PHASE_0_ONLY`** → dispatch Phase A pre-commit-hook-extension dry-run only with risk acceptance for downstream phases; review Phase A artifacts before Phase B authorization.
- **`AMEND_V2`** → author `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v3.md` (file path `_v3.md`; content version v4) addressing the blocker(s); preserve v3 content (`..._v2.md`) as historical baseline; re-run THIS handoff against the new content (rename + bump version refs + re-anchor).
- **`PAUSE_FOR_REDEBATE`** → halt; bring findings back to Claude Code; spawn fresh dual-Opus debate; do NOT proceed to implementation.

---

## Hard rules

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST (applies to handoff author logging this handoff to `prod_activity_log`; applies to Cursor reviewer if they touch Directus during analysis — they should not).
- **Multipass:** re-Read v3 spec after this handoff is authored (handoff author discipline; Cursor reviewer also re-reads if a HALT gate fires).
- **Rule 24:** confidence tags throughout (CONFIRMED / INFERRED / GUESSED).
- **DS-19 + DS-26:** always active; fire on any trigger condition. Autonomous mode does not bypass HALT gates.
- **DS-13 Layer 6:** input variation (read v2 review handoff as template + v3 spec content) → output variation (this handoff differs structurally to focus only on v3's 5-amendment fix-set + Q-NEW-1/2/3 new-blocker searches, not the full v2 task surface).
- **DS-27 explicit (absolute paths, dual-canonical):** all filesystem-touching commands MUST use absolute paths anchored to `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (canonical root #1) OR `/Users/kimberlysmith/Projects/` (canonical root #2). Do NOT operate inside `.claude/worktrees/` subdirectories. All paths in this handoff are anchored to one of the two canonical roots; companion files live across both roots and are tagged inline.
- **DS-28 dependency-order:** preflight steps 1-4 verified before Step 1; Step 1 before Step 2; Step 2 before Step 3.
- **DS-29 source tagging (REPORT vs FILE_FETCH vs CONFIG vs MODEL_PRIOR):** the handoff author tags every claim's source in the final report (this turn's report under §"Final report"); reviewer is encouraged but not required to apply DS-29 to its review output.
- **Companion path discipline (HANDOFF_TEMPLATE_v2 §0.3):** every companion file in this handoff is listed with absolute path + canonical-root tag. Author probed `ls -la` for each Projects-rooted file at authoring time (codeql.yml + pre-commit + legacy-file-gate.yml verified present; sizes captured in companion-files block).
- **Anchored citation:** every preflight evidence requirement uses anchored section/header + snippet match, not absolute line number alone. Specifically, Step 0 #3 uses **pure anchor+snippet** (title-line + §0 header + §0.1 changelog header), NOT fixed-line "first 20 lines" framing — closing the prior-session drift on PERIODIC v3 + payload validator v2 review where probe A returned PARTIAL.
- **Concise→full escalation (mandatory verbatim):** "If any required section cannot be evidenced, full mode is mandatory." (Verbatim in Step 2 prompt.)
- **Numeric AMEND_V2 thresholds (mandatory):** Tasks A, B, C, D have explicit numeric triggers (>50% combined FP, ≥1 unavailable input, wrong-PR-number edge case, >8 hr/week override burden); Task E is descriptive evaluation escalating per the standard rule.
- **No `task_description` in any prod_activity_log payload (LD-597):** the activity-log POST documented in §"Activity log POST" below uses ONLY the live `prod_activity_log` schema fields (`action_type`, `action_summary`, `session_phase`, `notes`, `details` JSON column, `created_at`); does NOT include `task_description` (LD-597 prohibits).

---

## Activity log POST (for the handoff author this turn)

The handoff author MUST log this handoff's authoring to `prod_activity_log` with the following pattern. Read-back per Rule 35.

**action_type:** `HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_V3_AUTHORED_V1`

**action_summary:** Authored DS-23/24/25 mechanical CI gate spec v3 Cursor cross-review handoff (HANDOFF_TEMPLATE_v2-compliant rewrite). Replaces prior v3 handoff (12:04 mtime) which had B PARTIAL + F MISSING + G MISSING per Cursor batch audit. Closes B (verbatim concise→full clause), F (HALT gates section with autonomous-mode reminder + 5 gates), G (Hard rules + Final report sections). v3 spec content (file path `..._v2.md`; content version v3) unchanged.

**session_phase:** `design_only`

**details (JSON dict):**
```json
{
  "spec_path": "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md",
  "spec_sha256": "52b227fe8f6d4f233cab82c6bbed22d6f5b30d3b7d130d0aecd00e24ee4a2024",
  "spec_size_bytes": 37834,
  "spec_content_version": "v3",
  "handoff_path": "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v3.md",
  "supersedes_handoff": "Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v3.md (12:04 mtime; HANDOFF_TEMPLATE_v2 compliance gaps B PARTIAL + F MISSING + G MISSING)",
  "structural_template": "Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md",
  "ld_filed": "HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_V3_TEMPLATE_COMPLIANT_V1",
  "anti_drift_fix_applied": "anchor+snippet stale-cache check at Step 0 #3 (NOT fixed-line first-20-lines framing); closes PERIODIC v3 + payload validator v2 probe-A PARTIAL drift",
  "ds_29_source_tags_applied": true,
  "ld_597_compliance": "no task_description field in this payload"
}
```

**notes:** Handoff author session is `gallant-bouman-804b4f`. Worktree-confusion gate respected (DS-27): all paths anchored to canonical root #1 (Dropbox); companion files on canonical root #2 (Projects) tagged inline. v2-content historical baseline (`..._v1.md`) verified preserved (sha256 + mtime) at preflight Gate 2.

**Read-back proof (Rule 35):** after POST, author runs `client.get_item("prod_activity_log", <new_id>)` and confirms the row's `action_type` + `action_summary` match the POST body. Read-back row id captured in §"Final report" §4 below.

---

## File LD POST (for the handoff author this turn)

| Field | Value |
|-------|-------|
| `decision_key` | `HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_V3_TEMPLATE_COMPLIANT_V1` |
| `decision_text` | Authority for the HANDOFF_TEMPLATE_v2-compliant rewrite of DS-23/24/25 v3 Cursor cross-review handoff. Replaces the prior v3 handoff (12:04 mtime) which had Cursor-batch-audit-flagged compliance gaps (B PARTIAL escalation logic without verbatim clause, F MISSING HALT gates section, G MISSING Hard rules + Final report sections). This rewrite closes B/F/G AND applies the anti-drift fix on Step 0 stale-cache check (anchor+snippet, NOT fixed-line first-20-lines framing) per the user's explicit directive. v3 spec content (file path `..._v2.md`; content version v3; sha256 `52b227fe8f6d4f233cab82c6bbed22d6f5b30d3b7d130d0aecd00e24ee4a2024`) unchanged. |
| `severity` | `SOFT` |
| `task_category` | `governance` |
| `enforcement_type` | `awareness_only` |
| `scope_domain` | `infra` |

**Read-back per Rule 35:** after POST, author confirms the LD row exists in `prod_locked_decisions` with the new id, then captures the id in §"Final report" §3 below.

---

## Specific questions Kim wants Cursor to answer regardless of verdict

1. **DS-25 trigger-model fix (the central v3 amendment).** Is the §7.3.1.A `on: pull_request` primary + §7.3.1.B `on: workflow_run` secondary split correct under GitHub Actions' documented event-payload semantics?
2. **MN_FRESH bypass vector.** Can a contributor abuse `MN_FRESH=1` by opening branches with multiple author identities? Mitigation?
3. **Phase E.5 vs Phase F sequencing.** Does inserting SKILL flip immediately after Phase D close the stale-doc window, or create a new ordering issue with `prod_blockers` row retirement?
4. **§11.2 threshold re-calibration directive.** Is `[INFERRED]` tag + Phase G recalibration mandate sufficient, or should v3 propose ranges?
5. **§7.3.1.B PR-from-fork edge case.** Does `gh api /repos/.../commits/<head_sha>/pulls` reliably return the PR number for fork PRs?

---

## Why this v3-rewrite handoff (delta vs prior v3 handoff at 12:04 mtime)

The prior v3 handoff (12:04 mtime, 24,724 bytes) drifted from `HANDOFF_TEMPLATE_v2` on three structural axes per Cursor's 2026-05-08 batch audit:

- **B PARTIAL:** escalation logic was present (concise mode authorized + ESCALATION TRIGGER paragraph) but missing the **verbatim** "If any required section cannot be evidenced, full mode is mandatory." clause. This rewrite places the verbatim clause in Step 2's prompt block under `CONCISE→FULL ESCALATION RULE`.
- **F MISSING:** no `## HALT gates` section (HANDOFF_TEMPLATE_v2 §"HALT gates" mandates this section + autonomous-mode reminder + gate enumeration). This rewrite adds a 5-gate enumeration with anchored evidence sources and explicit fail-action.
- **G MISSING:** no `## Hard rules` section AND no `## Final report` structure (HANDOFF_TEMPLATE_v2 §"Hard rules" + §"Final report" both mandate these sections). This rewrite adds both with the v2-required bullets (Rule 35, Rule 24, DS-19, DS-26, DS-27, DS-28, DS-29, companion path discipline, anchored citation, concise→full, numeric AMEND_V2 thresholds, LD-597 task_description prohibition).

Additionally, the user's explicit anti-drift directive on Step 0 stale-cache check is applied: **pure anchor+snippet** (title-line + §0 header + §0.1 changelog header), NOT fixed-line "first 20 lines" / "lines 1-20" framing. This closes the prior-session probe-A PARTIAL drift on PERIODIC v3 + payload validator v2 reviews.

The v3 SPEC content (file path `..._v2.md`) is NOT modified by this rewrite — it remains at sha256 `52b227fe8f6d4f233cab82c6bbed22d6f5b30d3b7d130d0aecd00e24ee4a2024`.

---

## Final report — required structure

Path: `Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_V3_REPORT_20260508.md` (authored by handoff author this turn after Directus writes complete) OR Cursor's review output saved to `Production/docs/CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v3.md` (authored by Cursor on review completion).

### Handoff-author final report (this turn)

Required sections:

1. **HALT gate scan results** — 5 gates (sha256 match, v2-baseline preserved, §0.1 changelog anchor, §7.3.1.A/B trigger-model anchors, Phase E.5 / §11.3 / §11.2 / §14.6 anchors) — per-gate state at handoff-authoring time (MET / NOT MET / N/A) with anchored evidence cited.
2. **Per-section diff (verbatim where load-bearing)** — what changed structurally vs prior v3 handoff (12:04 mtime). Specifically: HALT gates section added, Hard rules section added, Final report section added, concise→full verbatim clause added inside Step 2 prompt, anchor+snippet stale-cache check applied at Step 0 #3.
3. **Directus writes** — full LD POST body + read-back proof (LD row id captured); full activity-log POST body + read-back proof (row id captured); details dict per pattern; LD-597 compliance confirmed (no `task_description` field).
4. **Activity log row id** — verbatim row contents with row id captured.
5. **Confidence tags per Rule 24** — `[CONFIRMED]` for spec sha256 + companion-file existence + path-discipline; `[INFERRED]` for HANDOFF_TEMPLATE_v2 compliance gap classification (B/F/G) which derives from the user's prompt's stated Cursor batch audit result, not direct re-read of Cursor's audit output; `[GUESSED]` for any items not directly verified.
6. **Self-classification** — TRIVIAL / ROUTINE / **STANDARD-REVIEW-HANDOFF-AUTHORING** (this turn). Rationale: rewrite of an existing handoff to close template-compliance gaps; v3 SPEC content untouched; structural template (v6 schema migration handoff) mirrored; no doctrine change.
7. **Limitations** — what wasn't covered (Cursor's actual review verdict on v3 spec — Cursor will produce that on running Step 2; Directus writes may queue offline if Directus returns HTTP 500 per `feedback_desktop_no_hooks.md` doctrine, in which case the LD + activity-log row IDs land on queue replay).
8. **Cross-skill drift** — does the structural template inherited from v6 schema migration handoff require parallel updates to `mn-context` SKILL.md or `zero-error-qa` SKILL.md? Likely no — HANDOFF_TEMPLATE_v2 is canonical; this handoff inherits the canonical surface. Surface for Kim's review at session close.

### Cursor-reviewer final report (after Step 2)

Required sections:

1. **HALT gate scan results** — 5 gates (sha256 match, v2-baseline preserved, §0.1 changelog anchor, §7.3.1.A/B anchors, Phase E.5 / §11.3 / §11.2 / §14.6 anchors) — per-gate state with anchored evidence cited.
2. **Cursor verdict verbatim.**
3. **Per-task summary** — A (trigger criteria FP rate), B (coverage / mechanical detectability), C (CI integration / workflow_run vs pull_request), D (override-burden), E (sequencing), each with verdict + anchored evidence + numeric-threshold result where applicable.
4. **Q-NEW-1, Q-NEW-2, Q-NEW-3 new-blocker analysis** — each with verdict + anchored citation.
5. **Confidence tags per Rule 24.**
6. **Self-classification** — REVIEW (v3-scope tight; Cursor's classification of its own analysis).
7. **Limitations** — v2-baseline design surface intentionally excluded; live CodeQL alert state if unreachable; live Directus state if unreachable.
8. **Cross-skill drift** — does v3's `MN_FRESH=1` env-var pathway require parallel update to weekly_preflight_audit.py or zero-error-qa SKILL.md DS-23 sentinel discipline?
9. **Next-step recommendation.**

---

## Cross-references

- `LD DS_23_24_25_DISCIPLINE_STANDARDS_V1` (LD 580) — locks the discipline-only enforcement that this spec proposes to upgrade to mechanical.
- `LD DS_23_24_25_MECHANICAL_GATE_SPEC_V3_AMEND_V2_FIXES_V1` — v3 SPEC content authority (file at `..._v2.md`; content version v3).
- `LD HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_V3_TEMPLATE_COMPLIANT_V1` — **this handoff's authority** (filed 2026-05-08 same session as this rewrite).
- `LD GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1` (HANDOFF_TEMPLATE_v1 authority) + `LD WORKTREE_CONFUSION_PREVENTION_V1` (HANDOFF_TEMPLATE_v2 dual-canonical-paths authority).
- `LD-597` — prod_activity_log payload schema (no `task_description` field; this handoff complies).
- `Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508.md` — v1 prior review handoff (historical baseline).
- `Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md` — v2 prior review handoff (historical baseline; AMEND_V2 verdict drove v3 SPEC content).
- `Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md` — **v3 SPEC content** (file path `..._v2.md`; content version v3).
- `Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md` — v2-content historical baseline (file path `..._v1.md`; content version v2).
- `Production/docs/DS_23_24_25_V3_AMENDMENT_REPORT_20260508.md` — v3 amendment proof report (verbatim §7.3.1.A/B YAML + per-finding resolution table).
- `Production/docs/HANDOFF_DS23_24_25_IMPLEMENTATION_20260508.md` — implementation handoff consumed on AUTHORIZE_IMPLEMENTATION verdict.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` — structural template for this rewrite.
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure mandate (this rewrite conforms).
- `.claude/skills/zero-error-qa/SKILL.md` — DS-23/24/25 source rule definitions; DS-19, DS-26, DS-27, DS-28, DS-29 doctrine.

---

## §12 — Change log

- **v1** — 2026-05-08 08:48 — initial v1 handoff against v1-content spec (`..._v1.md`).
- **v2** — 2026-05-08 11:42 — v2 handoff against v2-content spec; HANDOFF_TEMPLATE_v2 partial compliance; Cursor returned AMEND_V2 driving v3-content amendments.
- **v3 (prior, 12:04 mtime)** — authored against v3-content spec (file at `..._v2.md`); HANDOFF_TEMPLATE_v2 compliance gaps per Cursor batch audit (B PARTIAL, F MISSING, G MISSING). Preserved as historical baseline at the prior file path until this rewrite supersedes in place.
- **v3 (this rewrite)** — 2026-05-08 — HANDOFF_TEMPLATE_v2-compliant rewrite. Closes B/F/G gaps. Applies anti-drift fix on Step 0 stale-cache check (anchor+snippet, NOT fixed-line first-20-lines). Mirrors v6 schema migration handoff structural template. Adds 5 HALT gates, Hard rules section with all v2-required bullets including DS-29 + LD-597 task_description prohibition, Final report structure (handoff-author this turn + Cursor-reviewer post-Step-2). v3 SPEC content (file at `..._v2.md`) unchanged. Author: Claude Opus 4.7 (1M context), session `gallant-bouman-804b4f`.

---

*End of HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v3.md (HANDOFF_TEMPLATE_v2-compliant rewrite).*
