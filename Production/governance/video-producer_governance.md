# Video Producer — Governance Gate

**Skill:** video-producer
**Created:** April 15, 2026
**Severity:** HIGH — lip-sync prevention is production-critical

> **[V1 CASCADE TAG 2026-04-21 — V1_CREATURE_SET_6_BENSON_AT_M3 (supersedes LD-335) + V1_SCOPE_CONDENSED_20260420 (revised 2×)]** V1 production scope: **M3 = Benson** (RESTORED 2026-04-21) teaching Physiological Sigh under Courage domain. Arc 8 Hopegrove is IN V1 — full video production for M43-M48. V1 play order reverts to: M1 Tessa → M2 Luna → M3 **Benson** → M4 Ember → M6 Bramble → M5 Bork. Oliver is Arc 1 narrative-only (no module-teaching video work; Event 3b Oliver Meet remains). See LDs 332-346 + LD-352 + LD-353 + LD-354 + `SCOPE_REVERSAL_BENSON_BACK_20260421.md`.

## Governing Documents (Read Before Proceeding)

1. `CLAUDE.md` Rule 8 — Motion Prompt Lip-Sync Prevention (Multi-Model with Safeguards)
2. `Production/PIPELINE_BRAIN_v1.md` — Video pipeline section
3. `CLAUDE.md` Rule 7 — Two-Path Protocol (for storyboard-adjacent video work)
4. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 2 (Video/Animation Production)

## Startup Validation Checklist

Before ANY video/animation generation, verify ALL of the following:

### 1. Model Selection Check
- [ ] Default model is Kling v3.0 Pro via WaveSpeed (`kwaivgi/kling-v3.0-pro/image-to-video`) or EvoLink
- [ ] If Seedance is being used: Kim explicitly requested it OR Kling is unavailable
- [ ] If Seedance is being used: Lip-Sync Review Gate is scheduled for EVERY clip

### 2. Motion Prompt Banned Words Check
Scan ALL motion prompts for banned words. If ANY are present, REJECT the prompt:
- `speaking`, `speech`, `dialogue`, `lip sync`, `lip movement`
- `mouth movement`, `beak movement`, `talking`, `singing`, `vocal`

### 3. Motion Prompt Required Constraints Check
- [ ] Bird characters include: `"Beak closed, no speech, no lip movement"`
- [ ] Turtle/mammal characters include: `"Mouth closed, no speech"`
- [ ] ALL prompts end with: `"Silent subtle idle movement only"` or `"no dialogue in video"`

### 4. API Parameters Check
- [ ] `sound: false` is set
- [ ] `negative_prompt` includes: `"lip sync, speaking, talking, mouth movement, dialogue, speech, open mouth, Chinese, audio, voice, singing"`
- [ ] `cfg_scale: 0.5` is set

### 5. Visual Consistency Check
- [ ] Style is Pixar 3D (NOT painterly — superseded April 10, 2026)
- [ ] Character stills generated from single master image (NOT per-character generation)
- [ ] No cross-pasting between AI generators
- [ ] Master images generated at 2048×2048 minimum

### 6. Dashboard Integration Check
- [ ] Dashboard-gate session start protocol completed
- [ ] Model choice logged in `prod_activity_log`
- [ ] Every generated clip registered in `prod_visual_assets` immediately

### 7. Delivery Encoding Default + Size Budget Check (added 2026-04-18, LDs `SIZE_BUDGET_VIDEO_V1` + `SIZE_BUDGET_V1` + LD-283)

- [ ] Every shipped video clip + every assembled segment is encoded with the canonical command:

  ```
  ffmpeg -i in.mp4 -c:v libx264 -preset slow -profile:v high -pix_fmt yuv420p \
    -b:v 1500k -maxrate 1800k -bufsize 3000k -movflags +faststart \
    -c:a aac -b:a 96k -ac 2 -ar 44100 out.mp4
  ```

  (Use `-b:v 1000k -maxrate 1200k` for static / slow-pan scenes.)

- [ ] **HARD FAIL post-encode assertion (mandatory, no exceptions):** ffprobe stream bit_rate must be ≤ **1,900,000 bps** for every output. The 1.9 Mbps guard band sits 5% under the 2.0 Mbps SIZE_BUDGET_VIDEO_V1 hard ceiling to absorb VBR drift.

  ```
  BR=$(ffprobe -v error -select_streams v:0 -show_entries stream=bit_rate \
        -of default=noprint_wrappers=1:nokey=1 out.mp4)
  if [ "$BR" -gt 1900000 ]; then echo "FAIL: $BR bps"; exit 1; fi
  ```

