# Audio Stripping Defense-in-Depth Architecture
## MindfulNest Production Safety Layer

**Date:** April 15, 2026  
**Status:** Design proposal + reference implementation  
**Related:** CLAUDE.md Rule 8 (anti-lip-sync safeguards), Motion Prompt Lip-Sync Prevention

---

## Problem Statement

Animation models (Kling, Seedance, EvoLink) have a documented bias toward generating lip-sync artifacts when they receive audio input. To prevent any lip-sync in the final product, we strip audio at download time (Layer 1). But what if the strip fails silently? What if Kim copies a clip manually into `animation_clips/`? What if there's an edge case we haven't anticipated?

**Risk:** A single clip with embedded audio could generate Chinese phoneme lip-sync (discovered April 14, 2026 with Seedance). The app would ship with talking heads instead of silent creatures.

**Defense:** Four independent validation layers. No single point of failure.

---

## Architecture Overview

| Layer | When | What | Blocking? | Cost |
|-------|------|------|-----------|------|
| **Layer 1** | Download time | Strip audio via ffmpeg | YES (reject clip) | ~500ms per clip (parallel) |
| **Layer 2** | Serve time | Validate before HTTP response | NO (warn header) | ~500ms per request |
| **Layer 3** | Build time | Audit all storyboard clips | YES (ask Kim) | ~500ms × N clips |
| **Layer 4** | Export time | Final audit of selections | NO (log + inform) | ~500ms × M selected |

---

## Layer 1: Download-Time Strip (PRIMARY DEFENSE)

**Location:** `production_server.py` PollingThread._poll_one() (~line 492)

**Responsibility:** The primary defense. When WaveSpeed polling completes and we download a clip, IMMEDIATELY strip audio before saving to `animation_clips/`.

**Implementation:**
```python
# In production_server.py PollingThread._poll_one():
size = self.client.download(url, dest)

# ADD THIS:
ok, msg = AudioStripLayer.layer1_download_strip(str(dest))
if not ok:
    print(f"[ERROR] {beat_id} option {opt_idx+1}: {msg}")
    self._handle_transient_failure(beat_id, opt_idx, msg)
    dest.unlink()
    return

# Continue with state mutation
self.state.mutate_state(lambda s, b=beat_id, i=opt_idx, f=fname, sz=size: _mark_completed(s, b, i, f, sz))
```

**What it does:**
1. Use `ffmpeg -an -c copy` to re-mux without audio (lossless, ~100ms)
2. Verify with ffprobe that result has zero audio streams
3. Replace original with stripped version
4. If any failure: reject the clip, trigger retry logic

**Cost:** ~500ms per clip (mostly ffmpeg I/O). Acceptable because:
- Clips are downloaded sequentially (PollingThread batches 5 at a time)
- Strip happens in background thread, doesn't block UI
- One-time cost per clip, not recurring

**Why this layer is essential:**
- Animation models sometimes include audio in output (rare, but documented)
- This is where we catch the problem EARLIEST, before Kim even sees the options
- Prevents clips with audio from ever entering `animation_clips/`

**Success criteria:** Every clip in `animation_clips/` has zero audio streams (by construction)

---

## Layer 2: Serve-Time Validation (DETECTION GATE)

**Location:** `production_server.py` ProductionHandler._serve_asset() (~line 677)

**Responsibility:** Paranoia layer. Before serving a clip to the browser, validate it. If audio is detected, serve with warning header.

**Implementation:**
```python
# In production_server.py ProductionHandler._serve_asset():
safe = Path(filename).name
target = self.app.state.clips_dir / safe

# ADD THIS (after file exists check):
is_clean, result = AudioStripLayer.layer2_serve_validate(str(target))
if not is_clean:
    # Add warning header but serve anyway
    extra_headers = {"X-Warn-Audio-Present": "true"}
    # Browser extension (future) can act on this header
    print(f"[WARN] {filename} has audio — layer 1 stripe may have failed")

# Serve as normal, but pass extra_headers to _send_bytes()
```

**What it does:**
1. Run ffprobe on the clip
2. Count audio streams
3. If count > 0: log warning, add header
4. Always serve (don't block Kim's workflow)

**Cost:** ~500ms per HTTP request (which is acceptable because browsers cache).

