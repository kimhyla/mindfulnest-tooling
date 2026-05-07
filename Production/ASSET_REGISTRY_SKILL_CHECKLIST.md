# Asset Registry Skill Checklist

**Quick reference for production skills: audio-producer, video-producer, phase-b-writer, and tools like build_storyboard.py and build_cropper.py**

---

## Before You Start

- [ ] Read `ASSET_REGISTRY_WORKFLOW_v1.md` in full
- [ ] Load dashboard-ops skill (required for all asset operations)
- [ ] Authenticate to Directus (token expires in 15 minutes)

---

## Creating Any Asset (Audio, Video, Still, Script, HTML)

### Immediately After File Is Written

```bash
# 1. Verify file exists
if [ ! -f "$FILE_PATH" ]; then
  echo "ERROR: File not written"; exit 1
fi

# 2. Compute file metadata
FILE_SIZE=$(stat -c%s "$FILE_PATH")
FILE_HASH=$(sha256sum "$FILE_PATH" | cut -d' ' -f1)
DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1:novalue=1 "$FILE_PATH" 2>/dev/null || echo "unknown")

# 3. Register in dashboard IMMEDIATELY (do not wait)
curl -s -X POST "$BASE/items/prod_assets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "module_id": MODULE_ID,
    "event_number": EVENT_NUM,
    "asset_type": "ASSET_TYPE",        # See valid types in ASSET_REGISTRY_WORKFLOW_v1.md
    "asset_name": "Human-readable name",
    "file_path": "Production/Event_{N}/filename",
    "file_size_bytes": FILE_SIZE,
    "file_hash": "FILE_HASH",
    "created_by": "claude",
    "status": "pending",
    "metadata": {...type-specific...},
    "notes": "Context for Kim"
  }' | jq '.data.id'  # Capture the asset_id for next steps
```

**Do NOT proceed to the next step until registration is complete.**

### Type-Specific Metadata

When registering, include relevant metadata in the `metadata` JSON field:

**Audio Stem:**
```json
"metadata": {
  "audio": {
    "duration_seconds": 145.2,
    "voice_id": "oR4uRy4fHDUGGISL0Rev",
    "model": "eleven_v3",
    "stability": 0.5,
    "similarity": 0.75,
    "style": 0.3
  }
}
```

**Visual Still:**
```json
"metadata": {
  "visual": {
    "width": 960,
    "height": 960,
    "dpi": 72,
    "color_space": "sRGB",
    "generator": "flux_kontext",
    "reference_images": ["m1_tessa_ref_1.png", "m1_tessa_ref_2.png"]
  }
}
```

**Video Clip:**
```json
"metadata": {
  "video": {
    "duration_seconds": 5.2,
    "fps": 24,
    "codec": "h264",
    "resolution": "1080p",
    "generator": "seedance_2.0",
    "motion_prompt_length": 75
  }
}
```

**Wand Overlay:**
```json
"metadata": {
  "gameplay": {
    "overlay_type": "wand",
    "applies_to_module": "m1_tessa",
    "applies_to_spell": "Magic Hands Spell",
    "animation_duration_seconds": 2.5,
    "format": "png_with_alpha"
  }
}
```

**Breath Cycle JSON:**
```json
"metadata": {
  "data": {
    "config_type": "breathcycle_rhythm",
    "applies_to_technique": "Magic Hands Spell",
    "in_breath_seconds": 4,
    "hold_seconds": 0,
    "out_breath_seconds": 4,
    "count_breathing_style": "1-2-3-4, 1-2-3-4",
    "audio_timing_locked": true
  }
}
```

**Module JSON:**
```json
"metadata": {
  "data": {
    "config_type": "complete_module",
    "module_id": "m1_tessa",
    "includes": ["phase_b_script", "audio_cuepoints", "personalization_map", "technique_data"],
    "child_variables": ["childName", "childPronoun", "chosenGuideName"],
    "schema_version": "2.0"
  }
}
```

**Voice Profile:**
```json
"metadata": {
  "voice": {
    "creature_name": "Tessa",
    "m_number": 1,
    "voice_id": "aZz7k8jX9mN2pQ4vL5wE",
    "model": "eleven_v3",
    "stability": 0.50,
    "similarity_boost": 0.75,
    "style": 0.30,
    "emotional_tone": "curious_playful_physical"
  }
}
```