- [ ] **Per-module size budget check (LD-283 SIZE_BUDGET_PER_MODULE_V1):** the assembled atomic module MP4 must be ≤ **80 MB** (60 MB target). Sum of per-beat normalized clips + Phase B audio + transitions counted against this. If exceeded, EITHER compress further (drop motion bitrate, shorten scenes) OR file `SHORTCUT_MODULE_{module_id}_CEILING_V1` in `prod_locked_decisions` with Kim's explicit approval per Rule 19. Silent overages are forbidden.

- [ ] **Source preservation:** if re-encoding existing clips for size budget compliance, originals MUST be copied to `/masters/Event_N/` (mirroring the source path) BEFORE the re-encode lands in place. This is non-destructive precondition for any size-budget-driven re-encode pass.

Reference: `SIZE_BUDGET_AUDIT_20260418.md` §5.1, `prod_locked_decisions` SIZE_BUDGET_VIDEO_V1 / SIZE_BUDGET_V1 / LD-283.

### 8. No Directus Writes Outside Wrapper (LD-421)
All media file writes (TTS, stills, animation clips, lipsync clips, final videos) MUST go through `Production/tools/registered_write.py`. Direct curl/urllib POSTs to prod_audio_assets, prod_visual_assets, or prod_activity_log for asset registration are FORBIDDEN. The wrapper performs atomic registration + activity logging with SHA256 dedup and iteration_notes capture.

Verification:
```bash
python3 Production/scripts/check_compliance_gate_6.py --skill video-producer
```

## Validation Logic (Pseudocode)

```python
def validate_video_producer_governance():
    errors = []
    
    # Check 1: Model selection
    if model == "seedance" and not kim_explicitly_requested:
        errors.append("HARD FAIL: Seedance requires Kim's explicit request or Kling unavailability")
    
    # Check 2: Banned words
    BANNED = ["speaking", "speech", "dialogue", "lip sync", "lip movement",
              "mouth movement", "beak movement", "talking", "singing", "vocal"]
    for prompt in motion_prompts:
        for word in BANNED:
            if word.lower() in prompt.lower():
                errors.append(f"HARD FAIL: Banned word '{word}' in motion prompt")
    
    # Check 3: Required constraints
    for prompt in motion_prompts:
        if not any(c in prompt for c in ["Beak closed", "Mouth closed"]):
            errors.append("SOFT FAIL: Missing character-specific mouth constraint")
        if not any(c in prompt for c in ["Silent subtle idle", "no dialogue in video"]):
            errors.append("SOFT FAIL: Missing end constraint")
    
    # Check 4: API params
    if api_params.get("sound") != False:
        errors.append("HARD FAIL: sound must be false")
    if "lip sync" not in api_params.get("negative_prompt", ""):
        errors.append("HARD FAIL: negative_prompt missing lip-sync terms")
    
    return errors
```

## What Happens When Validation Fails

- **HARD FAIL:** Stop immediately. Do not proceed with generation. Flag the violation to Kim.
- **SOFT FAIL:** Log a warning. Proceed only if there's a documented reason (e.g., character has no visible mouth). Log the exception in `prod_activity_log`.

## Past Failure This Gate Prevents

**April 14, 2026:** Every Seedance generation produced Chinese lip-sync animation on a cartoon turtle and bird, despite prompts saying "Beak closed, no speech" and API params including `generate_audio: false`. Root cause: Seedance v1.5 has a talking-head bias in its model weights. Switching to Kling eliminated the problem entirely.

## Locked Architecture Constraints (added 2026-04-18, task_id: size-budget-arch-cascade-1caa1e0b)

Before producing ANY deliverable, verify:

- [ ] **Single-MP4 atomic (RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1):** Output is ONE MP4 file per module/event with all audio + video + animations baked in. No separate audio track. No separate overlay file. No multi-file deliverable.
- [ ] **No runtime TTS (NO_RUNTIME_TTS_PERSONALIZATION_V1):** Rendered audio contains NO personalization variables (`{childName}`, `{therapistName}`, `{parentTitle}`, `{parentName}`, `{chosenGuideName}`, pronouns). All spoken content is universal phrasing. ElevenLabs runs ONCE per module in the production pipeline; never at runtime from the app.
- [ ] **Arc-aware sizing (CATALOG_DELIVERY_ARC_AT_A_TIME_V1):** Per-module target ≤ 60 MB with 100 MB hard ceiling. If exceeded, either compress before registering or file a `SHORTCUT_SIZE_OVERRIDE_*` escape-hatch decision with Kim's approval.
- [ ] **Transparent MP4 loops (if used for characters/breathing circle):** BAKED INTO the atomic module MP4 at production time. Not layered at runtime. Reference: LD-128 2026-04-18 appendix.
- [ ] **Tool-layer enforcement (per Rule 19 addendum):** ffmpeg/cwebp/ElevenLabs command flags in this governance file are the enforcement point — hardcode bitrate and format ceilings here. Phase 0 prose gate is a reminder, not enforcement.

