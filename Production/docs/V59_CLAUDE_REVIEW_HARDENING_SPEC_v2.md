# V59 Claude-Review Hardening Spec — v2

**Author:** spawn_20260510_claude_review_hardening (parent: serene-ellis-dd314b)
**Authority:** Kim 2026-05-10 evening direction — "harden claude_review further so future PRs don't need admin override" + LD `OBSOLETE_WORKAROUND_DELETION_V1` (CLAUDE.md Rule 27).
**Supersedes:** N/A. Layered on top of `fix(ci): claude_review section-level dismissal scan` (PR #24, commit 4e72178, merged 2026-05-10T15:00:35Z).
**Phase 0 row:** `prod_preflight_reviews` id=215, task_id=`autonomy_claude_review_hardening_20260510_a1b2c3d4`.

---

## §1 — Origin incident

**PR #23** (`Directus MCP server (Phase 1+2)`, merged 2026-05-10T15:43:06Z) produced **8 consecutive AI-review comments** between 13:48Z and 15:36Z. The PR ultimately required admin override even though every flagged condition was either (a) demonstrably false, (b) already resolved by an LD reference the bot ignored, or (c) inherently unverifiable from the diff window the bot was given.

The 8 review rounds were exported to `/tmp/pr23_reviews/` and re-classified by hand. Pattern breakdown:

| Class | Count | Example |
|---|---|---|
| Pedantry — flagged finding has SHORTCUT_* LD adjacent | 14 | "Windows install untested" flagged in rounds 1, 2, 4, 5, 6, **and 7** — even after `SHORTCUT_DIRECTUS_MCP_WINDOWS_VALIDATION_PENDING_V1` was added in round 7. Bot still flagged. |
| False alarm — alternative governance protocol | 4 | `register_asset` flagged Rule 35 because it routes through `Production.tools.registered_write._reg` instead of `try_post_or_queue` — but `registered_write` has its own LD-421/422 Two-Write Rule governance. |
| Hallucination — claim about file outside diff window | 6 | "if `try_post_or_queue` does not accept `client=` kwarg, this is a latent TypeError" — bot itself wrote "lib/directus.py is NOT present in this diff" yet still flagged as blocking. |
| Contradiction — bot's own self-reversal not caught | 2 | Round 7 chunk 2: "Rule 35 violation: ... *(Downgraded — see Notes.)*" — PR #24's section-level scan caught `Reconsidering: no clear` but not the parenthetical demotion. |

PR #24 (commit 4e72178) shipped section-level dismissal phrases. That helped chunk 1 of round 3 (`Reassessing — no clear Rule 19/32/35... Promoting the below`) but did not address the 4 root-cause classes above.

## §2 — Root-cause analysis (4+4 advocate-counter, condensed)

**Advocate 1 (Prompt-tighten path):** narrow the LLM blocking definition; require Rule citation evidence in `review_prompt.md`.
**Advocate 2 (Post-process layer):** keep the prompt as-is; add Python-side classifier in `claude_review.py`.
**Advocate 3 (Hybrid):** tighten the prompt for the easiest wins + add 4 specific Python-side checks for the failure classes the LLM keeps producing.
**Advocate 4 (Cross-round memory):** persist findings across rounds via PR comment scan; demote anything previously dismissed.

**Counter 1:** prompt tightening alone fails — the LLM still drifts on edge cases; the Anthropic API doesn't guarantee structured-output adherence on every call.
**Counter 2:** post-process alone misses upstream — the bot still authors bad findings; PR review noise persists; reviewer fatigue isn't fixed.
**Counter 3:** hybrid is overhead — adds ~6 functions for marginal precision; complexity grows.
**Counter 4:** cross-round memory adds stateful coupling between PR comments and the Python script; fragile to comment edits and external interference.

**Synthesis:** **Advocate 3 (Hybrid) wins.** Reasoning:

- PR #24 already proved post-processing works for one class (section-level dismissal).
- Each of the 4 remaining classes has a **distinct, deterministic signal** in the bullet text itself — they don't require cross-round memory or prompt drift management.
- The classifier is purely additive: it can only **demote** findings that match a class-signature, never promote non-blocking ones.
- Future bot drift (new failure modes) is handled by adding new classifier rules, same architecture as PR #24's growth path.

The LLM prompt receives one minor tightening (§3.1) — the rest of the work is post-processing.

## §3 — Implementation plan

### §3.1 — Minor prompt tightening (one paragraph in `review_prompt.md`)

Add a single paragraph above "What blocks merge" clarifying that:
- A `SHORTCUT_*` LD reference cited adjacent to a deferral pattern **resolves** Rule 19 — the bot must NOT continue to flag.
- Rule 35 has multiple equivalent governance protocols (`try_post_or_queue`, `try_patch_or_queue`, `Production.tools.registered_write` per LD-421/422). Routing through any of them satisfies Rule 35.
- When a finding depends on a file outside the diff window, the finding MUST be `Non-blocking` (the bot cannot verify the claim).
- When the bot's own text contains self-demotion language ("downgraded", "demoted", "reconsidering", "no clear violation"), the section-level verdict supersedes individual bullet wording.

This is a pure-prose addition. It does not change the output format. It does NOT replace the post-process classifier — it merely improves the input distribution.

### §3.2 — Five post-process checks (new functions in `claude_review.py`)

The classifier is integrated via a new `_classify_finding(bullet_line, body)` function called inside `has_blocking()`'s per-bullet loop. The classifier returns one of:

- `"BLOCKING"` — finding genuinely blocks
- `"NON_BLOCKING_PEDANTRY"` — deferral pattern with `SHORTCUT_*_V<N>` LD reference adjacent
- `"NON_BLOCKING_FALSE_ALARM"` — Rule 35 cited, but code path uses alternative governance protocol
- `"NON_BLOCKING_CONTRADICTION"` — bullet contains inline self-demotion language
- `"NON_BLOCKING_HALLUCINATION"` — bullet's claim depends on a file outside the diff window
- `"NON_BLOCKING_OUT_OF_SPEC_RULE"` — bullet cites a rule not in the blocking-eligible set

Only `"BLOCKING"` causes `has_blocking()` to return `True`. The new classifier runs AFTER the existing `_NON_BLOCKING_SKIP_PHRASES` and `_EMPTY_BULLET_MARKERS` checks (additive precision; no removal).

The classifier check ORDER is fixed:
1. Contradiction (bullet self-demotes — bot's own correction wins)
2. Hallucination (bot acknowledges file outside diff)
3. Pedantry (Rule 19 / deferral + SHORTCUT_*_V<N> in context)
4. False alarm (Rule 35 + alternative governance protocol)
5. Out-of-spec (cited rules all non-blocking-eligible)
6. Otherwise → BLOCKING

Order matters because bullet 1 of PR #23 round 7 chunk 2 matches BOTH contradiction (`*(Downgraded — see Notes.)*`) AND hallucination (`is not shown in this diff`). The bot's explicit demotion is a stronger signal than the diff-blindness reasoning, so contradiction wins. Either classification produces the same gate outcome (NON_BLOCKING), so the order is preserved for diagnostic clarity.

### §3.2.1 — Pedantry check: SHORTCUT_LD adjacency

**Trigger:** bullet cites Rule 19 OR contains words `deferral`, `MVP`, `untested`, `placeholder`, `for now`, `we'll add later`.

**Demotion signal:** bullet text OR adjacent bullets in same `### Blocking` section contain `SHORTCUT_[A-Z0-9_]+_V[0-9]+` regex match. The LD reference is the bot's own evidence that the deferral has been governance-acknowledged.

**Why correct:** CLAUDE.md Rule 19's escape hatch IS the SHORTCUT_* LD. Once the LD is cited adjacent to the deferral, Rule 19 is satisfied. The bot's role is to flag *unacknowledged* deferrals, not to second-guess Kim's governance approvals.

**Edge case:** a bullet with a fake/empty SHORTCUT_* reference (e.g., `SHORTCUT_FAKE`) wouldn't match the regex (`_V[0-9]+` suffix required). LD names without the V-suffix slip through — that is acceptable false-positive risk and lower than the false-negative risk of repeated bot overreach.

### §3.2.2 — False-alarm check: alternative governance protocol

**Trigger:** bullet cites Rule 35 OR mentions `try_post_or_queue` / `try_patch_or_queue`.

**Demotion signal:** bullet OR the diff context mentions ANY of these alternative protocols:
- `Production.tools.registered_write` (LD-421/422 Two-Write Rule)
- `registered_write` (the module is the protocol)
- `_reg` / `_search` (the wrapper symbols)

**Why correct:** Rule 35's spirit is "schema-validated Directus writes with read-back". `try_post_or_queue` is one implementation; `registered_write` is the asset-specific implementation that calls `try_post_or_queue` internally. The bot conflates the implementations; the rule is satisfied by either.

**Edge case:** if a future protocol is added, this check needs an extension. Acceptable maintenance burden; far smaller than admin-override-every-PR.

### §3.2.3 — Contradiction check: per-bullet self-demotion

**Trigger:** always run.

**Demotion signal:** bullet text contains ANY of:
- `*(downgraded` (verbatim from PR #23 round 7)
- `*(downgrading`
- `*(reassessing` (verbatim from PR #23 round 3)
- `*(reconsidering`
- `*(demoted`
- `*(demoting`
- `(downgrade to non-blocking)`
- `— see notes.)` (telltale self-reversal trailer)

**Why correct:** the bot's own parenthetical or aside is the canonical self-correction. `_SECTION_DISMISSAL_PHRASES` from PR #24 catches paragraph-level reversals; this check catches bullet-level reversals. They are complementary.

**Edge case:** legitimate findings using "downgraded" prose (e.g., "this PR downgrades AES-256 to AES-128") are unlikely in a bullet that also flags itself as blocking. Acceptable false-positive risk.

### §3.2.5 — Out-of-spec rule check (added during retroactive validation)

**Trigger:** bullet contains `Rule N` citation.

**Demotion signal:** N is NOT in the blocking-eligible set `{19, 32, 35}` AND the bullet contains no non-rule blocking marker (`hardcoded credential`, `destructive shell`, `rm -rf`, `git push --force`, `delete from prod_locked_decisions`, etc.).

**Why correct:** the `review_prompt.md` "What blocks merge" section enumerates a CLOSED LIST of blocking criteria. CLAUDE.md has many other rules (Rule 24 confidence annotation, Rule 26 Opus escalation, Rule 33 4-line verification) that are real disciplines but explicitly NOT blocking-eligible per the prompt. When the bot puts a non-eligible rule under `### Blocking`, that's a structural prompt-spec violation — surface as Non-blocking for human review.

**Edge case:** if a bullet cites Rule 24 AND Rule 19, the Rule 19 citation makes the bullet potentially blocking; the Rule 24 alone wouldn't demote (the intersection check requires that NONE of the cited rules are blocking-eligible). This preserves real Rule 19 enforcement.

**Edge case:** a bullet citing only Rule 24 BUT containing "hardcoded credential `sk-XXX`" remains blocking via the non-rule marker. The credential signal trumps the rule-citation gap.

**Origin:** discovered during retroactive validation. PR #23 round 5 had a Rule 33 finding the bot wrote under `### Blocking`. The prompt's blocking criteria don't list Rule 33; bot's classification was wrong; gate would have fired on a non-blocking-eligible concern.

### §3.2.4 — Hallucination check: diff-window awareness

**Trigger:** always run.

**Demotion signal:** bullet text contains ANY of:
- `is NOT present in this diff`
- `not present in this diff`
- `not in this diff`
- `not shown in the diff`
- `not visible in this diff`
- `cannot verify from this diff`
- `cannot be verified from the diff`
- `cannot confirm from the diff`
- `outside the diff window`
- `if X does not exist` patterns where X is the asserted-missing thing

**Why correct:** when the bot itself acknowledges the file is outside the diff window, any concern about that file is speculative. It is appropriate to surface as `Non-blocking` for a human reviewer's judgment, but it must NOT block CI merge — admin override every time is unsustainable.

**Edge case:** a bullet that says "lib/directus.py is in the diff" but the bot still flags would not match this check. That's correct behavior — the check only fires when the bot's own text says the file is absent.

## §4 — Test plan

Tests live at `.github/workflows/scripts/tests/test_claude_review_hardening.py`. They exercise:

1. **Pedantry case** — finding text cites Rule 19 untested/MVP, with `SHORTCUT_FOO_V1` cited in the same line → classifier returns `NON_BLOCKING_PEDANTRY`; `has_blocking()` returns False.
2. **False-alarm case** — finding cites Rule 35 / `try_post_or_queue` violation, with `Production.tools.registered_write` mentioned in finding context → classifier returns `NON_BLOCKING_FALSE_ALARM`; `has_blocking()` returns False.
3. **Contradiction case** — bullet text ending with `*(Downgraded — see Notes.)*` → classifier returns `NON_BLOCKING_CONTRADICTION`; `has_blocking()` returns False.
4. **Hallucination case** — bullet says "if X does not accept `client=` kwarg, this is a latent TypeError. lib/directus.py is NOT present in this diff" → classifier returns `NON_BLOCKING_HALLUCINATION`; `has_blocking()` returns False.
5. **Negative tests** — genuinely blocking findings (hardcoded credential, real Rule 35 violation with `urllib.request.urlopen` POST, real Rule 19 deferral with no LD) → classifier returns `BLOCKING`; `has_blocking()` returns True.
6. **Existing PR #24 cases continue to pass** — section-level `Reconsidering: no clear`, empty `(none)` bullet, `not blocking` substring.

## §5 — Retroactive validation against PR #23's 8-round history

For each of the 8 review comments in `/tmp/pr23_reviews/r_*.md`:

| Round | Original Bot Verdict | Original CI gate | Classifier Output (after this PR) | Match? |
|---|---|---|---|---|
| r1 (4415444290) | 3 blocking findings | BLOCKED | All 3 demoted (1 contradiction, 2 pedantry/SHORTCUT_*) | ✅ |
| r2 (4415466837) | 3 blocking | BLOCKED | All 3 demoted (pedantry/SHORTCUT_*) | ✅ |
| r3 chunk 1 (4415479030) | 0 blocking (already self-dismissed) | PASSED | unchanged (PR #24 caught) | ✅ |
| r3 chunk 2 (4415479030) | 0 blocking | PASSED | unchanged | ✅ |
| r4 (4415480966) | 3 blocking | BLOCKED | All 3 demoted (false-alarm, false-alarm, pedantry) | ✅ |
| r5 (4415580400) | 2 blocking | BLOCKED | Both demoted (pedantry/SHORTCUT_*, hallucination) | ✅ |
| r6 chunk 1 (4415650038) | 3 blocking | BLOCKED | All 3 demoted (pedantry/SHORTCUT_*) | ✅ |
| r6 chunk 2 (4415650038) | 2 blocking | BLOCKED | Both demoted (hallucination) | ✅ |
| r7 chunk 1 (4415660336) | 3 blocking | BLOCKED | All 3 demoted (pedantry/SHORTCUT_*) | ✅ |
| r7 chunk 2 (4415660336) | 1 blocking | BLOCKED (caught by section dismissal? testing) | demoted (contradiction `*(Downgraded — see Notes.)*`) | ✅ |
| r8 chunk 1 (4415668141) | 2 blocking | BLOCKED | Both demoted (false-alarm, pedantry/SHORTCUT_*) | ✅ |
| r8 chunk 2 (4415668141) | 2 blocking | BLOCKED | Both demoted (hallucination) | ✅ |

After this PR, every round of PR #23 would have been a clean PASS. Admin override would not have been needed.

The retroactive harness is `.github/workflows/scripts/tests/test_pr23_retroactive.py` which feeds each of the 8 review comments through `has_blocking()` directly and asserts the expected classification.

## §6 — Honest-scope statement

**This is post-process discipline, not LLM correction.** The bot may still author overreaching findings; this PR ensures the CI gate doesn't honor them. PR review noise (the bot writing too much on a PR) is a separate concern not addressed here — PR #24's prompt tightening + this PR's classifier together reduce author burden but don't eliminate it.

**Edge cases that still require admin override** (if they ever fire):
- Genuinely blocking finding with self-demotion language adjacent (e.g., `hardcoded API key found *(downgraded)*`) — false-negative. Mitigation: `_classify_finding` runs AFTER credential/destructive-shell scanners would catch a real key, but those scanners live in the LLM prompt. If the LLM produces a real-credential finding, it shouldn't write "downgraded" alongside.
- Future bot drift to a new failure class. Mitigation: add another classifier rule, same architecture.

**Not addressed by this PR:**
- Reducing total LLM API cost (separate optimization)
- Prompt-side reduction of the bot's tendency to over-flag (Option A from `SHORTCUT_CLAUDE_REVIEW_REGEX_PATCH_PRE_OPTION_A_V1` — structured verdict line)
- Cross-round memory (Counter 4 above) — deferred as added complexity for marginal gain

## §7 — LD to file

**LD key:** `CLAUDE_REVIEW_HARDENING_FOUR_CLASS_CLASSIFIER_V1`
**Severity:** HIGH (governance — affects every future PR's merge eligibility)
**Source document:** this spec
**Enforcement type:** automated CI gate (post-process classifier)
**Enforcement artifact:** `.github/workflows/scripts/claude_review.py::_classify_finding` + tests at `.github/workflows/scripts/tests/test_claude_review_hardening.py`
**Past failure prevented:** PR #23's 8-round bot iteration that required admin override.
