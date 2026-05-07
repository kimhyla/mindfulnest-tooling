# Governance checklist — `kling_startend_pipeline.py`

**Directus decisions:** 172 (`KLING_STARTEND_V1_CAPABILITY`), 177 (`KLING_STARTEND_V1_VALIDATED`).
**Governing rules:** CLAUDE.md Rule 6 (image sizing), Rule 8.1 (anti-lipsync), Rule 8.2 (lipsync source requirements), Rule 8.3 (start-end pipeline), Rule 8.4 (silence compression), Rule 11 (source fidelity), Rule 18 (two-write), Rule 19 (no shortcuts), Rule 20 (auto-capture).

Per CLAUDE.md Rule 17, read this checklist before running `tools/kling_startend_pipeline.py`. Confirm each locked decision applies (or explicitly does not) before acting.

---

## Pre-run checklist (verify before submitting)

- [ ] **§8.3 routing decision (LD-180 universal default).** Before invoking `kling_startend_pipeline.py`, confirm routing per CLAUDE.md §8.3:
  - Event_1 (Tessa + Chipper): start-end pipeline is the **UNIVERSAL DEFAULT** for ALL beats (decision 180). Use legacy single-image Kling ONLY if `state.beats[beat].force_legacy: true` is explicitly set.
  - Other modules (Luna, Benson, Ember, Bramble, Bork, Arcs 2+): start-end is NOT yet validated per-creature; first Generate B+C on a new creature is implicitly a V2 validation test. Monitor first-beat output for LatentSync starvation or character drift; set `force_legacy: true` and escalate per-creature if needed.
  - Action beats where gaze isn't critical (Bramble knocking, Bork loudspeaker): use default `_handle_animate` + §8.4 silcomp only; do NOT route through start-end pipeline.
- [ ] **Beat is V1-scoped.** V1 is validated for Tessa-style single-creature closed-mouth dialogue beats ONLY. If the beat is:
  - **Luna** (owl, wing motion, sometimes open beak) → still V2; get explicit Kim approval before running.
  - **Benson** (deer, courage beat, forward momentum) → still V2.
  - **Any action beat** (Bramble knocking, Bork loudspeaker) → use default `_handle_animate` + silcomp audio (§8.4 only, no start-end).
  - **Any creature with open-mouth expression requirement** (Luna "Owl Peace Prize") → NOT SUPPORTED. Violates §8.1 beak/mouth closed requirement. Defer to V2.
- [ ] **Start image resolves cleanly.** `production_state.image_overrides[beat_id]` returns a known key, or storyboard L[] has the `i:` field populated, OR user passed `--end-image` explicitly.
- [ ] **End-frame prompt is appropriate for the creature's emotional arc.** Default is Tessa-specific; all other beats require `--end-prompt` CLI override.
- [ ] **Anti-lipsync baseline intact (§8.1):** `sound: false`, Rule 8 negative_prompt present, `cfg_scale: 0.5` (Rule 8.2 forbids deviation for lipsync-targeted clips).
- [ ] **Positive prompt contains NONE of** `"minimal motion"`, `"static camera"`, `"head remains facing forward"`, `"no head movement"`, `"frozen face"`, `"eyes meet camera"`, `"face centered"`, `"direct forward gaze"`, `"looking at camera"`, `"mouth pressed"`, `"mouth sealed"`, `"mouth tight"`, `"mouth clamped"`. If any present → §8.2 do-not-stack violation. Abort.
- [ ] **Kontext end-frame prompt starts with** `"Same character, same outfit, same lighting, same art style."` to anchor character identity. If missing, character drift risk is high.
- [ ] **Preserve-before-change intent:** prior `beats.beat_NN.lipsync.file` is preserved to `preserved_winners/` before state mutation. Script handles this automatically; verify after run.

## During-run checklist (what the script enforces automatically)

- [x] Rule 6 auto-upscale on both start + end frames to ≥600px shortest side (`ensure_min_dimensions`).
- [x] Fresh `http.client` connection per Kling poll (decision 137 pattern, urllib-stuck-state workaround).
- [x] Silence-compression audio preprocessing per §8.4 (`silcomp_audio_if_needed`).
- [x] Video trim to `audio_duration + 0.4s` tail room before lipsync submission (§8.4 target).
- [x] Preserve raw Kling + end frame + final lipsync to `preserved_winners/` with TS-stamped names.
- [x] State update via atomic tmp+rename — NOT direct `production_state.json` write.
- [x] Directus `prod_activity_log` write on submission + completion (Rule 18 two-write).
- [x] New option appended to `phase_1.options[]` with `source: "kling_startend"` provenance field (state-shape stability per decision 172).

## Post-run checklist (before promoting output to live)