---

## Opening Assets for Kim Review

### Never Tell Kim a Path

**WRONG:**
> "Voice stem is at Production/Event_1/m1_voice_stem_v3.mp3"

**RIGHT:**
> "I've generated a voice stem with faster pacing. Please listen and let me know if the rhythm works."
> [Uses computer-use to open file in QuickTime]

### Implementation

```python
# 1. Query asset to get file_path
asset = query_directus(f"prod_assets/{asset_id}")
file_path = asset["file_path"]  # e.g., "Production/Event_1/m1_voice_stem_v3.mp3"

# 2. Construct Mac path
mac_path = f"/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/{file_path}"

# 3. Use computer-use MCP to open
request_access(apps=["Finder", "QuickTime Player"])  # or Preview, Chrome, Word depending on type
open_file_via_finder(mac_path)  # Opens in appropriate app

# 4. Tell Kim it's open (natural language only)
# "I've opened your voice stem. Let me know if the rhythm works."
```

**File type → default app mapping:**
- `.mp3`, `.wav`: QuickTime Player
- `.png`, `.jpg`: Preview
- `.mp4`: QuickTime Player
- `.html`: Chrome/Safari
- `.md`: Preview
- `.docx`: Microsoft Word

---

## Getting Kim's Verdict

### After Kim Reviews, Ask Directly

"Is this approved, or does it need changes?"

**Possible responses:**
- ✅ **Approved** → Update `prod_assets.status = 'approved'`
- ❌ **Rejected** → Update `prod_assets.status = 'rejected'` + capture `kim_feedback`
- 🔄 **Revise** → Update `prod_assets.status = 'in_review'` + capture feedback + create new version

### Update Asset Status

```bash
# Kim approved
curl -s -X PATCH "$BASE/items/prod_assets/{ASSET_ID}" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "approved",
    "kim_verdict": "approved"
  }'

# Kim rejected
curl -s -X PATCH "$BASE/items/prod_assets/{ASSET_ID}" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "rejected",
    "kim_verdict": "rejected",
    "kim_feedback": "Too dark, adjust lighting"
  }'

# Kim says revise
curl -s -X PATCH "$BASE/items/prod_assets/{ASSET_ID}" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "in_review",
    "kim_verdict": "revise_and_resubmit",
    "kim_feedback": "Pacing feels rushed in section 2, slow it down"
  }'
```

---

## Using Approved Assets

### Query Pattern: Get All Approved Assets of Type

```bash
# Get approved audio stems for a module
curl -s "$BASE/items/prod_assets?filter[module_id][_eq]=$MODULE_ID&filter[asset_type][_eq]=audio_stem&filter[status][_eq]=approved" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[0] | {id, asset_name, file_path}'
```

### Extract File Path and Use

```python
assets = query_directus(
  "prod_assets",
  filters={
    "module_id": module_id,
    "asset_type": "audio_stem",
    "status": "approved"
  }
)

if not assets:
  print("ERROR: No approved voice stem for this module")
  print("STOP and ask Kim. Do not guess filenames.")
  exit(1)

voice_stem = assets[0]  # Most recent
file_path = voice_stem["file_path"]
mac_path = f"/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/{file_path}"

# Use in ffmpeg mix, etc.
ffmpeg_command = f'ffmpeg -i "{mac_path}" -i ambient_bed.mp3 ...'
```

---

## Registering Gameplay Assets

### Wand Overlays

```bash
# After generating wand overlay PNG/MP4
curl -s -X POST "$BASE/items/prod_assets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "module_id": MODULE_ID,
    "event_number": EVENT_NUM,
    "asset_type": "gameplay_overlay",
    "asset_name": "M1 Magic Hands Wand Overlay — Warm Glow",
    "file_path": "Production/Event_1/overlays/m1_wand_overlay_warm_v2.png",
    "status": "pending",
    "metadata": {
      "gameplay": {
        "overlay_type": "wand",
        "applies_to_spell": "Magic Hands Spell",
        "animation_duration_seconds": 2.5,
        "format": "png_with_alpha"
      }
    },
    "tags": ["wand", "overlay", "m1_tessa", "spell_effect"]
  }'
```

### Avatar Variants

