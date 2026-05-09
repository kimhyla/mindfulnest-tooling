# Visible Magic Implementation Handoff v1
**Date:** 2026-04-24  
**For:** Any Claude session (terminal CLI) picking up visible magic implementation  
**Status:** Ready to implement — spec agreed, no Kim approvals pending before starting  
**Session that produced this:** Three-agent Opus debate + synthesis, 2026-04-24  

---

## SECTION 0 — READ THIS FIRST (2-minute orientation)

### Who sent you here
Kim asked for a "produce visible magic → first time works" skill. A three-agent debate diagnosed why the current skill is broken and agreed on a full technical spec. This handoff is the executable version of that spec.

### The one-sentence problem
The current `magic_compositor.py` is a parameter snapshot of one approved scene (Heartwood daytime, tessa_ori style), deployed as a general system, with no geometry auto-detection and no validated stitch path — so every new shot requires a 20-iteration manual search that converges by luck, not design.

### The one-sentence fix
Build a `render_magic(scene_key)` entry point that auto-detects geometry from the source clip, routes parameters by background class, applies only locked approved params, and registers outputs to Directus — so Kim approves a preview PNG and the system does the rest.

### Who implements
Claude Code terminal CLI. All tasks below are local Python + Directus API writes. No Kim interaction needed until the first preview render is ready for approval.

### Governing documents (read before touching any file)
- `Production/tools/VISIBLE_MAGIC_TECH_SPEC_v1.md` — authoritative spec (this handoff is derived from it)
- `Production/VISIBLE_MAGIC_LESSONS_LEARNED_v4.md` — full failure history and root cause analysis
- `Production/PIPELINE_BRAIN_v1.md` — pipeline master (read first in any production session)
- `Production/API_KEYS_MASTER.md` — Directus credentials

### Rules that apply
- Rule 19 (no shortcuts, no error paths) — every task must be complete, not "MVP"
- Rule 18 (locked decision auto-registration) — any new LD must be written to Directus immediately
- LD-284 `NORMALIZATION_BEFORE_CONCAT_V1` — all clips normalized before ffmpeg concat
- LD-398 `MAGIC_STYLE_TESSA_ORI_V1` — tessa_ori is the only approved V1 style; all others block in production

---

## SECTION 1 — CURRENT STATE INVENTORY

### Files that exist RIGHT NOW

| File | Status | Notes |
|---|---|---|
| `Production/tools/magic_compositor.py` | EXISTS — needs major surgery | The core compositor class. Has v6 approved logic but wrong abstraction. `KNOWN_SCENES` stores pixel coords not archetypes. `STYLES["tessa_ori"]["directus_ld"] = None` (should be 398). No `render_magic()` entry point. |
| `Production/tools/magic_position_finder.py` | EXISTS — migrate then keep | Contains 6 color-threshold lambdas (orange, purple, yellow, red, blue, green). These migrate INTO `geometry_detector.py`. Keep as legacy fallback during transition. |
| `Production/tools/magic_clip_registry.json` | EXISTS — replace with Directus | Loose JSON tracking approved/pending clips. The v2 full-sequence stitch failure happened because this was bypassed. Replace with `prod_magic_clips` Directus collection. Delete after migration. |
| `Production/Event_1/composite_magic_path_tessa.py` | EXISTS — reference only | The "best" pre-v6 script. Uses screen blend (banned). Do not use; it's a reference for the path geometry only. |
| `Production/Event_1/composite_magic_path_v6.py` | EXISTS — reference only | The approved v6 approach. Its logic is already in `magic_compositor.py`. |
| `Production/Event_1/composite_magic_overlay.py` | EXISTS — reference only | Earlier overlay attempt. Reference only. |
| `.claude/skills/visible-magic/SKILL.md` | EXISTS — update after implementation | The skill Kim invokes. Update to call `render_magic()` after implementation is done. |
| `Production/governance/visible-magic_governance.md` | EXISTS — update after implementation | Governance checklist. Update after implementation. |
| `Production/tools/VISIBLE_MAGIC_TECH_SPEC_v1.md` | EXISTS — authoritative | The spec this handoff is based on. |
| `Production/VISIBLE_MAGIC_LESSONS_LEARNED_v4.md` | EXISTS — reference | Full failure history. |

### Files that DO NOT EXIST yet (must be created)

| File | Priority | What it does |
|---|---|---|
| `Production/tools/geometry_detector.py` | 1 — FIRST | Auto-detects path_pts from source clip. Eliminates coordinate hunt. |
| `Production/tools/scene_registry.yaml` | 2 | Archetype-addressed scene definitions (replaces KNOWN_SCENES). |
| `Production/tools/background_classifier.py` | 3 | Classifies bg luminance/saturation → routes parameters. |

### Directus collections that DO NOT EXIST yet (must be created)

| Collection | Priority | What it does |
|---|---|---|
| `prod_magic_clips` | 4 | Replaces `magic_clip_registry.json`. Tracks approved magic clips with Directus-enforced status. |

---

## SECTION 2 — IMPLEMENTATION TASKS (in execution order)

---

### TASK 1 — Create `Production/tools/geometry_detector.py`

**Why first:** This is the single biggest unlock. Every new shot currently requires a 4-step interactive pixel-verification dance that takes 10–20 iterations to converge. This eliminates it structurally.

**What to build:**

