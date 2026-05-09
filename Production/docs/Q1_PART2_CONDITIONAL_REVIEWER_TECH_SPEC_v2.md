# Q1 — Part 2: Conditional Opus Reviewer Subagent — Tech Spec v2

**Status:** Spec authored 2026-05-08 (v2 amendment cycle, post-Cursor-v1-review). DESIGN ONLY — no code, no Directus writes, no edits.
**Authority:** Kim's Q1 directive (state-claim verification stack — Part 2 of 3).
**Pairs with:** Q1 Part 1 (`Production/docs/Q1_PART1_STOP_HOOK_SPEC_v1.md`, LD 579 `Q1_PART1_STOP_HOOK_INSTALLED_V1`).
**Authoring method:** v1 dual-Opus debate preserved by reference; v2 surgical amendments addressing 4 Cursor-v1 defects (HIGH-1, HIGH-2, MEDIUM-1, MEDIUM-2).
**Supersedes:** v1 (`Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md`) for the four amended sections; all other v1 sections preserved verbatim by reference.

---

## §0. Operating Mode

- DESIGN ONLY. v2 specifies surgical amendments to v1's §3, §6, §7, and §10 to close the four defects Cursor surfaced on v1. No production scripts, no settings.json edits, no hook installs, no Directus rows are written by the act of authoring this spec.
- Multipass authoring: pass 1 drafts amendments §3-AMEND, §6-AMEND, §7-AMEND, §10-AMEND; pass 2 verifies cross-references and counts; pass 3 stress-tests deterministic semantics + fail-closed default + tightened path list + cost-field fallback.
- Per Rule 24: state claims about Q1 Part 1 internals are tagged `[CONFIRMED from <file>:<line>]` where verified inline; un-verified architectural assertions are tagged `[INFERRED]` or `[GUESSED]`.
- HALT triggers: any unresolved cost-model gap; any recursion-guard failure mode I cannot mechanically prevent; any open decision Kim has not signaled on.
- Implementation requires a separate authorized session post-Cursor cross-review of v2.

## §0.1. Changelog (descending — v2 row above v1 row)

| Version | Date | Author | Change |
|---|---|---|---|
| v2-A | 2026-05-08 | Claude (post-Cursor v1 review) | Surgical 4-defect closure: (HIGH-1) §3 + §6 L4 deterministic semantics — define 120-char tag-suppression window with explicit regex pair + edge-case rules; (HIGH-2) §10 recursion guard inverted to FAIL-CLOSED on exception (return True/skip spawn); (MEDIUM-1) §6 allow-list narrowed — REMOVE doc/spec patterns (`*_SPEC_v*.md`, `*LD*.md`, `MINDFULNEST_PROFESSIONAL_SETUP_ROADMAP_v*.md`), KEEP only infrastructure-wiring file paths; add note decoupling L3 path-class from L4 regex; (MEDIUM-2) §7 cost-field fallback — define behavior when `total_cost_usd`/`total_tokens` absent or JSON malformed (banner shows "(cost unknown)", session-log records fallback, cost-cap treats None as 0 for budgeting). 4 new risk rows in §14. Reference index extended with v1 historical baseline + this LD + self-reference. |
| v1 | 2026-05-08 | Claude (initial dual-Opus debate) | Initial spec — trigger model L0–L5, cost ceiling 7 spawns/session, 4-layer recursion guard, stderr banner output. See v1 doc for full content. |

## §0.2. Reading order (for reviewers)

v2 is a surgical amendment overlay on v1, NOT a full rewrite. To review v2 in context:

1. **Read v1 first** in full (`Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md`).
2. **Then read v2 §3-AMEND, §6-AMEND, §7-AMEND, §10-AMEND** — these supersede v1's corresponding sections.
3. **All other v1 sections** (§0-§5, §8-§9, §11-§17, except where explicitly amended below) **remain authoritative**.

This v2 doc is intentionally surgical to keep the diff against v1 small and reviewable. A monolithic v3 rewrite would obscure the four-defect boundary.

---

## §3-AMEND. L4 Deterministic Tag-Suppression Semantics (HIGH-1 fix)

### 3-AMEND.1. Cursor's finding (verbatim)

