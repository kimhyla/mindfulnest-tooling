# MindfulNest Universal Asset Registry Workflow

**Version:** 1.0  
**Date:** April 13, 2026  
**Purpose:** Unified workflow for tracking, creating, reviewing, approving, and using ALL asset types (visual, audio, video, storyboards, croppers, data) across the 5-stage production pipeline.

---

## Problem Statement

The MindfulNest production pipeline creates dozens of asset types across 5 stages (intake → phase_b → phase_a_json → audio → listen_through). Until now, these assets lived in folders with ambiguous names, and Claude had to guess which file was the "right one."

**Real-world consequences:**
1. Wrong image loaded into cropper tool (loaded 16:9 pre-crop instead of 960x960 original)
2. Wrong image embedded in storyboard (neutral Tessa instead of sad Tessa)
3. Hours wasted on file-finding when Kim should have been reviewing
4. No way to query "what audio assets do I have for M1?" or "which stills are approved?"

This workflow solves this by establishing:
- **A single asset registry** (Directus) as the source of truth
- **Immediate registration** of every asset when created
- **Status tracking** from creation → review → approval → usage
- **Query-first pattern** for tools (storyboard builder, audio mixer, etc.)
- **File path mapping** from dashboard to Mac Finder for Kim review

---

## Asset Types in the MindfulNest Pipeline

| Asset Type | Created By | Stage | File Format | Quantity Per Module |
|----------|-----------|-------|-------------|-------------------|
| **Visual Stills** | video-producer skill or manual | phase_a_json, audio | .png, .jpg (FLUX output) | 8–12 per event |
| **Cropped Images (4:3)** | build_cropper.py or manual | audio | .png, .jpg | 3–5 per cropper HTML |
| **Composed Composites** | video-producer (layering) | audio | .png, .jpg | 1–2 per event |
| **Animated Clips** | video-producer (Seedance/Kling) | audio | .mp4 | 8–12 per event |
| **Lip-Synced Video** | video-producer (ByteDance) | audio | .mp4 | 4–8 per event |
| **Assembled Event Video** | video-producer (ffmpeg) | audio, listen_through | .mp4 | 1–3 per event |
| **TTS Voice Stems** | audio-producer (ElevenLabs) | audio | .mp3 | 1–6 per module (iterations) |
| **Ambient Beds** | audio-producer (sourced) | audio | .mp3 | 1 per module |
| **SFX (bell, shimmer, etc.)** | audio-producer (sourced) | audio | .mp3 | 2–4 per module |
| **Final Audio Mix** | audio-producer (ffmpeg) | audio, listen_through | .mp3 | 1 per module |
| **Cue Point Maps** | audio-producer (Vosk STT) | audio | .json | 1 per module |
| **Phase B Scripts** | phase-b-writer skill | phase_b | .md (working) → .docx (locked) | 1 per module |
| **Phase A JSON Configs** | phase-a-designer skill | phase_a_json | .json | 1 per module |
| **Module JSON (Full)** | module-json-builder skill | audio | .json | 1 per module |
| **Storyboard HTMLs** | build_storyboard.py | audio | .html | 1–2 per event |
| **Cropper HTMLs** | build_cropper.py | audio | .html | 1–3 per event |
| **Wand Overlays** | video-producer or design tool | audio, listen_through | .png, .mp4 | 1–3 per event |
| **Avatar Variants** | video-producer or design tool | audio, listen_through | .png | 1–2 per child path |
| **Zone/Background Assets** | video-producer or design tool | phase_a_json, audio | .png | 3–6 per zone |
| **Story Recap Assets** | video-producer or narrative-generator | audio, listen_through | .png, .mp4, .html | 1–2 per recap trigger |
| **BreathCycle Rhythm JSON** | audio-producer (computed) | audio | .json | 1 per module |
| **Personalization Maps** | narrative-generator or phase-a-designer | intake, phase_a_json | .json | 1 per module |
| **Technique Instruction Data** | phase-a-designer | phase_a_json | .json | 1 per module |
| **Voice Profiles** | dashboard-gate or admin | all stages | .json (Directus records) | 1 per creature, Guide Bird |
| **Event Metadata** | narrative-generator or skeleton tool | phase_b, phase_a_json | .json | 1 per event |
| **Dialogue Transcripts (Locked)** | arc-builder or skeleton extraction | phase_b, audio | .md, .json | 1 per event |

---

## The Asset Registry: Directus Collections

The dashboard has **THREE primary asset collections**:

### 1. `prod_assets` (Universal Asset Metadata)

**Purpose:** Single source of truth for ALL asset files. Every asset created in production gets registered here, regardless of type.

**Schema:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | UUID | Yes | Directus auto-ID |
| `module_id` | FK → prod_modules | Yes | Which module this asset belongs to |
| `event_number` | integer | Yes | Event [N] for cross-event queries |
| `asset_type` | enum | Yes | Allowed: `visual_still`, `visual_crop`, `visual_composite`, `video_clip`, `video_lipsync`, `video_assembled`, `audio_stem`, `audio_bed`, `audio_sfx`, `audio_mix`, `audio_cuepoint`, `script_phase_b`, `script_phase_a`, `html_storyboard`, `html_cropper`, `gameplay_overlay`, `gameplay_avatar`, `gameplay_zone`, `data_module_json`, `data_phase_a_json`, `data_breathcycle`, `data_personalization_map`, `data_technique_data`, `voice_profile`, `narrative_metadata`, `dialogue_transcript`, `other` |
| `asset_name` | text | Yes | Human-readable: "Tessa Opening Still — Sad", "Luna Ambient Bed", "M1 Voice Stem v3" |
| `file_path` | text | Yes | Relative path in Dropbox: `Production/Event_1/m1_tessa_opening_still.png` (NOT full Mac path) |
| `file_size_bytes` | integer | No | File size for audit purposes |
| `file_hash` | text | No | SHA-256 hash to verify file integrity |
| `created_at` | timestamp | Yes | Directus auto (when registered) |
| `created_by` | text | Yes | "claude" or "kim" |
| `status` | enum | Yes | Allowed: `pending`, `in_review`, `approved`, `rejected`, `superseded`, `archived` |
| `kim_verdict` | enum | No | Allowed: `approved`, `rejected`, `revise_and_resubmit`, `pending` (only populated when Kim has reviewed) |
| `kim_feedback` | text | No | Kim's review notes: "Too dark", "Perfect", "Needs lighter background" |
| `source_asset_id` | FK → prod_assets | No | If this asset was derived from another (e.g., crop from master still), point to parent |
| `metadata` | JSON | No | Type-specific metadata: `{visual: {dimensions: "960x960", dpi: 72}, audio: {duration_seconds: 120, voice_id: "oR4uRy4fHDUGGISL0Rev"}}` |
| `tags` | text array | No | For filtering: `["master", "reference", "approved", "ready_for_storyboard"]` |
| `notes` | text | No | Production context: "Voice stem v3 — faster pacing", "Tessa sad expression for resolution" |
| `session_id` | text | No | Which production session created it (for audit) |

