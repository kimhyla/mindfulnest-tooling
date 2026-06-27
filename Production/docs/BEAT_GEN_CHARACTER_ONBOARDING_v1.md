# Beat Gen Character Onboarding v1

**Status:** active — canonical process for every new dialogue character  
**Last updated:** 2026-06-27  
**Applies to:** Beat Gen tab, all events, all speakers with dialogue beats

---

## What this replaces (never again)

| Banned detour | Why |
|---|---|
| Silent O3 → ElevenLabs mp3 → WaveSpeed lipsync | Returns 832×464; resolution flip-flop; multi-step failure |
| Prompt-only voice tuning for Element speakers | Create-voice sample dominates delivery |
| Sharing another character's `kling_voice_id` | Voice/enthusiasm drift beat-to-beat |
| Shipping raw provider MP4 to kids | Must pass through delivery encode |

**Canonical path:** ElevenLabs sample → Kling create-voice → Element → **O3 Pro reference-to-video** (`sound:true`, `element_list`) → **1280×720 delivery encode**.

Implementation: `Production/tools/kling_o3_element_beat_pipeline.py` (invoked by Beat Gen submit).

---

## Aspect ratio & resolution policy

| Stage | Target | Notes |
|---|---|---|
| O3 provider raw | **min(width,height) ≥ 720** | Accept 720 or 1080 from Kling; never upscale |
| Kid-facing delivery | **1280×720 (16:9)** | `video_delivery.encode_delivery_video` — automatic in pipeline |
| Aspect ratio | **16:9** | Matches module playback (`expo-video` full-screen 16:9). Not 4:3. |

**720 vs 1080 for kids:** Delivery is always 720. Raw 1080 from O3 is fine as a master only. Smaller downloads, faster cache, fewer errors on iPhone/iPad. Do not ship 1080 to the app.

---

## 8-step onboarding (every new character)

Every dialogue character needs **two voice layers** before Beat Gen O3 spend:

| Layer | Where | What it fixes |
|---|---|---|
| **1. O3 delivery lock** | `kling_o3_prompt.py` → `_DELIVERY_BY_SPEAKER` | Prevents generic Kling TTS / robotic reads in generated beats |
| **2. Tagged create-voice sample** | `element_sample_lines` + `voice_sample_lock` + `kling_voice_samples/*.mp3` | ElevenLabs eleven_v3 emotional direction → Kling create-voice clone quality |

`setup_all_kling_character_voices.py` **blocks WaveSpeed spend** (first register, `--refresh-voice`, `--samples-only`) unless both layers pass. Use `--skip-lock-check` only for dev/emergency.

### 1. Discovery
- Pick ElevenLabs voice from `VOICE_ROSTER_LOCKED_v2.md`
- Classify archetype: **guide** (calm) vs **expressive** (Tessa-style)

### 2. Visual Element prep
- Register poses in `Production/character_subjects.json`
- `frontal_image` + `refer_images` (1024×1024 PNG, Rule 6)

### 3. ElevenLabs roster entry
Edit `Production/tools/kling_element_voice.py` → `ELEVENLABS_VOICE_ROSTER`:

| Archetype | stability | style | speed |
|---|---|---|---|
| **Guide** (Chipper, Arlo) | **0.70–0.75** | **0.05–0.08** | 1.0–1.15 |
| Expressive (Tessa, Luna…) | 0.30 | 0.30 | per roster |

**Guide voices use high stability + low style** — this is the anti-hyper fix.

