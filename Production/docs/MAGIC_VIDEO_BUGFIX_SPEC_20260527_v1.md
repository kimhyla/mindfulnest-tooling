# Magic Video Bug Fix Spec — 2026-05-27 v1

Two confirmed bugs introduced with the CANVAS_MISMATCH_FIX (Kim 2026-05-27):
- **Q1** — `path_picker.html`: video frame load is unreliable; silent fallback to wrong-coordinate still
- **Q2** — `StoryboardTab.tsx`: magic_video preview doubles the dialogue audio

Both are **Tier B / cursor-agent dispatch** — each is a targeted fix in a single file with known exact location.

---

## Bug Q1 — path_picker.html: Unreliable video frame load for canvas background

### Root cause

`loadVideoFrameAsBackground()` (path_picker.html lines ~467–542) creates a hidden `<video>` element and listens for `loadedmetadata → seeked` to capture frame 0 via canvas `drawImage`. This approach is unreliable because:

1. **Browser video decode is heavy.** Streaming an MP4 via HTTP, decoding it in a hidden offscreen element, and waiting for `loadedmetadata` → `seeked` involves browser-internal buffering that competes with the GIL and main-thread parse time. On a loaded machine the 8s timeout fires before `loadedmetadata`, triggering silent fallback to the reference still.

2. **Silent fallback is invisible to Kim.** When fallback fires, `console.warn(...)` is emitted (browser console only) and `loadImageFromURL(sourceImagePath)` runs. Kim draws her path on the still, not the video frame. The coordinate system of the still crop differs from the video frame (different framing, different aspect ratio). The magic overlay is spatially wrong but there is no UI error.

3. **The server already speaks ffmpeg.** `production_server.py` can extract a PNG frame in ~50ms via `ffmpeg -ss 0 -frames:v 1 -f image2pipe -vcodec png`. This is deterministic, server-side, and returns a PNG — no browser video decode required.

### Fix

**File: `Production/tools/production_server.py`** — add a new GET endpoint `/api/video/thumbnail`.

Route: `GET /api/video/thumbnail?path=<video_path>&t=0`

Handler logic (pseudo-code):
```python
# In do_GET, route table
if path == "/api/video/thumbnail":
    return self._handle_video_thumbnail()

def _handle_video_thumbnail(self) -> None:
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
    video_path = (qs.get("path") or [None])[0]
    t = float((qs.get("t") or ["0"])[0])

    # Validate path using same containment logic as /files
    resolved = self._resolve_and_validate_path(video_path)  # existing helper or inline
    if not resolved:
        return self._send_error_v59(404, error_code="FILE_NOT_FOUND", ...)

    # Extract frame at t seconds via ffmpeg, return as PNG
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(t),
        "-i", resolved,
        "-frames:v", "1",
        "-f", "image2pipe",
        "-vcodec", "png",
        "pipe:1",
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=15)
    if result.returncode != 0 or not result.stdout:
        return self._send_error_v59(500, error_code="THUMBNAIL_FAILED",
                                    error_message="ffmpeg frame extract failed")

    png_bytes = result.stdout
    self.send_response(200)
    self.send_header("Content-Type", "image/png")
    self.send_header("Content-Length", str(len(png_bytes)))
    self.send_header("Cache-Control", "no-store")
    self._cors_headers()
    self.end_headers()
    self.wfile.write(png_bytes)
```

**File: `Production/tools/path_picker.html`** — replace `loadVideoFrameAsBackground()` with a direct PNG fetch.

Replace the entire body of `loadVideoFrameAsBackground(videoPath)` (lines ~467–542) with:

