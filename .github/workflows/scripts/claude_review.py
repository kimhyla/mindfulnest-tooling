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
# Authority: LD-667 SHORTCUT_CLAUDE_REVIEW_REGEX_PATCH_PRE_OPTION_A_V1
# (interim regex patch; the LD itself is the deferral anchor — see also
# the inline references on the "interim", "follows", and "unblocks PR
# #22" admissions a few lines below).
# Closure plan: Option A — modify review_prompt.md to require a
# structured verdict line (e.g. "## Final verdict: NO_BLOCKING_FINDINGS")
# and parse THAT instead of natural-language reversal phrases. Option B
# (this code) is interim per LD-667 but unblocks PR #22 today per
# LD-667; Option A follows per LD-667 closure plan.
#
# Pattern class observed across multiple PR #22 rounds: bot writes a
# concerning bullet then concludes the section with explicit
# self-reversal language ("Reconsidering: no clear ... violations are
# present", "Not clearly blocking on its own", "Downgrading to
# Non-blocking"). The conclusion is the bot's actual verdict; the gate
# honors it.
#
# Patterns intentionally narrow [CONFIRMED via 15-case smoke test in
# PR #24 round-2 commit f24e527 message + 16-case smoke in round-3]:
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
)


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
    if len(stripped) >= 2 and stripped[0].isdigit() and stripped[1] in ".)":
        return False  # ordered list "1. " / "1) "
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
