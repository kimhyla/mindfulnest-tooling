# TECH SPEC — Beat Gen Avatar Pro default v1

**Status:** **Superseded** — production default restored to Kling Omni (`element_native`) per `TECH_SPEC_BEATGEN_CATEGORY_FIX_ARC_v1.md` (2026-06-27). Avatar Pro remains **Phase B lipsync only** (`MN_BEATGEN_AVATAR_ALLOWED=1` opt-in rollback for Beat Gen speak beats).  
**Historical scope:** Replace Beat Gen speak-beat default with Avatar Pro — experiment rolled back after sidecar pollution + storage scope bugs.  
**Proof anchor (Phase B parity):** Event_2 Avatar job `fbb800405fb54c829e12e6b795f923f7` — $2.93 / 26.07s — operator-approved quality; Phase B full-stem wire shipped in `phase_b_avatar_lipsync.py` + `handle_phase_b_lipsync`.

**Related specs (must not contradict):**

- `Production/docs/TECH_SPEC_PHASE_B_AVATAR_PRO_WIRE_v1.md` — module lipsync; Beat Gen reuses `LipSyncClient.submit_avatar_pro()` + delivery choke point only.
- `.cursor/rules/mindfulnest-intro-canonical-tail.mdc` — intro canonical mirror tail beat unchanged (pre-built composite, not Avatar).
- LD-280 / kid app — one atomic MP4 per module; Beat Gen output still lands in Stitcher slots unchanged.

---

## 1. Success statement (operator-visible)

Kim opens **Beat Gen (Bg tab)** on any event, selects a **dialogue beat** (speaker ≠ stage direction), clicks **Generate**:

1. Server runs **one subprocess** (`arlo_avatar_beat_pipeline.py` — see §5) that:
   - Renders dialogue via **ElevenLabs** (existing Arlo/Chipper voice profile).
   - Submits **one** Avatar Pro job: beat `reference_image` still + TTS audio + **portrait frozen-BG prompt** derived from beat prompt.
   - Polls to completion → downloads MP4 → **`encode_delivery_video`** with `voice_first_upscale` (1280×720).
2. Sidecar shows `kling_o3_status=approved`, `kling_o3_mode=o3_avatar_pro_v1`, gallery option labeled **Avatar Pro (latest)**.
3. **Preview, trim, Send to Stitcher, lean bake** behave identically to today’s approved voice-first clips (same sidecar fields, same export path).
4. **Wall-clock per beat decreases** (one WaveSpeed job, not O3 + LipSync sequential).
5. **WaveSpeed cost per beat decreases** (~$0.35/job LipSync eliminated; no padded O3 bucket billing).

Kim does **not** see voice-first vs Element native toggles on speak beats. Rollback is env-only (§14).

---

## 2. Non-goals (v1)

| Item | Reason |
|------|--------|
| Avatar for **Phase B** | Already shipped (`single_full_stem_v1`). This spec is Beat Gen only. |
| Avatar for **intro canonical mirror tail** | Pre-built composite; trim/export exception unchanged. |
| Avatar for **still_insert** beats | Ken Burns / static hold / kling_idle — separate pipeline. |
| Avatar for **stage_direction** beats | No speaker; bg-motion spec deferred (§11). |
| Segmented Avatar on long beats | Beat Gen clips are ≤12s; one Avatar job per beat. |
| Third UI pipeline toggle | Category fix: Avatar **is** the speak path, not option C. |
| Delete Element native code in v1 | Soft-retire: hide UI, keep gallery read + env rollback. |
| New delivery profile | Reuse `voice_first_upscale` + `PHASE_MODULE_LIPSYNC_DELIVERY_V1` metadata shape. |

---

## 3. Beat taxonomy (routing table)

Every beat resolves to **exactly one** effective mode via `resolve_beat_generation_mode()` (`beat_generator.py`).

