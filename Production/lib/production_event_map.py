"""Structured Production Event Map — single source for play-order slots and prod_modules.

Encodes PRODUCTION_EVENT_MAP_v1.md (Dropbox canonical doc). Re-read that doc when
updating; this module is the tooling-repo runtime authority per LD PROD_MODULES
_GAMEPLAY_SCOPE_SOURCE_V1 (Judgment Call 2, Kim 2026-07-04).
"""
from __future__ import annotations

from typing import Any, Iterator

# Per-arc ordered play-order slots. kind: module | milestone | narrative
# confidence defaults to confirmed unless noted.
ARC_SLOTS: dict[int, list[dict[str, Any]]] = {
    1: [
        {"kind": "narrative", "label": "Opening Video Sequence", "confidence": "confirmed"},
        {"kind": "narrative", "label": "Avatar Creation", "confidence": "confirmed"},
        {"kind": "narrative", "label": "Guide Bird Introduction", "confidence": "confirmed"},
        {"kind": "narrative", "label": "Map Landing", "confidence": "confirmed"},
        {
            "kind": "module",
            "m_number": 1,
            "creature": "Tessa",
            "spell_name": "Magic Hands Spell",
            "technique_name": "Palm Interoception",
            "label": "M1 — Tessa, Magic Hands Spell",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 2,
            "creature": "Luna",
            "spell_name": "Breath-Squeezers Spell",
            "technique_name": "Squeeze-and-Release",
            "label": "M2 — Luna, Breath-Squeezers Spell",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 4,
            "creature": "Ember",
            "spell_name": "Heart-Sending Spell",
            "technique_name": "Art of Kindness",
            "label": "M4 — Ember, Heart-Sending Spell",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Oliver Meet",
            "suggested_milestone_id": "oliver_meet",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 6,
            "creature": "Bramble",
            "spell_name": "Humming Spell",
            "technique_name": "Humming Breath",
            "label": "M6 — Bramble, Humming Spell",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 3,
            "creature": "Benson",
            "spell_name": "Brave Sniffing Spell",
            "technique_name": "Physiological Sigh",
            "label": "M3 — Benson, Brave Sniffing Spell",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 5,
            "creature": "Bork",
            "spell_name": "Letting Go Spell",
            "technique_name": "Letting Go",
            "label": "M5 — Bork, Letting Go Spell",
            "confidence": "confirmed",
        },
        {"kind": "narrative", "label": "Agent Encounter", "confidence": "confirmed"},
    ],
    2: [
        {"kind": "narrative", "label": "Arc 2 Intro", "confidence": "confirmed"},
        {
            "kind": "module",
            "m_number": 7,
            "creature": "Luna",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M7 — Luna (free-order w/ M8)",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 8,
            "creature": "Bramble",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M8 — Bramble (free-order w/ M7)",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Willow's Entrance (gates M9)",
            "suggested_milestone_id": "willows_entrance",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 9,
            "creature": "Ember",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M9 — Ember (co-facilitated by Willow)",
            "confidence": "confirmed",
        },
        {
            "kind": "narrative",
            "label": "King's Arrival cinematic (4 beats)",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 13,
            "creature": "Oliver",
            "spell_name": "4-7-8 Breathe Spell",
            "technique_name": "Breath Awareness",
            "label": "M13 — Oliver, 4-7-8 Breathe Spell",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 10,
            "creature": "Bork",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M10 — Bork (parallel w/ M11, M12)",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 11,
            "creature": "Luna",
            "spell_name": "Thought Clouds Spell",
            "technique_name": "TBD",
            "label": "M11 — Luna, Thought Clouds Spell",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 12,
            "creature": "Benson",
            "spell_name": "Strong Push Spell",
            "technique_name": "TBD",
            "label": "M12 — Benson, Strong Push Spell",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Investigation Thread (3 short beats)",
            "suggested_milestone_id": "willow_investigation",
            "creature": "Willow",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Revelation + Departure",
            "suggested_milestone_id": "willow_revelation",
            "creature": "Willow",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Mission Briefing + Zap Distribution",
            "suggested_milestone_id": "mission_briefing",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Memory Charm + Departure",
            "suggested_milestone_id": "memory_charm_departure",
            "confidence": "confirmed",
        },
    ],
    3: [
        {
            "kind": "milestone",
            "label": "Arrival at Foxhollow",
            "suggested_milestone_id": "foxhollow_arrival",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 14,
            "creature": "Fox cub",
            "spell_name": "Humming Spell: Evolution",
            "technique_name": "TBD",
            "label": "M14 — Fox cub, Humming Spell: Evolution",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 15,
            "creature": "Beatriz",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M15 — Beatriz",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 16,
            "creature": "Mama Hearth",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M16 — Mama Hearth",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 17,
            "creature": "Grandpa Stanley",
            "spell_name": "Gentle Flow Spell",
            "technique_name": "TBD",
            "label": "M17 — Grandpa Stanley, Gentle Flow Spell",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Underground Journey",
            "suggested_milestone_id": "underground_journey",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 18,
            "creature": "The Heart Stone",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M18 — The Heart Stone",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 19,
            "creature": "Village of Foxhollow",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M19 — Village of Foxhollow",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Departure",
            "suggested_milestone_id": "foxhollow_departure",
            "confidence": "confirmed",
        },
    ],
    4: [
        {
            "kind": "milestone",
            "label": "Arrival at the Hamlet (video)",
            "suggested_milestone_id": "hamlet_arrival",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 20,
            "creature": "Mountain goat",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M20 — Mountain goat",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 21,
            "creature": "Oliver",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M21 — Oliver",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "The Invitation (Nieva Guard dialogue)",
            "suggested_milestone_id": "nieva_invitation",
            "creature": "Nieva Guard",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 22,
            "creature": "The party",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M22 — The party",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 23,
            "creature": "Young snow leopard",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M23 — Young snow leopard",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 24,
            "creature": "Willow",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M24 — Willow",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Court of Nieva Part 1 (video)",
            "suggested_milestone_id": "court_of_nieva_part1",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 25,
            "creature": "First Mother/child",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M25 — First Mother/child",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Permission and Departure (video)",
            "suggested_milestone_id": "nieva_permission_departure",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Carriage Reward Screen (interstitial)",
            "suggested_milestone_id": "carriage_reward",
            "confidence": "confirmed",
        },
    ],
    5: [
        {
            "kind": "milestone",
            "label": "The Coastal Road (arrival/reunion video)",
            "suggested_milestone_id": "coastal_road",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Tessa's Announcement / Grand Warden grants trial",
            "suggested_milestone_id": "tessa_announcement",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 26,
            "creature": "Tessa",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M26 — Tessa",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 27,
            "creature": "Tessa",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M27 — Tessa",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Pearl/Eddy react to Pipsqueak (video)",
            "suggested_milestone_id": "pearl_eddy_react",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 28,
            "creature": "Pipsqueak",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M28 — Pipsqueak (Evolution of M25)",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 29,
            "creature": "Tessa + child",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M29 — Tessa + child (Rite of Great Transformation)",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 30,
            "creature": "Tessa + Willow",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M30 — Tessa + Willow",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 31,
            "creature": "Tessa + child",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M31 — Tessa + child",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Departure (video)",
            "suggested_milestone_id": "dragonshell_departure",
            "confidence": "confirmed",
        },
    ],
    6: [
        {
            "kind": "milestone",
            "label": "Arrival + HoneyPot Tour (video)",
            "suggested_milestone_id": "honeypot_arrival",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 32,
            "creature": "Cooper",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M32 — Cooper",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 33,
            "creature": "Rufus",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M33 — Rufus",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 34,
            "creature": "Thornlius",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M34 — Thornlius",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 35,
            "creature": "Bramble",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M35 — Bramble (Humming Wand reward)",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 36,
            "creature": "Bramble",
            "spell_name": "Humming Roots Spell",
            "technique_name": "TBD",
            "label": "M36 — Bramble, Humming Roots Spell",
            "confidence": "confirmed",
        },
        {
            "kind": "narrative",
            "label": "Thornlius' Question / Light Keeper Beat + Departure",
            "confidence": "confirmed",
        },
    ],
    7: [
        {
            "kind": "milestone",
            "label": "Arrival (video)",
            "suggested_milestone_id": "owl_college_arrival",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 37,
            "creature": "Luna",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M37 — Luna",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Grizzle's Return",
            "suggested_milestone_id": "grizzles_return",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 38,
            "creature": "Bramble",
            "spell_name": "Humming Roots Spell: Evolution",
            "technique_name": "TBD",
            "label": "M38 — Bramble, Humming Roots Spell: Evolution",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 39,
            "creature": "Luna",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M39 — Luna",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 40,
            "creature": "Bramble",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M40 — Bramble",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 41,
            "creature": "Oliver",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M41 — Oliver",
            "confidence": "confirmed",
        },
        {
            "kind": "narrative",
            "label": "Benson's Zap",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 42,
            "creature": "Luna",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M42 — Luna",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Dragon Patrol: Cliffside",
            "suggested_milestone_id": "dragon_patrol_cliffside",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Departure (2 cuts, video)",
            "suggested_milestone_id": "owl_college_departure",
            "confidence": "confirmed",
        },
    ],
    8: [
        {
            "kind": "milestone",
            "label": "Arrival / Wonder Beat (video)",
            "suggested_milestone_id": "hopegrove_arrival",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 43,
            "creature": "Benson/Oliver",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M43 — Benson/Oliver",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 44,
            "creature": "Benson",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M44 — Benson (Courage)",
            "confidence": "confirmed",
        },
        {
            "kind": "narrative",
            "label": "Wolf Sighting",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 45,
            "creature": "Child",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M45 — Child",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 46,
            "creature": "Child",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M46 — Child (continuous with M45)",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 47,
            "creature": "Oliver",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M47 — Oliver (Wolf Confrontation)",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Atticus Returns & The Prediction (video)",
            "suggested_milestone_id": "atticus_returns",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 48,
            "creature": "Oliver",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M48 — Oliver, Making Room Spell",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Departure (video)",
            "suggested_milestone_id": "hopegrove_departure",
            "confidence": "confirmed",
        },
    ],
    9: [
        {
            "kind": "module",
            "m_number": 49,
            "creature": "Bork",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M49 — Bork (embedded in Arrival video)",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 50,
            "creature": "Bork",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M50 — Bork",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 51,
            "creature": "Rex",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M51 — Rex (mirroring ceremony milestone)",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Dragon Patrol: Luminara (video)",
            "suggested_milestone_id": "dragon_patrol_luminara",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 52,
            "creature": "Bork",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M52 — Bork, Mountain Shrug Spell",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 53,
            "creature": "Rex",
            "spell_name": "TBD",
            "technique_name": "TBD",
            "label": "M53 — Rex",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Oliver's Mother (video)",
            "suggested_milestone_id": "olivers_mother",
            "creature": "Oliver",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Departure (video)",
            "suggested_milestone_id": "luminara_departure",
            "confidence": "confirmed",
        },
    ],
    10: [
        {
            "kind": "narrative",
            "label": "Arc opens — Zap call to muster homelands",
            "creature": "Bork/Benson",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 55,
            "creature": "Ember",
            "spell_name": "TBD",
            "technique_name": "Gratitude/Savoring (K-1)",
            "label": "M55 — Ember",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 56,
            "creature": "Luna",
            "spell_name": "TBD",
            "technique_name": "Eye Palming (VP-1)",
            "label": "M56 — Luna",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 57,
            "creature": "Oliver (via child)",
            "spell_name": "TBD",
            "technique_name": "Lion's Breath (CO-M6)",
            "label": "M57 — Oliver (via child)",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 58,
            "creature": "Child",
            "spell_name": "TBD",
            "technique_name": "Extended Exhale",
            "label": "M58 — Child (Ophelia appears)",
            "confidence": "confirmed",
        },
        {
            "kind": "milestone",
            "label": "Ophelia's address, King stands down",
            "suggested_milestone_id": "ophelia_address",
            "creature": "Ophelia",
            "confidence": "confirmed",
        },
        {
            "kind": "module",
            "m_number": 59,
            "creature": "Child, guided by Ophelia",
            "spell_name": "TBD",
            "technique_name": "Integrated Somatic",
            "label": "M59 — Master Light Keeper ceremony",
            "confidence": "confirmed",
        },
    ],
}

