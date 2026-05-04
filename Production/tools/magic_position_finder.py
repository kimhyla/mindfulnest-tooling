"""
magic_position_finder.py — debug image generator + pixel-threshold target detection
for the visible-magic skill positioning protocol.

Usage (from skill Phase 1):
    # Generate debug grid image
    python3 magic_position_finder.py --debug-image clip.mp4 --output /tmp/debug.png

    # Detect target object + draw path overlay
    python3 magic_position_finder.py --detect clip.mp4 --target-hint "orange crystal" --output /tmp/confirm.png

    # Compute frame SHA for KNOWN_SCENES validation
    python3 magic_position_finder.py --sha clip.mp4
"""

import sys, hashlib, argparse
import numpy as np
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "-q"])
    from PIL import Image, ImageDraw

try:
    import imageio.v3 as iio
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "imageio[ffmpeg]", "-q"])
    import imageio.v3 as iio


# ── Color thresholds for all 6 runestones ────────────────────────────────
# Each lambda returns True if (r,g,b) matches that stone's color.
# Used by detect_by_color() for automatic target finding.

STONE_COLOR_THRESHOLDS = {
    "orange": lambda r, g, b: r > 200 and g > 100 and b < 100 and g < r - 50,  # Body Stone
    "yellow": lambda r, g, b: r > 200 and g > 200 and b < 100,                  # Watching Stone
    "red":    lambda r, g, b: r > 200 and g < 100 and b < 100,                  # Heart Stone
    "blue":   lambda r, g, b: r < 100 and g < 100 and b > 180,                  # Calm Stone
    "green":  lambda r, g, b: r < 120 and g > 160 and b < 120,                  # Courage Stone
    "purple": lambda r, g, b: r > 130 and g < 80  and b > 130,                  # Grounding Stone
}

KEYWORD_MAP = {
    "orange": "orange", "amber": "orange", "body": "orange",
    "yellow": "yellow", "watching": "yellow",
    "red": "red", "heart": "red",
    "blue": "blue", "calm": "blue",
    "green": "green", "courage": "green",
    "purple": "purple", "grounding": "purple",
}


def load_frame(path: str) -> np.ndarray:
    """Load first frame from video or image file as RGB numpy array."""
    suf = path.lower().rsplit(".", 1)[-1]
    if suf in ("mp4", "mov", "avi", "webm"):
        frame = next(iio.imiter(path, plugin="pyav"))
        return np.array(frame)[:, :, :3]
    else:
        return np.array(Image.open(path).convert("RGB"))


def compute_frame_sha(path: str) -> str:
    """Compute sha256[:16] of first frame bytes. Used for KNOWN_SCENES validation."""
    frame = load_frame(path)
    return hashlib.sha256(frame.tobytes()).hexdigest()[:16]


def find_strongest_color_centroid(frame: np.ndarray) -> tuple:
    """
    Check all stone color thresholds; return (x_frac, y_frac) centroid of
    the largest matching pixel cluster. Falls back to frame center if none found.
    Strides by 4px for speed.
    """
    H, W = frame.shape[:2]
    best_centroid = (0.5, 0.5)
    best_count = 0

    for name, fn in STONE_COLOR_THRESHOLDS.items():
        xs, ys = [], []
        for y in range(0, H, 4):
            for x in range(0, W, 4):
                r, g, b = int(frame[y, x, 0]), int(frame[y, x, 1]), int(frame[y, x, 2])
                if fn(r, g, b):
                    xs.append(x)
                    ys.append(y)
        if len(xs) > best_count:
            best_centroid = (float(np.mean(xs)) / W, float(np.mean(ys)) / H)
            best_count = len(xs)

    return best_centroid