| Taxonomy | Detection | Generate action | Vendor |
|----------|-----------|-----------------|--------|
| **Speak portrait** | `pipeline=kling_o3_omni`, speaker set, not stage direction | **Avatar Pro v1** (new default) | `kwaivgi/kling-v2-ai-avatar-pro` |
| **Still insert** | `pipeline=still_insert` | `render_still_insert_o3_clip` | Local Ken Burns + TTS (unchanged) |
| **Stage direction** | `beat_type=stage_direction` or speaker `[stage direction]` | No Avatar; manual / future bg-motion | N/A v1 |
| **Canonical mirror** | `intro_beat_role=canonical_mirror_video` | Protected; no Generate overwrite | N/A |

**Classifier authority:** `classify_beat_pipeline_fields()` + `resolve_beat_pipeline_mode()` — must run before submit routing (`background.py` `handle_bg_submit_arlo_o3_voice`).

---

## 4. Architecture (before → after)

### 4.1 Today (`voice_first`)

```
BgTab Generate
  POST /api/bg/submit-arlo-o3-voice { beat_id }
       ↓
handle_bg_submit_arlo_o3_voice → subprocess arlo_o3_voice_pipeline.py
       ↓
ElevenLabs TTS
       ↓
O3 Pro reference-to-video (silent, char+bg refs)  ← WaveSpeed job 1
       ↓
encode_lipsync_input → Kling LipSync              ← WaveSpeed job 2
       ↓
encode_delivery_video (voice_first_upscale)
       ↓
sidecar: kling_o3_video_path, kling_o3_mode=o3_voice_first_lipsync
```

### 4.2 Target (`avatar_pro`)

```
BgTab Generate
  POST /api/bg/submit-arlo-o3-voice { beat_id }   // endpoint unchanged (category: one operator button)
       ↓
handle_bg_submit_arlo_o3_voice
  resolve_o3_generate_mode → avatar_pro (default)
  subprocess arlo_avatar_beat_pipeline.py
       ↓
ElevenLabs TTS (unchanged text + voice profile path)
       ↓
LipSyncClient.submit_avatar_pro(still, audio, AVATAR_BEAT_PROMPT)
       ↓
poll → download → encode_delivery_video (voice_first_upscale)
       ↓
sidecar: kling_o3_video_path, kling_o3_mode=o3_avatar_pro_v1
```

**Jobs removed from hot path:** silent O3 submit, silent O3 poll, lipsync submit, lipsync poll, `encode_lipsync_input`.

---

## 5. Module layout (single contract surface)

| Module | Role |
|--------|------|
| **`beat_avatar_lipsync.py`** (new) | Constants: `AVATAR_USD_PER_SEC`, `estimate_avatar_pro_usd()`, `resolve_beat_avatar_still(beat, prod_root)`, `build_avatar_beat_prompt(beat, speaker)`, `KLING_O3_MODE_AVATAR = "o3_avatar_pro_v1"`. Shared by pipeline + handler budget gate. |
| **`arlo_avatar_beat_pipeline.py`** (new) | Subprocess entry: TTS → Avatar submit/poll/download → delivery encode → sidecar persist. Fork structure from `arlo_o3_voice_pipeline.py` (lock, attempt_id, persist, gallery upsert). |
| **`lipsync_sender.py`** | Existing `submit_avatar_pro()` — **no fork**; Beat Gen calls same method as Phase B. |
| **`video_delivery.py`** | Existing `encode_delivery_video(..., delivery_profile="voice_first_upscale")`. |
| **`beat_generator.py`** | Add `O3_GENERATE_MODE_AVATAR = "avatar_pro"`; extend `resolve_o3_generate_mode`, `infer_o3_option_pipeline_mode`, `VALID_GENERATION_MODES`, mismatch guards. |
| **`server_handlers/background.py`** | Route `avatar_pro` → `arlo_avatar_beat_pipeline.py`; budget preflight via `estimate_avatar_pro_usd(audio_dur)`. |
| **`arlo_o3_voice_pipeline.py`** | **Retained** for `MN_O3_GENERATE_MODE=voice_first` rollback only — not default. |
| **`kling_o3_element_beat_pipeline.py`** | **Retained** for `MN_O3_GENERATE_MODE=element_native` rollback only — not default. |

