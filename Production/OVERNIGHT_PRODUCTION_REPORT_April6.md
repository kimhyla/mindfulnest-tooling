# Overnight Production Report — April 6, 2026

## Summary

**191 TTS audio files generated** across all Arc 1 narrative events (Events 0–7, map sprites, tomorrow hooks). Zero failures. Full video pipeline tested end-to-end: Tessa image → Seedance 1.5 Pro → ByteDance LipSync. Pipeline works.

---

## TTS Audio Generation — COMPLETE

All 191 dialogue lines from `ARC_1_DIALOGUE_EXTRACTION_TTS_v1.md` (plus skeleton resolution lines) rendered via ElevenLabs API using the locked voice roster.

### Files by Event

| Event | Scene | Files | Characters |
|-------|-------|-------|------------|
| 0 | Opening Storybook | 7 | Myrrhin |
| 0b | Guide Bird Introduction | 13 | Guide Bird |
| 0c | Map Landing | 1 | Guide Bird |
| 1 | Tessa Intro | 7 | Guide Bird, Tessa |
| 1 | Tessa Resolution | 2 | Tessa |
| 1 | Map Sprites | 2 | Tessa, Guide Bird |
| 1 | Tomorrow Hook | 1 | Guide Bird |
| 2 | Luna Intro | 11 | Luna, Tessa, Guide Bird |
| 2 | Luna Resolution | 3 | Luna |
| 2 | Map Sprites + Hook | 2 | Luna, Guide Bird |
| 3 | Ember Intro | 16 | Ember, Tessa, Luna, Guide Bird |
| 3 | Ember Resolution | 1 | Guide Bird |
| 3 | Map Sprites + Hook | 4 | Tessa, Luna, Ember, Guide Bird |
| 3b | Oliver Meet | 10 | Oliver, Luna, Guide Bird |
| 3b | Map Sprites + Hook | 5 | Oliver, Tessa, Luna, Ember, Guide Bird |
| 4 | Bramble Intro | 29 | Bramble, Oliver, Ember, Tessa, Luna, Guide Bird |
| 4 | Bramble Resolution | 4 | Bramble, Luna, Ember |
| 4 | Map Sprites + Hooks | 9 | Bramble, Luna, Oliver, Tessa, Ember, Guide Bird |
| 5 | Benson Intro | 11 | Oliver, Benson, Bramble, Luna, Tessa, Guide Bird |
| 5 | Benson Resolution | 7 | Benson, Bramble, Tessa, Oliver |
| 5 | Map Sprites + Hook | 3 | Benson, Luna, Guide Bird |
| 6 | Bork Intro | 21 | Bork, Benson, Luna, Guide Bird |
| 6 | Map Sprites + Hooks | 11 | Bork, Luna, Oliver, Tessa, Ember, Bramble, Benson, Guide Bird |
| 7 | Agent Encounter | 11 | Grizzle, Ember, Luna, Bramble |
| **TOTAL** | | **191** | **10 characters** |

### Location
All audio files: `video_pipeline/audio/arc_1/` organized by event subfolder.

### Personalization Notes
Lines containing `{childName}`, `{chosenGuideName}`, `{therapistName}`, etc. were generated with template placeholder text and have `_TEMPLATE` suffix. These are the universal-render versions. Per-child versions will be generated at runtime with actual variable values.

---

## Video Pipeline Test — PASS

### Test Run
- **Input image:** `tessa1.png` (2048×2048 PNG)
- **Input audio:** M1 intro line 2 — "Oh... Hi... I'm sorry. I'm Tessa. I'm a turtle. It's not my best day." (96 KB MP3)

### Stage 1: Seedance 1.5 Pro (Image → Video)
- **API:** `api.wavespeed.ai/api/v3/bytedance/seedance-v1.5-pro/image-to-video`
- **Status:** Completed in ~68 seconds
- **Output:** `videos/tessa_seedance_test.mp4` (4.5 MB)
- **Prompt used:** "A gentle young turtle character looking up with a mix of sadness and hope, blinking slowly, slight head movement, subtle breathing animation. Soft lighting, fantasy forest background."

### Stage 2: ByteDance LipSync (Video + Audio → Lip-Synced Video)
- **API:** `api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video`
- **Status:** Completed in ~60 seconds
- **Output:** `videos/tessa_lipsync_test.mp4` (900 KB)

### Pipeline Assessment
Both stages worked without errors. Total pipeline time: ~2 minutes per scene. File hosting via uguu.se (temporary URLs for API inputs).

---

## What Kim Should Review

1. **Listen to the voice quality** — spot-check a few files per character:
   - Myrrhin: `event_0_storybook/01_myrrhin_long_ago.mp3` (narrator warmth)
   - Guide Bird: `event_0b_guidebird_intro/02_guidebird_finally_TEMPLATE.mp3` (energy, personality)
   - Tessa: `event_1_tessa_intro/04_tessa_i_fell.mp3` (vulnerability)
   - Luna: `event_2_luna_intro/04_luna_mindfulnest.mp3` (excitable energy)
   - Bramble: `event_4_bramble_intro/19_bramble_dead_quiet.mp3` (Irish accent)
   - Bork: `event_6_bork_intro/12_bork_do_not_play.mp3` (British pompousness)
   - Oliver: `event_3b_oliver_meet/03_oliver_im_oliver.mp3` (earnest emotion)
   - Benson: `event_5_benson_resolution/05_benson_i_did_it.mp3` (shy pride)
   - Grizzle: `event_7_agent/07_grizzle_sent_proof.mp3` (neutral authority)

2. **Watch the lip-sync test video** — `videos/tessa_lipsync_test.mp4`
   - Does the mouth movement match the audio?
   - Is the animation quality acceptable?
   - Does the visual style fit the MindfulNest aesthetic?

3. **Flag any lines that need re-rendering** — pacing issues, wrong emotion, model mismatch, etc.

---

## Cost Summary

- **TTS generation:** ~191 lines × ~$0.003/line ≈ **$0.57** (estimated)
- **Seedance test:** 1 video × $0.06 = **$0.06**
- **LipSync test:** 1 video × $0.15 = **$0.15**
- **Total overnight spend:** ~**$0.78**

---

## Next Steps (Pending Kim Review)

1. Kim listens to spot-check audio and watches lip-sync test
2. Re-render any flagged lines with adjusted settings
3. If pipeline quality is approved → batch-generate Seedance + LipSync for all M1 scenes
4. Scale to remaining events (M2–M6 + Event 7)
5. Begin per-child personalized segment rendering test
