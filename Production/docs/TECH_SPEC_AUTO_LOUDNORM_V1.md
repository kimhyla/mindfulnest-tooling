# TECH SPEC — Auto Loudnorm (v1)

**Status:** Spec only — no implementation in this pass (avoid merge conflict with parallel stitch work).

**Owner surface:** mindfulnest-tooling — Beat Gen export + Stitcher bake pipeline.

**Problem:** Perceived loudness varies across beats inside a module (e.g. Event_3 intro: Kling Element-native VO vs ElevenLabs muxed hand shots). Today there is **no automatic** speech leveling on Send to Stitcher or Bake final MP4. Manual per-slot Loudnorm exists in Stitcher UI but is opt-in.

**Non-goals (v1):**
- Changing canonical ambient bed level (`STITCH_AMBIENT_BED_VOLUME = 0.15`) or default SFX cue volume (`0.45`).
- Re-leveling ambient/SFX source files in `sound_library/`.
- Replacing operator trim, crossfade, or MODULE_FINAL_LEAN encode behavior.

---

## 1. Current pipeline (reference)

### 1.1 Beat Gen → Send to Stitcher (intro / resolution slot)

```
approved beat MP4s
  → resolve_segment_stitch_export_clip_paths (per-beat trims)
  → _ffmpeg_concat_kling_clips_reencode | _ffmpeg_concat_kling_clips_with_pair_fades
  → assembled/{slot}_kling_o3_{ts}.mp4   # speech baked in video audio; no ambient/SFX
```

Concat audio lane: mono resample + micro join fades only (`_kling_export_audio_lane_filter`). **No loudnorm.**

### 1.2 Stitcher slot → Bake final MP4

Per slot (`_stitch_build_pipeline`):

```
slot.video_path
  → (1) _stitch_normalize_slot     # LD-284 video delivery (scale/fps/codec) — NOT loudness
  → (2) _stitch_ensure_audio        # audio stream parity
  → (3) _stitch_mix_slot_audio      # speech [0:a] + ambient bed + SFX cues → se_slot_*.mp4
  → concat slots (+ transitions)
  → encode_module_final_lean        # bitrate/size cap — NOT loudness
```

### 1.3 Manual Loudnorm today (Stitcher UI)

`POST /api/stitch_editor/loudnorm` on **`slot.video_path`** (pre-pipeline source):

- `ffmpeg -af loudnorm=I=-19:TP=-1.5:LRA=11 -c:v copy`
- Marks path in `loudnorm_already_applied_paths`; slot shows `loudnorm_already_applied ✓`
- Runs **before** ambient/SFX mix when operator assigns the `_ln.mp4` output back to the slot (or replaces source)

### 1.4 Existing speech-only loudnorm (lipsync / TTS prep — not stitch bake)

`production_server._silcomp_audio(..., loudnorm=True)` uses:

```
dynaudnorm=f=200:g=5:p=0.95:m=15,
loudnorm=I=-16:TP=-1.5:LRA=8
```

That path is for **TTS/mp3** before ByteDance/Kling lipsync — **out of scope** for stitch auto-loudnorm v1 unless we explicitly align targets.

---

## 2. Two loudness problems (do not conflate)

| Layer | Symptom | Example | Best fix layer |
|-------|---------|---------|----------------|
| **A — Within-slot beat bus** | Adjacent beats in one intro MP4 differ (Kling vs ElevenLabs mux) | Event_3 beats 7–9 vs 10–11 inside `intro` slot | **Per-beat** leveling before Beat Gen concat |
| **B — Cross-slot module bus** | `intro` slot hotter/quieter than `phase_a` / `phase_b` / `resolution` | Whole-module perceived level | **Per-stitch-slot** leveling before ambient/SFX mix |

Auto loudnorm v1 should address **both**, at the correct insertion points. Fixing only layer B does not fully solve Kim’s Event_3 intro beat-to-beat issue.

---

## 3. Ratio Contract (frozen)

**Token:** `STITCH_AUDIO_RATIO_CONTRACT_V1`

This is the accepted operator mix pattern — ambient **under** speech, SFX **above** ambient as accents. Auto loudnorm v1 **must not alter these ratios** in the audio that ships in the **final bake MP4**.

### 3.1 Canonical linear gains (ffmpeg `volume` before `amix`)