**Category rule:** One new pipeline file + one contract module — **not** a third branch inside `arlo_o3_voice_pipeline.py` (avoids O3+lipsync dead code in default path).

---

## 6. Constants (verified sources)

| Constant | Value | Source |
|----------|-------|--------|
| Endpoint | `https://api.wavespeed.ai/api/v3/kwaivgi/kling-v2-ai-avatar-pro` | `lipsync_sender.AVATAR_PRO_ENDPOINT` |
| Model id | `kwaivgi/kling-v2-ai-avatar-pro` | `lipsync_sender.AVATAR_PRO_MODEL` |
| `AVATAR_USD_PER_SEC` | `0.1122` | Measured Event_2 job $2.9257 / 26.074467s (`phase_b_avatar_lipsync.py`) |
| Min billed seconds | 5s | WaveSpeed model page pricing table |
| Transport | data-URI PNG + MP3 in POST JSON | Phase B probe + `submit_avatar_pro()` |
| Delivery profile | `voice_first_upscale` | `phase_module_lipsync_delivery.py`, `video_delivery.py` |
| Output dimensions | 1280×720 H.264 | Delivery encode contract |
| TTS | ElevenLabs v3 via existing `_write_elevenlabs_audio` | `arlo_o3_voice_pipeline.py` |

**Budget gate:** `estimate_avatar_pro_usd(ffprobe_duration(tts_audio))` at submit — **not** `COST_PER_LIPSYNC` ($0.35) and **not** `COST_PER_CLIP_KLING` ($0.26).

---

## 7. Still source + prompt

### 7.1 Still image

**Primary:** beat sidecar `reference_image.abs_path` (operator-locked character portrait) — same ref used for O3 `@Image1` today.

**Validation (submit-time, fail closed):**

1. File exists on disk.
2. `ensure_min_dimensions()` then `ensure_avatar_still_dimensions()` from `kling_startend_pipeline` — **1920×1080** scale-to-fit + pad via `video_delivery.LIPSYNC_INPUT_*` (same choke point as Phase A/B inside `LipSyncClient.submit_avatar_pro()`).
3. Optional: `char_ref_matches_element_images()` when speaker has Element binding — warn in UI, do not block v1 if portrait approved by operator.

**Not used for Avatar:** `bg_ref_image` as Avatar input (Avatar is portrait-only). Background motion comes from **prompt text**, not second image.

### 7.2 Prompt template (`build_avatar_beat_prompt`)

Derived from beat `kling_o3_prompt` with:

- Spoken dialogue stripped (reuse `_visual_prompt` / `extract_spoken_dialogue` patterns).
- **Tripod lock + frozen background** block (adapt `STATIC_BG_PROMPT` from Phase B — character name substituted via `kling_character_registry.kling_image1_speaker_label(speaker)`).
- Preserve emotion/staging hints from prompt box where they do not request camera motion.

**Example invariant lines (mandatory in template):**

- Tripod lock — zero pan/zoom/dolly.
- Background frozen except natural portrait motion (blink, breath, subtle gesture).
- No new objects / creatures / pop-in props.

---

## 8. Sidecar fields

### 8.1 Set on successful Avatar generate

| Field | Value / notes |
|-------|----------------|
| `kling_o3_video_path` | Delivery-encoded MP4 under `{event}/kling_o3_clips/` |
| `kling_o3_status` | `approved` |
| `kling_o3_mode` | `o3_avatar_pro_v1` (new) |
| `kling_o3_generate_mode` | `avatar_pro` |
| `generation_mode` | `avatar_pro` |
| `kling_o3_actual_duration_s` | ffprobe after encode |
| `kling_o3_voice_fix_*` | Mirror voice-first audit fields where applicable (audio path, duration, task_id, transport=`avatar_pro_data_uri`) |
| `kling_o3_options[]` | Upsert `{ source: "kling_o3_avatar_pro", label: "Avatar Pro (latest)", video_path }` |
| `arlo_visual_quality.method` | Updated string documenting Avatar path |