> **HIGH — L4 trigger semantics underspecified.** Lines 95-99 trigger description says "contains regex match", but lines 254-255 example assumes tagged claims (`[CONFIRMED…]`) suppress matches per Step 2.5b semantics. Spec doesn't specify exact tag-suppression rules. If implemented literally, tagged claims still trigger (false positives); if over-suppressed, real claims skipped (false negatives).

### 3-AMEND.2. Root cause

v1's L4 row in the §3.2 trigger-model table reads literally: "last turn's assistant text contains ≥1 state-claim regex match (canonical Step 2.5b pattern)". v1's §6.4 fixture row 254 then ALSO requires that a tagged claim NOT trigger — but the mechanism is left implicit ("L4 fails — tag suppresses regex match per Step 2.5b semantics"). Step 2.5b in `mn-context/SKILL.md:300` defines suppression as "claim followed in the same turn by Rule 24-style verification" — this is "same turn" granularity, not character-distance granularity. If the L4 implementation literally re-uses Step 2.5b's same-turn rule, every tagged turn's untagged claims would be suppressed by the existence of any tag elsewhere in the turn — over-suppression. If it ignores tags entirely, every tagged claim would still trigger — false positives. v1 left the choice unspecified.

### 3-AMEND.3. v2 deterministic rule (locked)

L4 fires if AND ONLY IF the assistant text contains at least one state-claim regex match whose **per-match suppression** check fails. Per-match suppression is computed as follows:

```python
import re

# L4 PRIMARY: state-claim regex (canonical Step 2.5b pattern from
# mn-context/SKILL.md:296 — preserved verbatim, including the verb-form
# group and the trailing modifier-phrase group).
STATE_CLAIM_RE = re.compile(
    r"\b(is|are|will be|gets?|gates?|surfaces?|fires?|runs?|executes?|"
    r"reads?|writes?|cross-references?|hooks? into|enforces?|prevents?|"
    r"catches?)\s+(wired|fired|surfaced|read|written|enforced|mechanically|"
    r"automatically|by the [a-z\s]+|on [a-z\s]+|when [a-z\s]+|via [a-z\s]+|"
    r"through [a-z\s]+)",
    re.IGNORECASE,
)

# L4 SUPPRESSION: per-match Rule-24 tag check within a 120-character
# trailing window beginning AT the regex match's end position.
TAG_SUPPRESS_RE = re.compile(
    r"\[(CONFIRMED|INFERRED|GUESSED)\b",
    re.IGNORECASE,
)

# Window length is 120 chars, chosen to comfortably cover the longest
# realistic well-formed Rule 24 tag chain in a single sentence
# (e.g., "[CONFIRMED from ~/.claude/hooks/some_long_hook_filename.py:42]")
# while remaining short enough that a tag attached to a DIFFERENT,
# subsequent claim in a NEW sentence does not bleed back to suppress
# the prior unrelated claim. See §3-AMEND.4 edge-case rules.
SUPPRESSION_WINDOW_CHARS = 120

def has_unverified_state_claim(text: str) -> bool:
    """L4 trigger evaluator. Returns True iff at least one state-claim
    regex match has NO Rule 24 tag within its trailing 120-char window."""
    for match in STATE_CLAIM_RE.finditer(text):
        window_start = match.end()
        window_end = window_start + SUPPRESSION_WINDOW_CHARS
        lookahead = text[window_start:window_end]
        if not TAG_SUPPRESS_RE.search(lookahead):
            return True  # this match is unsuppressed → L4 fires
    return False  # zero matches OR all matches suppressed by nearby tags
```

### 3-AMEND.4. Edge-case rules (locked)