```bash
curl -s -X POST "$BASE/items/prod_assets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "module_id": MODULE_ID,
    "event_number": EVENT_NUM,
    "asset_type": "gameplay_avatar",
    "asset_name": "Child Avatar — Proud Expression",
    "file_path": "Production/Gameplay/avatar_variants/avatar_proud_v1.png",
    "status": "pending",
    "metadata": {
      "gameplay": {
        "avatar_variant_type": "expression",
        "variant_key": "proud",
        "resolution": "512x512",
        "applies_to_contexts": ["success_moment", "courage_narrative"]
      }
    },
    "tags": ["avatar", "expression", "proud"]
  }'
```

### Zone / Background Assets

```bash
curl -s -X POST "$BASE/items/prod_assets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "module_id": MODULE_ID,
    "event_number": EVENT_NUM,
    "asset_type": "gameplay_zone",
    "asset_name": "Everdale Forest — Day Variant",
    "file_path": "Production/Gameplay/zones/everdale_forest_day_v2.png",
    "status": "pending",
    "metadata": {
      "gameplay": {
        "zone_type": "environment_background",
        "zone_name": "Everdale Forest",
        "variant": "day_sunlight",
        "resolution": "1920x1080"
      }
    },
    "tags": ["zone", "everdale", "background", "environment"]
  }'
```

---

## Registering Data / Configuration Assets

### Phase A JSON Config

```bash
curl -s -X POST "$BASE/items/prod_assets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "module_id": MODULE_ID,
    "event_number": EVENT_NUM,
    "asset_type": "data_phase_a_json",
    "asset_name": "M1 Tessa Phase A Config — Ingredients + Instructions",
    "file_path": "Production/Event_1/configs/m1_tessa_phase_a_v2.json",
    "status": "pending",
    "metadata": {
      "data": {
        "config_type": "phase_a_design",
        "ingredient_count": 5,
        "instruction_sections": ["ingredients", "technique", "outcome"],
        "schema_version": "1.0"
      }
    },
    "tags": ["phase_a", "config", "m1_tessa"]
  }'
```

### Breath Cycle Rhythm JSON

```bash
curl -s -X POST "$BASE/items/prod_assets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "module_id": MODULE_ID,
    "event_number": EVENT_NUM,
    "asset_type": "data_breathcycle",
    "asset_name": "M1 Magic Hands BreathCycle Rhythm",
    "file_path": "Production/Event_1/breathcycles/m1_magic_hands_breathcycle_v2.json",
    "status": "pending",
    "metadata": {
      "data": {
        "applies_to_technique": "Magic Hands Spell",
        "total_breath_cycles": 4,
        "in_breath_seconds": 4,
        "out_breath_seconds": 4,
        "audio_timing_locked": true
      }
    },
    "tags": ["breathcycle", "rhythm", "m1_tessa"]
  }'
```

### Module JSON (Complete)

```bash
curl -s -X POST "$BASE/items/prod_assets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "module_id": MODULE_ID,
    "event_number": EVENT_NUM,
    "asset_type": "data_module_json",
    "asset_name": "M1 Tessa Complete Module JSON",
    "file_path": "Production/Event_1/modules/m1_tessa_module_complete_v1.json",
    "status": "pending",
    "metadata": {
      "data": {
        "config_type": "complete_module",
        "includes": ["phase_b_script", "audio_cuepoints", "personalization_map"],
        "schema_version": "2.0"
      }
    },
    "tags": ["module_json", "complete", "m1_tessa"]
  }'
```

---

## Registering Derivative Assets (Crops, Clips, Mixes)

### Link to Source Asset

When you create an asset FROM another asset (e.g., 4:3 crop from 960x960 master still):

```bash
curl -s -X POST "$BASE/items/prod_assets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "module_id": MODULE_ID,
    "event_number": EVENT_NUM,
    "asset_type": "visual_crop",
    "asset_name": "Tessa Opening — 4:3 Crop for Storyboard",
    "file_path": "Production/Event_1/crops/m1_tessa_opening_4x3.png",
    "source_asset_id": "UUID-OF-MASTER-STILL",  # MANDATORY
    "status": "pending",
    "metadata": {
      "visual": {
        "aspect_ratio": "4:3",
        "crop_from_master": true,
        "crop_coords": {"x": 100, "y": 50, "w": 760, "h": 570}
      }
    },
    "tags": ["crop", "4:3", "ready_for_storyboard"]
  }'
```

