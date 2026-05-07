# MODULE LIFECYCLE: FROM NARRATIVE EVENT TO MAP RETURN
## How Arc Skeletons Map to Technical Implementation

### Version: 1.1 — March 9, 2026
### Purpose: Bridge document connecting narrative skeleton format to Firestore fields, module player steps, and production pipeline
### Audience: Claude Code, developers, and content authors who need to understand the full event-to-module-to-map-return cycle
### Status: DRAFT — Aligned with the Bible

---

## WHY THIS DOCUMENT EXISTS

The information in this document is already present across the Bible, Canonical Data Model, Module JSON Schema Guardrails, and the Module Authoring Guide. However, no single document traces the **complete lifecycle** of one narrative event from trigger to map return. This creates a risk that developers building the narrative engine or module player might misunderstand how arc skeleton content maps to the technical system — particularly the relationship between the skeleton's "Resolution" paragraphs and the module player's Rescue step.

This document is a Rosetta Stone. It translates between two languages: the narrative language of arc skeletons (Events, Video Intros, Resolutions) and the technical language of the implementation (Firestore collections, module JSON fields, AI narrative cache).

---

## THE COMPLETE LIFECYCLE: ONE EVENT, ONE MODULE, START TO FINISH

### Phase 1: Narrative Event Triggers

The narrative engine reads the child's `nextEventIndex` from the `children` document and looks up the corresponding `narrativeEvent` document for the current arc.

**Firestore path:** `narrativeEvents/{eventId}`

**Key fields consumed:**
- `triggerCondition` — determines WHEN this event fires (e.g., `modulesCompleted >= 3`)
- `videoAssetRef` — path to pre-produced video file (if this event has one)
- `createsBar` — whether this event spawns a measuring bar with modules
- `circleModuleIds` — which module(s) this event uses

**Skeleton equivalent:** The Event header and trigger line.
```
Example from Arc 2 skeleton:
  EVENT 2: BRAMBLE'S PROPOSAL — FIGHT (M8)
  Trigger: After M7 (child returns to map, walks pathway)
```

---

### Phase 2: Video Intro Plays

If `videoAssetRef` is not null, the app plays the pre-produced video. This is the **Video Intro** section from the arc skeleton — the creature's situation, the problem that surfaces, the emotional context.

**Technical:** Standard HTML5 video playback. Video file is a bundled asset produced offline (fal.ai / Midjourney frames + ElevenLabs narration + AI video tools). No runtime generation.

**Skeleton equivalent:** Everything under `### Video Intro` in the event.
```
Example from Arc 2 skeleton:
  ### Video Intro
  Bramble's response to the threat is the opposite of Tessa's.
  He doesn't want to hide. He wants to FIGHT...
```

**CRITICAL UNDERSTANDING:** The Video Intro IS the situation setup. It is NOT a separate system from the module — it is the narrative preamble that leads directly into the module player launching. When the video ends, the module player takes over at Step 1 (Call).

---

### Phase 3: Module Player Runs (Steps 1–5)

When the video ends (or immediately if no video), the module player loads the module and the bar's narrative cache. The module player combines two data sources:

| Source | What It Provides | Narrative-Specific? |
|---|---|---|
| **Module JSON** (`modules/{moduleId}`) | Therapeutic core: Phase A pattern, Phase A config, instruction cues, Phase B audio, technique card, visual effects, adult-facing fields | **NO — reusable across any narrative context** |
| **Bar's AI Narrative Cache** (`children/{childId}/bars/{barId}.aiNarrativeCache`) | Story wrapper: Call dialogue, Buy-In dialogue, Rescue transition line, Win celebration, tomorrow hook | **YES — generated fresh per bar from narrative context** |

