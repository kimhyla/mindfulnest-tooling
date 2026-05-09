# Visible Magic Lessons Learned v2
**Supersedes:** VISIBLE_MAGIC_LESSONS_LEARNED_v1.md
**Derived from:** Sessions 2026-04-22 and 2026-04-23 — Beat 2 production
**Approved scripts:** tessa_exit_right_v3.py, tessa_trail_stitch.py, runestone_activation.py
**Approved outputs:** beat01_tessa_exit_stitched_v1.mp4, beat_magic_path_v6.mp4, beat02_runestone_activation_v1.mp4, beat02_event1_full_sequence_v1.mp4

---

## 1. Composite Method: Additive ONLY
```python
result = np.clip(base.astype(np.float32) + trail_layer, 0, 255).astype(np.uint8)
```
Screen blend is BANNED. Invisible on bright daytime backgrounds (bg pixels 150–200/255; screen only adds +30–60). PIL.ImageChops.screen() = zero visible output. Additive is the only approach that works.

## 2. Ambient Blur Radius
- Ground-level trails: **radius = 6px** (PIL) or `AMBIENT_BLUR_YX = [6.0, 28.0]` (scipy)
- Elevated/stone trails: `AMBIENT_BLUR_YX = [8.0, 32.0]` (scipy only)
- **NEVER exceed 8px Y sigma.** At 22px, glow floats 44–66px above ground — visually hovering, not traveling.

## 3. Brightness Floor Formula
```python
brightness = (0.25 + 0.75 * tail_frac) * alpha_mult
```
Never `tail_frac * alpha_mult` (pure linear = origin invisible). 25% floor anchors the trail to the character's foot.

Particle system version:
```python
alpha = bmax * max(0.25 + 0.75 * tail_frac, fade) * twinkle
```

## 4. t_head Decoupling (CRITICAL BUG PATTERN)
```python
# WRONG: t_head = t_frac
# CORRECT:
t_head = min(1.0, t_frac / T_TRAIL_COMPLETE) if T_TRAIL_COMPLETE > 0 else 1.0
```
Always include `frame_idx=0` default param: `def make_trail(t_head, particles, W, H, gain, frame_idx=0):`

## 5. Path Pixel Verification — MANDATORY BEFORE FIRST RENDER
1. Color-threshold background still for stone endpoint (numpy)
2. Debug image with vertical lines every 0.01x → Kim picks foot x
3. Debug image with horizontal lines every 0.01y → Kim picks ground y
4. Combined overlay sanity check before production render
**Confirmed Tessa values:** foot x=0.52, ground y=0.968
**NEVER trust numpy luminosity peak as ground** — it found Tessa's shell highlight (y=0.898), not the dirt path (y=0.96)

Stone color thresholds:
- Body Stone (orange): R>200, G>100, B<100, G<R-50
- Watching Stone (yellow): R>200, G>200, B<100
- Heart Stone (red): R>200, G<100, B<100
- Calm Stone (blue): R<100, G<100, B>180
- Courage Stone (green): R<120, G>160, B<120
- Grounding Stone (purple): R>130, G<80, B>130

## 6. Gain Calibration
```python
gain = float(np.clip(0.7 + (avg_lum / 128.0) * 0.6, 0.5, 2.0))
```
Sample 10–20 points along path centerline using `0.299R + 0.587G + 0.114B`. For video base, sample middle frame.

## 7. Still vs. Animated Video Base
**Decision tree:**
- Character actively moving during trail? → Kling animated video base
- No character / scenic shot? → Still PNG base (NEVER use Kling)
- Already have approved still? → Use it, do NOT regenerate Kling (different composition risk)

**Tessa stitch pattern (hybrid):**
1. Kling 5s (character walks)
2. Extract last frame as still
3. 4s trail on held still
4. ffmpeg concat → 9s total

## 8. Particle System Parameters (Approved Defaults)
```python
PALETTE         = [(255,255,238),(255,252,200),(255,240,155)]  # warm gold/cream — DO NOT CHANGE
PALETTE_WEIGHTS = [3, 2, 1]
N_PARTICLES     = 5000
SCATTER_X_FRAC  = 0.35      # ground trails
SCATTER_Y_FRAC  = 0.40      # ground trails
DOT_SIZES       = [1,1,1,2,2,3]  # ALWAYS this list — no sizes >3
BRIGHT_RANGE    = (0.40, 1.0)
TWINKLE_RANGE   = (0.06, 0.22)
FADE_TAIL       = 0.65      # ground trails (0.70 for elevated)
SPARKLE_GAIN    = 240.0     # (260 for elevated/stone)
AMBIENT_GAIN    = 44.0      # (48 for elevated/stone)
AMBIENT_BLUR_YX = [6.0, 28.0]  # (8.0, 32.0 for elevated/stone)
SPARKLE_BLUR    = 0.9
AMBIENT_MIX     = 2.4       # (2.6 for elevated/stone)
```
Always symmetric scatter: `gauss(0, SIGMA_Y)` — NEVER `abs(gauss(0, SIGMA_Y))`.