### 8.2 Preserved unchanged (export durability)

All fields in `SIDECAR_MERGE_PRESERVE_FIELDS` (`beat_generator.py`) — especially:

- `kling_o3_trim_start`, `kling_o3_trim_back`, `kling_o3_cut_*`
- `kling_o3_baked_path`, `kling_o3_still_stitch_approved`
- Intro roles: `intro_beat_role`, canonical mirror paths

### 8.3 Not written on new Avatar generates

| Field | Reason |
|-------|--------|
| `kling_o3_voice_fix_silent_video_path` | No silent O3 |
| `kling_o3_voice_fix_lipsync_input_path` | No Kling LipSync |
| `kling_o3_task_id` (O3) | Replace with `kling_o3_avatar_task_id` or reuse voice_fix task_id slot with `method=avatar_pro` |

### 8.4 Legacy clips

Gallery options from `voice_first` / `element_native` remain readable. `infer_o3_option_pipeline_mode()` extended:

| Path / source pattern | Mode |
|-----------------------|------|
| `_avatar_pro` or `kling_o3_avatar_pro` | `avatar_pro` |
| `_voice_lipsync` | `voice_first` (legacy) |
| `_element_o3` | `element_native` (legacy) |

**Mismatch guard:** `o3_option_matches_generation_mode()` — beat set to `avatar_pro` cannot export with Element clip selected without explicit operator override toast.

---

## 9. HTTP API surface

| Endpoint | Change |
|----------|--------|
| `POST /api/bg/submit-arlo-o3-voice` | Route `avatar_pro` → `arlo_avatar_beat_pipeline.py`; reject `still_insert` beats (unchanged). |
| `GET /api/bg/poll-arlo-o3-voice-status` | No schema change; reads sidecar job fields written by new pipeline. |
| `POST /api/bg/kling-o3-trim` | Unchanged — operates on `kling_o3_video_path` regardless of pipeline. |
| `POST /api/bg/set-pipeline` / `bg_set_pipeline` | Accept `avatar_pro`; **remove** voice_first/element_native from UI-exposed values (server still accepts for rollback tooling). |
| Send to Stitcher (`concat_kling_o3_approved_beats`) | Unchanged — exports trimmed delivery path; Avatar clips pass same gates as voice-first delivery clips. |

**Budget errors:** HTTP 402 with `audio_duration_s` + `cost` estimate when `estimate_avatar_pro_usd` exceeds remaining budget.

---

## 10. UI surface (`BgTab.tsx`)

| Element | v1 behavior |
|---------|-------------|
| Pipeline toggle (voice_first ↔ element_native) | **Removed** for speak beats |
| Generate button label | `Generate (Avatar Pro)` or plain `Generate` |
| Pipeline toast | Single line: ElevenLabs → Avatar Pro → 720 delivery |
| Character ref row | Unchanged — still required before Generate |
| BG ref row | Shown for prompt context; label clarifies Avatar uses portrait still only |
| Gallery option labels | `Avatar Pro (latest)` / `Avatar Pro gN` |
| Mismatch banner | Extended for `avatar_pro` vs legacy clip selection |
| Still insert beats | Unchanged UI (`render-still-clip`) |

**Phase B tab:** unchanged (already Avatar Pro).

---

## 11. Stage direction & background-only motion (deferred sub-spec)

**v1 behavior:** Beats with `beat_type=stage_direction` or speaker `[stage direction]` — **no Generate Avatar**; existing manual / magic overlay workflows.

**Future (`stage_direction_motion_v1`):** Silent O3 on `bg_ref_image` only (~5s), no character — **separate beat type**, not a fourth speak pipeline. Visible Magic overlays remain on composite preview (unchanged).

---

## 12. Job durability (category fix)

### 12.1 Problem class

