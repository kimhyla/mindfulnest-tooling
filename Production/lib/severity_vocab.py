"""severity_vocab.py — vocabulary-tolerant severity helpers for prod_locked_decisions queries.

Per LD SCHEMA_VOCAB_TOLERANT_FILTER_V1 (2026-05-08).

Background
----------
The prod_locked_decisions schema enum was silently migrated 2026-05-04 to
canonical values {HARD, SOFT}. Old values (HIGH/CRITICAL/MEDIUM/LOW + lowercase
+ MED abbrev) still live in 303+ active rows and are still accepted by Directus
on write. This is documented in
`Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md`:

  | severity | count | status |
  |---|---|---|
  | HIGH      | 174   | canonical legacy |
  | CRITICAL  | 129   | canonical legacy |
  | MEDIUM    |  94   | legacy |
  | HARD      |  45   | canonical NEW |
  | SOFT      |  30   | canonical NEW |
  | LOW       |  20   | legacy |
  | high      |  15   | lowercase variant |
  | medium    |  15   | lowercase variant |
  | low       |   3   | lowercase variant |
  | critical  |   2   | lowercase variant |
  | MED       |   2   | abbreviation |

Until a mass migration runs (see SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md),
queries that filter by severity must tolerate the mixed vocabulary or they
will silently filter out genuinely-active rows.

What this module provides
-------------------------
A single canonical normalization rule + ranking dict + filter expansion API:

- `normalize_severity(value)` -> canonical UPPER form (lossless: returns the
  uppercased input as-is; we do NOT remap HIGH->HARD here, that is a migration
  decision Kim has not yet made).
- `SEVERITY_RANK` -> dict mapping every observed legacy + canonical value to
  an integer rank so `>= threshold` comparisons work uniformly.
- `is_high_severity(value)` -> bool, True iff rank >= HIGH-equivalent.
- `expand_severity_filter(min_level)` -> list of every concrete severity value
  Directus might hold whose rank is >= the given level, suitable for a
  `_in` filter expression.

Ranking convention
------------------
Per the report's mapping proposal (Investigation 1, 30-LD sample): HIGH and
HARD are functionally equivalent ("hard rule, must comply"); CRITICAL is a
strict superset of HARD; SOFT and MEDIUM and LOW are progressively softer.
We assign ranks accordingly:

    CRITICAL / critical     -> 4
    HIGH / high / HARD      -> 3
    MEDIUM / medium / MED   -> 2
    SOFT                    -> 2   (live canonical; sits between HARD and LOW)
    LOW / low               -> 1

This means `--min-severity HARD` and `--min-severity HIGH` return the same
rows on the live mixed dataset. Document on the consumer side that MEDIUM
and SOFT are intentionally NOT included in the "high importance" tier;
governance work cares about HARD/HIGH/CRITICAL, not the medium tier.

Note: this module does NOT modify Directus rows. It only provides a
read-side compatibility layer. Mass canonicalization is a separate Kim-gated
session per the migration tech spec.
"""

from __future__ import annotations

from typing import Iterable

# Single source of truth for severity ranking across the codebase. Every
# legacy + canonical + lowercase variant observed in production data
# (per the 2026-05-08 audit) is mapped explicitly. Unknown values rank 0
# so they are filtered out by any `>= threshold` check.
SEVERITY_RANK: dict[str, int] = {
    # canonical NEW (post 2026-05-04 migration)
    "HARD": 3,
    "SOFT": 2,
    # canonical legacy UPPER
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    # legacy lowercase variants (15 high + 15 medium + 3 low + 2 critical rows)
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    # abbreviation (2 rows)
    "MED": 2,
    # empty / null sentinels
    "": 0,
}

# Threshold ranks (use these in consumer code instead of magic numbers).
RANK_CRITICAL = 4
RANK_HIGH = 3
RANK_MEDIUM = 2
RANK_LOW = 1