| Bus | Default gain | Code constant | Perceived role |
|-----|--------------|---------------|----------------|
| **Speech / dialogue** | **1.0** | base lane `[0:a]` | Primary — loudest bus |
| **Ambient bed** | **0.15** | `STITCH_AMBIENT_BED_VOLUME` | Under-speech bed (ST-004 gate) |
| **SFX cue** | **0.45** | `STITCH_SFX_CUE_DEFAULT_VOLUME` | Event accents — louder than bed, not drowning speech |

Per-cue SFX may override `0.45` in slot JSON; ambient may override `0.15` via slot `ambient_volume`. **Defaults are frozen** for auto-loudnorm v1 unless a separate product spec changes them.

Mix sum:

```text
amix(inputs=speech + bed? + cues…, normalize=0)
```

`normalize=0` means ffmpeg does **not** rebalance inputs — the table above **is** the ratio contract.

### 3.2 Where the contract is baked (unchanged by this spec)

| Stage | Output | Ratio contract |
|-------|--------|----------------|
| `_stitch_mix_slot_audio` | `se_slot_*.mp4` | **Baked here** — speech + 0.15 bed + 0.45 SFX |
| Slot concat + transitions | pipeline master | Passthrough — no new gain stage |
| `encode_module_final_lean` | `*_final.mp4` | AAC re-encode only — **no** loudnorm, **no** gain change |

**Final bake inherits the mix baked at `se_slot_*`.** Lean encode must not insert loudnorm, `dynaudnorm`, or `amix normalize=1`.

### 3.3 What auto loudnorm may change vs must not

| May change | Must not change |
|------------|-----------------|
| **Absolute level** of the speech bus before mix (target −19 LUFS integrated) | `ambient_volume` default **0.15** |
| Beat-to-beat / slot-to-slot speech consistency | SFX cue default **0.45** |
| | **Order:** speech level → then bed/SFX at fixed gains |
| | **Relative pattern:** speech > SFX > ambient (typical moment) |
| | Post-mix loudnorm on `se_slot_*` or final module MP4 |

### 3.4 Invariant (implementation gate)

> After auto loudnorm + bake, an A/B mux using the **same** slot `ambient_bed` / `sfx_cues` JSON as today must produce the **same** ffmpeg filter gains (`volume=0.150` on bed, `volume=0.450` on default cues). Only the speech input amplitude to that graph may differ (leveled).

### 3.5 Regression anchors

- **ST-004** — ambient must not read louder than speech (canonical 0.15 gate).
- **ST-003 / ambient merge** — slot saves must not wipe beds when releveling speech.
- Acceptance §9.2–9.3 — ear + A/B against pre-auto mux with identical cue JSON.

---

## 4. Ambient beds & SFX — interaction rules (CRITICAL)

### 4.1 How mix works today

`_stitch_mix_slot_audio` / waveform mix:

```text
mix_inputs = [base_audio]           # [0:a] from normalized slot video (speech/dialogue)
           + [bed]                   # ambient at ambient_volume (default 0.15)
           + [cue0..cueN]            # each SFX at cue.volume (default 0.45)
amix=...:normalize=0                # NO auto gain — relative levels are literal
```

Canonical design: ambient is **under-speech** at fixed ratio; SFX are event accents at fixed ratio.

### 4.2 What happens if we loudnorm the wrong thing

| Loudnorm target | Effect on ambient/SFX | Verdict |
|-----------------|----------------------|---------|
| **Speech lane only** (video audio before mix) | Ambient still added at 0.15 × normalized speech; SFX still at 0.45 × normalized speech. **Preserves designed ratios.** | ✅ Required |
| **Whole slot after ambient+SFX mix** (`se_slot_*.mp4`) | Integrated loudnorm sees speech+bed+SFX together. Quiet bed gets pulled up; SFX peaks drive limiter; **breaks 0.15 under-speech contract.** | ❌ Forbidden |
| **Final module bake output** | Same problem at module scale; also invalidates stitch cache lineage. | ❌ Forbidden v1 |
| **Ambient bed source file** | Decouples bed from speech forever; wrong when speech is re-leveled. | ❌ Forbidden |

### 4.3 Rule (v1 invariant)