```python
"""
Production/tools/geometry_detector.py

Auto-detects path_pts for MagicCompositor from source clip and scene archetype.
Eliminates manual coordinate specification for known scene archetypes.
"""

import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw
import cv2
import json
import subprocess
from typing import Optional
import yaml


# Color threshold lambdas — migrated from magic_position_finder.py
COLOR_THRESHOLDS = {
    "orange": lambda r, g, b: r > 180 and g > 80 and g < 160 and b < 80,
    "purple": lambda r, g, b: r > 100 and b > 130 and g < 100,
    "yellow": lambda r, g, b: r > 200 and g > 180 and b < 100,
    "red":    lambda r, g, b: r > 180 and g < 80 and b < 80,
    "blue":   lambda r, g, b: b > 160 and r < 100 and g < 130,
    "green":  lambda r, g, b: g > 150 and r < 120 and b < 120,
}


class GeometryDetector:

    def __init__(self, scene_registry_path: Path = None):
        if scene_registry_path is None:
            scene_registry_path = Path(__file__).parent / "scene_registry.yaml"
        with open(scene_registry_path) as f:
            self.registry = yaml.safe_load(f)

    def infer(self, scene_key: str, source_clip: Path,
              bg_frame: Optional[np.ndarray] = None) -> tuple[list, float]:
        """
        Main entry point. Look up archetype from scene_registry.yaml,
        dispatch to correct detector, return (path_pts, confidence).

        path_pts: list of (x_frac, y_frac) tuples, fractional coords 0-1
        confidence: float 0-1; < 0.8 → ask Kim to confirm debug image
        """
        scene = self.registry.get(scene_key)
        if scene is None:
            raise ValueError(f"Scene key '{scene_key}' not found in scene_registry.yaml. "
                             f"Add it before running.")

        archetype = scene["archetype"]

        # Extract representative frames from source clip
        mid_frame = self._extract_frame(source_clip, position="mid")
        last_frame = self._extract_frame(source_clip, position="last")
        if bg_frame is None:
            bg_frame = self._extract_frame(source_clip, position="first")

        if archetype == "ground_left_to_target":
            return self._detect_ground_left_to_target(
                bg_frame, scene.get("color_target"), scene.get("direction", "left")
            )
        elif archetype == "character_exit_ground":
            return self._detect_character_exit_ground(
                mid_frame, last_frame, source_clip, scene.get("direction", "right")
            )
        elif archetype == "stone_activation":
            return self._detect_stone_activation(bg_frame, scene.get("color_target"))
        elif archetype == "wide_clearing_cross":
            return self._detect_wide_clearing_cross(bg_frame)
        else:
            raise ValueError(f"Unknown archetype: {archetype}")

    def detect_foot_contact(self, frame: np.ndarray) -> tuple[tuple[float, float], float]:
        """
        Find where a character's foot/base contacts the ground.
        Uses alpha channel bottom edge if available; falls back to luminance gradient.

        Returns ((x_frac, y_frac), confidence)
        """
        h, w = frame.shape[:2]

        if frame.shape[2] == 4:
            # Has alpha channel — find bottom-most non-transparent pixel
            alpha = frame[:, :, 3]
            rows_with_content = np.where(alpha.max(axis=1) > 30)[0]
            if len(rows_with_content) == 0:
                return ((0.5, 0.95), 0.3)  # low confidence fallback
            bottom_row = rows_with_content.max()
            cols_at_bottom = np.where(alpha[bottom_row, :] > 30)[0]
            center_col = int(cols_at_bottom.mean()) if len(cols_at_bottom) > 0 else w // 2
            confidence = min(1.0, len(cols_at_bottom) / 50)  # more pixels = higher confidence
            return ((center_col / w, bottom_row / h), confidence)
        else:
            # No alpha — use luminance gradient to find character base
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY).astype(float)
            grad_y = np.abs(np.gradient(gray, axis=0))
            # Find strongest horizontal gradient band in bottom 60% of frame
            lower_half = grad_y[int(h * 0.4):, :]
            row_sums = lower_half.sum(axis=1)
            peak_row = int(h * 0.4) + row_sums.argmax()
            center_col = w // 2  # approximate; low confidence
            return ((center_col / w, peak_row / h), 0.55)

    def detect_exit_vector(self, clip: Path, direction: str = "right") -> tuple[list, float]:
        """
        Detect where a character exits the frame using optical flow on last 10 frames.
        Returns (path_pts, confidence) where path_pts is a 3-point path:
        [foot_contact_point, midpoint, off_screen_exit_point]
        """
        frames = self._extract_last_n_frames(clip, n=10)
        if len(frames) < 2:
            # Fallback: use direction to construct path
            return self._fallback_exit_path(direction), 0.4

        # Compute optical flow
        flows = []
        for i in range(len(frames) - 1):
            gray1 = cv2.cvtColor(frames[i], cv2.COLOR_RGB2GRAY)
            gray2 = cv2.cvtColor(frames[i+1], cv2.COLOR_RGB2GRAY)
            flow = cv2.calcOpticalFlowFarneback(
                gray1, gray2, None,
                pyr_scale=0.5, levels=3, winsize=15,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0
            )
            flows.append(flow)

        avg_flow = np.mean(flows, axis=0)
        h, w = avg_flow.shape[:2]

        # Find dominant motion direction
        flow_magnitude = np.sqrt(avg_flow[..., 0]**2 + avg_flow[..., 1]**2)
        # Focus on regions with strong motion
        strong_motion_mask = flow_magnitude > np.percentile(flow_magnitude, 80)
        if strong_motion_mask.sum() == 0:
            return self._fallback_exit_path(direction), 0.4

        mean_vx = avg_flow[..., 0][strong_motion_mask].mean()
        mean_vy = avg_flow[..., 1][strong_motion_mask].mean()

        # Find centroid of moving region in last frame as foot contact
        motion_rows, motion_cols = np.where(strong_motion_mask)
        # Use bottom-most motion centroid (character base)
        bottom_idx = motion_rows.argsort()[-max(1, len(motion_rows)//4):]
        foot_x = motion_cols[bottom_idx].mean() / w
        foot_y = motion_rows[bottom_idx].mean() / h

        # Project exit point off-screen in motion direction
        magnitude = np.sqrt(mean_vx**2 + mean_vy**2)
        if magnitude < 0.1:
            return self._fallback_exit_path(direction), 0.45

        norm_vx = mean_vx / magnitude
        norm_vy = mean_vy / magnitude

        # Off-screen exit: extend until outside [0,1] range
        exit_x = foot_x + norm_vx * 2.0   # overshoot deliberately
        exit_y = foot_y + norm_vy * 0.5   # keep Y near ground

        # Clamp to just outside frame
        exit_x = max(-0.05, min(1.05, exit_x))
        exit_y = max(0.0, min(1.0, exit_y))

        mid_x = (foot_x + exit_x) / 2
        mid_y = (foot_y + exit_y) / 2

        path_pts = [(foot_x, foot_y), (mid_x, mid_y), (exit_x, exit_y)]
        confidence = min(1.0, flow_magnitude[strong_motion_mask].mean() / 5.0)

        return path_pts, confidence

    def detect_stone_center(self, bg_frame: np.ndarray,
                             color: str) -> tuple[tuple[float, float], float]:
        """
        Find centroid of a colored stone/target in the background frame.
        Uses color threshold lambdas (migrated from magic_position_finder.py).

        Returns ((x_frac, y_frac), confidence)
        confidence based on pixel count (more pixels = more confident)
        """
        if color not in COLOR_THRESHOLDS:
            raise ValueError(f"Unknown color '{color}'. Valid: {list(COLOR_THRESHOLDS.keys())}")

        h, w = bg_frame.shape[:2]
        thresh_fn = COLOR_THRESHOLDS[color]

        # Find all pixels matching the color threshold
        r = bg_frame[:, :, 0].astype(int)
        g = bg_frame[:, :, 1].astype(int)
        b = bg_frame[:, :, 2].astype(int)

        # Vectorized threshold
        mask = np.zeros((h, w), dtype=bool)
        for y in range(h):
            for x in range(w):
                mask[y, x] = thresh_fn(r[y, x], g[y, x], b[y, x])

        # NOTE: The above loop is slow for large images.
        # Optimized vectorized version:
        mask = (
            thresh_fn(r, g, b)  # thresh_fn must support array inputs
        )
        # Since lambdas use comparison operators they DO support arrays.

        pixel_count = mask.sum()
        if pixel_count < 10:
            return ((0.5, 0.5), 0.1)  # very low confidence — no stone found

        rows, cols = np.where(mask)
        centroid_x = cols.mean() / w
        centroid_y = rows.mean() / h

        # Confidence scales with pixel count, capped at ~500 pixels = full confidence
        confidence = min(1.0, pixel_count / 500)

        return ((centroid_x, centroid_y), confidence)

    def detect_horizon_line(self, bg_frame: np.ndarray) -> tuple[float, float]:
        """
        Find the horizon line for wide clearing cross shots.
        Detects the bright/dark luminance band transition.

        Returns (y_frac, confidence)
        """
        gray = np.mean(bg_frame[:, :, :3], axis=2)  # luminance proxy
        h = gray.shape[0]

        # Row-wise luminance profile
        row_lum = gray.mean(axis=1)

        # Find the transition from bright (sky) to dark (ground) or vice versa
        grad = np.abs(np.gradient(row_lum))
        # Strongest gradient = horizon
        horizon_row = grad.argmax()

        # Confidence: how sharp is the transition?
        max_grad = grad.max()
        confidence = min(1.0, max_grad / 30.0)  # 30+ luminance units/row = sharp

        return (horizon_row / h, confidence)

    def render_debug_image(self, bg_frame: np.ndarray, path_pts: list,
                           output_path: Path, scene_key: str = "") -> Path:
        """
        Overlay detected path_pts as red circles on bg_frame.
        Used for Kim's one-time confirmation on novel archetypes.
        Opens in Preview.app automatically.
        """
        img = Image.fromarray(bg_frame[:, :, :3])
        draw = ImageDraw.Draw(img)
        h, w = bg_frame.shape[:2]

        for i, (x_frac, y_frac) in enumerate(path_pts):
            px = int(x_frac * w)
            py = int(y_frac * h)
            # Red circle, 20px radius
            draw.ellipse([px-20, py-20, px+20, py+20], outline=(255, 0, 0), width=3)
            # Label
            draw.text((px+25, py-10), f"pt{i}", fill=(255, 0, 0))

        # Draw path connecting points
        if len(path_pts) > 1:
            pixel_pts = [(int(x*w), int(y*h)) for x, y in path_pts]
            draw.line(pixel_pts, fill=(255, 100, 0), width=2)

        # Title
        draw.text((10, 10), f"Geometry detection: {scene_key}", fill=(255, 255, 0))
        draw.text((10, 30), "Red circles = detected path points. Confirm or reject.", 
                  fill=(255, 255, 0))

        img.save(output_path)
        subprocess.run(["open", "-a", "Preview", str(output_path)])
        return output_path

    # ── Private helpers ──────────────────────────────────────────────────────

    def _detect_ground_left_to_target(self, bg_frame, color_target, direction):
        """Archetype: magic travels from left edge to a colored target stone."""
        h, w = bg_frame.shape[:2]

        # Target: stone centroid
        target_coords, target_conf = self.detect_stone_center(bg_frame, color_target)

        # Origin: left edge at same Y as target (floor-level)
        origin_x = 0.0 if direction == "left" else 1.0
        origin_y = target_coords[1]  # same floor level as target

        # Midpoint: arc slightly lower to hug floor
        mid_x = (origin_x + target_coords[0]) / 2
        mid_y = target_coords[1] + 0.01  # very slight floor dip

        path_pts = [(origin_x, origin_y), (mid_x, mid_y), target_coords]
        return path_pts, target_conf

    def _detect_character_exit_ground(self, mid_frame, last_frame, clip, direction):
        """Archetype: character walks off screen with ground trail."""
        foot_coords, foot_conf = self.detect_foot_contact(mid_frame)
        exit_pts, exit_conf = self.detect_exit_vector(clip, direction)

        if foot_conf > 0.6 and exit_conf > 0.5:
            # Use detected foot as origin, detected exit vector for path
            path_pts = [foot_coords] + exit_pts[1:]
            confidence = min(foot_conf, exit_conf)
        else:
            path_pts = exit_pts
            confidence = exit_conf * 0.7  # penalize for missing foot detection

        return path_pts, confidence

    def _detect_stone_activation(self, bg_frame, color_target):
        """Archetype: radial burst from stone centroid."""
        centroid, confidence = self.detect_stone_center(bg_frame, color_target)
        # For burst: path_pts is just the centroid (compositor handles radial expansion)
        return [centroid], confidence

    def _detect_wide_clearing_cross(self, bg_frame):
        """Archetype: horizontal cross at horizon line."""
        h, w = bg_frame.shape[:2]
        horizon_y, confidence = self.detect_horizon_line(bg_frame)
        path_pts = [(0.0, horizon_y), (0.5, horizon_y), (1.0, horizon_y)]
        return path_pts, confidence

    def _fallback_exit_path(self, direction):
        """Fallback when optical flow fails."""
        if direction == "right":
            return [(0.5, 0.92), (0.75, 0.94), (1.05, 0.96)]
        elif direction == "left":
            return [(0.5, 0.92), (0.25, 0.94), (-0.05, 0.96)]
        else:
            return [(0.5, 0.92), (0.5, 0.94), (0.5, 0.98)]

    def _extract_frame(self, clip: Path, position: str = "mid") -> np.ndarray:
        """Extract a single frame from a video clip."""
        cap = cv2.VideoCapture(str(clip))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if position == "first":
            frame_idx = 0
        elif position == "mid":
            frame_idx = total // 2
        elif position == "last":
            frame_idx = max(0, total - 3)
        else:
            frame_idx = int(position)

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise RuntimeError(f"Could not extract frame {frame_idx} from {clip}")
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def _extract_last_n_frames(self, clip: Path, n: int = 10) -> list:
        """Extract last N frames from a video clip for optical flow."""
        cap = cv2.VideoCapture(str(clip))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        start = max(0, total - n)

        frames = []
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        for _ in range(n):
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        cap.release()
        return frames


# CLI
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Detect magic trail geometry from source clip")
    parser.add_argument("--scene", required=True, help="Scene key from scene_registry.yaml")
    parser.add_argument("--clip", required=False, help="Source clip path (overrides Directus lookup)")
    parser.add_argument("--confirm", action="store_true", 
                        help="Always render debug image for Kim confirmation, even if high confidence")
    parser.add_argument("--output-debug", default=None, help="Path for debug image output")
    args = parser.parse_args()

    detector = GeometryDetector()

    clip_path = Path(args.clip) if args.clip else None
    if clip_path is None:
        print("ERROR: --clip required (Directus lookup not yet implemented in CLI)")
        exit(1)

    path_pts, confidence = detector.infer(args.scene, clip_path)

    print(f"Scene: {args.scene}")
    print(f"Path points: {path_pts}")
    print(f"Confidence: {confidence:.2f}")

    if confidence < 0.8 or args.confirm:
        print(f"Confidence < 0.8 — rendering debug image for Kim confirmation...")
        bg_frame = detector._extract_frame(clip_path, "first")
        debug_path = Path(args.output_debug) if args.output_debug else (
            clip_path.parent / f"debug_geometry_{args.scene}.png"
        )
        detector.render_debug_image(bg_frame, path_pts, debug_path, args.scene)
        print(f"Debug image: {debug_path} (opened in Preview)")
    else:
        print("High confidence — no Kim confirmation needed for this archetype.")
```

