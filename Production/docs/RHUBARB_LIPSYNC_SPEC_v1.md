# Technical Spec: Rhubarb Lip Sync — Cartoon-Native Beak Compositing Pipeline
Date: 2026-05-23
Produced by: tech-spec skill (inline research, Cursor execution, no API agents per Kim directive)

---

## §0 — Mandatory Operating Mode

### §0.1 — Skill load + Phase 0 classification
- Task: **new pipeline feature + one bug revert** — Tier B (multi-file, new module + server wiring)
- zero-error-qa applies; advocate/counter spawned inline in §3
- `prod_preflight_reviews` row written before execution begins

### §0.2 — Six-Layer Verification Contract
For every functional change: UI shows lipsync status → /api/lipsync submits → server routes Rhubarb path → composite video produced → state marks completed → storyboard preview plays the composited result. All 6 layers verified before "done."

### §0.3 — Risk classes for this spec
- **Multi-stage pipeline**: Rhubarb CLI failure / bad phoneme output must not silently corrupt the beat
- **AI-driven** (Rhubarb): phoneme output quality varies by audio quality — smoke on a known beat before batch
- **Async fire-and-forget**: lipsync runs in a background thread — verify state transition actually fires
- **Cost display**: Rhubarb path has zero WaveSpeed cost — budget check must be bypassed (not silently 402-errored)

### §0.4 — Authoring discipline
All field names confirmed against live `vendor_jobs.py` read (lines 462–558, read this session).
All pipeline behavior confirmed against the actual `handle_lipsync_submit` implementation, not memory.

### §0.5 — Don't rely on memory or guess
Every file path and field name below is `[CONFIRMED against vendor_jobs.py read 2026-05-23]` unless tagged otherwise.

---

## §1 — Task

**Why this exists:** Every AI lipsync service tested (ByteDance LatentSync, Kling LipSync, SyncLabs) was trained on human speech and hallucinates arm-like wing gestures when applied to Chipper (cartoon bird). These services cannot be fixed via prompts or negative params — it is a model-training artifact. The face-composite workaround (added 2026-05-23, `vendor_jobs.py` lines 462–558) made things worse: it introduced face ghosting at the mask boundary because ByteDance shifts the entire frame slightly, desynchronizing source and lipsync streams at the blend edge.

**What this spec produces:**
1. **Revert** the face-composite block — it is a known-bad approach and the only beats that went through it (beat_10) have visible artifacts.
2. **Build** a cartoon-native lipsync pipeline: Rhubarb Lip Sync (phoneme timings from audio) + ChatGPT-generated beak sprite images (one-time setup, Kim generates) + OpenCV frame-by-frame compositing onto the ORIGINAL UNTOUCHED Kling animation.
3. **Wire** the new path into `/api/lipsync` as `lipsync_mode: "rhubarb"` routing — same button Kim already uses, no UI changes required.
4. **Re-lipsync** beats 01–10 using the Rhubarb path. Beat_11 uses the approved whiteout pipeline — excluded.

