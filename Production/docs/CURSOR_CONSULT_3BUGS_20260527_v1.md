# MindfulNest — Three Persistent Bugs: Full Root Cause + Fix Spec
**Date:** 2026-05-27 | **Status:** Unresolved — ready for Cursor implementation  
**Severity:** HIGH — blocks visual QA on magic trail, watercolor animation, and storyboard audio

---

## Project Context

MindfulNest production server runs at `localhost:5111` (Python, `Production/tools/production_server.py`).

**Magic video:** Kim draws a path on a canvas showing where a sparkle trail should travel across a lipsync video clip (mouth animation already baked in). Server composites the sparkle trail frame-by-frame and outputs a final MP4.

**Watercolor animation:** A static watercolor PNG is converted to a short animated MP4 (oscillating motion) via PIL frame rendering. Used as an overlay in Phase B (meditation portion).

Both features have been reporting "verified working" for days while remaining broken. Root causes confirmed by direct code read. This document is self-contained.

---

## Key Files

| File | Purpose |
|---|---|
| `Production/tools/path_picker.html` | Browser UI for drawing the trail path. Sends normalized [0,1] coords (fx, fy). |
| `Production/tools/server_handlers/background.py` | `handle_magic_video` (~line 807), `handle_watercolor_animate` (~line 3703), ffmpeg composite pipeline (~line 1020–1110) |
| `Production/tools/magic_compositor.py` | Converts (fx,fy) path points → pixel coords against video W/H. Trail rendering. |
| `Production/tools/build_storyboard.py` | Generates storyboard HTML. Line audio (`playLine` ~line 1148). Magic video `<video>` elements (~lines 3031/3055/3075). |
| `Production/tools/server_handlers/phases.py` | `GET /api/phase/watercolor_file` consumer endpoint |

---

## BUG 1 — Magic trail appears in wrong position (diagonal across screen)

### Root cause (THREE compounding layers)

**1A — The video-frame loader silently falls back to a wrong canvas.**

`path_picker.html` line 467–542 (`loadVideoFrameAsBackground`) attempts to load frame 0 of the lipsync video into a hidden `<video>` element for the path-picker draw surface. This fails consistently with an 8-second timeout. Confirmed by browser console: `"[path_picker] Video frame load failed (timeout after 8s), falling back to still image"`.

The fallback calls `console.warn(...)` (browser console only, invisible to Kim) and loads the still image instead. **There is NO visible UI warning that coordinates will be wrong.**

Why the timeout fires: the hidden `<video>` element with `visibility:hidden` is subject to browser buffering/throttle races. The seek-then-capture handshake (`loadedmetadata → currentTime=0 → seeked → captureFrame`) is fragile — some browsers don't fire `seeked` if `currentTime` was already 0, or fire it before the frame is decoded. The 8s timer then fires the fallback.

**1B — Still image has different aspect ratio than the lipsync video.**

