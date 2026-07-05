# TECH_SPEC — Kling Real-Voice Harvest v1

**Marker:** `KLING_REAL_VOICE_HARVEST_V1`  
**Status:** Shipped  
**Script:** `Production/tools/scripts/kling_real_voice_harvest.py`  
**Audit:** `Production/Event_N/_kling_real_voice_harvest.jsonl`  
**Operator skill:** `.cursor/skills/kling-real-voice-harvest/SKILL.md`

---

## Problem

`still_insert` beats mux **ElevenLabs TTS** onto Ken Burns stills. Operator and kid-facing quality require **Omni Element native voice** (same bind as motion beats). Kling cannot animate a frozen still with Element voice directly — harvest uses a throwaway speak render and remuxes audio onto the approved visual.

## Authority

| Concept | Shape | Read gate | Write path |
|---------|-------|-----------|------------|
| **Harvest audit trail** | disk | `_kling_real_voice_harvest.jsonl` | `kling_real_voice_harvest._audit` |
| **Active clip after harvest** | disk | `kling_o3_video_path` + active option `source: kling_real_voice_harvest` | `import_delivery_clip_to_beat` |
| **TTS preview superseded** | explicit | `beat_active_clip_supersedes_tts_preview(beat)` | `apply_real_voice_harvest_beat_fields` on import |
| **Gallery visibility (still mode)** | derived | `o3_option_visible_in_ui_slots` / client `buildFixedO3OptionSlots` | normalize on session-state |

## Pipeline

```
Still+TTS clip (visual lock, tts_muxed ~4s)
        │
        ▼
O3 Element native speak (throwaway, ~8s)  ← harvest Kling job
        │
        ▼
ffmpeg remux: visual track + harvest audio (tpad if needed)
        │
        ▼
import_delivery_clip_to_beat (slot 2 default, make_active)
        │
        ▼
apply_real_voice_harvest_beat_fields
  • real_voice_harvest_active = true
  • audio_file → superseded_tts_audio_file (cleared from beat)
```

## Sidecar fields (preserve on merge)

- `real_voice_harvest_active`, `real_voice_harvest_at`
- `superseded_tts_audio_file`, `superseded_tts_audio_at`

## Gallery UX (still_insert mode)

Both clips remain visible:

| Slot | Source | Duration | Audio |
|------|--------|----------|-------|
| 0 | `still_insert_ken_burns` | ~4s | ElevenLabs TTS |
| 2 | `kling_real_voice_harvest` | ~8s | Omni embedded |

Active after harvest = harvest tile. Label: **Omni voice on still (harvest)**.

## Export / stitch

`resolve_beat_stitch_export_clip_path` uses active `kling_o3_video_path` (harvest delivery after import). **Send to Stitcher** required to update concatenated segment preview.

## Blast radius

| Area | Impact |
|------|--------|
| Beats never harvested | Unchanged — `audio_file` + TTS preview still work |
| Beats after harvest | `audio_file` cleared; ElevenLabs path preserved in `superseded_tts_audio_file` |
| Element-native beats | Never enter harvest path |
| Storyboard `production_state` beat audio | Unchanged (separate store); Beat Gen gallery is authoritative for O3 |

## Tests

- `Production/tools/tests/test_real_voice_harvest_durability.py`
- `Production/tools/tests/test_o3_pipeline_cross_contamination.py` (infer harvest = element_native)

## CI / durability

- `SIDECAR_MERGE_PRESERVE_FIELDS` includes harvest supersede fields
- Client gallery filter mirrors `o3_option_visible_in_ui_slots` for `kling_real_voice_harvest`
