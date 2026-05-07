# Kim Review Flags — Session 2026-04-22 04:09 Extended Persistence

Generated 2026-04-22 04:30 UTC by the extended-persistence run that followed the Phase A M1E1 panel pipeline lock session. This file flags items for Kim's review; it does NOT auto-edit governance files or memory files.

**NOTE ON LOCATION:** Task spec requested this file at `.claude/session_checkpoints/20260422_0409_kim_review_flags.md` but the sandbox denied write permission to `.claude/session_checkpoints/`. Placing it under `Production/` where writes are permitted. Move at your convenience.

---

## 1. Governance file review candidates (Rule 17)

Three governance files have candidate new rules surfaced by this session. None have been edited. Kim to decide whether to apply each, defer, or re-scope.

### 1a. `Production/governance/audio-producer_governance.md`

**Candidate new rule A — amix `normalize=0` default**
Source LDs: `AMIX_NORMALIZE_OFF_V1_20260421`, `FFMPEG_FORMAT_FORCE_MP3_V1_20260421`.
Proposed wording: "Every `amix` filter in production code MUST set `normalize=0` unless equal-weight 1/N averaging is explicitly desired. ffmpeg's default `normalize=1` silently scales explicit volume multipliers, causing inaudible-bed / halved-voice bugs."

**Candidate new rule B — ffmpeg `-f` forcing on atomic writes**
Source LD: `FFMPEG_FORMAT_FORCE_MP3_V1_20260421`.
Proposed wording: "Any ffmpeg call that writes to a PID-suffixed tmp path (`.mp3.tmp.<PID>`, `.mp4.tmp.<PID>`, etc.) MUST include `-f <format>` to force the muxer — filename-based format auto-detect fails on tmp-suffixed names."

**Candidate new rule C — silcomp before mix**
The canonical pipeline (CLAUDE.md §8.4) says "silcomp before lipsync". The Phase A canonical assembly does NOT currently silcomp the voice before mixing with the bed. Kim to decide whether §8.4 silcomp should also be mandated before the voice-plus-bed mix, or whether lipsync alone remains the trigger.

### 1b. `Production/governance/video-producer_governance.md`

**Candidate new rule D — Phase A canonical auto-assembly recipe**
Source LDs: `PHASE_A_CANONICAL_PIPELINE_V1_20260421`, `PHASE_A_XFADE_RECIPE_V1_20260421`, `AMBIENT_BED_CONTINUOUS_OVERLAY_V1_20260421`.
Proposed wording: "For Phase A assemblies: flyin -> raw-lipsync -> flyout, with xfade `fade_in_s=0.5 transition=fade` and `fade_out_s=2.5 transition=fadeblack`. Ambient bed is overlaid CONTINUOUSLY across the entire canonical (not just the middle); use `aloop + atrim + amix(volume=0.15, normalize=0)` in a stage-2 overlay. Canonical concat uses the RAW lipsync video (bit-exact ByteDance timing preservation), NOT the `_withbed` intermediate."

**Candidate new rule E — `fadeblack` over `fade` when tail has unsynced mouth frames**
Source LD: `PHASE_A_XFADE_RECIPE_V1_20260421`.
Proposed wording: "When the tail of a lipsync clip contains unsynced mouth frames (e.g. ByteDance never had cue audio for 'Good luck!'), use `transition=fadeblack` for the outgoing fade so the dissolve passes through black at the midpoint and masks the frames. Plain `transition=fade` leaves them visible."

### 1c. `Production/governance/storyboard-producer_governance.md`

**Candidate new rule F — canonical player DOM injection pattern**
Source: session checkpoint `features_touched.phase_a_panel_pipeline.ui_surfaces_added` ("Canonical Phase A video player in storyboard panel — phase A only").
Proposed wording: "When injecting a canonical-video `<video>` player into a storyboard panel, inject only into the scoped panel DOM (Phase A panel in this case); Phase B panels should not receive the same injection until Phase B's own canonical auto-assembly pipeline is built. Pattern is Path-B JS-only per CLAUDE.md Rule 7."

---

## 2. Memory file suggestions (auto-memory)

Three new `.auto-memory/*.md` files are proposed. NONE have been written. Kim to approve/reject each.

### 2a. `feedback_wavespeed_dns_poisoning.md`

**Proposed content:**
> Kim's ISP (Altice/Optimum) DNS-poisons `api.wavespeed.ai` to `167.206.37.145` instead of the real `49.51.190.24` (Tencent Cloud). Any WaveSpeed call that uses the OS DNS resolver will fail silently — it looks like a WaveSpeed API failure, not a DNS failure. Fix: always resolve via public DNS (`dig @8.8.8.8` + `dig @1.1.1.1`) and pass the IP to curl via `--resolve`. `Production/tools/lipsync_sender.py::_resolve_host` implements this. Applies to WaveSpeed only; other endpoints are not affected.

