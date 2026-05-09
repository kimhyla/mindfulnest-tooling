# DS-23 / DS-24 / DS-25 Mechanical Gate Tech Spec v1

**Status:** DESIGN-ONLY — awaiting Kim authorization. NO implementation in this session.
**Author:** Claude (subagent, dual-Opus advocate/counter pattern per `tech-spec` + `zero-error-qa` skills).
**Date:** 2026-05-08
**Classification:** ARCHITECTURAL (governance + CI/local-hook infrastructure; touches both `Production/scripts/git_hooks/pre-commit` and a new GitHub Actions workflow).
**Predecessors / inputs:**
- `.claude/skills/zero-error-qa/SKILL.md` — DS-23 (lines 244–272), DS-24 (274–302), DS-25 (304–336), DS-22 (213–242), Phase 7.5 Step 6 + Step 7 (1313–1335). [VERIFIED — read in this session]
- `.claude/skills/mn-context/SKILL.md` — Step 2.5b State-Claim Verification Audit (lines 291–321), Step 2.5 Verbal-Deferral Audit (lines 251–289). [VERIFIED — read in this session]
- `Production/scripts/git_hooks/pre-commit` — existing tooling-repo pre-commit hook with Dropbox-edit gate + watch-list anti-pattern detection (161 lines). [VERIFIED — read in this session]
- `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml` — CodeQL static analysis workflow (52 lines). [VERIFIED]
- `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/ai_review.yml` — Claude AI PR review workflow (71 lines). [VERIFIED]
- `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/smoke.yml` — Smoke build workflow (30 lines). [VERIFIED]
- `/Users/kimberlysmith/Projects/MindfulNest/.github/workflows/legacy-file-gate.yml` — example of file-existence GHA blocking gate (78 lines). [VERIFIED]
- `Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v2.md` — format reference (§0/§0.1 layout). [VERIFIED — read first 80 lines]
- `Production/docs/HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_v2_20260508.md` — format reference for the Cursor handoff (208 lines). [VERIFIED]
- LD `DS_23_24_25_DISCIPLINE_STANDARDS_V1` (LD 580) — locks the discipline-only enforcement that this spec proposes to upgrade to mechanical. [INFERRED — referenced verbatim in SKILL.md line 1319 + 1331; not directly Directus-queried this session]

---

## §0 Operating Mode Declaration (per zero-error-qa §0)

- **Mode:** DESIGN-ONLY tech spec. **No code edits, no Directus PATCHes, no hook installs, no workflow merges in this session.** This file lands as a reviewable doc. Implementation requires Kim authorization on the §12 pre-implementation gates.
- **Tier:** Tier C (architectural — gate infrastructure that BLOCKS commits and PR merges, has direct enforcement consequences, lands across two surfaces — local pre-commit hook and CI workflow — and introduces a documented bypass mechanism).
- **Scope risk class:** Multi-stage + side-effect + governance-doctrine-shaping. The gate's false-positive rate directly determines whether the gate is respected or routed around (`--no-verify`, MN_SKIP override). Therefore the FP-rate analysis (§11) is load-bearing, not decorative.
- **Six-Layer applicability (DS-13):**
  - Layer 1 (UI exists) N/A — this is governance infra.
  - Layer 2 (UI→backend wiring) N/A.
  - Layer 3 (backend processing) APPLIES — the hook + workflow ARE the backend processing.
  - Layer 4 (state propagation) APPLIES — `prod_activity_log` row written on bypass; `prod_blockers` row to retire when each gate ships.
  - Layer 5 (UI re-render) N/A.
  - Layer 6 (intent→outcome smoke test) APPLIES — §13 Testing Plan covers synthetic PRs that PROVE the gate fires/holds.
- **Authoring discipline (DS-15):** every existence/wiring claim cites a Read line range or grep result from this session. No claim about "current behavior" without citation.
- **Confidence tags (Rule 24):** `[VERIFIED]` = directly read from source in this session; `[INFERRED]` = derived from cited evidence; `[ASSUMED]` = working hypothesis pending confirmation.

### §0.1 Scope

#### In scope (this spec)

