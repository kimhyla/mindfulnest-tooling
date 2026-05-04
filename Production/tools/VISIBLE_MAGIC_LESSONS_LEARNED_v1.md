# Visible Magic Compositor — Lessons Learned & Skill Spec
## Version: v1 — 2026-04-23
## Purpose: First attempt should work correctly without iteration

This document captures everything learned across ~20 iterations building the sparkle-trail "visible magic" effects for MindfulNest Event 1 Beat 2. Use this as the primary reference any time Kim says **"use the visible magic making spell"** or **"make a visible magic trail"**.

---

## WHAT WAS BUILT

Two approved effects for Event 1 Beat 2:

1. **Tessa exit-right** — sparkle trail starting under Tessa's feet `(x=0.52, y=0.968)`, traveling along the ground and exiting bottom-right off screen.
   - Script: `/tmp/tessa_exit_right_v3.py`
   - Compositing mode: video-based (adds trail onto existing Tessa video)

2. **Runestone arrival** — sparkle trail entering from left edge, terminating ON the orange Body Stone.
   - Built using `MagicCompositor` class in `Production/tools/magic_compositor.py`
   - Style: `wide_ori`
   - Endpoint pixel-verified at `(0.362, 0.440)`
   - Compositing mode: still-background (uses `MagicCompositor` class)

Both effects use the approved **"sparkle river"** approach documented in `magic_compositor.py`.

---

## QUICK-START CHECKLIST (run before first render)

Before generating a single frame, complete all of these steps in order:

- [ ] Identify compositing mode: **video-based** (trail over an existing clip) or **still-background** (trail over a static PNG)
- [ ] Pixel-verify the **trail start point** — never guess foot x; generate a vertical-line debug image, show to Kim
- [ ] Pixel-verify the **trail end point** — use numpy color thresholding for stone/object targets; confirm off-screen direction with Kim for exits
- [ ] Confirm **ground y** using a horizontal reference-line debug image at 0.01 increments in the foot zone — Kim picks the line that matches the dirt path surface
- [ ] Set **ambient blur radius = 6px** (never start higher)
- [ ] Set **SIGMA_Y = 10px** for ground-hugging trails; `~30px` only for aerial/wide-beam
- [ ] Set **preview frame**: `t=0.65` for standalone scripts; `frame_idx=82` for `MagicCompositor`
- [ ] Use **additive blend** (`np.clip(base + trail, 0, 255)`); never `ImageChops.screen`
- [ ] Use **dot sizes** `[1, 1, 1, 2, 2, 3]`; never larger
- [ ] Use **brightness floor** `0.25 + 0.75 * tail_frac`; never pure linear

---

## APPROVED VISUAL PARAMETERS

These are the locked, tested values. Do not deviate without a specific reason.

| Parameter | Approved Value | Why |
|---|---|---|
| Dot sizes | `[1, 1, 1, 2, 2, 3]` | 1–3px crisp dots. Larger = blob, not sparkles |
| Composite method | `np.clip(base + trail, 0, 255)` (additive) | Screen blend is invisible on bright daytime forest bg |
| Ambient glow blur radius | `6px` | Tight. 22px+ spreads glow upward into brighter zones, trail appears to float |
| SIGMA_Y (scatter perp to path) | `10px` for ground trails; `~30px` for aerial/wide_ori | Wide scatter makes upper particles more visible → trail appears higher than path centerline |
| Tail brightness fade | `0.25 + 0.75 * tail_frac` | 25% minimum keeps origin visible. Pure linear makes tail origin invisible |
| N_PER_PT | `8` | Sparse sparkle look. More = density; less = hairline |
| ORI palette | `[(255,255,238), (255,252,200), (255,240,155)]` weights `[3,2,1]` | Tested warm gold/cream sparkles |
| cfg_scale (if Kling involved) | N/A — magic compositor is ffmpeg/numpy only | |

---

## THE CRITICAL DIAGNOSTIC PROCESS

### RULE #1: Never guess path coordinates. Always pixel-verify.

Guessed coordinates for the runestone were wrong by 0.08 in both x and y. The calibration process below is mandatory for any new scene.

---

### Step 1 — Find the trail END POINT (stone or object target)

Use numpy color thresholding on the background image:

```python
import numpy as np
from PIL import Image

arr = np.array(Image.open("background.png"))
H, W = arr.shape[:2]

# Example: orange Body Stone — adapt color ranges per stone color
# Orange: R>200, G>100, B<100, G<R-50
mask = (
    (arr[:,:,0] > 200) &
    (arr[:,:,1] > 100) &
    (arr[:,:,2] < 100) &
    (arr[:,:,1] < arr[:,:,0] - 50)
)
ys, xs = np.where(mask)
center_x = xs.mean() / W   # fractional coord
center_y = ys.mean() / H   # fractional coord
print(f"Stone center: ({center_x:.3f}, {center_y:.3f})")
```

