# Voice reliability V1 — tagged create-voice + proven binds

**Status:** active  
**Last updated:** 2026-06-27  
**Related:** `BEAT_GEN_CHARACTER_ONBOARDING_v1.md`, `TECH_SPEC_BEATGEN_TRUTH_STACK_V1.md`

---

## Problem class

Layer 1 (O3 delivery lock) was shipping; Layer 2 (tagged ElevenLabs → Kling create-voice) was incomplete on active cast. Result: beat-to-beat robotic reads and accent drift despite correct `voice_id` in submit logs.

**Bramble beat 1 vs beat 3:** same bind — provider lottery; operator keeps current speed/voice; redo beat 1 only.

---

## Category fix

| Layer | Fix |
|-------|-----|
| **Registry** | `sync_roster_voice_sample_tags.py` — tagged `element_sample_lines` + lock fingerprint from `DEFAULT_ELEMENT_SAMPLE_LINES` |
| **Roster** | Arlo guide speed aligned to lock (`1.15`) |
| **Refresh** | `--refresh-voice` for chars whose sample text changed (not Bramble; not Arlo proven bind) |
| **Proven pin** | `proven_o3_bind` on Oliver from Event_4 beat 2 golden stack |
| **Beat Gen delete** | `delete_beat_locked` — targeted SQLite DELETE |
| **Stitch hydrate** | `stitchSlotServerArtifactReady` + purge on cleared artifacts |

---

## Operator commands

```bash
cd Production
python3 scripts/sync_roster_voice_sample_tags.py          # tag sync all active
doppler run -- python3 scripts/setup_all_kling_character_voices.py \
  --char Oliver --refresh-voice --confirm-voice-overwrite
```

Skip: **Bramble** (keep-as-is), **Arlo** (proven bind — tag sync only).

---

## Gates

- `verify_character_voice_onboarding_contract.sh`
- `sync_roster_voice_sample_tags.py` + pytest voice onboarding
- `test_stitch_slot_artifact_freshness.py`
- `test_delete_beat_locked_sqlite`

---

## Acceptance

- [ ] All active roster (except Bramble waiver) pass `validate_voice_onboarding_before_spend`
- [ ] Refreshed chars have new `kling_voice_samples/*.mp3` on disk
- [ ] Oliver `proven_o3_bind` matches beat 2 element+voice
- [ ] Beat Gen delete succeeds under SQLite
- [ ] Stitcher no 404 mux after load_job artifact clear