- [ ] **Kim playback-verified** the full clip. Critical checks:
  - Opening phrase lipsyncs (no settling-window gap)
  - Tail phrase lipsyncs (no drift-region gap)
  - Character identity visually preserved start → end (no FLUX Kontext style drift)
  - Gaze direction is acceptable (camera-facing or close enough)
  - No uncanny-valley motion, no frozen frames, no "stamp giving up" regions
- [ ] **File-level sanity:** lipsync output size should be ≥ 800 KB for Tessa-style beats (empirical floor from decision 177 — 957 KB was first working start-end, silcomp baseline is 808 KB). Smaller file = potential LatentSync starvation.
- [ ] **State consistency:** `phase_1.selected_option` points to the new option index; `lipsync.source_option` matches; `lipsync.source_changed = False`.
- [ ] **Promotion to live:** `animation_clips/beat_NN_lipsync.mp4` swapped ONLY after Kim approval. Prior version preserved to `preserved_winners/` with clear naming.

## Failure recovery

- **FLUX Kontext returns style-drifted end frame:** output visible in opened Preview window. Abort with Ctrl-C before Kling submit; re-run with `--end-prompt` tuned OR `--end-image` hand-picked.
- **Kling poll stalls** (WaveSpeed congestion, tonight's pattern): fresh-connection pattern retries automatically; if it truly times out, task_id is logged — use `recover_stuck_tasks.py` to recover via CDN direct-pull (decision 131).
- **ByteDance LipSync drops opening or tail:** means even start-end pinning wasn't enough for this beat. Creature/beat may not be V1-compatible. Document at `prod_activity_log` and defer to V2 treatment.
- **State write collision with running production server:** unlikely (tool uses atomic tmp+rename) but check for `.bak_kling_startend_*` backup after run; restore if needed.

## V2 roadmap (not implemented)

1. Automated Kontext output consistency gate (SSIM or CLIP embedding similarity vs start frame).
2. Per-beat emotion-arc schema in Directus `prod_modules` or new `prod_beat_arcs` collection.
3. Action-beat support via pose-reference images.
4. Open-mouth creature support (Luna, excited-state beats) — requires relaxing Rule 8.1 for specific creatures, which itself requires new locked decision.
5. 5s Kling test clip for end-frame pose-compatibility check before full 10s submit.
6. Integration with `recover_stuck_tasks.py` for seamless CDN recovery.

---

*Changes to this file cascade: update CLAUDE.md Rule 8.3 + PIPELINE_BRAIN §19 simultaneously. Register amendment in Directus `prod_locked_decisions` per Rule 18.*

## Locked Architecture Constraints (added 2026-04-18, task_id: size-budget-arch-cascade-1caa1e0b)

Before producing ANY deliverable, verify:

- [ ] **Single-MP4 atomic (RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1):** Output is ONE MP4 file per module/event with all audio + video + animations baked in. No separate audio track. No separate overlay file. No multi-file deliverable.
- [ ] **No runtime TTS (NO_RUNTIME_TTS_PERSONALIZATION_V1):** Rendered audio contains NO personalization variables (`{childName}`, `{therapistName}`, `{parentTitle}`, `{parentName}`, `{chosenGuideName}`, pronouns). All spoken content is universal phrasing. ElevenLabs runs ONCE per module in the production pipeline; never at runtime from the app.
- [ ] **Arc-aware sizing (CATALOG_DELIVERY_ARC_AT_A_TIME_V1 + LD-283 SIZE_BUDGET_PER_MODULE_V1):** Per-module target ≤ 60 MB with **80 MB hard ceiling** (LD-283 supersedes the audit's preliminary 100 MB number per the 4-agent debate documented in LD-283 decision_text). Per-clip video bitrate ≤ 1.5 Mbps motion / 1.0 Mbps static; HARD ceiling 2.0 Mbps with ffprobe assertion ≤1,900,000 bps post-encode (SIZE_BUDGET_VIDEO_V1). If exceeded, either compress before registering or file a `SHORTCUT_SIZE_OVERRIDE_*` (or `SHORTCUT_MODULE_{id}_CEILING_V1` for per-module) escape-hatch decision with Kim's approval.
- [ ] **Transparent MP4 loops (if used for characters/breathing circle):** BAKED INTO the atomic module MP4 at production time. Not layered at runtime. Reference: LD-128 2026-04-18 appendix.
- [ ] **Tool-layer enforcement (per Rule 19 addendum):** ffmpeg/cwebp/ElevenLabs command flags in this governance file are the enforcement point — hardcode bitrate and format ceilings here. Phase 0 prose gate is a reminder, not enforcement.

If ANY box cannot be checked, STOP. Either adjust the plan to comply OR file a `SHORTCUT_*` Directus decision with Kim's explicit approval.

Reference: `APP_ARCHITECTURE_MASTER_v1.md`, `SIZE_BUDGET_AUDIT_20260418.md`, preflight id=84.
