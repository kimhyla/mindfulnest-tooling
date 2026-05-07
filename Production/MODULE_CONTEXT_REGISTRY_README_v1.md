# Module Context Registry — README

**Version:** 1.0  
**Date:** April 11, 2026  
**Status:** ACTIVE — Ready for Haiku API integration  

---

## What This Is

The **Module Context Registry** is a structured JSON lookup table that the Haiku API reads at runtime to populate module-specific context into the Guide Bird System Prompt.

When a child taps a creature on the map and triggers a module (e.g., Tessa's M1 "Magic Hands Spell"), the MindfulNest runtime:

1. Identifies the `moduleId` being launched (e.g., `bodysensing_magic_hands`)
2. Queries this registry for the full context object
3. Injects the module context into the Guide Bird System Prompt
4. The Guide Bird's voice generation (via the Haiku API) incorporates the module-specific context

This ensures that the Guide Bird always speaks in the correct tone, references the right spell name and technique, and includes narrative context appropriate to that specific module.

---

## File Location

```
/Claude Mindfulnest Project Files/Production/MODULE_CONTEXT_REGISTRY_v1.json
```

---

## Current Coverage

| Arc | Module Count | Status | Details |
|-----|--------------|--------|---------|
| **Arc 1: The Gathering** | 6 (M1–M6) | ✅ COMPLETE | All modules extracted from ARC_1_SKELETON_DRAFT.md v2.0. Comet revision included. |
| **Arc 2: The King's Visit** | 6 (M7–M12) | ⚠️ PARTIAL | M7–M8 complete. M9–M12 identified but missing technique specs (skeleton stopped at narrative setup). |
| **Arcs 3–9** | 42 (M13–M54) | ⏳ PENDING | Ready for extension. Structure is in place. Arcs 3–9 not yet read. |

---

## JSON Schema

### Top-Level Structure

```json
{
  "_meta": { /* registry metadata */ },
  "arc_1_the_gathering": { /* Arc 1 modules */ },
  "arc_2_the_kings_visit": { /* Arc 2 modules */ },
  "placeholder_arcs_3_9": { /* Placeholder for future arcs */ },
  "usage_guidelines": { /* Implementation docs */ },
  "data_quality_flags": { /* Completeness and issues */ }
}
```

### Per-Arc Structure

Each arc object contains:

```json
{
  "arcNumber": 1,
  "arcName": "The Gathering",
  "arcType": "Crisis / Setup",
  "arcPremise": "...",
  "modulesInArc": 6,
  "playOrder": [ "module_id_1", "module_id_2", ... ],
  "modules": {
    "module_id_1": { /* module context object */ },
    "module_id_2": { /* module context object */ }
  }
}
```

### Module Context Object

Each module entry contains these fields:

#### Identity & Location
- `moduleId`: Unique kebab-case ID (e.g., `bodysensing_magic_hands`)
- `arcNumber`: Arc (1-9)
- `arcName`: Arc name (e.g., "The Gathering")
- `moduleMNumber`: M-number (M1-M54+)
- `barPosition`: Play order (1-6 within arc, NOT M-number)
- `eventNumber`: Event number in skeleton
- `eventTitle`: Narrative event title

#### Creature & Domain
- `moduleCreature`: Creature enum (tessa, luna, benson, ember, bork, bramble)
- `creatureCommonName`: Display name (e.g., "Tessa (Turtle)")
- `moduleDomain`: Domain enum (breathing, watching, kindness, bodysensing, courage, selfgrounding)
- `domainLabel`: Human-readable domain (e.g., "Body-Sensing")

#### Spell & Technique
- `moduleSpellName`: In-world spell name (e.g., "Magic Hands Spell") — **PRIMARY for Guide Bird dialogue**
- `clinicalLabel`: Clinical technique name (e.g., "Palm Interoception / Energy Hands") — therapist-facing only
- `techniqueId`: Reference to UNIFIED_TECHNIQUE_INVENTORY (e.g., "PI-M1", "F-2")

#### Module Type
- `eventType`: `"full_call"` | `"transitional_call"` | `"evolution"` — determines spell evolution mechanic
- `moduleIsEvolution`: Boolean. True if module evolves a previous technique.
- `baseModuleRef`: M-number of base module (if evolution). Otherwise null.
- `classification`: "New Spell" | "Evolution"

#### Narrative Context
- `stoneColor`: Rune color (orange, yellow, red, blue, green, purple) or null
- `stoneInscription`: Inscription carved on rune (Arc 1) or null
- `bridgeDialogueCondition`: What triggers the module narrative (e.g., "Bramble is about to punch the Agent")
- `integrationType`: Integration type (e.g., "Enabling Care", "Task Facilitation")
- `notes`: Implementation notes, flags, or continuity pointers

---

## How the Guide Bird System Prompt Uses This

The Guide Bird System Prompt template has placeholder slots for module context:

```
You are speaking to a 7-year-old child in the role of the Guide Bird,
a warm, energetic, and slightly self-deprecating mentor.

The child is about to practice: {SPELL_NAME}
This spell teaches the Ancient Art of: {DOMAIN_LABEL}
The creature who needs help is: {CREATURE_COMMON_NAME}
The creature's challenge is: {BRIDGE_DIALOGUE_CONDITION}

This is a {CLASSIFICATION} spell. {EVOLUTION_CONTEXT_IF_APPLICABLE}

Speak directly to the child. Use their name ({childName}). Keep your
sentences short (2–3 sentences max). Your tone should be {TONE_GUIDANCE}.

[More system prompt content...]
```

At runtime, the Haiku API receives:

```
POST /v1/messages
{
  "model": "claude-3-5-haiku-20241022",
  "system": "[template with injected MODULE context]",
  "messages": [{ "role": "user", "content": "[Guide Bird call-to-action]" }]
}
```

The injected context ensures the Guide Bird always:
- Uses the correct spell name
- References the right creature and domain
- Understands the specific narrative condition
- Knows whether this is a new spell or evolution (for phrasing)

---

## Field Definitions (Complete Reference)

### moduleId
**Format:** `{domain}_{spell_name_kebab}`  
**Example:** `bodysensing_magic_hands`, `watching_big_little`  
**Purpose:** Unique identifier for the module. Used as the lookup key at runtime.

### arcNumber
**Type:** Integer (1-9+)  
**Purpose:** Which arc the module belongs to.

### arcName
**Type:** String  
**Example:** "The Gathering", "The King's Visit"  
**Purpose:** Human-readable arc name.

### moduleMNumber
**Type:** String (M1-M54+)  
**Example:** "M1", "M7"  
**Important:** M-numbers are FIXED to creatures per the M-Number Convention:
- M1 = Tessa
- M2 = Luna
- M3 = Benson
- M4 = Ember
- M5 = Bork
- M6 = Bramble

Within each arc, the **play order differs from M-number order**. M-numbers never change across arcs.

### barPosition
**Type:** Integer (1-6)  
**Purpose:** Play order position within the arc (the order the child encounters modules). NOT the same as M-number.  
**Example:** M1 (Tessa) appears at barPosition 1 in Arc 1. M2 (Luna) appears at barPosition 2 in Arc 1. But in Arc 2, M7 (Luna) appears at barPosition 1, and M8 (Bramble) appears at barPosition 2.

### eventNumber
**Type:** Integer  
**Purpose:** Matches the "EVENT ##" label in the arc skeleton narrative.

### eventTitle
**Type:** String  
**Example:** "Tessa's Gentle Arrival", "Luna's Discovery"  
**Purpose:** The narrative event title from the skeleton. Used for continuity tracking.

### moduleCreature
**Type:** Enum: tessa | luna | benson | ember | bork | bramble  
**Purpose:** Which creature the module centers on. Derives from M-number.

### creatureCommonName
**Type:** String  
**Example:** "Tessa (Turtle)", "Luna (Owl)"  
**Purpose:** Display name for UI and human-readable reference.

### moduleDomain
**Type:** Enum: breathing | watching | kindness | bodysensing | courage | selfgrounding  
**Purpose:** The Ancient Art domain. Determines rune layer and color.

### domainLabel
**Type:** String  
**Example:** "Body-Sensing", "Now-Watching"  
**Purpose:** Human-readable domain name (for system prompts and therapist-facing docs).

### moduleSpellName
**Type:** String  
**Example:** "Magic Hands Spell", "Big-Little Spell", "Dragon Stomp Spell"  
**Purpose:** The in-world spell name. This is what the child and the Guide Bird use when speaking. PRIMARY reference for Guide Bird dialogue.

### clinicalLabel
**Type:** String  
**Example:** "Palm Interoception / Energy Hands", "Attention Shifting / Flexible Attention"  
**Purpose:** The clinical technique name. For therapist-facing documentation and clinical logs only. NEVER appears in child-facing dialogue.

### techniqueId
**Type:** String (matches UNIFIED_TECHNIQUE_INVENTORY keys)  
**Example:** "PI-M1", "F-2", "BI-M8"  
**Purpose:** Cross-reference to the UNIFIED_TECHNIQUE_INVENTORY_v1_15.md. Provides a link to full clinical specs, sources, and mechanism.

### eventType
**Type:** Enum: `"full_call"` | `"transitional_call"` | `"evolution"`  
**Purpose:** Determines narrative structure.
- **full_call:** Standard module with full Phase A → Phase B → Rescue → Win.
- **transitional_call:** Shorter variant (used between major narrative beats).
- **evolution:** The module evolves a previous technique. Triggers the 3-beat Spell Evolution Mechanic (Guide Bird names original spell → magic audio → names evolved spell + enthusiasm).

### moduleIsEvolution
**Type:** Boolean  
**Purpose:** Is this an evolution of a previously-taught technique?  
- `true` → Spell Evolution Mechanic applies.
- `false` → Standard new spell framing.

### baseModuleRef
**Type:** String (M-number) | null  
**Purpose:** If `moduleIsEvolution` is true, which module does this evolve from?  
**Example:** `"M1"` (if this module evolves M1's technique)  
**null:** If this is a new spell.

### classification
**Type:** String  
**Example:** "New Spell", "Evolution"  
**Purpose:** Determines spell card labeling ("Big-Little Spell" vs. "Big-Little Spell: Evolution").

### integrationType
**Type:** String  
**Example:** "Enabling Care", "Task Facilitation", "Personal Healing", "Access Support", "Contribution"  
**Purpose:** How the technique integrates into the arc narrative. For documentation and continuity tracking.

### stoneColor
**Type:** String | null  
**Example:** "orange", "yellow", "red", "blue", "green", "purple"  
**Purpose:** The color of the rune stone associated with this module (Arc 1 and beyond). Used for rune layer visuals.  
**null:** If the module doesn't have a physical stone (post-Arc 1, some modules).

### stoneInscription
**Type:** String | null  
**Example:** "Feel what's real", "Stay loose and light"  
**Purpose:** The inscription carved into the rune stone (Arc 1). Used for narrative immersion and inscription puzzle.  
**null:** If no physical stone.

### bridgeDialogueCondition
**Type:** String | null  
**Example:** "Luna tries to come up with a plan but can't think of anything that works"  
**Purpose:** Brief description of the narrative condition that triggers the module. Contextualizes the Guide Bird's call-to-action.  
**null:** If this is auto-triggered or no special condition applies.

### notes
**Type:** String (multi-line)  
**Purpose:** Implementation notes, flags, continuity pointers, or historical context.  
**Example:** "Front-loaded Tier 1 physiological sensation. No flinch scene — Guide Bird introduces himself and goes straight to the spell transition."

---

## Enums (Reference)

### Domain Enum
```
breathing
watching
kindness
bodysensing
courage
selfgrounding
```

### Creature Enum
```
tessa
luna
benson
ember
bork
bramble
```

### Event Type Enum
```
full_call
transitional_call
evolution
```

### Stone Color Enum
```
orange   (Body Stone)
yellow   (Watching Stone)
red      (Heart Stone)
blue     (Calm Stone)
green    (Courage Stone)
purple   (Grounding Stone)
null     (no stone for this module)
```

---

## M-Number Convention (FIXED)

This is critical for maintaining continuity across arcs:

| M-Number | Creature | Domain (Arc 1) | Never Changes |
|----------|----------|---|---|
| M1 | Tessa (Turtle) | Body-Sensing → Breathing (comet) | M1 is ALWAYS Tessa, in every arc |
| M2 | Luna (Owl) | Now-Watching | M2 is ALWAYS Luna, in every arc |
| M3 | Benson (Bunny) | Courage | M3 is ALWAYS Benson, in every arc |
| M4 | Ember (Fox) | Kindness | M4 is ALWAYS Ember, in every arc |
| M5 | Bork (Firefly) | Self-Grounding | M5 is ALWAYS Bork, in every arc |
| M6 | Bramble (Bear) | Calm-Breathing → Body-Sensing (comet) | M6 is ALWAYS Bramble, in every arc |

**Play order CAN differ across arcs.** For example:
- **Arc 1:** M1 → M2 → M4 → M6 → M3 → M5 (barPosition 1-6)
- **Arc 2:** M7 → M8 → M9 → M10 → M11 → M12 (barPosition 1-6, but M-numbers are M7=Luna, M8=Bramble, etc.)

---

## Data Quality Flags

### Arc 1: COMPLETE ✅

All 6 modules (M1–M6) extracted from **ARC_1_SKELETON_DRAFT.md v2.0 (March 21, 2026)**.

- Comet revision applied (4 technique reassignments for front-loaded physiological sensation)
- All fields populated
- Ready for Haiku API integration

### Arc 2: PARTIAL ⚠️

**Modules completed:**
- M7 (Luna, watching_big_little) — COMPLETE
- M8 (Bramble, bodysensing_dragon_stomp) — COMPLETE

**Modules incomplete (missing technique specs):**
- M9 (Ember, kindness module) — Narrative setup provided. Technique specs missing.
- M10 (Bork, selfgrounding module) — Identified by position/creature. No narrative setup.
- M11 (Luna, watching evolution) — Identified as evolution. Technique specs missing.
- M12 (Benson, courage module) — Identified by position/creature. No narrative setup.

**Reason:** ARC_2_SKELETON_v10.md (v10, March 17 2026) provided narrative setup for M9 and creature/domain for M10-M12 but stopped before providing clinical technique specifications.

**Next Step:** Complete Arc 2 by:
1. Reading **ARC_2_SKELETON_v10.docx** (the working .docx may be more current than the .md)
2. OR sourcing from a later Arc 2 skeleton revision (v11+)
3. OR extracting from **NARRATIVE_DECISIONS_UNIFIED_v2_8.md** or **ARC_PRODUCTION_BIBLE_v2_10.md** if Arc 2 technique assignments are documented there

### Arcs 3–9: NOT YET IMPLEMENTED ⏳

- Structure is ready for extension
- Skeletons exist but were not read in this build pass
- Will be added arc-by-arc as each skeleton is finalized and locked
- Expected: 42 modules total (M13–M54)

---

## How to Update This Registry

### Adding a new arc:

1. **Read the skeleton** for the new arc (e.g., `ARC_3_SKELETON_*_v*.md`)
2. **Extract module data** for each event:
   - Module M-number and creature
   - Spell name and clinical technique name
   - Domain and stone color (if applicable)
   - Narrative setup and bridge dialogue condition
   - Classification (New Spell / Evolution / other)
3. **Create the arc object** following the structure:
   ```json
   "arc_N_name": {
     "arcNumber": N,
     "arcName": "...",
     "arcPremise": "...",
     "modulesInArc": 6,
     "playOrder": [ ... ],
     "modules": { ... }
   }
   ```
4. **Update `_meta.coverage`** to reflect new arc count
5. **Move placeholder_arcs_X_Y** down as needed
6. **Increment version number** (v1 → v1_1, etc.)
7. **Update `data_quality_flags.arcs_X_Y`** section

### Fixing incomplete modules:

1. **Source the missing data** (technique specs, clinical details, narrative setup)
2. **Update the module context object** with all fields
3. **Remove any "[NEEDS COMPLETION]" flags**
4. **Update the arc status** in `data_quality_flags` from PARTIAL to COMPLETE
5. **Increment version number**

---

## API Integration Notes

### Request Format (Example)

The runtime system will query this registry like:

```javascript
const moduleContext = registry.arc_1_the_gathering.modules.bodysensing_magic_hands;
```

### System Prompt Injection

The Haiku API receives the injected context in the Guide Bird system prompt:

```
[System Prompt Template]

Module Context:
- Spell Name: {moduleContext.moduleSpellName}
- Domain: {moduleContext.domainLabel}
- Creature: {moduleContext.creatureCommonName}
- Challenge: {moduleContext.bridgeDialogueCondition}
- Type: {moduleContext.eventType}

[Rest of System Prompt]
```

### Runtime Behavior

1. Child taps a creature on the map → triggers a module
2. System identifies `moduleId` (e.g., `bodysensing_magic_hands`)
3. System queries `MODULE_CONTEXT_REGISTRY_v1.json` for the module object
4. System injects module context into the Guide Bird system prompt
5. Haiku API generates Guide Bird's call-to-action dialogue
6. Child hears the Guide Bird speak the spell name and invitation
7. Module begins (Phase A demonstration)

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| **v1.0** | April 11, 2026 | Initial registry build. Arc 1 complete (M1-M6). Arc 2 partial (M7-M8 complete, M9-M12 flagged as incomplete). Arcs 3-9 placeholder. |

---

## Questions / Blockers

**For Kim:** If you have feedback on the schema, need to rename fields, or want to adjust what gets injected into the Guide Bird prompt, let me know and I'll update the registry and system prompt template accordingly.

**For Claude Code:** When extending to Arcs 3-9, follow the same structure and field definitions. If you encounter a module that doesn't fit the schema (e.g., a narrative-only milestone without a technique), update the schema and document it in this README.

---

## Related Documents

- **ARC_PRODUCTION_BIBLE_v2_10.md** — Production standards for all arc skeletons
- **UNIFIED_TECHNIQUE_INVENTORY_v1_15.md** — Complete technique specs (clinical details, sources, mechanism)
- **CANONICAL_DATA_MODEL_v1_12.md** — Firestore schema (rune states, domain enums, module fields)
- **CLAUDE_Everdale_World_Design_Bible_v13_11.md** — World design and character details
- **CLAUDE_Guide_Bird_AI_System_Prompt_v1_4.md** — Guide Bird system prompt template (consumer of this registry)
- **TTS_PERSONALIZATION_PIPELINE_v1.md** — Voice rendering and personalization (uses module context for dialogue)

---

**Built by:** Claude Code  
**For:** MindfulNest Production  
**Status:** Ready for Haiku API integration  
