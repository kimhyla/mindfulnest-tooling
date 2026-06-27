# Voice-First Beat Gen — Tech Spec v1

**Status:** Proposed — pilot validated (Event_2 beats 04/05/06/08)  
**Owner:** mindfulnest-tooling  
**Pilot proof:** `Production/Event_2/_pilot/scene_option1/scene_option1_pilot.mp4` (~17 s, 4 lines, hard-cut concat)  
**User-facing promise:** **Same Beat Gen workflow** (author → Generate → Approve → Send to Stitcher). Speaking beats get **ElevenLabs voice + silent O3 + lipsync**, not O3 native audio. Kid app still receives **720p delivery MP4s** — no change to LD-296 / session load model.

---

## Problem statement

Event_2 intro production uses **`kling_o3_element_beat_pipeline.py`** (O3 Pro, `sound:true`, Kling native voice per beat). Each beat is an isolated ~12 s generation. Result:

- Emotional tone jumps beat-to-beat (23 different native-audio gens)
- Clip length decoupled from dialogue (12 s bucket, not line length)
- Operator hears inconsistent Tessa / Lorelai vs Directus ElevenLabs profiles

**Option 1 pilot** proved a better model for dialogue beats:

1. ElevenLabs TTS (Directus `prod_voice_profiles`)
2. Silent O3 Pro visual (duration from padded lipsync audio, `sound:false`)
3. WaveSpeed Kling lipsync (mouth synced to ElevenLabs MP3)
4. **LD-296 delivery encode** → `kling_o3_video_path` (1280×720, ≤1.9 Mbps)
5. Existing **Send to Stitcher** concat → one intro MP4 (hard cuts + penultimate fades + canonical tail)

The pilot script is **R&D only**. Shipping requires wiring **`arlo_o3_voice_pipeline.py`** into the normal Beat Gen **Generate** button — not a separate operator tool.

---

## What we are not doing (v1)

- Scene-level authoring UI (group 4 lines → one approval) — Phase 2
- Changing LD-280 (still one module MP4 in app)
- Changing session load model (6–10 MP4s per arc, swap on arc advance)
- Shipping 1080p to the child app — **delivery stays 720p**
- Replacing WaveSpeed lipsync wrapper (separate spec: `KLING_NATIVE_LIPSYNC_WRAPPER_REPLACEMENT_SPEC_v1.md`)
- Re-authoring beats or sidecar schema overhaul

---

## Design decision: voice-first as Generate backend for speak beats

| | Today (canonical Generate) | v1 voice-first |
|---|---------------------------|----------------|
| API | `POST /api/bg/submit-arlo-o3-voice` | **Same endpoint** |
| Subprocess | `kling_o3_element_beat_pipeline.py` | **`arlo_o3_voice_pipeline.py`** when mode=voice_first |
| Audio source | Kling native (`sound:true`) | ElevenLabs v3 MP3 |
| Visual | O3 + audio in one call | Silent O3 (`sound:false`) |
| Lipsync | None | WaveSpeed Kling lipsync |
| Output field | `kling_o3_video_path` | **Same** |
| Approve / trim / Send to Stitcher | Unchanged | **Unchanged** |
| Kid delivery profile | LD-296 720p | **Same** |

**Non-speak beats** (no dialogue, magic-on-still, canonical tail slot): keep current pipelines.

---

## Resolution & app size (explicit)

| Stage | Resolution | In app bundle? |
|-------|------------|----------------|
| Lipsync input encode | 1920×1080 (`encode_lipsync_input`) | No — intermediate |
| Lipsync provider output | Must be **≥720 min dimension** before approve | No — intermediate |
| Delivery encode | **1280×720**, CRF + ≤1.9 Mbps (`video_delivery.py`) | **Yes** — this is `kling_o3_video_path` |

1080p in the pipeline is **upstream quality**, not kid-facing bloat. Final intro/module MP4 size is driven by **duration × 720p cap × beat count**, same as today.

**Pilot caveat:** `data_uri` lipsync fallback returned 832×464 (below gate). Production voice-first **must use URL transport first**; sub-720 output **must fail Generate** (existing `_assert_lipsync_quality`). Pilot waived for R&D only.

---

## Operator workflow (unchanged)

