# Audio Producer — Governance Gate

**Skill:** audio-producer
**Created:** April 15, 2026
**Severity:** HIGH — voice settings and delivery method are locked decisions

> **[V1 CASCADE TAG 2026-04-21 — V1_CREATURE_SET_6_BENSON_AT_M3 (supersedes LD-335) + V1_SCOPE_CONDENSED_20260420 (revised 2×)]** V1 audio production scope: **M3 = Benson** (RESTORED 2026-04-21) teaching Physiological Sigh under Courage domain. Benson voice profile in `prod_voice_profiles` IS produced in V1. Arc 8 Hopegrove (M43-M48) is IN V1 — full audio production for those modules. V1 play order reverts to: M1 Tessa → M2 Luna → M3 **Benson** → M4 Ember → M6 Bramble → M5 Bork. Oliver is Arc 1 narrative-only (no Phase B audio production). See LDs 332-346 + LD-352 + LD-353 + LD-354 + `SCOPE_REVERSAL_BENSON_BACK_20260421.md`.

## Governing Documents (Read Before Proceeding)

1. `Production/PIPELINE_BRAIN_v1.md` — Audio section
2. `TTS_PERSONALIZATION_PIPELINE_v1.md` — Voice/personalization architecture
3. `CLAUDE.md` Rule 8 — Lip-sync prevention (applies to any TTS that feeds video)
4. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 1 (Audio Production)

## Startup Validation Checklist

Before ANY audio production work, verify ALL of the following:

### 1. Dashboard Queries Completed
- [ ] 7-query session start protocol completed (dashboard-gate)
- [ ] `prod_audio_locked_decisions` read — all 10 rules loaded
- [ ] `prod_voice_profiles` queried — Myrrhin settings confirmed
- [ ] `prod_activity_log` checked — Kim's prior verdicts on voice settings reviewed
- [ ] No rejected settings are being re-used

### 2. Voice Settings Check
- [ ] Myrrhin voice ID: `oR4uRy4fHDUGGISL0Rev`
- [ ] Myrrhin settings: stability 0.70, speed 0.50 (query `prod_voice_profiles` to confirm — Directus is authoritative; if Kim has updated settings there, the new values are the locked values)
- [ ] Model: `eleven_v3` for all characters
- [ ] "MindfulNest" hyphenated as "Mindful-Nest" in ALL TTS scripts
- [ ] Emotional direction tags on EVERY line

### 3. Script Readiness Check
- [ ] Phase B script is Kim-approved (check `prod_modules.stage_status`)
- [ ] Script contains `{{CUE_MARKERS}}`
- [ ] Script text preserved VERBATIM from Kim's approved version (Source Fidelity Protocol)

### 4. API Method Check
- [ ] Using Python `urllib.request` for Directus API calls (NEVER curl)
- [ ] ElevenLabs API key read from `Production/API_KEYS_MASTER.md` (never hardcoded)
- [ ] curl is acceptable ONLY for ElevenLabs TTS endpoint (no `$` in API key)

### 5. Delivery Method Check
- [ ] Audio files for Kim's review opened in QuickTime Player via Finder
- [ ] NEVER use `computer://` links (auto-play, no pause control)
- [ ] NEVER use HTML audio players (break in Cowork)

### 6. Pipeline Discipline Check
- [ ] One module per session only
- [ ] Sequential execution (no parallel audio tasks)
- [ ] Voice stem generated FIRST, then cue points extracted from real audio (never estimated)
- [ ] Vosk STT used for cue point extraction (never manual timing)

## Validation Logic (Pseudocode)

```python
def validate_audio_producer_governance():
    errors = []
    
    # Check 1: Dashboard
    if not session_start_protocol_completed:
        errors.append("HARD FAIL: 7-query session start protocol not completed")
    
    # Check 2: Voice settings
    voice_profile = query_directus("prod_voice_profiles", filter={"character_name": "Myrrhin"})
    if tts_settings.stability != voice_profile.stability:
        errors.append(f"HARD FAIL: Stability mismatch. Using {tts_settings.stability}, locked is {voice_profile.stability}")
    if tts_settings.speed != voice_profile.speed:
        errors.append(f"HARD FAIL: Speed mismatch. Using {tts_settings.speed}, locked is {voice_profile.speed}")
    
    # Check 3: Rejected settings
    prior_verdicts = query_directus("prod_activity_log", filter={"kim_verdict": "rejected"})
    for verdict in prior_verdicts:
        rejected_settings = verdict.get("voice_settings", {})
        if current_settings_match(rejected_settings):
            errors.append(f"HARD FAIL: Re-using settings Kim rejected: {verdict.get('kim_feedback')}")
    
    # Check 4: Script readiness
    module = query_directus("prod_modules", filter={"id": module_id})
    if module.current_stage == "phase_b" and module.stage_status != "completed":
        errors.append("HARD FAIL: Phase B script not approved — cannot produce audio")
    
    # Check 5: Delivery
    if delivery_method != "quicktime_via_finder":
        errors.append("HARD FAIL: Audio must be delivered via QuickTime Player")
    
    return errors
```