> **AUTO_LOUDNORM_V1:** Apply loudness processing only to the **speech/dialogue audio embedded in the slot video** (or per-beat clip pre-concat). Ambient beds and SFX are mixed **after** speech leveling, using existing `ambient_volume` and cue `volume` — unchanged.

### 4.4 Operator-visible guarantee

After auto loudnorm:

- Ambient bed slider semantics unchanged (0.15 still means “15% of linear mix input”).
- SFX cue volume semantics unchanged.
- Waveform / mux preview must rebuild from new speech level + same bed/SFX recipe (cache bust required).

---

## 5. Proposed insertion points

### 5.1 Layer A — Per-beat (Beat Gen export)

**When:** Inside `resolve_segment_stitch_export_clip_paths` or immediately before each clip enters `_ffmpeg_concat_kling_clips_*`.

**Input:** Approved beat delivery MP4 (speech in `a:0`).

**Output:** Cache file e.g. `{beat_id}_speech_ln_{hash}.mp4` (video copy or re-mux).

**Filter:** Single-pass `loudnorm` on audio only (see §6). Optional v1.1: `dynaudnorm` for beat clips with wide internal dynamic range — **not required for v1**.

**Skip when:**
- Clip has no audio stream (inject anullsrc path unchanged).
- Beat already marked `speech_loudnorm_applied` with matching source hash (idempotent).

**Cache key includes:** source path, mtime, trim args, loudnorm recipe version.

### 5.2 Layer B — Per-stitch-slot (Stitcher pipeline)

**When:** After `_stitch_normalize_slot` + `_stitch_ensure_audio`, **before** `_stitch_mix_slot_audio`.

**Input:** `norm_path` (LD-284 normalized slot video; speech only if slot came from Beat Gen export).

**Output:** `se_speech_ln_{hash}.mp4` or in-place replace norm_path for downstream mix.

**Filter:** Same loudnorm params as §6.

**Skip when:**
- `slot.loudnorm_already_applied` true AND source hash matches (upgrade manual flag).
- Slot has no audio (pass-through to mix).

**Default:** Auto-on for bake + export hydration; manual Loudnorm button becomes “re-run / force” (or hidden when auto satisfied).

### 5.3 Ordering diagram

```text
[LAYER A — Beat Gen]
  beat delivery MP4
    → (NEW) speech loudnorm per beat
    → concat → intro slot video_path

[LAYER B — Stitcher]
  slot video_path
    → normalize (video spec)
    → ensure audio
    → (NEW) speech loudnorm          ← only if Layer A skipped or slot not from Beat Gen
    → mix ambient (0.15) + SFX (0.45)
    → concat slots → bake lean encode
```

**Recommendation:** Implement **Layer A first** for intro/resolution slots fed by Send to Stitcher; Layer B as safety net for phase slots, standalone, and legacy paths without per-beat export.

---

## 6. Loudnorm parameters (v1)

Align with existing manual stitch loudnorm (operator-familiar):

| Param | Value | Source |
|-------|-------|--------|
| Integrated target `I` | **-19 LUFS** | `handle_stitch_loudnorm` default |
| True peak `TP` | **-1.5 dBTP** | same |
| Loudness range `LRA` | **11 LU** | same |

Implementation:

```bash
-af "loudnorm=I=-19:TP=-1.5:LRA=11:print_format=summary" -c:v copy
```

**Do not** use lipsync `dynaudnorm+loudnorm@−16` on stitch speech bus without listening tests — different target and dynamics.

**Recipe version string:** `STITCH_SPEECH_LOUDNORM_V1` — include in all cache keys and sidecar metadata.

---

## 7. State & cache invalidation

### 7.1 New metadata fields (proposed)

**Beat sidecar (optional, Layer A):**

```json
{
  "speech_loudnorm_applied": true,
  "speech_loudnorm_recipe": "STITCH_SPEECH_LOUDNORM_V1",
  "speech_loudnorm_source_hash": "<md5 of pre-ln video>",
  "speech_loudnorm_at": "<iso8601>"
}
```

**Stitch slot (extend existing):**

```json
{
  "loudnorm_already_applied": true,
  "loudnorm_recipe": "STITCH_SPEECH_LOUDNORM_V1",
  "loudnorm_source_hash": "<hash of norm_path pre-ln>"
}
```