# Canonical groups (every concrete value Directus might hold for that tier).
EXPANDED_CRITICAL: tuple[str, ...] = ("CRITICAL", "critical")
EXPANDED_HIGH: tuple[str, ...] = ("HARD", "HIGH", "high", "CRITICAL", "critical")
EXPANDED_MEDIUM: tuple[str, ...] = (
    "HARD", "HIGH", "high", "CRITICAL", "critical",
    "SOFT", "MEDIUM", "medium", "MED",
)
EXPANDED_LOW: tuple[str, ...] = (
    "HARD", "HIGH", "high", "CRITICAL", "critical",
    "SOFT", "MEDIUM", "medium", "MED",
    "LOW", "low",
)


def normalize_severity(value: str | None) -> str:
    """Return uppercased severity string. Lossless: HIGH stays HIGH, HARD stays HARD.

    This is NOT a remap to canonical-only values; it only case-folds for
    consistent dict lookup. A migration that rewrites HIGH -> HARD is a
    separate, Kim-gated operation per the migration tech spec.
    """
    return (value or "").strip().upper()


def severity_rank(value: str | None) -> int:
    """Return the integer rank of a severity value across all known variants.

    Lookup is case-sensitive against SEVERITY_RANK so that lowercase variants
    match their lowercase keys. Falls back to 0 for unknown values.
    """
    raw = (value or "").strip()
    if raw in SEVERITY_RANK:
        return SEVERITY_RANK[raw]
    upper = raw.upper()
    return SEVERITY_RANK.get(upper, 0)


def is_high_severity(value: str | None) -> bool:
    """True iff severity rank is >= HIGH (i.e. HARD / HIGH / CRITICAL family)."""
    return severity_rank(value) >= RANK_HIGH


def is_critical_severity(value: str | None) -> bool:
    """True iff severity rank is >= CRITICAL."""
    return severity_rank(value) >= RANK_CRITICAL


def expand_severity_filter(min_level: str) -> list[str]:
    """Return every concrete severity value at-or-above the given minimum.

    Use as input to a Directus `_in` filter when querying prod_locked_decisions:

        client.get_items(
            "prod_locked_decisions",
            filters={"severity": {"_in": expand_severity_filter("HARD")}},
        )

    Aliases:
        HARD <-> HIGH       both expand to {HARD, HIGH, high, CRITICAL, critical}
        SOFT <-> MEDIUM     both expand to the medium tier and above
        CRITICAL            strict (no HARD/HIGH)
        LOW                 everything

    Unknown levels default to HIGH-tier expansion (defensive).
    """
    level = (min_level or "").strip().upper()
    if level in ("CRITICAL",):
        return list(EXPANDED_CRITICAL)
    if level in ("HARD", "HIGH"):
        return list(EXPANDED_HIGH)
    if level in ("SOFT", "MEDIUM", "MED"):
        return list(EXPANDED_MEDIUM)
    if level == "LOW":
        return list(EXPANDED_LOW)
    # default: HIGH tier
    return list(EXPANDED_HIGH)


def filter_rows_by_min_severity(
    rows: Iterable[dict],
    min_level: str,
    severity_field: str = "severity",
) -> list[dict]:
    """In-memory filter helper for already-fetched LD rows.

    Use when the upstream query did not pre-filter by severity (e.g.
    failure_mode_matrix.py fetches all active LDs then trims client-side).
    """
    threshold = SEVERITY_RANK.get(normalize_severity(min_level), RANK_HIGH)
    return [r for r in rows if severity_rank(r.get(severity_field)) >= threshold]


__all__ = [
    "SEVERITY_RANK",
    "RANK_CRITICAL",
    "RANK_HIGH",
    "RANK_MEDIUM",
    "RANK_LOW",
    "EXPANDED_CRITICAL",
    "EXPANDED_HIGH",
    "EXPANDED_MEDIUM",
    "EXPANDED_LOW",
    "normalize_severity",
    "severity_rank",
    "is_high_severity",
    "is_critical_severity",
    "expand_severity_filter",
    "filter_rows_by_min_severity",
]