**Indexes:**
- `(module_id, asset_type)` — Query "all visual stills for M1"
- `(event_number, asset_type, status)` — Query "all approved stills for Event 3"
- `(status, created_at)` — Find pending assets for review
- `(source_asset_id)` — Track lineage

---

## The Request → Create → Register → Review → Approve Cycle

This is the standard workflow. Every asset follows this path, regardless of type.

### Phase 1: Request (Claude ← Kim)

**Trigger:** Kim says "produce audio for M1" or Claude recognizes a production need.

**Claude's action:**
1. Query `prod_assets WHERE module_id={id} AND asset_type='audio_stem'` to check if a voice stem already exists
2. If one exists and status is `approved`, reuse it
3. If multiple exist with status in (`pending`, `in_review`), ask Kim which to use or whether to create a new one
4. If none exist or all are `rejected`, proceed to Create

**Example query:**

```bash
# Check for existing voice stems for M1
curl -s "$BASE/items/prod_assets?filter[module_id][_eq]=1&filter[asset_type][_eq]=audio_stem&sort=-created_at" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {id, asset_name, status, kim_verdict}'
```

---

### Phase 2: Create (Claude ✍️)

**Trigger:** Asset doesn't exist or needs to be regenerated.

**Claude's action:**
1. Generate the asset (TTS, FLUX Kontext, ffmpeg mix, etc.)
2. Save to disk at `$DROPBOX_PATH/Production/Event_{N}/[filename]`
3. Verify file was written successfully (check file size, run hash)
4. **Immediately register** in `prod_assets` with status `pending`

**Do NOT wait to register until review.** Registration happens the moment the file hits disk.

**Example: Creating a voice stem**

```bash
# Step 1: Generate via ElevenLabs
curl -X POST "https://api.elevenlabs.io/v1/text-to-speech/oR4uRy4fHDUGGISL0Rev" \
  -H "xi-api-key: $ELEVENLABS_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "<script text>", "model_id": "eleven_multilingual_v2", ...}' \
  --output "$LOCAL_PATH/m1_voice_stem_v3.mp3"

# Step 2: Verify file exists
if [ ! -f "$LOCAL_PATH/m1_voice_stem_v3.mp3" ]; then
  echo "ERROR: File not written"; exit 1
fi

# Step 3: Register in dashboard IMMEDIATELY
FILE_PATH="Production/Event_1/m1_voice_stem_v3.mp3"
FILE_SIZE=$(stat -c%s "$LOCAL_PATH/m1_voice_stem_v3.mp3")
FILE_HASH=$(sha256sum "$LOCAL_PATH/m1_voice_stem_v3.mp3" | cut -d' ' -f1)

curl -s -X POST "$BASE/items/prod_assets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "module_id": 1,
    "event_number": 1,
    "asset_type": "audio_stem",
    "asset_name": "M1 Voice Stem v3 (Faster pacing)",
    "file_path": "'$FILE_PATH'",
    "file_size_bytes": '$FILE_SIZE',
    "file_hash": "'$FILE_HASH'",
    "created_by": "claude",
    "status": "pending",
    "metadata": {"audio": {"duration_seconds": 145, "voice_id": "oR4uRy4fHDUGGISL0Rev", "stability": 0.5}},
    "notes": "Voice stem v3 with adjusted pacing — faster count-breathing rhythm"
  }'
```

**The registration returns an `id`.** Keep this for the next phase.

---

### Phase 3: Review (Kim 👁️)

**Trigger:** Claude has registered the asset and asks Kim to review.

**Claude's action:**
1. Query the asset record to get `file_path`
2. Construct full Mac path: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/{file_path}`
3. Use computer-use MCP to open file in appropriate app via Finder:
   - `.mp3`: QuickTime Player
   - `.png`, `.jpg`: Preview
   - `.mp4`: QuickTime Player
   - `.html`: Chrome browser
   - `.md`, `.docx`: Preview or Word
4. Tell Kim the asset is ready for review (never tell her a file path — she sees it open on screen)

**Example: Opening audio for Kim review**

```bash
# Never do this: "Audio is at Production/Event_1/m1_voice_stem_v3.mp3"
# Instead, open it programmatically using computer-use MCP

MAC_PATH="/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/Event_1/m1_voice_stem_v3.mp3"

# Use computer-use to open via Finder
# (calls mcp__computer-use__open_application and file navigation)
```

**Kim reviews and provides verdict.** Examples:
- "Approved" / "Looks good" → status → `approved`
- "Rejected — too dark" / "Not right" → status → `rejected`, kim_feedback → "Too dark, needs lighter background"
- "Close, but adjust X" → status → `in_review`, kim_feedback → "Adjust X and resubmit"

---

### Phase 4: Approve (Claude ✍️ + Directus)

**Trigger:** Kim has given her verdict.

**Claude's action:**
1. Update `prod_assets` record:
   - Set `status` to match verdict (`approved`, `rejected`, `in_review`)
   - Set `kim_verdict` enum field
   - Set `kim_feedback` with her notes
   - Update `kim_verdict` timestamp

**Example:**

```bash
# Kim said "Approved"
curl -s -X PATCH "$BASE/items/prod_assets/{ASSET_ID}" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "approved",
    "kim_verdict": "approved",
    "kim_feedback": null,
    "updated_at": "2026-04-13T14:30:00Z"
  }'

# OR Kim said "Rejected — too dark"
curl -s -X PATCH "$BASE/items/prod_assets/{ASSET_ID}" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "rejected",
    "kim_verdict": "rejected",
    "kim_feedback": "Too dark, needs lighter background"
  }'