This is the fundamental architectural principle: **Modules are context-free reusable content units.** The same grounding breathing module can appear in Arc 1 (Bramble excited, joy-grounding) and Arc 2 (Bramble angry, anger-grounding) with completely different narrative wrappers. The therapeutic content (how to do grounding breathing) is identical. The story context (why we're doing it now) changes.

#### Step 1: The Call
- **Content source:** `aiNarrativeCache.callDialogue[circleIndex]` (AI-generated)
- **Display:** Guide Bird dialogue + creature sprite (distressed state) + "Help [creature]" button
- **Skeleton equivalent:** The `### Therapeutic Note` section is a creative brief for the AI. It tells Haiku what emotional context to convey. Example: "This is the 'fight' response — anger dressed in armor."

#### Step 2: The Buy-In
- **Content source:** `aiNarrativeCache.buyInDialogue[circleIndex]` (AI-generated)
- **Display:** Guide Bird sprite + gradient background + ElevenLabs TTS audio
- **Skeleton equivalent:** The therapeutic note's connection to real-world child experience. Example: "Every kid knows the feeling of someone taking their stuff."

#### Step 3A: Training Phase A (Interactive Demo)
- **Content source:** Module JSON — `phaseAPattern`, `phaseAConfig`, `instructionCues[]`
- **Display:** Left zone (Guide Bird, 1/3 width) + Right zone (interactive demo, 2/3 width)
- **Skeleton equivalent:** Not in the skeleton. Phase A is defined in the module JSON, designed per the Module Authoring Guide, and validated by the seed module demos. The skeleton only needs to establish WHICH technique is being taught (e.g., "anger-grounding — same technique as Arc 1, different emotional register").

#### Step 3B: Training Phase B (Guided Meditation)
- **Content source:** Module JSON — `guidedAudioRef`, `phaseBVisualRef`, `phaseBTransitionCue`
- **Display:** Gentle visual guide (breathing circle, body outline) + meditation audio
- **Skeleton equivalent:** Not in the skeleton. Phase B scripts are authored separately per the Phase B Research Dossier Process and Phase B Production Process.

#### Step 4: The Rescue
- **Content source:** BOTH module JSON and AI cache
  - Module JSON: `rescueCreatureVisual` (creature's settling sprite state), `rescueVisualEffect` (domain-specific visual — e.g., `"roots_settling"` for Grounding), `rescueDurationSeconds`
  - AI cache: `aiNarrativeCache.rescueTransition[circleIndex]` (Guide Bird's narrative-specific transition line)
- **Display:** Continuous flow from Phase B. Guide Bird voice fades in over the meditation ending. Creature visually responds — settling, glowing, transforming. Child sustains the state they just reached.
- **Skeleton equivalent:** THE RESOLUTION PARAGRAPH.

**THIS IS THE KEY MAPPING.** When an arc skeleton says:
```
### Resolution
Bramble's anger doesn't vanish — it redirects. He's still fierce.
But grounded fierce, not out-of-control fierce. The energy that was
going to swing fists is now going to protect his friends.
```

This maps to THREE technical elements:
1. `rescueCreatureVisual` — Bramble's sprite transitions from bristling/stomping to steady/grounded
2. `rescueVisualEffect` — `"roots_settling"` (Grounding domain default) — visual roots/earth energy stabilizing
3. `rescueTransition` — AI-generated line conveying the narrative resolution. e.g., "Stay right there... feel that? Your Grounding magic is reaching Bramble... look — he's still strong, but steady now. YOUR magic did that."

**The skeleton's Resolution paragraph is a creative brief, not a video script.** It tells the AI narrative generator and the art/animation team what the emotional payoff should look and feel like. It does NOT require a separate post-module video scene.

#### Step 5: The Win
- **Content source:** BOTH module JSON and AI cache
  - Module JSON: `coinReward`, `decorationReward`, `creatureId`, `domain`
  - AI cache: `aiNarrativeCache.winCelebration[circleIndex]`, `aiNarrativeCache.tomorrowHook[circleIndex]`
- **Display:** Creature settled state → coin animation (coins-clanking sound) → rune pulse → Spell Card appears with lazy magic trail animation leading to Spell Book icon → decoration unlock (if applicable) → Guide Bird celebration → tomorrow hook → return to map
- **Note:** The measuring bar is a backend-only progress tracker. It is NOT displayed as a child-facing UI element. Progress is communicated through creature sprite states and narrative dialogue.
- **Skeleton equivalent:** Not typically in the skeleton (standard win flow). The skeleton may note specific decoration rewards or narrative-significant win beats if they differ from the standard pattern.

---

### Phase 4: Return to Map

After the Win step, the child returns to the Everdale map (or current world map). The narrative engine:

1. Updates `nextEventIndex` on the child document
2. Updates creature state (sprite may change from distressed to idle/happy)
3. Updates rune glow level if applicable
4. Sets `pendingNarrativeHook` for next-session return (Cloud Function, async)

**Skeleton equivalent:** The `### Post-M[N]: Return to Map` section.
```
Example from Arc 2 skeleton:
  ### Post-M8: Return to Map
  Standard return. Child can explore, decorate, spend earnings.
  Walking down pathway triggers Event 3.
```

The child is now in free-roam. They can explore, decorate, visit homes, play creature games, shop at the Mountain Store, talk to Pip, or continue the story by walking down the pathway (which triggers the next event's `triggerCondition` check).

---

## HOW ARC SKELETON SECTIONS MAP TO TECHNICAL FIELDS

| Skeleton Section | Maps To | Who Creates It |
|---|---|---|
| **Event header** (creature, domain, type, trigger) | `narrativeEvents` document fields | Content author (skeleton) |
| **Video Intro** | `videoAssetRef` on the narrative event → pre-produced video file | Video production pipeline (fal.ai + ElevenLabs) |
| **Therapeutic Note** | `narrativeContextHint` on module JSON + creative brief for AI prompt | Content author (skeleton → module JSON) |
| **Resolution** | `rescueCreatureVisual` + `rescueVisualEffect` (module JSON) + `rescueTransition` (AI cache) | Module JSON author (visual spec) + Haiku (narrative line) |
| **Post-Module: Return to Map** | `nextEventIndex` increment + creature state update + standard map return | Narrative engine (automated) |
| **Map triggers** ("walking down pathway triggers Event N") | `triggerCondition` on next narrative event | Content author (skeleton → narrative event doc) |

---

## WHAT THE SKELETON DOES AND DOES NOT SPECIFY

### The skeleton specifies:
- The narrative EVENT sequence (what happens in what order)
- Video Intro content (what the child SEES before the module starts)
- Which creature, domain, and technique each module uses
- The emotional context and therapeutic rationale (creative brief for AI + clinical validation)
- The Resolution (creative brief for Rescue visual + AI transition line)
- Map state changes between events (what the world looks like, what's available)
- Milestone scenes (non-module narrative beats like the King's Arrival video)

### The skeleton does NOT specify:
- Phase A interactive demo design (defined in module JSON per the Authoring Guide)
- Phase B meditation script content (defined per the Phase B Research Dossier Process)
- Exact Call/Buy-In/Win dialogue (AI-generated from narrative context)
- Instruction cues (human-authored in module JSON, not skeleton)
- Technical field values (the skeleton is a narrative document, not a database schema)

---

## STANDALONE MODULES vs. MEASURING BAR MODULES

Arc 2 uses **standalone modules** (one module per event, no measuring bar). The lifecycle is the same as above, but with these differences:

| Aspect | Standalone Module | Measuring Bar Module |
|---|---|---|
| `createsBar` | `true` (bar with 1 circle) | `true` (bar with 2–5 circles) |
| `circleCount` | `1` | `2–5` |
| Bar tracking (backend only) | Circle fills immediately on completion | Circles fill one at a time across multiple modules |
| `resolutionDescription` | Fires after the single module | Fires after the LAST circle fills |
| AI cache | One set of dialogue (Call, Buy-In, Rescue, Win) | One set PER circle in the bar |

**Note:** The measuring bar is a backend data structure only. It is NOT rendered as a child-facing UI element. Progress is communicated to the child through creature sprite states and narrative dialogue, not through visual bar/circle UI.

For Arc 2's standalone modules, each event creates a bar with exactly one circle and one module. The bar completes as soon as the module completes. This is functionally equivalent to "no bar" from the child's perspective but maintains architectural consistency.

---

## MILESTONE SCENES (NON-MODULE NARRATIVE BEATS)

Some skeleton sections are pure narrative — no module attached. Examples: the King's Arrival video, Willow's Revelation, the Mission Briefing. These are:

- `narrativeEvent` documents with `createsBar: false`
- `videoAssetRef` points to the pre-produced video
- `type: "milestone"` or `"village"`
- No `circleModuleIds` (no modules to run)

After the video plays, the child returns to the map and the narrative engine advances `nextEventIndex`.

---

## THERAPIST TECHNIQUE PREFERENCES

Therapists influence module selection through technique-level preferences, not domain-level toggles. The therapist sets a `preferredTechniques` string array on the child document (e.g., `["belly_breathing", "grounding_breath"]`). When the narrative engine selects modules for a new bar, preferred techniques receive priority in circle assignment.

This is a technique-level system, not a domain-level system. The therapist picks specific techniques, not broad domains. The Spell Book UI shows preferred techniques with a gold shimmer badge and a note like "Dr. Brown chose this for you."

**Firestore field:** `children/{childId}.preferredTechniques` — string array
**UI:** Therapist Child Detail screen shows technique list with toggle/selection
**Runtime effect:** At bar creation, if preferred techniques exist, inject one matching module into the bar (same injection rules as before — second-to-last position, only if bar has ≤3 base circles)

---

## DOCUMENT REFERENCES

| Document | What It Contributes |
|---|---|
| **The Bible** — Module Template section | The 5-step flow definition, content architecture (human vs. AI), rescue sustain principle |
| **Canonical Data Model** — `narrativeEvents`, `modules`, `bars` collections | All Firestore field definitions, AI narrative cache structure, write patterns |
| **Module JSON Schema Guardrails** — Guardrails 7, 8, 10 | Instruction cues structure, modules as context-free units, complete field audit per step |
| **Module Authoring Guide** — §2–§7 | Call/Buy-In/Phase A/Phase B/Rescue/Win authoring rules |
| **Arc Skeleton documents** (Arc 1 v3, Arc 2 reconstructed) | Narrative event sequence, video intro content, resolution briefs |
| **Visual Production Guide v4.2** — §7.1 | Module player engine build spec and input documents |

---

*This document is a reference bridge. When it conflicts with any source document, the source document wins. Document hierarchy: The Bible > Canonical Data Model > Guardrails > Authoring Guide > This document.*
