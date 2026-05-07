# Audio Stripping Integration Checklist

Quick reference for integrating the 4 defense layers into production code.

---

## Layer 1: Download-Time Strip (MANDATORY)

**File:** `Production/tools/production_server.py`

**Location:** PollingThread._poll_one() method, ~line 492

**Current code:**
```python
size = self.client.download(url, dest)
self.state.mutate_state(lambda s, b=beat_id, i=opt_idx, f=fname, sz=size: _mark_completed(s, b, i, f, sz))
```

**Insert after download:**
```python
from Production.validators.audio_stripping import AudioStripLayer

# ... in _poll_one():
size = self.client.download(url, dest)

# NEW: Strip audio immediately
ok, msg = AudioStripLayer.layer1_download_strip(str(dest))
if not ok:
    print(f"[ERROR] {beat_id} option {opt_idx + 1}: audio strip failed: {msg}")
    self._handle_transient_failure(beat_id, opt_idx, f"strip failed: {msg}")
    try:
        dest.unlink()
    except OSError:
        pass
    return

# Original code continues
self.state.mutate_state(lambda s, b=beat_id, i=opt_idx, f=fname, sz=size: _mark_completed(s, b, i, f, sz))
self.state.add_spend("kling_animation", COST_PER_CLIP_KLING)
```

**What this does:**
- Strips audio from downloaded clip (re-mux with ffmpeg -an)
- Verifies result has zero audio streams
- On failure: rejects clip, triggers retry
- On success: proceeds normally

**Test:**
```bash
python3 production_server.py --smoke-test
```

---

## Layer 2: Serve-Time Validation (OPTIONAL)

**File:** `Production/tools/production_server.py`

**Location:** ProductionHandler._serve_asset() method, ~line 677

**Current code:**
```python
def _serve_asset(self, filename: str) -> None:
    safe = Path(filename).name
    target = self.app.state.clips_dir / safe
    if not target.is_file():
        return self._send_json(404, {"error": f"asset not found: {safe}"})
    # ... rest of method
```

**Insert after file check:**
```python
from Production.validators.audio_stripping import AudioStripLayer

def _serve_asset(self, filename: str) -> None:
    safe = Path(filename).name
    target = self.app.state.clips_dir / safe
    if not target.is_file():
        return self._send_json(404, {"error": f"asset not found: {safe}"})
    
    # NEW: Layer 2 validation
    is_clean, result = AudioStripLayer.layer2_serve_validate(str(target))
    if not is_clean:
        print(f"[WARN] Serving {safe} which contains audio — Layer 1 strip may have failed")
        # Add warning header
        extra_headers = {"X-Warn-Audio-Present": "true"}
    else:
        extra_headers = None
    
    # ... rest of method (modify _send_bytes call to include extra_headers):
    self._send_bytes(
        200, body, ctype,
        extra_headers=extra_headers or {"Accept-Ranges": "bytes"},
    )
```