Long-running Avatar jobs (124s stem ≈ 30–60 min; beats ≈ 5–15 min) must survive:

- Subprocess parent exit / nohup failures
- Server restart
- Operator closing browser tab

### 12.2 Beat Gen requirements

| Mechanism | Requirement |
|-----------|-------------|
| Subprocess | Detached with log file under `{event}/arlo_o3_jobs/{job_id}_{beat_id}.log` (existing pattern) |
| Sidecar heartbeat | `kling_o3_voice_fix_phase` + `kling_o3_voice_fix_updated_at` during poll (existing) |
| **`--resume-task-id`** | Production runners (`run_phase_b_avatar_full_stem_production.py` — **already added**) and beat pipeline must support resume without double submit |
| Server poller | Existing O3 job poll sweep picks up in-flight Avatar beats by `task_id` if subprocess dies — extend `recover_stuck_tasks` / poll handler to treat `o3_avatar_pro_v1` like voice-first phases |

### 12.3 Phase B production runner

`run_phase_b_avatar_full_stem_production.py`:

- `--resume-task-id TASK` — poll/download/pin only (no second billing).
- Logs to operator-specified path; exit non-zero on vendor `failed`.

---

## 13. Delivery encode (shared choke point)

All Avatar outputs — Beat Gen and Phase B — pass:

```python
encode_delivery_video(
    src, dst,
    include_audio=True,
    sharpen=True,
    delivery_profile="voice_first_upscale",
)
```

**Kid-facing gate:** min dimension ≥720 after encode (`phase_module_lipsync_delivery.finalize_phase_module_lipsync_delivery` for module; inline in beat pipeline for Beat Gen — same ffmpeg recipe).

**Stitcher lean bake:** `module_final_lean` downstream — unchanged.

---

## 14. Rollback

| Layer | Mechanism |
|-------|-----------|
| Env | `MN_O3_GENERATE_MODE=voice_first` or `element_native` forces legacy subprocess |
| Per-segment | Sidecar `segments.{key}.o3_generate_mode` override (existing) |
| Git | Revert spec implementation commit |
| Data | Legacy clips remain in gallery; no sidecar migration required |

**UI rollback:** Re-expose toggle only if env `MN_BG_SHOW_LEGACY_PIPELINE=1` (optional dev flag) — not shipped to Kim by default.

---

## 15. Migration phases

| Phase | Action | Proof |
|-------|--------|-------|
| **M0** | Ship this spec + Phase B full-stem pin on Event_2 | ffprobe duration parity audio/video; freeze detect 0 events |
| **M1** | Implement `beat_avatar_lipsync.py` + `arlo_avatar_beat_pipeline.py`; default `resolve_o3_generate_mode` → `avatar_pro` for all speak beats | pytest mocked submit; one live beat on Event_2 intro |
| **M2** | UI toggle removal + label updates | Browser smoke Bg tab Generate |
| **M3** | Regenerate intro speak beats on Event_2; Send to Stitcher | Concat duration + beat count |
| **M4** | Hide Element native from UI; document env rollback | grep handler routes |
| **M5** | Delete dead hot-path code only after 30 days no legacy generates | git archaeology |

---

## 16. 3×3 agent debate (binding verdicts)

### Axis 1 — Replace vs add third pipeline

| Agent | Position |
|-------|----------|
| A — Add `avatar_pro` toggle beside voice_first and element_native | Three-way UI complexity |
| B — Replace default speak path; legacy env-only | Category fix |
| C — Avatar only on Phase B | Leaves Beat Gen broken cost/quality |

**Verdict: B**

### Axis 2 — Pipeline file strategy

| Agent | Position |
|-------|----------|
| A — Branch inside `arlo_o3_voice_pipeline.py` | Keeps O3+lipsync imports in default path |
| B — New `arlo_avatar_beat_pipeline.py` | Clean subprocess; shared TTS helpers imported |
| C — Inline in `background.py` handler | Untestable monolith |

**Verdict: B**

### Axis 3 — Endpoint naming