def generate_debug_image(frame: np.ndarray, output_path: str) -> str:
    """
    Generate a debug image with:
    - Full frame with labeled 5% grid lines (yellow)
    - 2x zoomed crop centered on strongest color-match centroid (or center)
    Combined into a single PNG: full frame on top, zoom below.
    """
    H, W = frame.shape[:2]
    img = Image.fromarray(frame[:, :, :3])
    draw = ImageDraw.Draw(img)

    # Grid lines every 5%
    for i in range(1, 20):
        x = int(i * W / 20)
        y = int(i * H / 20)
        draw.line([(x, 0), (x, H)], fill=(255, 220, 0), width=1)
        draw.line([(0, y), (W, y)], fill=(255, 220, 0), width=1)
        label_x = f"{i*5}%"
        label_y = f"{i*5}%"
        draw.text((x + 2, 2), label_x, fill=(255, 220, 0))
        draw.text((2, y + 2), label_y, fill=(255, 220, 0))

    # Find strongest color match for zoom center
    cx_frac, cy_frac = find_strongest_color_centroid(frame)
    cx, cy = int(cx_frac * W), int(cy_frac * H)

    # Zoomed crop: 40% of frame around centroid
    crop_w, crop_h = int(W * 0.40), int(H * 0.40)
    x0 = max(0, cx - crop_w // 2)
    y0 = max(0, cy - crop_h // 2)
    x1 = min(W, x0 + crop_w)
    y1 = min(H, y0 + crop_h)
    crop = img.crop((x0, y0, x1, y1)).resize((crop_w * 2, crop_h * 2), Image.LANCZOS)

    # Stack vertically: full frame + separator + zoom
    sep = 10
    combined = Image.new("RGB", (W, H + sep + crop_h * 2), (20, 20, 20))
    combined.paste(img, (0, 0))
    combined.paste(crop, ((W - crop_w * 2) // 2, H + sep))

    combined.save(output_path)
    print(f"Debug image saved: {output_path}  (grid + zoom at centroid {cx_frac:.2f},{cy_frac:.2f})")
    return output_path


def detect_by_color(frame: np.ndarray, target_hint: str) -> tuple:
    """
    Find target object center using stone color thresholds.
    target_hint: plain English from Kim (e.g. "orange crystal", "the runestone")
    Returns (x_frac, y_frac) of detected centroid.
    """
    H, W = frame.shape[:2]
    hint_lower = target_hint.lower()

    candidates = [STONE_COLOR_THRESHOLDS[v]
                  for k, v in KEYWORD_MAP.items() if k in hint_lower]
    if not candidates:
        candidates = list(STONE_COLOR_THRESHOLDS.values())

    best = (0.5, 0.5)
    best_count = 0
    for fn in candidates:
        xs, ys = [], []
        for y in range(0, H, 2):
            for x in range(0, W, 2):
                r, g, b = int(frame[y, x, 0]), int(frame[y, x, 1]), int(frame[y, x, 2])
                if fn(r, g, b):
                    xs.append(x)
                    ys.append(y)
        if len(xs) > best_count:
            best = (float(np.mean(xs)) / W, float(np.mean(ys)) / H)
            best_count = len(xs)

    return best


def draw_path_overlay(frame: np.ndarray, path_pts: list,
                      target_pt: tuple, output_path: str) -> str:
    """
    Draw confirmation image:
    - Yellow polyline through path_pts (x_frac, y_frac)
    - Red circle at target_pt (x_frac, y_frac)
    """
    H, W = frame.shape[:2]
    img = Image.fromarray(frame[:, :, :3])
    draw = ImageDraw.Draw(img)

    # Yellow path line
    pixel_pts = [(int(x * W), int(y * H)) for x, y in path_pts]
    if len(pixel_pts) >= 2:
        draw.line(pixel_pts, fill=(255, 220, 0), width=3)

    # Red circle at target
    tx, ty = int(target_pt[0] * W), int(target_pt[1] * H)
    r = max(20, int(W * 0.025))
    draw.ellipse([(tx - r, ty - r), (tx + r, ty + r)], outline=(255, 40, 40), width=4)
    draw.text((tx + r + 4, ty - 10), f"({target_pt[0]:.3f}, {target_pt[1]:.3f})",
              fill=(255, 40, 40))

    img.save(output_path)
    print(f"Path overlay saved: {output_path}  target=({target_pt[0]:.3f},{target_pt[1]:.3f})")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Visible magic position finder")
    parser.add_argument("--debug-image", metavar="PATH",
                        help="Generate debug grid image from this clip/still")
    parser.add_argument("--detect", metavar="PATH",
                        help="Detect target + draw path overlay for this clip/still")
    parser.add_argument("--target-hint", default="",
                        help="Kim's plain-English description of target object")
    parser.add_argument("--output", required=False, default="/tmp/magic_debug.png",
                        help="Output PNG path")
    parser.add_argument("--sha", metavar="PATH",
                        help="Compute frame SHA for KNOWN_SCENES validation")
    args = parser.parse_args()

    if args.sha:
        sha = compute_frame_sha(args.sha)
        print(f"Frame SHA: {sha}")
        return

    if args.debug_image:
        frame = load_frame(args.debug_image)
        generate_debug_image(frame, args.output)

    if args.detect:
        frame = load_frame(args.detect)
        cx, cy = detect_by_color(frame, args.target_hint)
        path = [(0.0, cy + 0.05), (cx * 0.5, cy + 0.02), (cx, cy)]
        draw_path_overlay(frame, path, (cx, cy), args.output)
        print(f"Detected center: ({cx:.3f}, {cy:.3f})")


if __name__ == "__main__":
    main()