## 9. Timing Parameters
**Travel-only scene:**
```python
T_TRAIL_COMPLETE = 0.70
T_FADEOUT_START  = 0.75
T_FADEOUT_END    = 1.00
```
**Activation scene (stone lights up):**
```python
T_TRAIL_COMPLETE  = 0.45
T_FADEOUT_START   = 0.52
T_FADEOUT_END     = 0.68
T_DISSOLVE_START  = 0.68  # starts AFTER trail gone
T_DISSOLVE_END    = 0.88
```
Dissolve must start AFTER trail is gone — overlapping = visual chaos.

## 10. Output Encoding
```python
iio.imwrite(output_path, frames_list, fps=24, plugin="pyav", codec="libx264")
# NOT output_params or ffmpeg_params — those are v2 API
```
**Even dimensions MANDATORY:**
```python
W_out = W - (W % 2); H_out = H - (H % 2)
frames = [frame[:H_out, :W_out, :3] for frame in frames]  # :3 drops alpha
```
ffmpeg concat (no re-encode): `ffmpeg -y -f concat -safe 0 -i list.txt -c copy output.mp4`

## 11. Approved Scene Configs

### Tessa Exit-Right
```python
RAW_PTS = [(0.52,0.968),(0.62,0.972),(0.74,0.982),(0.86,0.995),(0.96,1.010),(1.04,1.025)]
SIGMA_Y=10; SIGMA_X=22; N_PER_PT=8; DOT_SIZES=[1,1,1,2,2,3]
ambient_blur_radius=6; AMBIENT_MIX=2.4
t_start=0.05; t_end=0.90  # stitch script timing
```

### Heartwood Wide (still-based)
```python
PATH_PTS=[(-0.05,0.60),(0.15,0.58),(0.35,0.57),(0.55,0.58),(0.75,0.60),(1.05,0.62)]
TARGET_W,TARGET_H=1920,1000; AMBIENT_BLUR_YX=[6.0,28.0]; DURATION=5.0
T_TRAIL_COMPLETE=0.70; T_FADEOUT_START=0.75; T_FADEOUT_END=1.00
```

### Runestone Activation
```python
PATH_PTS=[(0.00,0.65),(0.08,0.58),(0.18,0.51),(0.28,0.46),(0.36,0.44)]
TARGET_W,TARGET_H=1676,938; AMBIENT_BLUR_YX=[8.0,32.0]; SPARKLE_GAIN=260; DURATION=4.5
T_TRAIL_COMPLETE=0.45; T_FADEOUT_START=0.52; T_FADEOUT_END=0.68
T_DISSOLVE_START=0.68; T_DISSOLVE_END=0.88
```

## 12. Preview Rules
- MagicCompositor class: `frame_idx=82` (NOT 55 — at 55, trail only 66% complete)
- Standalone scripts: `t=0.65`
- Always `open -a "Preview"` for images, `open -a "QuickTime Player"` for video — links don't work in Claude Code UI

## 13. What FAILED
| Failed approach | Why | Fix |
|---|---|---|
| Screen blend | Invisible on bright bg | Additive only |
| Dot sizes >3 | Blobs not sparkles | [1,1,1,2,2,3] |
| Guessing path coords | Off by 130px | Numpy threshold + debug images |
| Ambient blur 22px | Trail floats 6" above ground | radius=6px |
| abs(gauss) scatter | Hard horizontal slice at top | Full symmetric gauss |
| Pure linear tail fade | Origin invisible | 0.25 floor |
| t_head = t_frac | No room for hold/fade phases | Decoupled ratio |
| preview at frame 55 | Trail 66% complete, misleading | frame_idx=82 |
| Numpy lum peak for ground | Found shell highlight not dirt | Reference line image → Kim |
| Kling video as heartwood base | Wrong scene + sparkle pooling | Still PNG always for scenic shots |
| Regenerating approved Kling | Different composition output | Use existing approved file |
| frame_idx missing default | NameError | frame_idx=0 default param |
| Odd dimensions | libx264 encode fail | Force W-(W%2), H-(H%2) |