### 7.2 Cache bust triggers

Re-run speech loudnorm when any of:

- Source video mtime/hash changes (re-export, re-import beat).
- Trim window changes (`trim_in_ms` / `trim_out_ms`).
- Recipe version bumps.
- Operator “Force relevel” action.

Must invalidate downstream:

- `se_slot_*` mux cache (ambient/SFX mix hash includes norm mtime today — confirm after speech-ln insert).
- `stitch_audio_*` waveform mux artifacts.
- `stitch_preview_*` / playback artifact URLs.

---

## 8. API / UX (minimal)

- **No new operator toggle required for v1 default-on** inside bake/export paths.
- Stitcher slot tag: `speech loudnorm ✓` (rename from `loudnorm ✓` for clarity).
- Manual **Loudnorm** button: retained as **force relevel**; clears `loudnorm_already_applied` and requeues Layer B.
- Send to Stitcher: no UI change; log line per beat: `[export] speech loudnorm beat_10 ok`.

---

## 9. Acceptance criteria

1. **Beat-to-beat:** Event_3 intro — hand-shot ElevenLabs beats within ~2 LU of adjacent Kling Element-native beats (ear test + ffprobe `ebur128` spot-check on 3s windows).
2. **Ratio contract (§3):** After auto loudnorm + final bake, default mux graph still uses `volume=0.150` bed and `volume=0.450` default SFX; `amix normalize=0` unchanged.
3. **Ambient contract:** Intro slot with default ambient bed — bed still clearly under speech; `ST-004` regression does not return.
4. **SFX contract:** Head whoosh + resolution tail SFX unchanged in relative prominence vs pre-auto baseline (A/B mux with same cue JSON).
5. **Idempotent:** Second bake without source changes does not re-encode speech loudnorm (cache hit).
6. **No double-apply:** Manual loudnorm + auto path cannot stack (hash gate).
7. **CI:** Unit test — mix filter receives speech-ln norm_path; assert ambient `volume=0.15` unchanged in filter graph.

---

## 10. Implementation phases (for other session)

| Phase | Scope | Risk |
|-------|-------|------|
| **P0** | Layer A in `concat_kling_o3_approved_beats` export path + cache | Low — speech-only, pre-ambient |
| **P1** | Layer B hook in `_stitch_build_pipeline` pre-mix | Medium — touch hot bake path |
| **P2** | Migrate manual loudnorm to same helper; deprecate duplicate ffmpeg block | Low |
| **P3** | Optional `ebur128` QA script on assembled intro | Ops only |

**Files (expected touch list — do not implement here):**

- `beat_generator.py` — per-beat speech loudnorm helper + export hook
- `server_handlers/stitch_editor.py` — shared `apply_speech_loudnorm_to_mp4()`
- `production_server.py` — `_stitch_build_pipeline` pre-mix call
- `storyboard-v2/.../StitcherTab.tsx` — label/copy only
- Tests: `test_kling_o3_concat_export.py`, `test_stitch_slot_media_artifacts_v1.py`, new `test_speech_loudnorm_v1.py`

---

## 11. Open questions (resolve before P1)

1. **Layer A only vs A+B both on intro:** If A runs at export, is B redundant for intro slot? (Recommend: B skip when export manifest records all beats speech-ln at same recipe.)
2. **Silent / music-only clips:** Confirm pass-through without marking applied.
3. **Crossfade intro tails:** Loudnorm before or after pair-fade concat? (Recommend: **per-beat before concat**; fades unchanged.)
4. **Standalone milestone slot:** Layer B only — confirm no Beat Gen concat.

---

## 12. Summary answer for operators

> **Will final bake normalize volume?**  
> Not today. This spec adds **automatic speech loudnorm** at export (per beat) and/or stitch (per slot), **before** ambient beds and SFX are mixed in.
>
> **Will final bake preserve the speech / ambient / SFX pattern?**  
> **Yes.** §3 **Ratio Contract** is frozen: speech **1.0**, ambient **0.15**, SFX **0.45** (linear gains, `amix normalize=0`), baked at slot mix and carried through lean encode unchanged. Auto loudnorm only levels the speech bus first; beds and SFX keep the same multipliers, so the under-speech / accent-SFX pattern you approved is preserved in the shipped module MP4.