# Verified module counts per arc (modules only — milestones/narratives excluded).
MODULE_COUNT_BY_ARC: dict[int, int] = {
    arc: sum(1 for s in slots if s.get("kind") == "module")
    for arc, slots in ARC_SLOTS.items()
}

# Expected: Arc 1=6, 2=7, 3=6, 4=6, 5=6, 6=5, 7=6, 8=6, 9=5, 10=5 → 58 modules
# prod_modules rows = 60 per V1_SCOPE_EXPANSION (includes M54 gap accounting in Directus)
EXPECTED_MODULE_ROW_COUNT = 60


def modules_per_arc(arc_number: int) -> int:
    """Return module-only count for an arc (Event_N boundary unit)."""
    return MODULE_COUNT_BY_ARC.get(int(arc_number), 0)


def all_arc_numbers() -> list[int]:
    return sorted(ARC_SLOTS.keys())


def iter_slots(*, arc_number: int | None = None) -> Iterator[tuple[int, dict[str, Any]]]:
    arcs = [arc_number] if arc_number is not None else all_arc_numbers()
    for arc in arcs:
        for slot in ARC_SLOTS.get(arc, []):
            yield arc, slot


def iter_module_slots(*, arc_number: int | None = None) -> Iterator[tuple[int, dict[str, Any]]]:
    for arc, slot in iter_slots(arc_number=arc_number):
        if slot.get("kind") == "module":
            yield arc, slot