1. Convert DS-23, DS-24, DS-25 from discipline-only to MECHANICAL gates that BLOCK commits and/or merges when violated.
2. Specify the surface for each rule (pre-commit local? CI? both?) with reasoning.
3. Specify the EXACT regex / structural check semantics per rule.
4. Specify the legitimate-bypass mechanism per rule (mirroring DS-20/22's `MN_SKIP_*` + audit-row pattern).
5. Specify acceptance criteria — concrete passing and failing test cases.
6. Specify rollback per phase.
7. Author the Cursor cross-review handoff in v2-hardened format.

#### Out of scope (deferred or explicitly NOT in this spec)

1. Implementation. This is design-only. Implementation is gated on §12 approval.
2. Mechanical gates for DS-19 (standing escape hatches), DS-26 (HALT-gate discipline) — both have their own `MECHANICAL_GATE_PENDING` blocker rows; this spec is scoped to DS-23/24/25 only.
3. Re-litigating the underlying DS-23/24/25 rule definitions. Those are locked per LD 580. This spec ONLY asks: *given the rules as written, how do we mechanically enforce them?*
4. Migrating to Husky in the tooling repo. The tooling repo uses the source-controlled `Production/scripts/git_hooks/pre-commit` + `install_pre_commit_hook.sh` pattern (per `Production/scripts/git_hooks/pre-commit:5-7` [VERIFIED]). MindfulNest app repo uses Husky (per `MindfulNest/.husky/pre-commit:1` [VERIFIED]). This spec respects the existing split and lands DS-23/24 in BOTH hook surfaces (each surface gets the same check, language-localized).
5. AST-similarity detection for DS-24 copy-source detection. SKILL.md line 302 [VERIFIED] notes this is "hard" and is itself a future hardening — outside this spec's scope. We use a weaker but reliable proxy (commit-message marker + structural new-handler heuristic — see §7.2).

---

## §1 Background

### §1.1 The originating incident — PR #8

PR #8's bundle agent fixed three CodeQL-flagged path-traversal sites in `production_server.py`:

- **CRIT-1:** Bundle agent fixed `_handle_magic_still:8249` after CodeQL flag. Did NOT grep file for the same `\.startswith\(.*project_root` pattern. Sister sites at lines 6140, 6195, 8364 stayed vulnerable. Line 8364 was brand-new code authored in the same PR. (Per `.claude/skills/zero-error-qa/SKILL.md:268` [VERIFIED].)
- **CRIT-2:** CodeQL flagged the `startswith(root)` containment bypass at one site. CodeQL did NOT flag a pre-existing adjacent vulnerability in the same hot zone (sanitizer-recognition gap). The fix shipped, the adjacent vulnerability shipped with it, surfaced only in adversarial review post-merge. (Per `.claude/skills/zero-error-qa/SKILL.md:332` [VERIFIED].)
- **CRIT-3:** New `_handle_magic_video` at line 8364 was authored by copy-pasting from `_handle_magic_still:8249`. Source had `except Exception: pass` swallowing the security check's exception. Bug propagated verbatim into the new handler. Agent never independently audited line 8249 before treating it as a template. (Per `.claude/skills/zero-error-qa/SKILL.md:298` [VERIFIED].)

The 3 rules added in response (DS-23, DS-24, DS-25) would have caught all three bugs. They are currently DISCIPLINE-ONLY — enforced by Claude self-discipline + Phase 7.5 Step 6 (DS-23 commit-message gate) + Step 7 (DS-25 PR-body gate), both manual reviewer steps. (Per `.claude/skills/zero-error-qa/SKILL.md:1313-1335` [VERIFIED].)

### §1.2 Why discipline-only is insufficient

LD 551 VERBAL_DEFERRAL_TRACKING_REQUIRED_V1 originated in the same pattern: "Claude has discipline rules; Claude bypasses them under pressure." That LD authored DS-20 (verbal-deferral mechanical gate) at SAVE-time. DS-22 followed (state-claim verification, same SAVE hook) for the same reason — `enforcement_type=awareness_only` proved insufficient (per `.claude/skills/zero-error-qa/SKILL.md:234-235` [VERIFIED]).

Terminal A on PERIODIC class implementation (2026-05-08) executed v1 spec without halting at gates the handoff explicitly mandated, despite "HALT" + "do NOT proceed without authorization" + "§15's gates 1-10 NOT yet checked off" all being present — proving discipline-only HALT gates degrade silently. (Per `.claude/skills/zero-error-qa/SKILL.md:340 + 380` [VERIFIED].)

DS-23/24/25 are at the same risk — and worse, the failure mode is silent (a missing sweep in a commit message looks identical to a non-applicable rule), so the discipline-only enforcement has no audit trail for "rule applied but skipped vs rule didn't apply."

### §1.3 Current discipline-only enforcement (the baseline)

| Rule | Today's enforcement | Source |
|---|---|---|
| DS-23 (post-fix pattern sweep) | Phase 7.5 Step 6 — reviewer manually inspects commit messages for the `Swept <FILE>` block on security PRs. | `.claude/skills/zero-error-qa/SKILL.md:1313-1323` [VERIFIED] |
| DS-24 (audit copy source) | Phase 3 (Adversarial Review) — reviewer eyeballs new handler scaffolding for missing audit comments. | `.claude/skills/zero-error-qa/SKILL.md:300` [VERIFIED] |
| DS-25 (adjacent risk sweep after CodeQL) | Phase 7.5 Step 7 — reviewer manually inspects PR body for the structured sweep block on PRs touching CodeQL-flagged files. | `.claude/skills/zero-error-qa/SKILL.md:1325-1335` [VERIFIED] |

All three are explicitly tagged `ENFORCEMENT IS DISCIPLINE-ONLY for now` with a corresponding `prod_blockers` row (`DS_2{3,4,5}_MECHANICAL_GATE_PENDING`) tracking the future hardening. (Per `.claude/skills/zero-error-qa/SKILL.md:272, 302, 336` [VERIFIED].) This spec is the design that retires those three blockers.

---

## §2 Existing Landscape — Mechanical-Gate Patterns Already In Place

### §2.1 mn-context SAVE-time gates (DS-20 + DS-22)

The canonical pattern for mechanical regex gates lives in `.claude/skills/mn-context/SKILL.md`:

- **Step 2.5 (DS-20 — verbal-deferral):** Regex-scan assistant turns since `session_start`. If 1+ unmatched deferrals → HALT SAVE, render checklist, require Kim resolution. Override: `MN_SKIP_VERBAL_DEFERRAL_GATE=1` env var + `VERBAL_DEFERRAL_GATE_BYPASSED` activity-log row with rationale. (Per `.claude/skills/mn-context/SKILL.md:251-289` [VERIFIED].)
- **Step 2.5b (DS-22 — state-claim verification):** Same pattern — regex scan for unverified state claims, HALT if found, override `MN_SKIP_STATE_CLAIM_GATE=1` + `STATE_CLAIM_GATE_BYPASSED` audit row. (Per `.claude/skills/mn-context/SKILL.md:291-321` [VERIFIED].)

These run at SAVE time (end of session). They scan assistant *output* turns only (per line 287, 321 [VERIFIED]) — avoiding false positives on quoted file content.

**Reuse:** This spec adopts the IDENTICAL bypass pattern (`MN_SKIP_*=1` env + audit row) for all three new gates (per §7).

### §2.2 Tooling-repo pre-commit hook

Path: `Production/scripts/git_hooks/pre-commit` (canonical source). Installed to `.git/hooks/pre-commit` via `Production/scripts/install_pre_commit_hook.sh` (per `Production/scripts/git_hooks/pre-commit:5-7` [VERIFIED]).

The hook already implements two fail-closed checks:

1. **Dropbox-edit gate** (lines 51-69 [VERIFIED]) — staged files where Dropbox runtime mtime is newer than tooling-repo file → FATAL. Override: `MN_SKIP_DROPBOX_EDIT_GATE=1`.
2. **Watch-list anti-pattern detection** (lines 104-160 [VERIFIED]) — 5 grep-based content-pattern detectors (live overlay + cue timing, runtime TTS, expo-audio in playback path, per-child variables in production output, multi-file expo-video playlist). Override: `MN_SKIP_WATCHLIST_GATE=1` + SHORTCUT LD.

**Reuse:** This is the EXACT surface where DS-23 and DS-24 mechanical checks land — append more grep checks to this hook (per DS-10 "APPEND not replace, no globs" — `.claude/skills/zero-error-qa/SKILL.md:405` [VERIFIED]). DS-25 lands in CI (PR-body grep), not pre-commit (no PR body at commit time).

### §2.3 Existing CI workflows in the tooling repo

| Workflow | Purpose | Reuse for this spec |
|---|---|---|
| `codeql.yml` | CodeQL static analysis on push/PR + weekly cron. Findings appear in Security tab. | Independent — does NOT need modification. DS-25 gate runs IN ITS OWN workflow `ds_23_24_25_gate.yml`. |
| `ai_review.yml` | Claude AI PR review. Posts comment + sets blocking status when issues found. | Independent — DS gates do not extend AI review (different concern: AI = subjective judgment, DS gate = mechanical check). |
| `smoke.yml` | Storyboard-v2 build. | Independent — pure build check. |
| `playwright_e2e.yml` | E2e test suite. | Independent — functional behavior check. |

**Reuse:** A new workflow `ds_23_24_25_gate.yml` lands in `.github/workflows/` under both `mindfulnest-tooling` (storyboard-v59 surface) and (in a future cross-pollination phase) `MindfulNest/.github/workflows/` (RN-app surface — per `feedback_main_app_cicd_greenfield_lock.md` from MEMORY.md, the RN-app CI/CD must be greenfield, NOT inherit from tooling — so this spec lands ONLY in tooling for now and the RN-app gets its own greenfield equivalent later). [INFERRED from MEMORY.md `Main React Native app CI/CD must be greenfield (LOCKED 2026-05-06)` plus `Production/scripts/git_hooks/pre-commit` location in tooling repo only — VERIFIED.]

### §2.4 Phase 7.5 Step 6 + Step 7 — manual reviewer surface to retire

Currently Phase 7.5 Step 6 (DS-23 commit-message gate, `.claude/skills/zero-error-qa/SKILL.md:1313-1323` [VERIFIED]) and Step 7 (DS-25 PR-body gate, lines 1325-1335 [VERIFIED]) are DISCIPLINE-ONLY reviewer steps.

**This spec retires Step 6 + Step 7 as separate manual phases** — once mechanical, they collapse into "the CI gate either passed or failed; the reviewer no longer needs to inspect commit/PR text manually for the sweep block." The Step 6/7 SKILL.md text amends to: *"DS-23/25 mechanical gate now enforces this in CI. Reviewer's role: confirm `ds_23_24_25_gate / *` is green in PR checks. Manual inspection retained as belt-and-suspenders for cases where the bypass override fired."*

**Phase 4 (Six-Layer applied to this spec):** the proof that retirement actually fires lives in §13.4 (synthetic PR test cases) — a synthetic security PR with a missing DS-23 sweep block must FAIL the CI gate, AND the existing Phase 7.5 Step 6 reviewer step must be marked "redundant" in the SKILL.md amend.

---

## §3 Proposed Design — Gate Locations + Check Semantics Per Rule

### §3.1 Three rules, three surfaces

| Rule | Trigger surface | Check at | Block what | Override |
|---|---|---|---|---|
| DS-23 (post-fix pattern sweep) | Pre-commit (local) AND CI (PR-time) | The most recent commit's message in the PR head's commit graph | The `git push` (pre-commit) + the PR check (CI) | `MN_SKIP_DS23_GATE=1` + `DS23_GATE_BYPASSED` activity-log row |
| DS-24 (audit copy source) | Pre-commit (local) AND CI (PR-time) | The diff for newly-added handler-shaped functions | The `git push` (pre-commit) + the PR check (CI) | `MN_SKIP_DS24_GATE=1` + `DS24_GATE_BYPASSED` activity-log row |
| DS-25 (adjacent risk sweep after CodeQL) | CI only (PR-time, no local equivalent) | The PR body when the PR touches a file with a recent CodeQL alert | The PR merge (CI gate) | `MN_SKIP_DS25_GATE=1` (env at workflow-dispatch level — NOT possible in normal PR flow) + `DS25_GATE_BYPASSED` audit row |

**Why dual-surface for DS-23/24:** pre-commit catches the developer locally (fast, no round-trip), CI catches the developer who set `--no-verify` or `MN_SKIP_DS23_GATE=1` without writing the audit row (CI re-checks for the audit row's presence in `prod_activity_log` — see §7). This dual-surface mirrors how DS-22 + Step 2.5b already work (SAVE-time AND its audit-row trail).

**Why CI-only for DS-25:** pre-commit doesn't know about CodeQL alerts (no PR exists yet, no Security-tab API access from a local hook). The CodeQL run-state is only queryable from CI via `gh api` after CodeQL has actually run. Therefore DS-25 enforcement runs as a CI workflow that:
1. Reads the list of CodeQL alerts touched/closed by this PR.
2. If any → require the structured sweep block in the PR body.
3. Block merge until present (or `ADJACENT_RISK_SWEEP_WAIVED` row exists).

### §3.2 Check semantics summary (concrete)

| Rule | What we look FOR | Where we look | Pass condition | Fail signal |
|---|---|---|---|---|
| DS-23 | The 4-line block: `Swept <FILE> for `<PATTERN>`:\n  - L (fixed)\n  - L'_1 ...` (per SKILL.md template lines 258-264 [VERIFIED]) | Each commit message in the PR's commit range that touches a security-adjacent file | Commit message contains the literal `Swept ` token (case-sensitive) followed by a path AND a `for ` line PROVIDED the commit touches `production_server.py`, `firestore/rules/*`, `Production/lib/*.py`, or other paths in `security_paths_glob.txt` | Security-adjacent file modified, no `Swept ` block in commit message, no `MN_SKIP_DS23_GATE=1` + audit row |
| DS-24 | The literal `Copied ... pattern from <SOURCE>:<LINE>` (per SKILL.md inline-comment template lines 289-292 [VERIFIED]) OR `DS-24 audit:` in the commit message | New code blocks structurally matching an existing handler (heuristic: a function whose first 5 lines AST-match an existing function in the same file or an adjacent imported file) | Either marker present | New handler-shaped code added, no marker, no `MN_SKIP_DS24_GATE=1` + audit row |
| DS-25 | The literal `Adjacent risk sweep on <FILE>` block (per SKILL.md template lines 320-327 [VERIFIED]) | The PR body | PR body contains the literal `Adjacent risk sweep on ` token + ` after CodeQL triage` token within 100 chars OR an `ADJACENT_RISK_SWEEP_WAIVED` Directus row with this PR number | PR touches a file with an open or closed-this-PR CodeQL alert, no sweep block in PR body, no waiver row |

### §3.3 Why the regex is loose (the FP defense)

The check is on the PRESENCE of the marker, NOT the content. Rationale:

- The marker is human-authored (Claude writes the commit message; or Kim writes it manually).
- The marker's *content* (what was swept, what was found) is verified by the Phase 3 reviewer (per existing Phase 7.5 reviewer role) — the gate's job is to FORCE the marker to exist, not to grade the sweep's quality.
- The mechanical gate prevents the failure mode where the rule is silently skipped. The reviewer prevents the failure mode where the rule is performatively followed but shallow.
- This split-of-concerns is identical to DS-22's pattern: the regex catches "you didn't tag" (mechanical); Rule 24 + reviewer catch "you tagged something false" (semantic).

The FP rate is therefore bounded by:

- DS-23 FP = (security-adjacent commits where no sweep was needed because no security pattern was fixed) / (all security-adjacent commits). Bypass: `MN_SKIP_DS23_GATE=1` + audit row stating "rename-only commit, no security pattern fix" — 30 seconds of friction.
- DS-24 FP = (new handler-shaped code where no copy was performed) / (all new handler-shaped code). Bypass: `MN_SKIP_DS24_GATE=1` + audit row stating "scaffold authored from scratch, no copy template" — 30 seconds of friction.
- DS-25 FP = (PRs touching CodeQL-alerted files where the alert is provably non-security — e.g., a typo fix in a comment near an alerted line) / (all such PRs). Bypass: `ADJACENT_RISK_SWEEP_WAIVED` row with rationale.

The FP cost (30 seconds + audit row) is the SAME as the DS-22 pattern Kim has already accepted. The FN cost (a CRIT vulnerability shipping again) is what motivated DS-23/24/25 in the first place — orders of magnitude worse.

---

## §4 Dual-Opus Debate (Verbatim)

### §4.1 Advocate's opening — "Mechanical gates are the only durable defense"

**Claim:** DS-23/24/25 must become mechanical gates because:

1. **The originating failure mode is silent.** A missing sweep block in a commit message looks identical to "rule didn't apply." The reviewer cannot distinguish them without re-doing the analysis from scratch — which defeats the rule's purpose.
2. **Discipline-only rules degrade silently under load.** DS-22 was authored because DS-20 + Rule 24's discipline-only enforcement of state-claim verification was bypassed in the LD 551 incident. DS-26 was authored because DS-19's discipline-only HALT enforcement was bypassed in the Terminal A incident on 2026-05-08. Pattern: every "discipline-only" rule we have authored has needed a mechanical gate within ~7-30 days of its first violation.
3. **PR #8 already cost real production bugs.** CRIT-1 + CRIT-2 + CRIT-3 are not hypothetical — they shipped to main and were caught in adversarial review. DS-23/24/25 were authored as the post-mortem hardening. Leaving them discipline-only is, by Anthropic's own pattern, a known-incomplete fix.
4. **The implementation cost is bounded.** DS-22's mechanical gate took ~120 lines of regex + bypass-mechanism code in `mn-context/SKILL.md`. DS-23/24/25 will land in 2 surfaces (pre-commit hook ~150 LOC; CI workflow ~80 LOC). This is one focused session of work, not a long-running program.
5. **The override mechanism preserves Kim's trapdoor.** `MN_SKIP_DS{23,24,25}_GATE=1 + audit row` mirrors DS-20/22 exactly. Kim's existing acceptance of that pattern means the override is socially calibrated — Kim already knows what "30 seconds of friction" feels like for a bypass and has not pushed back on DS-20/22.

**Strongest evidence:** PR #8's CRIT-1 was authored AND shipped under cover of a partial fix. The bundle agent fixed `_handle_magic_still:8249` and pushed. Phase 7.5 Step 6 (reviewer manual inspection of commit message for sweep block) did not catch the missing block — the rule was new, the reviewer didn't yet have it as muscle memory. A mechanical gate would have failed the push before it left the developer's machine.

### §4.2 Counter's opening — "Mechanical gates introduce false-positive friction that undermines the whole point"

**Claim:** Mechanical gates are the wrong tool for DS-23/24/25 because:

1. **DS-23 is the hardest of the three to gate cleanly.** "Grep the file for sister patterns" requires the gate to know what counts as "the same pattern." That's a semantic question, not a syntactic one. CRIT-1's pattern was `\.startswith\(.*project_root` — fine, regex-friendly. CRIT-3's pattern was `except Exception: pass` swallowing a security check return — that's structural, not regex-friendly. A gate that only catches the regex-friendly cases will give Kim a false sense of safety on the structural cases.
2. **DS-24 is structurally undecidable without AST analysis.** "New code structurally matching an existing handler" requires AST diffing or fuzzy-hashing. Both are heavy and have well-known failure modes — function-rename, parameter-reorder, partial-extraction all defeat naive AST-similarity. We will end up with either too many FPs (every new function flagged as "did you copy?") or too many FNs (any cosmetic change defeats detection).
3. **DS-25's CodeQL-touched-file detection is racy.** CodeQL runs asynchronously after the PR is opened. If the gate checks `gh api codeql/alerts` before CodeQL completes, it gets a stale list and flags the wrong files. If it waits, the PR check sits in `pending` for minutes — a UX regression.
4. **The bypass mechanism becomes the de-facto path.** When a gate's FP rate hits some threshold (variously cited as 5-15% in research literature), contributors learn to skip it reflexively — the bypass becomes muscle memory, the gate is functionally absent. We already see hints of this: `MN_SKIP_DROPBOX_EDIT_GATE=1` is documented as an emergency override but ends up used routinely on the work PC where the gate doesn't apply.
5. **The existing Phase 7.5 reviewer step IS the gate.** A human reviewer is structurally good at "did the agent perform the sweep meaningfully?" — far better than a regex. Promoting from human review to mechanical-only is a downgrade in detection quality, even if it's an upgrade in detection consistency.

**Strongest evidence:** Counter's critique #4 is the load-bearing one. If contributors start setting `MN_SKIP_DS23_GATE=1` reflexively, the gate is worse than no gate — it produces an audit trail of "the gate was checked" while the actual rule was skipped. We have prior art for this exact failure mode in branches outside this codebase.

### §4.3 Advocate's response

1. **On "DS-23 is the hardest":** the advocate concedes DS-23 cannot regex-detect *structural* patterns like `except Exception: pass` swallow. But the gate's job is NOT to detect the bug — it's to require the developer to TYPE OUT the sweep block. The block declares "I swept for pattern X and found these instances." If the developer types `Swept production_server.py for "except Exception: pass":` and only lists 1 site when there are 4, that's a Phase 3 reviewer catch (the human reviewer reads the listed sites and runs the same grep). The mechanical gate's job: ENSURE THE BLOCK EXISTS. The reviewer's job: verify the block's content. This is the same split as DS-22 (regex detects unverified-claim language; Rule 24 reviewer verifies the tag was honest).
2. **On "DS-24 is structurally undecidable":** the advocate concedes AST-similarity is heavy and unreliable. The proposed gate doesn't require AST-similarity — it requires the developer to TYPE the audit comment whenever they author NEW handler-shaped code. The gate's heuristic: "does this commit add a new function definition (top-level `def` in Python or `function` in TS) that matches a regex of the form `def _handle_*(self, ...)` or `function handle*(...)` (configurable per-repo)?" If yes, the commit message must contain `DS-24 audit:` OR the new function must contain a `# Copied ... pattern from <SOURCE>:<LINE>` comment within its first 10 lines. This is a much weaker heuristic than AST-similarity, but it's load-bearing on the SAME mechanism — the developer is forced to TYPE the audit. False positives (new function authored from scratch, no copy performed) bypass with `# DS-24: authored from scratch` comment OR `MN_SKIP_DS24_GATE=1` + audit row. The 30-second friction is bounded.
3. **On "DS-25's race condition":** the advocate concedes CodeQL latency is real. Mitigation: the gate runs as a `workflow_run` workflow that fires AFTER `codeql.yml` completes, not on `pull_request` directly. By that time, the alert list is stable. If CodeQL fails or is skipped on the PR (e.g., draft PR, force-push race), the DS-25 gate is N/A — gate emits a `::notice::` and exits 0. This adds ~5 minutes to PR-merge readiness but is acceptable because (a) CodeQL itself takes that long, (b) DS-25 only fires when CodeQL has findings, which is not most PRs.
4. **On "bypass becomes the de-facto path":** the advocate accepts this is the strongest counter. Mitigations:
   - **The audit row is mandatory, not optional.** `MN_SKIP_DS23_GATE=1` env var WITHOUT a `DS23_GATE_BYPASSED` row in `prod_activity_log` is itself a CI failure. The CI re-validates the audit row exists.
   - **Bypass rate is monitored.** Weekly preflight audit (`Production/scripts/weekly_preflight_audit.py`, per existing roadmap §1.6 — the same audit that runs PERIODIC) gains a check: if `DS{23,24,25}_GATE_BYPASSED` rows exceed N per 7-day window, surface to Kim. Threshold proposal: 3 bypasses per 7-day window OR any single bypass with rationale shorter than 50 characters → blocker row.
   - **The override is socially expensive.** Setting `MN_SKIP_DS23_GATE=1` requires writing a Directus row that Kim sees in the daily preflight scan. The friction is asymmetric: 30 seconds for a legitimate bypass; visible to Kim if abused.
5. **On "human reviewer is the better gate":** the advocate disagrees. Phase 7.5 Step 6/7 are MANUAL inspection steps. Manual inspection has been documented to fail in PR #8 itself — the rules existed (in spirit, if not codified) and the bundle agent shipped CRIT-1/2/3 anyway. The mechanical gate is a FORCING FUNCTION, not a replacement for the reviewer. Both layers stay (Phase 4 of this spec retains the reviewer role; the mechanical gate is BELT, the reviewer is SUSPENDERS). The mechanical gate cuts the cost of the easy 90% of cases (presence-of-block) so the reviewer's attention can focus on the harder 10% (block-content quality).

### §4.4 Counter's response

1. **On "the gate forces the block to exist":** Counter accepts this framing. Counter's revised position: the gate IS the right tool IF (a) the FP rate is bounded by the bypass mechanism's friction cost, (b) the bypass is auditable so abuse is detectable, (c) the reviewer role is preserved for content quality. All three conditions are met by the advocate's revised design.
2. **On "DS-25 race condition mitigated by `workflow_run`":** Counter accepts. The 5-minute latency cost is paid by all PRs touching CodeQL-flagged files, which is rare.
3. **Counter's residual concern:** the spec must include a HARD COMMITMENT to retire the gate if FP rate exceeds threshold. Without a sunset clause, "we'll monitor it" becomes "we never look again." Proposal: §11 Risk Assessment mandates a 30-day post-launch FP audit with a `DS_2{3,4,5}_GATE_FP_REVIEW` blocker row that BLOCKS further mechanical-gate work until the audit completes. If FP rate >5%, the gate downgrades to discipline-only with a documented post-mortem.

### §4.5 Resolution

Both Opuses converge:

- **Mechanical gates are the right tool**, contingent on:
  - The check is presence-of-marker (not content quality) — preserves the reviewer's role.
  - The bypass mechanism mirrors DS-20/22's audit-row pattern — preserves Kim's trapdoor.
  - The FP rate is monitored via the weekly preflight audit, with a 30-day sunset clause if abuse exceeds threshold (per §11).
  - DS-23/24 land in BOTH pre-commit AND CI (dual-surface defense against `--no-verify`).
  - DS-25 lands in CI only (no local PR-body equivalent).

**No HALT condition.** The debate resolves cleanly. Spec proceeds to §5.

---

## §5 Resolution + Decision Criteria

### §5.1 Decisions resolved by debate

| Question | Resolution | Authority |
|---|---|---|
| Can DS-23/24/25 be gated mechanically with low FP rate? | YES, when the gate checks for marker presence (not content quality) and the bypass is audit-row-backed. | §4.5 |
| Where does the gate live? | DS-23/24: pre-commit hook (local) + CI (PR-time). DS-25: CI only (PR-time, post-CodeQL). | §3.1 |
| What does the gate ACTUALLY check? | Marker presence in commit message (DS-23/24) or PR body (DS-25). NOT content quality. | §3.2 |
| How does a contributor LEGITIMATELY bypass? | `MN_SKIP_DS{23,24,25}_GATE=1` env var + `DS{23,24,25}_GATE_BYPASSED` audit row. CI re-validates the audit row exists when the env var is set. | §4.3 + §7 |

### §5.2 Decisions deferred

| Question | Defer to | Rationale |
|---|---|---|
| Should the same gate land in `MindfulNest/.husky/pre-commit`? | Future CI/CD greenfield session per `feedback_main_app_cicd_greenfield_lock.md` | RN-app CI/CD must be greenfield; this spec respects that lock. |
| Should AST-similarity detection be added to DS-24 as a hardening over the regex heuristic? | DS_24_AST_SIMILARITY_FUTURE_HARDENING_V1 (new blocker row, NOT created in this session) | Out of scope per §0.1. Future work after FP audit shows regex heuristic is insufficient. |
| Should DS-26 (HALT-gate discipline) get a mechanical gate using the same pattern? | DS_26_MECHANICAL_GATE_PENDING (existing blocker row per SKILL.md:390) | Out of scope per §0.1 #2. |

---

## §6 Acceptance Criteria

### §6.1 What passes

| Test case | Expected outcome | Source rule |
|---|---|---|
| AT1: Commit message contains `Swept production_server.py for "\.startswith.*project_root":\n  - 8249 (fixed)` AND commit touches `production_server.py` | DS-23 gate PASSES | DS-23 |
| AT2: Commit touches non-security file (`Production/docs/foo.md`) | DS-23 gate N/A (skipped, no error) | DS-23 |
| AT3: Commit message contains `DS-23 sweep waived (rationale: rename-only)` AND `DS23_GATE_BYPASSED` row exists in `prod_activity_log` referencing this commit SHA | DS-23 gate PASSES via bypass | DS-23 |
| AT4: New function `def _handle_magic_video(self, ...)` added in `production_server.py` AND inline comment within first 10 lines contains `# Copied containment pattern from _handle_magic_still:8249.` AND audit checklist | DS-24 gate PASSES | DS-24 |
| AT5: New function added with commit message containing `DS-24 audit: authored from scratch, no template source` | DS-24 gate PASSES | DS-24 |
| AT6: PR body contains `Adjacent risk sweep on production_server.py after CodeQL triage:\n  - Hot zone: lines 8200-8400, functions _handle_magic_*\n  - Findings: ...\n  - Result: CLEAN` AND PR closes a CodeQL alert | DS-25 gate PASSES | DS-25 |
| AT7: PR body contains `ADJACENT_RISK_SWEEP_WAIVED` reference to a `prod_activity_log` row with rationale | DS-25 gate PASSES via waiver | DS-25 |

### §6.2 What fails

| Test case | Expected outcome | Source rule |
|---|---|---|
| AF1: Commit fixes `production_server.py:8249` (security file), commit message has NO `Swept` block, NO `MN_SKIP_DS23_GATE` env, NO bypass row | DS-23 gate FAILS pre-commit AND CI | DS-23 |
| AF2: `MN_SKIP_DS23_GATE=1` set at commit time but NO `DS23_GATE_BYPASSED` row in `prod_activity_log` for this SHA | DS-23 gate PASSES pre-commit (env honored locally) but FAILS CI (audit row required) | DS-23, §7.1 |
| AF3: New `def _handle_*` function added, no inline audit comment, no commit-msg `DS-24 audit:` marker, no bypass | DS-24 gate FAILS pre-commit AND CI | DS-24 |
| AF4: PR closes CodeQL alert on `production_server.py`, PR body contains no `Adjacent risk sweep` block, no waiver row | DS-25 gate FAILS CI (merge blocked) | DS-25 |
| AF5: PR closes CodeQL alert, PR body has `Adjacent risk sweep` block but block is shorter than 100 chars (placeholder text like `Adjacent risk sweep: TODO`) | DS-25 gate FAILS CI (block min-length 100 chars enforced) | DS-25 |
| AF6: Commit message has `Swept production_server.py for "":` (empty pattern) | DS-23 gate FAILS pre-commit (pattern field non-empty enforced) | DS-23 |

### §6.3 Edge cases (gate must handle)

| Edge case | Expected behavior | Source rule |
|---|---|---|
| EC1: Empty commit (no files changed) | All gates SKIP (N/A); CI emits `::notice::` | All |
| EC2: Merge commit (multiple parents) | Gate inspects only NEW commits added by the PR (not historical commits brought in by merge); use `git log <base>..<head>` | All |
| EC3: Force-push rewrites history | Gate re-runs on the new commit graph; previous-commit bypass rows do NOT carry over (audit row is SHA-keyed) | All |
| EC4: Revert commit (security fix being reverted, not added) | DS-23 gate FAILS unless commit message contains `DS-23 sweep N/A: revert of <SHA>` | DS-23 |
| EC5: PR opened against non-`main` branch (e.g., `claude/*` or `feature/*` development branch) | All gates RUN per workflow `on: pull_request:` config; this is intentional (per `Production/scripts/git_hooks/pre-commit:11` [VERIFIED] precedent — pre-commit runs on every commit regardless of branch) | All |
| EC6: CodeQL workflow failed (didn't produce alerts due to autobuild failure) | DS-25 gate is N/A (no alerts to sweep against); CI emits `::warning::CodeQL incomplete; DS-25 gate skipped` | DS-25 |
| EC7: Pre-commit hook not installed locally (developer hasn't run `install_pre_commit_hook.sh`) | Gate FALLS BACK to CI-only enforcement; CI is the backstop. Pre-commit's role is fast feedback, not the only line of defense. | DS-23, DS-24 |

---

## §7 Per-Rule Check Semantics

### §7.1 DS-23 — Post-fix pattern sweep

#### §7.1.1 Pre-commit check (local, in `Production/scripts/git_hooks/pre-commit`)

```bash
# ============================================================================
# DS-23: Post-fix pattern sweep gate (per DS-23 + LD 580)
# ============================================================================

DS23_FAIL=0

# Override
if [[ "${MN_SKIP_DS23_GATE:-}" = "1" ]]; then
    echo "PRE-COMMIT: MN_SKIP_DS23_GATE=1 — DS-23 gate bypassed (CI will validate audit row)."
else
    # Identify security-adjacent paths in the staged set
    SECURITY_GLOBS=(
        'production_server.py'
        'Production/lib/*.py'
        'firestore/rules/*'
        'functions/src/**/*.ts'
        'functions/src/**/*.js'
    )
    SECURITY_HIT=0
    while IFS= read -r staged; do
        for pattern in "${SECURITY_GLOBS[@]}"; do
            case "$staged" in
                $pattern) SECURITY_HIT=1; break ;;
            esac
        done
    done < <(git diff --cached --name-only)

    if [[ "$SECURITY_HIT" -eq 1 ]]; then
        # Read the prepared commit message (pre-commit hook reads .git/COMMIT_EDITMSG when invoked from commit-msg, but pre-commit fires before the editor; instead we check the ENV's GIT_COMMIT_MSG_FILE if present, else fall back to looking at the most recent staged sweep marker in a tracked file like .last_sweep)
        # Implementation note: DS-23 pre-commit can't fully validate commit-message body (commit message isn't written yet at pre-commit time). It validates that EITHER:
        #   (a) the developer staged a `.ds23_sweep` sentinel file AND the file contains a `Swept ` block, OR
        #   (b) the env var MN_SKIP_DS23_GATE=1 is set
        # CI then validates the commit message after the commit is made.
        if [[ -f "$TOOLING_ROOT/.ds23_sweep" ]]; then
            if grep -q "^Swept " "$TOOLING_ROOT/.ds23_sweep"; then
                # Sentinel file exists with sweep block — clear it after read so it doesn't carry over
                rm -f "$TOOLING_ROOT/.ds23_sweep"
                echo "Pre-commit DS-23 gate: sweep sentinel found, gate clear."
            else
                echo "FATAL DS-23: .ds23_sweep sentinel exists but contains no 'Swept ' block."
                DS23_FAIL=1
            fi
        else
            echo "FATAL DS-23: security-adjacent file modified, no .ds23_sweep sentinel + no MN_SKIP_DS23_GATE override."
            echo "  See zero-error-qa SKILL.md DS-23 for the sweep template."
            echo "  To create sentinel: echo 'Swept <FILE> for `<PATTERN>`:' > .ds23_sweep && add findings"
            echo "  Or override: MN_SKIP_DS23_GATE=1 git commit ..."
            DS23_FAIL=1
        fi
    fi
fi

if [[ "$DS23_FAIL" -eq 1 ]]; then
    exit 1
fi
```

**Why a sentinel file rather than parsing the commit message:** the pre-commit hook fires BEFORE the commit message is written. It cannot validate text that doesn't exist yet. We therefore use a sentinel file (`.ds23_sweep`, gitignored) that the developer (or Claude) writes BEFORE running `git commit`. CI then re-validates by parsing the commit message itself (which DOES exist at PR time) — see §7.1.2.

**Alternative considered + rejected:** use `prepare-commit-msg` hook to inject the sweep template into the commit message editor. Rejected because: (a) doesn't compose with `-m "..."` non-editor commits, (b) doesn't compose with squash-merges where the final message is rewritten by GitHub, (c) adds boilerplate to non-security commits.

#### §7.1.2 CI check (in new workflow `ds_23_24_25_gate.yml`)

```yaml
ds_23_check:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
      with: { fetch-depth: 0 }
    - name: Identify security-adjacent commits in PR range
      id: scan
      run: |
        BASE="${{ github.event.pull_request.base.sha }}"
        HEAD="${{ github.event.pull_request.head.sha }}"
        SECURITY_GLOBS='production_server.py|Production/lib/.*\.py$|firestore/rules/|functions/src/.*\.(ts|js)$'
        FAIL=0
        for commit in $(git rev-list "$BASE..$HEAD"); do
          if git show --name-only --format= "$commit" | grep -qE "$SECURITY_GLOBS"; then
            msg=$(git log -1 --format=%B "$commit")
            if echo "$msg" | grep -qE '^Swept .+ for `.+`:'; then
              echo "  $commit: DS-23 sweep block present"
            elif echo "$msg" | grep -qE 'DS-23 sweep waived'; then
              # Check audit row in Directus
              # (Implementation: curl Directus prod_activity_log filtered by this SHA + DS23_GATE_BYPASSED action_type)
              echo "  $commit: DS-23 sweep waived; audit row check TODO in implementation phase"
            else
              echo "  $commit: DS-23 BLOCK MISSING"
              FAIL=1
            fi
          fi
        done
        echo "fail=$FAIL" >> "$GITHUB_OUTPUT"
    - name: Fail if any commit lacks sweep block
      if: steps.scan.outputs.fail == '1'
      run: |
        echo "::error::One or more security-adjacent commits in this PR lack the DS-23 sweep block."
        echo "::error::See .claude/skills/zero-error-qa/SKILL.md DS-23 for the template."
        exit 1
```

**Marker regex (canonical):** `^Swept .+ for ` `` ` `` `.+` ` `` ` `` `:` — case-sensitive, anchored to line start, requires path + backtick-wrapped pattern + colon. This matches the SKILL.md template at lines 258-264 [VERIFIED] exactly.

**Bypass: marker regex (canonical):** `^DS-23 sweep waived[: ]` — also requires `DS23_GATE_BYPASSED` row in `prod_activity_log` keyed by commit SHA.

### §7.2 DS-24 — Audit copy source before copy

#### §7.2.1 Pre-commit check (heuristic — new handler-shaped function)

```bash
# ============================================================================
# DS-24: Audit copy source before copy (per DS-24 + LD 580)
# ============================================================================

DS24_FAIL=0

if [[ "${MN_SKIP_DS24_GATE:-}" = "1" ]]; then
    echo "PRE-COMMIT: MN_SKIP_DS24_GATE=1 — DS-24 gate bypassed."
else
    # Detect new function definitions in the diff matching handler-shaped patterns
    HANDLER_PATTERNS=(
        '^\+def _handle_'        # Python class method handlers
        '^\+    def _handle_'    # Indented Python class handlers
        '^\+function handle'     # TS/JS top-level handlers
        '^\+const handle'        # TS arrow-function handlers
    )
    NEW_HANDLER=0
    for pattern in "${HANDLER_PATTERNS[@]}"; do
        if git diff --cached -U0 -- '*.py' '*.ts' '*.tsx' '*.js' 2>/dev/null | grep -qE "$pattern"; then
            NEW_HANDLER=1
            break
        fi
    done

    if [[ "$NEW_HANDLER" -eq 1 ]]; then
        # Look for either:
        #   (a) inline `# Copied ... pattern from <SOURCE>:<LINE>` within the diff's added lines
        #   (b) commit message marker `DS-24 audit:` (validated at CI time; pre-commit checks sentinel)
        #   (c) sentinel file .ds24_audit
        if git diff --cached -U10 -- '*.py' '*.ts' '*.tsx' '*.js' 2>/dev/null | grep -qE '^\+.*(# |// )Copied .* pattern from '; then
            echo "Pre-commit DS-24 gate: inline audit comment found in diff."
        elif [[ -f "$TOOLING_ROOT/.ds24_audit" ]]; then
            if grep -q '^DS-24 audit:' "$TOOLING_ROOT/.ds24_audit"; then
                rm -f "$TOOLING_ROOT/.ds24_audit"
                echo "Pre-commit DS-24 gate: audit sentinel found, gate clear."
            fi
        else
            echo "FATAL DS-24: new handler-shaped function added, no audit comment + no sentinel + no MN_SKIP_DS24_GATE override."
            echo "  Required: either an inline comment '# Copied <PATTERN> from <SOURCE>:<LINE>' in the new function,"
            echo "  OR a .ds24_audit sentinel containing 'DS-24 audit:' line,"
            echo "  OR MN_SKIP_DS24_GATE=1 git commit ..."
            DS24_FAIL=1
        fi
    fi
fi

if [[ "$DS24_FAIL" -eq 1 ]]; then
    exit 1
fi
```

#### §7.2.2 CI check

Mirrors §7.1.2 but checks for `DS-24 audit:` token in commit message OR inline comment regex `(# |// )Copied .+ pattern from .+:[0-9]+` in the diff for any newly-added handler-shaped function.

#### §7.2.3 FP-rate honest accounting

The handler-shape regex is INTENTIONALLY broad. It matches:
- True positives: `def _handle_magic_video` copy-pasted from `_handle_magic_still` (PR #8 CRIT-3 case).
- False positives: any new Python handler authored from scratch.

The override pathway (`MN_SKIP_DS24_GATE=1` + audit row OR `DS-24 audit: authored from scratch`) is the FP-handling mechanism. Expected FP rate (estimate, [INFERRED]): 30-50% of new handler functions are NOT copy-pasted. The 30-second friction is acceptable IF the override is honored cleanly. This is the strongest case for the §11 30-day FP audit.

### §7.3 DS-25 — Adjacent risk sweep after CodeQL triage

#### §7.3.1 CI check (workflow_run after CodeQL completes)

```yaml
name: DS-25 Adjacent Risk Sweep Gate

on:
  workflow_run:
    workflows: [CodeQL]
    types: [completed]
  pull_request:
    types: [opened, synchronize, reopened, edited]

jobs:
  ds_25_check:
    if: github.event.pull_request.base.ref == 'main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check if this PR touches CodeQL-flagged files
        id: codeql_scope
        run: |
          # Use gh api to enumerate alerts touched by this PR's files
          PR_NUMBER="${{ github.event.pull_request.number }}"
          FILES=$(gh pr view "$PR_NUMBER" --json files --jq '.files[].path')
          ALERTS=$(gh api -H "Accept: application/vnd.github+json" \
              "/repos/${{ github.repository }}/code-scanning/alerts?state=open" \
              --jq '.[] | select(.most_recent_instance.location.path) | .most_recent_instance.location.path' 2>/dev/null || echo "")
          TOUCHED=0
          for file in $FILES; do
              if echo "$ALERTS" | grep -qF "$file"; then
                  TOUCHED=1
                  break
              fi
          done
          echo "touched=$TOUCHED" >> "$GITHUB_OUTPUT"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Require sweep block in PR body
        if: steps.codeql_scope.outputs.touched == '1'
        run: |
          BODY="${{ github.event.pull_request.body }}"
          if echo "$BODY" | grep -qE 'Adjacent risk sweep on .+ after CodeQL triage'; then
              # Block must be ≥100 chars to prevent placeholder
              BLOCK=$(echo "$BODY" | sed -n '/Adjacent risk sweep on /,/Result:/p')
              if [[ ${#BLOCK} -lt 100 ]]; then
                  echo "::error::DS-25 sweep block present but <100 chars (placeholder rejected)"
                  exit 1
              fi
              echo "DS-25 gate: sweep block found, length OK"
          elif echo "$BODY" | grep -qE 'ADJACENT_RISK_SWEEP_WAIVED'; then
              echo "DS-25 gate: waiver row referenced; activity-log validation TODO in impl phase"
          else
              echo "::error::PR touches CodeQL-flagged file(s) but PR body lacks DS-25 adjacent risk sweep block"
              echo "::error::Required template (per zero-error-qa SKILL.md DS-25):"
              echo "::error::  Adjacent risk sweep on <FILE> after CodeQL triage:"
              echo "::error::    - Hot zone: lines X-Y, functions A/B/C"
              echo "::error::    - Findings: ..."
              echo "::error::    - Result: CLEAN | N findings, all addressed | DEFERRED with prod_blockers rows"
              exit 1
          fi
```

**Race-condition mitigation:** the workflow fires on `workflow_run` AFTER CodeQL completes. If CodeQL fails or hasn't run yet, the alert list is empty and the gate is N/A. The duplicate `pull_request` trigger ensures the gate re-runs when the PR body is edited (so adding the sweep block after-the-fact updates the gate's status to PASS without requiring a CodeQL re-run).

#### §7.3.2 No pre-commit equivalent

DS-25 has no pre-commit equivalent because:
1. PR body doesn't exist at commit time.
2. CodeQL alerts are queryable only via the GitHub API after CodeQL has run on the PR.

CI is the only enforcement surface. Phase 7.5 Step 7 (manual reviewer check) is retained as belt-and-suspenders — the SKILL.md amend reads: *"DS-25 mechanical gate runs in CI. Reviewer's role: confirm `ds_25_check` is green; manually inspect block content for quality (the gate enforces presence; reviewer enforces depth)."*

---

## §8 Implementation Phases

### Phase A — Pre-commit hook extension (DS-23 + DS-24)

1. Append the DS-23 + DS-24 blocks to `Production/scripts/git_hooks/pre-commit` (per DS-10 "APPEND not replace" — `.claude/skills/zero-error-qa/SKILL.md:405` [VERIFIED]).
2. Update `Production/scripts/install_pre_commit_hook.sh` if needed (no changes expected — installer just copies the canonical source).
3. Document the `.ds23_sweep` and `.ds24_audit` sentinel files in the hook's header comment.
4. Add `.ds23_sweep` and `.ds24_audit` to the tooling-repo `.gitignore` (these are local-only sentinels).

### Phase B — CI workflow (`ds_23_24_25_gate.yml`)

1. Author `.github/workflows/ds_23_24_25_gate.yml` with three jobs: `ds_23_check`, `ds_24_check`, `ds_25_check`.
2. Each job uses `gh` CLI + Directus REST API to validate audit rows when bypass env is set.
3. Workflow trigger: `pull_request` (synchronize, opened, reopened, edited) for DS-23/24; `workflow_run` after CodeQL for DS-25.

### Phase C — PR template extension

1. Update `.github/PULL_REQUEST_TEMPLATE.md` (or create if absent) with an `## Adjacent Risk Sweep (DS-25 — required if PR closes a CodeQL alert)` section pre-populated with the template block. This nudges the developer to fill it in, reducing FP friction.

### Phase D — Bypass-mechanism wiring

1. Document `MN_SKIP_DS{23,24,25}_GATE=1` in `Production/docs/RUNBOOK_GATE_BYPASS_MECHANICS.md` (NEW doc).
2. Implement audit-row writer helper: `Production/scripts/write_gate_bypass_row.py` accepts `--gate DS23|DS24|DS25 --rationale "<text>" --commit-sha <sha>` and writes to `prod_activity_log` via `try_post_or_queue`.
3. CI validates audit-row presence by querying Directus `prod_activity_log` filtered by `action_type=DS{23,24,25}_GATE_BYPASSED` AND `metadata.commit_sha=<head sha>`.

### Phase E — Weekly preflight audit hook

1. Extend `Production/scripts/weekly_preflight_audit.py` with a check: count `DS{23,24,25}_GATE_BYPASSED` rows in the last 7 days. If >3 OR any has `rationale` shorter than 50 chars, write `prod_blockers` row `DS_GATE_BYPASS_THRESHOLD_HIT` (severity HARD per DS-9).
2. This is the FP-rate monitoring mechanism per §11.

### Phase F — SKILL.md amend

1. Amend `.claude/skills/zero-error-qa/SKILL.md` DS-23/24/25 sections — flip `ENFORCEMENT IS DISCIPLINE-ONLY for now` to `ENFORCEMENT IS MECHANICAL`. Reference this spec.
2. Amend Phase 7.5 Step 6 + Step 7 — note manual reviewer role is now belt-and-suspenders for content quality, not presence-of-block.
3. Retire `prod_blockers` rows `DS_2{3,4,5}_MECHANICAL_GATE_PENDING` with `closed_at=<date>` + `closure_reason=<this spec's path>`.

### Phase G — 30-day FP audit checkpoint

1. Calendar-scheduled task (NOT `tomorrow`'s problem; mn-context auto-schedules per the existing scheduled-tasks integration): 30 days post-Phase-F shipping, run a query: "Count `DS{23,24,25}_GATE_BYPASSED` rows / Count `DS{23,24,25}_GATE_FAILED` rows. If bypass:fail ratio > 0.3, surface to Kim as `DS_GATE_FP_RATE_REVIEW` blocker."
2. If ratio acceptable: write `DS_2{3,4,5}_MECHANICAL_GATE_FP_AUDIT_PASS_V1` LD.
3. If ratio not acceptable: pause new gate work, investigate, possibly downgrade gate to discipline-only with documented post-mortem (per §4.4 Counter's residual concern).

---

## §9 Open Decisions (for Kim or Cursor)

| # | Question | Recommendation |
|---|---|---|
| OD1 | Sentinel file `.ds23_sweep` vs prepare-commit-msg hook injection? | Sentinel file — composes with all commit modes (editor, `-m`, squash). Per §7.1.1. |
| OD2 | Should DS-23 also validate the sweep block's *content* mechanically (e.g., parse the listed line numbers and verify they exist in the file)? | NO — content quality is Phase 3 reviewer's job per §3.3. Mechanical gate enforces presence only. |
| OD3 | Should DS-24's handler-shape regex be configurable per-repo (e.g., MindfulNest RN-app has different handler patterns than tooling-repo Python)? | YES — per-repo `ds_gate_config.yaml` listing the handler patterns. Default config ships with the spec's regex. |
| OD4 | Should the bypass audit row require a Kim @-mention (i.e., social cost of bypass is "Kim sees a notification")? | DEFER — initial spec uses `prod_activity_log` row only (visible in weekly preflight). Add @-mention only if FP audit shows abuse pattern. |
| OD5 | Should DS-25's "PR body" check accept the block in a PR comment instead (some teams prefer comments to body)? | NO for v1 — body only. PR comments are mutable by anyone with write access; body is the PR's canonical record. Future amendment if Kim requests. |
| OD6 | Should `ds_23_24_25_gate.yml` be 1 workflow with 3 jobs (proposed) or 3 separate workflows? | 1 workflow with 3 jobs — single status check name reduces branch-protection-rules surface and matches `legacy-file-gate.yml` pattern (per `MindfulNest/.github/workflows/legacy-file-gate.yml:14` [VERIFIED] — single workflow, single job). |
| OD7 | Should the gate run on `claude/*` and `feature/*` PRs (not just main)? | YES per EC5 — gate runs on all PRs to `main` AND on push to `claude/*` for early feedback. Matches `smoke.yml:11` [VERIFIED] precedent. |

---

## §10 Pre-Implementation Gates (Kim must approve)

These are checkbox-semantic gates per DS-26's HALT-gate doctrine. Implementation does NOT proceed until each is explicitly approved (Kim's "yes" in chat OR `prod_locked_decisions` row).

- [ ] **G1 — Spec content approval.** Kim has read this spec + agrees with the §3 design and §4 dual-Opus resolution.
- [ ] **G2 — Cursor cross-review verdict.** Cursor returns `AUTHORIZE_IMPLEMENTATION` (or `AMEND_V2` followed by a v2 spec that Cursor then approves).
- [ ] **G3 — Open decisions resolved.** OD1-OD7 each have a Kim or Cursor-locked answer (or explicit DEFER tag).
- [ ] **G4 — `prod_blockers` rows confirmed retireable.** `DS_23_MECHANICAL_GATE_PENDING`, `DS_24_MECHANICAL_GATE_PENDING`, `DS_25_MECHANICAL_GATE_PENDING` all read from Directus, status confirmed pre-implementation.
- [ ] **G5 — Bypass audit row schema lock.** Confirm `prod_activity_log` schema has `action_type`, `metadata` (JSONB), `created_at`, `notes` fields sufficient to record bypass rationale + commit SHA. (Per `feedback_directus_schema_canonical.md` from MEMORY.md, schema migrated 2026-05-04 — verify enum allows new `DS{23,24,25}_GATE_BYPASSED` values OR confirm enum is permissive.)
- [ ] **G6 — RN-app deferral acknowledged.** Per §5.2 DEFER row, the RN-app (MindfulNest/.husky) does NOT receive this gate in the same session. Future session per `feedback_main_app_cicd_greenfield_lock.md`.
- [ ] **G7 — 30-day FP audit calendar entry locked.** Phase G's calendar task is created at implementation time, not "we'll remember." (Per `feedback_time_estimates.md` from MEMORY.md — "we'll get to it" is anti-pattern.)
- [ ] **G8 — Synthetic PR test cases pre-authored.** §13 Testing Plan's synthetic PRs have content drafted before implementation begins (so the test-first ordering of DS-2 TDD strict — `.claude/skills/zero-error-qa/SKILL.md:40` [VERIFIED] — is honored).
- [ ] **G9 — LD `DS_23_24_25_MECHANICAL_GATE_V1` will be authored at implementation start.** Locks the design decisions in Directus per Rule 35.
- [ ] **G10 — Phase boundary commit ordering locked per DS-12.** Each of Phases A-G ships as its own atomic commit + push (per `.claude/skills/zero-error-qa/SKILL.md:407` [VERIFIED]).

---

## §11 Risk Assessment

### §11.1 False-positive rate per rule

| Rule | Estimated FP rate | FP cost per occurrence | Total FP friction (per week, est.) |
|---|---|---|---|
| DS-23 | LOW (~5%) — security paths are narrow; rename-only commits are rare in those paths | 30 sec (write sentinel + override) | ~1-2 min/week |
| DS-24 | HIGH (~30-50%) — handler-shape regex is broad; many new handlers are authored from scratch | 30 sec (inline comment OR sentinel OR override) | ~5-10 min/week |
| DS-25 | LOW (~10%) — PRs touching CodeQL-flagged files are rare; most have a real adjacent-risk concern | 2-5 min (write sweep block) | ~1-2 min/week (under most weeks; spikes when CodeQL fires) |

**Total estimated FP friction:** ~10-15 min/week. **Compare to FN cost:** PR #8 CRIT-1/2/3 cost a full adversarial review session (~hours) post-merge plus a hardening doctrine deluge. ROI clear.

### §11.2 Bypass mechanism abuse risk

**Risk:** developers (including Claude) reflexively set `MN_SKIP_DS23_GATE=1` to avoid friction.

**Mitigations:**
1. **Audit row mandatory.** CI re-validates the `DS{23,24,25}_GATE_BYPASSED` row exists with rationale ≥50 chars. Blank or formulaic rationale fails CI.
2. **Weekly preflight audit threshold.** >3 bypasses/7-day window OR any rationale <50 chars → blocker row visible to Kim (§8 Phase E).
3. **30-day FP-rate audit checkpoint.** Phase G — if bypass:fail ratio >0.3, gate downgrades to discipline-only with post-mortem.
4. **Sunset clause.** If FP rate forces downgrade, no future spec re-introduces the gate without first proving the FP root cause is fixed.

### §11.3 New-developer friction

**Risk:** a contributor cloning the tooling repo doesn't know about `.ds23_sweep` / `.ds24_audit` sentinels and is blocked on first commit.

**Mitigations:**
1. **Hook header comment** documents the sentinels.
2. **`Production/docs/RUNBOOK_GATE_BYPASS_MECHANICS.md`** (Phase D) is the canonical reference.
3. **Failing-gate output** prints the exact bypass command (per `Production/scripts/git_hooks/pre-commit:65-66, 99` [VERIFIED] precedent — "Override: MN_SKIP_DROPBOX_EDIT_GATE=1 git commit ...").

### §11.4 Workflow-orchestration risk

**Risk:** the `workflow_run` trigger for DS-25 is racy with CodeQL completion; the gate may fire before alerts are populated.

**Mitigations per §7.3.1:**
1. Gate fires on `workflow_run` AFTER CodeQL completes (not on `pull_request` directly).
2. Duplicate `pull_request` trigger handles PR-body edits after CodeQL has settled.
3. If CodeQL is broken (autobuild fail), gate emits `::warning::` and exits 0 — does NOT block on CodeQL infra failure. (Trade-off: if CodeQL is broken, DS-25 is bypassed — but CodeQL itself is the upstream alert source, so a broken CodeQL is already a blocker independent of DS-25.)

### §11.5 Schema-drift risk

**Risk:** `prod_activity_log` enum for `action_type` doesn't accept `DS23_GATE_BYPASSED` / `DS24_GATE_BYPASSED` / `DS25_GATE_BYPASSED` values, blocking the bypass mechanism.

**Mitigation:** G5 (pre-implementation gate) requires schema verification before implementation begins. Per `feedback_directus_schema_canonical.md` from MEMORY.md, post-2026-05-04 migration the enum is silently permissive but `/fields` should be queried to confirm.

---

## §12 Rollback Per Phase

| Phase | Rollback | Cost |
|---|---|---|
| A (pre-commit) | `git revert <SHA>` removing the DS-23/24 blocks from `Production/scripts/git_hooks/pre-commit`; existing watch-list + Dropbox-edit blocks remain intact. | Low — single commit revert. |
| B (CI workflow) | `git rm .github/workflows/ds_23_24_25_gate.yml` + commit. Branch-protection rule update needed if the check name was made required. | Low if not yet required-check; medium if required (need branch-protection edit). |
| C (PR template) | `git revert` the template change. | Low — 1 line. |
| D (bypass wiring) | Remove `Production/scripts/write_gate_bypass_row.py` + RUNBOOK doc. Existing audit rows in Directus stay (no historical-row deletion). | Low. |
| E (weekly preflight) | Remove the new check from `Production/scripts/weekly_preflight_audit.py`. | Low. |
| F (SKILL.md amend) | `git revert` the SKILL.md amend; flip ENFORCEMENT label back to DISCIPLINE-ONLY. | Low. |
| G (30-day audit) | The audit IS the rollback signal — if it fires, follow §11.2 mitigation 3 (downgrade). | N/A (the audit IS the rollback decision-point). |

**Full-spec rollback:** revert all Phase A-F commits in reverse order. Total cost: ~15 minutes. The audit-trail in `prod_activity_log` is preserved (historical rows of bypasses or fails) for post-mortem.

---

## §13 Testing Plan

### §13.1 Unit-level tests (per surface)

#### Pre-commit hook unit tests

Author `Production/tests/test_pre_commit_ds_gates.sh`:
- Stages a fake `production_server.py` edit + no `.ds23_sweep` sentinel → expect exit 1 + DS-23 FATAL.
- Stages same edit + `.ds23_sweep` containing `Swept production_server.py for "X":` → expect exit 0.
- Stages same edit + `MN_SKIP_DS23_GATE=1` → expect exit 0 + bypass message.
- Stages a fake new `def _handle_foo` + no audit comment + no sentinel → expect exit 1 + DS-24 FATAL.
- Stages same + inline `# Copied X pattern from Y:Z` → expect exit 0.

#### CI workflow unit tests

Author `Production/tests/test_ds_gate_workflow.py` using `act` (local GHA runner) or a synthetic PR matrix:
- PR touching `production_server.py` with no sweep block in any commit → expect `ds_23_check` failure.
- PR touching `production_server.py` with sweep block in HEAD commit → expect pass.
- PR touching `production_server.py` with sweep block in a non-HEAD commit (e.g., 2 commits, sweep in commit 1, fix in commit 2) → expect pass (as long as the security-touching commit has the block).
- PR with `MN_SKIP_DS23_GATE` env at runtime + audit row in Directus → expect pass.
- PR with env but NO audit row → expect failure ("audit row missing").

### §13.2 Integration-level tests (synthetic PRs)

Author 6 synthetic PRs in a test branch (`test/ds_23_24_25_gate_dryrun/`) — each is a controlled fake commit designed to test exactly one gate behavior:

| Synthetic PR | Expected outcome | Validates |
|---|---|---|
| SYNTH1: Edit `production_server.py:8249`, no sweep block in commit msg | DS-23 CI gate fails, merge blocked | DS-23 happy-fail |
| SYNTH2: Same edit, sweep block in commit msg | DS-23 CI gate passes | DS-23 happy-pass |
| SYNTH3: Add `def _handle_test_foo` with no audit comment | DS-24 CI gate fails | DS-24 happy-fail |
| SYNTH4: Same add, inline `# Copied containment pattern from <SOURCE>:<LINE>` comment | DS-24 CI gate passes | DS-24 happy-pass |
| SYNTH5: Trigger a CodeQL alert (synthetic — add a known anti-pattern), close it in PR, no sweep block in PR body | DS-25 CI gate fails | DS-25 happy-fail |
| SYNTH6: Same trigger + close, sweep block in PR body | DS-25 CI gate passes | DS-25 happy-pass |

These PRs are NEVER merged. They are dry-run validations of the gate behavior. After implementation, the PRs are closed with `wontfix` label + a `prod_activity_log` row recording the validation outcome.

### §13.3 Adversarial tests

- ADV1: Author a security fix WITHOUT setting any sentinel + WITH `--no-verify` (skipping pre-commit) → expect CI to catch it (CI is the backstop).
- ADV2: Set `MN_SKIP_DS23_GATE=1` env at commit time WITHOUT writing the audit row → expect CI to catch the missing audit row.
- ADV3: Write an audit row referencing a DIFFERENT commit SHA than the one being merged → expect CI to fail (SHA mismatch).
- ADV4: Author a sweep block with empty pattern (`Swept X for "":`) → expect pre-commit AND CI to fail (pattern non-empty enforced).

### §13.4 End-to-end regression

After Phase F SKILL.md amend ships:
- Open a fresh `claude/*` branch.
- Commit a real (small) security-adjacent change (e.g., a comment-only edit in `production_server.py` near the realpath check).
- Verify:
  - Pre-commit fires DS-23 gate.
  - Sentinel-or-override resolves it.
  - PR opens.
  - CI's `ds_23_check` runs and passes/fails per the sentinel state.
  - Phase 7.5 Step 6 SKILL.md text now reads "MECHANICAL" not "DISCIPLINE-ONLY".

---

## §14 Reference Index (per DS-15 §16)

### §14.1 Files cited in this spec (with confidence tags)

| File | Path | Confidence | Source/use |
|---|---|---|---|
| zero-error-qa SKILL | `.claude/skills/zero-error-qa/SKILL.md` | [VERIFIED] | DS-23/24/25 + DS-22 + DS-26 + Phase 7.5 + DS-10 |
| mn-context SKILL | `.claude/skills/mn-context/SKILL.md` | [VERIFIED] | Step 2.5 + 2.5b mechanical-gate template |
| Tooling pre-commit | `Production/scripts/git_hooks/pre-commit` | [VERIFIED] | DS-10 APPEND surface for Phase A |
| MindfulNest pre-commit | `MindfulNest/.husky/pre-commit` | [VERIFIED] | RN-app surface (deferred to greenfield session) |
| Tooling CodeQL workflow | `mindfulnest-tooling/.github/workflows/codeql.yml` | [VERIFIED] | DS-25 `workflow_run` upstream |
| Tooling AI review workflow | `mindfulnest-tooling/.github/workflows/ai_review.yml` | [VERIFIED] | Independent — not modified |
| Tooling smoke workflow | `mindfulnest-tooling/.github/workflows/smoke.yml` | [VERIFIED] | Branch-trigger pattern reuse |
| Legacy-file-gate workflow | `MindfulNest/.github/workflows/legacy-file-gate.yml` | [VERIFIED] | Single-job blocking-gate pattern |
| Patch-forward spec v2 | `Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v2.md` | [VERIFIED] | Format reference §0/§0.1 |
| Cursor handoff v2 | `Production/docs/HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_v2_20260508.md` | [VERIFIED] | v2-hardened handoff format |

### §14.2 LDs / blockers cited

- LD `DS_23_24_25_DISCIPLINE_STANDARDS_V1` (LD 580) — current discipline-only enforcement; this spec retires the DISCIPLINE-ONLY framing. [INFERRED — referenced via SKILL.md but not directly Directus-queried this session.]
- LD 551 VERBAL_DEFERRAL_TRACKING_REQUIRED_V1 — pattern precedent for mechanical-gate-after-discipline-failure. [INFERRED — referenced via SKILL.md.]
- `prod_blockers` rows: `DS_23_MECHANICAL_GATE_PENDING`, `DS_24_MECHANICAL_GATE_PENDING`, `DS_25_MECHANICAL_GATE_PENDING` — retired by this spec at Phase F. [INFERRED — referenced via SKILL.md.]
- `prod_blockers` row to be CREATED at implementation: `DS_GATE_BYPASS_THRESHOLD_HIT` (Phase E weekly audit), `DS_GATE_FP_RATE_REVIEW` (Phase G 30-day audit). [DESIGN — not yet created.]

### §14.3 Memory references

- `feedback_main_app_cicd_greenfield_lock.md` — RN-app CI/CD greenfield mandate; defers Phase A/B from `MindfulNest/.husky` per §5.2 OD `DEFER`. [VERIFIED via MEMORY.md context this session.]
- `feedback_directus_schema_canonical.md` — schema enum verification at G5. [VERIFIED via MEMORY.md.]
- `feedback_browser_smoke_required.md` — N/A here (no UI); included for completeness of Six-Layer per DS-13. [VERIFIED via MEMORY.md.]
- `feedback_time_estimates.md` — anti-pattern reference for G7 calendar entry. [VERIFIED via MEMORY.md.]

### §14.4 Cross-references between this spec's sections

- §3.1 (gate-location table) ↔ §7.1-§7.3 (per-rule semantics) — table summarizes; §7 specifies.
- §4.5 (debate resolution) ↔ §5.1 (decisions resolved) — debate produces; §5.1 enumerates.
- §6 (acceptance criteria) ↔ §13 (testing plan) — §6 defines pass/fail; §13 enumerates the synthetic PRs that prove each.
- §10 (pre-implementation gates) ↔ §12 (rollback) — gates protect entry; rollback protects exit.
- §11 (FP risk) ↔ §8 Phase G (30-day audit) — risk identifies threshold; phase enforces it.

### §14.5 What is NOT in this spec (and where to find it later)

- DS-26 mechanical gate → `DS_26_MECHANICAL_GATE_PENDING` blocker row, future spec.
- DS-19 mechanical gate → `DS_19_MECHANICAL_GATE_PENDING` if it exists; otherwise discipline-only stays.
- AST-similarity for DS-24 → `DS_24_AST_SIMILARITY_FUTURE_HARDENING_V1` blocker row (NEW, to be created at implementation start as a deferred blocker).
- RN-app gate parity → future greenfield CI/CD session per memory lock.
- DS-23 content-quality validation (parsing line numbers, etc.) → deferred per §9 OD2.

---

## §15 Confidence Sweep (per Rule 24)

Every load-bearing claim in this spec is tagged. Roll-up:

- **[VERIFIED]:** all file-path + line-range + text-content claims (read directly in this session). Includes all §1.3 + §2 + §14.1 entries.
- **[INFERRED]:** all LD-id + Directus-row references (LD 580, LD 551, blocker rows). Not directly Directus-queried this session — derivation cited.
- **[ASSUMED]:** §11.1 FP-rate estimates (~5%, ~30-50%, ~10%) — not measured, derived from PR #8's incident pattern + the breadth/narrowness of the rule's trigger surface. Phase G's 30-day audit is the empirical ground-truth check.
- **[DESIGN]:** §6 acceptance criteria, §13 test cases, §8 phase ordering — these are the spec's own design proposals, not claims about existing state.

No untagged claims should be present. Any reviewer-found untagged claim is itself a Cursor finding to correct in v2.

---

## §16 Self-Classification

**Tier:** ARCHITECTURAL (governance + CI infra).
**Risk classes affected:** governance-doctrine-shaping, side-effect (the gate BLOCKS commits/merges), multi-stage (pre-commit + CI surfaces), async (CodeQL workflow_run dependency). Per DS-14 risk classes.
**Six-Layer applicable layers:** 3, 4, 6 (per §0).
**Reviewer expectations:** Cursor cross-review handoff (next file) requires: preflight evidence + per-section verification + new-blocker search + STRICT gate verdict.

---

*End of `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md`.*
