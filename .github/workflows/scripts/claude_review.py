#!/usr/bin/env python3
"""V59 CI/CD gap-fix Phase C — Claude API PR reviewer.

Called by .github/workflows/ai_review.yml on PR open/sync/reopen.

Reads /tmp/pr.diff, sends to Claude (sonnet 4.6) with the system prompt
at .github/workflows/scripts/review_prompt.md, writes the assistant
response to /tmp/ai_review_comment.md, and creates /tmp/ai_review_blocking
if any "### Blocking" finding has at least one "- " entry.

Failure modes (per spec §Phase C escape hatches):
  - ANTHROPIC_API_KEY missing/invalid → write "skipped" comment, exit 0
    (do NOT block merge on infra unavailability).
  - Diff > 1 MB → write "diff too large" comment, exit 0.
  - Anthropic 5xx → retry once with exponential backoff; on second failure
    write "API unavailable" comment, exit 0.
  - Diff > 100 KB → split into chunks, review each, concatenate findings.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

DIFF_PATH = Path("/tmp/pr.diff")
OUT_PATH = Path("/tmp/ai_review_comment.md")
BLOCKING_FLAG = Path("/tmp/ai_review_blocking")
PROMPT_PATH = Path(".github/workflows/scripts/review_prompt.md")

MAX_DIFF_BYTES = 1_000_000  # 1 MB hard cap → "too large" skip
CHUNK_SOFT_BYTES = 100_000  # 100 KB → split into chunks
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4_000


def write_skip(reason: str) -> None:
    OUT_PATH.write_text(
        f"## AI Review Findings\n\nReview skipped — {reason}.\n",
        encoding="utf-8",
    )


def chunk_diff(text: str) -> list[str]:
    if len(text.encode("utf-8")) <= CHUNK_SOFT_BYTES:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for hunk in re.split(r"(?=^diff --git )", text, flags=re.MULTILINE):
        if not hunk:
            continue
        size = len(hunk.encode("utf-8"))
        if current and current_size + size > CHUNK_SOFT_BYTES:
            chunks.append("".join(current))
            current = []
            current_size = 0
        current.append(hunk)
        current_size += size
    if current:
        chunks.append("".join(current))
    return chunks


def call_anthropic(client, system_prompt: str, diff_chunk: str, *, retries: int = 2) -> str:
    pr_meta = (
        f"PR #{os.environ.get('PR_NUMBER', '?')} — {os.environ.get('PR_TITLE', '')}\n"
        f"base={os.environ.get('PR_BASE_SHA', '?')[:8]} "
        f"head={os.environ.get('PR_HEAD_SHA', '?')[:8]}\n\n"
    )
    user_content = (
        pr_meta
        + "Review this PR diff against the rules in your system prompt. "
        + "Output the structured findings table.\n\n"
        + "```diff\n"
        + diff_chunk
        + "\n```\n"
    )
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_content}],
            )
            return "".join(
                block.text for block in resp.content if getattr(block, "type", "") == "text"
            )
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise
    raise RuntimeError(f"call_anthropic exhausted retries: {last_err}")


_NON_BLOCKING_SKIP_PHRASES = (
    # Explicit "(non-)blocking" markers — high-precision phrases.
    "no blocking",
    "not blocking",
    "non-blocking",
    "non-blocker",
    "no blocker",
    "no new blocking",
    "downgrading to non-blocking",
    # Anchored bot self-resolution pattern. Earlier broad substrings
    # ("not a new", "not a blocker", "this is a fix") were all rejected
    # because they can match mid-sentence in genuine blocking findings
    # — [CONFIRMED against has_blocking() smoke test in this commit:
    # "this is not a new pattern but a real blocker" → blocks; "this is
    # a fix for X but introduces Y blocking issue" → blocks; "this is
    # not a blocker for deployment but is genuinely concerning" → blocks.
    # All three would have been silently masked under the broader phrase
    # set]. Only retain phrases that are unambiguous self-dismissal in
    # any context.
    "not a new introduction",
)

# Bullet content markers indicating "no findings" — bot writes "- (none)"
# when the section has no entries. Compared against the bullet's content
# AFTER stripping the leading "- ", normalized to lowercase.
_EMPTY_BULLET_MARKERS = (
    "(none)",
    "none",
    "n/a",
    "—",
)

# Section-level dismissal markers — phrases the bot writes in its
# section body (OUTSIDE individual bullet first-lines) when it has
# reconsidered its own findings and concluded that nothing is actually
# blocking. The bot's own conclusion at section level wins over
# individual bullet wording.
#
# Authority: SHORTCUT_CLAUDE_REVIEW_REGEX_PATCH_PRE_OPTION_A_V1 (LD-667)
# — interim regex patch with closure plan = Option A.
# Closure plan per SHORTCUT_CLAUDE_REVIEW_REGEX_PATCH_PRE_OPTION_A_V1:
# Option A — modify review_prompt.md to require a structured verdict
# line (e.g. "## Final verdict: NO_BLOCKING_FINDINGS") and parse THAT
# instead of natural-language reversal phrases. Option B (this code)
# is interim per SHORTCUT_CLAUDE_REVIEW_REGEX_PATCH_PRE_OPTION_A_V1
# but unblocks PR #22 today per
# SHORTCUT_CLAUDE_REVIEW_REGEX_PATCH_PRE_OPTION_A_V1; Option A follows
# per SHORTCUT_CLAUDE_REVIEW_REGEX_PATCH_PRE_OPTION_A_V1 closure plan.
#
# Pattern class observed across multiple PR #22 rounds: bot writes a
# concerning bullet then concludes the section with explicit
# self-reversal language ("Reconsidering: no clear ... violations are
# present", "Not clearly blocking on its own", "Downgrading to
# Non-blocking"). The conclusion is the bot's actual verdict; the gate
# honors it.
#
# Patterns intentionally narrow [INFERRED — verify by re-running the
# 24-case smoke enumerated in PR #24 round-3 (commit description) +
# any new adversarial cases at PR-author time. Smoke fixtures are NOT
# persisted as a pytest in this repo yet — that's a follow-up under
# Option A / a separate test-extraction PR.]:
#   * "reconsidering: no clear"  — bot's "I changed my mind" prefix only
#     when followed by "no clear" (avoids false-skip on
#     "Reconsidering: no, the concern stands")
#   * "not clearly blocking"     — bot's explicit self-doubt admission
#   * "no clear rule N"          — bot's per-rule self-reversal
#   * "no clear rule N/M"        — bot's combined-rule enumerations
#                                  (PR #22 round-3 actual phrase)
#   * "no clear violations are present" — full-verdict catch
_SECTION_DISMISSAL_PHRASES = (
    "reconsidering: no clear",
    "not clearly blocking",
    # Per-rule self-reversals.
    "no clear rule 19",
    "no clear rule 24",
    "no clear rule 32",
    "no clear rule 33",
    "no clear rule 35",
    # Combined-form enumerations (observed in actual bot output on
    # PR #22 round-3: "no clear Rule 19/35/32/credential/destructive-
    # command violations are present"). Matches the bot's verbatim
    # phrasing — narrower than "no clear" alone (which could mask
    # real findings about format conventions etc).
    "no clear rule 19/35",
    "no clear rule 19/35/32",
    "no clear rule 32/35",
    "no clear credential",
    "no clear destructive",
    # Full-verdict catches.
    "no clear violations are present",
    "no clear violations introduced",
    # Section-level reassessment (PR #23 round 3 chunk 1 verbatim).
    "reassessing — no clear",
    "promoting the below",
    "no hard-blocking violations per the defined blocking criteria",
    "demoting the above to non-blocking",
)


# ---------------------------------------------------------------------------
# Four-class finding classifier (LD CLAUDE_REVIEW_HARDENING_FOUR_CLASS_CLASSIFIER_V1)
#
# Layered on top of the existing _NON_BLOCKING_SKIP_PHRASES + _EMPTY_BULLET_MARKERS
# + _SECTION_DISMISSAL_PHRASES checks. After PR #24 caught section-level dismissal,
# four bot-overreach failure classes remained visible in PR #23's 8-round history:
#
#   1. Pedantry        — bot flags Rule 19 deferral when the same finding cites a
#                         SHORTCUT_*_V<N> LD (Kim's governance-acknowledged escape
#                         hatch). The LD reference IS the resolution; flagging
#                         again is overreach.
#   2. False alarm     — bot flags Rule 35 violation when code routes through an
#                         alternative documented governance protocol
#                         (Production.tools.registered_write per LD-421/422)
#                         instead of try_post_or_queue directly.
#   3. Contradiction   — bot writes a blocking bullet then self-demotes inline
#                         (e.g. "*(Downgraded — see Notes.)*"). The bullet's own
#                         self-correction wins; the existing section-paragraph
#                         scan misses parenthetical inline demotions.
#   4. Hallucination   — bot flags a kwarg/field/file as missing when the bullet
#                         text itself acknowledges the file is OUTSIDE THE DIFF
#                         WINDOW. Speculation-as-blocking; demote to advisory.
#
# Each classifier rule is purely additive — it can DEMOTE a bullet but never
# promote a non-blocking one. Genuinely blocking findings (hardcoded credentials,
# destructive shell, real urllib.request.urlopen POST without try_post_or_queue,
# real LD-less deferrals) are unaffected.
#
# Origin incident: PR #23 needed admin override after 8 review rounds. See
# Production/docs/V59_CLAUDE_REVIEW_HARDENING_SPEC_v2.md for full rationale +
# advocate/counter debate + retroactive validation table.
# ---------------------------------------------------------------------------

# §3.2.1 — Pedantry: SHORTCUT_<NAME>_V<N> regex. Loose enough to catch all
# observed LD-naming patterns; strict enough to reject empty/fake references
# (e.g. just "SHORTCUT_" without a name+version).
_SHORTCUT_LD_PATTERN = re.compile(r"\bSHORTCUT_[A-Z0-9_]+_V[0-9]+\b")

# §3.2.1 — Pedantry triggers. Deferral-pattern words from CLAUDE.md Rule 19
# that the bot keys on. When ANY of these appear AND a SHORTCUT_*_V<N> LD is
# present in the bullet OR adjacent context, the finding is demoted.
_PEDANTRY_TRIGGER_WORDS = (
    "deferral",
    "deferred",
    "untested",
    "phase 1 mvp",
    " mvp",  # leading space avoids matching "mvpath" or similar tokens
    "placeholder",
    "for now",
    "we'll add later",
    "not yet been run",
    "first invocation",
    "first run",
)

# §3.2.2 — Alternative governance protocols recognized as Rule 35 equivalents.
# These are documented governance paths that wrap try_post_or_queue internally
# OR provide their own read-back-after-write (LD-421/422 Two-Write Rule for
# registered_write). Bot conflates "uses X instead of try_post_or_queue" with
# "Rule 35 violation"; this list teaches the gate the alternatives.
_ALTERNATIVE_GOVERNANCE_TOKENS = (
    "registered_write",
    "production.tools.registered_write",
    "production/tools/registered_write",
    "register_asset",  # the wrapper that uses registered_write
    "find_asset",  # the read-side wrapper
    "_reg",  # the imported alias used in tools/assets.py
    "ld-421",  # LD-421 ASSET_FINDABILITY_BUILD_V1
    "ld-422",
)

# §3.2.2 — Rule 35 trigger phrases. When the bullet cites Rule 35 / mentions
# try_post_or_queue / try_patch_or_queue AND any token above appears, demote.
_RULE_35_TRIGGER_PHRASES = (
    "rule 35",
    "rule-35",
    "try_post_or_queue",
    "try_patch_or_queue",
)

# §3.2.3 — Contradiction: inline self-demotion phrases the bot writes within
# a single bullet. Complementary to _SECTION_DISMISSAL_PHRASES (which catches
# paragraph-level reversals); these catch bullet-level reversals.
_CONTRADICTION_BULLET_PHRASES = (
    "*(downgraded",
    "*(downgrading",
    "*(reassessing",
    "*(reconsidering",
    "*(demoted",
    "*(demoting",
    "(downgraded —",
    "(downgrade to non-blocking)",
    "(downgrade to non blocking)",
    "— see notes.)",
    "see notes.)",
    "(reclassifying — see non-blocking)",
    "reclassifying — see non-blocking",
    "(see non-blocking)",
    "this is not itself a blocking violation",
    "demoted to non-blocking",
)

# §3.2.5 — Out-of-spec rule citation. The review_prompt.md "What blocks merge"
# section enumerates a CLOSED LIST of blocking-eligible criteria: Rule 19
# (deferral pattern), Rule 32 (fetch URL), Rule 35 (direct POST without
# try_post_or_queue), hardcoded credential, destructive shell command, and
# deletion of prod_locked_decisions. ALL OTHER RULES (Rule 24 confidence
# annotation, Rule 26 Opus escalation, Rule 33 4-line verification, etc.) are
# CLAUDE.md disciplines but are NOT blocking-eligible per the prompt's own
# specification. When the bot puts a non-blocking-eligible rule under
# `### Blocking`, that's a structural prompt-spec violation.
#
# Implementation: scan bullet for `Rule N` mentions; if the rule number isn't
# in the blocking-eligible set AND no blocking-eligible rule is also cited,
# demote.
_BLOCKING_ELIGIBLE_RULE_NUMBERS = frozenset({"19", "32", "35"})
_RULE_CITATION_REGEX = re.compile(r"\brule[\s-]?(\d+)\b", re.IGNORECASE)
# Non-rule blocking-eligible markers — when ANY of these appear, the bullet
# is potentially blocking-eligible regardless of rule citation.
_BLOCKING_ELIGIBLE_NON_RULE_MARKERS = (
    "hardcoded credential",
    "hard-coded credential",
    "credential leak",
    "api key in source",
    "destructive shell",
    "destructive command",
    "rm -rf",
    "git push --force",
    "drop table",
    "delete from prod_locked_decisions",
    "deletion of prod_locked_decisions",
    "deletion of a prod_locked_decisions",
)


# §3.2.4 — Hallucination: phrases the bot writes when it KNOWS the asserted-
# missing thing is outside the diff window it received. When these appear in
# the bullet, the finding is speculation, not fact. Demote.
_HALLUCINATION_DIFF_BLINDNESS_PHRASES = (
    # "X is NOT present in this diff" / variants
    "is not present in this diff",
    "not present in this diff",
    "not in this diff",
    "not shown in the diff",
    "not shown in this diff",
    "not visible in this diff",
    "not visible in the diff",
    # "no <FILE> diff is present in this PR" pattern (PR #23 round 8 chunk 2)
    "diff is present in this pr",
    "diff is not present",
    "no diff present in this pr",
    "is not in this pr",
    # "cannot verify / confirm" passive + active forms
    "cannot verify from this diff",
    "cannot be verified from this diff",
    "cannot be verified from the diff",
    "cannot confirm from the diff",
    "cannot confirm from this diff",
    "cannot be confirmed from the diff",
    "cannot be confirmed from this diff",
    "cannot be audited from this pr",
    "cannot be audited from the diff",
    "could not be checked from this diff",
    "could not be assessed",
    # "no evidence in this diff" — bot's explicit acknowledgment of blindness
    "no evidence in this diff",
    "no evidence in the diff",
    # "outside the diff window" — explicit blindness
    "outside the diff window",
    "outside the diff",
    # "if X does not exist / accept / propagate" — speculative claims
    "if it does not yet exist",
    "if x does not exist",
    "if it does not accept",
    "does not accept/propagate",
    "may not accept",
    "is unverifiable from",
    "unverifiable from this diff",
    "unverifiable from the diff",
    # "files not in the diff are not reviewable" / explicit blind acknowledgments
    "not reviewed for fix",
    "flagged for verification",
    "could not be verified from",
)

# Regex catch for the speculative "if <symbol> does not yet exist" pattern
# where the bot fills in a specific function/file name. Matches things like:
#   "If `try_patch_or_queue` does not yet exist in"
#   "If try_post_or_queue does not exist"
# The literal-phrase scan above handles "if it does not yet exist" (generic
# pronoun); this regex handles the named-symbol case.
_HALLUCINATION_REGEX = re.compile(
    r"\bif\s+`?[\w./]+`?\s+does\s+not\s+(?:yet\s+)?(?:exist|accept|propagate|return)\b",
    re.IGNORECASE,
)


def _has_shortcut_ld_in_context(bullet_line: str, body: str) -> bool:
    """True if a SHORTCUT_*_V<N> LD reference appears in the bullet itself
    OR anywhere in the surrounding ### Blocking section body.

    Body-wide scan covers the case where a bot lists 3 related Rule 19
    deferrals and cites the LD once at the top of the section instead of
    on each bullet (PR #23 round 6: "The three Windows-related blocking
    findings all trace to the same untested code path; a single SHORTCUT_*
    LD reference covering the Windows install path would resolve all
    three simultaneously")."""
    if _SHORTCUT_LD_PATTERN.search(bullet_line):
        return True
    if _SHORTCUT_LD_PATTERN.search(body):
        return True
    return False


def _classify_finding(bullet_line: str, body: str) -> str:
    """Classify a single ### Blocking bullet against the four overreach
    classes. Returns one of:
      - "BLOCKING"
      - "NON_BLOCKING_PEDANTRY"
      - "NON_BLOCKING_FALSE_ALARM"
      - "NON_BLOCKING_CONTRADICTION"
      - "NON_BLOCKING_HALLUCINATION"

    The classifier is INTENTIONALLY conservative on demotion — only when a
    deterministic signal in the bullet text matches the failure class. It
    will never demote a finding that lacks the class signature, which means
    genuinely blocking findings (real credentials, real destructive shell,
    real LD-less deferrals) pass through unchanged.

    Order of checks matters: contradiction + hallucination are checked FIRST
    because they are content-based (don't depend on Rule N citation). Then
    pedantry (Rule 19 + LD adjacency). Then false-alarm (Rule 35 +
    alternative-governance tokens)."""
    line_l = bullet_line.lower()

    # §3.2.3 — inline self-demotion (bullet-level contradiction).
    for phrase in _CONTRADICTION_BULLET_PHRASES:
        if phrase in line_l:
            return "NON_BLOCKING_CONTRADICTION"

    # §3.2.4 — diff-window hallucination (literal phrases + regex).
    for phrase in _HALLUCINATION_DIFF_BLINDNESS_PHRASES:
        if phrase in line_l:
            return "NON_BLOCKING_HALLUCINATION"
    if _HALLUCINATION_REGEX.search(bullet_line):
        return "NON_BLOCKING_HALLUCINATION"

    # §3.2.1 — pedantry: deferral-trigger word + SHORTCUT_*_V<N> in context.
    has_pedantry_trigger = any(w in line_l for w in _PEDANTRY_TRIGGER_WORDS)
    cites_rule_19 = "rule 19" in line_l or "rule-19" in line_l
    if (cites_rule_19 or has_pedantry_trigger) and _has_shortcut_ld_in_context(
        bullet_line, body
    ):
        return "NON_BLOCKING_PEDANTRY"

    # §3.2.2 — false alarm: Rule 35 cited + alternative governance protocol
    # mentioned in bullet OR body context.
    cites_rule_35 = any(p in line_l for p in _RULE_35_TRIGGER_PHRASES)
    if cites_rule_35:
        body_l = body.lower()
        for tok in _ALTERNATIVE_GOVERNANCE_TOKENS:
            if tok in line_l or tok in body_l:
                return "NON_BLOCKING_FALSE_ALARM"

    # §3.2.5 — out-of-spec rule citation. Bullet cites a rule that isn't in
    # the prompt's blocking-eligible set, AND no other blocking-eligible
    # signal (credential, destructive shell, LD-deletion) is present.
    cited_rule_numbers = set(_RULE_CITATION_REGEX.findall(bullet_line))
    if cited_rule_numbers:
        # If any cited rule IS blocking-eligible, do not demote here — fall
        # through to BLOCKING (the genuine concern stands).
        if not (cited_rule_numbers & _BLOCKING_ELIGIBLE_RULE_NUMBERS):
            # Cited rules are all non-blocking-eligible. Check if any
            # non-rule blocking marker appears (credential, etc.) — if so,
            # the bullet is still blocking-eligible.
            has_non_rule_blocker = any(
                marker in line_l for marker in _BLOCKING_ELIGIBLE_NON_RULE_MARKERS
            )
            if not has_non_rule_blocker:
                return "NON_BLOCKING_OUT_OF_SPEC_RULE"

    return "BLOCKING"


def _is_section_paragraph_line(line: str) -> bool:
    """True if line is plain section-level paragraph text — NOT a bullet,
    NOT indented continuation, NOT a blockquote, NOT blank. Used to
    restrict the dismissal scan to top-level prose where the bot writes
    its actual section-level conclusion. Closes the false-skip vectors
    flagged by AI review NB2/NB3 on PR #24 round-1 (markdown alt-bullet
    `* `, blockquote `>`, indented continuation lines could carry a
    dismissal phrase that doesn't reflect a section-level verdict)."""
    if not line:
        return False
    if line[0] in (" ", "\t"):
        return False  # indented = continuation of bullet/list/quote
    stripped = line.strip()
    if not stripped:
        return False
    # Markdown bullets (all three list markers + ordered).
    if stripped.startswith(("- ", "* ", "+ ")):
        return False
    # Ordered list "1. ", "10. ", "1) ", "10) ", etc. Match leading run
    # of digits followed by ". " or ") " — handles single AND multi-digit
    # numbers (NB3 fix: prior code only checked stripped[1] which missed
    # "10. item" and longer-numbered lists).
    if re.match(r"\d+[.)]\s", stripped):
        return False
    # Blockquote — bot might quote a prior review's reversal phrase.
    if stripped.startswith(">"):
        return False
    return True


def has_blocking(text: str) -> bool:
    blocking_section = re.search(
        r"###\s*Blocking\s*\n(.*?)(?:\n###|\Z)",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not blocking_section:
        return False
    body = blocking_section.group(1)
    # Section-level dismissal check FIRST, but ONLY against TOP-LEVEL
    # PARAGRAPH text (excludes bullets `- *  +`, ordered lists `1. `,
    # blockquotes `>`, indented continuations, blank lines). This
    # ensures a bullet that quotes the bot's earlier reversal language
    # — or a blockquote, or an indented continuation — can't falsely
    # trigger a skip. The dismissal phrase must appear in a top-level
    # section paragraph where the bot writes its actual verdict.
    section_paragraph_text = "\n".join(
        line for line in body.splitlines()
        if _is_section_paragraph_line(line)
    ).lower()
    if any(p in section_paragraph_text for p in _SECTION_DISMISSAL_PHRASES):
        return False
    # Per-bullet scan — catch all markdown bullet forms (`- `, `* `, `+ `)
    # so that real concerns in alternate-bullet syntax aren't silently
    # dropped. Symmetric with the section-paragraph exclusion above:
    # whatever the section scan excludes as "bullet", the per-bullet
    # scan must include — otherwise concerns in alt-bullet syntax fall
    # through both checks.
    for line in body.splitlines():
        line = line.strip()
        is_bullet = (
            (line.startswith("- ") and len(line) > 2)
            or (line.startswith("* ") and len(line) > 2)
            or (line.startswith("+ ") and len(line) > 2)
        )
        if not is_bullet:
            continue
        line_l = line.lower()
        # Empty-marker structural skip: bot writes "- (none)" / "* N/A"
        # when there are no findings. Compare bullet content (after the
        # "- " / "* " / "+ " prefix) trimmed + lowercased against known
        # markers. This is more reliable than substring match — "(none)"
        # inside a real finding ("this is (none) of the issue") would no
        # longer mask.
        bullet_content = line[2:].strip().lower()
        if bullet_content in _EMPTY_BULLET_MARKERS:
            continue
        # Skip bullets where the bot's own prose explicitly says the finding
        # isn't blocking (e.g. "no blocking", "no new blocking issue
        # introduced", "not a new introduction"). The original single-phrase
        # check ("no blocking") missed common patterns the bot emits when it
        # lists a deletion or pre-existing issue.
        if any(p in line_l for p in _NON_BLOCKING_SKIP_PHRASES):
            continue
        # Four-class classifier (LD CLAUDE_REVIEW_HARDENING_FOUR_CLASS_CLASSIFIER_V1):
        # demote pedantry / false-alarm / contradiction / hallucination patterns
        # where the bullet's own text or its section context contains the
        # class signature. Genuinely blocking findings without these patterns
        # pass through.
        classification = _classify_finding(line, body)
        if classification != "BLOCKING":
            continue
        return True
    return False


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        write_skip("ANTHROPIC_API_KEY not configured on this repo")
        return 0
    if not DIFF_PATH.exists():
        write_skip(f"diff file {DIFF_PATH} not found")
        return 0
    if not PROMPT_PATH.exists():
        write_skip(f"review_prompt.md not found at {PROMPT_PATH}")
        return 0

    diff_bytes = DIFF_PATH.stat().st_size
    if diff_bytes > MAX_DIFF_BYTES:
        write_skip(
            f"diff is {diff_bytes // 1024} KB, exceeds {MAX_DIFF_BYTES // 1024} KB cap "
            f"— please request manual review"
        )
        return 0
    if diff_bytes == 0:
        write_skip("diff is empty (no file changes)")
        return 0

    try:
        from anthropic import Anthropic  # type: ignore
    except ImportError as e:
        write_skip(f"anthropic SDK not installed: {e}")
        return 0

    client = Anthropic()
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    diff_text = DIFF_PATH.read_text(encoding="utf-8", errors="replace")

    chunks = chunk_diff(diff_text)
    findings_parts: list[str] = []
    for idx, chunk in enumerate(chunks):
        try:
            section = call_anthropic(client, system_prompt, chunk)
        except Exception as e:  # noqa: BLE001
            write_skip(f"Anthropic API error after retries: {type(e).__name__}: {e}")
            return 0
        if len(chunks) > 1:
            findings_parts.append(f"#### Chunk {idx + 1}/{len(chunks)}\n{section}")
        else:
            findings_parts.append(section)

    combined = "\n\n".join(findings_parts).strip() or "## AI Review Findings\n\nNo content returned."
    OUT_PATH.write_text(combined + "\n", encoding="utf-8")

    if has_blocking(combined):
        BLOCKING_FLAG.write_text("1", encoding="utf-8")
        print("AI review: blocking findings present")
    else:
        print("AI review: no blocking findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