### 4. Element sample lines
- Add `element_sample_lines` in `character_subjects.json`
- Use **normal conversational beat lines**, not hype intros ("Here we go!" only if that's the character)
- Guides: intro/help lines, not teleport countdown energy

### 4a. O3 delivery lock (mandatory — Layer 1)
Edit `Production/tools/kling_o3_prompt.py`:

1. Add `KLING_O3_<NAME>_VOICE_DELIVERY = "warm … pace, … not robotic, …"` (copy pattern from Tessa/Ember)
2. Register in `_DELIVERY_BY_SPEAKER["Name"]` (and display-name aliases if any, e.g. Lorelai → Loral)

Without this, Beat Gen falls back to generic `speaks clearly at a natural pace` → **robotic AI voice**.

### 4b. eleven_v3 emotion tags on sample lines (mandatory for new characters — Layer 2)
- Add tagged lines to `DEFAULT_ELEMENT_SAMPLE_LINES` in `kling_voice_sample_lock.py` **and** `character_subjects.json`
- Format: `[warm, gentle] Come here — you don't have to do this alone.` (comma inside brackets per `VOICE_ROSTER_LOCKED_v2.md`)
- `[pause]` alone does **not** count — need emotion descriptors
- **Waiver (rare):** set `"voice_onboarding_waiver": "reason"` on the character entry to skip the tag gate only (narrator-only edge cases). Delivery lock still required for Beat Gen dialogue speakers.

### 5. Speed audition
```bash
cd Production
python3 scripts/audition_character_voice_speed.py --char <Name>
```
Kim picks speed in `listen.html`.

### 6. Lock speed
```bash
python3 scripts/audition_character_voice_speed.py --char <Name> --lock-speed <speed> --from-dir <speed_compare_dir>
```
Writes `voice_sample_lock` — **required before spending WaveSpeed credits** (enforced on first register and voice refresh).

### 7. Register Element + create-voice
```bash
python3 scripts/setup_all_kling_character_voices.py --char <Name>
```
Produces: `kling_voice_samples/<name>.mp3`, `kling_voice_id`, `element_id` in `character_subjects.json`.

**Script gates (exit 1 if missing):**
- `voice_sample_lock` with matching fingerprint
- O3 delivery lock in `kling_o3_prompt.py`
- eleven_v3 emotion tags on sample lines (first register only; active binds grandfather tag check on refresh; `voice_onboarding_waiver` skips tag gate only)
- No legacy arc-audio fallback for roster characters (`ensure_voice_sample` uses ElevenLabs only)

**CI / deploy gates (fail loud — do not rely on memory):**
- `Production/scripts/verify_character_voice_onboarding_contract.sh` (also in `verify_o3_intro_contract.sh`, pre-push, deploy step d.6)
- Asserts every `ELEVENLABS_VOICE_ROSTER` key has `_DELIVERY_BY_SPEAKER` entry + tagged `DEFAULT_ELEMENT_SAMPLE_LINES`

### 8. Smoke one beat
```bash
cd Production
PYTHONUNBUFFERED=1 python3 tools/kling_o3_element_beat_pipeline.py --beat-id <beat_id>
```
Verify: raw ≥720 + audio, delivery = 1280×720, voice acceptable to Kim.

---

## Beat Gen submit (production)

- UI: Beat Gen tab → Generate on a beat with an Element-ready speaker
- API: `POST /api/bg/submit-arlo-o3-voice` (name legacy; works for **all** Element speakers)
- Backend: `kling_o3_element_beat_pipeline.py`
- Poll: `GET /api/bg/poll-arlo-o3-voice-status`

Pipeline steps (automatic):
1. Validate Element + refs
2. Build prompt + locked delivery phrase (`kling_o3_prompt.py`)
3. O3 Pro reference-to-video (`kling_o3_client.py`)
4. Raw gate ≥720 + audio
5. **`encode_delivery_video` → 1280×720** (always)

---

## Locked decisions (Directus)

- `BEAT_GEN_VOICE_AUDITION_BEFORE_ELEMENT_V1` — lock before `--force`
- `BEAT_GEN_ELEMENT_VOICE_DOMINATES_PROMPT_V1` — tune voice in ElevenLabs roster + re-register Element, not prompts alone
- Raw provider gate ≥720; delivery 1280×720; no upscale

---

## Phase A / Phase B note

Phase A/B use separate stitch/lipsync tooling for fly-in/flyout mechanics. **Dialogue beats in Beat Gen** use this Element O3 path. When Phase A/B need character dialogue with voice, route through the same Element registry — do not invent a third lipsync detour.

---

## Files (source of truth on Dropbox)

```
Production/character_subjects.json          — Element IDs, voice_sample_lock
Production/tools/kling_element_voice.py   — ElevenLabs roster + setup
Production/tools/kling_o3_client.py       — O3 Pro submit
Production/tools/kling_o3_prompt.py         — Delivery phrase locks
Production/tools/kling_o3_element_beat_pipeline.py — Beat Gen subprocess
Production/tools/video_delivery.py        — 1280×720 kid encode (LD-284/LD-296)
Production/scripts/setup_all_kling_character_voices.py
Production/scripts/audition_character_voice_speed.py
Production/scripts/verify_character_voice_onboarding_contract.sh
```

Server runs from **Dropbox** `Production/tools/` — not the sibling git repo alone.

---

## Arlo reference (2026-06-10)

- Penultimate intro beat: `bg_arc1_event1_pre_beat_10`
- Ultimate (canonical mirror tail): `bg_arc1_event1_pre_beat_11` — use Intro Kit, not Beat Gen roulette
- Arlo calm clone: stability 0.75, style 0.05, speed 1.0, own `kling_voice_id` (not shared with Chipper)