```

**If rejected:** Delete/move file (or keep with `status = 'archived'` for audit trail). Create a new one and repeat the cycle.

**If approved:** Asset is ready for use downstream. Tag it appropriately if needed.

---

### Phase 5: Use (Claude + Downstream Tools)

**Trigger:** Another tool (storyboard builder, audio mixer) needs the asset.

**Claude's action:**
1. Query `prod_assets` for approved assets of the required type:

```bash
# Get all approved visual stills for Event 1
curl -s "$BASE/items/prod_assets?filter[event_number][_eq]=1&filter[asset_type][_eq]=visual_still&filter[status][_eq]=approved" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {id, asset_name, file_path}'
```

2. Extract `file_path` values
3. Construct Mac paths and pass to the tool
4. **Never use a file that isn't registered AND approved**

---

## Storyboard/Cropper Integration

### Storyboard Builder Query Pattern

**Storyboard HTMLs** are built by `build_storyboard.py`. Before building, query the dashboard for approved assets.

**Query:**

```bash
# Get all approved stills for Event 3
EVENT=3
curl -s "$BASE/items/prod_assets?filter[event_number][_eq]=$EVENT&filter[asset_type][_eq]=visual_still&filter[status][_eq]=approved&sort=created_at" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {asset_name, file_path, metadata}'
```

**Pass to `build_storyboard.py`:**

```python
# build_storyboard.py receives:
stills = [
  {"asset_name": "Tessa Opening Still", "file_path": "Production/Event_1/m1_tessa_opening_still.png"},
  {"asset_name": "Tessa Walking", "file_path": "Production/Event_1/m1_tessa_walking.png"},
  ...
]
audio_files = [
  {"asset_name": "M1 Phase B Final Mix", "file_path": "Production/Event_1/m1_phase_b_complete_mix.mp3"}
]

# Tool constructs Mac paths internally:
mac_path = f"/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/{file_path}"
```

### Cropper Builder Query Pattern

**Cropper HTMLs** are built by `build_cropper.py`. It needs the REFERENCE MASTER still (the original 960x960 image before cropping).

**Asset lineage:** When a crop is saved (e.g., 4:3 crop of Tessa sad), the `prod_assets` record for the crop has `source_asset_id` pointing to the master.

**Query for cropper input:**

```bash
# Get the reference master for Tessa sad expression
curl -s "$BASE/items/prod_assets?filter[asset_name][_contains]=Tessa&filter[asset_name][_contains]=sad&filter[tags][_contains]=master&filter[status][_eq]=approved" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[0] | {id, asset_name, file_path}'
```

**Pass to `build_cropper.py`:**

```python
reference_still = {
  "id": "uuid-123",
  "asset_name": "Tessa Sad Expression (Master 960x960)",
  "file_path": "Production/Event_1/m1_tessa_sad_master.png"
}

# build_cropper.py opens the reference and creates crops
# Each crop is saved locally, then registered as a new asset:
{
  "asset_type": "visual_crop",
  "asset_name": "Tessa Sad — 4:3 Crop for Storyboard",
  "source_asset_id": "uuid-123",  # Links back to master
  "file_path": "Production/Event_1/crops/m1_tessa_sad_4x3.png",
  "tags": ["crop", "4:3", "ready_for_storyboard"]
}
```

---

## File Opening Protocol

### The Rule

**Claude NEVER tells Kim a file path. Instead:**
1. Query the asset registry to get `file_path`
2. Use computer-use MCP to navigate Finder and open the file
3. Kim sees the file open on her screen, not a path

### Implementation

**Step 1: Query asset**

```bash
curl -s "$BASE/items/prod_assets/{ASSET_ID}" \
  -H "Authorization: Bearer $TOKEN" | jq '.data | {asset_name, file_path}'
# Returns: {"asset_name": "M1 Voice Stem v3", "file_path": "Production/Event_1/m1_voice_stem_v3.mp3"}
```

**Step 2: Construct Mac path**

```bash
DROPBOX_PROJECT="/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
FILE_PATH="Production/Event_1/m1_voice_stem_v3.mp3"
FULL_PATH="$DROPBOX_PROJECT/$FILE_PATH"
```

**Step 3: Open via Finder (computer-use MCP)**

```python
# Pseudo-code — actual implementation uses mcp__computer-use__*
request_access(apps=["Finder", "QuickTime Player"])
open_application("Finder")
navigate_to_path(FULL_PATH)
open_with_default_app(FULL_PATH)
# Result: File opens in appropriate app (QuickTime for MP3, Preview for images, etc.)
```

**Step 4: Tell Kim (natural language only)**

Do NOT repeat the path. Say:

> "I've opened your voice stem. This is v3 with faster pacing. Please let me know if the breathing rhythm works better."

Kim never sees: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/...`

---

## Error Prevention Rules

### Rule 1: Query Before Using

**ALWAYS query the asset registry before using a file.**

```python
# WRONG (guessing filenames):
image = "Production/Event_1/m1_tessa_sad.png"  # Hope this exists?

# RIGHT (querying dashboard):
image_record = query_dashboard(
  "prod_assets",
  filters={
    "module_id": 1,
    "asset_type": "visual_still",
    "status": "approved",
    "tags": "contains:sad"
  }
)
image = image_record["file_path"]  # Guaranteed correct
```

### Rule 2: Check Status Before Using

**Never use a file with status `rejected`, `superseded`, or `pending`.**

```bash
# Query only approved assets
curl -s "$BASE/items/prod_assets?filter[module_id][_eq]=1&filter[status][_eq]=approved&filter[asset_type][_eq]=audio_stem" \
  -H "Authorization: Bearer $TOKEN"
```

If a required asset is missing or not approved:

```bash
echo "ERROR: No approved voice stem for M1"
echo "Available assets:"
curl -s "$BASE/items/prod_assets?filter[module_id][_eq]=1&filter[asset_type][_eq]=audio_stem" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {asset_name, status}'
echo ""
echo "ACTION: Stop and ask Kim. Do NOT guess filenames or use rejected assets."
exit 1
```

### Rule 3: Register Immediately, Never Later

**Every file created MUST be registered in `prod_assets` before returning from the creation step.** This is non-negotiable.

| Situation | Action |
|-----------|--------|
| Voice stem generated | POST to `prod_assets` immediately (status: `pending`) |
| FLUX Kontext still rendered | POST to `prod_assets` immediately |
| Seedance clip animated | POST to `prod_assets` immediately |
| ffmpeg mix complete | POST to `prod_assets` immediately |
| Cropper HTML saved | POST to `prod_assets` immediately |
| Phase B script written | POST to `prod_assets` immediately |

