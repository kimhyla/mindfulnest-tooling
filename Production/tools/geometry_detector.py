"""
Production/tools/geometry_detector.py

Auto-detects magic trail path_pts from source clip and scene archetype.
Eliminates the manual 4-step coordinate-specification dance for all known scene archetypes.

Usage:
    python3 geometry_detector.py --scene m1_e1_res_beat_01_heartwood --clip path/to/clip.mp4
    python3 geometry_detector.py --scene m1_e1_res_beat_01_heartwood --clip path/to/clip.mp4 --confirm
    python3 geometry_detector.py --scene m1_e1_res_beat_01_heartwood --bg path/to/still.png
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------------------
# Color threshold functions (vectorized — work on numpy arrays OR scalars)
# Migrated from magic_position_finder.py
# Each takes r, g, b as np.ndarray (H×W) and returns bool mask (H×W)
# ---------------------------------------------------------------------------

def _thresh_orange(r, g, b):
    return (r > 180) & (g > 80) & (g < 160) & (b < 80)

def _thresh_purple(r, g, b):
    return (r > 100) & (b > 130) & (g < 100)

def _thresh_yellow(r, g, b):
    return (r > 200) & (g > 180) & (b < 100)

def _thresh_red(r, g, b):
    return (r > 180) & (g < 80) & (b < 80)

def _thresh_blue(r, g, b):
    return (b > 160) & (r < 100) & (g < 130)

def _thresh_green(r, g, b):
    return (g > 150) & (r < 120) & (b < 120)

COLOR_THRESHOLDS = {
    "orange": _thresh_orange,
    "purple": _thresh_purple,
    "yellow": _thresh_yellow,
    "red":    _thresh_red,
    "blue":   _thresh_blue,
    "green":  _thresh_green,
}

# Confidence thresholds
CONFIDENCE_AUTO    = 0.80   # >= this: proceed without Kim confirmation
CONFIDENCE_WARN    = 0.50   # >= this: render debug image and ask Kim
# < CONFIDENCE_WARN: stop and ask Kim to specify manually


class GeometryDetector:
    """
    Detects path_pts for MagicCompositor from source clip + scene archetype.

    All coordinates are returned as fractional (x_frac, y_frac) tuples in [0, 1].
    confidence is float [0, 1]; < CONFIDENCE_AUTO triggers debug image gate.
    """

    def __init__(self, scene_registry_path: Optional[Path] = None):
        if scene_registry_path is None:
            scene_registry_path = Path(__file__).parent / "scene_registry.yaml"
        if not scene_registry_path.exists():
            raise FileNotFoundError(
                f"scene_registry.yaml not found at {scene_registry_path}. "
                f"Create it before using GeometryDetector."
            )
        with open(scene_registry_path) as f:
            self.registry = yaml.safe_load(f) or {}

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def infer(
        self,
        scene_key: str,
        source_clip: Optional[Path] = None,
        bg_still: Optional[Path] = None,
    ) -> tuple[list[tuple[float, float]], float]:
        """
        Main entry point.

        Looks up archetype from scene_registry.yaml, dispatches to correct
        detector method, returns (path_pts, confidence).

        Provide either source_clip (video) or bg_still (PNG). If both are
        provided, source_clip is used for motion-based detectors and bg_still
        for colour-based detectors.

        Returns:
            path_pts  : list of (x_frac, y_frac)
            confidence: float 0–1
                        < CONFIDENCE_AUTO (0.80) → caller should render debug image
                        < CONFIDENCE_WARN (0.50) → caller should stop and ask Kim
        """
        scene = self.registry.get(scene_key)
        if scene is None:
            raise ValueError(
                f"Scene key '{scene_key}' not found in scene_registry.yaml. "
                f"Add an entry before running."
            )

        # HIGHEST PRIORITY: Kim-clicked path from path_picker.html
        # When present, skip ALL detection — confidence=1.0, no debug gate.
        if scene.get("manual_path"):
            path_pts = [tuple(float(v) for v in pt) for pt in scene["manual_path"]]
            return path_pts, 1.0

        archetype = scene["archetype"]

        # Resolve frames we need
        bg_frame = self._load_bg_frame(source_clip, bg_still, position="first")
        mid_frame = self._load_bg_frame(source_clip, bg_still, position="mid")

        if archetype == "ground_left_to_target":
            return self._detect_ground_left_to_target(
                bg_frame,
                color_target=scene.get("color_target"),
                direction=scene.get("direction", "left"),
                target_y_min=float(scene.get("target_y_min", 0.0)),
                floor_perspective=bool(scene.get("floor_perspective", False)),
                manual_target=scene.get("manual_target"),
                manual_origin=scene.get("manual_origin"),
            )
        elif archetype == "character_exit_ground":
            return self._detect_character_exit_ground(
                mid_frame,
                source_clip=source_clip,
                direction=scene.get("direction", "right"),
            )
        elif archetype == "stone_activation":
            return self._detect_stone_activation(
                bg_frame,
                color_target=scene.get("color_target"),
            )
        elif archetype == "wide_clearing_cross":
            return self._detect_wide_clearing_cross(bg_frame)
        else:
            raise ValueError(
                f"Unknown archetype '{archetype}' for scene '{scene_key}'. "
                f"Valid: ground_left_to_target, character_exit_ground, "
                f"stone_activation, wide_clearing_cross"
            )

    def detect_foot_contact(
        self, frame: np.ndarray
    ) -> tuple[tuple[float, float], float]:
        """
        Find where a character's foot/base contacts the ground.

        Priority order:
          1. Alpha channel bottom edge (highest confidence)
          2. Luminance-gradient bottom band (medium confidence)

        Returns ((x_frac, y_frac), confidence)
        """
        h, w = frame.shape[:2]

        if frame.ndim == 3 and frame.shape[2] == 4:
            alpha = frame[:, :, 3]
            rows_with_content = np.where(alpha.max(axis=1) > 30)[0]
            if len(rows_with_content) > 0:
                bottom_row = int(rows_with_content.max())
                cols_at_bottom = np.where(alpha[bottom_row, :] > 30)[0]
                if len(cols_at_bottom) > 0:
                    center_col = int(cols_at_bottom.mean())
                    # Confidence: wider alpha footprint = more certain
                    confidence = float(min(1.0, len(cols_at_bottom) / 60))
                    return ((center_col / w, bottom_row / h), confidence)

        # Fallback: luminance gradient — find strongest horizontal edge in
        # the lower 60% of the frame (where the character base would be)
        gray = cv2.cvtColor(
            frame[:, :, :3] if frame.ndim == 3 else frame,
            cv2.COLOR_RGB2GRAY,
        ).astype(np.float32)
        grad_y = np.abs(np.gradient(gray, axis=0))
        lower = grad_y[int(h * 0.4):, :]
        row_sums = lower.sum(axis=1)
        peak_local = int(row_sums.argmax())
        peak_row = int(h * 0.4) + peak_local
        center_col = w // 2
        # Low confidence: gradient can be misleading (shell highlights, etc.)
        confidence = 0.50
        return ((center_col / w, peak_row / h), confidence)

    def detect_exit_vector(
        self, clip: Path, direction: str = "right"
    ) -> tuple[list[tuple[float, float]], float]:
        """
        Detect character exit direction using optical flow on last 10 frames.

        Returns (path_pts, confidence) where path_pts is 3 control points:
            [foot_contact, midpoint, off_screen_exit]
        """
        frames = self._extract_last_n_frames(clip, n=10)
        if len(frames) < 2:
            return self._fallback_exit_path(direction), 0.40

        # Compute dense optical flow between consecutive frame pairs
        flows = []
        for i in range(len(frames) - 1):
            g1 = cv2.cvtColor(frames[i], cv2.COLOR_RGB2GRAY)
            g2 = cv2.cvtColor(frames[i + 1], cv2.COLOR_RGB2GRAY)
            flow = cv2.calcOpticalFlowFarneback(
                g1, g2, None,
                pyr_scale=0.5, levels=3, winsize=15,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
            )
            flows.append(flow)

        avg_flow = np.mean(flows, axis=0)   # shape (H, W, 2)
        h, w = avg_flow.shape[:2]

        magnitude = np.sqrt(avg_flow[..., 0] ** 2 + avg_flow[..., 1] ** 2)
        threshold = np.percentile(magnitude, 80)
        strong = magnitude > threshold

        if strong.sum() == 0:
            return self._fallback_exit_path(direction), 0.40

        mean_vx = float(avg_flow[..., 0][strong].mean())
        mean_vy = float(avg_flow[..., 1][strong].mean())
        mag_norm = np.sqrt(mean_vx ** 2 + mean_vy ** 2)

        if mag_norm < 0.1:
            return self._fallback_exit_path(direction), 0.45

        # Find character base in the last frame using strong-motion region
        rows, cols = np.where(strong)
        n_bottom = max(1, len(rows) // 4)
        bottom_idx = rows.argsort()[-n_bottom:]
        foot_x = float(cols[bottom_idx].mean()) / w
        foot_y = float(rows[bottom_idx].mean()) / h

        # Project exit point in motion direction, far enough to be off-screen
        nx, ny = mean_vx / mag_norm, mean_vy / mag_norm
        exit_x = float(np.clip(foot_x + nx * 2.0, -0.10, 1.10))
        exit_y = float(np.clip(foot_y + ny * 0.3, 0.0, 1.0))

        mid_x = (foot_x + exit_x) / 2
        mid_y = (foot_y + exit_y) / 2

        path_pts = [(foot_x, foot_y), (mid_x, mid_y), (exit_x, exit_y)]
        confidence = float(min(1.0, magnitude[strong].mean() / 5.0))
        return path_pts, confidence

    def detect_stone_center(
        self,
        bg_frame: np.ndarray,
        color: str,
        target_y_min: float = 0.0,
    ) -> tuple[tuple[float, float], float]:
        """
        Find centroid of a coloured stone/target using vectorised thresholding.

        target_y_min: ignore any matching pixels whose Y fraction is < this value.
                      Use this when the colour also appears on elevated geometry
                      (e.g. altar bowl contents above the floor step edge).
                      0.0 = no floor clamp (default).

        Returns ((x_frac, y_frac), confidence)
        Confidence scales with pixel count — more matching pixels = more certain.
        """
        if color not in COLOR_THRESHOLDS:
            raise ValueError(
                f"Unknown color '{color}'. "
                f"Valid: {sorted(COLOR_THRESHOLDS.keys())}"
            )

        h, w = bg_frame.shape[:2]
        rgb = bg_frame[:, :, :3].astype(np.int32)
        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]

        mask = COLOR_THRESHOLDS[color](r, g, b)

        # Apply floor clamp: blank out rows above target_y_min
        if target_y_min > 0.0:
            clamp_row = int(target_y_min * h)
            mask[:clamp_row, :] = False

        pixel_count = int(mask.sum())

        if pixel_count < 10:
            # Nothing found at or below floor level — return a safe floor-level
            # fallback at the centre X and the clamped Y, very low confidence.
            fallback_y = max(target_y_min, 0.70)
            return ((0.5, fallback_y), 0.10)

        rows, cols = np.where(mask)
        cx = float(cols.mean()) / w
        cy = float(rows.mean()) / h

        # ~500 matching pixels → full confidence (stone fills small area)
        confidence = float(min(1.0, pixel_count / 500))
        return ((cx, cy), confidence)

    def detect_horizon_line(
        self, bg_frame: np.ndarray
    ) -> tuple[float, float]:
        """
        Detect the horizon for wide-clearing-cross shots.
        Finds the row with the sharpest luminance transition.

        Returns (y_frac, confidence)
        """
        gray = bg_frame[:, :, :3].mean(axis=2).astype(np.float32)
        h = gray.shape[0]
        row_lum = gray.mean(axis=1)
        grad = np.abs(np.gradient(row_lum))
        horizon_row = int(grad.argmax())
        max_grad = float(grad.max())
        # 30+ luminance-units per row = sharp, unambiguous horizon
        confidence = float(min(1.0, max_grad / 30.0))
        return (horizon_row / h, confidence)

    def render_debug_image(
        self,
        bg_frame: np.ndarray,
        path_pts: list[tuple[float, float]],
        output_path: Path,
        scene_key: str = "",
        confidence: float = 0.0,
    ) -> Path:
        """
        Overlay detected path_pts as numbered red circles on bg_frame.
        Connects them with an orange line.
        Opens the result in Preview.app automatically.

        Used for Kim's one-time confirmation on novel archetypes.
        """
        img = Image.fromarray(bg_frame[:, :, :3].astype(np.uint8))
        draw = ImageDraw.Draw(img)
        h, w = bg_frame.shape[:2]
        R = max(16, int(min(w, h) * 0.025))   # circle radius scales with image

        # Draw connecting path first (under circles)
        if len(path_pts) > 1:
            pixel_pts = [(int(x * w), int(y * h)) for x, y in path_pts]
            draw.line(pixel_pts, fill=(255, 120, 0), width=max(2, R // 6))

        # Draw numbered circles
        for i, (x_frac, y_frac) in enumerate(path_pts):
            px, py = int(x_frac * w), int(y_frac * h)
            draw.ellipse(
                [px - R, py - R, px + R, py + R],
                outline=(255, 30, 30),
                width=max(2, R // 5),
            )
            label = str(i)
            # Simple text — ImageFont.load_default() is always available
            draw.text((px + R + 4, py - 8), label, fill=(255, 255, 0))

        # Header text
        header = (
            f"Geometry: {scene_key}   confidence={confidence:.2f}\n"
            f"Red circles = detected path points.  "
            f"Reply 'ok' to confirm, 'reposition' to override."
        )
        draw.rectangle([0, 0, w, 42], fill=(0, 0, 0, 180))
        draw.text((6, 4), header, fill=(255, 255, 180))

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path)
        subprocess.run(["open", "-a", "Preview", str(output_path)], check=False)
        return output_path

    # -----------------------------------------------------------------------
    # Archetype detectors (private)
    # -----------------------------------------------------------------------

    def _detect_ground_left_to_target(
        self,
        bg_frame: np.ndarray,
        color_target: Optional[str],
        direction: str,
        target_y_min: float = 0.0,
        floor_perspective: bool = False,
        manual_target: Optional[list] = None,
        manual_origin: Optional[list] = None,
    ) -> tuple[list, float]:
        """
        Archetype: magic travels from one side of the frame to a coloured stone.

        manual_origin   — [x_frac, y_frac] override for the start point. Use when
                          the floor entry point can't be auto-detected reliably.
        manual_target   — [x_frac, y_frac] override for the endpoint. Use when
                          the landing point has no distinctive colour signature.
        floor_perspective — shapes the midpoint between origin and target to follow
                           the floor slope. When both manual points are set this
                           simply interpolates between them with a slight ground-hug.
        target_y_min    — floor clamp; ignores colour matches above this Y.
        """
        # ── Resolve target ───────────────────────────────────────────────────
        if manual_target is not None:
            target_x = float(manual_target[0])
            target_y = float(manual_target[1])
            target_confidence = 1.0
        else:
            if color_target is None:
                raise ValueError(
                    "ground_left_to_target requires either color_target or manual_target"
                )
            target, target_confidence = self.detect_stone_center(
                bg_frame, color_target, target_y_min=target_y_min
            )
            target_x, target_y = target

        # ── Resolve origin ───────────────────────────────────────────────────
        origin_x = 0.0 if direction == "left" else 1.0

        if manual_origin is not None:
            origin_x = float(manual_origin[0])
            origin_y = float(manual_origin[1])
            origin_confidence = 1.0
        elif floor_perspective:
            # Perspective rule: foreground floor is LOWER in the image (larger y)
            # than the mid-ground altar step. The origin is further from camera so
            # it sits lower in frame. Typical drop: +0.08 in y per 0.5 horizontal.
            horizontal_travel = abs(target_x - origin_x)
            perspective_drop = horizontal_travel * 0.18
            origin_y = min(1.0, target_y + perspective_drop)
            origin_confidence = 0.7
        else:
            origin_y = target_y
            origin_confidence = 0.8

        # ── Midpoint: interpolate along the floor slope ──────────────────────
        mid_x = (origin_x + target_x) / 2
        # Linear blend + tiny downward nudge so the trail hugs the ground surface
        mid_y = (origin_y + target_y) / 2 + 0.005

        confidence = min(target_confidence, origin_confidence)
        path_pts = [(origin_x, origin_y), (mid_x, mid_y), (target_x, target_y)]
        return path_pts, confidence

    def _detect_character_exit_ground(
        self,
        mid_frame: np.ndarray,
        source_clip: Optional[Path],
        direction: str,
    ) -> tuple[list, float]:
        """Archetype: character walks off screen with a ground trail."""
        foot_coords, foot_conf = self.detect_foot_contact(mid_frame)

        if source_clip is not None and source_clip.exists():
            exit_pts, exit_conf = self.detect_exit_vector(source_clip, direction)
        else:
            exit_pts = self._fallback_exit_path(direction)
            exit_conf = 0.40

        if foot_conf >= 0.60 and exit_conf >= 0.50:
            # Replace exit_pts[0] with detected foot for a cleaner join
            path_pts = [foot_coords] + exit_pts[1:]
            confidence = float(min(foot_conf, exit_conf))
        else:
            path_pts = exit_pts
            confidence = exit_conf * 0.70   # penalise for missing foot

        return path_pts, confidence

    def _detect_stone_activation(
        self,
        bg_frame: np.ndarray,
        color_target: Optional[str],
    ) -> tuple[list, float]:
        """Archetype: radial burst from stone centroid."""
        if color_target is None:
            raise ValueError("stone_activation archetype requires color_target")
        centroid, confidence = self.detect_stone_center(bg_frame, color_target)
        # For burst-type magic the compositor only needs the single centroid;
        # it handles the radial expansion internally.
        return [centroid], confidence

    def _detect_wide_clearing_cross(
        self, bg_frame: np.ndarray
    ) -> tuple[list, float]:
        """Archetype: horizontal trail across a clearing at the horizon line."""
        h, w = bg_frame.shape[:2]
        horizon_y, confidence = self.detect_horizon_line(bg_frame)
        path_pts = [(0.0, horizon_y), (0.5, horizon_y), (1.0, horizon_y)]
        return path_pts, confidence

    # -----------------------------------------------------------------------
    # Frame extraction helpers
    # -----------------------------------------------------------------------

    def _load_bg_frame(
        self,
        source_clip: Optional[Path],
        bg_still: Optional[Path],
        position: str = "first",
    ) -> np.ndarray:
        """
        Load a background frame from either a video clip or a PNG still.
        position: 'first' | 'mid' | 'last'
        """
        if bg_still is not None and bg_still.exists():
            img = np.array(Image.open(bg_still).convert("RGB"))
            return img
        if source_clip is not None and source_clip.exists():
            return self._extract_frame(source_clip, position)
        raise ValueError(
            "Must provide at least one of source_clip or bg_still that exists on disk."
        )

    def _extract_frame(self, clip: Path, position: str = "mid") -> np.ndarray:
        """Extract a single frame from a video clip as an RGB numpy array."""
        cap = cv2.VideoCapture(str(clip))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open clip: {clip}")

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            total = 1

        pos_map = {"first": 0, "mid": total // 2, "last": max(0, total - 3)}
        frame_idx = pos_map.get(position, int(position))
        frame_idx = max(0, min(frame_idx, total - 1))

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            raise RuntimeError(
                f"Could not read frame {frame_idx} from {clip} "
                f"(total frames: {total})"
            )
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def _extract_last_n_frames(self, clip: Path, n: int = 10) -> list[np.ndarray]:
        """Extract the last N frames from a video clip."""
        cap = cv2.VideoCapture(str(clip))
        if not cap.isOpened():
            return []

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        start = max(0, total - n)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)

        frames = []
        for _ in range(n):
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        cap.release()
        return frames

    def _fallback_exit_path(self, direction: str) -> list[tuple[float, float]]:
        """Safe fallback path when optical flow detection fails."""
        if direction == "right":
            return [(0.55, 0.93), (0.78, 0.95), (1.05, 0.97)]
        elif direction == "left":
            return [(0.45, 0.93), (0.22, 0.95), (-0.05, 0.97)]
        else:   # up or unknown
            return [(0.50, 0.90), (0.50, 0.80), (0.50, 0.65)]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Detect magic trail geometry from source clip or background still."
    )
    parser.add_argument(
        "--scene", required=True,
        help="Scene key from scene_registry.yaml (e.g. m1_e1_res_beat_01_heartwood)"
    )
    parser.add_argument(
        "--clip", default=None,
        help="Path to source video clip (MP4). Used for motion-based detectors."
    )
    parser.add_argument(
        "--bg", default=None,
        help="Path to background still PNG. Used for colour-based detectors. "
             "Takes priority over --clip for colour detection."
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Always render debug image for Kim confirmation, even at high confidence."
    )
    parser.add_argument(
        "--output-debug", default=None,
        help="Custom path for debug image output. "
             "Defaults to <clip-parent>/debug_geometry_<scene_key>.png"
    )
    parser.add_argument(
        "--registry",
        default=str(Path(__file__).parent / "scene_registry.yaml"),
        help="Path to scene_registry.yaml (default: same dir as this script)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output result as JSON (for programmatic use)"
    )
    args = parser.parse_args()

    if args.clip is None and args.bg is None:
        parser.error("Provide at least one of --clip or --bg")

    clip_path = Path(args.clip) if args.clip else None
    bg_path   = Path(args.bg)   if args.bg   else None

    if clip_path and not clip_path.exists():
        print(f"ERROR: clip not found: {clip_path}", file=sys.stderr)
        sys.exit(1)
    if bg_path and not bg_path.exists():
        print(f"ERROR: bg still not found: {bg_path}", file=sys.stderr)
        sys.exit(1)

    detector = GeometryDetector(Path(args.registry))
    path_pts, confidence = detector.infer(args.scene, clip_path, bg_path)

    if args.json:
        print(json.dumps({
            "scene_key": args.scene,
            "path_pts": path_pts,
            "confidence": round(confidence, 4),
            "needs_confirmation": confidence < CONFIDENCE_AUTO,
        }, indent=2))
    else:
        print(f"\nScene:      {args.scene}")
        print(f"Path pts:   {[f'({x:.4f}, {y:.4f})' for x, y in path_pts]}")
        print(f"Confidence: {confidence:.2f}  ", end="")
        if confidence >= CONFIDENCE_AUTO:
            print("✓ High — no Kim confirmation needed")
        elif confidence >= CONFIDENCE_WARN:
            print("⚠  Medium — rendering debug image for Kim confirmation")
        else:
            print("✗ Low — stop and ask Kim to specify position manually")

    # Render debug image when: low/medium confidence OR --confirm flag
    needs_debug = (confidence < CONFIDENCE_AUTO) or args.confirm
    if needs_debug:
        source_for_debug = clip_path or bg_path
        try:
            bg_frame = detector._load_bg_frame(clip_path, bg_path, position="first")
        except Exception as e:
            print(f"WARNING: Could not load frame for debug image: {e}", file=sys.stderr)
            bg_frame = None

        if bg_frame is not None:
            if args.output_debug:
                debug_path = Path(args.output_debug)
            else:
                base = (clip_path or bg_path).parent
                debug_path = base / f"debug_geometry_{args.scene}.png"

            out = detector.render_debug_image(
                bg_frame, path_pts, debug_path, args.scene, confidence
            )
            print(f"\nDebug image: {out}  (opened in Preview)")
            if confidence < CONFIDENCE_AUTO:
                print(
                    "→ Ask Kim to confirm the red circles are on correct positions "
                    "before proceeding with video render."
                )
    elif not args.json:
        print("(No debug image needed — confidence is high)")


if __name__ == "__main__":
    main()