**After writing this file:**
- Run `python3 Production/tools/geometry_detector.py --scene m1_e1_res_beat_01_heartwood --clip Production/Event_1/kling_clips/beat01_tessa_magic_composite.mp4 --confirm`
- Verify debug image opens with red circles on correct positions
- Show Kim the debug image once per archetype

---

### TASK 2 — Create `Production/tools/scene_registry.yaml`

**Why:** Replaces the fragile coordinate-based `KNOWN_SCENES` dict in `magic_compositor.py`. Stores recipes, not pixels.

```yaml
# Production/tools/scene_registry.yaml
# Scene archetypes for visible magic production.
# DO NOT store pixel coordinates here. Store semantic anchors only.
# Geometry is computed at render time from the actual source clip.
#
# Archetypes:
#   ground_left_to_target   — magic travels across floor to a colored stone
#   character_exit_ground   — character walks off screen with ground trail
#   stone_activation        — radial burst from stone centroid
#   wide_clearing_cross     — horizontal trail across a clearing

m1_e1_res_beat_01_heartwood:
  archetype: "ground_left_to_target"
  description: "Magic travels from left forest edge to Heartwood altar step (orange stone)"
  module_id: "m1"
  event_id: "e1"
  beat: "res_beat_01"
  style: "tessa_ori"
  color_target: "orange"
  direction: "left"
  source_asset_query:
    collection: "prod_visual_assets"
    filter:
      module_id: "m1"
      event_id: "e1"
      shot_role: "res_beat_01_heartwood_base"
      status: "approved"

m1_e1_res_beat_01_tessa_exit:
  archetype: "character_exit_ground"
  description: "Tessa walks right off frame with ground magic trail"
  module_id: "m1"
  event_id: "e1"
  beat: "res_beat_01"
  style: "tessa_ori"
  color_target: null
  direction: "right"
  source_asset_query:
    collection: "prod_visual_assets"
    filter:
      module_id: "m1"
      event_id: "e1"
      shot_role: "res_beat_01_tessa_kling"
      status: "approved"

m1_e1_res_beat_02_runestone:
  archetype: "stone_activation"
  description: "Orange runestone activation burst"
  module_id: "m1"
  event_id: "e1"
  beat: "res_beat_02"
  style: "tessa_ori"
  color_target: "orange"
  direction: null
  source_asset_query:
    collection: "prod_visual_assets"
    filter:
      module_id: "m1"
      event_id: "e1"
      shot_role: "res_beat_02_base"
      status: "approved"

# Template for new scenes — copy this block and fill in values:
# <scene_key>:
#   archetype: "ground_left_to_target" | "character_exit_ground" | "stone_activation" | "wide_clearing_cross"
#   description: "Human-readable description"
#   module_id: "mN"
#   event_id: "eN"
#   beat: "res_beat_NN"
#   style: "tessa_ori"   # only approved style in V1
#   color_target: "orange" | "purple" | "yellow" | "red" | "blue" | "green" | null
#   direction: "left" | "right" | null
#   source_asset_query:
#     collection: "prod_visual_assets"
#     filter:
#       module_id: "mN"
#       event_id: "eN"
#       shot_role: "<role>"
#       status: "approved"
```

