# ffmpeg_utils.py — Migration Guide

How to integrate ffmpeg_utils.py into existing production scripts without breaking changes.

## Overview

The module provides drop-in replacements for ffmpeg operations currently scattered across:
- `production_server.py` — WaveSpeed video download handling
- `generate_animation_options.py` — duration probing for animation metadata

No scripts require changes immediately. Migration is optional and incremental.

## Current State

### production_server.py

No direct ffmpeg calls (uses WaveSpeed API only). Future audio-stripping endpoint can use:
```python
from ffmpeg_utils import strip_audio, verify_no_audio

@app.route("/api/download-safe")
def download_safe_video():
    """Download animation and strip audio."""
    url = request.json["url"]
    local_path = state.clips_dir / "temp.mp4"
    
    # Download (existing code)
    client.download(url, local_path)
    
    # Strip audio (new, using ffmpeg_utils)
    safe_path, size = strip_audio(str(local_path))
    verify_no_audio(safe_path)  # Security gate
    
    return {"path": safe_path, "size_bytes": size}
```

### generate_animation_options.py

Currently duplicates ffprobe logic:
```python
def get_duration(path):
    """Get video duration using ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True
        )
        return float(r.stdout.strip())
    except:
        return 0.0
```

**Migration (optional):**
```python
# At top of file
from ffmpeg_utils import get_duration

# Remove local get_duration() function
# Replace all calls with:
duration = get_duration(path)  # Same API, same behavior
```

## Migration Path (Phase 1 — Optional)

### Step 1: Add import at module top
```python
from ffmpeg_utils import strip_audio, get_duration, has_audio_track, verify_no_audio, trim_clip
from ffmpeg_utils import FFmpegError, CommandNotFoundError, VideoError
```

### Step 2: Replace subprocess calls

**Before:**
```python
def download_video(url, dest):
    with urllib.request.urlopen(url, timeout=120) as resp:
        content = resp.read()
    Path(dest).write_bytes(content)
    return len(content)

def get_duration(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True
        )
        return float(r.stdout.strip())
    except:
        return 0.0
```

**After:**
```python
def download_video(url, dest):
    with urllib.request.urlopen(url, timeout=120) as resp:
        content = resp.read()
    Path(dest).write_bytes(content)
    return len(content)

# Remove get_duration — use ffmpeg_utils.get_duration instead
# (imported at top)
```

Then replace all calls:
```python
# Before:
dur = get_duration(path)

# After:
dur = get_duration(path)  # Now calls ffmpeg_utils.get_duration
```

### Step 3: Test

```bash
python3 generate_animation_options.py --dry-run --beats 1,2,3
# Should work exactly as before (using ffmpeg_utils under the hood)
```

## Migration Path (Phase 2 — Optional, Future)

When adding audio-stripping to animation downloads:

```python
# Before: raw ffmpeg command
def strip_and_serve(local_path):
    subprocess.run([
        "ffmpeg", "-i", local_path,
        "-c:v", "copy", "-an", "-y",
        local_path + ".noaudio.mp4"
    ], check=True)
    return local_path + ".noaudio.mp4"

# After: using ffmpeg_utils
def strip_and_serve(local_path):
    safe_path, size = strip_audio(local_path)
    verify_no_audio(safe_path)  # Extra safety
    return safe_path
```

## Non-Breaking Changes

All existing ffmpeg operations will continue to work:
- **subprocess calls** — still valid, coexist with ffmpeg_utils
- **Error handling** — ffmpeg_utils uses exceptions (Python convention), not subprocess return codes
- **Logging** — ffmpeg_utils logs to stdout with `[ffmpeg]` prefix (won't interfere with existing logs)
- **Dependencies** — zero new dependencies (uses standard library only)

## Compatibility

| Script | Current | Migrate To | Status |
|--------|---------|-----------|--------|
| production_server.py | WaveSpeed API | ffmpeg_utils (future) | ✅ Ready |
| generate_animation_options.py | subprocess + custom functions | ffmpeg_utils | ✅ Ready |
| patch_animation_layer.py | None | ffmpeg_utils (future) | ✅ Ready |
| build_animation_review.py | None | ffmpeg_utils (future) | ✅ Ready |
| pipeline.py | None | ffmpeg_utils (future) | ✅ Ready |

## Future Enhancements

Once ffmpeg_utils is integrated:

1. **Centralized audio stripping** — All downloaded videos automatically safe
2. **Batch operations** — Strip audio from multiple clips in parallel
3. **Progress tracking** — Long operations show estimated time remaining
4. **Format conversion** — Generate WebM fallbacks for browser compatibility
5. **Quality validation** — Verify output meets minimum bitrate/resolution

## Questions?

See `FFMPEG_UTILS_INTEGRATION.md` for complete API docs and examples.
