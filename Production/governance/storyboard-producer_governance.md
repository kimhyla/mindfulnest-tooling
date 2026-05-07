# storyboard-producer — Governance Gate

**Skill:** storyboard-producer
**Created:** April 15, 2026
**Severity:** HIGH

## Governing Documents (Read Before Proceeding)

1. `CLAUDE.md` Rule 7 — Two-Path Protocol (CRITICAL)
2. `CLAUDE.md` Rule 7 — Export-first rebuild protocol (April 13, 2026)
3. `CLAUDE.md` Rule 7 — Pre-rebuild browser-edit gate
4. `Production/PIPELINE_BRAIN_v1.md` — Storyboard section
5. `Production/TASK_GOVERNANCE_PROTOCOL.md` — Category 3

## Startup Validation Checklist

### 0. Dashboard-Gate Prerequisite
- [ ] Dashboard-gate 7-query session start protocol COMPLETED before starting storyboard work
- [ ] This is a MANDATORY prerequisite — storyboard-producer must not run without dashboard context

### 1. Build Method Check
- [ ] Structural/image changes → Path A (Python builder `build_storyboard.py`)
- [ ] JS/behavior-only fixes → Path B (JS-only patch script)
- [ ] FORBIDDEN: Direct HTML editing, base64 injection, hand-writing HTML replacements
- [ ] If both image + JS changes needed: Path A first, then Path B

### 2. Pre-Rebuild Gate
- [ ] Asked Kim: "Have you made edits in the browser (dialogue, drag-drop, image assignments) that haven't been exported?"
- [ ] If Kim has unsaved edits: she must click "Export Locked Sequence" FIRST
- [ ] Export-first protocol: Kim's exported sequence JSON is MANDATORY primary source for `--lines` input
- [ ] NEVER extract lines from previous storyboard's embedded JavaScript (doesn't reflect drag-drop edits)

