# Arlo Phase A voice — canonical (Kim approved 2026-06-19)

## Reference stem (ground truth)

**File:** `phase_a_voice_stem_20260613-124825.mp3`  
**Event:** Event_1  
**Duration:** ~40.3s  
**Approved:** Kim screenshot audition in Apple Music, 2026-06-19

This stem is the canonical Arlo Phase A voice. Future regens must match these
settings — not the experimental 2026-06-19 “calmer” pass
(`phase_a_voice_stem_20260619-183109.mp3`, rejected).

## ElevenLabs / Directus settings

Arlo TTS resolves to **Directus `prod_voice_profiles` id=2** (`character_name: Chipper`).
`_resolve_voice_profile("Arlo")` maps to that row.

| Field | Canonical value |
|-------|-----------------|
| `elevenlabs_voice_id` | `7o9pyvsN0ob5GO6LBQp6` |
| `stability` | **0.25** |
| `similarity_boost` | **0.70** |
| `style` | **0.35** |
| `speed` | null (ElevenLabs default) |
| `model` | `eleven_v3` |

`production_server.py` `_PHASE_VOICE_CONFIG["a"].fallback_settings` mirrors the
same values for when Directus is unreachable.

## Restore canonical settings (Directus)

```bash
curl -s -X POST http://localhost:5111/api/voice/profile_update \
  -H 'Content-Type: application/json' \
  -d '{"id":2,"stability":0.25,"similarity_boost":0.70,"style":0.35}'
```

## Pin canonical stem in Event_1 state

```bash
MTIME=$(stat -f "%m" "$HOME/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/Event_1/phase_a_voice_stem_20260613-124825.mp3")
curl -s -X POST http://localhost:5111/api/v2/module/patch \
  -H 'Content-Type: application/json' \
  -d "{\"field\":\"phase_a_voice_stem_file\",\"value\":\"phase_a_voice_stem_20260613-124825.mp3\",\"scope_event_id\":\"Event_1\",\"scope_video_role\":\"intro\"}"
curl -s -X POST http://localhost:5111/api/v2/module/patch \
  -H 'Content-Type: application/json' \
  -d "{\"field\":\"phase_a_voice_stem_mtime\",\"value\":$MTIME,\"scope_event_id\":\"Event_1\",\"scope_video_role\":\"intro\"}"
```

## Related production assets

Stitched Phase A on disk from the same session (old voice, still valid until script changes):

- `phase_a_stitched_20260613-183709.mp4` (~39s)

After script edits, regen stem with canonical settings above, then re-lipsync + re-stitch.
