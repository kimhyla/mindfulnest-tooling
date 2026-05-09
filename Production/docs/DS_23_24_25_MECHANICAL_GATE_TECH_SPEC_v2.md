# DS-23 / DS-24 / DS-25 Mechanical Gate Tech Spec v2

**Status:** DESIGN-ONLY — awaiting Kim authorization. NO implementation in this session.
**Author:** Claude (subagent, dual-Opus advocate/counter pattern per `tech-spec` + `zero-error-qa` skills).
**Date:** 2026-05-08 (v2 authored 2026-05-08 in response to Cursor's v1 review.)
**Classification:** ARCHITECTURAL (governance + CI/local-hook infrastructure; touches both `Production/scripts/git_hooks/pre-commit` and a new GitHub Actions workflow).
**Predecessor (v1 baseline, retained):** `Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md` — preserved verbatim as historical baseline. v2 ONLY supersedes the four sections enumerated in §0.1; all other v1 sections carry forward by reference.

**Predecessors / inputs (preserved from v1):**
- `.claude/skills/zero-error-qa/SKILL.md` — DS-23/24/25 + DS-22 + Phase 7.5 Step 6 + Step 7. [VERIFIED in v1]
- `.claude/skills/mn-context/SKILL.md` — Step 2.5 + 2.5b mechanical-gate template. [VERIFIED in v1]
- `Production/scripts/git_hooks/pre-commit` — existing tooling-repo hook. [VERIFIED in v1]
- `mindfulnest-tooling/.github/workflows/codeql.yml` — CodeQL static analysis. [VERIFIED in v1]
- `mindfulnest-tooling/.github/workflows/ai_review.yml` — Claude AI PR review. [VERIFIED in v1]
- `mindfulnest-tooling/.github/workflows/smoke.yml`. [VERIFIED in v1]
- `MindfulNest/.github/workflows/legacy-file-gate.yml`. [VERIFIED in v1]
- LD `DS_23_24_25_DISCIPLINE_STANDARDS_V1` (LD 580). [INFERRED in v1]

**v2-specific input (NEW):**
- Cursor's AMEND_V2 verdict on v1 (2026-05-08) — surfaced 2 HIGH (HIGH-1 workflow_run trigger payload mismatch; HIGH-2 sentinel-file integrity gap) + 2 MED (MED-1 TODO bypass-validation; MED-2 DS-24 FP churn) findings. v2 addresses each. [VERIFIED — quoted in §0.1 below.]
- GitHub Actions documentation on `workflow_run` event payload behavior — `workflow_run` payload does NOT carry `pull_request.*` fields the same way `pull_request` events do; PR context must be resolved via `gh api commits/<sha>/pulls`. [INFERRED from Cursor finding HIGH-1 + standard GHA docs precedent.]

---

## §0 Operating Mode Declaration (per zero-error-qa §0)

- **Mode:** DESIGN-ONLY tech spec. **No code edits, no Directus PATCHes, no hook installs, no workflow merges in this session.** v2 lands as a reviewable doc; implementation requires Kim authorization on the §10 pre-implementation gates (preserved from v1).
- **Tier:** Tier C (architectural — gate infra that BLOCKS commits/PR merges, has direct enforcement consequences, lands across two surfaces).
- **Scope risk class:** Multi-stage + side-effect + governance-doctrine-shaping. v2's amendments specifically target the failure modes Cursor surfaced — gate runtime correctness (HIGH-1), audit-trail integrity (HIGH-2), bypass-policy completeness (MED-1), FP-flap thresholding (MED-2).
- **Six-Layer applicability (DS-13):** unchanged from v1 — Layers 3, 4, 6 apply.
- **Authoring discipline (DS-15):** every v2 amendment cites either a v1 line range OR Cursor's quoted finding. No new claims about existing system state without citation.
- **Confidence tags (Rule 24):** `[VERIFIED]` carries forward from v1 for unchanged sections; `[INFERRED]` for derivations from Cursor's findings; `[ASSUMED]` for FP-rate estimates pending Phase G empirical audit; `[DESIGN]` for v2's own proposed semantics.

### §0.1 v2 Changelog — Cursor v1-review amendments applied

Cursor's review of v1 returned **AMEND_V2** with 2 HIGH (BLOCKERS) + 2 MED non-blocker findings. v2 addresses each below. v1 sections are preserved verbatim except where a finding required a targeted insert/replace.

| # | Cursor finding (severity) | v1 lines cited | v2 section addressing it |
|---|---------------------------|----------------|--------------------------|
| HIGH-1 | DS-25 workflow_run trigger payload mismatch. v1 §7.3.1 triggers on `workflow_run` after CodeQL completion (lines 483–493) but reads `github.event.pull_request.number` (lines 500–501). The `workflow_run` payload does NOT carry `pull_request.*` fields. DS-25 will skip or break in the exact mode designed to avoid CodeQL race conditions. | 483–493, 500–501 | §7.3.1 (NEW v2) — trigger model fix: keep dual `pull_request` + `workflow_run` triggers; resolve PR context via a `Resolve PR context` step that branches on `$GITHUB_EVENT_NAME` and uses `gh api /repos/<owner>/<repo>/commits/<head_sha>/pulls` for `workflow_run` mode. New edge-case audit row `DS_25_NO_PR_CONTEXT` for SHAs pushed direct to main with no PR. |
| HIGH-2 | DS-23 sentinel file integrity. v1 §7.1.1 lines 337–341 use ephemeral `.ds23_sweep` deleted after read; CI later validates commit-message audit-row checks (lines 386–389) but TODO. No deterministic linkage between local sentinel content and final commit message. Local pass mostly advisory. | 337–341, 386–389 | §7.1.1 (NEW v2) — replace ephemeral `.ds23_sweep` with commit-message-anchored evidence: pre-commit hook appends `Swept:` / `Verified:` lines to `$1` (the commit message file), evidence rides IN the commit. CI reads `gh api commits/<sha>` `.commit.message` and validates the block mechanically. No ephemeral file. |
| MED-1 | TODOs in load-bearing bypass paths. v1 lines 528–530 (DS-25 bypass) + lines 386–389 (DS-23 audit) defer audit-row verification as TODO. Bypass-abuse prevention has a policy gap exactly where override abuse is expected. | 528–530, 386–389 | §7.1.2 + §7.3.1 (NEW v2) — replace TODOs with concrete `curl Directus → jq → exit 1 if missing` snippets. Audit-row count check is mechanical; missing row fails CI; rationale length and SHA-match enforced. |
| MED-2 | DS-24 30-50% FP churn. v1 lines 474–475 acknowledge HIGH FP rate; lines 634–636 estimate 5–10 min/week override burden. Operationally erodes trust + normalizes bypass use unless thresholds + reporting implemented immediately at launch (not 30 days later). | 474–475, 634–636 | §11.2 + Phase E (NEW v2) — explicit halt-on-flap threshold: >5 sweep-needed events in 24h on the same file → halt + surface (likely FP loop). Weekly preflight aggregates DS-24 trigger counts; >50% override rate flags for tuning at week 1, not week 4. |

**No HALT condition raised by Cursor.** v2 proceeds as a targeted amendment, not a re-debate of §4.

### §0.2 Scope (preserved verbatim from v1 §0.1)

In-scope and out-of-scope items unchanged. See v1 §0.1.

### §0.3 What changes in v2 vs v1

| Section | v1 status | v2 status |
|---|---|---|
| §1 Background | Preserved | Preserved by reference |
| §2 Existing landscape | Preserved | Preserved by reference |
| §3 Gate locations + check semantics | Preserved | Preserved by reference (table is unchanged) |
| §4 Dual-Opus debate | Preserved | Preserved by reference |
| §5 Resolution | Preserved | Preserved by reference |
| §6 Acceptance criteria | Preserved | Preserved by reference |
| §7.1.1 DS-23 pre-commit semantics | v1 sentinel design | **REPLACED by §7.1.1 (v2)** — commit-message-anchored evidence |
| §7.1.2 DS-23 CI check | v1 had TODO on audit-row | **REPLACED by §7.1.2 (v2)** — concrete Directus query |
| §7.3.1 DS-25 CI workflow YAML | v1 had `workflow_run` payload bug | **REPLACED by §7.3.1 (v2)** — `Resolve PR context` step + branching `gh api commits/<sha>/pulls` lookup |
| §8 Implementation phases | Preserved A–G | **AMENDED Phase E (NEW v2)** — adds DS-24 24h flap threshold + week-1 reporting hook |
| §11 Risk assessment | Preserved | **AMENDED §11.2** — explicit thresholds for DS-24 FP churn + early reporting |
| §14 Reference index | Preserved | **AMENDED §14** — adds v1 historical baseline + LD-NEW (v2's own LD) + v2 self-reference |
| §0.1 Changelog | (no changelog) | **NEW v2-A row above** any future v3-A row |
| §7 Risk rows | Preserved | **NEW** — 4 risk rows added covering the four Cursor defect classes |
| §12 Changelog (v1 final entry) | (none) | **APPENDED** — v2 entry per §12 below |

All v1 sections not enumerated above are preserved verbatim by reference. No content silently changed.

---

## §1 Background — preserved verbatim from v1 §1

(See `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md` §1.1, §1.2, §1.3.)

---

## §2 Existing Landscape — preserved verbatim from v1 §2

(See v1 §2.1 mn-context SAVE-time gates, §2.2 tooling-repo pre-commit, §2.3 existing CI workflows, §2.4 Phase 7.5 Step 6 + Step 7.)

---

## §3 Proposed Design — preserved verbatim from v1 §3

(See v1 §3.1 three-rules-three-surfaces table, §3.2 check-semantics summary, §3.3 FP-defense rationale.)

---

## §4 Dual-Opus Debate — preserved verbatim from v1 §4

(See v1 §4.1 advocate, §4.2 counter, §4.3 advocate response, §4.4 counter response, §4.5 resolution.)

---

## §5 Resolution + Decision Criteria — preserved verbatim from v1 §5

(See v1 §5.1 decisions resolved, §5.2 decisions deferred.)

---

## §6 Acceptance Criteria — preserved verbatim from v1 §6

(See v1 §6.1 what passes, §6.2 what fails, §6.3 edge cases. v2 retains all 7 AT, 6 AF, 7 EC test cases. New v2-specific test cases are added in §6.4 below.)

### §6.4 v2-additional acceptance criteria

| Test case | Expected outcome | Source rule | Cursor finding addressed |
|---|---|---|---|
| AT8 (v2): Commit fixes `production_server.py` and pre-commit hook appends `Swept:` + `Verified:` lines INTO the commit message; CI reads commit message via `gh api commits/<sha> --jq .commit.message` and finds the block | DS-23 gate PASSES end-to-end (no ephemeral file gap) | DS-23 | HIGH-2 |
| AT9 (v2): PR triggered via `workflow_run` after CodeQL completes; `Resolve PR context` step queries `gh api /repos/<owner>/<repo>/commits/<head_sha>/pulls` and resolves PR number; subsequent steps use `${{ steps.pr.outputs.pr_number }}` | DS-25 gate executes correctly under `workflow_run` mode | DS-25 | HIGH-1 |
| AT10 (v2): SHA pushed directly to main with no PR open; `gh api commits/<sha>/pulls` returns empty array | DS-25 gate skips with explicit `DS_25_NO_PR_CONTEXT` audit row written, exit 0 | DS-25 | HIGH-1 |
| AT11 (v2): `MN_SKIP_DS23_GATE=1` set + commit message contains `DS-23 sweep waived` AND `prod_activity_log` contains `DS_23_GATE_BYPASSED` row with `details._contains $COMMIT_SHA` | DS-23 CI gate PASSES via concrete bypass-row query | DS-23 | MED-1 |
| AT12 (v2): `MN_SKIP_DS23_GATE=1` set + NO `DS_23_GATE_BYPASSED` row referencing this SHA | DS-23 CI gate FAILS with explicit "no audit row referencing this SHA" message (no TODO fallback) | DS-23 | MED-1 |
| AT13 (v2): Same file `production_server.py` triggers DS-24 gate >5 times within 24h | Gate halts on the 6th and emits `DS_24_FP_LOOP_SUSPECTED` blocker row visible to Kim same day | DS-24 | MED-2 |
| AF7 (v2): Pre-commit hook does NOT append `Swept:` / `Verified:` lines to commit message AND security file modified | Pre-commit fails AND CI verifies commit message has no block (no ephemeral file means CI's view IS the source of truth) | DS-23 | HIGH-2 |

---

## §7 Per-Rule Check Semantics

### §7.1 DS-23 — Post-fix pattern sweep

#### §7.1.1 Pre-commit check (REPLACED in v2 — commit-message-anchored evidence)

**v1 design:** ephemeral `.ds23_sweep` sentinel file written by developer pre-commit, read + deleted by hook, CI later checks commit message (TODO).

**Cursor HIGH-2 finding:** the local sentinel file is deleted after the hook reads it, and CI's commit-message validation was a TODO. There is no deterministic linkage between what the local hook saw and what landed in the commit message. The local pass is mostly advisory; an attacker (or distracted dev) can satisfy the local hook with a sentinel file and ship a commit message with no sweep block.

**v2 fix:** the pre-commit hook writes the sweep evidence DIRECTLY INTO the commit message file (passed by Git as `$1` to the `commit-msg` hook, or to `prepare-commit-msg`). The evidence rides IN the commit itself. CI reads the commit message via `gh api commits/<sha> --jq .commit.message` and validates the block mechanically. No ephemeral file. No local-pass-CI-can't-verify gap.

**v2 hook structure** (illustrative — implementation in Phase A; this is the design):

```bash
# ============================================================================
# DS-23: Post-fix pattern sweep gate (v2 — commit-message-anchored)
# Hook surface: prepare-commit-msg (passes commit message file path as $1)
# ============================================================================

# Override
if [[ "${MN_SKIP_DS23_GATE:-}" = "1" ]]; then
    echo "PRE-COMMIT: MN_SKIP_DS23_GATE=1 — DS-23 gate bypassed (CI will validate audit row)."
    # Append explicit waiver line to commit message so CI sees the bypass intent
    echo "" >> "$1"
    echo "DS-23 sweep waived (MN_SKIP_DS23_GATE=1; see DS_23_GATE_BYPASSED audit row)" >> "$1"
    exit 0
fi

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
    # Match the security pattern that triggered the sweep (configurable per-repo
    # via Production/scripts/ds23_pattern_config.txt; default = startswith(root) family)
    SWEPT_FILES=$(git diff --cached --name-only | xargs grep -l "<security-fix-pattern>" 2>/dev/null || true)
    if [[ -n "$SWEPT_FILES" ]]; then
        # Append sweep evidence INTO the commit message file ($1)
        # so it lands IN the commit, not as ephemeral file
        echo "" >> "$1"
        echo "Swept: $SWEPT_FILES" >> "$1"
        echo "Verified: $(grep -c '<security-fix-pattern>' $SWEPT_FILES 2>/dev/null || echo 'n/a')" >> "$1"
        echo "Pre-commit DS-23 gate: sweep evidence appended to commit message."
    else
        # Security file modified but no match for the configured pattern;
        # still REQUIRE explicit annotation so the gate's audit trail is closed.
        if ! grep -qE '^Swept:' "$1"; then
            echo "FATAL DS-23: security-adjacent file modified, no Swept: line in commit message."
            echo "  Either fix the configured pattern (Production/scripts/ds23_pattern_config.txt)"
            echo "  OR set MN_SKIP_DS23_GATE=1 + write DS_23_GATE_BYPASSED audit row."
            exit 1
        fi
    fi
fi
exit 0
```

**Why this closes HIGH-2:**
- Evidence lives IN the commit message itself — no ephemeral state.
- CI's view of the commit message IS the source of truth (`gh api commits/<sha>` returns the canonical post-commit message).
- Local hook and CI cannot disagree on what was swept.
- Bypass path also writes to the commit message (`DS-23 sweep waived (MN_SKIP_...)`), so CI sees the explicit waiver intent.

**Hook surface choice (note):** v1 used `pre-commit` which fires BEFORE the message is written. v2 uses `prepare-commit-msg` (which receives `$1`=commit-message file path AFTER Git generates the default but BEFORE the editor opens) so the hook can append. The existing `Production/scripts/git_hooks/pre-commit` continues to handle Dropbox-edit + watch-list checks; a NEW `Production/scripts/git_hooks/prepare-commit-msg` is added by Phase A. Installer (`install_pre_commit_hook.sh`) extends to install both.

#### §7.1.2 CI check (REPLACED in v2 — concrete audit-row query, no TODO)

**v1 had:** `# (Implementation: curl Directus prod_activity_log filtered by this SHA + DS23_GATE_BYPASSED action_type)` — a TODO comment, not executable.

**v2 has:** concrete executable query that fails CI when audit row absent.

```yaml
ds_23_check:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
      with: { fetch-depth: 0 }
    - name: Identify security-adjacent commits in PR range
      id: scan
      env:
        DIRECTUS_URL: ${{ secrets.DIRECTUS_URL }}
        DIRECTUS_TOKEN: ${{ secrets.DIRECTUS_TOKEN }}
      run: |
        BASE="${{ github.event.pull_request.base.sha }}"
        HEAD="${{ github.event.pull_request.head.sha }}"
        SECURITY_GLOBS='production_server.py|Production/lib/.*\.py$|firestore/rules/|functions/src/.*\.(ts|js)$'
        FAIL=0
        for COMMIT_SHA in $(git rev-list "$BASE..$HEAD"); do
          if git show --name-only --format= "$COMMIT_SHA" | grep -qE "$SECURITY_GLOBS"; then
            BODY=$(git log -1 --format=%B "$COMMIT_SHA")
            if echo "$BODY" | grep -qE '^Swept: '; then
              echo "  $COMMIT_SHA: DS-23 sweep block present in commit message"
            elif echo "$BODY" | grep -qE 'DS_23_GATE_BYPASSED|DS-23 sweep waived'; then
              # v2: CONCRETE audit-row check (was TODO in v1)
              AUDIT_ROW=$(curl -s -H "Authorization: Bearer $DIRECTUS_TOKEN" \
                "$DIRECTUS_URL/items/prod_activity_log?filter[action][_eq]=DS_23_GATE_BYPASSED&filter[details][_contains]=$COMMIT_SHA" \
                | jq '.data | length')
              if [[ "$AUDIT_ROW" -lt 1 ]]; then
                  echo "::error::DS-23 BYPASS rejected: no audit row referencing $COMMIT_SHA"
                  FAIL=1
              else
                  echo "  $COMMIT_SHA: DS-23 sweep waived; audit row verified ($AUDIT_ROW match)"
              fi
            else
              echo "::error::$COMMIT_SHA: DS-23 BLOCK MISSING in commit message"
              FAIL=1
            fi
          fi
        done
        echo "fail=$FAIL" >> "$GITHUB_OUTPUT"
    - name: Fail if any commit lacks sweep block
      if: steps.scan.outputs.fail == '1'
      run: exit 1
```

**Why this closes MED-1 (DS-23 half):** the bypass-validation logic is concrete and executable. Setting `MN_SKIP_DS23_GATE=1` without writing a matching audit row to `prod_activity_log` fails CI with an explicit error message. The TODO is gone.

### §7.2 DS-24 — Audit copy source before copy

§7.2.1 Pre-commit + §7.2.2 CI check + §7.2.3 FP-rate accounting all preserved verbatim from v1 §7.2 with one v2 amendment:

**v2 amendment to §7.2.3:** the FP-rate honest accounting carries forward, BUT the mitigation is no longer "30-day audit only." Per §11.2 (v2 amended), DS-24 gains an immediate halt-on-flap threshold: >5 sweep-needed events in 24h on the same file halts the gate and surfaces a `DS_24_FP_LOOP_SUSPECTED` blocker. Weekly preflight aggregates DS-24 trigger counts at week 1; >50% override rate flags for tuning. This addresses MED-2.

### §7.3 DS-25 — Adjacent risk sweep after CodeQL triage

#### §7.3.1 CI check (REPLACED in v2 — workflow_run payload normalization)

**Cursor HIGH-1 finding:** v1 §7.3.1 lines 483–493 trigger on both `pull_request` AND `workflow_run` (post-CodeQL). But lines 500–501 read `${{ github.event.pull_request.number }}` directly. Under `workflow_run`, the event payload doesn't carry `pull_request.*` fields. The job's `if:` guard (`github.event.pull_request.base.ref == 'main'`) silently filters out the `workflow_run` invocation entirely — meaning the post-CodeQL race-condition mitigation never fires. DS-25 either skips or breaks on the EXACT path it was designed to use.

**v2 fix:** add a `Resolve PR context` step that branches on `$GITHUB_EVENT_NAME` and uses `gh api /repos/<owner>/<repo>/commits/<head_sha>/pulls` for `workflow_run` mode. Subsequent steps reference `${{ steps.pr.outputs.pr_number }}`, not `github.event.pull_request.number`.

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
    if: >-
      (github.event_name == 'pull_request' && github.event.pull_request.base.ref == 'main') ||
      (github.event_name == 'workflow_run' && github.event.workflow_run.event == 'pull_request')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Resolve PR context
        id: pr
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          if [[ "$GITHUB_EVENT_NAME" == "workflow_run" ]]; then
            # v2: workflow_run payload does NOT carry pull_request.*; resolve via head_sha
            HEAD_SHA="${{ github.event.workflow_run.head_sha }}"
            PR_NUMBER=$(gh api "/repos/${{ github.repository }}/commits/$HEAD_SHA/pulls" --jq '.[0].number // empty')
            if [[ -z "$PR_NUMBER" ]]; then
              # Edge case: SHA pushed directly to main, no PR open
              echo "::notice::DS-25 skipped: head_sha $HEAD_SHA has no associated PR (DS_25_NO_PR_CONTEXT)"
              # Write audit row so the skip is auditable, not silent
              curl -s -X POST -H "Authorization: Bearer ${{ secrets.DIRECTUS_TOKEN }}" \
                -H "Content-Type: application/json" \
                "${{ secrets.DIRECTUS_URL }}/items/prod_activity_log" \
                -d "{\"action\":\"DS_25_NO_PR_CONTEXT\",\"details\":{\"head_sha\":\"$HEAD_SHA\",\"reason\":\"workflow_run with no PR\"}}"
              echo "skip=1" >> "$GITHUB_OUTPUT"
              exit 0
            fi
            echo "pr_number=$PR_NUMBER" >> "$GITHUB_OUTPUT"
          else
            echo "pr_number=${{ github.event.pull_request.number }}" >> "$GITHUB_OUTPUT"
          fi
          echo "skip=0" >> "$GITHUB_OUTPUT"

      - name: Check if this PR touches CodeQL-flagged files
        id: codeql_scope
        if: steps.pr.outputs.skip != '1'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          PR_NUMBER="${{ steps.pr.outputs.pr_number }}"
          FILES=$(gh pr view "$PR_NUMBER" --json files --jq '.files[].path')
          ALERTS=$(gh api -H "Accept: application/vnd.github+json" \
              "/repos/${{ github.repository }}/code-scanning/alerts?state=open" \
              --jq '.[] | select(.most_recent_instance.location.path) | .most_recent_instance.location.path' 2>/dev/null || echo "")
          TOUCHED=0
          for file in $FILES; do
              if echo "$ALERTS" | grep -qF "$file"; then
                  TOUCHED=1; break
              fi
          done
          echo "touched=$TOUCHED" >> "$GITHUB_OUTPUT"

      - name: Require sweep block in PR body
        if: steps.codeql_scope.outputs.touched == '1'
        env:
          DIRECTUS_URL: ${{ secrets.DIRECTUS_URL }}
          DIRECTUS_TOKEN: ${{ secrets.DIRECTUS_TOKEN }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          PR_NUMBER="${{ steps.pr.outputs.pr_number }}"
          BODY=$(gh pr view "$PR_NUMBER" --json body --jq '.body')
          HEAD_SHA=$(gh pr view "$PR_NUMBER" --json headRefOid --jq '.headRefOid')
          if echo "$BODY" | grep -qE 'Adjacent risk sweep on .+ after CodeQL triage'; then
              BLOCK=$(echo "$BODY" | sed -n '/Adjacent risk sweep on /,/Result:/p')
              if [[ ${#BLOCK} -lt 100 ]]; then
                  echo "::error::DS-25 sweep block present but <100 chars (placeholder rejected)"
                  exit 1
              fi
              echo "DS-25 gate: sweep block found, length OK"
          elif echo "$BODY" | grep -qE 'ADJACENT_RISK_SWEEP_WAIVED|DS_25_GATE_BYPASSED'; then
              # v2: CONCRETE audit-row check (was TODO in v1 line 528-530)
              AUDIT_ROW=$(curl -s -H "Authorization: Bearer $DIRECTUS_TOKEN" \
                "$DIRECTUS_URL/items/prod_activity_log?filter[action][_eq]=DS_25_GATE_BYPASSED&filter[details][_contains]=$HEAD_SHA" \
                | jq '.data | length')
              if [[ "$AUDIT_ROW" -lt 1 ]]; then
                  echo "::error::DS-25 BYPASS rejected: no audit row referencing $HEAD_SHA"
                  exit 1
              fi
              echo "DS-25 gate: waiver row referenced; audit row verified"
          else
              echo "::error::PR touches CodeQL-flagged file(s) but PR body lacks DS-25 adjacent risk sweep block"
              exit 1
          fi
```

**Note (v2):** DS-25 normalizes both `pull_request` and `workflow_run` events to a unified PR context. Edge case: if `gh api commits/<sha>/pulls` returns empty (e.g., SHA pushed directly to main, no PR), DS-25 skips with explicit `DS_25_NO_PR_CONTEXT` audit row — the skip is auditable, not silent.

**Why this closes HIGH-1 + MED-1 (DS-25 half):**
- Trigger payload mismatch resolved via `Resolve PR context` step.
- Both event modes share the same downstream PR-number reference.
- The `DS_25_NO_PR_CONTEXT` audit row makes the no-PR edge case observable.
- The bypass-row check is now concrete (not TODO); missing audit row fails CI explicitly.

#### §7.3.2 No pre-commit equivalent — preserved verbatim from v1.

---

## §8 Implementation Phases

Phases A–D + F–G preserved verbatim from v1 §8. Phase E amended in v2.

### Phase E (AMENDED in v2) — Weekly preflight audit hook + DS-24 24h flap threshold

1. Extend `Production/scripts/weekly_preflight_audit.py` with a check: count `DS{23,24,25}_GATE_BYPASSED` rows in the last 7 days. If >3 OR any has `rationale` shorter than 50 chars, write `prod_blockers` row `DS_GATE_BYPASS_THRESHOLD_HIT` (severity HARD per DS-9).
2. **(v2 NEW — addresses MED-2)** Add a `DS_24_24H_FLAP` sub-check: count `DS_24_GATE_FAILED` events grouped by file path within the last 24h. If any file exceeds 5 events, write `prod_blockers` row `DS_24_FP_LOOP_SUSPECTED` and halt the DS-24 gate for that file pending Kim review.
3. **(v2 NEW — addresses MED-2)** Add a `DS_24_WEEK1_OVERRIDE_RATE` reporter: at the end of week 1 post-launch (calendar day 7), aggregate `DS_24_GATE_BYPASSED` / (`DS_24_GATE_BYPASSED` + `DS_24_GATE_FAILED`). If ratio >0.5, surface `DS_24_FP_TUNING_NEEDED` blocker. This is week-1 reporting, NOT the 30-day audit (Phase G remains week-4).
4. This is the FP-rate monitoring mechanism per §11.

### Phase E.5 — preserved (was added in earlier amendment work outside this session) — N/A in v2.

### All other phases — preserved verbatim from v1.

---

## §9 Open Decisions — preserved verbatim from v1 §9

(See v1 §9 OD1–OD7. v2 adds two new ODs below.)

### §9-v2 — additional open decisions surfaced by Cursor

| # | Question | v2 recommendation |
|---|----------|-------------------|
| OD8 (v2) | Does the `prepare-commit-msg` hook compose with `git commit -m "..."` non-editor commits? | YES per Git docs — `prepare-commit-msg` fires for both editor and `-m` paths; `$1` is the commit-msg-source file in both. Append-mode (`>>`) lands the sweep block AFTER the user's `-m` content. To validate empirically, AT8 in §6.4 covers this case. |
| OD9 (v2) | Should `DS_25_NO_PR_CONTEXT` count toward bypass abuse thresholds? | NO — it's a structural skip (no PR exists), not an abuse. Phase E counter logic excludes `DS_25_NO_PR_CONTEXT` from the bypass-threshold accumulator. |

---

## §10 Pre-Implementation Gates — preserved verbatim from v1 §10 G1–G10

(See v1 §10. v2 adds two new gates below.)

### §10-v2 — additional pre-implementation gates

- [ ] **G11 (v2) — `prepare-commit-msg` hook plumbing verified.** `Production/scripts/install_pre_commit_hook.sh` extends to install the new hook surface; `Production/scripts/git_hooks/prepare-commit-msg` source authored; `.git/hooks/prepare-commit-msg` lands at install time alongside the existing `pre-commit`.
- [ ] **G12 (v2) — Directus secrets verified in tooling-repo GHA.** `DIRECTUS_URL` + `DIRECTUS_TOKEN` secrets exist in the tooling-repo GitHub Actions secret store (required for both DS-23 audit-row query and DS-25 audit-row query + `DS_25_NO_PR_CONTEXT` write).

---

## §11 Risk Assessment

§11.1 + §11.3 + §11.4 + §11.5 preserved verbatim from v1. §11.2 amended in v2.

### §11.2 (AMENDED in v2) — Bypass mechanism abuse risk + DS-24 FP churn

**Risk:** developers (including Claude) reflexively set `MN_SKIP_DS{23,24,25}_GATE=1` to avoid friction, OR DS-24's 30–50% FP rate produces a flap loop that normalizes bypass.

**Mitigations (v2 expanded):**
1. **Audit row mandatory + concrete CI verification.** v2 §7.1.2 + §7.3.1 now contain executable Directus queries (no TODO). Setting `MN_SKIP_DS{23,25}_GATE=1` without a matching `DS_{23,25}_GATE_BYPASSED` row fails CI explicitly. (Closes MED-1.)
2. **Weekly preflight audit threshold.** >3 bypasses/7-day window OR any rationale <50 chars → blocker row. (Preserved from v1.)
3. **(v2 NEW — addresses MED-2)** **DS-24 24h flap threshold.** >5 sweep-needed events in 24h on the same file → `DS_24_FP_LOOP_SUSPECTED` blocker + DS-24 halts on that file. Surfaces FP loops within hours, not 30 days.
4. **(v2 NEW — addresses MED-2)** **Week-1 DS-24 override rate report.** End of calendar day 7: if `DS_24_GATE_BYPASSED` / (BYPASSED + FAILED) > 0.5 → `DS_24_FP_TUNING_NEEDED` blocker. Catches operational erosion at week 1, not week 4.
5. **30-day FP-rate audit checkpoint** preserved from v1 (§8 Phase G).
6. **Sunset clause** preserved from v1.

### §11.6 (NEW v2) — Risk rows for the four Cursor defect classes

| Risk row | Failure mode | Cursor finding | v2 mitigation |
|---|---|---|---|
| RR1 — Workflow_run trigger payload mismatch | DS-25 gate silently skips the post-CodeQL invocation because `pull_request.*` fields are unpopulated under `workflow_run`. The race-condition mitigation v1 designed never fires; CodeQL latency reverts to discipline-only effective enforcement. | HIGH-1 | §7.3.1 v2 — `Resolve PR context` step branches on `$GITHUB_EVENT_NAME`; `gh api commits/<sha>/pulls` resolves PR; `DS_25_NO_PR_CONTEXT` for empty-PR edge case. |
| RR2 — Sentinel-file integrity gap | DS-23 local hook reads + deletes `.ds23_sweep`; commit message is unconstrained; CI's view (the commit message) and the hook's view (the deleted file) cannot be cross-validated. Bug class: ephemeral state. | HIGH-2 | §7.1.1 v2 — evidence appended to commit message file `$1` via `prepare-commit-msg`; CI reads `gh api commits/<sha> --jq .commit.message`; commit message IS the audit trail. |
| RR3 — TODO bypass-validation | `MN_SKIP_*` env honored locally but CI's audit-row check is a TODO; bypass can be set without consequence; abuse undetectable. | MED-1 | §7.1.2 + §7.3.1 v2 — concrete Directus queries; SHA-keyed `details._contains` filter; `--jq '.data | length'` < 1 fails CI with explicit error. |
| RR4 — DS-24 FP churn / bypass normalization | DS-24's 30–50% FP rate generates 5–10 min/week override burden; without same-day reporting, bypass becomes muscle-memory before the 30-day audit fires. | MED-2 | §11.2 + Phase E v2 — 24h flap threshold (>5 events/file → halt); week-1 override-rate reporter (>50% → `DS_24_FP_TUNING_NEEDED`). |

---

## §12 Rollback Per Phase — preserved verbatim from v1 §12

§12 changelog (NEW v2 entry, appended to v1's existing v1 entry):

| Date | Version | Change | Driver |
|---|---|---|---|
| 2026-05-08 | v1 | Initial spec authored. | Tech-spec dual-Opus debate per §4. |
| 2026-05-08 | **v2** | **Cursor v1 review (4 findings: 2 HIGH + 2 MED) addressed. §7.1.1 + §7.1.2 + §7.3.1 + §11.2 + Phase E amended. §0.1 v2-A changelog row added. §6.4 + §7-RR + §10-v2 gates appended. All other v1 sections preserved verbatim by reference.** | **Cursor's AMEND_V2 verdict on v1.** |

---

## §13 Testing Plan — preserved verbatim from v1 §13

(v2-additional test cases AT8–AT13 + AF7 enumerated in §6.4 above; they extend the §13 synthetic PR matrix without removing any v1 test.)

---

## §14 Reference Index (per DS-15 §16)

§14.1–§14.5 preserved verbatim from v1 §14. v2 amendments below.

### §14.1-v2 — additional files cited in v2

| File | Path | Confidence | Source/use |
|---|---|---|---|
| **v1 historical baseline (THIS spec's predecessor)** | `Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md` | [VERIFIED] | All preserved-by-reference sections (§1, §2, §3, §4, §5, §6.1–§6.3, §7.2, §7.3.2, §8 A-D + F-G, §9 OD1–OD7, §10 G1–G10, §11.1 + §11.3–§11.5, §12, §13, §14). |
| **v2 self-reference** | `Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md` | [DESIGN] | This document. Cited from §0.1, §0.3, §6.4, §7.1.1–§7.1.2, §7.3.1, §8 Phase E (amended), §11.2 (amended), §11.6 (new). |
| Cursor v1 review record | (Cursor session output, captured in this session) | [VERIFIED] | Cited verbatim in §0.1 row 1–4 + §11.6 RR1–RR4. |

### §14.2-v2 — LDs / blockers cited

- **LD-NEW (v2's own LD):** `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V2_WORKFLOW_TRIGGER_AUDIT_FIX_V1` — to be filed at end of this session per §15-v2. Locks the v2 design decisions (workflow_run normalization, commit-message-anchored evidence, concrete bypass-row queries, DS-24 24h flap threshold) in Directus per Rule 35.
- All v1-cited LDs (LD 580, LD 551) preserved by reference from v1 §14.2.
- Phase E (v2 amended) creates two new blocker classes: `DS_24_FP_LOOP_SUSPECTED` (24h flap), `DS_24_FP_TUNING_NEEDED` (week-1 override rate). [DESIGN — not yet created.]
- Phase G (preserved from v1) still creates `DS_GATE_FP_RATE_REVIEW` at day-30. [DESIGN — not yet created.]

### §14.3-v2 — Memory references — preserved verbatim from v1 §14.3.

### §14.4-v2 — Cross-references between this spec's sections

Preserved from v1 §14.4. v2 adds:
- §0.1 (v2 changelog) ↔ §6.4 (v2 acceptance criteria) ↔ §7.1.1 + §7.1.2 + §7.3.1 (v2 amended sections) ↔ §11.6 (v2 risk rows) — all four trace back to the same four Cursor findings, ensuring no orphan amendments.
- §10-v2 (G11 + G12) ↔ Phase A (preserved from v1) — new pre-implementation gates feed into the same Phase-A entry condition.

### §14.5-v2 — preserved verbatim from v1 §14.5.

---

## §15 Confidence Sweep (per Rule 24)

Every v2 amendment carries a confidence tag:
- **[VERIFIED]:** v1 file path + v1 line ranges quoted by Cursor (cross-checked in v2 authoring session against `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md`); existing tooling-repo hook + workflow paths preserved from v1.
- **[INFERRED]:** GitHub Actions `workflow_run` payload behavior (HIGH-1 rationale); Directus `prod_activity_log` filter syntax (`filter[action][_eq]` + `filter[details][_contains]`) per existing tooling patterns.
- **[ASSUMED]:** DS-24 FP-rate estimates (30–50% from v1) carry forward; v2's 24h flap threshold (>5 events/file) and week-1 override-rate threshold (>50%) are operator-set and to be re-calibrated post-Phase G empirical audit.
- **[DESIGN]:** all v2 YAML examples in §7.1.1, §7.1.2, §7.3.1, §11.6 RR rows, §10-v2 gates — proposed design, not extant.

### §15-v2 — LD-filing intent

At end of this session, file LD `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V2_WORKFLOW_TRIGGER_AUDIT_FIX_V1` in `prod_locked_decisions` via `Production/scripts/lock_decision.py lock` with full required args, citing this v2 file path as `source_document`.

---

## §16 Self-Classification

**Tier:** ARCHITECTURAL (governance + CI infra) — preserved from v1.
**Risk classes affected:** governance-doctrine-shaping, side-effect, multi-stage, async — preserved from v1. v2 specifically targets the workflow_run async-race + sentinel-file ephemeral-state classes.
**Six-Layer applicable layers:** 3, 4, 6 — preserved from v1.
**Reviewer expectations:** Cursor v2 cross-review handoff (next file, NOT authored in this session) requires preflight evidence for the four amended sections (§7.1.1, §7.1.2, §7.3.1, Phase E v2) + STRICT verification that the four Cursor findings (HIGH-1, HIGH-2, MED-1, MED-2) are each addressed end-to-end with no residual TODO.

---

*End of `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md`.*