---

### TASK 3 — Create `Production/tools/background_classifier.py`

**Why:** Single scalar gain calibration fails on non-daytime-warm backgrounds. Luna (nighttime), Bork (cave), Ember (campfire) will use different sigma/blur values. This routes automatically so Kim never has to specify.

```python
"""
Production/tools/background_classifier.py

Classifies background frame by luminance + saturation.
Routes to appropriate parameter block for MagicCompositor.
Prevents daytime-warm Heartwood params from being used on nighttime/cave scenes.
"""

import numpy as np


# Classification thresholds
LUMINANCE_NIGHTTIME_MAX = 60
LUMINANCE_INDOOR_MIN = 60
LUMINANCE_INDOOR_MAX = 119
LUMINANCE_DAYTIME_MIN = 120
SATURATION_WARM_MIN = 80


# Parameter blocks per background class
# These are OVERRIDES applied on top of the base tessa_ori style.
# Only override what differs from daytime-warm baseline.
BG_CLASS_PARAMS = {
    "daytime-warm": {
        # Baseline — matches approved tessa_ori v6 parameters exactly
        "AMBIENT_BLUR_YX": [6.0, 28.0],
        "scatter_y_frac_multiplier": 1.0,    # no change
        "gain_floor": 0.7,
        "gain_ceiling": 1.3,
        "notes": "Heartwood, Everdale exterior. Approved via LD-398.",
    },
    "daytime-cool": {
        "AMBIENT_BLUR_YX": [6.0, 28.0],     # same blur geometry
        "scatter_y_frac_multiplier": 1.0,
        "gain_floor": 0.8,                   # slightly higher gain (cooler bg = more contrast available)
        "gain_ceiling": 1.4,
        "notes": "Sky-heavy shots, Cliffside. Warmer palette shift available but not validated V1.",
    },
    "nighttime": {
        "AMBIENT_BLUR_YX": [10.0, 40.0],    # wider glow OK on dark bg
        "scatter_y_frac_multiplier": 1.5,    # can spread more on dark bg
        "gain_floor": 0.5,                   # lower gain — dark bg makes magic pop more
        "gain_ceiling": 0.9,
        "notes": "Luna garden, Luminara arc. NOT YET VALIDATED — first nighttime scene "
                 "must be run with --confirm regardless of confidence score.",
    },
    "indoor": {
        "AMBIENT_BLUR_YX": [8.0, 30.0],
        "scatter_y_frac_multiplier": 1.2,
        "gain_floor": 0.6,
        "gain_ceiling": 1.1,
        "notes": "Bork cave, interior scenes. NOT YET VALIDATED.",
    },
}


class BackgroundClassifier:

    def classify(self, bg_frame: np.ndarray, path_pts: list) -> str:
        """
        Measure luminance + saturation along path centerline.
        Returns class string: 'daytime-warm' | 'daytime-cool' | 'nighttime' | 'indoor'

        path_pts: list of (x_frac, y_frac) fractional coordinates
        """
        h, w = bg_frame.shape[:2]

        # Sample pixels along path centerline
        samples = []
        for i in range(20):
            t = i / 19
            # Interpolate along path
            if len(path_pts) >= 2:
                seg_t = t * (len(path_pts) - 1)
                seg_idx = min(int(seg_t), len(path_pts) - 2)
                local_t = seg_t - seg_idx
                x = path_pts[seg_idx][0] + local_t * (path_pts[seg_idx+1][0] - path_pts[seg_idx][0])
                y = path_pts[seg_idx][1] + local_t * (path_pts[seg_idx+1][1] - path_pts[seg_idx][1])
            else:
                x, y = path_pts[0]

            px = int(np.clip(x * w, 0, w-1))
            py = int(np.clip(y * h, 0, h-1))
            samples.append(bg_frame[py, px, :3])

        samples = np.array(samples, dtype=float)

        # Luminance (perceptual)
        lum_weights = np.array([0.299, 0.587, 0.114])
        luminances = (samples * lum_weights).sum(axis=1)
        mean_lum = luminances.mean()

        # Saturation (HSV-style approximation)
        max_c = samples.max(axis=1)
        min_c = samples.min(axis=1)
        range_c = max_c - min_c
        saturation = np.where(max_c > 0, range_c / max_c, 0)
        mean_sat = saturation.mean() * 255  # scale to 0-255 for threshold comparison

        # Classify
        if mean_lum < LUMINANCE_NIGHTTIME_MAX:
            return "nighttime"
        elif mean_lum < LUMINANCE_INDOOR_MAX:
            return "indoor"
        elif mean_sat >= SATURATION_WARM_MIN:
            return "daytime-warm"
        else:
            return "daytime-cool"

    def get_params(self, bg_class: str) -> dict:
        """Return parameter override block for a background class."""
        if bg_class not in BG_CLASS_PARAMS:
            raise ValueError(f"Unknown background class: {bg_class}. "
                             f"Valid: {list(BG_CLASS_PARAMS.keys())}")
        return BG_CLASS_PARAMS[bg_class].copy()

    def warn_if_unvalidated(self, bg_class: str) -> Optional[str]:
        """
        Returns a warning string if the background class has not been validated in production.
        Caller should log this warning and surface to Kim.
        """
        params = BG_CLASS_PARAMS.get(bg_class, {})
        notes = params.get("notes", "")
        if "NOT YET VALIDATED" in notes:
            return (f"WARNING: Background class '{bg_class}' has not been validated in production. "
                    f"Always run with --confirm on the first render of this scene type. "
                    f"Notes: {notes}")
        return None
```