**Never say:** "I'll register it later."  
**Always say:** "Registering now..." and POST before proceeding.

### Rule 4: Lineage Is Mandatory for Derivatives

**When an asset is derived from another (crop from master, clip from still, mix from stems), record the lineage.**

```bash
# Registering a 4:3 crop of the master Tessa still
curl -s -X POST "$BASE/items/prod_assets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "visual_crop",
    "asset_name": "Tessa Opening (4:3 Crop)",
    "file_path": "Production/Event_1/crops/m1_tessa_opening_4x3.png",
    "source_asset_id": "uuid-of-master-still",  # MANDATORY
    "metadata": {"visual": {"crop_aspect": "4:3", "crop_from_master": true}}
  }'
```

**Why:** If the master changes, we can trace which crops need to be regenerated.

---

## Gameplay Assets

### Wand Overlays

**What:** Animated wand overlay effects applied to child's screen during spell casting sequences.

**Created by:** video-producer skill (compositing) or design tool (Midjourney/Figma export)

**Stage:** audio, listen_through

**Registration pattern:**

```json
{
  "asset_type": "gameplay_overlay",
  "asset_name": "M1 Magic Hands Wand Overlay — Warm Glow",
  "file_path": "Production/Event_1/overlays/m1_wand_overlay_warm_v2.png",
  "metadata": {
    "gameplay": {
      "overlay_type": "wand",
      "applies_to_module": "m1_tessa",
      "applies_to_spell": "Magic Hands Spell",
      "animation_duration_seconds": 2.5,
      "format": "png_with_alpha",
      "color_profile": "sRGB"
    }
  },
  "tags": ["wand", "overlay", "m1_tessa", "spell_effect"],
  "notes": "Warm glow effect for calm moments during Magic Hands intro"
}
```

### Avatar Variants

**What:** Child avatar visual variants (expression changes, poses, costume/accessory changes).

**Created by:** video-producer skill (FLUX Kontext with consistent references) or design tool

**Stage:** audio, listen_through

**Registration pattern:**

```json
{
  "asset_type": "gameplay_avatar",
  "asset_name": "Child Avatar — Proud Expression",
  "file_path": "Production/Gameplay/avatar_variants/avatar_proud_v1.png",
  "metadata": {
    "gameplay": {
      "avatar_variant_type": "expression",
      "variant_key": "proud",
      "resolution": "512x512",
      "applies_to_contexts": ["success_moment", "courage_narrative"],
      "color_space": "sRGB",
      "consistent_reference_ids": ["avatar_base_v1", "avatar_hair_style_a"]
    }
  },
  "tags": ["avatar", "expression", "proud"],
  "notes": "Variant triggered on Courage Stone unlock or courageous action completion"
}
```

### Zone / Background Assets

**What:** Interactive zone backgrounds, forest/mountain/castle environment art, UI backplates for mini-games or rest areas.

**Created by:** video-producer skill (FLUX Kontext environment generation) or design tool

**Stage:** phase_a_json, audio

**Registration pattern:**

```json
{
  "asset_type": "gameplay_zone",
  "asset_name": "Everdale Forest — Day Variant with Sunlight",
  "file_path": "Production/Gameplay/zones/everdale_forest_day_v2.png",
  "metadata": {
    "gameplay": {
      "zone_type": "environment_background",
      "zone_name": "Everdale Forest",
      "variant": "day_sunlight",
      "resolution": "1920x1080",
      "applies_to_narrative_stages": ["m1_tessa", "m2_luna"],
      "color_space": "sRGB",
      "layer_count": 3
    }
  },
  "tags": ["zone", "everdale", "background", "environment"],
  "notes": "Used as main narrative background for Event 1–2, can be parallax-layered"
}
```

### Story Recap Assets

**What:** Visual assets (stills, short clips, interactive cards) displayed when parent triggers Story Recap feature.

**Created by:** video-producer skill or narrative-generator

**Stage:** audio, listen_through

**Registration pattern:**

```json
{
  "asset_type": "story_recap_asset",
  "asset_name": "Event 1 Recap Card — Magic Hands Spell Summary",
  "file_path": "Production/Event_1/recap/event_1_recap_card_spell_summary.png",
  "metadata": {
    "gameplay": {
      "recap_asset_type": "card",
      "recap_trigger_event": "m1_tessa",
      "recap_section": "spell_summary",
      "display_duration_seconds": 10,
      "includes_audio": false,
      "interactive_elements": ["tap_to_continue"]
    }
  },
  "tags": ["recap", "m1_tessa", "card", "interactive"],
  "notes": "Displays when parent taps 'Story Recap' on home screen or after 3-day idle trigger"
}
```

---

## Data / Configuration Assets

### Module JSON Configs (Phase A Designer Output)

**What:** Ingredient list, technique instructions, narrative context, and child-facing task definitions in structured JSON. Output of phase-a-designer skill.

**Created by:** phase-a-designer skill

**Stage:** phase_a_json

**Registration pattern:**

```json
{
  "asset_type": "data_phase_a_json",
  "asset_name": "M1 Tessa Phase A Config — Ingredients + Instructions",
  "file_path": "Production/Event_1/configs/m1_tessa_phase_a_v2.json",
  "metadata": {
    "data": {
      "config_type": "phase_a_design",
      "module_id": "m1_tessa",
      "stage": "phase_a_json",
      "ingredient_count": 5,
      "instruction_sections": ["ingredients", "technique", "outcome"],
      "child_task_count": 2,
      "personalization_variables": ["childName", "childPronoun"],
      "schema_version": "1.0"
    }
  },
  "tags": ["phase_a", "config", "m1_tessa", "design_spec"],
  "notes": "Finalized Phase A instructions from clinical review — includes body-sensing focus"
}
```

### Full Module JSON (Module JSON Builder Output)

**What:** Complete module configuration combining Phase B script, audio cue points, personalization variables, technique metadata, and progress state tracking.

**Created by:** module-json-builder skill

**Stage:** audio

**Registration pattern:**