```javascript
function loadVideoFrameAsBackground(videoPath) {
  setDropText([
    { text: 'Loading frame from lipsync video…' },
    { tag: 'br' },
    { tag: 'small', style: 'color:#888', text: 'Draw your path on the actual video frame below.' },
  ]);

  // CANVAS_MISMATCH_FIX_V2: fetch frame 0 as PNG via server-side ffmpeg.
  // Avoids the browser video-decode race that caused 8s timeouts + silent fallback
  // to the reference still (which has different framing from the lipsync video).
  const thumbnailUrl = `http://localhost:5111/api/video/thumbnail?path=${encodeURIComponent(videoPath)}&t=0`;
  const image = new Image();
  image.onload = () => { applyImage(image); };
  image.onerror = () => {
    // Surface the error visibly — don't silently fall back to the wrong still.
    if (sourceImagePath) {
      setDropText([
        { text: '⚠ Could not load video frame — using reference still instead.' },
        { tag: 'br' },
        { tag: 'small', style: 'color:#f90', text: 'Coordinates may not match the final composite. Retry if incorrect.' },
      ]);
      loadImageFromURL(`http://localhost:5111/files?path=${encodeURIComponent(sourceImagePath)}`);
    } else {
      setDropText([
        { text: 'Could not load video frame.' },
        { tag: 'br' },
        { tag: 'small', style: 'color:#555', text: 'Drag a PNG/JPEG instead.' },
      ]);
    }
  };
  image.src = thumbnailUrl;
}
```

Key differences from the old implementation:
- No hidden `<video>` element, no `loadedmetadata` listener, no 8s timeout
- Error is shown visibly in the drop-zone with a warning color (not `console.warn`)
- Fallback still shows when server extract fails, but Kim sees the warning and knows to retry
- ~50ms deterministic vs ~8000ms race

### Invariants this fix must preserve

- `applyImage(image)` sets `img = image`, `canvas.width/height`, `canvas.style.display = 'block'`, hides `#drop-text`, resets `points`, and calls `redraw()` + `updateYAML()` + `updateCount()` + `updateSubmitBtn()`. The new code must reach `applyImage` on success — not bypass it.
- The path containment + CORS validation in the server `/api/video/thumbnail` handler must be the same as the existing `/files` handler (no new attack surface).
- The `_cors_headers()` method (sends `Access-Control-Allow-Origin: *`) must be called so the browser's fetch from `http://localhost:5111/magic` to `http://localhost:5111/api/video/thumbnail` is allowed.

### Test

1. Open a beat that has a `lipsync.file` (e.g., beat_01 in Event_1)
2. Click "Add magic on video" button
3. Confirm path_picker loads with the lipsync video frame 0 as canvas background (not the reference still)
4. Confirm the canvas dimensions match the video dimensions (not the still dimensions)
5. Simulate server error: stop server, click again — confirm error text appears in yellow/orange in the drop zone (not a blank canvas with no message)

---

## Bug Q2 — StoryboardTab.tsx: magic_video preview doubles dialogue audio

### Root cause

When Kim clicks "Preview Still" (button calls `handlePreviewOption(-1)`) and the beat has a `magic_video_path` but NOT a `magic_still_path`, the `previewVideoSrc` resolves to `_magicVideoSrc` (StoryboardTab.tsx lines 1740-1742).

The magic_video file has **lipsync audio baked in** — confirmed at `Production/tools/server_handlers/background.py` lines 1055-1062:
```python
encode_cmd = [
    "ffmpeg", "-y",
    # stdin pipe = composited video frames
    "-i", "pipe:0",
    "-i", safe_ffmpeg_src,  # original lipsync source for audio
    "-map", "0:v",
    "-map", "1:a?",         # audio COPIED from lipsync source
    ...
]
```

The video has one audio stream (lipsync dialogue). But the playback effect at StoryboardTab.tsx lines 1854-1970 treats `previewOptIdx === -1` as `!isLipsyncPreview`, which is correct for `magic_still_path` (still has no audio). When `previewOptIdx === -1` resolves to a `magic_video_path` instead, the code at line 1958 still starts `audioRef.current` (Phase B TTS audio) because it only checks `!isLipsyncPreview`, not whether the video source is audio-bearing:

```tsx
// line 1958 — this fires for BOTH magic_still AND magic_video
if (!isLipsyncPreview && aud) {
  // ... starts aud.play() → Phase B TTS audio plays
}
```

Result: magic_video plays its own baked lipsync audio AND `audioRef` plays the same TTS track → Kim hears dialogue twice, out of phase.

### Fix

**File: `Production/tools/storyboard-v2/src/components/StoryboardTab.tsx`**

The fix is in the `useEffect` hook (lines ~1815–1976) that plays audio/video when `previewOptIdx` changes.

At line 1854, the block is:
```tsx
if (!isLipsyncPreview) {
  if (!aud) return;
  aud.currentTime = 0;
}
```

And at lines 1958-1970:
```tsx
if (!isLipsyncPreview && aud) {
  if (audioDelaySec > 0) {
    const ms = Math.round(audioDelaySec * 1000);
    const t = window.setTimeout(() => {
      aud.play().catch(() => {});
    }, ms);
    return () => {
      window.clearTimeout(t);
      ...
    };
  }
  aud.play().catch(() => {});
}
```

The fix: derive a new flag `isAudioBearingVideo` that is true when `previewOptIdx === -1` AND the resolved `previewVideoSrc` comes from `_magicVideoSrc` (not `_magicStillSrc` or `_finalFileSrc`). When this flag is true, skip `audioRef` playback entirely — the video's baked audio is sufficient.

**Exact change — two locations in the same useEffect:**

Location 1 (around line 1854):
```tsx
// BEFORE:
if (!isLipsyncPreview) {
  if (!aud) return;
  aud.currentTime = 0;
}

// AFTER:
// magic_video_path has lipsync audio baked in (background.py encode_cmd -map 1:a?).
// When previewOptIdx===-1 resolves to magic_video (not magic_still), skip Phase B
// audio element — playing both is doubled dialogue.
const isStillFinalPreview = previewOptIdx === -1;
const previewSrcIsMagicVideo = isStillFinalPreview && !_magicStillOk && _magicVideoOk;
if (!isLipsyncPreview) {
  if (previewSrcIsMagicVideo) {
    // video has its own audio — do not touch audioRef
  } else {
    if (!aud) return;
    aud.currentTime = 0;
  }
}
```

Location 2 (around line 1958):
```tsx
// BEFORE:
if (!isLipsyncPreview && aud) {
  // ... audioDelaySec branch + aud.play()
}

// AFTER:
if (!isLipsyncPreview && !previewSrcIsMagicVideo && aud) {
  // ... same body unchanged
}
```

**Note on scope of `previewSrcIsMagicVideo`:** the variable must be declared before the `if (!isLipsyncPreview)` block at line 1854 so both uses can see it. The `useEffect` dependency array (line 1976) must add `_magicStillOk` and `_magicVideoOk` if they are not already present. Check: they are derived from `beat.magic_still_path` + `beat.magic_still_path_exists` and `beat.magic_video_path` + `beat.magic_video_path_exists` which are already in the beat state — add `beat.magic_still_path`, `beat.magic_video_path` to the dep array at line 1976 if not already there. (Check: the current dep array at line 1976 includes `beat.magic_still_path` and `beat.magic_video_path` via the outer `handlePreviewOption` callback deps at line 2028; they are NOT in the `useEffect` dep array at line 1976. Add them.)

**Also fix: `handlePreviewOption` toggle-play at line 2021:**

```tsx
// BEFORE (line 2021):
if (!isLipsyncPreview) safePlay(aud).catch((err) => handlePlayRejection(err, 'toggle-play-aud'));

// AFTER:
const _previewIsMagicVideo = isStillFinalPreview && !beat.magic_still_path && beat.magic_video_path;
if (!isLipsyncPreview && !_previewIsMagicVideo) {
  safePlay(aud).catch((err) => handlePlayRejection(err, 'toggle-play-aud'));
}
```

