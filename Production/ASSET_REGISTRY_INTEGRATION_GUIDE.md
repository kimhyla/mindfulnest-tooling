# Asset Registry Integration Guide

**For:** Production Architects, Skill Developers, and Tool Builders  
**Date:** April 13, 2026  
**Purpose:** How to integrate the unified asset registry into existing production workflows

---

## Overview

The **Asset Registry** (Directus `prod_assets` collection) solves a critical production workflow problem: **asset chaos**. Before this, assets (stills, audio, video, scripts, HTML tools) lived scattered across folders with ambiguous names. Now they're tracked centrally with status, approval state, and lineage.

This guide helps you:
1. Understand what changed
2. Update your skill/tool to use the registry
3. Follow the new query-first workflow
4. Avoid old pitfalls (guessing filenames, losing track of what's approved)

---

## What Changed: The Old Way vs. New Way

### Old Workflow (Before Asset Registry)

```
Generate Voice Stem
  ↓
[Save to Production/Event_1/m1_voice_stem_v3.mp3]
  ↓
[Ask Kim to review — manually find file in Finder]
  ↓
[Kim approves — update status HOW? No system for this]
  ↓
[Next step: Hope the filename hasn't changed — just hardcode "m1_voice_stem_v3.mp3"]
  ↓
[If you need the final mix file path later, grep the codebase or ask Kim where it is]
```

**Problems:**
- No record that Kim approved anything
- If you generate a new version, you lose track of which is "current"
- Tools (storyboard builder, audio mixer) hardcode filenames and break if names change
- Impossible to query "what audio assets do I have for M1?"
- If production is interrupted, no way to resume — what was the last thing that happened?

### New Workflow (With Asset Registry)

```
Generate Voice Stem
  ↓
[Save to Production/Event_1/m1_voice_stem_v3.mp3]
  ↓
[POST to prod_assets immediately — get asset_id back, status='pending']
  ↓
[Query asset_id to get file_path, open via Finder for Kim]
  ↓
[Kim approves — PATCH prod_assets to status='approved']
  ↓
[Log to prod_activity_log — module state is now traceable]
  ↓
[Next step: Query prod_assets WHERE module_id=1 AND asset_type='audio_stem' AND status='approved']
  ↓
[Got the right file automatically — proceed to mixing]
```

**Benefits:**
- Every asset has an audit trail (created, reviewed, approved, when)
- Multiple versions of the same asset can coexist; status determines which is "current"
- Tools query the registry instead of guessing filenames
- Resumable sessions — know exactly where you left off
- Lineage tracking — crops link to masters, clips link to stills, etc.

---

## Integration Checklist for Developers

### Phase 1: Understand the Schema

Read these in order:
1. ✅ `ASSET_REGISTRY_WORKFLOW_v1.md` — The master spec
2. ✅ `ASSET_REGISTRY_SKILL_CHECKLIST.md` — Quick patterns for skills
3. ✅ This document — Integration guide

Skim these for reference:
- `dashboard-ops/SKILL.md` — Directus API patterns
- `audio-producer/SKILL.md` — Example skill using registry (partially implemented)
- `video-producer/SKILL.md` — Example skill for visual assets

### Phase 2: Update Your Skill/Tool

For **each asset type** your skill creates:

| Asset Type | Register As | Example |
|-----------|------------|---------|
| TTS voice stem | `audio_stem` | Audio producer generates → POST to prod_assets |
| Ambient music bed | `audio_bed` | Audio producer sources → POST to prod_assets |
| FLUX still | `visual_still` | Video producer generates → POST to prod_assets |
| 4:3 crop | `visual_crop` | Cropper tool saves → POST to prod_assets (with source_asset_id) |
| Seedance clip | `video_clip` | Video producer generates → POST to prod_assets |
| Final assembled video | `video_assembled` | Video producer ffmpeg → POST to prod_assets |
| Phase B script | `script_phase_b` | phase-b-writer generates → POST to prod_assets |
| Storyboard HTML | `html_storyboard` | build_storyboard.py → POST to prod_assets |
| Cropper HTML | `html_cropper` | build_cropper.py → POST to prod_assets |

For **each asset type** your skill **uses**:

| Asset Type | Query Pattern | Example |
|-----------|--------------|---------|
| Voice stem to mix | `WHERE module_id=X AND asset_type='audio_stem' AND status='approved'` | Audio mixer queries for approved stem |
| Stills for storyboard | `WHERE event_number=X AND asset_type='visual_still' AND status='approved'` | Storyboard builder queries for approved stills |
| Master still to crop | `WHERE event_number=X AND tags contains 'master' AND status='approved'` | Cropper tool queries for reference master |

### Phase 3: Test Locally

1. Generate an asset (e.g., test voice stem)
2. Register it with POST to `prod_assets` (use dashboard-ops skill)
3. Verify it appears in dashboard with `status='pending'`
4. Update status to `approved` (simulate Kim approval)
5. Query it back with the new query pattern
6. Verify the file path is correct

### Phase 4: Deploy

When your skill is ready:
1. Update documentation to reference `ASSET_REGISTRY_WORKFLOW_v1.md`
2. Add registry query/registration code to the skill
3. Test end-to-end with Kim
4. Log the change to `prod_activity_log` for audit

---

## Common Integration Patterns

### Pattern 1: "I Generate an Asset, Kim Reviews It"

**Code structure:**

```python
# Step 1: Generate asset (TTS, FLUX, ffmpeg, etc.)
asset_file = generate_audio_stem(script, voice_settings)

# Step 2: Register immediately
asset_id = register_asset(
    module_id=module_id,
    event_number=event_num,
    asset_type="audio_stem",
    asset_name="M1 Voice Stem v3",
    file_path="Production/Event_1/m1_voice_stem_v3.mp3",
    metadata={"audio": {"duration": 145, "voice_id": "oR4..."}},
    status="pending"
)

# Step 3: Open for Kim via Finder
mac_path = construct_mac_path("Production/Event_1/m1_voice_stem_v3.mp3")
open_file_in_app(mac_path, app="QuickTime Player")

# Step 4: Get Kim's verdict
verdict = ask_kim("Is this voice stem approved?")
# Possible: "approved", "rejected", "too slow — try v4"

# Step 5: Update asset status
if verdict == "approved":
    update_asset_status(asset_id, status="approved", kim_verdict="approved")
elif verdict == "rejected":
    update_asset_status(asset_id, status="rejected", kim_feedback=verdict)
else:
    update_asset_status(asset_id, status="in_review", kim_feedback=verdict)
    # Generate new version and loop back to Step 1

# Step 6: Proceed to next step (if approved)
if verdict == "approved":
    proceed_to_mixing(asset_id)  # Pass asset_id, not filename
```

### Pattern 2: "I Need an Approved Asset to Start My Work"

**Code structure:**

```python
# ALWAYS query first — never hardcode filenames
required_asset = query_assets(
    module_id=module_id,
    asset_type="audio_stem",
    status="approved"
)

if not required_asset:
    error("No approved voice stem for this module. Cannot proceed.")
    print("Ask Kim whether to:")
    print("  1. Generate a new voice stem")
    print("  2. Approve an existing pending version")
    print("  3. Provide a different module to work on")
    exit(1)

# Extract file path from registry
voice_stem_path = required_asset["file_path"]
mac_path = construct_mac_path(voice_stem_path)

# Use in your work (ffmpeg mix, etc.)
ffmpeg_command = f'ffmpeg -i "{mac_path}" -i ambient_bed.mp3 ...'
subprocess.run(ffmpeg_command, shell=True)
```

### Pattern 3: "I Create an Asset Derived From Another"

**Code structure:**

```python
# Query the parent/source asset
master_still = query_assets(
    event_number=event_num,
    asset_type="visual_still",
    status="approved",
    tags="contains:master"
)

master_id = master_still["id"]
master_path = construct_mac_path(master_still["file_path"])

# Create derivative (e.g., crop)
crop_file = crop_image(master_path, aspect_ratio="4:3")

# Register the crop WITH lineage
register_asset(
    module_id=module_id,
    event_number=event_num,
    asset_type="visual_crop",
    asset_name="Tessa Opening — 4:3 Crop",
    file_path=crop_file,
    source_asset_id=master_id,  # MANDATORY — links back to master
    metadata={"visual": {"aspect_ratio": "4:3", "source_master": master_id}},
    tags=["crop", "4:3", "ready_for_storyboard"]
)
```

---

## Migration Path: Updating Existing Skills

### Step 1: Identify Assets Your Skill Creates/Uses

**Example: audio-producer skill**

**Creates:**
- Voice stem (via ElevenLabs) → register as `audio_stem`
- Cue point map (via Vosk) → register as `audio_cuepoint`
- Final mix (via ffmpeg) → register as `audio_mix`

**Uses:**
- Approved voice stem (to verify it exists before mixing)
- Approved ambient bed (query before mixing)

### Step 2: Add Registration Calls

**Before:**
```python
# Generate voice stem
voice_stem = elevenlabs_tts(script, voice_settings)
# Save to disk
save_file(voice_stem, "Production/Event_1/m1_voice_stem_v3.mp3")
# Ask Kim to review (somehow)
kim_review = open_file_somehow()
```

**After:**
```python
# Generate voice stem
voice_stem = elevenlabs_tts(script, voice_settings)

# Save to disk
file_path = "Production/Event_1/m1_voice_stem_v3.mp3"
save_file(voice_stem, file_path)

# Register IMMEDIATELY
asset_id = register_asset(
    module_id=1,
    event_number=1,
    asset_type="audio_stem",
    asset_name="M1 Voice Stem v3",
    file_path=file_path,
    metadata={"audio": {"duration": 145, "voice_id": "oR4..."}},
    status="pending"
)

# Ask Kim to review (using registered asset)
mac_path = construct_mac_path(file_path)
open_file_in_app(mac_path, "QuickTime Player")
```

### Step 3: Replace Hardcoded File Paths With Queries

**Before:**
```python
# Hardcoded guess
voice_stem_file = "Production/Event_1/m1_voice_stem_v3.mp3"
# Hope this exists and is the right one!
ffmpeg_mix(voice_stem_file, ambient_bed, output)
```

**After:**
```python
# Query the registry
voice_stem = query_assets(
    module_id=1,
    asset_type="audio_stem",
    status="approved"
)

if not voice_stem:
    error("No approved voice stem. Ask Kim.")
    exit(1)

voice_stem_file = construct_mac_path(voice_stem["file_path"])
ffmpeg_mix(voice_stem_file, ambient_bed, output)
```

### Step 4: Add Logging

After every significant action:

```python
# Log to prod_activity_log
log_activity(
    module_id=module_id,
    action="Registered voice stem v3 and opened for Kim pacing review",
    details={
        "asset_id": asset_id,
        "asset_type": "audio_stem",
        "status": "pending"
    }
)
```

---

## Integration Patterns for New Pipeline Stages

### Module JSON Builder Integration

**What it does:** Combines approved assets (Phase A config, voice stems, cue points, personalization map) into a complete runtime module JSON.

**Integration pattern:**

```python
# Step 1: Query all required upstream assets
phase_a = query_assets(
    module_id=module_id,
    asset_type="data_phase_a_json",
    status="approved"
)
voice_stem = query_assets(
    module_id=module_id,
    asset_type="audio_stem",
    status="approved"
)
cuepoints = query_assets(
    module_id=module_id,
    asset_type="audio_cuepoint",
    status="approved"
)
personalization = query_assets(
    module_id=module_id,
    asset_type="data_personalization_map",
    status="approved"
)

# Check all are present
if not all([phase_a, voice_stem, cuepoints, personalization]):
    error("Missing required assets for module JSON building")
    exit(1)

# Step 2: Read the JSON files from disk
phase_a_config = json.load(construct_mac_path(phase_a["file_path"]))
personalization_vars = json.load(construct_mac_path(personalization["file_path"]))

# Step 3: Combine into complete module JSON
module_json = {
    "module_id": module_id,
    "phase_a_config": phase_a_config,
    "audio_settings": {
        "voice_stem_path": voice_stem["file_path"],
        "cuepoints_path": cuepoints["file_path"]
    },
    "personalization": personalization_vars,
    "schema_version": "2.0"
}

# Step 4: Save and register
output_path = f"Production/Event_{event_num}/modules/module_complete_v1.json"
save_json(module_json, output_path)

asset_id = register_asset(
    module_id=module_id,
    event_number=event_num,
    asset_type="data_module_json",
    asset_name="Complete Module JSON",
    file_path=output_path,
    status="pending",
    metadata={"data": {"schema_version": "2.0"}}
)

# Step 5: Open for Kim review
mac_path = construct_mac_path(output_path)
open_file_in_app(mac_path, "Visual Studio Code")

# Step 6: Get verdict and update
verdict = ask_kim("Is the module JSON correct?")
if verdict == "approved":
    update_asset_status(asset_id, status="approved")
```

### Narrative Generator Integration

**What it does:** Extracts narrative metadata and dialogue from the arc skeleton, generates personalization variable maps, and registers all as assets.

**Integration pattern:**

```python
# Step 1: Extract from skeleton .docx
skeleton_path = construct_mac_path("ARC_1_SKELETON_DRAFT.docx")
skeleton_data = extract_from_skeleton(skeleton_path)

# Step 2: Generate event metadata
event_metadata = {
    "event_number": 1,
    "creatures_featured": skeleton_data.creatures,
    "spell_taught": skeleton_data.spell_name,
    "technique_clinical_name": skeleton_data.technique,
    "domain_taught": skeleton_data.domain,
    "stone_introduced": skeleton_data.stone_name,
    "story_beats_count": len(skeleton_data.beats)
}

# Register metadata
metadata_id = register_asset(
    event_number=1,
    asset_type="narrative_metadata",
    asset_name=f"Event 1 Metadata",
    file_path="Production/Event_1/metadata/event_1_metadata_v1.json",
    status="pending",
    metadata={"narrative": event_metadata}
)

# Step 3: Extract dialogue transcript
dialogue_transcript = {
    "dialogue_lines": skeleton_data.dialogue,
    "speakers": skeleton_data.characters,
    "locked_lines": len(skeleton_data.dialogue)
}

# Register transcript
transcript_id = register_asset(
    event_number=1,
    asset_type="dialogue_transcript",
    asset_name=f"Event 1 Dialogue Transcript",
    file_path="Production/Event_1/dialogue/event_1_dialogue_locked_v1.json",
    status="pending"
)

# Step 4: Generate personalization variable map
personalization_map = {
    "variables": {
        "childName": {"required": True, "type": "string", "usage_count": 12},
        "childPronoun": {"required": True, "type": "enum", "usage_count": 8},
        "chosenGuideName": {"required": True, "type": "string", "usage_count": 4}
    },
    "total_personalization_locations": 24
}

# Register map
map_id = register_asset(
    module_id=1,
    event_number=1,
    asset_type="data_personalization_map",
    asset_name="M1 Personalization Variables Map",
    file_path="Production/Event_1/maps/m1_personalization_vars_v1.json",
    status="pending"
)

# Step 5: Open all for Kim review
for asset_id, filename in [(metadata_id, "metadata"), (transcript_id, "dialogue"), (map_id, "map")]:
    asset = query_assets(asset_id)
    open_file_in_app(construct_mac_path(asset["file_path"]), "Visual Studio Code")

# Step 6: Get verdict and update
verdict = ask_kim("Are the narrative assets correct?")
if verdict == "approved":
    for asset_id in [metadata_id, transcript_id, map_id]:
        update_asset_status(asset_id, status="approved")
```

### Video Producer: Gameplay Assets Integration

**What it does:** Generates and registers wand overlays, avatar variants, and zone backgrounds.

**Integration pattern:**

```python
# Step 1: Generate wand overlays
for spell in ["Magic Hands", "Breath-Squeezers", "Humming"]:
    overlay_file = generate_wand_overlay(spell, style="warm_glow")
    
    register_asset(
        module_id=module_id,
        event_number=event_num,
        asset_type="gameplay_overlay",
        asset_name=f"{spell} Wand Overlay",
        file_path=overlay_file,
        status="pending",
        metadata={"gameplay": {"overlay_type": "wand", "applies_to_spell": spell}},
        tags=["wand", "overlay", spell]
    )

# Step 2: Generate avatar variants
for expression in ["neutral", "proud", "calm", "curious"]:
    avatar_file = generate_avatar_variant(expression)
    
    register_asset(
        module_id=module_id,
        asset_type="gameplay_avatar",
        asset_name=f"Child Avatar — {expression} Expression",
        file_path=avatar_file,
        status="pending",
        metadata={"gameplay": {"avatar_variant_type": "expression", "variant_key": expression}},
        tags=["avatar", "expression", expression]
    )

# Step 3: Generate zone backgrounds
for zone in ["everdale_forest", "mountain_kingdom", "heartwood"]:
    zone_file = generate_zone_background(zone, variant="day")
    
    register_asset(
        module_id=module_id,
        event_number=event_num,
        asset_type="gameplay_zone",
        asset_name=f"{zone.title()} — Day Variant",
        file_path=zone_file,
        status="pending",
        metadata={"gameplay": {"zone_type": "environment_background", "zone_name": zone}},
        tags=["zone", zone, "background"]
    )

# Step 4: Open all for Kim review
all_gameplay = query_assets(module_id=module_id, asset_type="gameplay_overlay|gameplay_avatar|gameplay_zone", status="pending")
for asset in all_gameplay:
    open_file_in_app(construct_mac_path(asset["file_path"]), "Preview")

# Step 5: Get verdict and update
verdict = ask_kim("Are all gameplay assets correct?")
if verdict == "approved":
    for asset in all_gameplay:
        update_asset_status(asset["id"], status="approved")
```

---

## Tools That Benefit Most From Registry

### 1. build_storyboard.py

**Before:** Hardcoded image filenames, missing audio

**After:** Query approved stills + audio, build storyboard with guaranteed correct assets

```python
# Query approved assets
stills = query_assets(event_number=1, asset_type="visual_still", status="approved")
audio = query_assets(module_id=1, asset_type="audio_mix", status="approved")

if not audio:
    exit("No approved audio for this module")

# Build storyboard
build_storyboard(
    stills=[s["file_path"] for s in stills],
    audio=audio["file_path"],
    output="event_1_storyboard.html"
)

# Register the HTML
register_asset(
    event_number=1,
    asset_type="html_storyboard",
    asset_name="Event 1 Full Storyboard",
    file_path="Production/Event_1/event_1_storyboard.html",
    status="pending"
)
```

### 2. build_cropper.py

**Before:** Hardcoded "m1_tessa_sad.png", no lineage tracking

**After:** Query for master still, save crops with lineage

```python
# Query for master still
master = query_assets(event_number=1, tags="contains:master", status="approved")

if not master:
    exit("No master still found")

master_file = construct_mac_path(master["file_path"])
master_id = master["id"]

# Build cropper
crop_files = build_cropper(master_file, aspect_ratios=["4:3", "16:9"])

# Register each crop with lineage
for crop_file, aspect in zip(crop_files, ["4:3", "16:9"]):
    register_asset(
        event_number=1,
        asset_type="visual_crop",
        asset_name=f"Tessa Opening — {aspect} Crop",
        file_path=crop_file,
        source_asset_id=master_id,  # Links back to master
        tags=["crop", aspect]
    )
```

---

## Troubleshooting Integration

### "I'm not sure if my skill needs to use the registry"

**Ask yourself:**
1. Does my skill CREATE any files? → Register them
2. Does my skill USE any files? → Query for them (don't hardcode paths)
3. Do I ask Kim to review anything? → Use computer-use to open files from registry

If the answer to any question is "yes," you need the registry.

### "How do I handle API failures when registering assets?"

The dashboard-ops skill has retry logic built in. When you call `register_asset()`, it handles:
- Token expiration (re-authenticates)
- Network timeouts (retries with backoff)
- Invalid enum values (validates before posting)

If registration still fails:
1. Log the failure to `prod_activity_log`
2. Mark the module as `blocked` with the error
3. Ask Kim to investigate

### "What if an asset already exists in prod_assets but isn't registered properly?"

You can retroactively register it:

```python
register_asset(
    module_id=1,
    event_number=1,
    asset_type="audio_stem",
    asset_name="M1 Voice Stem v5 (Existing — retroactive)",
    file_path="Production/Event_1/m1_voice_stem_v5.mp3",
    created_by="kim",  # If Kim created it directly
    status="approved",  # Assume approved unless Kim says otherwise
    notes="Retroactively registered April 13 — existing file, verified working"
)
```

---

## Success Criteria: How to Know Integration Is Working

After integrating the asset registry into your skill:

- ✅ Every file your skill creates is registered with `status='pending'` before proceeding
- ✅ Every query for a required asset uses the dashboard, not hardcoded paths
- ✅ Kim reviews files via Finder (opened by computer-use), not told paths
- ✅ Asset status updates are logged to `prod_activity_log`
- ✅ If an asset is missing or not approved, your skill stops and asks Kim (doesn't guess)
- ✅ Derivative assets (crops from masters, clips from stills) have `source_asset_id` set
- ✅ Session resumption works: If interrupted and restarted, your skill checks `prod_assets` to see what's pending/approved

---

## Query Patterns for New Asset Types

### Getting All Data Assets for a Module

```bash
# Query all data configuration assets for module M1
curl -s "$BASE/items/prod_assets?filter[module_id][_eq]=1&filter[asset_type][_in]=data_phase_a_json,data_module_json,data_breathcycle,data_personalization_map,data_technique_data&filter[status][_eq]=approved" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {asset_type, asset_name, file_path}'
```

### Getting Voice Profiles

```bash
# Get Tessa's voice profile
curl -s "$BASE/items/prod_assets?filter[asset_type][_eq]=voice_profile&filter[metadata][voice][creature_name][_eq]=Tessa&filter[status][_eq]=approved" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[0]'

# Get all locked voice profiles
curl -s "$BASE/items/prod_assets?filter[asset_type][_eq]=voice_profile&filter[status][_eq]=approved" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {asset_name, metadata.voice.creature_name, metadata.voice.stability}'
```

### Getting Narrative Assets

```bash
# Get all narrative metadata and dialogue for Event 1
curl -s "$BASE/items/prod_assets?filter[event_number][_eq]=1&filter[asset_type][_in]=narrative_metadata,dialogue_transcript&filter[status][_eq]=approved" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {asset_type, asset_name}'

# Get personalization variables for building module JSON
curl -s "$BASE/items/prod_assets?filter[module_id][_eq]=1&filter[asset_type][_eq]=data_personalization_map&filter[status][_eq]=approved" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[0] | .file_path'
```

### Getting Gameplay Assets for a Module

```bash
# Get all approved gameplay assets for M1
curl -s "$BASE/items/prod_assets?filter[module_id][_eq]=1&filter[asset_type][_in]=gameplay_overlay,gameplay_avatar,gameplay_zone&filter[status][_eq]=approved" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {asset_type, asset_name, file_path}'

# Get all wand overlays
curl -s "$BASE/items/prod_assets?filter[asset_type][_eq]=gameplay_overlay&filter[tags][_contains]=wand&filter[status][_eq]=approved" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {asset_name, metadata.gameplay.applies_to_spell}'
```

---

## References

| Document | Purpose |
|----------|---------|
| `ASSET_REGISTRY_WORKFLOW_v1.md` | Complete specification (read first) |
| `ASSET_REGISTRY_SKILL_CHECKLIST.md` | Quick patterns for skill developers |
| `dashboard-ops/SKILL.md` | Directus API patterns for registration/queries |
| `audio-producer/SKILL.md` | Example of partially-integrated skill |
| `CLAUDE.md` → "File Location and Format Rule" | Dropbox path structure for Mac |

---

**Ready to integrate?**

1. Read `ASSET_REGISTRY_WORKFLOW_v1.md` (15 min)
2. Pick your skill from the Integration Checklist above
3. Follow the migration path for your asset types
4. Test with Kim
5. Update skill documentation to reference the registry

Questions? Refer back to the spec or ask Kim.

---

**End of Integration Guide**