```json
{
  "asset_type": "data_module_json",
  "asset_name": "M1 Tessa Complete Module JSON",
  "file_path": "Production/Event_1/modules/m1_tessa_module_complete_v1.json",
  "module_id": 1,
  "event_number": 1,
  "metadata": {
    "data": {
      "config_type": "complete_module",
      "module_id": "m1_tessa",
      "stage": "audio",
      "includes": ["phase_b_script", "audio_cuepoints", "personalization_map", "technique_data", "narrative_metadata"],
      "child_variables": ["childName", "childPronoun", "chosenGuideName"],
      "audio_file_references": 3,
      "personalization_variable_count": 8,
      "schema_version": "2.0"
    }
  },
  "tags": ["module_json", "complete", "m1_tessa", "production_ready"],
  "notes": "Ready for app integration — contains all personalization and audio routing"
}
```

### BreathCycle Rhythm JSON

**What:** Breath-pacing instructions in JSON format: breath length, hold time, pause duration, and count-breathing guidance for each phase of a technique. Computed by audio-producer during breathing rhythm mapping.

**Created by:** audio-producer skill

**Stage:** audio

**Registration pattern:**

```json
{
  "asset_type": "data_breathcycle",
  "asset_name": "M1 Magic Hands BreathCycle Rhythm — Palm Interoception",
  "file_path": "Production/Event_1/breathcycles/m1_magic_hands_breathcycle_v2.json",
  "metadata": {
    "data": {
      "config_type": "breathcycle_rhythm",
      "applies_to_technique": "Magic Hands Spell",
      "applies_to_module": "m1_tessa",
      "phase_count": 3,
      "total_breath_cycles": 4,
      "in_breath_seconds": 4,
      "hold_seconds": 0,
      "out_breath_seconds": 4,
      "count_breathing_style": "1-2-3-4, 1-2-3-4",
      "audio_timing_locked": true,
      "version": "3.1"
    }
  },
  "tags": ["breathcycle", "rhythm", "m1_tessa", "timing_locked"],
  "notes": "Synced to audio voice stem v3 — breathing cues at 2.5s, 6.8s, 11.2s marks"
}
```

### Personalization Variable Maps

**What:** JSON mapping of personalization variables (`{childName}`, `{childPronoun}`, `{parentTitle}`, etc.) to their runtime values and all locations where they're used in dialogue/UI.

**Created by:** narrative-generator or phase-a-designer

**Stage:** intake, phase_a_json

**Registration pattern:**

```json
{
  "asset_type": "data_personalization_map",
  "asset_name": "M1 Personalization Variables Map",
  "file_path": "Production/Event_1/maps/m1_personalization_vars_v1.json",
  "metadata": {
    "data": {
      "config_type": "personalization_map",
      "applies_to_module": "m1_tessa",
      "variables": {
        "childName": {"required": true, "type": "string", "usage_count": 12},
        "childPronoun": {"required": true, "type": "enum", "options": ["he/him", "she/her"], "usage_count": 8},
        "parentTitle": {"required": false, "type": "string", "default": "Parent", "usage_count": 3},
        "chosenGuideName": {"required": true, "type": "string", "usage_count": 4}
      },
      "total_personalization_locations": 27,
      "tts_segments_affected": 12,
      "ui_text_affected": 15
    }
  },
  "tags": ["personalization", "variables", "m1_tessa", "mapping"],
  "notes": "All variables set at app onboarding by therapist — mapping guides TTS generation"
}
```

### Technique Instruction Data

**What:** Structured JSON containing technique name, clinical name, step-by-step instructions, body-sensing language, outcome description, safety notes, and visual animation triggers for the instruction sequence.

**Created by:** phase-a-designer skill

**Stage:** phase_a_json

**Registration pattern:**

```json
{
  "asset_type": "data_technique_data",
  "asset_name": "Magic Hands Spell — Technique Definition & Instructions",
  "file_path": "Production/Event_1/techniques/magic_hands_spell_technique_v2.json",
  "metadata": {
    "data": {
      "config_type": "technique_definition",
      "spell_name": "Magic Hands Spell",
      "clinical_name": "Palm Interoception",
      "applies_to_module": "m1_tessa",
      "technique_tier": "tier_1_high_sensation",
      "instruction_steps": 5,
      "outcome_metrics": ["tingling_sensation", "warmth", "awareness"],
      "recommended_duration_seconds": 90,
      "animation_sequence_count": 4,
      "safety_notes_included": true,
      "schema_version": "1.0"
    }
  },
  "tags": ["technique", "m1_tessa", "magic_hands", "instruction_data"],
  "notes": "Phase A shows WHAT (ingredients + outcome). This defines HOW for Phase B meditation."
}
```

---

## Voice Profile Management

### Voice Profiles (Directus Records)

**What:** Locked TTS settings for each creature character and Guide Bird — ElevenLabs voice ID, stability, similarity, speed, emotional tone, and audio format preferences.

**Created by:** dashboard-gate skill (at session start) or admin-managed

**Stage:** all stages (locked at intake)

**Registration pattern:**

Voice profiles are registered as **Directus collection records** in `prod_voice_profiles`, not as file assets. However, they should also be tracked in `prod_assets` as reference data for audit purposes.

```json
{
  "asset_type": "voice_profile",
  "asset_name": "Tessa (M1) Voice Profile — Curious & Playful",
  "file_path": "N/A — Directus record",
  "metadata": {
    "voice": {
      "creature_name": "Tessa",
      "m_number": 1,
      "voice_id": "aZz7k8jX9mN2pQ4vL5wE",
      "model": "eleven_v3",
      "stability": 0.50,
      "similarity_boost": 0.75,
      "style": 0.30,
      "use_speaker_boost": false,
      "language": "en-US",
      "emotional_tone": "curious_playful_physical",
      "default_audio_format": "mp3_44100_128"
    }
  },
  "created_by": "dashboard-gate",
  "status": "approved",
  "tags": ["voice_profile", "creature", "m1_tessa", "locked"],
  "notes": "Locked April 10 — do not change without explicit session decision"
}
```

**Guide Bird & Myrrhin Profiles:**

```json
{
  "asset_type": "voice_profile",
  "asset_name": "Guide Bird Voice Profile — Warm & Energetic",
  "file_path": "N/A — Directus record",
  "metadata": {
    "voice": {
      "creature_name": "Guide Bird",
      "role": "guide_character_all_arcs",
      "voice_id": "pL9k3mN7wQ2jX8vZ1aE",
      "model": "eleven_v3",
      "stability": 0.65,
      "similarity_boost": 0.70,
      "style": 0.25,
      "use_speaker_boost": false,
      "emotional_tone": "warm_energetic_self_deprecating",
      "default_audio_format": "mp3_44100_128"
    }
  },
  "created_by": "dashboard-gate",
  "status": "approved",
  "tags": ["voice_profile", "guide", "all_arcs", "locked"],
  "notes": "Consistent across all 9 arcs — locked at Arc 1 production start"
}
```