Same fix at line 2007 (pause branch):
```tsx
// BEFORE (line 2007):
if (!isLipsyncPreview) safePause(aud).catch(() => {});

// AFTER:
if (!isLipsyncPreview && !_previewIsMagicVideo) safePause(aud).catch(() => {});
```

And at line 2026 (switching-away pause):
```tsx
// BEFORE (line 2026):
if (!isLipsyncPreview) safePause(aud).catch(() => {});

// AFTER:
if (!isLipsyncPreview && !_previewIsMagicVideo) safePause(aud).catch(() => {});
```

### Invariants this fix must preserve

- **magic_still_path preview (`previewOptIdx === -1`, `_magicStillOk=true`)**: UNCHANGED. Still image has no audio — `audioRef` must still play. `previewSrcIsMagicVideo` is false when `_magicStillOk=true`.
- **lipsync preview (`previewOptIdx === 0`)**: UNCHANGED. `isLipsyncPreview=true` guards the entire branch.
- **animation option N preview (`previewOptIdx > 0`)**: UNCHANGED. `isLipsyncPreview=false`, `previewSrcIsMagicVideo=false` (neither is `-1`).
- **beat with magic_video_path AND magic_still_path**: `_magicStillOk=true` wins in the Bug-B1 priority chain, so `previewVideoSrc` is `_magicStillSrc`. `previewSrcIsMagicVideo=false`. `audioRef` plays. Correct.
- **beat with magic_video_path only**: `previewVideoSrc = _magicVideoSrc`. `previewSrcIsMagicVideo=true`. `audioRef` is silent. Correct — video has audio.

### `handlePreviewEnded` and `handleAudioEnded` — no change needed

`handlePreviewEnded` (line 2030) already handles `previewOptIdx === -1` with the MAGIC_STILL_AUDIO_TAIL_FIX. For magic_video, `aud` will be paused (never started), so `aud.ended === true` and `aud.paused === true` — the condition `!aud.ended && !aud.paused` at line 2037 is false. `handlePreviewEnded` falls through to `aud?.pause()` (no-op since aud is already paused) and `setPreviewOptIdx(null)`. Correct.

### Test

1. Generate a beat through the full magic_video pipeline (lipsync → Add magic on video → submit)
2. Confirm beat has `magic_video_path` set and `magic_still_path` is null/absent
3. Click "Preview Still" (▶ Preview Still button)
4. Listen: dialogue should play ONCE (from the video's baked audio), not twice
5. Confirm playback ends cleanly and button resets to ▶
6. Also test a beat that has BOTH magic_still_path and magic_video_path — confirm audio plays from `audioRef` (no regression on the still path)

---

## Dependency order

Fix Q1 first (server endpoint + path_picker.html) because Q2 depends on magic_video existing, and Q1 affects path drawing which produces the magic_video input. However both fixes are independent and can be dispatched in parallel.

## Files changed

| File | Change | Bug |
|---|---|---|
| `Production/tools/production_server.py` | Add `/api/video/thumbnail` GET endpoint | Q1 |
| `Production/tools/path_picker.html` | Replace `loadVideoFrameAsBackground()` body | Q1 |
| `Production/tools/storyboard-v2/src/components/StoryboardTab.tsx` | `previewSrcIsMagicVideo` guard in useEffect + 3 call sites in handlePreviewOption | Q2 |

## Branch

Work on `feature/overnight-watercolor-rebuild-20260526` (current branch per `git branch --show-current`).

## Verification after both fixes

1. Q1: Open path_picker in magic_video mode — canvas loads with lipsync video frame, not reference still. No 8s wait.
2. Q1: With server stopped, open path_picker in magic_video mode — yellow warning visible in drop-zone (not silent blank canvas).
3. Q2: Preview Still on a beat with only magic_video_path — single audio stream, no doubling.
4. Q2: Preview Still on a beat with magic_still_path — audio plays from audioRef as before (no regression).
5. Q2: Lipsync preview (▶ lipsync) — unchanged behavior.
