# ffmpeg_utils.py — Integration Guide

Shared FFmpeg utilities module for MindfulNest production pipeline. Provides safe, tested operations for audio stripping, duration probing, and video trimming across all production scripts.

## Quick Start

```python
from ffmpeg_utils import strip_audio, get_duration, has_audio_track, verify_no_audio, trim_clip

# Download animation and strip audio before serving
video_path = "/path/to/downloaded_anim.mp4"
output_path, size_bytes = strip_audio(video_path)
print(f"Output: {output_path} ({size_bytes} bytes)")

# Check duration for UI metadata
duration = get_duration(output_path)
print(f"Video is {duration:.1f}s")

# Security: verify no audio before serving
verify_no_audio(output_path)  # Raises VideoError if audio exists
serve_file(output_path)

# Future: trim multi-clip videos
trim_clip("/path/to/long.mp4", 2.5, 7.3, "/output/trimmed.mp4")
```

## API Reference

### strip_audio(input_path, output_path=None) → (str, int)

Remove audio track from video file (video stream copy, no re-encode).

**Usage in production_server.py:**
```python
# When user downloads animation from WaveSpeed
video_url = "https://api.wavespeed.ai/..."
local_path = "/event_dir/clips/beat_001_option_1.mp4"
download_video(video_url, local_path)

# Strip audio before serving to child
safe_path, size = strip_audio(local_path)
# Now serve safe_path — no audio, child-safe

# Optionally clean up temp files (if any were left on error)
# Note: strip_audio handles temp cleanup on success; only need this if manual recovery needed
```

**Error handling:**
```python
from ffmpeg_utils import strip_audio, FFmpegError, CommandNotFoundError, VideoError

try:
    output, size = strip_audio("/path/to/video.mp4")
except CommandNotFoundError:
    # ffmpeg not installed — need to install on this system
    print("Install ffmpeg: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)")
except FileNotFoundError:
    # Input file doesn't exist
    print("Video file missing")
except VideoError:
    # ffmpeg failed: corrupt file, permission denied, etc.
    # Check stderr in exception message for details
    print("ffmpeg error:", exc)
```

### get_duration(path) → float

Get video duration in seconds (silent on error, returns 0.0).

**Usage:**
```python
duration = get_duration("/path/to/clip.mp4")
if duration > 0:
    print(f"Video is {duration:.1f}s")
    metadata = {"duration_sec": duration}
else:
    print("Could not determine duration (file missing or ffprobe failed)")
    metadata = {"duration_sec": None}
```

**Note:** Returns 0.0 for any error (file missing, corrupt, permission denied). Safe for UI where missing duration is acceptable fallback.

### has_audio_track(path) → bool

Check if video file has an audio stream.

**Usage:**
```python
if has_audio_track("/path/to/video.mp4"):
    print("Video has audio — strip it before serving to children")
else:
    print("Video is safe: no audio")
```

### verify_no_audio(path) → None

Assert that video file has no audio stream. Raises if audio exists.

**Usage as security gate:**
```python
def serve_video(path):
    # Security gate: ensure no audio before serving
    try:
        verify_no_audio(path)
    except VideoError:
        log.error(f"Security gate failed: {path} has audio!")
        return 500, "Video failed security check"

    return serve_file(path)
```

### trim_clip(input_path, start_sec, end_sec, output_path) → (str, int)

Trim video to time range (copies audio and video, no re-encode).

**Usage for future multi-clip features:**
```python
# Trim clip 1 from a longer video
try:
    output, size = trim_clip("/long_video.mp4", 0, 5.0, "/clip_1.mp4")
    print(f"Clipped: {output} ({size} bytes)")
except ValueError:
    print("Invalid time range")
except VideoError:
    print("Trimming failed")
```

## Error Handling Classes

All functions raise specific exceptions (never `Exception`). Catch what you need:

```python
from ffmpeg_utils import FFmpegError, CommandNotFoundError, VideoError

# Catch all ffmpeg errors
try:
    strip_audio("/path/to/video.mp4")
except FFmpegError as e:
    log.error(f"ffmpeg operation failed: {e}")

# Catch specific error types
try:
    strip_audio("/path/to/video.mp4")
except CommandNotFoundError:
    # ffmpeg not installed
except FileNotFoundError:
    # File doesn't exist
except VideoError:
    # ffmpeg command failed (corrupt file, etc.)
```

## Logging

All operations log with `[ffmpeg]` prefix. Duration queries are silent (no log spam).

```
[ffmpeg] Stripping audio: anim.mp4 → anim_no_audio.mp4
[ffmpeg] Audio stripped: anim_no_audio.mp4 (12345678 bytes)

[ffmpeg] Trimming video.mp4: 2.5s - 7.3s (4.8s)
[ffmpeg] Trimmed: trimmed.mp4 (8765432 bytes)
```