---

## Narrative Structure Assets

### Event Metadata

**What:** Metadata for each narrative event (event number, creatures involved, story beats, technique being taught, domain/stone assignment, locked dialogue beats).

**Created by:** narrative-generator or skeleton extraction tool

**Stage:** phase_b, phase_a_json

**Registration pattern:**

```json
{
  "asset_type": "narrative_metadata",
  "asset_name": "Event 1 Metadata — Tessa Introduction & Magic Hands Spell",
  "file_path": "Production/Event_1/metadata/event_1_metadata_v1.json",
  "event_number": 1,
  "metadata": {
    "narrative": {
      "event_number": 1,
      "creatures_featured": ["Tessa", "Guide Bird", "Oliver"],
      "spell_taught": "Magic Hands Spell",
      "technique_clinical_name": "Palm Interoception",
      "domain_taught": "Body-Sensing",
      "stone_introduced": "Body Stone",
      "stone_inscription": "Feel what's real",
      "story_beats_count": 6,
      "locked_dialogue_lines": 3,
      "estimated_duration_minutes": 8,
      "phase_b_narrative_arcs": 2
    }
  },
  "tags": ["narrative_metadata", "event_1", "m1_tessa", "skeleton_reference"],
  "notes": "Single source of truth for Event 1 structural metadata — used by phase-b-writer and audio-producer"
}
```

### Dialogue Transcripts (Locked)

**What:** Final, locked dialogue from the arc skeleton — character names, exact lines, parenthetical actions/emotions, line attribution. Extracted for reference during audio/video production.

**Created by:** arc-builder skill (skeleton extraction) or manual export from skeleton .docx

**Stage:** phase_b, audio

**Registration pattern:**

```json
{
  "asset_type": "dialogue_transcript",
  "asset_name": "Event 1 Dialogue Transcript — Locked from ARC_1_SKELETON_DRAFT",
  "file_path": "Production/Event_1/dialogue/event_1_dialogue_locked_v1.json",
  "event_number": 1,
  "metadata": {
    "narrative": {
      "asset_type_name": "dialogue_transcript",
      "extracted_from_skeleton": "ARC_1_SKELETON_DRAFT.docx",
      "skeleton_version": "v3",
      "dialogue_line_count": 27,
      "speakers": ["Guide Bird", "Tessa", "Oliver", "Myrrhin (narrator)"],
      "locked_lines": 27,
      "format": "json_with_line_numbers_and_emotions"
    }
  },
  "source_asset_id": "skeleton_record_id",
  "created_by": "arc-builder",
  "status": "approved",
  "tags": ["dialogue", "locked", "event_1", "transcript"],
  "notes": "Locked from skeleton for audio production reference — never edit without skeleton update"
}
```

---

## Dashboard Schema: Asset Types & Metadata

Each `asset_type` has specific metadata stored in the JSON `metadata` field. This allows type-specific queries and validation.

| Asset Type | Metadata Schema |
|-----------|-----------------|
| `visual_still` | `{visual: {width: int, height: int, dpi: int, color_space: "sRGB", reference_images: [], generator: "flux_kontext\|midjourney"}}`|
| `visual_crop` | `{visual: {aspect_ratio: "4:3\|16:9\|1:1", original_dimensions: {w, h}, crop_coords: {x, y, w, h}}}`|
| `video_clip` | `{video: {duration_seconds: float, fps: int, codec: "h264\|h265", resolution: "1080p\|720p", tool: "seedance_2.0\|kling_3.0"}}`|
| `audio_stem` | `{audio: {duration_seconds: float, voice_id: string, stability: float, similarity: float, model: "eleven_v3", sample_rate: int}}`|
| `audio_mix` | `{audio: {duration_seconds: float, layers: int, loudness_lufs: float, format: "mp3\|wav", bitrate_kbps: int}}`|
| `html_storyboard` | `{html: {event_number: int, image_count: int, audio_file: string, embedded_styles: bool}}`|
| `html_cropper` | `{html: {master_asset_id: string, preset_aspect_ratios: ["4:3", "16:9"]}}`|
| `script_phase_b` | `{script: {word_count: int, duration_estimate_seconds: float, cue_marker_count: int, status: "draft\|ready_for_audio"}}`|
| `gameplay_overlay` | `{gameplay: {overlay_type: "wand\|effect", applies_to_module: string, animation_duration_seconds: float, format: "png_with_alpha\|mp4"}}`|
| `gameplay_avatar` | `{gameplay: {avatar_variant_type: "expression\|pose\|costume", variant_key: string, resolution: string, applies_to_contexts: []}}`|
| `gameplay_zone` | `{gameplay: {zone_type: "environment_background\|mini_game_ui", zone_name: string, variant: string, resolution: string, applies_to_narrative_stages: []}}`|
| `data_phase_a_json` | `{data: {config_type: "phase_a_design", ingredient_count: int, instruction_sections: [], child_task_count: int, schema_version: string}}`|
| `data_module_json` | `{data: {config_type: "complete_module", includes: [], child_variables: [], audio_file_references: int, schema_version: string}}`|
| `data_breathcycle` | `{data: {applies_to_technique: string, phase_count: int, total_breath_cycles: int, in_breath_seconds: float, out_breath_seconds: float}}`|
| `data_personalization_map` | `{data: {applies_to_module: string, variables: {}, total_personalization_locations: int, tts_segments_affected: int}}`|
| `data_technique_data` | `{data: {spell_name: string, clinical_name: string, instruction_steps: int, technique_tier: string, animation_sequence_count: int}}`|
| `voice_profile` | `{voice: {creature_name: string, voice_id: string, stability: float, similarity_boost: float, style: float, emotional_tone: string}}`|
| `narrative_metadata` | `{narrative: {event_number: int, creatures_featured: [], spell_taught: string, domain_taught: string, stone_introduced: string}}`|
| `dialogue_transcript` | `{narrative: {extracted_from_skeleton: string, dialogue_line_count: int, speakers: [], format: string, locked_lines: int}}`|

---

## Skill Integration: How This Works With Existing Skills

### Audio Producer Skill

**Current workflow (without registry):**
1. Generates voice stem
2. Saves to `Production/Event_1/m1_voice_stem_v3.mp3`
3. Plays for Kim
4. ??? (file is lost in chaos)