**Why:** If the master still changes, you can query for all its derived crops and regenerate them.

---

## Build Storyboard / Build Cropper: Updated Workflow

### Storyboard Builder (build_storyboard.py)

**BEFORE:** Hardcoded filenames, lots of guessing

**NOW:**
```python
# 1. Query dashboard for approved stills
stills = query_directus(
  "prod_assets",
  filters={
    "event_number": event_num,
    "asset_type": "visual_still",
    "status": "approved"
  },
  sort="created_at"
)

# 2. Extract file paths
still_files = [s["file_path"] for s in stills]

# 3. Query for approved audio mix
audio = query_directus(
  "prod_assets",
  filters={
    "module_id": module_id,
    "asset_type": "audio_mix",
    "status": "approved"
  }
)

if not audio:
  print("ERROR: No approved audio mix. Cannot build storyboard.")
  exit(1)

audio_file = audio[0]["file_path"]

# 4. Pass to build_storyboard.py
build_storyboard(still_files, audio_file, output_html)

# 5. Register the HTML as an asset
curl -s -X POST "$BASE/items/prod_assets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "html_storyboard",
    "asset_name": "Event 1 Storyboard — Full Narrative",
    "file_path": "Production/Event_1/event_1_storyboard.html",
    "status": "pending",
    "metadata": {"html": {"image_count": 10, "audio_file": "'$audio_file'"}}
  }'
```

### Cropper Builder (build_cropper.py)

**BEFORE:** Guessed "m1_tessa_sad.png" and hoped it existed

**NOW:**
```python
# 1. Query for the MASTER still (tagged as such)
master = query_directus(
  "prod_assets",
  filters={
    "event_number": event_num,
    "asset_type": "visual_still",
    "status": "approved",
    "tags": "contains:master"  # Or specify by asset_name
  }
)

if not master:
  print("ERROR: No master still found for cropping")
  exit(1)

master_file = master[0]["file_path"]
master_id = master[0]["id"]

# 2. Pass to build_cropper.py
build_cropper(master_file, aspect_ratios=["4:3", "16:9"])

# 3. For each crop saved, register it
for crop_file, aspect_ratio in saved_crops:
  curl -s -X POST "$BASE/items/prod_assets" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "asset_type": "visual_crop",
      "asset_name": "Tessa Sad — '$aspect_ratio' Crop",
      "file_path": "'$crop_file'",
      "source_asset_id": "'$master_id'",
      "status": "pending",
      "tags": ["crop", "'$aspect_ratio'"]
    }'
```

---

## Error Handling

### Missing Required Asset

```bash
# You need an approved voice stem for M1
STEM=$(curl -s "$BASE/items/prod_assets?filter[module_id][_eq]=1&filter[asset_type][_eq]=audio_stem&filter[status][_eq]=approved" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[0]')

if [ -z "$STEM" ] || [ "$STEM" = "null" ]; then
  echo "ERROR: No approved voice stem for M1"
  echo "STOP. Ask Kim what to do."
  echo ""
  echo "Available voice stems for M1:"
  curl -s "$BASE/items/prod_assets?filter[module_id][_eq]=1&filter[asset_type][_eq]=audio_stem" \
    -H "Authorization: Bearer $TOKEN" | jq '.data[] | {asset_name, status, kim_feedback}'
  exit 1
fi
```

### Asset Status Check Before Use

```bash
# WRONG — just use the file
audio_file = "Production/Event_1/m1_voice_stem_v3.mp3"

# RIGHT — verify it's approved
ASSET=$(curl -s "$BASE/items/prod_assets?filter[file_path][_eq]=Production/Event_1/m1_voice_stem_v3.mp3" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[0]')

STATUS=$(echo "$ASSET" | jq -r '.status')
if [ "$STATUS" != "approved" ]; then
  echo "ERROR: Asset status is $STATUS (not approved)"
  exit 1
fi

audio_file=$(echo "$ASSET" | jq -r '.file_path')
```

---

## Logging

After every significant action, log to `prod_activity_log`:

