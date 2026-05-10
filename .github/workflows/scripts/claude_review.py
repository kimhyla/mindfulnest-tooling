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
    # Anchored bot self-resolution patterns. Replace earlier broad
    # substrings ("not a new", "not a blocker") with longer phrases that
    # are unambiguous self-dismissal — addresses the bot's own concern
    # that short substrings could mask real findings whose text happens
    # to contain "not a new pattern" or "not a blocker for deployment".
    # Note: "is not a blocker" is intentionally OMITTED — even anchored
    # via "is", it still matches "is not a blocker for deployment". Rely
    # on explicit non-blocking markers + "this is a fix" instead.
    "not a new introduction",
    "this is a fix",
)


def has_blocking(text: str) -> bool:
    blocking_section = re.search(
        r"###\s*Blocking\s*\n(.*?)(?:\n###|\Z)",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not blocking_section:
        return False
    body = blocking_section.group(1)
    for line in body.splitlines():
        line = line.strip()
        if not (line.startswith("- ") and len(line) > 2):
            continue
        line_l = line.lower()
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