## Integration Examples

### production_server.py — Download and Strip Audio

**Current pattern (using shell commands):**
```python
def download_and_strip(video_url, local_path):
    # 1. Download
    with urllib.request.urlopen(video_url) as resp:
        Path(local_path).write_bytes(resp.read())
    
    # 2. Strip audio via shell (error-prone)
    subprocess.run([
        "ffmpeg", "-i", local_path,
        "-c:v", "copy", "-an", "-y",
        local_path + ".tmp"
    ], check=True)
    os.rename(local_path + ".tmp", local_path)
```

**New pattern (using ffmpeg_utils):**
```python
from ffmpeg_utils import strip_audio, verify_no_audio

def download_and_strip(video_url, local_path):
    # 1. Download (existing code)
    with urllib.request.urlopen(video_url) as resp:
        Path(local_path).write_bytes(resp.read())
    
    # 2. Strip audio (safe, tested)
    try:
        safe_path, size = strip_audio(local_path)
        verify_no_audio(safe_path)  # Sanity check
        return safe_path
    except VideoError as e:
        print(f"Failed to strip audio: {e}")
        raise
```

### generate_animation_options.py — Check Clip Duration

**Current pattern:**
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

**New pattern (DRY):**
```python
from ffmpeg_utils import get_duration

# Same behavior, but centralized, tested, documented
duration = get_duration(path)
print(f"Clip duration: {duration:.1f}s")
```

### Future: Multi-Clip Video Assembly

When adding clip trimming, concatenation, or audio delay padding:

```python
from ffmpeg_utils import trim_clip, get_duration

# Trim first 5s of a longer video
clip_1_path, size = trim_clip("/long_video.mp4", 0, 5.0, "/clip_1.mp4")

# Check duration for metadata
duration = get_duration(clip_1_path)

# Continue with assembly (uses ffmpeg batch processing)
# ...
```

## Testing

Self-contained tests (no input files needed):

```bash
python3 ffmpeg_utils.py test
```

Output:
```
[ffmpeg] Running self-test...
✓ ffmpeg and ffprobe found
✓ get_duration handles missing files gracefully
✓ has_audio_track handles missing files gracefully
✓ verify_no_audio raises FileNotFoundError for missing files
✓ strip_audio raises FileNotFoundError for missing files
✓ trim_clip validates missing files

[ffmpeg] All self-tests passed!
```

## Design Decisions

### Why subprocess.run() instead of Popen?

`subprocess.run()` is simpler and cleaner:
- Handles process lifecycle automatically
- Built-in timeout support
- No need to manually read/close pipes
- stderr/stdout captured safely

Used for all operations (none are streaming).

### Why atomic rename (temp → output)?

Temp file allows:
- Safe error recovery (original untouched if ffmpeg fails)
- No partial/corrupt output files (rename is atomic)
- Debugging (temp left on error for inspection)

Temp naming: `{stem}_audio_stripped_{pid}.mp4` ensures no collisions if multiple processes run.

### Why silent return for get_duration()?

When probing missing files:
- Returning 0.0 is safe (UI treats as "no metadata")
- Raising would require try/catch in every UI code path
- Common use case: optional metadata (missing is acceptable)

### Exceptions vs Return Codes

All functions raise exceptions (never return error codes):
- Python convention (no C-style errno checking)
- Clearer error messages (include command, stderr, context)
- Explicit error handling (caller must decide what to do)
- Type hints work (callers know what's raised)

## Future Enhancements

1. **Batch operations** — `batch_strip_audio([paths])` for parallel processing
2. **Progress callbacks** — Track ffmpeg progress for long operations
3. **Selective audio** — Strip specific audio stream by index
4. **Format conversion** — MP4 → WebM, etc.
5. **Bitrate adjustment** — Re-encode at specific bitrate
6. **Concatenation** — Join multiple clips with audio sync

All additions will maintain the same error handling pattern and logging style.

## Troubleshooting

**"ffmpeg not found in PATH"**
- Install ffmpeg: `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux)
- Verify: `which ffmpeg` and `which ffprobe`

**"Invalid argument" or "Unknown encoder"**
- ffmpeg version too old (minimum: 4.x)
- Check: `ffmpeg -version`

**"Operation timed out"**
- Video too large or system too slow
- Timeout: 300s for strip_audio/trim_clip, 60s for probes
- For very large files, consider pre-processing to smaller size

**"Permission denied"**
- Input or output directory not writable
- Check file/directory permissions: `ls -la`

**"Corrupt file" or "No such file or directory"**
- Input file missing or moved
- Check path exists: `ls -la {path}`
- Verify it's actually a video file: `file {path}`