| # | Edge case | Behavior | Rationale |
|---|---|---|---|
| EC-1 | Tag in a different sentence within 120 chars | SUPPRESS (count it) | Tags often appear at end of paragraph after a string of claims; treating them as scoped to the immediately-preceding claim is the most user-charitable interpretation. False-suppress cost: low (Kim usually tags every claim). False-trigger cost: high (banner noise on legitimate work). |
| EC-2 | Tag wrapped across line break (`\n`) | SUPPRESS | The 120-char window uses `text[start:start+120]` with no whitespace normalization — newlines are characters, the regex `re.IGNORECASE` is the only flag. A tag immediately after `\n` is still within the window and matches `\[CONFIRMED`. |
| EC-3 | Tag is the literal string `[CONFIRMED` but with no closing bracket (e.g., a partial paste) | SUPPRESS | The regex `\[(CONFIRMED\|INFERRED\|GUESSED)\b` requires only the open-bracket + word + word-boundary. A truncated tag still suppresses; the cost of a single false-suppress on a malformed tag is much lower than the complexity of validating tag structure. |
| EC-4 | Two state claims back-to-back, single tag at end | First claim: tag is within first claim's 120-char window? If yes, SUPPRESS first claim. Second claim: tag is within second claim's 120-char window (which starts AT the second claim's match-end)? If yes, SUPPRESS second claim. | Per-match windows are independent. A single trailing tag can suppress multiple claims if they all fit within 120 chars before it. This is the user-intended pattern: "X is wired and Y fires when Z [CONFIRMED from file:42]". |
| EC-5 | Tag appears BEFORE the claim (prefix-style) | DOES NOT SUPPRESS | The window is forward-looking only, starting at `match.end()`. Prefix tags are unusual and the design chooses determinism over heuristic complexity. If Kim's pattern shifts to prefix-tagging, document a v3 amendment. |
| EC-6 | State-claim match overlaps with a tag (e.g., the regex matches inside `[CONFIRMED from file:42]` quoted text) | NO SUPPRESS HEURISTIC; let the regex match fire | The Step 2.5b regex is unlikely to match Rule-24 tag prose; if it does, this is a model authoring quirk and the banner is non-blocking. Acceptable false-trigger rate. |
| EC-7 | The 120-char window crosses end-of-text | Window is clipped at `len(text)`; `text[N:N+120]` past the end returns empty string; treated as no tag found → DOES NOT SUPPRESS | Standard Python slicing; no special handling. End-of-text claims that lack a trailing tag DO trigger L4 — this is intentional. |
| EC-8 | Multiple regex matches in one sentence with one tag at sentence end | Per EC-4: each match's window independently checks; tag suppresses any match whose window reaches the tag | Same logic as EC-4. The 120-char window is the only bound. |

### 3-AMEND.5. Why 120 chars (window-length derivation)

- Average sentence length in Kim's tagged work prose: ~80–110 chars (sampled from existing `Production/docs/*.md` v1+v2 specs). [INFERRED — sample-based, not formally measured]
- Longest realistic Rule 24 tag: `[CONFIRMED from ~/.claude/hooks/some_long_hook_filename.py:NNN]` ≈ 75 chars. Adding a leading "→ " or " " separator brings it to ~80.
- 120 is a comfortable upper bound that fits one sentence + one trailing tag without bleeding into a second sentence's content. Selected to balance EC-1 (charitable to multi-claim sentences) against avoiding cross-sentence over-suppression.
- Adjustable via constant `SUPPRESSION_WINDOW_CHARS` at hook script top — can be tightened to 80 or loosened to 200 without re-architecting. [INFERRED — verify in implementation Phase D fixture testing]

### 3-AMEND.6. v1 fixture row 253-255 reconciled

v1's §6.4 fixture F3 row reads:

> Edit to `~/.claude/skills/zero-error-qa/SKILL.md` + state-claim text + `[CONFIRMED…]` tag → NO TRIGGER (L4 fails — tag suppresses regex match per Step 2.5b semantics)

This row is now mechanically grounded in the v2 deterministic rule: the single state-claim regex match's `match.end()` + 120-char window contains `[CONFIRMED`, suppression fires, `has_unverified_state_claim()` returns False, L4 fails, no spawn. The fixture passes per the §3-AMEND.3 algorithm.

### 3-AMEND.7. Test fixtures (added to v1 §16)

| Fixture | Setup | Expected | EC ref |
|---|---|---|---|
| F-EC-1 | Sentence: `the hook fires when X. [CONFIRMED from foo.py:42]` (period before tag, total <120 chars from match end) | NO TRIGGER | EC-1 |
| F-EC-2 | `the hook fires when X.\n[CONFIRMED from foo.py:42]` (newline-separated) | NO TRIGGER | EC-2 |
| F-EC-4 | `X is wired and Y fires when Z [CONFIRMED from foo.py:42]` (two claims, one tag) | NO TRIGGER (both suppressed if both fit in 120-char window) | EC-4 |
| F-EC-5 | `[CONFIRMED] X is wired by the new gate` (tag prefix-style) | TRIGGER | EC-5 |
| F-EC-7 | `the audit reads from LD-565` at very end of text, no tag | TRIGGER | EC-7 |

These add to v1 §16's positive/negative path fixtures.

---

## §6-AMEND. Tightened Allow-List (MEDIUM-1 fix) + L3/L4 Decoupling

### 6-AMEND.1. Cursor's finding (verbatim)

> **MEDIUM — allow-list too broad.** Lines 223-226 patterns include `**/Production/docs/*_SPEC_v*.md` + `**/Production/docs/*LD*.md` — matches many planning/doc edits not actually infrastructure-wiring critical. Combined with hard cap (7 spawns/session), risks burning spawns on low-stakes docs.

### 6-AMEND.2. Root cause

v1's §6.1 list mixed three categories under one heading "Infrastructure file path patterns":

- (a) Hook scripts and settings — genuinely infrastructure-wiring.
- (b) Lib/script files that ARE the hook implementation — genuinely infrastructure-wiring.
- (c) Documentation/spec/LD files — these are PLANNING and AUTHORITY documents, not running infrastructure.

A spec doc like `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md` contains many state claims by nature ("the L0 check tests for the env var", "the hook is wired by the Stop event") — but those claims are about a *design*, not a *running system*. They are not yet "wired" until a separate authorized session installs the hook. Triggering Part 2 on every spec edit burns spawns on documents whose claims are explicitly conditional ("will be wired", "is designed to fire").

### 6-AMEND.3. v2 narrowed allow-list (locked)

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
**/Production/scripts/migrate_*.py
**/Production/scripts/git_hooks/**
**/Production/lib/directus*.py
**/Production/lib/preflight.py
**/Production/.github/workflows/**.yml
**/Production/.github/workflows/**.yaml
**/Production/github_actions/*.yml
**/Production/github_actions/*.yaml
**/firestore.rules
**/firestore.indexes.json
```

### 6-AMEND.4. Patterns REMOVED from v1 list

| Removed pattern | Reason |
|---|---|
| `**/Production/docs/*_SPEC_v*.md` | Specs are design docs; their claims are conditional ("will fire", "is designed to"). State-claim regex over-fires on design language, not running-system language. |
| `**/Production/docs/*LD*.md` | LD authoring/planning docs are pre-decision narrative. The actual LD rows live in `prod_locked_decisions` (Directus) — file edits to LD-summarizing markdown do not change running system behavior. |
| `**/Production/docs/MINDFULNEST_PROFESSIONAL_SETUP_ROADMAP_v*.md` | Master roadmap is a living planning doc; aspirational not active. |

### 6-AMEND.5. Patterns ADDED to v1 list (closing genuine infra gaps)

| Added pattern | Reason |
|---|---|
| `**/Production/scripts/migrate_*.py` | Schema migration scripts are exactly the high-stakes "did this actually wire X" risk class. |
| `**/Production/scripts/git_hooks/**` | Git hook installs (per the 8-phase gap-fix spec) are infrastructure-wiring critical. |
| `**/Production/lib/directus*.py` (was `directus.py`) | Glob covers `directus.py`, `directus_writers.py`, etc.; v1's exact match was too narrow. |
| `**/Production/.github/workflows/**.yml` | Future CI/CD wiring location (per master roadmap Layer 1). |

### 6-AMEND.6. L3 / L4 decoupling rule (NEW — locked)

**Doc/spec edits trigger Part 2 ONLY via L4 regex (state-claim language with no nearby tag), NOT via L3 path-class match.**

This decouples two concerns:
- **L3 (path class):** "I touched a file that runs as infrastructure." — narrow allow-list, infrastructure-wiring files only.
- **L4 (state-claim regex):** "I wrote prose that asserts a wiring fact." — applies to all assistant text regardless of which files were edited.

A spec edit (e.g., editing `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v2.md`) that contains state claims will NOT trigger Part 2 because L3 fails (the spec doc's path is not in §6-AMEND.3's allow-list) — even though L4 might match. The state claim in a spec document is correctly handled by Part 1's broader sieve and by SAVE-time DS-22 + Step 2.5b verification.

A hook script edit (e.g., editing `~/.claude/hooks/stop_state_claim_scan.py`) WITH accompanying state-claim prose will trigger Part 2 because BOTH L3 (path matches) AND L4 (regex unsuppressed) fire.

**Implementation note for v2:** the §3-AMEND.3 trigger conjunction (L0 ∧ L1 ∧ L2 ∧ L3 ∧ L4 ∧ L5) is unchanged structurally. The narrowing is in L3's allow-list contents, not in the conjunction logic.

### 6-AMEND.7. Risk: under-inclusiveness of the narrowed list

If a future infrastructure-touching script lives outside the listed patterns (e.g., a new file in `Production/scripts/` that ISN'T `lock_decision.py` or a `migrate_*.py`), Part 2 will not fire on edits to it. Mitigation:

- Quarterly review of the allow-list against `git ls-files Production/scripts/` (per zero-error-qa quarterly cadence).
- The allow-list is a single Python constant (`INFRASTRUCTURE_PATH_PATTERNS`) — adding a path is a one-line non-breaking spec amendment.
- Removal under cost pressure is harder than addition; v2 errs on the conservative side, accepting some under-inclusiveness as the lower-risk default.

---

## §7-AMEND. Cost-Field Fallback (MEDIUM-2 fix)

### 7-AMEND.1. Cursor's finding (verbatim)

> **MEDIUM — cost-field [INFERRED].** Lines 369-371 expect `total_cost_usd` + `total_tokens` fields from `claude -p` JSON output but marks as inferred. If absent/changed, banner + cost accounting underspecified.

### 7-AMEND.2. Root cause

v1's §8.3 cost monitoring assumed the `--output-format json` response contains `total_cost_usd` and `total_tokens` fields, then tagged the assumption `[INFERRED]`. If the SDK's actual output schema differs (older Claude Code version, future schema change, or schema variation across model classes), the hook script would either crash or silently mis-account cost. v1 did not specify fallback behavior.

### 7-AMEND.3. v2 deterministic fallback parser (locked)

```python
import json
import logging

logger = logging.getLogger("q1_part2")

def parse_claude_response(response_text: str) -> dict:
    """Parse the stdout from `claude -p ... --output-format json`.

    Returns a dict with at minimum these keys:
      - "text": the reviewer's text output (or raw stdout on JSON failure)
      - "total_cost_usd": float or None (None if absent/unparseable)
      - "total_tokens": int or None (None if absent/unparseable)
      - "schema": "v1" if expected fields present, "fallback" otherwise

    Never raises. Logs a WARNING when fallback is used so weekly review
    can detect schema drift.
    """
    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.warning(
            "q1_part2: claude -p response was not valid JSON; "
            "treating as plain text. error=%s, len=%d", e, len(response_text)
        )
        return {
            "text": response_text,
            "total_cost_usd": None,
            "total_tokens": None,
            "schema": "fallback",
        }

    if not isinstance(parsed, dict):
        # JSON valid but not an object (e.g., bare string, list, number)
        logger.warning(
            "q1_part2: claude -p response was JSON but not an object "
            "(type=%s); treating as plain text.", type(parsed).__name__
        )
        return {
            "text": response_text,
            "total_cost_usd": None,
            "total_tokens": None,
            "schema": "fallback",
        }

    # Coerce missing fields explicitly; None signals "unknown"
    parsed.setdefault("total_cost_usd", None)
    parsed.setdefault("total_tokens", None)

    # Schema marker: v1 if BOTH cost fields were present in original JSON,
    # fallback otherwise. We can detect this via the "before-setdefault"
    # state, but since setdefault has already mutated, recompute via
    # the response_text check.
    has_cost = '"total_cost_usd"' in response_text
    has_tokens = '"total_tokens"' in response_text
    parsed["schema"] = "v1" if (has_cost and has_tokens) else "fallback"

    if parsed["schema"] == "fallback":
        logger.warning(
            "q1_part2: claude -p JSON object missing expected cost fields "
            "(has_cost=%s, has_tokens=%s); using None placeholders.",
            has_cost, has_tokens
        )

    return parsed
```

### 7-AMEND.4. Banner behavior when cost fields absent

When `parsed["total_cost_usd"] is None`:

- Banner line `Spawn cost:` shows `(cost unknown)` literal text.
- Banner line `Session usage:` still shows `<N>/7 spawns used` — counter is incremented regardless.
- Cost-cap calculation treats None as 0 USD for budgeting purposes (under-counting; documented as a known surface).

```
Spawn cost:    (cost unknown — schema=fallback)
Session usage: 3/7 spawns used
```

### 7-AMEND.5. Session-log records the fallback

The session log file (`~/.claude/state/q1_part2_session_<id>.log`) appends a JSON line per spawn including the `schema` field:

```json
{"ts":"2026-05-08T12:34:56Z","files":["~/.claude/hooks/x.py"],"verdict":"PASS","schema":"fallback","total_cost_usd":null,"total_tokens":null,"raw_text_len":4823}
```

The `schema` field's value is the audit hook into schema-drift detection.

### 7-AMEND.6. Weekly review surface

If `schema=fallback` rows appear >5 times in a week, the weekly preflight audit (`Production/scripts/weekly_preflight_audit.py`) emits a notice asking Kim to investigate Claude Code SDK output schema drift.

```
[Q1-PART2 SCHEMA DRIFT NOTICE]
Q1 Part 2 reviewer JSON schema fallback fired N times this week (threshold: 5).
This may indicate the `claude -p --output-format json` response schema has
changed. Inspect the latest log entries:
  ~/.claude/state/q1_part2_session_*.log | grep '"schema":"fallback"'
If schema has drifted, update parse_claude_response() in
~/.claude/hooks/stop_conditional_opus_reviewer.py.
```

[INFERRED — the weekly_preflight_audit.py wiring is implementation-time work; this v2 spec mandates the surface but does not author the audit code.]

### 7-AMEND.7. Cost-cap behavior with None costs

The §3.3 / §8.2 cost ceiling math is unchanged: cap is on **spawn count** (7/session), not on cumulative USD. The USD figures in §8.2 are advisory estimates, not enforced. Therefore the fallback's None-as-0 budgeting choice does not weaken the spawn-count cap. The only loss is observability of true session USD when the schema drifts.

If a future v3 amendment introduces a USD-based cap, the fallback would need stronger semantics (e.g., None counted as a worst-case $2 per the §8.1 worst-case estimate). v2 does not adopt this — the spawn-count cap is sufficient for current cost concerns.

---

## §10-AMEND. Recursion Guard FAIL-CLOSED (HIGH-2 fix)

### 10-AMEND.1. Cursor's finding (verbatim)

> **HIGH — recursion guard fail-OPEN on exception.** Lines 447-465 reference implementation:
> ```python
>         except Exception:
>             return False  # FAIL-OPEN
> ```
> Spec calls this "final backstop" but `return False` means "no recursion detected" → spawn proceeds. Should fail-CLOSED (return True / skip spawn) on any exception per safety-default principle.

### 10-AMEND.2. Root cause

v1's §10.4 process-tree depth limit reads:

```python
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

The `except Exception: return False` clause means: on any unexpected error (ps not found, encoding error, transient subprocess failure, permission denied), the function returns False ("no recursion detected"), and the spawn proceeds. This is FAIL-OPEN — the OPPOSITE of the safety-default principle for safety-critical guards.

The same fail-open default is implicit in the function's terminating `return False` after a clean `max_depth` traversal — that's correct (we walked the chain and saw no `claude -p` parent). The bug is specifically the `except` arm, where we don't actually know the chain was clean — we know the check itself crashed.

### 10-AMEND.3. v2 inverted default (locked)

```python
import os
import subprocess
import logging

logger = logging.getLogger("q1_part2")

def has_recursion_ancestor(max_depth: int = 5) -> bool:
    """Return True iff this hook process appears to be running inside a
    `claude -p` (headless) invocation — i.e., we should SKIP spawning a
    reviewer to avoid recursion.

    FAIL-CLOSED: on any unexpected error during the parent-chain walk,
    return True (assume recursion, skip spawn). This is the safer default:
    occasional false-positive skip when ps/ancestry check transient-fails;
    cost: lose one Opus reviewer spawn that turn; benefit: prevents
    runaway recursion in edge cases the design did not anticipate.
    """
    try:
        pid = os.getpid()
        for _ in range(max_depth):
            ppid_raw = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "ppid="]
            )
            ppid = int(ppid_raw.strip())
            if ppid <= 1:
                # Reached init / launchd; chain is clean.
                return False
            cmd_raw = subprocess.check_output(
                ["ps", "-p", str(ppid), "-o", "command="]
            )
            cmd = cmd_raw.decode("utf-8", errors="replace")
            if "claude -p" in cmd or "claude --print" in cmd:
                # Found a headless claude ancestor → recursion path.
                return True
            pid = ppid
        # Walked max_depth without finding init OR claude -p:
        # ambiguous; FAIL-CLOSED.
        logger.warning(
            "q1_part2: process-tree walk exhausted max_depth=%d without "
            "reaching init; assuming recursion (FAIL-CLOSED).", max_depth
        )
        return True
    except Exception as e:
        logger.warning(
            "q1_part2: process-tree walk raised %s: %s; "
            "assuming recursion (FAIL-CLOSED).", type(e).__name__, e
        )
        return True  # FAIL-CLOSED: any exception → assume recursion → skip spawn
```

### 10-AMEND.4. Two changes from v1 §10.4

| Change | v1 behavior | v2 behavior | Rationale |
|---|---|---|---|
| Exception handling | `except Exception: return False` (fail-OPEN) | `except Exception: return True` (fail-CLOSED) | Safer default for safety-critical guards. |
| max_depth exhausted without init | implicit return False (fail-OPEN) | explicit `return True` (fail-CLOSED) | If the chain is so deep we can't reach init in 5 steps, something unusual is happening; assume recursion. |

### 10-AMEND.5. Updated §10 narrative

> "On any unexpected error, the recursion guard fails CLOSED (assumes recursion) rather than OPEN (assumes no recursion). Trade-off: occasional false-positive skip when ps/ancestry check transient-fails. Cost: lose one Opus reviewer spawn that turn. Benefit: prevents runaway recursion in edge cases the design did not anticipate.
>
> The fail-closed default is consistent with the broader safety doctrine of zero-error-qa: when in doubt, refuse the action that could cause harm. A missed reviewer spawn is recoverable (Kim sees no banner; can re-trigger via re-edit or manual review). Runaway recursion is not recoverable in the same turn (each level of recursion costs Opus tokens; the cap mitigates but does not eliminate damage)."

This text amends v1's §10's last narrative paragraph (currently silent on exception default).

### 10-AMEND.6. Test fixtures (added to v1 §16.4 recursion-guard fixtures)

| Fixture | Setup | Expected | New in v2 |
|---|---|---|---|
| F-FC-1 | Mock `subprocess.check_output` to raise `FileNotFoundError` (ps absent) | NO SPAWN (fail-closed) | Yes |
| F-FC-2 | Mock chain depth >5 without reaching init | NO SPAWN (fail-closed) | Yes |
| F-FC-3 | Mock `subprocess.check_output` to raise `subprocess.CalledProcessError` mid-walk | NO SPAWN (fail-closed) | Yes |
| F-FC-4 | Normal chain depth ≤5 reaching init with no claude -p | SPAWN (only the genuine clean-chain path proceeds) | Yes (regression test for the only fail-OPEN-equivalent path) |

### 10-AMEND.7. Consistency check across all 4 guards

| Guard | v1 default on failure | v2 default on failure | Status |
|---|---|---|---|
| §10.1 env-var sentinel | N/A (env-var read is single-line, can't fail) | N/A | OK as-is |
| §10.2 output sentinel | If `last_assistant_text` read fails, behavior undefined in v1 | v2: wrap in try/except, default to True (assume reviewer-output-style turn → skip spawn) | AMENDED — see §10-AMEND.8 |
| §10.3 SDK flag | Implementation-time discovery; fail mode TBD | v2: if SDK flag absent, falling back to env-var sentinel + ps walk is sufficient (already documented in v1 §10.3) | OK as-is |
| §10.4 ps walk | fail-OPEN | fail-CLOSED | AMENDED (this section) |

### 10-AMEND.8. Output sentinel (§10.2) consistency amendment

For consistency with the fail-closed doctrine, the output-sentinel check (v1 §10.2) is amended similarly:

```python
def has_output_sentinel(last_assistant_text: str | None) -> bool:
    """Return True iff the assistant text contains the reviewer-output
    sentinel — i.e., this turn IS a reviewer's output and we must NOT
    spawn another reviewer.

    FAIL-CLOSED: on None input or any unexpected error, return True
    (assume sentinel present → skip spawn).
    """
    SENTINEL = "<!-- Q1_PART2_REVIEWER_OUTPUT_SENTINEL_DO_NOT_TRIGGER -->"
    try:
        if last_assistant_text is None:
            return True  # FAIL-CLOSED
        return SENTINEL in last_assistant_text
    except Exception as e:
        logger.warning(
            "q1_part2: sentinel check raised %s: %s; "
            "assuming sentinel present (FAIL-CLOSED).", type(e).__name__, e
        )
        return True  # FAIL-CLOSED
```

This is a small ergonomic loss (a turn with `None` text — which shouldn't happen — would skip a reviewer spawn) for a meaningful safety win.

---

## §14-AMEND. Risk-Row Additions for v2 (4 NEW rows)

Appended to v1's §14 risk table:

| Risk (v2 NEW) | Likelihood | Severity | Mitigation |
|---|---|---|---|
| L4 over-suppression bleeds across sentences (EC-1 false-suppress on multi-sentence claims with one trailing tag far away) | Med | Low | 120-char window bounds the bleed; quarterly review of suppression rate via session-log analysis. If bleed exceeds 5% of triggered turns, tighten window to 80 chars. |
| Recursion guard false-CLOSE drops legitimate reviewer spawns under transient `ps` failures | Low | Low | Logged WARNING per fail-closed event; session-log review catches recurring patterns; cost is one missed reviewer banner per failure event, recoverable in next turn. |
| Allow-list under-inclusive: a NEW critical infrastructure file is added outside §6-AMEND.3 patterns and Part 2 silently doesn't fire | Med | Med | Quarterly review of allow-list against `git ls-files`; allow-list is a single user-amendable Python constant; any new infrastructure file authored should add itself to the list as part of its own LD checklist. |
| Cost-field schema drift causes systematic under-counting of session USD | Low | Low | `schema=fallback` row count surfaced in weekly_preflight_audit.py with threshold 5/week; session-log review catches drift; spawn-count cap (not USD cap) bounds true cost regardless of observability. |

---

## §11-AMEND. Reference Index (extended)

Appended to v1's §17 reference index:

- **v1 historical baseline:** `Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md` (this v2 supersedes only §3, §6, §7, §10; all other v1 sections remain authoritative)
- **v2 LD (this spec's own lock):** `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V2_TRIGGER_GUARD_LIST_COST_V1`
- **v2 self-reference:** `Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v2.md` (this document)
- **Cursor v1 review handoffs:**
  - `Production/docs/HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508.md` (v1)
  - `Production/docs/HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v2.md` (intermediate)
  - `Production/docs/HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v3.md` (latest)
- **Q1 Part 2 implementation handoff:** `Production/docs/HANDOFF_Q1_PART2_IMPLEMENTATION_20260508.md`
- **Step 2.5b canonical regex source:** `~/.claude/skills/mn-context/SKILL.md:296`
- **Step 2.5b suppression rule source:** `~/.claude/skills/mn-context/SKILL.md:300–306`

---

## §12-AMEND. Changelog (single appended row to v1's §0.1 master changelog)

Already captured at top of v2 (§0.1).

---

**End of v2 spec.** All other v1 sections (§0, §1, §2, §4, §5, §8, §9, §11, §12, §13, §14 v1 rows, §15, §16, §17) remain authoritative as published in v1.