**New workflow (with registry):**
1. Generates voice stem
2. Saves to `Production/Event_1/m1_voice_stem_v3.mp3`
3. **Registers in `prod_assets` with status `pending`** (gets back `asset_id`)
4. Opens file via Finder for Kim review (using `asset_id` + file_path lookup)
5. Kim approves → Claude updates `prod_assets` to status `approved`
6. Next step: mixer queries `prod_assets WHERE module_id=1 AND asset_type='audio_stem' AND status='approved'` to find the file to mix

**Required updates to audio-producer skill:**
- After TTS generation, POST to `prod_assets` (not just save to disk)
- When asking Kim to review, use computer-use to open via Finder
- Update asset status based on Kim verdict before proceeding

### Video Producer Skill

**New workflow:**
1. Generates FLUX Kontext stills → register each in `prod_assets` as `visual_still` (status: `pending`)
2. Generates Seedance clips → register each as `video_clip` (status: `pending`)
3. Ask Kim to review stills (open via Preview)
4. Kim approves → update status to `approved`
5. Build storyboard → query `prod_assets WHERE event_number=1 AND asset_type='visual_still' AND status='approved'` to get file paths
6. Build cropper → query for master still with `tags` containing `"master"`

### Build Storyboard/Cropper Tools

**New workflow:**
- **Never** hardcoded filenames like `m1_tessa_opening.png`
- **Always** query dashboard first: `prod_assets WHERE event_number=X AND asset_type='visual_still' AND status='approved'`
- Extract file paths from query results
- Pass file paths (not names) to tools
- After cropping, register new crop assets with `source_asset_id` pointing to master

### Module JSON Builder Skill

