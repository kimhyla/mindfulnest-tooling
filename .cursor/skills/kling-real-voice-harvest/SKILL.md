---
name: kling-real-voice-harvest
description: >-
  Run KLING_REAL_VOICE_HARVEST_V1 — port Omni Element native voice onto still+TTS
  beats. Use when Kim says "real voice harvest", "port Omni voice onto still",
  "TTS still needs Benson/Ember voice", "KLING_REAL_VOICE_HARVEST", or container
  beat needs character real voice instead of ElevenLabs.
---

# Kling real-voice harvest (still_insert → Omni voice)

Kim does **not** run terminal. Agent runs harvest, verifies audit, confirms gallery + stitch.

**Code:** `Production/tools/scripts/kling_real_voice_harvest.py`  
**Spec:** `Production/docs/TECH_SPEC_KLING_REAL_VOICE_HARVEST_V1.md`  
**Audit:** `Production/Event_N/_kling_real_voice_harvest.jsonl`

## Two-phase still_insert pipeline

| Phase | Operator action | Result |
|-------|-----------------|--------|
| **1 — Visual lock** | Generate **Still + TTS** (Ken Burns) | ~4s clip, ElevenLabs muxed, visual approved |
| **2 — Voice swap** | Agent runs **real-voice harvest** | Same visual, ~8s, Omni Element voice active |

Do **not** auto-run phase 2 on Generate — Kim locks picture first (~3 min Kling cost per harvest).

## Prerequisites (fail closed)

- Beat is `still_insert` / `beat_render_mode: still_insert`
- Active or candidate visual clip exists (`kling_o3_video_path` or `tts_muxed` option)
- Speaker has **active Element + bound voice** in `character_subjects.json`
- Char ref + bg ref locked on beat
- Event server running on dedicated port (see table below)

## One-step command

```bash
MN_BEATGEN_DB_PATH=~/.mindfulnest/state/beatgen_eventN.db \
MN_O3_EVENT_DIR=~/Library/CloudStorage/Dropbox/Claude\ Mindfulnest\ Project\ Files/Production/Event_N \
python3 Production/tools/scripts/kling_real_voice_harvest.py \
  --beat-id bg_arc1_eventN_<segment>_beat_XX
```

| Event | DB | Port |
|-------|-----|------|
| Event_5 | `beatgen_event5.db` | `:5115` |
| Event_4 | `beatgen_event4.db` | `:5114` |
| Event_3 | `beatgen_event3.db` | `:5113` |
| Event_2 | `beatgen_event2.db` | `:5112` |
| Event_1 | `beatgen_event1.db` | `:5111` |

**Flags:** `--dry-run` first on new beats · `--force` re-harvest · `--import-only PATH` skip O3 when remux already exists · `--slot 2` (default) · `--no-make-active` import without selecting

## Agent checklist (every run)

```
Harvest progress:
- [ ] 1. Dry-run or confirm `_needs_harvest` reason in audit
- [ ] 2. Run harvest (pinned MN_BEATGEN_DB_PATH + MN_O3_EVENT_DIR)
- [ ] 3. Audit: START → O3_SUBMIT → HARVEST_DONE → REMUX_DONE → IMPORTED
- [ ] 4. Sidecar: active = `kling_real_voice_harvest`, `real_voice_harvest_active: true`
- [ ] 5. Duration: active clip ~8s (not ~4s TTS)
- [ ] 6. Gallery: harvest tile labeled "Omni voice on still (harvest)" — not slot 0 TTS
- [ ] 7. Stitch: Send to Stitcher for segment if Kim listens in container preview
- [ ] 8. Tell Kim hard-refresh Beat Gen port; no terminal steps for her
```

## Verification commands (agent)

```bash
# Audit tail
tail -5 "…/Production/Event_N/_kling_real_voice_harvest.jsonl"

# Beat row (SQLite)
sqlite3 ~/.mindfulnest/state/beatgen_eventN.db \
  "SELECT json_extract(beat_json,'$.kling_o3_video_path'), \
          json_extract(beat_json,'$.real_voice_harvest_active'), \
          json_extract(beat_json,'$.audio_file') \
   FROM beats WHERE beat_id='…';"

# Duration sanity
ffprobe -v error -show_entries format=duration -of csv=p=0 \
  "…/kling_o3_clips/<beat>_g1_delivery.mp4"
```

Re-select active clip if needed:

```bash
curl -s -X POST "http://localhost:PORT/api/bg/select-o3-video" \
  -H 'Content-Type: application/json' \
  -d '{"beat_id":"…","option_key":"…","scope_event_id":"Event_N","scope_video_role":"resolution"}'
```

## What harvest does (do not reimplement)

1. Throwaway **Kling O3 Element native** speak render (Omni voice)
2. **Remux** harvest audio onto approved still visual (hold last frame if audio longer)
3. **Import** as gallery slot (`source: kling_real_voice_harvest`, `audio_contract: embedded_voice`)
4. **Supersede** ElevenLabs `audio_file` → `superseded_tts_audio_file` (preview truth)

## Do not use for verification

| Path | Why wrong |
|------|-----------|
| Storyboard **Audio** preview button | Streams ElevenLabs `audio_file` / production_state |
| **Magic still + TTS** preview | Muxes separate `/api/beat/audio/` over silent still |
| Gallery **slot 0** "Still + TTS" | Old ~4s ElevenLabs mux — harvest is separate tile |

**Correct listen path:** selected gallery tile with embedded voice (~8s).

## Failure modes

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Sounds like old voice, ~4s | Playing TTS slot 0 | Select harvest tile; hard refresh |
| Audit SKIP | Already element-native active | `--force` if re-harvest needed |
| O3_FAILED | Element/voice/char ref | Fix ref + voice bind; check server logs |
| Container unchanged | Stitch not re-sent | Send to Stitcher for segment |
| Wrong event beat | DB/env mismatch | Pin correct `MN_BEATGEN_DB_PATH` + `MN_O3_EVENT_DIR` |

## Deploy note

Script + gallery filter + import metadata live in **mindfulnest-tooling**. After Python/JS changes: deploy storyboard for target event + restart server. Kim hard-refreshes Beat Gen.

## Related

- `.cursor/rules/kling-real-voice-harvest.mdc` — trigger rule
- `.cursor/rules/kling-element-voice-alignment.mdc` — Element + voice bind law
- `restore-beats` skill — snapshot recovery if sidecar corrupted
