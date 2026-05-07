"""
Arc 10 cascade — batch replacements across the 4 canonical docs.

Performs targeted find-and-replace for V1-cascade-banner language. Preserves
historical narrative paragraphs that describe the pre-cascade design intentionally.

For each replacement, reports:
    file, count_before, count_after, pattern

Writes modified content back. Does NOT touch files outside the whitelist.
"""
from __future__ import annotations
import os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TARGETS = [
    "Canon/CLAUDE_Everdale_World_Design_Bible_v13_13.md",
    "Canon/NARRATIVE_DECISIONS_UNIFIED_v2_9.md",
    "Canon/CANONICAL_DATA_MODEL_v1_14.md",
    "Canon/UNIFIED_TECHNIQUE_INVENTORY_v1_16.md",
    "CLAUDE.md",
]

# Ordered list — first matches have higher specificity. Later general patterns
# must not undo earlier specific replacements, which is enforced by the ordering.
REPLACEMENTS = [
    # Highly specific V1 cascade banner text — full rewrites
    (
        "V1 ships **54 modules • 6 creatures • 9 story arcs** (Arcs 1-9 — Arc 8 Hopegrove REINSTATED 2026-04-20 evening; Benson REINSTATED 2026-04-21 at M3 after Arc 8 reinstatement made his cut narratively incoherent). Arc 10 THE RETURN deferred V1.x.",
        "V1 ships **59 modules • 6 creatures • 10 story arcs** (Arcs 1-10, none cut — Arc 8 Hopegrove REINSTATED 2026-04-20 evening; Benson REINSTATED 2026-04-21 at M3; Arc 10 THE RETURN RESTORED 2026-04-22 per LD-358, shipping M55-M59).",
    ),
    (
        "**6 creatures (Benson at M3 restored 2026-04-21)**, **9 arcs (Arcs 1-9 — Arc 8 Hopegrove REINSTATED 2026-04-20 evening)**, **54 modules** (9 × 6)",
        "**6 creatures (Benson at M3 restored 2026-04-21)**, **10 arcs (Arcs 1-10, none cut; Arc 10 THE RETURN restored 2026-04-22 per LD-358)**, **59 modules** (9 × 6 + Arc 10 × 5)",
    ),
    # Summary tables and structural rows
    (
        "9 arcs (typically 5--6 modules each): Arc 1 The Gathering, Arc 2 Everdale, Arc 3 Foxhollow, Arc 4 Nieva, Arc 5 Dragonshell, Arc 6 HoneyPot (5 modules, detective arc), Arc 7 Cliffside (Luna), Arc 8 Hopegrove (Benson, skeleton v4 complete), Arc 9 TBD (Bork/Luminara). Arc 10: The Restoration (Master Light Keeper win). Full game = ~54 modules (all 9 arcs ship as complete product).",
        "10 arcs (Arcs 1-10, none cut; V1 ships complete). Arc 1 The Gathering, Arc 2 Everdale, Arc 3 Foxhollow, Arc 4 Nieva, Arc 5 Dragonshell, Arc 6 HoneyPot (5 modules, detective arc), Arc 7 Cliffside (Luna), Arc 8 Hopegrove (Benson), Arc 9 Luminara (Bork), Arc 10 THE RETURN (M55-M59 — Kindness/Watching/Courage/Breathing/Integrated Somatic; M59 uniquely guided by Ophelia). Full V1 = 59 modules (9 arcs × 6 + Arc 10 × 5).",
    ),
    (
        "~54 modules for full game.",
        "59 modules for full game (9 arcs × 6 + Arc 10 × 5 per LD-358).",
    ),
    # Subtle current-state references that were "complete product, all 9 arcs, ~54 modules"
    (
        "all 9 arcs, ~54 modules",
        "all 10 arcs, 59 modules (LD-358 Arc 10 restoration)",
    ),
    (
        "Full game = ~54 modules (Arcs 1--9, typically 5--6 per arc).",
        "Full V1 = 59 modules (Arcs 1-10: 9 arcs × 6 + Arc 10 × 5 per LD-358).",
    ),
    (
        "Full game = ~54 modules (Arcs 1--9).",
        "Full V1 = 59 modules (Arcs 1-10; 9 arcs × 6 + Arc 10 × 5 per LD-358).",
    ),
    # GAMEPLAY_SCOPE reference bump
    ("GAMEPLAY_SCOPE_v2", "GAMEPLAY_SCOPE_v3"),
    # CLAUDE.md — the rule explanation that says "54 modules x many user sessions"
    ("54 modules × many user sessions", "59 modules × many user sessions"),
    # Arc 10 deferred language (catch remaining instances not matched above)
    (
        "Arc 10 THE RETURN deferred V1.x.",
        "Arc 10 THE RETURN IN V1 (restored 2026-04-22 per LD-358; M55-M59).",
    ),
    (
        "Arc 10 THE RETURN deferred V1.x",
        "Arc 10 THE RETURN IN V1 (restored 2026-04-22 per LD-358; M55-M59)",
    ),
    # Standalone "9+ arcs" phrasing (used in design overview)
    ("6 creatures, 9+ arcs, ~54 modules", "6 creatures, 10 arcs, 59 modules"),
    # Pass 2 — residuals from first-pass grep
    # Bible block-quote design snapshot headers
    (
        "> ~54 modules • 6 creatures • 9 story arcs • Complete map • Complete",
        "> 59 modules • 6 creatures • 10 story arcs (Arcs 1-10) • Complete map • Complete",
    ),
    (
        "At typical engagement (1--2 modules per week), ~54 modules provides",
        "At typical engagement (1--2 modules per week), 59 modules provides",
    ),
    # Cost line
    (
        "~$0.03 per child for the entire MVP (~54 modules × ~100",
        "~$0.03 per child for the entire MVP (59 modules × ~100",
    ),
    # Arc 8 row inside Bible summary table
    (
        "V1 now ships 9 arcs (Arcs 1-9).",
        "V1 now ships 10 arcs (Arcs 1-10 — Arc 10 restored 2026-04-22 per LD-358).",
    ),
    # Spell Book + ~54 modules
    (
        "With ~54 modules and the Spell Book providing infinite replay",
        "With 59 modules (9 arcs × 6 + Arc 10 × 5 per LD-358) and the Spell Book providing infinite replay",
    ),
    # Roadmap MVP line
    (
        "MVP = 24 modules (Arcs 1--4). Full game = ~54 modules (Arcs 1--9,",
        "MVP = 24 modules (Arcs 1-4). Full V1 = 59 modules (Arcs 1-10; 9 arcs × 6 + Arc 10 × 5 per LD-358),",
    ),
    # Technique-pool sizing line
    ("~54 module slots", "59 module slots"),
    (
        "Surplus of ~13 over the ~54 module slots needed.",
        "Surplus of ~8 over the 59 module slots needed.",
    ),
    # CDM line 7 banner (huge — full rewrite to reflect Arc 10)
    (
        "V1 ships **54 modules across 9 arcs (Arcs 1-9 — Arc 8 Hopegrove REINSTATED 2026-04-20 evening)** with **6 creatures** (Tessa, Luna, Benson, Ember, Bork, Bramble) and **7 stones** (6 domain + 1 Wisdom keystone). Arc 10 THE RETURN (M55-M59) deferred V1.x. Schema `source: \"official\"` rows should be 54 for V1.",
        "V1 ships **59 modules across 10 arcs (Arcs 1-10, none cut — Arc 8 Hopegrove REINSTATED 2026-04-20 evening; Arc 10 THE RETURN RESTORED 2026-04-22 per LD-358)** with **6 creatures** (Tessa, Luna, Benson, Ember, Bork, Bramble) and **7 stones** (6 domain + 1 Wisdom keystone). Arc 10 modules M55-M59 ship as part of V1. Schema `source: \"official\"` rows should be 59 for V1.",
    ),
    # CDM 491
    (
        "All ~54 modules are `source: \"official\"`, `createdBy: null`, `status: \"published\"`. The seed modules are `productionTier: \"seed\"`; the remainder are `productionTier: \"ai_drafted\"`.",
        "All 59 modules (9 arcs × 6 + Arc 10 × 5) are `source: \"official\"`, `createdBy: null`, `status: \"published\"`. The seed modules are `productionTier: \"seed\"`; the remainder are `productionTier: \"ai_drafted\"`.",
    ),
    # Technique 587 — pool description
    (
        "**Modules needed (Arcs 1–9):** ~54 (9 arcs × 6 modules).",
        "**Modules needed (Arcs 1-10):** 59 (9 arcs × 6 + Arc 10 × 5 per LD-358).",
    ),
    # Technique 737 — Arc 9 V1 cascade tag that says "9 arcs"
    (
        "**[V1 CASCADE TAG 2026-04-20 — V1_SCOPE_CONDENSED_20260420 (revised evening)]** Arc 9 Luminara is IN V1 per 2026-04-20 evening reversal (V1 now ships 9 arcs total: Arcs 1-9). Technique assignments below are V1-shipping.",
        "**[V1 CASCADE TAG 2026-04-22 — V1_SCOPE_CONDENSED_20260420 (revised x3) + LD-358 V1_ARC10_RESTORED_WITH_ARC8_20260421]** Arc 9 Luminara and Arc 10 THE RETURN are both IN V1 (V1 now ships 10 arcs total: Arcs 1-10, 59 modules). Technique assignments below are V1-shipping.",
    ),
    # Deferred V1.x phrasing variants (past-tense residuals)
    (
        "Arc 10 THE RETURN (M55-M59) deferred V1.x.",
        "Arc 10 THE RETURN (M55-M59) IN V1 (restored 2026-04-22 per LD-358).",
    ),
]


def apply_replacements(path: str) -> dict:
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return {"path": path, "skipped": True, "reason": "missing"}
    with open(full, "r", encoding="utf-8") as f:
        content = f.read()
    original = content
    counts = []
    for old, new in REPLACEMENTS:
        c = content.count(old)
        if c:
            content = content.replace(old, new)
            counts.append((old[:60] + ("..." if len(old) > 60 else ""), c))
    if content == original:
        return {"path": path, "changed": False, "replacements": []}
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    return {"path": path, "changed": True, "replacements": counts}


def main() -> int:
    results = []
    for t in TARGETS:
        r = apply_replacements(t)
        results.append(r)
        print(f"--- {r['path']} ---")
        if r.get("skipped"):
            print(f"  SKIPPED: {r.get('reason')}")
            continue
        if not r.get("changed"):
            print("  no changes (patterns not found)")
            continue
        for pat, n in r["replacements"]:
            print(f"  {n}x  {pat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