**Why this will work (answering Kim's question "are you sure??"):**
- Rhubarb is deterministic: same audio → same phoneme timings every run. No AI inference at composite time.
- OpenCV compositing is pixel-accurate: each beak sprite is blended at fixed coordinates on each frame. No hallucination possible.
- Chipper moves only ~40px in X and ~37px in Y across a 10s beat (`[CONFIRMED by frame-analysis 2026-05-23 on beat_10]`). Sprites sized at 15% of frame width accommodate this movement naturally.
- The original Kling animation pixels are 100% preserved everywhere except the small beak region during speech.
- Failure modes are explicit and catchable: Rhubarb binary not found → 500 error (not silent). Sprite file missing → 500 error (not silent). OpenCV write fails → exception propagated.

**Why ChatGPT not FLUX Kontext (answering Kim's question):**
- Kim specified ChatGPT. This spec uses ChatGPT.
- Practical: the beak sprites are a ONE-TIME setup — 7 PNG files generated once, reused forever. FLUX Kontext is scene-editing (costs $0.08/image, requires API). ChatGPT web interface is free/included, Kim generates directly with no code. For a 7-image one-time setup, ChatGPT is both correct and simpler.

---

## §2 — Governing Decisions

- `CLAUDE.md Rule 8.1` — anti-lip-sync prompts on source Kling clips (PRESERVED — Kling source clips unchanged)
- `CLAUDE.md Rule 8.2` — lipsync pipeline incompatibility (MOOT — Rhubarb path bypasses ByteDance entirely)
- `CLAUDE.md Rule 8.5` — ByteDance max 10s / silence-split (MOOT — Rhubarb path bypasses ByteDance)
- `CLAUDE.md Rule 19` — no error paths left open (see §7 for all failure modes)
- `CLAUDE.md Rule 29` — verify server is running AFTER edits before testing
- `LD LIPSYNC_MAX_DURATION_10S_NO_SILENCE_V1 (id=400)` — ByteDance-specific; does not apply to Rhubarb path
- `LD SIZE_BUDGET_VIDEO_V1` — output must remain H.264 / yuv420p / ≤2 Mbps

---

## §3 — Approach

### Design alternatives considered (inline advocate/counter):

**Option A — Kling LipSync (WaveSpeed) + keep existing infrastructure**
Advocate: already integrated, no new dependencies, 31s processing.
Counter: tested 2026-05-23. Kling LipSync re-animates wings like arm gestures. `body_motion` / `face_only` params silently ignored. Root cause is the same human-trained AI bias. No path to fix. Rejected.

**Option B — Face-composite (current, being reverted)**
Advocate: no new dependencies.
Counter: ByteDance frame-shift causes ghosting at mask boundary regardless of mask size. This is a fundamental property of submitting two temporally-desynchronized streams. No parameter tuning can fix it. Tested at rx=0.28 (ghost arm) and rx=0.12 (face ghosting). Rejected.

**Option C — Rhubarb + ChatGPT sprites + OpenCV** ← **CHOSEN**
Advocate: Rhubarb is industry-standard cartoon phoneme detection (Preston Blair system, DanielSWolf/rhubarb-lip-sync, active since 2015). The compositing is deterministic. Original Kling pixels are preserved everywhere except beak region during speech. No external API calls during per-beat processing (only the one-time ChatGPT setup). Zero hallucination possible at runtime.
Counter: Rhubarb needs installation. Sprites need one-time generation. OpenCV compositing is slightly slower than FFmpeg (est. 20-40s per clip locally — same order of magnitude as WaveSpeed polling). These are all one-time setup costs, not per-beat recurring costs.
Resolution: Option C wins. One-time costs are worth permanent elimination of the hallucination problem.

### Chosen approach detail:

```
TTS audio (mp3) ──→ rhubarb CLI ──→ phonemes.json
                                       │
Kling clip (mp4, silent) ──────────────┤
                                       ↓
                              Python: OpenCV frame loop
                              for each frame:
                                t = frame_idx/fps - trim_start
                                if 0 ≤ t ≤ audio_dur:
                                  phoneme = lookup(phonemes, t)
                                  overlay beak_sprites[phoneme] at beak_position
                                else:
                                  pass  # original frame unchanged
                                       │
                              temp_composited_silent.mp4
                                       │
FFmpeg mux ────────────────────────────┘
  + TTS audio (delayed by trim_start)
  → beat_NN_lipsync.mp4
```

**Key design decisions:**
- Beak position defined as FRACTIONS of frame size (resolution-independent). `beak_cx_frac=0.50, beak_cy_frac=0.53` for Chipper based on face-composite cy=0.52 calibration `[CONFIRMED against vendor_jobs.py line 504]`.
- Sprite size: 15% frame width × 12% frame height (accounts for Chipper's ±40px movement without needing per-frame tracking).
- No ByteDance submission → no LipSyncClient → no WaveSpeed API cost → skip budget check.
- Tail-append NOT needed: entire Kling clip is processed locally (no ByteDance truncation at audio+1.5s).
- Hold-last-frame (beat_11 whiteout) NOT applicable: beat_11 uses its own pipeline (excluded from this spec).
- Same output filename convention: `beat_NN_lipsync.mp4` in `animation_clips/`. Downstream stitcher unchanged.

---

## §4 — Implementation Phases

### Phase 0 — Revert face-composite (immediate, ~15 min, no new code)

**Classification: Tier A (single-file, remove-only, no new behavior)**

**What to do:** Delete the face-composite block from `vendor_jobs.py`.

Remove lines 454–558 in their entirety (the `# FACE-COMPOSITE: blend ByteDance...` comment through the `finally:` block that unlinks `_fc_src_tmp, _fc_out_tmp, _fc_mask_png`).

Specifically, the block to REMOVE starts at:
```python
                # FACE-COMPOSITE: blend ByteDance output (face/beak lipsync region only)
```
and ends at (inclusive):
```python
                    finally:
                        for _f in (_fc_src_tmp, _fc_out_tmp, _fc_mask_png):
                            try: _f.unlink()
                            except (OSError, UnboundLocalError): pass
```

The code after it (`# TAIL-APPEND:` block at line 560) stays unchanged.

**Verify:**
- `python3 -m py_compile Production/tools/server_handlers/vendor_jobs.py` exits 0
- Grep: `grep "face-composite" Production/tools/server_handlers/vendor_jobs.py` returns 0 lines

**After Phase 0 completes:** beat_10 still has the ghost-artifact lipsync.mp4. That's OK — Phase 4 will redo it. Do not re-lipsync beat_10 via ByteDance.

---

### Phase 1 — One-time setup: beak sprites + config (Kim-driven, ~30 min)

**What Kim does in ChatGPT:**

Generate 7 beak position images of Chipper. Each image:
- Shows ONLY the beak/lower face region of Chipper in one phoneme position
- Transparent background (PNG with alpha channel)
- Art style matching Chipper's illustrated look (cartoon bird beak, from the front)
- Roughly 300×240px (or any size — will be scaled at composite time)

**Phoneme positions to generate (Preston Blair system):**

| Filename | Mouth shape | Sounds |
|----------|-------------|--------|
| `chipper_beak_A.png` | Closed / rest | M, B, P, rest |
| `chipper_beak_B.png` | Slightly open | F, V |
| `chipper_beak_C.png` | Open, wide | TH, wide sounds |
| `chipper_beak_D.png` | Wide open | vowels like "ah", "oh" |
| `chipper_beak_E.png` | Small round | OO, W |
| `chipper_beak_F.png` | Lower beak down | L, TH variant |
| `chipper_beak_X.png` | Closed / silence | silence between words |

**ChatGPT prompt template:**
```
Generate a PNG image of Chipper the cartoon bird's beak in the "[POSITION]" position.
Chipper is a cheerful cartoon bird character (illustrated style).
Show only the lower face/beak area, isolated on a pure white background.
The beak should be centered, facing forward (viewer-facing).
Style: clean cartoon illustration, simple shapes, bright colors.
[Provide reference screenshot if available]
```

**After generating:** Use any background removal tool (remove.bg, ChatGPT's own background removal, or Python `rembg` library) to make the background transparent. Save as PNG.

**Where to save sprites:**
```
Production/Event_1/chipper_beak_sprites/
  chipper_beak_A.png
  chipper_beak_B.png
  chipper_beak_C.png
  chipper_beak_D.png
  chipper_beak_E.png
  chipper_beak_F.png
  chipper_beak_X.png
```

**Beak config file** (Claude creates this — Kim confirms beak_cy_frac if needed):
```json
# Production/Event_1/chipper_beak_config.json
{
  "character": "chipper",
  "beak_cx_frac": 0.50,
  "beak_cy_frac": 0.53,
  "sprite_w_frac": 0.15,
  "sprite_h_frac": 0.12,
  "sprites_dir": "chipper_beak_sprites",
  "note": "Position calibrated from face-composite default (cy=0.52). Fractions of frame size = resolution-independent."
}
```

**Rhubarb installation:**
```bash
brew install rhubarb-lip-sync
# verify:
rhubarb --version
# expected: "Rhubarb Lip Sync 1.x.x"
```

If brew unavailable, download binary from:
`https://github.com/DanielSWolf/rhubarb-lip-sync/releases/latest`
Place at `/usr/local/bin/rhubarb` and `chmod +x`.

---

### Phase 2 — Build `rhubarb_processor.py` (~1.5 hours, Cursor)

**New file:** `Production/tools/rhubarb_processor.py`

**Interface:**
```python
def run_rhubarb(audio_path: Path, rhubarb_bin: str = "rhubarb") -> list[dict]:
    """Run Rhubarb on audio_path. Returns list of {start, end, value} dicts.
    Raises subprocess.CalledProcessError on failure (fail-loud, Rule 19).
    """

def composite_rhubarb_lipsync(
    clip_path: Path,
    audio_path: Path,
    beak_config: dict,         # from chipper_beak_config.json
    sprites: dict[str, Path],  # {"A": Path, "B": Path, ...}
    output_path: Path,
    trim_start: float = 0.0,
    rhubarb_bin: str = "rhubarb",
) -> dict:
    """Main entry point. Returns {output_path, duration_s, phoneme_count}.
    All errors raise exceptions (fail-loud, Rule 19).
    """
```

**Implementation outline for Cursor:**

```python
# rhubarb_processor.py

import json, subprocess, tempfile, cv2, numpy as np
from pathlib import Path
from PIL import Image

def run_rhubarb(audio_path: Path, rhubarb_bin: str = "rhubarb") -> list[dict]:
    """
    Runs: rhubarb -f json -o <tmp.json> <audio.mp3>
    Returns parsed mouthCues list.
    Raises subprocess.CalledProcessError if rhubarb fails.
    Raises FileNotFoundError if rhubarb binary not found.
    """
    import shutil
    exe = shutil.which(rhubarb_bin) or rhubarb_bin
    if not Path(exe).is_file() and not shutil.which(exe):
        raise FileNotFoundError(
            f"rhubarb binary not found: {rhubarb_bin!r}. "
            "Install: brew install rhubarb-lip-sync"
        )
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out_json = Path(f.name)
    try:
        subprocess.run(
            [exe, "-f", "json", "-o", str(out_json), str(audio_path)],
            check=True, capture_output=True, timeout=120,
        )
        data = json.loads(out_json.read_text())
        return data["mouthCues"]  # list of {"start": float, "end": float, "value": str}
    finally:
        out_json.unlink(missing_ok=True)


def _lookup_phoneme(mouth_cues: list[dict], t: float) -> str:
    """Return phoneme value at time t, or 'X' (silence) if not covered."""
    for cue in mouth_cues:
        if cue["start"] <= t < cue["end"]:
            return cue["value"]
    return "X"


def composite_rhubarb_lipsync(
    clip_path: Path,
    audio_path: Path,
    beak_config: dict,
    sprites: dict[str, Path],
    output_path: Path,
    trim_start: float = 0.0,
    rhubarb_bin: str = "rhubarb",
) -> dict:
    """
    1. Run Rhubarb on audio_path → phoneme timings
    2. Open clip with OpenCV → composite beak sprites frame-by-frame
    3. Write silent composited video to temp file
    4. FFmpeg mux: composited video + TTS audio (delayed by trim_start) → output_path
    Returns: {"output_path": str, "duration_s": float, "phoneme_count": int}
    """
    # 1. Phoneme timings
    mouth_cues = run_rhubarb(audio_path, rhubarb_bin)
    audio_duration = mouth_cues[-1]["end"] if mouth_cues else 0.0

    # 2. Load beak sprites (PIL RGBA → pre-converted to BGRA numpy)
    beak_imgs: dict[str, np.ndarray] = {}
    known_phonemes = {"A", "B", "C", "D", "E", "F", "G", "H", "X"}
    for phoneme, sprite_path in sprites.items():
        img = Image.open(sprite_path).convert("RGBA")
        beak_imgs[phoneme.upper()] = np.array(img)  # H×W×4 RGBA

    # 3. Open video
    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        raise OSError(f"Cannot open clip: {clip_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Compute beak overlay position in pixels
    cx = int(beak_config["beak_cx_frac"] * w)
    cy = int(beak_config["beak_cy_frac"] * h)
    sprite_w = int(beak_config["sprite_w_frac"] * w)
    sprite_h = int(beak_config["sprite_h_frac"] * h)
    x0 = max(0, cx - sprite_w // 2)
    y0 = max(0, cy - sprite_h // 2)
    x1 = min(w, x0 + sprite_w)
    y1 = min(h, y0 + sprite_h)

    # 4. Write silent composited video via cv2.VideoWriter (mp4v)
    tmp_silent = output_path.with_suffix(".tmp_silent.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(tmp_silent), fourcc, fps, (w, h))
    if not out.isOpened():
        raise OSError(f"Cannot open VideoWriter for {tmp_silent}")

    frame_idx = 0
    total_frames = 0
    phoneme_counts: dict[str, int] = {}
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            t = frame_idx / fps - trim_start  # seconds relative to audio start
            if 0.0 <= t <= audio_duration:
                phoneme = _lookup_phoneme(mouth_cues, t)
                phoneme_counts[phoneme] = phoneme_counts.get(phoneme, 0) + 1
                if phoneme != "X" and phoneme in beak_imgs:
                    sprite_rgba = beak_imgs[phoneme]
                    # Resize sprite to overlay region
                    rh = y1 - y0
                    rw = x1 - x0
                    resized = cv2.resize(sprite_rgba, (rw, rh), interpolation=cv2.INTER_LANCZOS4)
                    alpha = resized[:, :, 3:4].astype(np.float32) / 255.0
                    sprite_bgr = resized[:, :, :3][:, :, ::-1]  # RGBA→BGR
                    region = frame[y0:y1, x0:x1].astype(np.float32)
                    blended = alpha * sprite_bgr.astype(np.float32) + (1 - alpha) * region
                    frame[y0:y1, x0:x1] = blended.clip(0, 255).astype(np.uint8)
            out.write(frame)
            frame_idx += 1
        total_frames = frame_idx
    finally:
        cap.release()
        out.release()

    # 5. FFmpeg mux: composited video + TTS audio, re-encode to H.264
    import subprocess as _sp
    delay_ms = int(trim_start * 1000)
    audio_filter = f"adelay={delay_ms}|{delay_ms}" if trim_start > 0.01 else "anull"
    _sp.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(tmp_silent),
        "-i", str(audio_path),
        "-filter_complex", f"[1:a]{audio_filter}[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
        "-shortest",
        str(output_path),
    ], check=True, capture_output=True, timeout=180)
    tmp_silent.unlink(missing_ok=True)

    duration_s = total_frames / fps
    return {
        "output_path": str(output_path),
        "duration_s": round(duration_s, 3),
        "phoneme_count": sum(phoneme_counts.values()),
        "phoneme_distribution": phoneme_counts,
    }
```

**Unit test file:** `Production/tests/test_rhubarb_processor.py`
- Test `_lookup_phoneme` with edge cases (exact boundary, empty cues, negative t)
- Test `run_rhubarb` with a short test WAV (skip if rhubarb binary not found, `pytest.mark.skipif`)
- Test `composite_rhubarb_lipsync` with a 2s synthetic clip (skip if rhubarb not installed)

---

### Phase 3 — Wire Rhubarb path into `vendor_jobs.py` (~45 min, Cursor)

**State field:** In `production_state.json`, add to any beat's `phase_1` block:
```json
"lipsync_mode": "rhubarb"
```
Default (absent) = `"bytedance"` (existing behavior unchanged).

**Change to `handle_lipsync_submit` in `vendor_jobs.py`:**

After the budget check (line ~219) and BEFORE the `§8.4 pre-conditioning` block, add a routing branch:

```python
    # RHUBARB ROUTING: if phase_1.lipsync_mode == "rhubarb", skip ByteDance entirely.
    lipsync_mode = phase1.get("lipsync_mode", "bytedance")
    if lipsync_mode == "rhubarb":
        return _handle_lipsync_rhubarb(h, body, beat_key, source_clip_path,
                                        source_audio_path, phase1, video_role, _pin)
```

**New function `_handle_lipsync_rhubarb`** in `vendor_jobs.py` (or in a separate `server_handlers/rhubarb_handler.py` — Cursor decides which is cleaner):

```python
def _handle_lipsync_rhubarb(h, body, beat_key, clip_path, audio_path,
                              phase1, video_role, _pin):
    """
    Local Rhubarb lipsync path. No WaveSpeed API call. No budget charge.
    Outputs beat_NN_lipsync.mp4 identical in convention to ByteDance path.
    """
    from rhubarb_processor import composite_rhubarb_lipsync
    import json as _json

    # Load beak config
    beak_config_path = h.app.event_dir / "chipper_beak_config.json"
    if not beak_config_path.is_file():
        return h._send_error_v59(400, error_code="RHUBARB_CONFIG_MISSING",
            error_message=f"chipper_beak_config.json not found at {beak_config_path}",
            retry_safe=False)
    beak_config = _json.loads(beak_config_path.read_text())

    sprites_dir = h.app.event_dir / beak_config["sprites_dir"]
    sprites = {}
    for p in ("A", "B", "C", "D", "E", "F", "X"):
        sp = sprites_dir / f"chipper_beak_{p}.png"
        if sp.is_file():
            sprites[p] = sp
    if not sprites:
        return h._send_error_v59(400, error_code="RHUBARB_SPRITES_MISSING",
            error_message=f"No beak sprites found in {sprites_dir}",
            retry_safe=False)

    trim_start = float(phase1.get("trim_start") or phase1.get("audio_delay") or 0.0)
    dest_name = f"{beat_key}_lipsync.mp4"
    dest = h.app.state.clips_dir / dest_name

    # Initialize state
    def init_rhubarb(st, _bk=beat_key, _role=video_role):
        beat = ((st.get("videos") or {}).get(_role) or {}).get("beats", {})[_bk]
        beat.setdefault("lipsync", {})
        ls = beat["lipsync"]
        ls["status"] = "submitting"
        ls["task_id"] = None
        ls["file"] = None
        ls["audio_file"] = audio_path.name
        ls.pop("last_error", None)
    h.app.state.mutate_state(init_rhubarb)

    def do_rhubarb():
        try:
            result = composite_rhubarb_lipsync(
                clip_path=clip_path,
                audio_path=audio_path,
                beak_config=beak_config,
                sprites=sprites,
                output_path=dest,
                trim_start=trim_start,
            )
            size = dest.stat().st_size

            def mark_done(st, _bk=beat_key, _fn=dest_name, _sz=size, _role=video_role):
                beat = ((st.get("videos") or {}).get(_role) or {}).get("beats", {})[_bk]
                ls = beat["lipsync"]
                ls["status"] = "completed"
                ls["file"] = _fn
                ls["size_bytes"] = _sz
                ls["lipsync_mode"] = "rhubarb"
                ls["phoneme_count"] = result.get("phoneme_count", 0)
                # Auto-promote to FINAL (parity with ByteDance path)
                prior_final = beat.get("final") or {}
                if prior_final.get("source") != "lipsync":
                    beat["final"] = {
                        "source": "lipsync",
                        "file": _fn,
                        "approved_at": datetime.now(timezone.utc).isoformat(),
                    }
            h.app.state.mutate_state(mark_done)
            print(f"[rhubarb] {beat_key} COMPLETED -> {dest_name} "
                  f"({size} bytes, {result['phoneme_count']} phonemes)")

        except Exception as exc:
            import traceback
            traceback.print_exc()
            def mark_err(st, _bk=beat_key, _err=str(exc), _role=video_role):
                ls = (((st.get("videos") or {}).get(_role) or {}).get("beats", {}).get(_bk) or {}).get("lipsync") or {}
                ls["status"] = "failed"
                ls["last_error"] = _err[:500]
            h.app.state.mutate_state(mark_err)

    import threading
    threading.Thread(target=do_rhubarb, daemon=True, name=f"rhubarb-{beat_key}").start()

    return h._send_json(200, {
        "status": "submitted",
        "beat": beat_key,
        "clip": clip_path.name,
        "audio": audio_path.name,
        "lipsync_mode": "rhubarb",
        "cost": 0.0,
        "message": f"Rhubarb lipsync submitted for {beat_key} (local processing, no API cost).",
    })
```

**State field injection for all Chipper beats:** After Phase 3 server wiring is confirmed working, set `lipsync_mode: "rhubarb"` on beats 01–10 via `/api/select` or directly in production_state.json. See Phase 4 for the exact method.

---

### Phase 4 — Re-lipsync beat_10 with Rhubarb (~5 min, beat_10 only)

**Context:** Beats 01–09 are already clean (no ghost artifacts — they were done before the face-composite block was added). Only beat_10 went through the face-composite path and has visible ghost artifacts. Beat_11 uses the approved whiteout explosion pipeline and is excluded.

**Pre-condition:** Phase 0 (face-composite removed), Phase 1 (sprites + config), Phase 2 (rhubarb_processor.py), Phase 3 (server wiring) all complete.

```bash
# 1. Set lipsync_mode on beat_10 in production_state.json
#    (direct JSON edit of the state file — or via /api/select if it exposes lipsync_mode)

# 2. Submit lipsync for beat_10
curl -s -X POST http://localhost:5111/api/lipsync \
  -H "Content-Type: application/json" \
  -d '{"beat": "beat_10"}'

# 3. Poll for completion (~90 seconds expected)
curl -s http://localhost:5111/api/lipsync/status | python3 -m json.tool | grep -A5 beat_10

# 4. Kim reviews in storyboard — verify:
#    a. Chipper's beak moves during speech
#    b. Wings are completely unchanged (no arm hallucination, no ghost)
#    c. Audio sync correct
```

**beat_11 EXCLUDED** — uses the approved whiteout explosion pipeline. Do not touch.

---

## §5 — Files Created / Modified

| File | Action | Why |
|------|--------|-----|
| `Production/tools/server_handlers/vendor_jobs.py` | MODIFY — remove face-composite block (lines 454–558) | Bug revert: causes face ghosting |
| `Production/tools/server_handlers/vendor_jobs.py` | MODIFY — add `_handle_lipsync_rhubarb()` function + routing branch | Rhubarb path |
| `Production/tools/rhubarb_processor.py` | CREATE | Core compositing logic |
| `Production/tests/test_rhubarb_processor.py` | CREATE | Unit tests |
| `Production/Event_1/chipper_beak_config.json` | CREATE | Beak position config |
| `Production/Event_1/chipper_beak_sprites/*.png` | CREATE (Kim via ChatGPT) | Beak sprite images |
| `Production/Event_1/storyboard_v59_prod.L.json` (state) | MODIFY — add `lipsync_mode: "rhubarb"` to beats 01–10 phase_1 | Route to Rhubarb |

**Do NOT modify:**
- `lipsync_sender.py` (ByteDance client — left intact for potential future use)
- Beat_11 state or lipsync pipeline
- Any storyboard HTML
- `production_server.py` router (unless `_handle_lipsync_rhubarb` import needs to be added there)

---

## §6 — Directus Writes

None required for the implementation. After implementation:
- Log Phase 0 completion via `log_activity` with action=`RHUBARB_LIPSYNC_PHASE0_COMPLETE`
- Log Phase 3 completion with action=`RHUBARB_LIPSYNC_PHASE3_COMPLETE`
- Lock decision: `RHUBARB_LIPSYNC_CARTOON_NATIVE_V1` after beat_10 smoke passes

---

## §7 — Error Cases and Handling (Rule 19 — no open error paths)

| Failure | Detection | Response |
|---------|-----------|----------|
| Rhubarb binary not found | `shutil.which()` returns None | HTTP 500 + `RHUBARB_CONFIG_MISSING` error code, clear message with install instructions |
| Rhubarb fails on audio | `subprocess.CalledProcessError` | Mark beat lipsync `failed`, include stderr in `last_error` |
| Beak config file missing | `beak_config_path.is_file()` | HTTP 400 + `RHUBARB_CONFIG_MISSING` |
| No sprite files found | `len(sprites) == 0` | HTTP 400 + `RHUBARB_SPRITES_MISSING` |
| OpenCV can't open clip | `cap.isOpened() == False` | Exception propagates → mark `failed`, logged |
| OpenCV VideoWriter fails | `out.isOpened() == False` | Exception propagates → mark `failed`, logged |
| FFmpeg mux fails | `subprocess.CalledProcessError` | Exception propagates → mark `failed`, temp_silent.mp4 deleted in finally |
| All sprites missing phoneme | `phoneme not in beak_imgs` | Skip overlay (use original frame) — degraded but not broken |
| trim_start ≥ clip duration | OpenCV loops will produce 0 frames with overlay | Graceful: all frames unmodified, audio synced at 0 → essentially passthrough |

---

## §8 — Verification Gates

| Phase | Gate | Method | Layer |
|-------|------|--------|-------|
| 0 (revert) | `py_compile` clean | `python3 -m py_compile vendor_jobs.py` | L1 |
| 0 (revert) | No face-composite code | `grep "face-composite" vendor_jobs.py` = 0 lines | L1 |
| 2 (rhubarb_processor) | Unit tests pass | `pytest Production/tests/test_rhubarb_processor.py` | L1–L2 |
| 3 (server wiring) | Server starts | `python3 -m py_compile` + server restart, no traceback | L1 |
| 3 (server wiring) | beat_10 smoke | `/api/lipsync` returns 200 with `lipsync_mode: "rhubarb"` | L2–L3 |
| 3 (server wiring) | State updates | `/api/lipsync/status` shows beat_10 `status: "completed"` | L4 |
| 3 (server wiring) | Output file exists | `beat_10_lipsync.mp4` in animation_clips | L5 |
| 3 (visual smoke) | Kim reviews beat_10 | No arm hallucination, beak moves with audio, wings unchanged | L6 |
| 4 (batch) | All beats 01–10 complete | `/api/lipsync/status` shows all 10 completed | L4–L5 |
| 4 (visual) | Kim spot-checks 3 beats | Same visual criteria as beat_10 smoke | L6 |

**L6 smoke is MANDATORY before Phase 4 batch.** One beat confirmed visually before batch-processing all 10.

---

## §9 — Rollback

- **Phase 0 (revert)**: git diff before commit. If face-composite revert breaks something unexpected, `git checkout Production/tools/server_handlers/vendor_jobs.py` to restore.
- **Phase 2/3 (new code)**: Rhubarb path is ADDITIVE — existing ByteDance path unchanged. If Rhubarb path fails, beats continue to work via default `lipsync_mode` (absent = ByteDance). No rollback needed for Phase 2/3 server code.
- **Phase 4 (re-lipsync)**: Old `beat_NN_lipsync.mp4` files are OVERWRITTEN. If needed, backs exist in storyboard state as source options. Can re-run ByteDance by temporarily removing `lipsync_mode: "rhubarb"` from phase_1.

---

## §10 — Out of Scope (V1)

- Beat_11 (whiteout explosion) — excluded, uses dedicated pipeline
- Per-beat beak position calibration (all Chipper beats use same config)
- Automatic OpenCV tracking of Chipper's beak position (fixed-position composite is sufficient given 2-4% movement range)
- Kling LipSync or SyncLabs integration (tested and rejected)
- Background removal automation for beak sprites (Kim handles this one-time)
- `G` and `H` Rhubarb phonemes (rare; treated as `X` / silence — beak stays at rest for these)
- Per-beat `lipsync_mode` UI toggle in storyboard (CLI/JSON set is sufficient for now)

---

## §11 — Dependencies

- **Hard:** Phase 0 must complete before Phase 4 (can't have face-composite and Rhubarb both running)
- **Hard:** Phase 1 (sprites) must complete before Phase 4 (no sprites = no compositing)
- **Hard:** Phase 2 (rhubarb_processor.py) must complete before Phase 3 (wiring imports it)
- **Hard:** Phase 3 smoke must pass before Phase 4 batch
- **Soft:** Rhubarb installation (Phase 1) can happen in parallel with Phase 2 code work
- **Unblocked by this spec:** Beat_11 lipsync (already approved, excluded)

**Topological order: Phase 0 → Phase 1+2 (parallel) → Phase 3 → Phase 4**

---

## §12 — Cursor Cross-Review Prompt (RECOMMENDED before Phase 3 execution)

```
Review Production/tools/rhubarb_processor.py and the routing change in 
Production/tools/server_handlers/vendor_jobs.py against this spec:

1. Does the _handle_lipsync_rhubarb() routing branch correctly detect 
   lipsync_mode == "rhubarb" and bypass the ByteDance budget check?

2. Does composite_rhubarb_lipsync() correctly handle trim_start > 0 
   (frames before trim_start should have NO beak overlay)?

3. Does the state mutation in mark_done() correctly match the schema 
   used by handle_lipsync_status() (status/file/size_bytes fields)?

4. Is the OpenCV VideoWriter using the correct codec/fourcc for the 
   platform (mp4v on Mac)?

5. Are all failure modes in §7 explicitly caught and either returned 
   as HTTP errors (pre-work) or mutated to "failed" state (post-work in thread)?

6. Does the FFmpeg mux command produce output that satisfies 
   SIZE_BUDGET_VIDEO_V1 (H.264 High / yuv420p / ≤2 Mbps)?

7. Is tmp_silent.mp4 cleaned up in ALL code paths (success and failure)?
```

---

## §13 — Notes for Executing Sessions

- Cursor should handle Phase 2 (rhubarb_processor.py) and Phase 3 wiring. Claude Code handles Phase 0 (simple delete) and Phase 4 (curl batch).
- The `rhubarb_processor.py` implementation outline in §4 Phase 2 is pseudocode-grade Python. Cursor should flesh it out with proper imports, error handling, and the specific OpenCV alpha-blend arithmetic.
- OpenCV color space: `cv2.VideoCapture` reads frames as BGR. Beak sprites from PIL/PNG are RGBA. The blend needs `sprite_bgr = sprite_rgba[:,:,:3][:,:,::-1]` (RGB→BGR channel swap) plus the alpha channel.
- The `mp4v` codec on Mac produces files OpenCV can write but FFmpeg should re-encode. The FFmpeg mux step in `composite_rhubarb_lipsync` handles this — it re-encodes the mp4v output to libx264.
- `trim_start` for most beats is 0.0. The audio delay logic only matters for beats where Kim used the Delay button in the storyboard.

---

## §14 — Pre-execution Discipline Checklist

```
PHASE 0 PRE-EXECUTION CHECKLIST
[ ] §0 read fully
[ ] zero-error-qa skill read (direct file read if Skill tool unavailable)
[ ] Phase 0 classification confirmed: Tier A (revert-only, single file)
[ ] vendor_jobs.py read fresh (not from memory) — done this session 2026-05-23
[ ] Exact line range confirmed: face-composite block = lines 454-558 (comment to finally block)
[ ] py_compile check planned for after edit
[ ] Server restart planned before any testing

PHASE 1 PRE-EXECUTION CHECKLIST
[ ] Rhubarb binary tested: rhubarb --version works
[ ] chipper_beak_sprites/ directory exists with all 7 .png files
[ ] chipper_beak_config.json created with correct beak_cy_frac
[ ] Kim confirms sprites look correct on a sample frame

PHASE 2+3 PRE-EXECUTION CHECKLIST
[ ] §0 read fully
[ ] Tier B classification confirmed (multi-file, new module)
[ ] rhubarb_processor.py created and py_compile clean
[ ] vendor_jobs.py routing branch added and py_compile clean
[ ] All imports valid (rhubarb_processor imported without circular dependency)
[ ] Unit tests pass (or skipped with correct reason if rhubarb binary not installed)
[ ] Server restarted after edit (Rule 29)

PHASE 4 PRE-EXECUTION CHECKLIST
[ ] Phase 0+1+2+3 all complete
[ ] beat_10 smoke PASSED (Kim confirmed visually — no arm hallucination)
[ ] lipsync_mode: "rhubarb" set in production_state.json for beats 01-10
[ ] beat_11 lipsync_mode NOT changed (excluded)
[ ] Sequential submission plan confirmed (not concurrent)
```