After fallback, `canvas.width = image.naturalWidth` (still's dimensions). `magic_compositor.py` line 413–416 maps `px = int(fx * self.W)` and `py = int(fy * self.H)` where `self.W, self.H` are the **lipsync video's** dimensions. If the still is 1024×1024 and the video is 720×544 (different aspect), a point drawn at fy=0.6 in the still (visually at Tessa's shell) maps to y = 0.6 × 544 = 326 in the video — but Tessa's shell is at a completely different fractional-y position in the video frame. Path drawn circling the shell on the still → trail cuts diagonally across the video.

**1C — Smoke tests overwrote Kim's production state with diagonal paths.**

During verification, browser smoke test Agents A and B each drew their own diagonal paths (A: upper-left to lower-right; B: different diagonal) and submitted them to the real `/api/storyboard/magic_video` endpoint. This overwrote `production_state.json`'s `videos.resolution.beats.beat_01.magic_video_path`. The diagonal trail Kim is seeing in her screenshot is partly the agent's path, not just the aspect mismatch. Future smoke tests MUST use a sandboxed `scope_event_id` that doesn't touch production state.

### Fix (three changes, all required)

**Change A — Server-side frame extraction endpoint** (replace fragile browser video decode)

In `Production/tools/server_handlers/background.py`, add a new handler:

```python
def handle_storyboard_video_frame(h, query: dict) -> None:
    """GET /api/storyboard/video_frame?path=<encoded>&t=0
    Returns PNG bytes of frame at time t (default 0) of the given video.
    Uses ffmpeg server-side (~50ms) instead of browser video decode (~8s timeout risk).
    """
    raw_path = query.get("path", "")
    if isinstance(raw_path, list):
        raw_path = raw_path[0] if raw_path else ""
    if not raw_path:
        return h._send_error_v59(400, error_code="PATH_REQUIRED",
                                 error_message="path required", retry_safe=False)
    p = Path(raw_path)
    if not p.is_absolute():
        p = Path(h.app.event_dir).parent.parent / raw_path
    safe = os.path.realpath(str(p))
    project_root = os.path.realpath(str(Path(h.app.event_dir).parent.parent))
    if not safe.startswith(project_root):
        return h._send_error_v59(403, error_code="PATH_OUT_OF_ROOT",
                                 error_message="path outside project root", retry_safe=False)
    t = 0.0
    t_raw = query.get("t", "0")
    if isinstance(t_raw, list):
        t_raw = t_raw[0] if t_raw else "0"
    try:
        t = float(t_raw or 0)
    except (ValueError, TypeError):
        t = 0.0
    cmd = ["ffmpeg", "-y", "-ss", str(t), "-i", safe,
           "-vframes", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10, check=False)
        if result.returncode != 0 or not result.stdout:
            return h._send_error_v59(500, error_code="FFMPEG_FRAME_EXTRACT_FAILED",
                                     error_message=result.stderr.decode('utf-8', errors='replace')[-500:],
                                     retry_safe=True)
        h.send_response(200)
        h.send_header("Content-Type", "image/png")
        h.send_header("Content-Length", str(len(result.stdout)))
        h.send_header("Cache-Control", "no-store")
        h.end_headers()
        h.wfile.write(result.stdout)
    except subprocess.TimeoutExpired:
        return h._send_error_v59(504, error_code="FFMPEG_FRAME_EXTRACT_TIMEOUT",
                                 error_message="ffmpeg timed out extracting frame",
                                 retry_safe=True)
```

Wire into the GET router: add `elif parsed.path == '/api/storyboard/video_frame':` in production_server.py.

**Change B — Replace broken video-element loader in path_picker.html**

Replace the entire `loadVideoFrameAsBackground` function (lines 467–542) with:

```javascript
function loadVideoFrameAsBackground(videoPath) {
    setDropText([
      { text: 'Loading frame from lipsync video…' },
      { tag: 'br' },
      { tag: 'small', style: 'color:#888', text: 'Draw your path on the actual video frame below.' },
    ]);
    const url = `http://localhost:5111/api/storyboard/video_frame?path=${encodeURIComponent(videoPath)}&t=0`;
    const image = new Image();
    image.onload = () => {
        applyImage(image);
        // Record dimensions so the server can aspect-correct coordinates.
        window.__pathAuthoredAgainst = { width: image.naturalWidth, height: image.naturalHeight };
    };
    image.onerror = () => {
        // HARD ERROR — do NOT fall back to still image.
        // A still-image fallback would use different aspect ratio and produce wrong trail positions.
        // Rule 19: no silent correctness-degrading fallbacks.
        console.error('[path_picker] Server-side frame extract failed — refusing to fall back to still (would cause coordinate mismatch).');
        setDropText([
          { text: '⚠️ Could not extract video frame from server.' },
          { tag: 'br' },
          { tag: 'small', style: 'color:#f88',
            text: 'Cannot fall back to still image — different aspect ratio would cause wrong trail position. Check server log.' },
        ]);
    };
    image.src = url;
}
```

**CRITICAL:** Do NOT keep a still-image fallback. A silent fallback that degrades correctness is a Rule 19 violation (no error paths). Kim must see an error if the endpoint fails.

Also update `submitPath()` to send `path_authored_against` in the POST body:
```javascript
// In the submitPath() function, find the fetch POST body and add:
path_authored_against: window.__pathAuthoredAgainst || null,
```

**Change C — Aspect-ratio correction in magic_compositor.py**

In `magic_compositor.py` `__init__` (around line 168), accept new optional param:
```python
def __init__(self, ..., path_authored_against: dict = None):
```

After `self.path_pts = path_pts`, add:
```python
self.path_pts = self._aspect_correct(self.path_pts, path_authored_against)
```

Add the method:
```python
def _aspect_correct(self, path_pts, authored):
    """Correct path coordinates if they were authored against a canvas with
    different aspect ratio than self.W/self.H (the compositor's canvas).
    Applies letterbox/pillarbox transform to preserve visual positions.
    """
    if not authored or "width" not in authored or "height" not in authored:
        return path_pts
    pw, ph = float(authored.get("width", 0)), float(authored.get("height", 0))
    if pw <= 0 or ph <= 0:
        return path_pts
    src_ar = pw / ph
    dst_ar = self.W / self.H
    if abs(src_ar - dst_ar) <= 0.01:
        return path_pts  # Same aspect — no correction needed
    corrected = []
    for (fx, fy) in path_pts:
        if src_ar > dst_ar:
            # source is wider: letterboxed top/bottom in destination
            scale = dst_ar / src_ar
            fy = (fy - 0.5) * scale + 0.5
        else:
            # source is taller: pillarboxed left/right in destination
            scale = src_ar / dst_ar
            fx = (fx - 0.5) * scale + 0.5
        corrected.append((fx, fy))
    print(f"  [aspect_correct] authored {pw:.0f}x{ph:.0f} (ar={src_ar:.3f}) → compositor {self.W}x{self.H} (ar={dst_ar:.3f}): corrected {len(corrected)} pts", flush=True)
    return corrected
```

Also pass `path_authored_against` through the call chain:
- `handle_magic_video` reads `path_authored_against = (body or {}).get("path_authored_against") or None`
- Pass it to `MagicCompositor(... path_authored_against=path_authored_against)`

### Verification for Bug 1

1. Start server. Open path_picker.html with `mode=magic_video` and a real `source_video_path`.
2. Open browser DevTools console — confirm NO `"Video frame load failed"` message appears.
3. Canvas should load within ~1 second showing the video frame (NOT a still).
4. Draw 4-6 points tracing a recognizable shape (e.g., circle around Tessa's shell).
5. Submit. Wait for completion.
6. Extract frame from output: `ffmpeg -i <output.mp4> -vframes 1 /tmp/frame0.png`
7. Open `/tmp/frame0.png`. Visually confirm the sparkle trail is at approximately the location you drew, NOT diagonal across the screen.
8. **FAIL condition:** if trail is more than ~50px away from drawn path, or cuts diagonally, the fix is incomplete.

---

## BUG 2 — Audio doubled ("whoah, where is it going now?" plays twice)

### Root cause

Two independent facts combine:

**Fact 1:** The magic_video output MP4 has the lipsync audio baked in. `background.py` encode_cmd line 1062: `-map 1:a?` copies audio from `safe_ffmpeg_src` (the lipsync source) into the output. The source has one audio stream (confirmed via ffprobe: `audio aac ch=2 dur=7.042540` — single stream).

**Fact 2:** `build_storyboard.py` `playLine(i)` function (~line 1148) plays `AU[k]` (a separate per-line TTS audio file) regardless of whether the beat has a magic_video with audio already embedded. When the storyboard preview plays beat_01, BOTH the magic_video's embedded lipsync audio AND the separate `AU[k]` TTS file play simultaneously → same dialogue heard twice.

The source video itself is NOT doubled. The doubling is purely in the storyboard playback layer.

### Fix

In `build_storyboard.py`, guard `playLine` to skip the `AU[k]` audio for beats that have a magic_video. The magic_video's embedded audio (lipsync) is the canonical version; the pre-lipsync TTS stem is the wrong source to play alongside it.

**Step 1:** When building the `L[]` line array in `build_storyboard.py`, add `magic_video_path` to each line entry. Find the loop that constructs `L.push({...})` entries and add:
```javascript
// Add to each line entry:
magic_video_path: ${json.dumps(beat.get('magic_video_path', None) or None)},
```
(Match the existing Python template syntax in the file.)

**Step 2:** In the `playLine` function (~line 1148), add a guard at the top:
```javascript
function playLine(i){
  stopAll();
  // NEW: beats with a magic_video have lipsync audio baked into the video.
  // Playing the separate AU[k] TTS stem on top doubles the dialogue.
  if (L[i] && L[i].magic_video_path) {
      // Advance the play-all sequencer without playing audio
      if (paA && paI===i) {
          var dur = (L[i].p || 3) * 1000;
          setTimeout(function(){
              if (!paA) return;
              var n = i + 1;
              while (n < L.length && (!L[n].a || !AU[L[n].a])) n++;
              if (n < L.length) { paI = n; playLine(n); }
              else { paA = false; document.getElementById("pab").innerHTML="&#9654; Play All (audio lines)"; }
          }, dur);
      }
      return;
  }
  var k = L[i].a;
  if(!k||!AU[k])return;
  // ... existing body continues unchanged
```

### Verification for Bug 2

1. Rebuild storyboard with `bash Production/scripts/deploy_storyboard_v59.sh` after changes.
2. Open storyboard for Event_1. Navigate to beat_01.
3. Click "Play All (audio lines)".
4. Listen to beat_01: confirm "whoah, where is it going now?" plays **exactly once**.
5. Also manually click the magic_video `<video>` element to play it. Confirm it plays with audio (embedded lipsync). Confirm the separate line audio does NOT also start.
6. **FAIL condition:** if the line plays twice, overlapping or in sequence, the fix is incomplete.

---

## BUG 3 — Watercolor animation not showing in Phase B

### Root cause (TWO independent failures)

**Root cause 3A (PRIMARY — state writeback absent):**

`handle_watercolor_animate` at `background.py` line 4027–4036 returns success:
```python
return h._send_json(200, {
    "ok": True,
    "watercolor_key": watercolor_key,
    "animated_path": str(out_path),
    "asset_id": registered_id,
    ...
})
```

**There is NO `scope_router.mutate_partition` call.** No state writeback. The beat state still has `watercolor_key: "hands_rubbing"` pointing at the static PNG. Phase B consumer reads `watercolor_key` from state, resolves it to the static file via `/api/phase/watercolor_file`, and never learns an animated version exists.

Compare to `handle_magic_video` (line 1243–1297) which correctly has:
```python
def _set_magic_video(partition: dict) -> None:
    beat["magic_video_path"] = magic_filename
scope_router.mutate_partition(h.app.state, scope, _set_magic_video)
# + DS-22 read-back verify
```

The watercolor handler has nothing equivalent. The prior task "RC1: Update cue watercolor_key after animation completes" was marked COMPLETE while this code change is verifiably absent.

**Root cause 3B (SECONDARY — postMessage origin mismatch):**

Even if the state were written correctly, the `path_picker.html` `submitPath()` success callback (line ~842) sends:
```javascript
window.opener.postMessage({ type: 'mn-magic-or-animate-complete', ... }, '*');
```

But `PhaseProducer.tsx` (line ~307) has a strict origin guard:
```typescript
if (e.origin !== window.location.origin) return;
```

If the path_picker is served from port 5111 and the storyboard is served from a different port (e.g., Vite's 5173), `e.origin` is `http://localhost:5111` but `window.location.origin` is `http://localhost:5173` — the guard rejects the message silently. RC1 never fires. The cue key is never updated client-side.

### Fix

**Change A — State writeback in handle_watercolor_animate**

In `background.py`, between line 4023 (end of the `register_asset` try block) and line 4027 (the `return h._send_json`), insert:

```python
    # State writeback — point Phase B consumers at the animated MP4.
    # Mirrors the magic_video writeback pattern at lines 1243–1297.
    animated_filename = Path(out_path).name
    scope = None
    try:
        scope = scope_router.resolve(body, h.app.event_dir.name)

        def _set_watercolor_animated(partition: dict) -> None:
            phase_b = partition.setdefault("phase_b", {})
            cues = phase_b.setdefault("cues", [])
            matched_any = False
            for cue in cues:
                if cue.get("watercolor_key") == watercolor_key:
                    cue["watercolor_animated_path"] = animated_filename
                    cue["watercolor_animated_asset_id"] = registered_id
                    matched_any = True
            if not matched_any:
                # No cue uses this key yet — store in the lookup map so
                # future cue assignments can find the animated version.
                ani_map = phase_b.setdefault("animated_watercolors", {})
                ani_map[watercolor_key] = {
                    "path": animated_filename,
                    "asset_id": registered_id,
                }

        scope_router.mutate_partition(h.app.state, scope, _set_watercolor_animated)
    except Exception as exc:
        print(f"[watercolor/animate] WARN state writeback failed: {exc}", flush=True)
        return h._send_error_v59(
                   500,
                   error_code="STATE_WRITEBACK_FAILED",
                   error_message=f"animated OK but state writeback failed: {exc}",
                   retry_safe=True,
                   extra={"animated_path": str(out_path), "asset_id": registered_id},
               )

    # DS-22 read-back verify (consumer-side: check phase_b, not just top-level)
    try:
        _state_after = h.app.state.read_state()
        _phase_b_after = _state_after.get("phase_b") or {}
        _cues_after = _phase_b_after.get("cues") or []
        _hit_cue = any(
            c.get("watercolor_key") == watercolor_key
            and c.get("watercolor_animated_path") == animated_filename
            for c in _cues_after
        )
        _ani_map = (_phase_b_after.get("animated_watercolors") or {})
        _hit_map = (_ani_map.get(watercolor_key) or {}).get("path") == animated_filename
        if not (_hit_cue or _hit_map):
            return h._send_error_v59(
                       500,
                       error_code="STATE_WRITEBACK_VERIFY_FAILED",
                       error_message="watercolor_animated_path not visible after writeback",
                       retry_safe=True,
                       extra={"expected_path": animated_filename, "expected_key": watercolor_key},
                   )
        print(f"[watercolor/animate] state writeback verified for key={watercolor_key}: {animated_filename}", flush=True)
    except Exception as exc:
        return h._send_error_v59(
                   500,
                   error_code="STATE_WRITEBACK_VERIFY_FAILED",
                   error_message=f"verify crashed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
               )
```

**Change B — Fix postMessage origin in path_picker.html**

Find line ~842 in `path_picker.html`:
```javascript
window.opener.postMessage({ type: 'mn-magic-or-animate-complete', ... }, '*');
```
Change to:
```javascript
window.opener.postMessage({ type: 'mn-magic-or-animate-complete', ... }, window.opener.location.origin);
```

This ensures `e.origin === window.location.origin` in PhaseProducer.tsx, so the strict origin check passes and RC1 fires.

**Change C — Consumer endpoint prefers animated version**

In `server_handlers/phases.py` (or wherever `GET /api/phase/watercolor_file` is handled), modify the resolver to prefer the animated path when present:

```python
def handle_phase_watercolor_file(h, query):
    key = query.get("key", "")
    if isinstance(key, list):
        key = key[0] if key else ""
    if not key:
        return h._send_error_v59(400, error_code="KEY_REQUIRED",
                                 error_message="key required", retry_safe=False)
    # NEW: check state for animated override first
    state = h.app.state.read_state()
    phase_b = state.get("phase_b") or {}
    animated_path = None
    for cue in (phase_b.get("cues") or []):
        if cue.get("watercolor_key") == key and cue.get("watercolor_animated_path"):
            animated_path = cue["watercolor_animated_path"]
            break
    if not animated_path:
        ani_map = (phase_b.get("animated_watercolors") or {})
        if key in ani_map:
            animated_path = (ani_map[key] or {}).get("path")
    if animated_path:
        # Resolve path relative to where handle_watercolor_animate writes: event_dir parent / watercolor_library
        # Check exact out_path construction at background.py line 3865
        wc_dir = _data_root(h) / "assets" / "watercolor_library"
        full = wc_dir / animated_path
        if full.exists():
            return _serve_file(h, full, content_type="video/mp4")
    # Fallback to static
    # ... existing logic unchanged
```

### Verification for Bug 3

1. Run `POST /api/watercolor/animate` for `key=hands_rubbing` with a real path and motion_description.
2. After 200 response, **immediately run:**
   ```bash
   curl -sI "http://localhost:5111/api/phase/watercolor_file?key=hands_rubbing" | grep -i content-type
   ```
   **MUST return `video/mp4`.** If it returns `image/png` or `image/jpeg`, the fix is incomplete.
3. Open the Phase B preview for the event. Navigate to the cue using `hands_rubbing`. Visually confirm the watercolor is **moving** (animated), not a static image.
4. Read `state.json` directly and confirm `phase_b.animated_watercolors.hands_rubbing.path` or `phase_b.cues[*].watercolor_animated_path` contains the animated filename.
5. **FAIL condition:** Content-Type is still image/*, OR the Phase B display shows a still PNG, OR state.json has no `watercolor_animated_path` field.

---

## What NOT to Do (Based on What Has Repeatedly Failed)

- **DO NOT** verify only "endpoint returned 200" or "file exists on disk" or "Directus row was written." These are necessary but NOT SUFFICIENT.
- **DO NOT** trust task-board "COMPLETE" status as proof code is in place. Re-grep the file for the specific change before declaring it deployed.
- **DO NOT** add a still-image fallback for the video-frame loader. Falling back to the still destroys coordinate correctness. Show a hard error instead.
- **DO NOT** let smoke-test agents POST to the real magic_video endpoint with their own paths. They overwrite Kim's production state. Smoke tests MUST use a sandbox scope or be read-only.
- **DO NOT** declare these bugs fixed without running the visual/audio verification steps above. "Storyboard shows checkmark badge" ≠ "trail is in the right place."
- **DO NOT** accept DS-22 state writeback as the only post-fix check. DS-22 verifies the producer wrote what it intended. These bugs require **consumer-side verification** — the consumer must actually display the correct output.
- **DO NOT** add timeout fallbacks without explicit Rule 19 approval. Silent fallbacks that degrade correctness are forbidden.

---

## Acceptance Criteria (all three must hold simultaneously)

**A — Trail position:** Kim draws a path circling Tessa's shell. Output frame 0 shows the sparkle trail at the shell, not diagonal across the screen. Verified by visual inspection of an extracted frame — every point of the drawn path should have a corresponding sparkle region within ~30px.

**B — Audio:** Storyboard preview of any beat with a magic_video plays the dialogue exactly once. Verified by listening AND by confirming no overlapping audio sources.

**C — Watercolor animation:** After running animate, `GET /api/phase/watercolor_file?key=<key>` returns `Content-Type: video/mp4`. The Phase B preview displays the animated MP4 with visible motion. Verified by Content-Type check AND visual inspection.

If ANY of (A), (B), (C) fails its visual/audio check, the fix is incomplete — regardless of state writeback, Directus rows, or endpoint-200 status.

---

## Files to Change

| File | Change |
|---|---|
| `Production/tools/server_handlers/background.py` | Add `handle_storyboard_video_frame` handler; add state writeback to `handle_watercolor_animate` |
| `Production/tools/production_server.py` | Wire new `/api/storyboard/video_frame` GET route |
| `Production/tools/path_picker.html` | Replace `loadVideoFrameAsBackground`; fix postMessage origin; add `path_authored_against` to submit body |
| `Production/tools/magic_compositor.py` | Add `path_authored_against` param and `_aspect_correct` method |
| `Production/tools/build_storyboard.py` | Add `magic_video_path` to `L[]` entries; guard `playLine` for magic_video beats |
| `Production/tools/server_handlers/phases.py` | Animated-preferred lookup in `/api/phase/watercolor_file` handler |

**Estimated time:** 90–120 minutes in Cursor. Verification per bug: 10–15 minutes each including visual confirmation.