**New workflow:**
1. Query `prod_assets WHERE module_id=X AND asset_type IN ('data_phase_a_json', 'audio_stem', 'audio_cuepoint', 'data_personalization_map')`
2. Combine these approved assets into complete module JSON
3. Register output as `data_module_json` (status: `pending`)
4. Ask Kim to review (this JSON becomes the child's runtime config)
5. Update status to `approved`

### Narrative Generator Skill

**New workflow:**
1. Generate event metadata and dialogue transcripts from skeleton
2. Register as `narrative_metadata` and `dialogue_transcript` (status: `pending`)
3. Register personalization variable maps as `data_personalization_map`
4. These feed downstream into phase-a-designer and audio-producer

### Video Producer: Gameplay Assets

**New workflow:**
1. Generate wand overlays as `gameplay_overlay` (status: `pending`)
2. Generate avatar variants as `gameplay_avatar` (status: `pending`)
3. Generate zone backgrounds as `gameplay_zone` (status: `pending`)
4. Ask Kim to review all visual gameplay assets
5. Update status to `approved`
6. Module-json-builder can then reference approved gameplay assets for inclusion in module config

---

## Practical Query Examples

### "What assets do I have for M1?"

```bash
curl -s "$BASE/items/prod_assets?filter[module_id][_eq]=1&sort=asset_type,created_at" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {asset_type, asset_name, status, file_path}'
```

Output:
```
{
  "asset_type": "audio_stem",
  "asset_name": "M1 Voice Stem v3",
  "status": "approved",
  "file_path": "Production/Event_1/m1_voice_stem_v3.mp3"
}
{
  "asset_type": "visual_still",
  "asset_name": "Tessa Opening",
  "status": "approved",
  "file_path": "Production/Event_1/m1_tessa_opening_still.png"
}
...
```

### "Which stills are ready for the storyboard?"

```bash
curl -s "$BASE/items/prod_assets?filter[asset_type][_eq]=visual_still&filter[status][_eq]=approved&filter[tags][_contains]=ready_for_storyboard&sort=created_at" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {asset_name, file_path}'
```

### "Show me all rejected assets so I can decide whether to redo them"

```bash
curl -s "$BASE/items/prod_assets?filter[status][_eq]=rejected&sort=-created_at" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {asset_name, asset_type, module_id, kim_feedback}'
```

### "Get the master still that this crop came from"

```bash
# First, find the crop
CROP_ID="uuid-of-crop"
SOURCE_ID=$(curl -s "$BASE/items/prod_assets/$CROP_ID" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.data.source_asset_id')

# Then fetch the master
curl -s "$BASE/items/prod_assets/$SOURCE_ID" \
  -H "Authorization: Bearer $TOKEN" | jq '.data | {asset_name, file_path}'
```

### "What audio assets are pending Kim review?"

```bash
curl -s "$BASE/items/prod_assets?filter[asset_type][_in]=audio_stem,audio_mix,audio_bed&filter[status][_eq]=pending&sort=-created_at" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {module_id, asset_name, created_at}'
```

---

## Dashboard-Gate Skill Integration

The **dashboard-gate** skill enforces the 7-query protocol at session start, which now includes:

**Query 4 (NEW): Asset status by type**

```bash
# What assets exist for this module, and are they approved?
curl -s "$BASE/items/prod_assets?filter[module_id][_eq]={id}&sort=asset_type,created_at" \
  -H "Authorization: Bearer $TOKEN"
```

**Why:** Before starting audio production for M1, check if a voice stem already exists in `approved` status. If it does, reuse it. If multiple exist, ask Kim which to use. If all are `rejected`, create a new one.

---

## File Naming Convention

While the asset registry is the source of truth (not filenames), consistent naming helps with Finder navigation and debugging.

**Pattern:** `m{N}_{creature}_{asset_type}_{variant}.{ext}`

| Asset | Example Filename |
|-------|-----------------|
| Voice stem | `m1_tessa_voice_stem_v3.mp3` |
| Still | `m1_tessa_opening_still.png` |
| 4:3 Crop | `m1_tessa_opening_4x3_crop.png` |
| Animated clip | `m1_tessa_walking_clip_01.mp4` |
| Ambient bed | `m1_ambient_warm_body_v1.mp3` |
| Final mix | `m1_phase_b_complete_mix.mp3` |
| Storyboard HTML | `event_1_m1_tessa_storyboard.html` |
| Cropper HTML | `event_1_m1_tessa_crops_4x3.html` |

**Folder structure:**

```
Production/
├── Event_1/
│   ├── m1_tessa_opening_still.png          [master still]
│   ├── m1_tessa_sad_still.png
│   ├── m1_tessa_walking_clip_01.mp4
│   ├── m1_voice_stem_v3.mp3                [approved voice stem]
│   ├── m1_ambient_warm_body_v1.mp3
│   ├── m1_phase_b_complete_mix.mp3
│   ├── m1_phase_b_script.docx
│   ├── crops/
│   │   ├── m1_tessa_opening_4x3.png        [derived from master]
│   │   ├── m1_tessa_sad_4x3.png
│   │   └── ...
│   ├── event_1_m1_tessa_storyboard.html
│   └── event_1_m1_tessa_cropper.html
├── Event_2/
│   └── ...
```

**Rule:** Filenames should be descriptive enough that Kim can identify the asset in Finder, but the asset registry is the authoritative source for which file is "current."

---

## Session Resumption: Recovery Pattern

If a production session is interrupted:

**At session start:**

```bash
# Query all assets for M1 with status != "archived"
curl -s "$BASE/items/prod_assets?filter[module_id][_eq]=1&filter[status][_neq]=archived&sort=asset_type,-created_at" \
  -H "Authorization: Bearer $TOKEN"
```

**Determine where you left off:**

| Last Registered Asset Type | Next Action |
|---------------------------|-------------|
| `audio_stem` with status `approved` | Proceed to mixing (query approved stem, mix with ambient + SFX) |
| `audio_stem` with status `pending` | Ask Kim for verdict before mixing |
| `visual_still` with status `approved` | Proceed to animation or storyboard |
| `video_clip` with status `pending` | Ask Kim to review clips before lip-sync |
| `audio_mix` with status `approved` | Proceed to listen-through |

**Resumption guarantee:** Every asset is tracked in the registry with creation time and status. You can always see exactly where production stopped and what's waiting for Kim's approval.

---

## Troubleshooting

### "I can't find the audio file Kim just approved"

**Solution:**
1. Query `prod_assets WHERE module_id=1 AND asset_type='audio_stem' AND status='approved'`
2. Extract `file_path` from the result
3. Construct Mac path and open via Finder
4. **Never** search the Dropbox folder manually

### "I generated 3 voice stems but don't know which one to use"

**Solution:**
1. Query all voice stems for M1: `prod_assets WHERE module_id=1 AND asset_type='audio_stem'`
2. Check their status and `kim_feedback`:
   - One is `approved` → use that one
   - Multiple are `approved` → ask Kim which
   - All are `pending` or `in_review` → ask Kim for verdict before proceeding
3. Never mix multiple voice stems together

### "The storyboard built last week isn't loading images"

**Likely cause:** Images weren't registered in `prod_assets` with status `approved`, or filenames changed.

**Solution:**
1. Check asset status: query `prod_assets WHERE event_number=1 AND asset_type='visual_still'`
2. If status is `rejected`, regenerate the stills
3. If status is `approved` but filenames in HTML don't match `file_path`, rebuild the storyboard (it will query the registry for current paths)

---

## Migration: Using Registry With Existing Workflows

**If production is already underway (e.g., M1 voice stem v5 exists on disk but isn't in registry):**

1. **Don't delete or move the file**
2. **Register it retroactively:**

```bash
curl -s -X POST "$BASE/items/prod_assets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "module_id": 1,
    "event_number": 1,
    "asset_type": "audio_stem",
    "asset_name": "M1 Voice Stem v5 (Existing)",
    "file_path": "Production/Event_1/m1_voice_stem_v5.mp3",
    "created_by": "claude",
    "status": "approved",  # Assume approved unless Kim says otherwise
    "notes": "Retroactively registered April 13 — existing file, confirmed working"
  }'
```

3. **From this point forward**, all new assets follow the register-immediately pattern

---

## Summary: The Golden Rules

1. **Query first.** Never guess filenames. Always query `prod_assets` before using a file.
2. **Register immediately.** Every file created must be registered in `prod_assets` before the function returns.
3. **Check status.** Never use a file with status other than `approved`.
4. **Track lineage.** Derivative assets must have `source_asset_id` pointing to their parent.
5. **Open via Finder.** Never tell Kim a file path. Use computer-use to open files so they appear on her screen.
6. **Log everything.** Every registration, approval, and status change goes in the dashboard (and in `prod_activity_log` for audit).
7. **Stop on missing assets.** If a required asset is missing or not approved, STOP and ask Kim. Never guess, never use rejected files.

---

## Appendix A: Directus Collection SQL

For future reference, `prod_assets` collection registration:

```sql
CREATE TABLE IF NOT EXISTS prod_assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  module_id UUID REFERENCES prod_modules(id) NOT NULL,
  event_number INTEGER NOT NULL,
  asset_type TEXT NOT NULL CHECK (asset_type IN (
    'visual_still', 'visual_crop', 'visual_composite', 'video_clip', 'video_lipsync', 'video_assembled',
    'audio_stem', 'audio_bed', 'audio_sfx', 'audio_mix', 'audio_cuepoint',
    'script_phase_b', 'script_phase_a', 'html_storyboard', 'html_cropper',
    'gameplay_overlay', 'gameplay_avatar', 'gameplay_zone',
    'data_phase_a_json', 'data_module_json', 'data_breathcycle', 'data_personalization_map', 'data_technique_data',
    'voice_profile', 'narrative_metadata', 'dialogue_transcript', 'other'
  )),
  asset_name TEXT NOT NULL,
  file_path TEXT NOT NULL,
  file_size_bytes BIGINT,
  file_hash TEXT,
  created_at TIMESTAMP DEFAULT now(),
  created_by TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
    'pending', 'in_review', 'approved', 'rejected', 'superseded', 'archived'
  )),
  kim_verdict TEXT CHECK (kim_verdict IN ('approved', 'rejected', 'revise_and_resubmit', 'pending')),
  kim_feedback TEXT,
  source_asset_id UUID REFERENCES prod_assets(id),
  metadata JSONB,
  tags TEXT[] DEFAULT ARRAY[]::TEXT[],
  notes TEXT,
  session_id TEXT,
  updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_prod_assets_module_id ON prod_assets(module_id);
CREATE INDEX idx_prod_assets_event_type_status ON prod_assets(event_number, asset_type, status);
CREATE INDEX idx_prod_assets_status_created ON prod_assets(status, created_at DESC);
CREATE INDEX idx_prod_assets_source_id ON prod_assets(source_asset_id);
```

---

**End of Document**

This workflow is the single source of truth for asset tracking in MindfulNest production. Every skill that creates, reviews, or uses assets should reference this document.