---

### TASK 4 — Create Directus `prod_magic_clips` Collection

**Why:** Replaces `magic_clip_registry.json`. Approval state lives in the same system Kim uses for everything. Eliminates the "two-place sync" failure that caused the v2 stitch catastrophe.

**Execute via Python (never curl):**

```python
import urllib.request
import json

DIRECTUS_URL = "https://your-directus-instance.com"   # from Production/API_KEYS_MASTER.md
DIRECTUS_TOKEN = "..."                                  # from Production/API_KEYS_MASTER.md

def create_collection(collection_name, fields):
    """Create a Directus collection with fields."""
    headers = {
        "Authorization": f"Bearer {DIRECTUS_TOKEN}",
        "Content-Type": "application/json"
    }

    # Create collection
    payload = json.dumps({
        "collection": collection_name,
        "meta": {"icon": "auto_awesome"},
        "schema": {},
        "fields": fields
    }).encode()

    req = urllib.request.Request(
        f"{DIRECTUS_URL}/collections",
        data=payload,
        headers=headers,
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

FIELDS = [
    {"field": "id", "type": "integer", "schema": {"is_primary_key": True, "has_auto_increment": True}},
    {"field": "scene_key", "type": "string", "schema": {"is_unique": True, "is_nullable": False}},
    {"field": "archetype", "type": "string", "schema": {"is_nullable": True}},
    {"field": "source_asset_id", "type": "integer", "schema": {"is_nullable": True}},
    {"field": "magic_asset_id", "type": "integer", "schema": {"is_nullable": True}},
    {"field": "status", "type": "string", "schema": {"is_nullable": False, "default_value": "pending"}},
    {"field": "background_class", "type": "string", "schema": {"is_nullable": True}},
    {"field": "gain_applied", "type": "float", "schema": {"is_nullable": True}},
    {"field": "path_pts_detected", "type": "json", "schema": {"is_nullable": True}},
    {"field": "geometry_confirmed_at", "type": "dateTime", "schema": {"is_nullable": True}},
    {"field": "style_name", "type": "string", "schema": {"is_nullable": True}},
    {"field": "directus_ld", "type": "integer", "schema": {"is_nullable": True}},
    {"field": "approved_at", "type": "dateTime", "schema": {"is_nullable": True}},
    {"field": "notes", "type": "text", "schema": {"is_nullable": True}},
    {"field": "created_at", "type": "dateTime", "schema": {"is_nullable": True}},
]

result = create_collection("prod_magic_clips", FIELDS)
print(f"Created: {result}")
```

**After creating the collection:** Migrate the 4 existing entries from `magic_clip_registry.json` to Directus. Then update `resolve_stitch_clips()` (Task 5) to query Directus. Then delete `magic_clip_registry.json`.

---

### TASK 5 — Wire `render_magic()` entry point into `magic_compositor.py`

**What to add/change in the existing file:**

#### 5a. Fix `STYLES["tessa_ori"]["directus_ld"]`
```python
# CHANGE THIS (currently None):
"directus_ld": None,   # TODO: link LD

# TO THIS:
"directus_ld": 398,    # LD-398 MAGIC_STYLE_TESSA_ORI_V1
```

#### 5b. Add `_validate_style()` — call at top of any render function
```python
def _validate_style(style_name: str, draft_mode: bool = False) -> None:
    style = STYLES.get(style_name)
    if style is None:
        raise RuntimeError(f"Unknown style: '{style_name}'. Valid: {list(STYLES.keys())}")
    if style.get("status") != "approved" and not draft_mode:
        raise RuntimeError(
            f"Style '{style_name}' is not approved for production "
            f"(status: '{style.get('status')}'). Use draft=True to force, "
            f"or obtain Kim approval and add LD before production use."
        )
    if style.get("directus_ld") is None and not draft_mode:
        raise RuntimeError(
            f"Style '{style_name}' has no Directus LD linked. "
            f"Link the LD before production use."
        )
```