If ANY box cannot be checked, STOP. Either adjust the plan to comply OR file a `SHORTCUT_*` Directus decision with Kim's explicit approval.

Reference: `APP_ARCHITECTURE_MASTER_v1.md`, `SIZE_BUDGET_AUDIT_20260418.md`, preflight id=84.

## Normalization-before-concat gate (added 2026-04-18, LD-284 `NORMALIZATION_BEFORE_CONCAT_V1`, preflight id=85)

Before assembling ANY module MP4 via concat (Step 8 of the video-producer skill), verify ALL of the following:

- [ ] **Per-beat normalization complete.** Every beat's final selected clip exists as a `beat_NN_normalized.mp4` sibling to the selected source. If any beat is missing its normalized output, STOP — do not proceed with concat.
- [ ] **Canonical codec spec applied.** Every `beat_NN_normalized.mp4` was produced with the exact command (no deviations):
  ```
  ffmpeg -y -i INPUT.mp4 \
    -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1:1,fps=24" \
    -c:v libx264 -profile:v high -pix_fmt yuv420p -preset slow -crf 20 -g 48 \
    -c:a aac -b:a 128k -ar 44100 -ac 1 \
    -movflags +faststart \
    beat_NN_normalized.mp4
  ```
  Any deviation requires a `NORMALIZATION_EXCEPTION_*` LD referencing LD-284.
- [ ] **Cache validity checked.** `beat_NN_normalized.meta.json` sidecar `{source_path, source_mtime, source_sha256_first_1mb, selected_option, codec_spec_hash}` matches the current state. Any mismatch → re-normalize.
- [ ] **Concat inputs are EXCLUSIVELY normalized clips.** Never raw lipsync output, raw Kling output, or hand-looped re-encodes. If the concat demuxer input list references any non-`beat_NN_normalized.mp4` path, STOP — that is the LD-284 shortcut.
- [ ] **`/api/scene/assemble` refused to run if ANY beat lacks a valid normalized output** matching the current `selected_option`.

**HARD FAIL conditions:**
- Concat input is a raw lipsync/Kling/hand-looped clip → stop, normalize, retry.
- Normalized output exists but codec_spec_hash doesn't match current LD-284 spec → re-normalize.
- Normalized output exists but source mtime/SHA mismatch → re-normalize (source was replaced).
- Normalized output is missing for any beat → stop, trigger normalization, wait for completion.

**SOFT FAIL (log warning, proceed with caveat):**
- Normalization produced an output whose bitrate exceeds SIZE_BUDGET_VIDEO_V1 2.0 Mbps ceiling — investigate source before concat; the source clip may have an encoding issue upstream.

Reference: `Production/PIPELINE_BRAIN_v1.md` §Normalization, `APP_ARCHITECTURE_MASTER_v1.md` §7 (LD-284 cross-ref), `SIZE_BUDGET_AUDIT_20260418.md` §5.5.

---

## Lessons Learned April 25–26, 2026

### Concat Audio-Stream Parity Check (LD: `CONCAT_AUDIO_PARITY_V1`)
Before ANY `ffmpeg concat demuxer` operation, run `ffprobe -show_streams` on EVERY input segment and confirm each has both `codec_type: video` AND `codec_type: audio`. If any segment lacks audio, inject a synthesized silent stream: `anullsrc=r=44100:cl=mono,atrim=duration=<segment_duration_s>` (the `atrim` is mandatory — without it, `anullsrc` generates infinite silence). Concat demuxer silently drops ALL audio from the entire output when even one input lacks an audio stream. Failure is silent; the output looks correct until playback.

### Audio/Video Decoupled Trim Points (LD: `AUDIO_VIDEO_DECOUPLED_TRIM_V1`)
When trimming a source clip that contains multiple scenes, set audio and video trim points INDEPENDENTLY. Single `-t <duration>` trims cause cross-scene audio bleed. Pattern: video trim at scene visual boundary; `afade=t=out:st=<aud_fade_start>:d=0.4` to silence audio after dialogue completes but before next-scene audio begins. Always confirm dialogue end with `silencedetect -45dB` — lower threshold catches quiet trailing phonemes. Verify whether any `silence_end` is followed by more audio; the last `silence_start` is NOT necessarily speech end (may be a breath between words).
