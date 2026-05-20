"""XML-leak-token sanitization for Directus MCP write tools.

Per LD-760 DIRECTUS_MCP_XML_TOKEN_SANITIZATION_V1 (locked 2026-05-17,
SHIPPED 2026-05-20 after retroactive fabrication-scan caught sanitize.py
as missing-from-disk).

Strips four narrow leak-token patterns documented in LD-743:
  1. Opening parameter tag pattern: <parameter name="...">
  2. Closing parameter tag pattern: </parameter>
  3. Closing tags whose name matches Directus-field shape
     (lowercase + underscore + digits, 2+ chars inside brackets)
  4. HTML-escaped equivalents (&lt;...&gt;)

Truncate-at-earliest-token semantic: when a leak token appears at
position N, the string is truncated to value[:N].

List elements that become empty after truncation are dropped.

INTENTIONALLY NARROW: code samples with angle brackets, math
comparisons, escaped prose, and opening tags WITHOUT slash all pass
through unchanged.

Logging: stderr WARN per stripped field with field path + 60-char
excerpt + token count.

Use:
    from tools.sanitize import sanitize_payload
    cleaned = sanitize_payload(payload, field_prefix="prod_locked_decisions.decision_text")
"""
from __future__ import annotations

import re
import sys
from typing import Any

# ────────────────────────────────────────────────────────────────────────
# Leak-token regexes (LD-743 patterns)
# ────────────────────────────────────────────────────────────────────────
# Pattern 1: opening parameter tag — <parameter name="..."> or <parameter ...>
_OPEN_PARAM_RE = re.compile(r'<parameter\b[^>]*>', re.IGNORECASE)

# Pattern 2: closing </parameter> tag
_CLOSE_PARAM_RE = re.compile(r'</parameter\s*>', re.IGNORECASE)

# Pattern 3: closing tag whose name matches Directus-field shape.
# Directus field names contain an underscore OR digit (e.g. decision_text,
# beat_id, video_role) — this distinguishes from common HTML tags like
# <div>, <span>, <p>, <button>, <a>. Pattern requires at least one _ or
# digit somewhere in the tag name (after the first char).
_DIRECTUS_FIELD_CLOSING_TAG_RE = re.compile(
    r'</[a-z][a-z0-9_]*[_0-9][a-z0-9_]*\s*>', re.IGNORECASE
)

# Pattern 4: HTML-escaped equivalents (&lt;...&gt; for any of the above).
# Note: between &lt; and &gt; we allow ANY non-greedy chars EXCEPT `<`
# (which would start a new tag). HTML entities like &quot; CAN appear
# inside, so we can't exclude `&` entirely.
_HTML_ESC_OPEN_PARAM_RE = re.compile(
    r'&lt;parameter\b[^<]*?&gt;', re.IGNORECASE
)
_HTML_ESC_CLOSE_PARAM_RE = re.compile(r'&lt;/parameter\s*&gt;', re.IGNORECASE)
_HTML_ESC_FIELD_CLOSE_RE = re.compile(
    r'&lt;/[a-z][a-z0-9_]*[_0-9][a-z0-9_]*\s*&gt;', re.IGNORECASE
)

# Order matters: more-specific patterns first (parameter > generic field).
_ALL_PATTERNS = [
    ("open_parameter_tag", _OPEN_PARAM_RE),
    ("close_parameter_tag", _CLOSE_PARAM_RE),
    ("html_esc_open_parameter", _HTML_ESC_OPEN_PARAM_RE),
    ("html_esc_close_parameter", _HTML_ESC_CLOSE_PARAM_RE),
    ("directus_field_closing_tag", _DIRECTUS_FIELD_CLOSING_TAG_RE),
    ("html_esc_field_closing_tag", _HTML_ESC_FIELD_CLOSE_RE),
]


# ────────────────────────────────────────────────────────────────────────
# Sanitization core
# ────────────────────────────────────────────────────────────────────────
def find_earliest_leak_position(value: str) -> tuple[int, str] | None:
    """Find the leftmost leak-token match. Returns (position, pattern_name) or None."""
    earliest_pos = None
    earliest_pattern = None
    for name, regex in _ALL_PATTERNS:
        m = regex.search(value)
        if m is None:
            continue
        if earliest_pos is None or m.start() < earliest_pos:
            earliest_pos = m.start()
            earliest_pattern = name
    if earliest_pos is None:
        return None
    return earliest_pos, earliest_pattern  # type: ignore


def sanitize_string(value: str, field_path: str = "") -> tuple[str, list[str]]:
    """Truncate at the earliest leak-token. Returns (cleaned, pattern_names_stripped).

    If no leak token found: returns (value, []) unchanged.
    If leak found at position N: returns (value[:N], [pattern_name]).
    """
    if not isinstance(value, str) or not value:
        return value, []
    result = find_earliest_leak_position(value)
    if result is None:
        return value, []
    pos, pattern_name = result
    excerpt = value[max(0, pos - 30): pos + 30].replace("\n", "\\n")
    print(
        f"[mcp:sanitize] WARN field={field_path!r} stripped at pos={pos} "
        f"pattern={pattern_name} excerpt={excerpt!r}",
        file=sys.stderr,
        flush=True,
    )
    return value[:pos].rstrip(), [pattern_name]


def sanitize_payload(payload: Any, field_prefix: str = "") -> Any:
    """Recursively sanitize a payload (dict / list / str). Returns cleaned copy.

    Empty strings produced by truncation are kept; empty LIST elements
    (post-sanitization) are DROPPED per LD-760 spec.
    """
    if isinstance(payload, str):
        cleaned, _ = sanitize_string(payload, field_prefix)
        return cleaned
    if isinstance(payload, dict):
        out = {}
        for k, v in payload.items():
            new_prefix = f"{field_prefix}.{k}" if field_prefix else k
            out[k] = sanitize_payload(v, new_prefix)
        return out
    if isinstance(payload, list):
        cleaned_items = []
        for idx, item in enumerate(payload):
            new_prefix = f"{field_prefix}[{idx}]"
            cleaned = sanitize_payload(item, new_prefix)
            # Drop empty list elements (strings that became "" after truncation)
            if isinstance(cleaned, str) and not cleaned.strip():
                continue
            cleaned_items.append(cleaned)
        return cleaned_items
    # Other types (int, float, bool, None): pass through
    return payload