### 2b. `project_phase_a_canonical_pipeline.md`

**Proposed content:**
> Phase A canonical auto-assembly pipeline (locked 2026-04-21, LD `PHASE_A_CANONICAL_PIPELINE_V1_20260421`). Triggered by 'Mix Audio' button. Stages: extract voice stem from raw lipsync -> mix voice+bed (amix normalize=0) -> re-mux raw lipsync with mixed audio -> concat flyin+rawlipsync+flyout via xfade (0.5s fade in / 2.5s fadeblack out) -> overlay continuous bed at volume 0.15 across whole canonical. Output: `phase_a_canonical_<ts>.mp4`. Canonical uses RAW lipsync, not `_withbed` intermediate. Governed by LDs `PHASE_A_XFADE_RECIPE_V1_20260421` + `AMBIENT_BED_CONTINUOUS_OVERLAY_V1_20260421` + LD-284 normalization spec. Phase B does not yet have an equivalent — Phase B still uses pre-produced audio+lipsync workflow.

### 2c. `feedback_canonical_uses_raw_not_withbed.md`

**Proposed content:**
> Canonical Phase A assembly uses the RAW lipsync video (`phase_a_lipsync_<ts>.mp4`) in the concat, NOT the withbed intermediate (`phase_a_lipsync_withbed_<ts>.mp4`). The withbed intermediate exists only for the panel's standalone middle-section player; the concat path bypasses it to preserve bit-exact ByteDance timing. If you feed the withbed into the concat, you will double-apply the ambient bed AND the concat xfade may drift by a few ms from ByteDance's lipsync anchor points. Do not "optimize" by consolidating the two code paths.

---

## 3. Discrepancies flagged (require Kim decision before any follow-up write)

### 3a. `phase_a_speech_combined.mp3` does not exist on disk

Task spec referenced `Production/Event_1/phase_a_speech_combined.mp3` as the voice-stem master. Actual disk has `phase_a_voice_stem_20260421-100111.mp3` + `phase_a_voice_stem_20260421-105138.mp3` + `phase_a_mixed_20260421-*.mp3` variants, but no `phase_a_speech_combined.mp3`. No asset row has been queued for `phase_a_speech_combined.mp3`. Kim to clarify: is this a renamed file, a file that needs to be produced, or a task-spec typo? Downstream: `phase_a_mixed_20260422-000017.mp3` parent_asset_id was left unspecified pending this resolution.

### 3b. CLAUDE.md line 473-504 dual-pointer table — content not re-verified

The PATCH directive for `prod_reference_docs` CLAUDE.md notes field references "arc-skeleton dual-pointer table added at lines 473-504 (prior session, 2026-04-20)" per the task spec. This content was not independently verified in this session — next-session replay operator should spot-check CLAUDE.md lines 473-504 before applying the PATCH. If the line numbers drifted (because CLAUDE.md is edited frequently), the PATCH note should be re-anchored to section heading rather than line numbers.

### 3c. `prod_assets` schema field uncertainty

Field names used (`file_path`, `file_size_bytes`, `role`, `parent_asset_id`, `module_id`, `event_number`, `asset_type`, `asset_key`, `created_at`, `notes`) are a best-effort reconstruction from `Production/scripts/resize_to_delivery.py` (confirms first 7) and `prod_visual_assets` conventions (asset_key, notes). `created_at` is in `_AUTO_FIELDS` in `Production/lib/directus.py` — Directus may silently overwrite whatever value is sent, in which case `post_item_verified` will raise `SilentWriteFailure`. Replay operator should probe `GET /fields/prod_assets` before bulk-replaying the 9 asset rows; any unknown-field 422 should trigger a schema re-probe rather than a silent drop.

### 3d. `parent_asset_id` vs `parent_asset_key_hint`

The task spec lists parent asset links as filenames, but Directus `prod_assets.parent_asset_id` is an integer FK to the parent row's id. Since no row IDs exist yet (all queued), the payload files include `parent_asset_key_hint` strings instead of numeric IDs. Replay operator must: (1) first-pass insert the masters, (2) capture the returned ids, (3) resolve the hint -> id mapping, (4) second-pass insert/PATCH the children with resolved `parent_asset_id` integers. Do not attempt to POST a string into `parent_asset_id`.

---

## 4. Session-specific todos (from checkpoint `kim_decisions_pending`)

These were already in the checkpoint and are NOT resolved by this extended-persistence run; carried forward for visibility:

1. voice_id=null in Directus `prod_voice_profiles` id=2 — backfill with `7o9pyvsN0ob5GO6LBQp6` or leave as-is with phase_a_tts.py fallback?
2. `phase_a_tts.py CUES[]` 3-cue structure (legacy) vs panel `phase_a_script` textarea (current) — delete legacy or keep as fallback?
3. "Phase A only button is transition to Phase B" LD — Kim referenced this but no existing LD found; locate-existing / relock-fresh / not-needed?

---

End of flags.