1. Open Beat Gen → Event_2 intro segment (same as today).
2. Select beat → edit dialogue / speaker / refs (same as today).
3. Click **Generate** (same button).
4. Wait for job (longer per speak beat: TTS + O3 + lipsync poll).
5. Preview → **Approve** (same).
6. Optional **Apply Trim** (same sidecar fields; export uses trimmed clip).
7. When all intro beats approved → **Send to Stitcher (intro)** (same).
8. One intro MP4 in Stitcher slot with penultimate fades + canonical mirror tail (same).

**What changes for Kim:** dialogue beats should sound like **consistent ElevenLabs characters** and run **~line length**, not fixed 12 s emotional O3 buckets. No new scripts, no manual concat.

---

## Rollout flag (Event_2 first)

```text
MN_O3_GENERATE_MODE=voice_first          # env on production_server LaunchAgent
```

Or sidecar segment override:

```json
"event_2_pre": { "o3_generate_mode": "voice_first" }
```

**v1 default:** `voice_first` for **`event_2_pre`** only. All other segments keep `element_native` (current `kling_o3_element_beat_pipeline.py`) until Event_2 intro sign-off.

Implementation: `handle_bg_submit_arlo_o3_voice` chooses subprocess script:

```python
if resolve_o3_generate_mode(beat, sidecar) == "voice_first":
    script = TOOLS / "arlo_o3_voice_pipeline.py"
else:
    script = TOOLS / "kling_o3_element_beat_pipeline.py"
```

---

## Implementation plan

### A. Server routing (1 PR)

**File:** `server_handlers/background.py` — `handle_bg_submit_arlo_o3_voice`

- Add `resolve_o3_generate_mode(beat, sidecar) -> Literal["voice_first", "element_native"]`
- Point `voice_first` at `arlo_o3_voice_pipeline.py` (already implements intent + `attempt_id` + sidecar persist)
- Keep generation intent commit path identical (`o3_generation_intent.py`)
- Poll endpoint unchanged (`poll-arlo-o3-voice-status` reads `kling_o3_voice_fix_*` — both pipelines write these)

### B. Lipsync URL hosting durability (1 PR)

**File:** `lipsync_sender.py`

Pilot blocked on filebin/catbox DNS + uguu 500. Production gate:

- URL transport required for approve path (existing arlo behavior; data_uri only when `MINDFULNEST_ALLOW_LOW_QUALITY_LIPSYNC_DATA_URI_FALLBACK=1`)
- Add **one durable host** (e.g. self-hosted presigned S3/R2, or production_server temporary upload route `POST /api/lipsync/staging-upload` → signed GET URL for WaveSpeed)

Without B, voice-first Generate will fail sub-720 or hosting errors in production.

### C. Duration from audio (verify, small fix if needed)

**File:** `arlo_o3_voice_pipeline.py`

- O3 `duration` = `ceil(padded_audio_duration_s + 0.25)` clamped `[5, 12]` (pilot + arlo already do this)
- Ensure intent snapshot does **not** force `kling_o3_duration: 12` over audio-derived value for voice_first mode

### D. Long-line guard (document + UI message)

**Rule:** `LIPSYNC_MAX_PADDED_AUDIO_S = 9.9` (arlo). Lines whose padded audio exceeds cap **cannot lipsync in one job**.

- v1: fail Generate with clear error + suggest split beat (same as pilot skipping beat 03)
- Optional follow-up: auto-split long dialogue in plan extract (out of v1 scope)

### E. Beat Gen UI (minimal)

**File:** storyboard bundle / BG panel

- Job phase labels already map from `kling_o3_voice_fix_phase` (`tts` → `o3` → `lipsync` → `finalize`)
- Add badge when segment is `voice_first`: **“Voice: ElevenLabs”** (informational only)
- No second Generate button

### F. Stitch export (no code change)

**Already works** when `kling_o3_status=approved` and `kling_o3_video_path` points at delivery MP4:

- `resolve_beat_stitch_export_clip_path` → `_kling_o3_export_clip_path` (respects trim)
- `concat_kling_o3_approved_beats` → intro fades + canonical tail

Voice-first beats are indistinguishable to Stitcher from today's approved clips.

---

## Sidecar fields (reuse — no new schema v1)

Existing `kling_o3_voice_fix_*` block written by `arlo_o3_voice_pipeline.py`:

| Field | Purpose |
|-------|---------|
| `kling_o3_voice_fix_audio_path` | ElevenLabs source MP3 |
| `kling_o3_voice_fix_lipsync_audio_path` | Padded MP3 for lipsync |
| `kling_o3_voice_fix_lipsync_transport` | `url` \| `data_uri` |
| `kling_o3_voice_fix_lipsync_quality` | width/height gate |
| `kling_o3_video_path` | **Final 720 delivery** (stitch source) |
| `kling_o3_status` | `approved` when done |

Add one audit field:

```json
"kling_o3_generate_mode": "voice_first"
```

---

## Acceptance criteria (Event_2 intro)

1. **Generate** on beat 05 (Lorelai speak) uses ElevenLabs Luna/Lorelai profile — operator hears profile voice, not random O3 native tone.
2. Approved clip duration ≈ dialogue length (+ padding trimmed at export), not forced 12 s.
3. `ffprobe` on approved `kling_o3_video_path`: **1280×720**, H.264, ≤1.9 Mbps.
4. Lipsync output **min(w,h) ≥ 720** or Generate fails (no silent approve of 832×464).
5. **Send to Stitcher (intro)** produces MP4 ≥ prior beat count duration; last two boundaries use fade-through-black; final beat uses canonical mirror tail.
6. Re-Generate on approved beat preserves prior clip as O3 option until new clip approved (existing arlo behavior).
7. Deploy path: mirror tooling → Dropbox → restart `:5112` Event_2 server; pytest gate green.

**Practice proof:** Re-run beats 04–08 through Beat Gen UI (not pilot script) → concat intro → operator A/B vs current native-audio intro on **voice consistency** and **cut timing**.

---

## Test plan

| Layer | Tests |
|-------|--------|
| Unit | `resolve_o3_generate_mode` segment/env; duration clamp from fake padding dict |
| Contract | `arlo_o3_voice_pipeline` still sets `kling_o3_video_path` + `approved`; sub-720 raises |
| Integration | Mock lipsync URL submit → poll complete → delivery 720 probe |
| Manual | Event_2 beats 04, 05, 06, 08 Generate → Approve → Send to Stitcher |

---

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Lipsync URL hosts down | §B staging upload route; fail loud, no data_uri in prod |
| WaveSpeed lipsync always 832×464 | Track native lipsync replacement spec; block ship if gate fails on URL path |
| Long dialogue (>9.9 s pad) | Clear error; split beat in authoring |
| Wall-clock per beat (~5–8 min) | Expected; no batch change in v1 |
| Operator confusion | Same buttons; optional “ElevenLabs voice” badge |

---

## Phase 2 (out of v1 — do not implement yet)

- **Scene mode:** author/approve **scene** (N lines, one bg) → one MP4 per scene → concat scenes for intro
- Batch regenerate all speak beats in segment
- Auto-split over-long dialogue at extract time

---

## File touch list (v1)

| File | Change |
|------|--------|
| `server_handlers/background.py` | Mode router → `arlo_o3_voice_pipeline.py` |
| `beat_generator.py` | `resolve_o3_generate_mode()` helper |
| `lipsync_sender.py` + optional `server_handlers/lipsync_staging.py` | Durable URL hosting |
| `arlo_o3_voice_pipeline.py` | Minor: stamp `kling_o3_generate_mode` |
| `tests/test_voice_first_generate_mode.py` | New |
| `Production/docs/VOICE_FIRST_BEAT_GEN_SPEC_v1.md` | This doc |

**No changes:** `concat_kling_o3_approved_beats`, `video_delivery.py` delivery profile, app MP4 loader, LD-280 module route.

---

## Deploy checklist

1. Commit on feature branch in **mindfulnest-tooling**
2. Mirror → Dropbox `Production/tools/`
3. `verify_tooling_dropbox_parity.py` exit 0
4. Restart Event_2 storyboard server (`:5112`)
5. Hard refresh storyboard HTML
6. Generate one speak beat → verify log shows `tts_start` → `o3_poll` → `lipsync_poll` → `finalize`
7. Send to Stitcher smoke on 2+ approved beats

---

## Glossary

| Term | Meaning |
|------|---------|
| **element_native** | Current Generate: O3 + Kling native audio (`kling_o3_element_beat_pipeline.py`) |
| **voice_first** | Pilot model: ElevenLabs → silent O3 → lipsync (`arlo_o3_voice_pipeline.py`) |
| **delivery** | Kid-facing 720p encode — only file Stitcher/app care about |
| **Send to Stitcher** | Existing BG export that concat approved beats into intro/phase slots |