def global_module_event_index(arc_number: int, m_number: int) -> int | None:
    """1-based global module index → Event_N folder number (modules only)."""
    count = 0
    for arc, slot in iter_module_slots():
        count += 1
        if arc == arc_number and slot.get("m_number") == m_number:
            return count
    return None


def suggested_event_folder_id(arc_number: int, m_number: int) -> str | None:
    idx = global_module_event_index(arc_number, m_number)
    if idx is None:
        return None
    return f"Event_{idx}"


def cumulative_modules_before_arc(arc_number: int) -> int:
    return sum(modules_per_arc(a) for a in range(1, int(arc_number)))


def build_prod_module_rows() -> list[dict[str, Any]]:
    """Rows for Directus prod_modules — one per module slot in play order."""
    rows: list[dict[str, Any]] = []
    for arc, slot in iter_module_slots():
        m_n = int(slot["m_number"])
        module_index = sum(
            1 for a, s in iter_module_slots(arc_number=arc) if int(s["m_number"]) <= m_n
        )
        creature = str(slot.get("creature") or "TBD")
        spell = str(slot.get("spell_name") or "TBD")
        technique = str(slot.get("technique_name") or "TBD")
        # Arc 1 uses real names; later arcs keep honest TBD placeholders until authored
        # unless the map already has verified creature/spell data.
        if arc > 1 and creature == "TBD":
            creature_name = f"M{m_n} — TBD"
        else:
            creature_name = creature
        rows.append(
            {
                "m_number": m_n,
                "arc_number": arc,
                "module_index": module_index,
                "creature_name": creature_name,
                "technique_name": technique,
                "spell_name": spell,
                "video_role": "intro",
            }
        )
    return rows


def slot_by_m_number(m_number: int) -> tuple[int, dict[str, Any]] | None:
    for arc, slot in iter_module_slots():
        if int(slot.get("m_number") or 0) == int(m_number):
            return arc, slot
    return None


def slot_by_suggested_milestone_id(milestone_id: str) -> tuple[int, dict[str, Any]] | None:
    mid = str(milestone_id or "").strip().lower()
    if not mid:
        return None
    for arc, slot in iter_slots():
        if slot.get("kind") != "milestone":
            continue
        suggested = str(slot.get("suggested_milestone_id") or "").strip().lower()
        if suggested == mid:
            return arc, slot
    return None
