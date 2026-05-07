# Visible Magic — Production Process v1
*Locked 2026-04-26. This is the standard going forward for all trail-based visible magic in MindfulNest.*

---

## What This Produces
A traveling gold bioluminescent light trail that appears to push through the ground (or air), following a path Kim draws on the actual background image. The head of the trail is bright; it fades to a dim persistent wake behind it. Floating orb motes scatter around the trail head. The style is: **light pushing through a surface** — NOT a shell glow, NOT an explosion, NOT a blob.

This is distinct from the **shell glow** (Ori-style stationary orb on Tessa's shell, in `composite_magic_overlay.py`). The trail is the *traveling* magic; the shell glow is the *source* of that magic.

---

## The Two Magic Effects — Know Which One You Need

| Effect | When to use | Script |
|--------|-------------|--------|
| **Shell glow** | Tessa's shell is actively glowing; magic is building | `composite_magic_overlay.py` |
| **Traveling trail** | Magic leaves the shell and travels somewhere | `composite_magic_path_tessa.py` (refactored per this doc) |

These are applied **sequentially** in a clip, not simultaneously.

---

## Standard Process — Every Time

### Step 1: Get the background image
- Use the **exact background still** the trail will travel across (PNG, full resolution from `Production/Backgrounds/`)
- For Tessa clips: extract a representative still frame from the source video via `ffmpeg -vf "select=eq(n\,15)" -vframes 1`
- The image loaded into the path picker is the ground truth — the compositor uses its pixel dimensions

### Step 2: Kim draws the path in path_picker.html
```
open "Production/tools/path_picker.html"
```
1. Drag the background PNG into the drop zone
2. Click 5–11 points along where the trail should travel (left to right or origin to destination)
3. Click **Copy YAML**
4. Paste the YAML into the chat

> **Rule: Never estimate the path.** Claude must not guess coordinates. Kim draws it every time, no exceptions. Wrong paths waste render cycles.

### Step 3: Run the compositor
Use the standard trail compositor script. Parameters that are LOCKED (do not change without Kim approval):

```python
# Palette — LOCKED (Ori gold, warm cream, not orange/pink/teal)
ORI_CORE   = (255, 255, 238)   # near-white warm
ORI_BRIGHT = (255, 252, 200)   # pale cream
ORI_MID    = (255, 240, 155)   # soft pale gold
ORI_DIM    = (190, 140,  35)   # dim amber for halo only
ORI_WISP   = (255, 253, 225)   # almost white

# Trail physics — LOCKED
n_samples   = max(10, int(trail_t * 70))   # density of glow samples
weight      = 22.0 / n_samples             # keeps total brightness bounded
back_frac_dimming = 0.65                   # how much tail dims (0=no dim, 1=fully dark)
burst_ramp  = 0.5 + 0.5 * min(1.0, trail_t / 0.25)  # initial burst starts at 50%

# Orb shape — flat on ground plane
ry = max(7, int(rx * 0.42))   # ry is ~42% of rx → perspective-flattened ellipse

# Blend mode — LOCKED
# Always PIL ImageChops.screen() — never ffmpeg blend=all_mode=screen
# ffmpeg blend has colorspace issues with imageio output. Screen blend in PIL is correct.
```

**Adjustable per scene:**
- `rx` (orb radius) — scale with background width: `max(14, int(W * (0.007 + t_persp * 0.015)))`
- `DURATION` / `FPS` — match the clip length needed
- `PATH_PTS` — always from Kim's YAML

### Step 4: Audio handling
imageio always drops audio. After every Python composite, mux audio back:
```bash
ffmpeg -y \
  -i output_noaudio.mp4 \
  -i source_with_audio.mp4 \
  -map 0:v -map 1:a \
  -c:v copy -c:a aac -b:a 128k -shortest \
  output_final.mp4
```
If the trail is over a still image (no source audio), add silence:
```bash
ffmpeg -y \
  -i output_noaudio.mp4 \
  -f lavfi -i "anullsrc=r=44100:cl=mono" \
  -map 0:v -map 1:a \
  -c:v copy -c:a aac -b:a 128k -shortest \
  output_final.mp4
```
> **Note on anullsrc:** `-f lavfi -i "anullsrc=..."` must come as a proper input flag BEFORE `-map`. Do NOT mix it inline with `-vf`.

### Step 5: Normalization before any stitch
Before concatenating with other clips, normalize to the canonical spec:
```bash
ffmpeg -y -i input.mp4 \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" \
  -c:v libx264 -profile:v high -pix_fmt yuv420p -r 24 \
  -c:a aac -b:a 128k -ar 44100 -ac 1 \
  normalized.mp4
```

---

## Reusable Script Template
Save as `Production/tools/trail_compositor.py`. Always copy this and adjust `PATH_PTS`, `BG_PATH`, `OUT`, `DURATION` for the specific scene:

```python
# [copy from heartwood_trail_v3 compositor — that is the canonical reference implementation]
# Key: PATH_PTS comes from Kim's path_picker YAML every time
# Key: burst_ramp = 0.5 + 0.5 * min(1.0, trail_t / 0.25) — always include
# Key: PIL ImageChops.screen() only — no ffmpeg blend
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Pink/magenta output | ffmpeg blend colorspace issue | Switch to PIL ImageChops.screen() entirely |
| No audio in output | imageio drops audio | Always explicit ffmpeg mux step after Python render |
| Trail looks like a blob, no movement | trail_t not incrementing | Check frame loop: `trail_t = i / max(N-1, 1)` |
| Initial burst too bright | burst_ramp missing | Add `burst_ramp = 0.5 + 0.5 * min(1.0, trail_t/0.25)` |
| Trail wrong shape | Path estimated, not drawn | Kim must draw in path_picker — never estimate |
| Trail too dim overall | weight too low | Increase `weight` constant (was 22.0) |
| Trail too bright / washing out bg | weight too high | Decrease `weight` constant |

---

## Approved Style Reference
- **Approved clip:** `Production/Event_1/kling_clips/heartwood_trail_v3.mp4` — canonical reference for how the trail should look
- **Approved Tessa clip:** `Production/Event_1/kling_clips/tessa_whoah_trail_v2.mp4` — trail off-screen right from shell
- Kim's description: *"light pushing through in a trail"* — not glowing, not explosive. A focused beam of warm gold light finding its path through the surface.