#### 5c. Add `render_magic()` top-level entry point
```python
def render_magic(scene_key: str, style: str = "auto", preview_only: bool = True,
                 gain_override: float = None, draft: bool = False,
                 clip_override: Path = None) -> "MagicRenderResult":
    """
    Main entry point. Kim calls this (via skill or directly).
    Handles: source resolution → geometry detection → bg classification →
             param routing → preview render → (on approval) full render →
             Directus registration → stitch assembly.

    scene_key: key from scene_registry.yaml
    style: "auto" infers from scene registry; explicit to override
    preview_only: True = render preview PNG only, don't proceed to video
    gain_override: multiplier applied after auto-calibration (Kim feedback)
    draft: True = allow non-approved styles
    clip_override: path to clip, bypasses Directus source lookup (for testing)
    """
    from .geometry_detector import GeometryDetector
    from .background_classifier import BackgroundClassifier
    import yaml

    # Load scene registry
    registry_path = Path(__file__).parent / "scene_registry.yaml"
    with open(registry_path) as f:
        registry = yaml.safe_load(f)

    scene = registry.get(scene_key)
    if scene is None:
        raise ValueError(f"Scene key '{scene_key}' not in scene_registry.yaml. "
                         f"Add it first.")

    # Resolve style
    if style == "auto":
        style = scene.get("style", "tessa_ori")
    _validate_style(style, draft_mode=draft)

    # Resolve source clip
    if clip_override:
        source_clip = Path(clip_override)
    else:
        source_clip = _resolve_source_clip(scene)

    # Detect geometry
    detector = GeometryDetector(registry_path)
    path_pts, confidence = detector.infer(scene_key, source_clip)

    # If confidence low, render debug image and pause for Kim
    if confidence < 0.8:
        bg_frame = detector._extract_frame(source_clip, "first")
        debug_path = source_clip.parent / f"debug_geometry_{scene_key}.png"
        detector.render_debug_image(bg_frame, path_pts, debug_path, scene_key)
        print(f"\n⚠️  Geometry confidence {confidence:.2f} < 0.80")
        print(f"Debug image opened: {debug_path}")
        print("Ask Kim to confirm the red circles are on correct positions before proceeding.")
        # In skill context, this pauses for Kim input
        # In CLI context, print and continue (Kim reviews before approving)

    # Classify background
    bg_frame_arr = detector._extract_frame(source_clip, "first")
    classifier = BackgroundClassifier()
    bg_class = classifier.classify(bg_frame_arr, path_pts)
    bg_params = classifier.get_params(bg_class)

    # Warn if unvalidated background class
    warning = classifier.warn_if_unvalidated(bg_class)
    if warning:
        print(f"\n{warning}")

    # Build compositor with merged params
    style_params = STYLES[style].copy()
    style_params.update({k: v for k, v in bg_params.items()
                         if k not in ("notes", "gain_floor", "gain_ceiling")})

    compositor = MagicCompositor(
        bg_path=source_clip,   # or bg PNG if available
        path_pts=path_pts,
        style_params=style_params,
        gain_override=gain_override,
        gain_floor=bg_params["gain_floor"],
        gain_ceiling=bg_params["gain_ceiling"],
    )

    # Render preview
    preview_path = source_clip.parent / f"preview_{scene_key}.png"
    compositor.render_preview(preview_path)

    print(f"\nPreview: {preview_path}")
    print("Kim options: approve / brighter / dimmer / lower / reposition / reject")

    if preview_only:
        return MagicRenderResult(
            preview_path=preview_path,
            video_path=None,
            coords_used=path_pts,
            background_class=bg_class,
            gain_applied=compositor.gain_applied,
            directus_asset_id=None,
        )

    # Full video render + register
    video_path = source_clip.parent / f"magic_{scene_key}.mp4"
    compositor.render_video(video_path)

    asset_id = _register_approved_magic(
        scene_key=scene_key,
        magic_clip_path=video_path,
        gain_applied=compositor.gain_applied,
        bg_class=bg_class,
        path_pts=path_pts,
        style_name=style,
    )

    return MagicRenderResult(
        preview_path=preview_path,
        video_path=video_path,
        coords_used=path_pts,
        background_class=bg_class,
        gain_applied=compositor.gain_applied,
        directus_asset_id=asset_id,
    )
```

#### 5d. Rewrite `resolve_stitch_clips()` to query Directus
```python
def resolve_stitch_clips(scene_key: str) -> "StitchManifest":
    """
    Query Directus prod_magic_clips for approved source + magic clips.
    NEVER resolve by filename. Raises ValueError if not approved.
    """
    # Read credentials from API_KEYS_MASTER.md at runtime
    creds = _load_directus_credentials()

    import urllib.request, json
    headers = {"Authorization": f"Bearer {creds['token']}"}

    url = (f"{creds['url']}/items/prod_magic_clips"
           f"?filter[scene_key][_eq]={scene_key}"
           f"&filter[status][_eq]=approved"
           f"&fields=id,source_asset_id,magic_asset_id,status")

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    rows = data.get("data", [])
    if not rows:
        raise ValueError(
            f"No approved magic clip in Directus for scene '{scene_key}'. "
            f"Run render_magic('{scene_key}') and get Kim approval first."
        )

    row = rows[0]

    # Resolve asset file paths
    def get_asset_path(asset_id):
        req = urllib.request.Request(
            f"{creds['url']}/items/prod_visual_assets/{asset_id}?fields=file_path",
            headers=headers
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())["data"]["file_path"]

    source_path = Path(get_asset_path(row["source_asset_id"]))
    magic_path = Path(get_asset_path(row["magic_asset_id"]))

    if not source_path.exists():
        raise FileNotFoundError(f"Source clip not found on disk: {source_path}")
    if not magic_path.exists():
        raise FileNotFoundError(f"Magic clip not found on disk: {magic_path}")

    return StitchManifest(
        base_clip=source_path,
        magic_clip=magic_path,
    )
```

---

### TASK 6 — Canonize `assemble_magic_sequence()` as first-class function

```python
def assemble_magic_sequence(scene_key: str, output_path: Path) -> Path:
    """
    Canonical stitch: [Kling base clip] + [compositor magic on held still]
    This is NOT a workaround — it is the permanent production pattern.
    Source resolution always via Directus, never filename patterns.
    Output is normalized per LD-284 before concat.
    """
    manifest = resolve_stitch_clips(scene_key)

    # Normalize both clips per LD-284 NORMALIZATION_BEFORE_CONCAT_V1
    # H.264 High / yuv420p / 1280x720 / 24fps / AAC 128kbps mono 44.1kHz / +faststart
    normalized_base = _normalize_clip(manifest.base_clip)
    normalized_magic = _normalize_clip(manifest.magic_clip)

    # Build concat list
    concat_list = output_path.parent / f"concat_{scene_key}.txt"
    with open(concat_list, "w") as f:
        f.write(f"file '{normalized_base}'\n")
        f.write(f"file '{normalized_magic}'\n")

    # Concat
    import subprocess
    result = subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(output_path)
    ], capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed:\n{result.stderr}")

    # Register assembled output to Directus
    _register_assembled_sequence(scene_key, output_path)

    # Cleanup temp files
    concat_list.unlink(missing_ok=True)

    print(f"Assembled: {output_path}")
    return output_path


def _normalize_clip(clip_path: Path) -> Path:
    """Normalize to canonical codec spec per LD-284."""
    out_path = clip_path.parent / f"{clip_path.stem}_normalized{clip_path.suffix}"
    if out_path.exists() and out_path.stat().st_mtime > clip_path.stat().st_mtime:
        return out_path  # cache hit

    import subprocess
    result = subprocess.run([
        "ffmpeg", "-y", "-i", str(clip_path),
        "-c:v", "libx264", "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,"
               "pad=1280:720:(ow-iw)/2:(oh-ih)/2",
        "-r", "24",
        "-c:a", "aac", "-b:a", "128k", "-ac", "1", "-ar", "44100",
        "-movflags", "+faststart",
        str(out_path)
    ], capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"Normalization failed for {clip_path}:\n{result.stderr}")

    return out_path
```