**Why this layer is valuable:**
- Catches cases where Layer 1's ffmpeg strip silently failed
- Detects manual file injection (if Kim copy/pastes a clip into `animation_clips/`)
- Provides forensics: header in browser dev tools shows which requests had audio
- Zero operational burden (doesn't affect the critical path)

**Doesn't block because:**
- If Layer 1 worked, this is just noise (shouldn't happen in prod)
- If Layer 1 failed, we want to know BEFORE we reject the whole beat
- Kim sees the warning in logs and can troubleshoot

---

## Layer 3: Build-Time Audit (PRE-RENDER GATE)

**Location:** `storyboard_producer.py` (when building HTML storyboard)

**Responsibility:** Before rendering a storyboard, audit all animation clips referenced by the beat data.

**Implementation:**
```python
# In storyboard_producer.py (before calling build_storyboard.py):

# Collect all animation clips from beat selections
clip_paths = []
for beat in beat_selections:
    selected_file = beat.get("selected_animation")
    if selected_file:
        full_path = event_dir / "animation_clips" / selected_file
        clip_paths.append(full_path)

# Validate all in one batch
results = AudioStripLayer.layer3_build_validate_all(clip_paths)

# Check for blockers
blockers = {p: r for p, r in results.items() if not r.is_valid}
if blockers:
    print(f"[BLOCKER] {len(blockers)} clips have audio:")
    for path, result in blockers.items():
        print(f"  {path}: {result.summary()}")
    # Log to Directus
    # Ask Kim: "Found audio in {N} clips. Review prod_activity_log. Safe to proceed?"
    # Block build until she confirms
```

**What it does:**
1. Run ffprobe on all referenced clips (parallel batch)
2. Collect results
3. If any Tier 1 failures: ask Kim before proceeding

**Cost:** ~500ms × M clips (where M = # of selected clips, typically 6-11 for Arc 1)

**Why this layer is essential:**
- Last chance to catch audio BEFORE the storyboard is built
- If Kim or Claude accidentally selected a clip with audio, this catches it
- Blocks the build (don't render HTML with audio clips)
- Gives Kim a clear decision point: "I found this problem. Do you want to proceed or re-do animation?"

**Blocks because:**
- Storyboard HTML is the artifact Kim will review — quality gate is appropriate
- If audio is present, ship quality suffers
- Better to ask now than for her to discover it during listen-through

---

## Layer 4: Export-Time Final Audit (FORENSICS & LOGGING)

**Location:** `production_server.py` ProductionHandler._handle_export() (~line 925)

**Responsibility:** When Kim exports animation selections, validate every selected clip and log results for forensics.

**Implementation:**
```python
# In production_server.py ProductionHandler._handle_export():

export = {
    "event_id": self.app.event_id,
    "exported_at": datetime.now(timezone.utc).isoformat(),
    "beats": [],
    "total_cost": spend["total_spent"],
    "clips_directory": str(self.app.state.clips_dir),
}

for bid, beat in sorted(state.get("beats", {}).items()):
    phase1 = beat.get("phase_1") or {}
    sel = phase1.get("selected_option")
    file = None
    if sel:
        opts = phase1.get("options", [])
        if 1 <= sel <= len(opts):
            file = opts[sel - 1].get("file")
    export["beats"].append({
        "beat": bid,
        "speaker": beat.get("speaker"),
        "section": beat.get("section"),
        "selected_animation": file,
    })

# ADD THIS (before returning):
# Final audit of all selected clips
selections = export["beats"]
results = AudioStripLayer.layer4_export_final_audit(selections)

# Summarize for log
clean_clips = sum(1 for r in results.values() if r.is_valid)
audio_clips = sum(1 for r in results.values() if not r.is_valid)

# Log to Directus prod_activity_log
log_entry = {
    "action": "export_audit",
    "details": {
        "clips_validated": len(results),
        "clips_with_audio": audio_clips,
        "clips_clean": clean_clips,
        "validation_results": [r.to_directus_log() for r in results.values()],
    },
}
# POST to Directus

# Inform Kim (email or dashboard notification)
if audio_clips > 0:
    print(f"[WARNING] Export completed with {audio_clips} clips containing audio. "
          "Review prod_activity_log and consider re-doing animation.")
else:
    print(f"[OK] Export validated — all {clean_clips} selected clips are audio-free.")
```

**What it does:**
1. Run ffprobe on every selected clip one more time
2. Log all results to Directus
3. Summarize for Kim
4. Allow export to complete (don't block)

**Cost:** ~500ms × M selected clips (typically 5-6)

**Why this layer exists:**
- Forensics & accountability: record which clips were validated at export time
- Catches edge cases where Layer 1/2/3 somehow passed audio through
- Kim gets a summary report (optional: email notification)
- If audio IS present: logged and she's informed, so no surprise at listen-through

**Doesn't block because:**
- Layer 3 (build-time) is the real gate — if we got here, Layer 3 passed
- Export is the final step; blocking it would be frustrating if false positive
- Logging is sufficient; Kim is informed

---

## Cost Analysis

### Per-Module Cost (Arc 1 Event with ~11 beats, 3 options each)

| Layer | Clips | Time per | Total | When |
|-------|-------|----------|-------|------|
| L1 Strip | 33 | 500ms | ~16.5s | Background, parallel |
| L2 Serve | ~10 requests | 500ms | ~5s | Cached; user ignores |
| L3 Build | 6-11 | 500ms | ~3-5s | Once, blocking |
| L4 Export | 5-6 | 500ms | ~2.5-3s | Once, non-blocking |

**Total added latency:** ~1-2 seconds per module, amortized over entire workflow.

**Negligible for the safety benefit.** Layer 1 happens in background. Layers 3-4 happen once per module during production, not during playback.

### At Scale (1 full Arc = 6 modules, 330 total animation renderings)

- Layer 1: ~150 seconds total (happens over hours as clips download)
- Layer 3: ~18 seconds one-time per module (build gate)
- Layer 4: ~15 seconds one-time per module (export)

**Acceptable. No performance impact on production.**

---

## Recommendations: Which Layers to Implement

### MANDATORY: Layer 1 (Download-Time Strip)

**Why:** This is the primary defense. Without it, audio clips could enter `animation_clips/`. This is where the problem starts.

**Implementation:** Add `AudioStripLayer.layer1_download_strip()` call to `production_server.py` PollingThread._poll_one() right after download.

**Timeline:** Implement immediately. Takes ~30 minutes. No dependencies.

**Testing:** Run `production_server.py --smoke-test` (already covers ffmpeg check). Add a test: download a mock clip with audio, verify it's stripped.

---

### HIGHLY RECOMMENDED: Layer 3 (Build-Time Audit)

**Why:** This is the last gate before storyboard HTML is finalized. It's where Kim makes her final selection. If audio is present, ask her before rendering.

**Implementation:** Add batch validation call to `storyboard_producer.py` before calling `build_storyboard.py`.

**Timeline:** Implement alongside Layer 1. Takes ~20 minutes.

**Blocking behavior:** YES. If audio found, ask Kim: "I found audio in N clips. Do you want to re-do animation or proceed anyway?"

**UX:** Kim sees a clear dialog, understands the risk, makes an informed choice. Much better than discovering audio at listen-through.

---

### OPTIONAL BUT LOW-COST: Layer 2 (Serve-Time Validation)

**Why:** Paranoia layer. Catches cases where Layer 1 silently failed or clips were manually injected.

**Implementation:** Add optional ffprobe call to `ProductionHandler._serve_asset()`. Add warning header if audio found. Zero blocking.

**Timeline:** Implement if you want defense-in-depth. Takes ~10 minutes.

**Cost:** ~500ms per clip request. Acceptable because browsers cache video playback requests.

**UX:** No impact. Generates warning in server logs if triggered (should never happen).

**Skip if:** You trust Layer 1 completely and want absolute minimal latency.

---

### RECOMMENDED: Layer 4 (Export-Time Audit)

**Why:** Forensics & accountability. Provides a log entry that "at export time, all selected clips were validated and X had audio."

**Implementation:** Add batch validation call and logging to `ProductionHandler._handle_export()`. Non-blocking, just logs and informs Kim.

**Timeline:** Implement after Layer 1 is working. Takes ~15 minutes.

**Cost:** Negligible. Runs once per module at export time.

**UX:** Kim sees a summary report. If clean, it's invisible. If audio found, she gets an email notification and a dashboard alert.

---

## Implementation Roadmap

### Phase 1 (Week 1) — MANDATORY
- [ ] Implement Layer 1 (download-time strip) in `production_server.py`
- [ ] Implement Layer 3 (build-time audit) in `storyboard_producer.py`
- [ ] Add `--skip-audio-validation` flag to production_server.py for testing

### Phase 2 (Week 2) — OPTIONAL
- [ ] Implement Layer 2 (serve-time validation) in `production_server.py`
- [ ] Test with live animation clips (Kling/Seedance)

### Phase 3 (Week 3) — FORENSICS
- [ ] Implement Layer 4 (export-time audit) in `production_server.py`
- [ ] Set up Directus logging for validation results
- [ ] Test full audit chain end-to-end

### Testing Protocol

**For each layer:**
1. Generate a test clip WITH audio (use ffmpeg: `ffmpeg -f lavfi -i testsrc=s=640x480:d=1 -f lavfi -i sine=f=1000:d=1 test_with_audio.mp4`)
2. Place it in `animation_clips/`
3. Verify layer detects it and behaves correctly:
   - L1: Rejects it, triggers retry
   - L2: Logs warning, serves with header
   - L3: Asks Kim before building
   - L4: Logs result

---

## Edge Cases

### Case 1: ffmpeg not installed
- Layer 1: Strip fails, clip rejected, retry triggered. Eventually fails if ffmpeg unavailable.
- Layer 2/3/4: ffprobe unavailable, validation downgrades to WARNING (Tier 2), not blocker.
- **Action:** Docker container should include ffmpeg. Fail fast at startup if missing.

### Case 2: Layer 1 strip silently fails (ffmpeg succeeds but audio remains)
- This is rare but possible if ffmpeg has a bug or codec issue.
- **Detection:** ffprobe check in Layer 1 itself (we re-verify after strip)
- **Action:** Clip rejected, retry triggered

### Case 3: Kim manually copies a clip into animation_clips/
- Layer 1 only runs on WaveSpeed downloads, not manual files
- **Detection:** Layer 2 (serve) or Layer 3 (build) catches it
- **Action:** Layer 3 asks Kim; Layer 2 warns server logs

### Case 4: ffprobe gives false negative (says audio_count = 0 when audio present)
- This would require ffprobe itself to be buggy — extremely unlikely
- **Detection:** Lip-sync would appear in final video, caught at listen-through
- **Recovery:** Re-do animation, ensure ffmpeg version is current

---

## Directus Logging

All validation results should be logged to `prod_activity_log` with structure:

```json
{
  "action": "audio_validation",
  "layer": "download|serve|build|export",
  "details": {
    "file_path": "path/to/clip.mp4",
    "audio_streams": 0,
    "is_valid": true,
    "validation_result": { /* from ValidationResult.to_directus_log() */ }
  },
  "timestamp": "2026-04-15T12:34:56Z"
}
```

Layer 1 (download): Log every strip attempt
Layer 2 (serve): Log only if audio detected
Layer 3 (build): Log batch results before asking Kim
Layer 4 (export): Log comprehensive audit with summary

---

## FAQ

**Q: Why four layers if Layer 1 should catch everything?**
A: Defense-in-depth. Layer 1 is the first line, but it can fail silently (ffmpeg bug, disk I/O error, etc.). Layers 2-4 are cheap insurance that catch the failure before it reaches Kim or users.

**Q: What if Layer 3 blocks and Kim gets frustrated?**
A: Fair point. Layer 3 is a quality gate, not a hard blocker. It should show her exactly which clips have audio and let her choose to re-do animation or proceed (with logged risk). Design the UX to be transparent, not annoying.

**Q: Why doesn't Layer 2 block serve?**
A: Because if we got to Layer 2 (serving to browser), Layer 3 (build-time) already passed. If Layer 3 passed, either audio was NOT present (good), or Kim decided to proceed anyway (her call). Blocking at serve-time would be redundant and frustrating.

**Q: What's the cost vs. benefit?**
A: Cost: ~1-2 seconds added per module workflow. Benefit: 100% certainty no audio clips reach the app. Absolutely worth it.

**Q: Do we need Layer 4 if Layer 3 passes?**
A: Layer 4 is forensics, not detection. It records "at export time, we validated all clips and here's the audit trail." Useful for accountability and debugging, but not operationally critical. Implement it for completeness, but Layer 3 is the real gate.

---

## Related Decisions (CLAUDE.md Rule 8)

This defense architecture complements the existing anti-lip-sync safeguards:
- **Banned prompt words** in motion prompts (CLAUDE.md Rule 8)
- **Negative prompt** with "no audio, no speaking" in all WaveSpeed requests
- **Lip-sync review gate** (manual inspection for Seedance clips)

Audio stripping adds a **technical enforcement layer** on top of the prompt-level safeguards. Together, they form a multi-layer defense against lip-sync artifacts.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2026-04-15 | Initial design: 4-layer architecture, cost analysis, roadmap |