| Agent | Position |
|-------|----------|
| A — New `/api/bg/submit-avatar-beat` | Operator retraining |
| B — Keep `/api/bg/submit-arlo-o3-voice` | Same Generate button wiring |
| C — Rename to `/api/bg/submit-speak-beat` | Wide breaking change |

**Verdict: B**

### Axis 4 — Still source

| Agent | Position |
|-------|----------|
| A — Extract first frame from last O3 clip | Reintroduces motion artifacts |
| B — Beat `reference_image` portrait | Operator already locks this |
| C — Registry refer_images[0] only | Ignores per-beat lock box |

**Verdict: B** (with registry validation warnings)

### Axis 5 — Background motion in Avatar

| Agent | Position |
|-------|----------|
| A — Also submit bg_ref to Avatar API | API is portrait-only (image + audio) |
| B — Prompt-locked frozen BG | Phase B proven pattern |
| C — Composite O3 bg plate under Avatar | Two vendor jobs — defeats simplification |

**Verdict: B**

### Axis 6 — Spend tracking

| Agent | Position |
|-------|----------|
| A — `COST_PER_LIPSYNC` | Wrong by ~40× |
| B — `AVATAR_USD_PER_SEC × audio_duration` | Matches WaveSpeed bill |
| C — Flat $0.56/beat | Wrong for 10s beats |

**Verdict: B**

### Axis 7 — Gallery / export compatibility

| Agent | Position |
|-------|----------|
| A — New sidecar root field `avatar_video_path` | Breaks Stitcher export |
| B — Reuse `kling_o3_video_path` + mode discriminator | Export unchanged |
| C — Dual-write both paths | Drift class |

**Verdict: B**

### Axis 8 — Tests

| Agent | Position |
|-------|----------|
| A — Manual only | No CI regression |
| B — Mock `submit_avatar_pro` + handler + sidecar field contract tests | CI-safe |
| C — Live Avatar in CI | Forbidden cost |

**Verdict: B** + one live beat in full QA manual pass

### Axis 9 — element_native retirement

| Agent | Position |
|-------|----------|
| A — Delete immediately | Breaks old clip audit |
| B — Soft-retire (hide UI, env rollback) | Safe migration |
| C — Keep Element as equal toggle | Per Kim direction — rejected |

**Verdict: B**

---

## 17. Integration checklist (multipass — all must pass)

### 17.1 Code routing

- [ ] `resolve_o3_generate_mode()` returns `avatar_pro` for speak beats (default)
- [ ] `handle_bg_submit_arlo_o3_voice` launches `arlo_avatar_beat_pipeline.py` when mode=`avatar_pro`
- [ ] `still_insert` beats still route to `render-still-clip` only
- [ ] Canonical mirror beats reject Generate overwrite

### 17.2 Vendor

- [ ] `submit_avatar_pro()` used — no `LipSyncClient.submit(video, audio)` on default path
- [ ] No silent O3 submit on default path
- [ ] Poll uses `kling_poll_fresh` / predictions endpoint

### 17.3 Delivery

- [ ] Output ffprobe: 1280×720, duration ≈ TTS audio (±0.5s)
- [ ] `voice_first_upscale` in delivery metadata
- [ ] Sharpen=True on finalize (parity Phase B + beat gen)

### 17.4 Export

- [ ] `materialize_kling_o3_trimmed_clip` applies when trim active
- [ ] Send to Stitcher concat count unchanged for regenerated module
- [ ] Intro penultimate fades still apply on BG export (canonical tail exception)

### 17.5 UI

- [ ] Bg tab Generate works without pipeline toggle
- [ ] Preview plays audio+video in sync (same file)
- [ ] No overlay geometry regression (`phaseWatercolorOverlayGeometry` — Phase B only, but verify no shared CSS break)

### 17.6 Phase B (parallel track — no regression)

- [ ] Event_2 `phase_b_lipsync_route=single_full_stem_v1`
- [ ] Phase B Send for Lipsync still uses Avatar (handler unchanged)
- [ ] Full-stem MP4 freeze detect: 0 events ≥2s static video with continuous audio