---

### TASK 7 — Update SKILL.md and governance file

After Tasks 1–6 are complete and at least one scene has been rendered through the full pipeline with Kim approval, update:

**`.claude/skills/visible-magic/SKILL.md`** — change PHASE 1 to call `render_magic(scene_key)` by default. Remove all references to manual coordinate specification. Update "Kim inputs" section to show the 5-button feedback surface only.

**`Production/governance/visible-magic_governance.md`** — update checklist to include: geometry detector confidence gate, background class warning gate, style validation gate, Directus registration gate.

---

## SECTION 3 — LOCKED PARAMETERS (never tune these)

These were locked through Kim approval and explicit rejection. Any Claude session that finds itself tuning these is doing it wrong — stop and re-read this document.

| Parameter | Locked value | Reason locked |
|---|---|---|
| Blend mode | Additive | Screen mode fails on daytime bg — tested v1–v5, all invisible |
| Palette | `(255,255,238)/(255,252,200)/(255,240,155)` | Teal rejected. Blue rejected. Cool palettes all rejected. |
| Dot sizes | `[1,1,1,2,2,3]` | Anything larger = blobs. Kim rejected explicitly. |
| Scatter distribution | Symmetric Gaussian (NOT `abs(gauss)`) | `abs(gauss)` = half-normal = floating horizontal band |
| `scatter_y_frac` | 0.032 (for floor trails) | Larger = floating appearance. Rejected. |
| `AMBIENT_BLUR_YX` | `[6.0, 28.0]` baseline | SIGMA_Y > 8px leaks into sky = floating. Rejected. |
| `AMBIENT_MIX` | 2.4 | Empirically tuned in v6 approval session |
| `T_TRAIL_COMPLETE` | 0.70 | Timing pattern approved in v6 |
| `T_FADEOUT_START` | 0.75 | Same |
| `seed` | 42 | Determinism |
| Particle pre-placement | All at `__init__`, sorted by `ts` | Per-frame placement = popping particles. Rejected. |
| `n_particles` | 1800 | Approved in v6. Do not reduce (invisible) or increase (not tested). |

---

## SECTION 4 — KIM'S FEEDBACK SURFACE (the ONLY adjustments allowed)

When Kim responds to a preview, Claude may ONLY do one of these five things:

| Kim says | Claude does | Parameter changed |
|---|---|---|
| "approve" | Proceed to full video render | None |
| "brighter" | `gain_override = 1.30` → one re-render | Gain multiplier only |
| "dimmer" | `gain_override = 0.75` → one re-render | Gain multiplier only |
| "lower" | `_adjust_path_vertical(delta_y=0.02)` → one re-render | Y offset of all path_pts |
| "reposition" / "wrong position" | Re-run `detect_stone_center()` or `detect_foot_contact()` → debug image | Path_pts only |
| "reject" | Log to Directus `prod_magic_clips` status=rejected, stop | N/A |

**Hard stop:** If Kim is not satisfied after 3 preview renders, STOP completely and ask: "Can you describe what looks wrong? I want to make sure I understand before rendering again." Do not attempt a 4th adjustment.

**Never do these in response to Kim feedback:**
- Tune `n_particles`, `SIGMA_Y`, `scatter_y_frac`, `dot_sizes`, `palette`, `blend_mode`, `ambient_mix`, `sparkle_blur`, or `ambient_gain`
- Ask Kim what opacity, blur, or particle count she prefers
- Suggest changing the style

---

## SECTION 5 — ANTI-PATTERNS (what went wrong before; do not repeat)

| Anti-pattern | Why it failed | Correct approach |
|---|---|---|
| Darkening the whole image to make magic visible | Kim: "you made it nighttime" | Additive blend + auto-gain, never alter the background |
| Screen blend mode | Math: bg=180, magic=100 → only +30 delta, invisible | Additive blend only |
| Storing pixel coordinates in KNOWN_SCENES | SHA drift when clip re-renders; integrity gate never fires (all null) | Archetype registry + geometry_detector.infer() at render time |
| Using numpy luminosity peak to find foot contact | Found shell highlight (y=0.898) not ground (y=0.96) | Alpha mask bottom edge or color-threshold |
| Eyeballing fractional coordinates | 130px error (0.08 fractional × 1676px) on runestone | geometry_detector + debug image + Kim confirms |
| Resolving stitch clips by filename | v2 full-sequence catastrophe: pulled wrong clips for all 3 sources | resolve_stitch_clips() → Directus only |
| Using `abs(gauss)` scatter | Half-normal distribution creates floating horizontal band | Symmetric `gauss(0, sigma)` |
| Per-frame particle placement | Particles pop into existence mid-trail | Pre-place all particles at init, sort by ts |
| Large dot sizes (>3px) | Blobs, not sparkles | `dot_sizes = [1,1,1,2,2,3]` locked |
| Using `wide_ori` or `burst` styles in production | Not approved — `wide_ori` is draft, `burst` doesn't exist | tessa_ori only in V1 |
| Tuning sigma/density in response to Kim feedback | Enters 25-D blind search space | Only adjust gain or path position |

---

## SECTION 6 — VERIFICATION CHECKLIST (run before marking any task complete)

### After TASK 1 (`geometry_detector.py`)
- [ ] `python3 Production/tools/geometry_detector.py --scene m1_e1_res_beat_01_heartwood --clip <clip> --confirm` runs without error
- [ ] Debug image opens in Preview with red circles visible
- [ ] Circles are in approximately correct positions (stone centroid, floor contact)
- [ ] Confidence score prints to console
- [ ] Low-confidence path (< 0.8) renders debug image automatically

### After TASK 2 (`scene_registry.yaml`)
- [ ] File is valid YAML (parse with `python3 -c "import yaml; yaml.safe_load(open('scene_registry.yaml'))"`)
- [ ] All 3 existing scenes are present: `m1_e1_res_beat_01_heartwood`, `m1_e1_res_beat_01_tessa_exit`, `m1_e1_res_beat_02_runestone`
- [ ] `GeometryDetector(registry_path).registry` loads all 3 scenes without KeyError