**What this does:**
- Non-blocking validation before serving clip to browser
- If audio found: adds warning header to HTTP response
- Logs to server console
- Always serves the clip (doesn't block workflow)

---

## Layer 3: Build-Time Audit (HIGHLY RECOMMENDED)

**File:** `Production/skills/storyboard_producer.py` (or wherever storyboard builder is called)

**Location:** Main orchestration function, before `build_storyboard.py` is invoked

**Pseudo-code (exact integration depends on your skill structure):**
```python
from Production.validators.audio_stripping import AudioStripLayer
from pathlib import Path

def orchestrate_storyboard_build(event_id, beat_selections, event_dir):
    """
    Before building storyboard HTML, audit all animation clips.
    """
    event_dir = Path(event_dir)
    
    # Collect all selected animation clips
    clip_paths = []
    for beat in beat_selections:
        selected_file = beat.get("selected_animation")
        if selected_file:
            full_path = event_dir / "animation_clips" / selected_file
            clip_paths.append(full_path)
    
    # NEW: Audit all clips
    if clip_paths:
        results = AudioStripLayer.layer3_build_validate_all([str(p) for p in clip_paths])
        blockers = {p: r for p, r in results.items() if not r.is_valid}
        
        if blockers:
            # Log to Directus
            for path, result in blockers.items():
                print(f"[BLOCKER] {path}: {result.summary()}")
                log_to_directus("audio_validation", "build", result.to_directus_log())
            
            # Ask Kim
            raise RuntimeError(
                f"Audio validation BLOCKED: {len(blockers)} clips have audio. "
                f"Check prod_activity_log. Do you want to re-do animation or proceed anyway?"
            )
    
    # If we get here, all clips are clean — proceed with build
    print(f"[OK] Audio validation passed — {len(clip_paths)} clips are audio-free")
    
    # Now call the actual storyboard builder
    return build_storyboard(event_id, beat_selections, event_dir)
```

**Integration point:**
- Call this before any storyboard HTML is generated
- If exception is raised, stop and ask Kim
- If validation passes, continue normally

**What this does:**
- Validates all animation clips referenced by the storyboard
- If any have audio: raises blocker, asks Kim
- Logs comprehensive results to Directus
- Prevents building storyboard with audio clips

---

## Layer 4: Export-Time Audit (RECOMMENDED)

**File:** `Production/tools/production_server.py`

**Location:** ProductionHandler._handle_export() method, ~line 925

**Current code:**
```python
def _handle_export(self) -> None:
    state = self.app.state.read_state()
    spend = self.app.state.read_spend()
    export = { ... }
    # ... build export dict ...
    
    # Write to disk and return
    disk_path.write_text(json.dumps(export, indent=2))
    # ... send download ...
```

**Insert before return:**
```python
from Production.validators.audio_stripping import AudioStripLayer

def _handle_export(self) -> None:
    state = self.app.state.read_state()
    spend = self.app.state.read_spend()
    export = { ... }
    # ... build export dict ...
    
    # NEW: Layer 4 audit
    selections = export["beats"]
    results = AudioStripLayer.layer4_export_final_audit(selections)
    
    clean_count = sum(1 for r in results.values() if r.is_valid)
    audio_count = sum(1 for r in results.values() if not r.is_valid)
    
    # Log comprehensive audit to Directus
    for file_name, result in results.items():
        log_to_directus("audio_validation", "export", {
            "file": file_name,
            "result": result.to_directus_log(),
        })
    
    if audio_count > 0:
        print(f"[WARNING] Export audit found {audio_count} clips with audio — see prod_activity_log")
        # Optionally: send email to Kim with summary
    else:
        print(f"[OK] Export audit: all {clean_count} selected clips are audio-free")
    
    # Write to disk and return
    disk_path.write_text(json.dumps(export, indent=2))
    # ... send download ...
```

**What this does:**
- Final validation of all exported clips
- Logs comprehensive audit trail to Directus
- Informs Kim (console log, optional email)
- Doesn't block export (non-critical gate)

---

## Implementation Order

### Step 1 (required): Copy validator module
```bash
# The validator is already at:
# Production/validators/audio_stripping.py
# No action needed; just import it in your code
```

### Step 2 (required): Implement Layer 1
- Modify `production_server.py` PollingThread._poll_one()
- Test with `--smoke-test`
- Deploy

### Step 3 (recommended): Implement Layer 3
- Modify `storyboard_producer.py` (or equivalent orchestration)
- Integrate with dashboard-gate skill to log results
- Test end-to-end with a module

### Step 4 (optional): Implement Layer 2
- Modify `production_server.py` ProductionHandler._serve_asset()
- Test by requesting a clip via HTTP
- Verify warning header appears in curl/browser dev tools

### Step 5 (recommended): Implement Layer 4
- Modify `production_server.py` ProductionHandler._handle_export()
- Integrate Directus logging
- Test by exporting selections

---

## Logging to Directus

Every layer should log validation results to `prod_activity_log`:

```python
import urllib.request
import json

def log_to_directus(action, layer, details):
    """Post a validation result to Directus prod_activity_log."""
    # Get API key from Production/API_KEYS_MASTER.md
    api_url = os.environ.get("DIRECTUS_URL") + "/items/prod_activity_log"
    
    payload = {
        "action": action,  # "audio_validation"
        "layer": layer,    # "download", "serve", "build", "export"
        "details": details,  # Result object
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"[WARN] Directus log failed: {exc}")
        return None
```

---

## Testing

### Test 1: Create a clip with audio
```bash
# Create test clip WITH audio
ffmpeg -f lavfi -i testsrc=s=640x480:d=1 \
        -f lavfi -i sine=f=1000:d=1 \
        test_with_audio.mp4

# Verify it has audio
ffprobe -v quiet -print_format json -show_streams test_with_audio.mp4 | jq '.streams[] | select(.codec_type=="audio")'
# Should output audio stream info
```

### Test 2: Layer 1 strip
```bash
from Production.validators.audio_stripping import AudioStripLayer
ok, msg = AudioStripLayer.layer1_download_strip("test_with_audio.mp4")
print(f"Strip result: {ok}, {msg}")

# Verify stripped file has NO audio
ffprobe -v quiet -print_format json -show_streams test_with_audio.mp4 | jq '.streams[] | select(.codec_type=="audio")'
# Should output nothing
```

### Test 3: Layer 2 validation
```bash
from Production.validators.audio_stripping import AudioStripLayer
is_clean, result = AudioStripLayer.layer2_serve_validate("test_with_audio.mp4")
print(f"Clean: {is_clean}")
print(result.summary())
```

### Test 4: Layer 3 batch
```bash
from Production.validators.audio_stripping import AudioStripLayer
results = AudioStripLayer.layer3_build_validate_all(["test_with_audio.mp4", "test_clean.mp4"])
for path, result in results.items():
    print(result.summary())
```

---

## Fallback: Skip Audio Validation (Emergency)

If ffmpeg is unavailable or validation causes issues, add a kill switch:

```python
import os

SKIP_AUDIO_VALIDATION = os.environ.get("SKIP_AUDIO_VALIDATION", "false").lower() == "true"

# In Layer 1:
if SKIP_AUDIO_VALIDATION:
    print("[WARN] Audio validation skipped (SKIP_AUDIO_VALIDATION=true)")
else:
    ok, msg = AudioStripLayer.layer1_download_strip(str(dest))
    if not ok:
        # ... handle failure ...
```

**Usage (emergency only):**
```bash
SKIP_AUDIO_VALIDATION=true python3 production_server.py --event-dir ...
```

---

## References

- **Validator module:** `Production/validators/audio_stripping.py`
- **Design doc:** `Production/AUDIO_STRIPPING_DEFENSE_v1.md`
- **CLAUDE.md Rule 8:** Anti-lip-sync safeguards (motion prompts, API params)
- **Related:** Motion Prompt Lip-Sync Prevention (CLAUDE.md), WaveSpeed client (production_server.py)