Stone color ranges by domain (adjust if stone colors were revised):
- **Body Stone (orange):** `R>200, G>100, B<100, G<R-50`
- **Watching Stone (yellow):** `R>200, G>200, B<100`
- **Heart Stone (red):** `R>200, G<100, B<100`
- **Calm Stone (blue):** `R<100, G<100, B>180`
- **Courage Stone (green):** `R<120, G>160, B<120`
- **Grounding Stone (purple):** `R>130, G<80, B>130`

For off-screen exits (character exits bottom-right), confirm direction with Kim — no thresholding needed, just ask "exits bottom-right?"

---

### Step 2 — Find the CHARACTER FOOT X

1. Extract a reference frame from the video at the trail-start moment (`t≈0.10`, roughly frame 12 of 121 at 24fps)
2. Generate a debug image with vertical lines every 0.01 in x across the foot zone
3. Show to Kim: "Which vertical line is at Tessa's feet?"
4. Record the confirmed x value

```python
import imageio.v3 as iio
import numpy as np
from PIL import Image, ImageDraw

# Extract frame ~12 from video
frames = list(iio.imiter(video_path, plugin="pyav"))
frame = frames[12]
img = Image.fromarray(frame)
W, H = img.size

# Draw vertical reference lines every 0.01 in foot zone (x=0.40 to x=0.65)
draw = ImageDraw.Draw(img)
for xi in range(40, 66):
    x_px = int(xi * 0.01 * W)
    color = (255, 0, 0) if xi % 5 == 0 else (200, 200, 0)
    draw.line([(x_px, 0), (x_px, H)], fill=color, width=1)

img.save("/tmp/foot_x_debug.png")
```

---

### Step 3 — Find the GROUND Y (where feet contact the surface)

1. Generate a debug image with dense horizontal reference lines (every 0.01 in y) in the lower portion of the frame
2. Show to Kim: "Which horizontal line is at the dirt path surface under Tessa's feet?"

```python
# Draw horizontal reference lines every 0.01 in y, from y=0.85 to y=1.0
for yi in range(85, 101):
    y_px = int(yi * 0.01 * H)
    color = (255, 0, 0) if yi % 5 == 0 else (200, 200, 0)
    draw.line([(0, y_px), (W, y_px)], fill=color, width=1)

img.save("/tmp/ground_y_debug.png")
```

**Key insight:** The luminosity peak detected by numpy is NOT always the visual ground. In the Tessa frame, numpy found a brightness peak at `y=0.898` but the visually correct ground (the dirt path) was at `y=0.96`. Always show the reference image to Kim — don't trust the luminosity peak alone.

---

### Step 4 — Verify with a combined debug image

Before first render, generate a single debug overlay showing:
- The video frame at the trail-start moment
- Vertical line at the confirmed foot x
- Horizontal line at the confirmed ground y
- A dot at the trail endpoint

This is the final sanity check before committing to a render.

---

## REUSABLE SYSTEM: magic_compositor.py

For **still-background scenes** (trail over a static PNG), use the `MagicCompositor` class:

```python
from magic_compositor import MagicCompositor

mc = MagicCompositor(
    background_path="still.png",
    path_pts=[(x0, y0), (x1, y1), (x2, y2)],  # pixel-verified fractional control points
    style="tessa_ori",   # "tessa_ori" for tight ground trail; "wide_ori" for wider beam
    duration=3.5,
    fps=24,
)

# ALWAYS use frame_idx=82 for preview — NOT the default 55
# Default 55 = t=0.66, trail only 66% complete — misleading
# frame_idx=82 = t≈0.99, full trail reaching endpoint
mc.render_preview(frame_idx=82)

# When preview looks correct, render full video
mc.render_video(output_path="/tmp/magic_trail.mp4")
```

**Style reference:**
- `tessa_ori` — tight sparkle river, SIGMA_Y=10, N_PER_PT=8. For ground-hugging trails.
- `wide_ori` — wider beam, SIGMA_Y≈30. For aerial entries or wide-beam arrival effects.

---

## REUSABLE PATTERN: Video-Based Compositing

For **video-based scenes** (adding trail onto an existing clip), use the standalone script pattern from `tessa_exit_right_v3.py`. Key structure:

```python
import imageio.v3 as iio
import numpy as np
from PIL import Image

# 1. Load source video frames
frames = list(iio.imiter(source_video_path, plugin="pyav"))
fps = 24
N = len(frames)

# 2. Define path as pixel-verified fractional control points
W, H = frames[0].shape[1], frames[0].shape[0]
path_pts = [(0.52, 0.968), (0.75, 0.98), (1.05, 1.02)]  # Tessa exit example

# 3. For each frame, render trail up to t = frame_idx / N
# ... (full parametric trail rendering — see tessa_exit_right_v3.py for complete impl)

# 4. ADDITIVE COMPOSITE (not screen, not multiply)
composited = np.clip(
    np.array(frame_rgb, dtype=np.float32) + trail_layer,
    0, 255
).astype(np.uint8)

# 5. Write output via imageio
iio.imwrite(output_path, composited_frames, fps=fps, plugin="pyav", codec="h264")
```

**Preview frame for standalone scripts:** use `t=0.65` to see a fully-formed trail. Earlier = trail not fully formed; later = character may have exited frame.

---

## FAILURE MODE TABLE

Every one of these was tried and failed. Do not repeat them.

| What was tried | Why it failed | Correct approach |
|---|---|---|
| `ImageChops.screen` blend | Invisible on bright daytime forest background | Use `np.clip(base + trail, 0, 255)` additive |
| Dot sizes `[8, 10, 12, 16, 22, 32]` | Creates burning white blob, not sparkles | Use `[1, 1, 1, 2, 2, 3]` |
| Guessing endpoint coords | Runestone was wrong by 0.08 in both x and y | Always pixel-verify with numpy color thresholding |
| `SIGMA_Y = 22` | Trail floats visually above ground — upper particles more visible against bright sky zones | Use `SIGMA_Y = 10` for ground trails |
| `sy = abs(gauss(0, SIGMA_Y))` | Creates hard horizontal slice at top of trail — one-sided distribution | Use full symmetric `gauss(0, SIGMA_Y)` — particles scatter both above and below path centerline |
| Ambient blur radius = 22 | Glow spreads 44–66px upward, trail appears 6+ inches above ground surface | Use `radius = 6` |
| Pure linear tail fade `tail_frac * alpha_mult` | Trail origin invisible — trail appears to start in the middle | Use `(0.25 + 0.75 * tail_frac) * alpha_mult` |
| `render_preview(frame_idx=55)` (default) | Trail only 66% complete — misleading, looks like it won't reach endpoint | Use `frame_idx=82` |
| Preview at `t=0.18` | Trail not yet formed | Use `t=0.65` for standalone scripts |
| Trusting numpy luminosity peak for ground y | Peak at `y=0.898` but visual ground was at `y=0.96` | Show reference-line image to Kim; Kim picks the ground |

---

## PARAMETERS THAT MUST BE RE-VERIFIED FOR EACH NEW SCENE

These are NOT reusable across scenes without calibration:

1. **Trail start point (x, y)** — character foot position changes with every shot. Always re-verify.
2. **Trail end point (x, y)** — stone/object positions vary by background. Always re-verify.
3. **Ambient blur radius** — start at `6px` for ground-level trails. Increase only if the surface is dark (low background luminosity in the trail zone).
4. **SIGMA_Y** — `10px` for ground-hugging; `~30px` for aerial/wide-beam. Determined by whether the trail hugs a surface or travels through air.
5. **Preview frame timing** — `t=0.65` for standalone scripts; `frame_idx=82` for `MagicCompositor`. These are locked — not scene-dependent.

Parameters that ARE reusable without calibration:
- Dot sizes `[1, 1, 1, 2, 2, 3]`
- ORI palette and weights
- Composite method (additive)
- Brightness floor `0.25 + 0.75 * tail_frac`
- N_PER_PT = 8

---

## OPEN IMPROVEMENT (Not Yet Built)

`MagicCompositor._calibrate_brightness()` auto-adjusts gain based on background luminosity for still backgrounds. For video-based compositing, the gain is currently hardcoded.

**Future improvement:** sample background luminosity along the path centerline in the first frame of the source video, and use it to auto-calibrate gain before rendering. This would handle scenes where the ground surface is darker or lighter than the Tessa forest floor, without requiring manual gain tuning.

Log this as an enhancement — it is NOT needed for the current effect to work correctly.

---

## FILE LOCATIONS

| File | Purpose |
|---|---|
| `Production/tools/magic_compositor.py` | Main `MagicCompositor` class with `tessa_ori` and `wide_ori` styles |
| `/tmp/tessa_exit_right_v3.py` | Standalone video-based script for Tessa exit-right effect |

---

*Document produced 2026-04-23 from ~20 iteration history. Goal: first attempt works.*