### 3. Image Source Check
- [ ] Never guess at disk file paths when rebuilding
- [ ] Extract embedded images FROM current HTML if rebuilding (or use Kim's explicit file paths)
- [ ] Exception: Kim explicitly provides a new/replacement image path

### 4. Audit Check
- [ ] `--audit` run on current version BEFORE rebuild
- [ ] `--audit-previous` run AFTER rebuild to compare features
- [ ] RED flags checked: drag-drop lost, play-all lost, export lost, image count dropped, line count dropped
- [ ] If ANY red flag and not intentional → DO NOT deliver

### 5. Registry Mode Check
- [ ] Default: `--registry` mode (queries Directus `prod_visual_assets`)
- [ ] If auth failure (401/403): escalate to Kim (token refresh)
- [ ] If server error (5xx) after 2 retries: switch to `--config` mode, warn Kim
- [ ] If BOTH fail: STOP and ask Kim — never manually reconstruct

### 6. Version Check
- [ ] Version-in-filename incremented (never overwrite)
- [ ] All prior versions preserved until Kim approves new one

### 7. No Directus Writes Outside Wrapper (LD-421)
All storyboard HTML file writes MUST go through `Production/tools/registered_write.py`. Direct curl/urllib POSTs to prod_visual_assets or prod_activity_log for asset registration are FORBIDDEN. The wrapper performs atomic registration + activity logging with SHA256 dedup and iteration_notes capture.

Verification:
```bash
python3 Production/scripts/check_compliance_gate_6.py --skill storyboard-producer
```

## Validation Logic (Pseudocode)

```python
def validate_storyboard_governance():
    errors = []
    
    # Check 1: Build method
    if change_type == "structural" and method != "path_a_builder":
        errors.append("HARD FAIL: Structural changes require Path A (Python builder)")
    if change_type == "js_only" and method != "path_b_js_patch":
        errors.append("HARD FAIL: JS-only changes require Path B (JS patch script)")
    if method == "direct_html_edit":
        errors.append("HARD FAIL: Direct HTML editing is FORBIDDEN")
    
    # Check 2: Pre-rebuild gate
    if not kim_confirmed_no_browser_edits:
        errors.append("HARD FAIL: Must ask Kim about unsaved browser edits before rebuild")
    
    # Check 3: Image source
    if image_paths_guessed_from_disk:
        errors.append("HARD FAIL: Never guess disk file paths — extract from current HTML or use Kim's explicit paths")
    
    # Check 4: Audit
    if previous_version_exists and not audit_run_before:
        errors.append("HARD FAIL: Must run --audit on current version before rebuild")
    if rebuild_complete and not audit_previous_run_after:
        errors.append("HARD FAIL: Must run --audit-previous after rebuild to catch regressions")
    
    return errors
```

## What Happens When Validation Fails

**HARD FAIL (blocks execution):**
- Direct HTML editing attempted → Refuse. Redirect to Path A or Path B.
- Pre-rebuild gate not cleared → Refuse until Kim confirms browser edit status.
- Audit not run → Refuse to deliver until `--audit-previous` confirms no regressions.
- Image paths guessed from disk → Refuse. Extract from HTML or ask Kim.

**SOFT FAIL (warn and proceed with caution):**
- Registry mode unavailable, falling back to `--config` → Warn Kim, proceed.
- Minor feature differences in `--audit-previous` that Kim explicitly intended → Log and proceed.

## Past Failure(s) This Gate Prevents

**April 13, 2026 — 5 related failures:**
1. Drag-drop lost in v8→v9 rebuild (no feature audit existed)
2. Wrong image embedded (base64 hand-injected instead of using builder)
3. Registry functions existed but main() wasn't wired to them
4. Full rebuild scrambled Kim's image selections (disk file paths guessed wrong)
5. The enforcement rule itself ("always use the builder") caused scrambling — a JS-only patch would have been safe

---

## Stitch Pipeline Decisions (April 16 2026 — designed, NOT YET IMPLEMENTED)

These decisions govern the upcoming Preview Scene + Commit Final feature. Authoritative copy in `prod_locked_decisions`; this section is a governance-file pointer for the `storyboard-producer` skill.

### `STITCH_ARCHITECTURE_MULTI_STAGE` (id=139)
Scene assembly is TWO stages, not one monolithic endpoint. The builder must NOT emit a "one-click stitch" button that does everything — it MUST emit a Preview button that calls the two-stage flow.

- **Stage 1** `POST /api/beat/finalize` per beat — trim + audio_delay + selected_lipsync → writes `beat_NN_final.mp4` to `animation_clips_final/`, idempotent via `finalize_args_hash`.
- **Stage 2** `POST /api/scene/assemble` — concat finalized clips via ffmpeg concat demuxer (stream-copy, <2s for 11 beats).
- **State:** extends `production_state.json` with per-beat `phase_2` block + top-level `phase_2_scene` record.

### `STITCH_WORKFLOW_PREVIEW_THEN_COMMIT` (id=140)
UX is strictly Preview → Reject? Edit in storyboard → Re-Preview → Commit Final.

- **NO separate edit UI.** If preview is wrong, Kim edits per-beat via the existing storyboard controls. Builder MUST NOT emit a modal or panel for "stitch-time editing."
- **Preview output:** `final_preview.mp4` in event_dir. NOT registered in Directus.
- **Commit output:** rename/copy preview to canonical filename (`M{N}_{EVENT}_STORY_SCENE_v{N}.mp4`). Register in `prod_visual_assets`. Log to `prod_activity_log`.
- **Caching:** `finalize_args_hash` means unchanged beats don't re-render on re-preview.

### `STITCH_BUTTON_LOCATION_STORYBOARD_OVERLAY` (id=141)
Preview + Commit buttons live in `inject_production_overlay.py` emission, adjacent to the existing Export Selections button. All status/progress UI is JS-driven via an `injectStitchButton()` function following the `injectLipSyncButtons` pattern.

- Builder: ONLY the button emit is Path A (structural rebuild). Status/progress behavior is Path B (JS-patchable).
- Rejected alternative: separate `/stitch` HTML page served by `production_server`. Kim's explicit requirement: "links to the appropriate portion of the storyboard section."

### Builder obligations when the Tier 4 feature is implemented
1. Emit Preview + Commit buttons in the production overlay (not in the per-beat section).
2. Emit `window._injectStitchButton` function for `pollStatus()` integration.
3. Use Path B patching for ALL subsequent stitch-behavior iterations (don't rebuild the storyboard HTML just to change button copy).
4. Registry entries: stitched final video in `prod_visual_assets`. `asset_type: "final_scene_video"`.

**Until Tier 4 is implemented, the storyboard-producer skill must refuse to emit any stitch-related UI.** Kim's current workflow does not include in-storyboard stitching; any premature button emission would be a Rule 19 shortcut.

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

The storyboard overlay is where Kim triggers Preview Scene + Commit (LD-141) — the entry point to the concat step. Before emitting any Preview/Stitch button action, verify:

- [ ] **All per-beat clips have a valid `beat_NN_normalized.mp4`** matching the current `selected_option` for that beat. If any beat is missing its normalized output, the Preview button's handler MUST invoke normalization for that beat BEFORE concat, or surface a blocking error in the overlay status UI.
- [ ] **Normalization cache is valid.** For each beat, the sidecar `beat_NN_normalized.meta.json` `{source_path, source_mtime, source_sha256_first_1mb, selected_option, codec_spec_hash}` matches current state. Any mismatch → re-normalize before concat.
- [ ] **Concat demuxer input list references ONLY `beat_NN_normalized.mp4` files.** Never raw lipsync, raw Kling, or hand-looped outputs. Emitting a concat list with non-normalized inputs is a Rule 19 shortcut.
- [ ] **Selected-option change detection wired.** When Kim flips `selected_option` for a beat in the storyboard drag-drop UI, the normalize step re-fires on that beat's new source before concat is available for that event.

**Canonical normalization command** (single source of truth — see `Production/PIPELINE_BRAIN_v1.md` §Normalization):

```
ffmpeg -y -i INPUT.mp4 \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1:1,fps=24" \
  -c:v libx264 -profile:v high -pix_fmt yuv420p -preset slow -crf 20 -g 48 \
  -c:a aac -b:a 128k -ar 44100 -ac 1 \
  -movflags +faststart \
  beat_NN_normalized.mp4
```

HARD FAIL if the storyboard overlay emits a Preview/Commit action that concats non-normalized inputs. Reference: `Production/PIPELINE_BRAIN_v1.md` §Normalization, `APP_ARCHITECTURE_MASTER_v1.md` §7 (LD-284 cross-ref).

---

## Lessons Learned April 24–26, 2026

### Chromium Drag-Source Mutation Deferral (LD: `CHROMIUM_DRAGSTART_DEFERRAL_V1`)
Any DOM/CSS change to a drag-source element during the `dragstart` event MUST be deferred to the next tick via `setTimeout(fn, 0)`. Synchronous mutations during `dragstart` (CSS transforms, `display:none`, parent transforms, geometry changes) cause Chromium to treat the source as destroyed and cancel the drag, so drop events never fire or fire with empty `dataTransfer`. Also: native `<img>` elements default to `draggable="true"` — always set `draggable="false"` on inner `<img>` elements inside custom drag handlers, or Chrome fights with its own native image-drag carrying stale URL data.

### Two-Layer Chrome Cache Discipline (LD: `TWO_LAYER_CHROME_CACHE_V1`)
Production HTML tool pages and their JSON API responses cache INDEPENDENTLY in Chrome. `Cache-Control: no-store` on JSON API endpoints does NOT prevent the HTML page from being cached. Both layers need `Cache-Control: no-store` separately. JS-internal cache-busters (`?_t=Date.now()`) are self-defeating when the JS that contains them is itself cached — the new buster never executes. Every endpoint returning user-modifiable data (HTML pages AND API JSON) MUST default to `Cache-Control: no-store`. Hard refresh (Cmd+Shift+R) busts page cache; regular refresh does not.