### 17.7 Durability

- [ ] `--resume-task-id` on full-stem runner prevents double billing
- [ ] Dropbox mirror parity script exit 0 after deploy
- [ ] `curl` storyboard `build-sha` == `git rev-parse --short HEAD`
- [ ] Server HTTP 200 on event port

---

## 18. Verification commands (copy/paste proof)

```bash
# Unit (tooling)
cd ~/Projects/mindfulnest-tooling/Production/tools
python3 -m pytest tests/test_phase_b_avatar_lipsync.py tests/test_voice_first_generate_mode.py -v
# After implementation add:
# tests/test_beat_avatar_pipeline.py

# Phase B full-stem on-disk proof
EVENT=~/Library/CloudStorage/Dropbox/Claude\ Mindfulnest\ Project\ Files/Production/Event_2
python3 -c "import json; s=json.load(open('$EVENT/production_state.json')); print(s.get('phase_b_lipsync_route'), s.get('phase_b_lipsync_file'))"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \
  "$EVENT/$(python3 -c "import json; print(json.load(open('$EVENT/production_state.json'))['phase_b_lipsync_file'])")"

# Freeze detect (category: no hold-frame assembly on full stem)
# use project freeze script or ffprobe scene detect — expect 0 gaps

# Deploy
cd ~/Projects/mindfulnest-tooling
bash Production/scripts/deploy_storyboard_v59.sh
curl -s "http://localhost:5112/?event=Event_2" | grep -o 'build-sha:[^"<]*'

# Browser smoke
# Open http://localhost:5112/?event=Event_2 → Phase B tab
# Confirm: lipsync file name, route single_full_stem_v1, preview plays without statue freeze
```

---

## 19. Test matrix (pytest — implement with M1)

| Test | Asserts |
|------|---------|
| `test_resolve_o3_generate_mode_default_avatar` | Speak beat → `avatar_pro` |
| `test_still_insert_not_avatar` | still_insert → `still_insert` |
| `test_estimate_avatar_beat_cost` | 7.4s → ~$0.83 |
| `test_avatar_pipeline_mock_submit` | Sidecar `kling_o3_mode=o3_avatar_pro_v1` |
| `test_infer_o3_option_avatar_path` | `_avatar_pro` path classifies correctly |
| `test_export_trim_preserved_avatar` | Trim fields survive merge on Avatar beat |
| `test_handler_routes_avatar_script` | background.py references `arlo_avatar_beat_pipeline.py` |
| `test_no_lipsync_submit_in_avatar_pipeline` | Source grep: no `submit(lipsync_input` in new pipeline |
| `test_phase_b_unchanged_handler` | phases.py still `submit_avatar_pro` |

---

## 20. Cost model (WaveSpeed only, per speak beat)

| Pipeline | Formula (typical 7s speech) |
|----------|----------------------------|
| voice_first | O3 bucket (~11s)×$0.112 + $0.35 lipsync ≈ **$1.58** |
| avatar_pro | max(5s, audio)×$0.112 ≈ **$0.78** |
| element_native | Similar O3 native voice billing — **retired** |

ElevenLabs cost unchanged (~$0.02/beat estimate).

---

## 21. Open items (explicit — not hidden)

| Item | Owner | Blocking M1? |
|------|-------|--------------|
| Stage direction bg-motion spec | Future spec | No |
| Per-character default Avatar prompt tuning | Operator + prompt box law | No — v1 uses template |
| Multi-speaker beat (two characters) | Product call | Yes for **those beats only** — v1 assumes single speaker portrait |
| Avatar vertical vs 16:9 module delivery | Delivery encode letterboxes to 1280×720 | Verify on first live beat |

---

## 22. Document history

| Date | Change |
|------|--------|
| 2026-06-24 | v1 initial — Beat Gen Avatar default spec; Phase B full-stem resume flag; integration matrix |