## What Happens When Validation Fails

- **HARD FAIL:** Stop immediately. Do not generate TTS or mix audio. Flag the violation to Kim.
- **SOFT FAIL:** Log a warning. Proceed with caution and note the exception in `prod_activity_log`.

## Past Failures This Gate Prevents

1. **April 11, 2026:** Claude generated 4 voice stems with wrong stability/speed settings because `prod_audio_locked_decisions` wasn't read first. Each failed attempt cost time, API credits, and Kim's patience.
2. **April 11, 2026:** Claude re-tried speed 1.0 and stability 0.30 after Kim had already rejected them. Kim's feedback: "wayyyy too fast" and "almost comical."
3. **April 11, 2026:** Three consecutive audio deliveries auto-played via `computer://` links without giving Kim a chance to prepare.

## Locked Architecture Constraints (added 2026-04-18, task_id: size-budget-arch-cascade-1caa1e0b)

Before producing ANY deliverable, verify:

- [ ] **Single-MP4 atomic (RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1):** Output is ONE MP4 file per module/event with all audio + video + animations baked in. No separate audio track. No separate overlay file. No multi-file deliverable.
- [ ] **No runtime TTS (NO_RUNTIME_TTS_PERSONALIZATION_V1):** Rendered audio contains NO personalization variables (`{childName}`, `{therapistName}`, `{parentTitle}`, `{parentName}`, `{chosenGuideName}`, pronouns). All spoken content is universal phrasing. ElevenLabs runs ONCE per module in the production pipeline; never at runtime from the app.
- [ ] **Arc-aware sizing (CATALOG_DELIVERY_ARC_AT_A_TIME_V1):** Per-module target ≤ 60 MB with 100 MB hard ceiling. If exceeded, either compress before registering or file a `SHORTCUT_SIZE_OVERRIDE_*` escape-hatch decision with Kim's approval.
- [ ] **Transparent MP4 loops (if used for characters/breathing circle):** BAKED INTO the atomic module MP4 at production time. Not layered at runtime. Reference: LD-128 2026-04-18 appendix.
- [ ] **Tool-layer enforcement (per Rule 19 addendum):** ffmpeg/cwebp/ElevenLabs command flags in this governance file are the enforcement point — hardcode bitrate and format ceilings here. Phase 0 prose gate is a reminder, not enforcement.

If ANY box cannot be checked, STOP. Either adjust the plan to comply OR file a `SHORTCUT_*` Directus decision with Kim's explicit approval.

Reference: `APP_ARCHITECTURE_MASTER_v1.md`, `SIZE_BUDGET_AUDIT_20260418.md`, preflight id=84.

---

## Lessons Learned April 25–26, 2026

### 7. No Directus Writes Outside Wrapper (LD-421)
All audio file writes (voice stems, mixes, ambient beds, SFX) MUST go through `Production/tools/registered_write.py`. Direct curl/urllib POSTs to prod_audio_assets, prod_assets, or prod_activity_log for asset registration are FORBIDDEN. The wrapper performs atomic registration + activity logging with SHA256 dedup and iteration_notes capture.

Verification:
```bash
python3 Production/scripts/check_compliance_gate_6.py --skill audio-producer
```

---

## Lessons Learned April 25–26, 2026

### Audio/Video Decoupled Trim Points — Audio-Side Rule (LD: `AUDIO_VIDEO_DECOUPLED_TRIM_V1`)
When trimming any clip containing multiple scenes, audio and video trim points MUST be set independently. Single `-t <duration>` trims cause cross-scene audio bleed into the next segment. Audio rule: use `afade=t=out:st=<dialogue_end_s>:d=0.4` to silence audio immediately after the last spoken phoneme. Always verify dialogue end with `silencedetect -45dB` (not -35dB — the tighter threshold catches quiet trailing consonants). The LAST `silence_start` in the output is NOT necessarily speech end — it may be a breath between words; always check whether `silence_end` is followed by more audio.