```bash
curl -s -X POST "$BASE/items/prod_activity_log" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "module_id": MODULE_ID,
    "action": "Registered audio stem v3 and presented to Kim for pacing review",
    "performed_by": "claude",
    "details": {
      "asset_id": "UUID-OF-ASSET",
      "asset_type": "audio_stem",
      "status": "pending"
    }
  }'
```

---

## Session Interruption Recovery

**At session start, check what assets exist:**

```bash
# Query all assets for this module
curl -s "$BASE/items/prod_assets?filter[module_id][_eq]=$MODULE_ID&sort=-created_at" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {asset_type, asset_name, status, kim_feedback}'
```

**Determine what to do next:**
- `approved` audio stem → proceed to mixing
- `pending` voice stem → ask Kim for verdict
- `rejected` video clip → regenerate
- `approved` final mix → proceed to listen-through

---

## Checklist for Each Skill

### Audio Producer Skill

- [ ] Query for existing approved voice stem before generating
- [ ] Generate voice stem via ElevenLabs
- [ ] Register in `prod_assets` immediately (status: `pending`)
- [ ] Open for Kim via Finder (QuickTime)
- [ ] Get Kim's verdict
- [ ] Update asset status to `approved` or `rejected`
- [ ] If approved, proceed to cue mapping + mixing
- [ ] Register final mix in `prod_assets` (status: `pending`)
- [ ] Open final mix for Kim via Finder
- [ ] Get listen-through verdict
- [ ] Update final mix status to `approved`

### Video Producer Skill

- [ ] Query for existing approved stills before generating
- [ ] Generate stills via FLUX Kontext
- [ ] Register each still in `prod_assets` immediately (status: `pending`)
- [ ] Open key stills for Kim via Preview
- [ ] Get verdict
- [ ] Update all stills to `approved` or `rejected`
- [ ] Generate clips via Seedance/Kling
- [ ] Register each clip in `prod_assets` immediately (status: `pending`)
- [ ] Proceed through lip sync and assembly...
- [ ] Register final assembled video in `prod_assets` (status: `pending`)

### Build Storyboard Tool

- [ ] Query `prod_assets WHERE event_number=X AND asset_type='visual_still' AND status='approved'`
- [ ] Extract file paths
- [ ] Query `prod_assets WHERE module_id=X AND asset_type='audio_mix' AND status='approved'`
- [ ] Build storyboard HTML using approved assets
- [ ] Register storyboard HTML in `prod_assets`

### Build Cropper Tool

- [ ] Query `prod_assets WHERE event_number=X AND tags contains 'master' AND status='approved'`
- [ ] Extract master still file_path and id
- [ ] Build cropper HTML
- [ ] Register cropper HTML in `prod_assets`
- [ ] After user saves crops, register each crop in `prod_assets` with `source_asset_id`

### Module JSON Builder Skill

- [ ] Query approved `data_phase_a_json` for this module
- [ ] Query approved `audio_stem` for this module
- [ ] Query approved `audio_cuepoint` for this module
- [ ] Query approved `data_personalization_map` for this module
- [ ] Combine into complete module JSON
- [ ] Register as `data_module_json` (status: `pending`)
- [ ] Open for Kim via Finder (JSON in text editor)
- [ ] Get verdict and update status

### Narrative Generator Skill

- [ ] Extract event metadata from skeleton
- [ ] Register as `narrative_metadata` (status: `pending`)
- [ ] Extract dialogue transcript from skeleton
- [ ] Register as `dialogue_transcript` (status: `pending`)
- [ ] Generate personalization variable map
- [ ] Register as `data_personalization_map` (status: `pending`)
- [ ] Open metadata for Kim review
- [ ] Get verdict and update all statuses

### Video Producer: Gameplay Assets

- [ ] Generate wand overlays via video compositing or design tool
- [ ] Register each overlay as `gameplay_overlay` (status: `pending`)
- [ ] Generate avatar variants
- [ ] Register each variant as `gameplay_avatar` (status: `pending`)
- [ ] Generate zone backgrounds
- [ ] Register each zone as `gameplay_zone` (status: `pending`)
- [ ] Open all visual gameplay assets for Kim review
- [ ] Get verdict and update all statuses to `approved`

---

**End of Checklist**

Print this and keep it handy while developing skills. When in doubt, refer to `ASSET_REGISTRY_WORKFLOW_v1.md`.