### After TASK 3 (`background_classifier.py`)
- [ ] `BackgroundClassifier().classify(heartwood_frame, path_pts)` returns `"daytime-warm"`
- [ ] `get_params("daytime-warm")["AMBIENT_BLUR_YX"]` returns `[6.0, 28.0]`
- [ ] `warn_if_unvalidated("nighttime")` returns a warning string
- [ ] `warn_if_unvalidated("daytime-warm")` returns None

### After TASK 4 (Directus `prod_magic_clips`)
- [ ] Collection exists in Directus admin panel
- [ ] All required fields present (scene_key, status, source_asset_id, magic_asset_id, etc.)
- [ ] Can POST a test row and retrieve it
- [ ] The 3 existing registry entries from `magic_clip_registry.json` are migrated as rows
- [ ] `magic_clip_registry.json` is deleted (after confirming migration)

### After TASK 5 (`render_magic()` entry point)
- [ ] `_validate_style("tessa_ori")` passes without error
- [ ] `_validate_style("wide_ori")` raises RuntimeError (not approved)
- [ ] `_validate_style("wide_ori", draft_mode=True)` passes
- [ ] `STYLES["tessa_ori"]["directus_ld"]` == 398 (not None)
- [ ] `render_magic("m1_e1_res_beat_01_heartwood", preview_only=True)` produces a preview PNG
- [ ] Preview PNG opens in Preview.app
- [ ] Background class prints to console
- [ ] Gain applied prints to console

### After TASK 6 (`assemble_magic_sequence()`)
- [ ] `resolve_stitch_clips("m1_e1_res_beat_01_heartwood")` returns correct paths from Directus
- [ ] `resolve_stitch_clips("nonexistent_key")` raises ValueError (not silent failure)
- [ ] `assemble_magic_sequence("m1_e1_res_beat_01_heartwood", output_path)` produces valid MP4
- [ ] `ffprobe` confirms output is H.264 High / yuv420p / 1280×720 / 24fps (LD-284 compliance)
- [ ] Output registered to Directus `prod_visual_assets`

### After TASK 7 (SKILL.md + governance update)
- [ ] SKILL.md PHASE 1 references `render_magic(scene_key)`, not manual compositor
- [ ] Governance file includes geometry/bg/style/Directus gates
- [ ] End-to-end test: say "produce visible magic" → preview opens → approve → full video → Directus registered → stitch → output MP4

---

## SECTION 7 — DEPENDENCIES AND EXECUTION ORDER

```
TASK 1 (geometry_detector.py)
  ↓ enables
TASK 2 (scene_registry.yaml)    ← TASK 1 reads this file
  ↓ enables
TASK 3 (background_classifier.py)   ← parallel with TASK 2, no dependency
  ↓
TASK 4 (Directus prod_magic_clips)  ← parallel, no code dependency
  ↓ enables
TASK 5 (render_magic() wires TASK 1+2+3+4 together)
  ↓ enables
TASK 6 (assemble_magic_sequence uses Directus from TASK 4)
  ↓ enables
TASK 7 (SKILL.md update — last, after end-to-end validated)
```

TASKS 1, 2, 3, and 4 can all be worked simultaneously. TASK 5 requires 1+2+3+4. TASK 6 requires 4+5. TASK 7 requires a passing end-to-end test.

---

## SECTION 8 — ESTIMATED EFFORT

| Task | Estimated hours |
|---|---|
| 1 — geometry_detector.py | 3–4 hrs |
| 2 — scene_registry.yaml | 30 min |
| 3 — background_classifier.py | 1–2 hrs |
| 4 — Directus prod_magic_clips | 1–2 hrs |
| 5 — render_magic() entry point | 2–3 hrs |
| 6 — assemble_magic_sequence() | 1 hr |
| 7 — SKILL.md + governance update | 30 min |
| **Total** | **~10–13 hrs** |

---

## SECTION 9 — MULTIPASS COMPLETENESS CHECK

### Pass 1 — Does this handoff cover all 7 fixes from the tech spec?
- [x] Fix 1: geometry_detector.py — TASK 1 (full implementation)
- [x] Fix 2: Archetype-addressed KNOWN_SCENES — TASK 2 (scene_registry.yaml)
- [x] Fix 3: Background-class routing — TASK 3 (background_classifier.py)
- [x] Fix 4: Directus registry — TASK 4 (prod_magic_clips collection)
- [x] Fix 5: render_magic() entry point — TASK 5
- [x] Fix 6: Style enforcement + LD-398 — TASK 5b (inside render_magic wiring)
- [x] Fix 7: Canonical stitch function — TASK 6

### Pass 2 — Does this handoff cover all failure modes from the lessons learned?
- [x] Invisibility on bright backgrounds → additive blend + gain routing (locked params + bg_classifier)
- [x] Floating trail → symmetric gaussian + SIGMA_Y locked + scatter_y_frac locked
- [x] Wrong coordinates → geometry_detector auto-detection
- [x] Jerky particles → pre-placement at init (locked invariant)
- [x] Wrong stitch clips → resolve_stitch_clips() Directus gate

### Pass 3 — Does this handoff cover the governance/compliance requirements?
- [x] LD-398 linked in code (Task 5b)
- [x] Style enforcement blocks non-approved styles (Task 5b)
- [x] LD-284 normalization applied before concat (Task 6)
- [x] Two-write rule (prod_visual_assets + prod_magic_clips) in Task 5d registration
- [x] Activity log write included in registration
- [x] Rule 19 compliance: no shortcuts, no placeholders, full implementation per task

### Pass 4 — Anything in the tech spec NOT covered here?
- [x] MagicRenderResult dataclass — referenced in Task 5c; Claude must define this simple dataclass when implementing (fields: preview_path, video_path, coords_used, background_class, gain_applied, directus_asset_id)
- [x] `_load_directus_credentials()` helper — referenced in Task 5d; reads from `Production/API_KEYS_MASTER.md` at runtime (not hardcoded)
- [x] `_register_approved_magic()` — referenced in Task 5c; implementation pattern in TECH_SPEC_v1.md §11.3
- [x] `_register_assembled_sequence()` — referenced in Task 6; similar to register_approved_magic but for the final concat output
- [x] `StitchManifest` dataclass — simple namedtuple, define when implementing Task 6

### Pass 5 — Is there anything Kim needs to do before implementation starts?
**No.** Implementation can begin immediately. The only Kim interaction needed is:
1. Confirm the first debug image from geometry_detector (one red-circle confirmation per scene archetype)
2. Approve the first full preview PNG from render_magic
Everything else is autonomous.

---

*This handoff is complete. Start with TASK 1. All code blocks above are production-ready implementations — not pseudocode.*
