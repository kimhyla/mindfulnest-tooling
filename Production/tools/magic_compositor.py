"""
MagicCompositor — reusable traveling-magic-trail compositor
Production/tools/magic_compositor.py

Enshrines the approved v6 "sparkle river" approach for ALL future resolution scenes.

APPROVED APPROACH (Kim approved 2026-04-22):
  - Pre-placed particles with fixed seeds → no jerk, no pop
  - 1–3px crisp sparkle dots, NO gradient ellipses → ephemeral not solid
  - Strong y-scatter compression (3.2% of path width) → flat on stone floor
  - Anisotropic ambient blur [sigma_y=2.5, sigma_x=18] → floor-pool glow
  - Additive composite → visible on bright daytime backgrounds
  - Auto-brightness calibration → adapts to any background luminosity

USAGE:
    from magic_compositor import MagicCompositor

    mc = MagicCompositor(
        background_path="/path/to/still.png",
        path_pts=[(0.01, 0.745), (0.18, 0.755), (0.35, 0.735), (0.47, 0.670)],
        style="tessa_ori",
        duration=3.5,
        fps=24,
    )
    preview_path = mc.render_preview()   # fast single-frame check
    video_path   = mc.render_video()     # full render

    # Or use the convenience factory:
    from magic_compositor import make_event1_resolution
    make_event1_resolution(preview_only=True)

ADDING A NEW STYLE:
    Add an entry to STYLES dict below. Lock as Directus LD once Kim approves.
    Key: MAGIC_STYLE_{NAME}_V{N}

PATH GEOMETRY — Event 1 Heartwood (locked):
    (0.47, 0.670) = altar STEP EDGE. Never go above 0.670 or magic floats above floor.

COST: Zero API calls. Pure local Python/PIL/numpy/scipy.
"""

import json as _json_mod
import math, os, random, time
import platform as _platform
import sys as _sys
from pathlib import Path as _Path
import numpy as np
from scipy.ndimage import gaussian_filter

# Cross-platform PROJECT_ROOT resolution (per LD-367, mirrors docx_confirmation_hook.py).
_PROJECT_ROOT_ENV = os.environ.get('MINDFULNEST_PROJECT_ROOT')
if _PROJECT_ROOT_ENV:
    _PROJECT_ROOT = _PROJECT_ROOT_ENV
elif _platform.system() == 'Windows':
    _PROJECT_ROOT = r"C:\Users\ECDS Clinical\Dropbox\Claude Mindfulnest Project Files"
else:
    _PROJECT_ROOT = "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

# LD-421 wrapper import — required by Compliance Gate Check 6.
# All output writes must be paired with registered_write.register_asset().
try:
    from Production.tools import registered_write as _rw
except ImportError:
    _rw = None  # Fallback: skip registration (CLI/standalone smoke tests)

try:
    from PIL import Image
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "-q"])
    from PIL import Image

try:
    import imageio.v3 as iio
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "imageio[ffmpeg]", "-q"])
    import imageio.v3 as iio


# ── Approved style registry ────────────────────────────────────────────────
# Status "approved" = Kim has seen and approved a preview rendered with these params.
# Status "draft"    = not yet approved; do not use in production pipeline.
# Once approved, lock as Directus LD with key MAGIC_STYLE_{NAME}_V{N}.

from magic_render_contract import (
    BRIGHT_STONE_AMB_BLUR_YX,
    BRIGHT_STONE_AMB_GAIN_MULT,
    BRIGHT_STONE_AMB_MIX,
    BRIGHT_STONE_LUM_THRESHOLD,
    bright_stone_ambient_from_lums,
    mixed_path_sparkle_guard_from_lums,
    sparkle_strength_for_bg_lum,
)


def composite_screen_rgb(bg_arr: np.ndarray, trail: np.ndarray) -> np.ndarray:
    """LD-469 RGB screen composite — magic shines through without additive clip on bright stone."""
    bg = bg_arr.astype(np.float32)
    return np.clip(255.0 - (255.0 - bg) * (255.0 - trail) / 255.0, 0, 255).astype(np.uint8)


STYLES = {
    "tessa_ori": {
        # Palette: golden-white Ori spirit-light (same as composite_magic_overlay.py v4)
        "palette": [
            (255, 255, 238),   # ORI_CORE   — near-white warm
            (255, 252, 200),   # ORI_BRIGHT — pale cream-white
            (255, 240, 155),   # ORI_MID    — soft pale gold
        ],
        "palette_weights": [3, 2, 1],

        "n_particles": 1800,

        # Floor-flat geometry
        "scatter_x_frac": 0.40,   # x spread: 40% of path width
        "scatter_y_frac": 0.032,  # y spread: 3.2% — nearly 2D flat on ground

        "dot_sizes": [1, 1, 1, 2, 2, 3],  # mostly 1px crisp dots

        "bright_range": (0.35, 1.0),
        "twinkle_range": (0.06, 0.22),
        "fade_tail": 0.72,  # tail fades to 28% of head brightness

        # Brightness — sparkle_gain * gain_multiplier = per-hit pixel value
        "sparkle_gain": 210.0,
        "ambient_gain": 30.0,
        "ambient_blur_yx": [2.5, 18.0],  # very wide x, narrow y → floor pool
        "sparkle_blur": 0.7,
        "ambient_mix": 2.2,

        "blend": "additive",  # additive visible on bright daytime bg; switch to "screen" for dark

        "status": "approved",      # Kim approved 2026-04-22 (v6 preview)
        "directus_ld": None,       # TODO: set after Kim locks it
    },

    "wide_ori": {
        # Same palette + SAME crisp 1-3px sparkle dots as tessa_ori (approved process).
        # Difference: scatter_y_frac raised to 0.22 → wider beam, not floor-flat.
        # More particles to fill the wider band without looking blobby.
        "palette": [
            (255, 255, 238),   # ORI_CORE
            (255, 252, 200),   # ORI_BRIGHT
            (255, 240, 155),   # ORI_MID
        ],
        "palette_weights": [3, 2, 1],

        "n_particles": 5000,

        "scatter_x_frac": 0.40,
        "scatter_y_frac": 0.50,   # 50% — wide sparkle river vs 3.2% floor-flat

        "dot_sizes": [1, 1, 1, 2, 2, 3],   # APPROVED: 1-3px crisp sparkle dots only

        "bright_range": (0.40, 1.0),
        "twinkle_range": (0.06, 0.22),
        "fade_tail": 0.70,

        "sparkle_gain": 260.0,
        "ambient_gain": 48.0,
        "ambient_blur_yx": [8.0, 32.0],   # wider than tessa_ori [2.5, 18] but not a blob
        "sparkle_blur": 0.9,
        "ambient_mix": 2.6,

        "blend": "additive",   # additive = visible on bright backgrounds

        "status": "approved",      # Kim approved for runestone/nest orbital paths (Event 1 res beat 2+)
        "directus_ld": None,
    },
}


class MagicCompositor:
    """
    Renders an animated magic trail composited onto a still background.

    All randomness is seeded deterministically. Particles are pre-placed at
    init time — render_preview() and render_video() always produce consistent
    output for the same inputs.
    """

    def __init__(
        self,
        background_path: str,
        path_pts: list,
        style: str = "tessa_ori",
        duration: float = 3.5,
        fps: int = 24,
        seed: int = 99,
        output_dir: str = None,
        label: str = None,
        # LD-421 registration metadata (optional — when set, render_* will register).
        module_id: int = None,
        event_id: int = None,
        beat_id: str = None,
        parent_asset_id: int = None,
        tags: list = None,
        scene_key: str = None,
        path_authored_against: dict = None,
        path_interp: str = "polyline",
    ):
        if style not in STYLES:
            raise ValueError(f"Unknown style '{style}'. Available: {list(STYLES)}")

        if path_interp not in ("polyline", "bezier"):
            raise ValueError(f"path_interp must be 'polyline' or 'bezier', got {path_interp!r}")

        self.bg_path  = background_path
        self.path_pts = path_pts
        self.path_interp = path_interp
        self.style    = style
        self.s        = STYLES[style]
        self.duration = duration
        self.fps      = fps
        self.seed     = seed
        self.n_frames = int(fps * duration)
        self._path_authored_against = path_authored_against

        # LD-421 registration metadata
        self.module_id = module_id
        self.event_id = event_id
        self.beat_id = beat_id
        self.parent_asset_id = parent_asset_id
        self.tags = list(tags) if tags else ["magic", "compositor", style]
        self.scene_key = scene_key

        self.output_dir = output_dir or os.path.dirname(background_path)
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        # Security (CodeQL py/path-injection alert #10): label flows into
        # default output_path via f"magic_{self.label}.mp4" / f"preview_{self.label}.png".
        # When label is attacker-controlled (e.g. flows from beat_id over HTTP),
        # an unsanitized label like '../../etc/x' lets the resulting output_path
        # escape self.output_dir. Sanitize at construction-time: strip path
        # separators and traversal sequences before assignment.
        import re as _re
        _raw_label = label or f"{style}_{ts}"
        _sanitized_label = _re.sub(r"[/\\]", "_", _raw_label).replace("..", "_")
        # Defensive: if anything else weird remains (null bytes, control chars),
        # fall back to a deterministic safe label.
        if "\x00" in _sanitized_label or not _sanitized_label.strip():
            _sanitized_label = f"{style}_{ts}"
        self.label = _sanitized_label

        print(f"Loading background: {os.path.basename(background_path)}", flush=True)
        self.bg_img = Image.open(background_path).convert("RGB")
        _orig_w, _orig_h = self.bg_img.size
        # libx264 in yuv420p (the default for codec="h264") requires both
        # width AND height to be EVEN — chroma subsampling math. Odd-dim
        # inputs explode with avcodec_open2("libx264", {}) ExternalError 542398533.
        # Crop 1 px off the right/bottom if needed; visually imperceptible
        # vs the alternative (silent black-square preview from a 500 error).
        # Failure mode observed 2026-05-20 on still_3_body_stone_glow_v9.png (1677x938)
        # and on 22 of 36 generator crops.
        if _orig_w % 2 or _orig_h % 2:
            _new_w = _orig_w - (_orig_w % 2)
            _new_h = _orig_h - (_orig_h % 2)
            self.bg_img = self.bg_img.crop((0, 0, _new_w, _new_h))
            print(f"  cropped odd dims {_orig_w}x{_orig_h} -> {_new_w}x{_new_h} (libx264 even-dim requirement)", flush=True)
        self.W, self.H = self.bg_img.size
        print(f"  {self.W}x{self.H}", flush=True)

        self.path_pts = self._aspect_correct(self.path_pts, self._path_authored_against)

        self._path_bg_lum = 0.0
        self._bg_lum_sample: np.ndarray | None = np.array(self.bg_img).astype(np.float32)
        self._gain = self._calibrate_brightness()
        self._particles = self._build_particles()
        print(f"  {len(self._particles)} particles placed (seed={seed})", flush=True)

    def _build_iteration_notes(self, kind: str) -> str:
        """Production-time iteration_notes per LD-421 spec §9.1 table."""
        s = self.s
        path_str = ",".join(f"({p[0]:.3f},{p[1]:.3f})" for p in self.path_pts)
        return (
            f"kind={kind}, style={self.style}, n_particles={s['n_particles']}, "
            f"palette_weights={s['palette_weights']}, "
            f"path_pts=[{path_str}], duration={self.duration}s, fps={self.fps}, "
            f"seed={self.seed}, blend={s['blend']}, gain_mult={self._gain:.2f}, "
            f"scene_key={self.scene_key or 'unspecified'}, bg={os.path.basename(self.bg_path)}"
        )

    def _maybe_register(self, output_path: str, asset_type: str, kind: str) -> int:
        """Register output via LD-421 wrapper if module_id is set and wrapper is available."""
        if _rw is None:
            print(f"  [LD-421] registered_write unavailable — skipping registration", flush=True)
            return -1
        if self.module_id is None:
            print(f"  [LD-421] module_id not set — skipping registration "
                  f"(pass module_id=... to MagicCompositor() to enable)", flush=True)
            return -1
        try:
            asset_id, _ = _rw.register_asset(
                file_path=output_path,
                asset_type=asset_type,
                module_id=self.module_id,
                event_id=self.event_id,
                beat_id=self.beat_id,
                parent_asset_id=self.parent_asset_id,
                produced_by_skill='visible-magic',
                iteration_notes=self._build_iteration_notes(kind),
                colloquial_name=self.scene_key or self.label,
                tags=self.tags,
                notes=f"MagicCompositor {kind} render via visible-magic skill",
            )
            print(f"  [LD-421] registered asset_id={asset_id} ({asset_type})", flush=True)
            return asset_id
        except Exception as e:
            print(f"  [LD-421] registration failed: {e}", flush=True)
            return -1

    # ── Public API ─────────────────────────────────────────────────────────

    def render_preview(self, frame_idx: int = 55, output_path: str = None) -> str:
        """Render single preview frame (~2s). Returns path. Registers via LD-421 wrapper if module_id set."""
        if output_path is None:
            output_path = os.path.join(self.output_dir, f"preview_{self.label}.png")
        trail = self._make_trail(frame_idx)
        comp  = self._composite(trail)
        comp.save(output_path)
        print(f"Preview saved: {output_path}", flush=True)
        # LD-421 — register composited preview still (asset_type='composite')
        self._maybe_register(output_path, asset_type='composite', kind='preview')
        return output_path

    def render_video(self, output_path: str = None, black_bg: bool = False) -> str:
        """Render full video. Returns path. Registers via LD-421 wrapper if module_id set.

        Per LD-469 MAGIC_TRAIL_ON_VIDEO_V1 (S5 v3.1):
        ``black_bg=True`` renders the magic onto a solid-black canvas of the
        same dimensions as the original background, forcing gain to 1.0 (full
        brightness — no luminosity-based attenuation). The output is then
        intended for ffmpeg ``blend=all_mode=screen`` overlay onto a source
        video: black pixels become transparent, magic pixels shine through.

        ``black_bg=False`` (default) is the legacy behavior — composites
        magic onto ``self.bg_img`` (the watercolor / still / scene bg).
        """
        if output_path is None:
            output_path = os.path.join(self.output_dir, f"magic_{self.label}.mp4")

        # If black_bg, swap bg_img + gain for the render then restore.
        saved_bg = self.bg_img
        saved_gain = self._gain
        try:
            if black_bg:
                self.bg_img = Image.new("RGB", (self.W, self.H), (0, 0, 0))
                self._gain = 1.0
                print(f"Rendering {self.n_frames} frames (black_bg=True, gain=1.0)...", flush=True)
            else:
                print(f"Rendering {self.n_frames} frames...", flush=True)
            frames = []
            for i in range(self.n_frames):
                trail = self._make_trail(i)
                frames.append(np.array(self._composite(trail)))
                if i % 12 == 0:
                    t = i / (self.n_frames - 1) if self.n_frames > 1 else 0
                    print(f"  frame {i}/{self.n_frames}  t={t:.2f}", flush=True)
            print("Writing video...", flush=True)
            iio.imwrite(output_path, frames, plugin="pyav", codec="h264", fps=self.fps)
            print(f"Done → {output_path}  ({os.path.getsize(output_path):,} bytes)", flush=True)
        finally:
            # Restore so a subsequent call without black_bg still works on bg_img.
            self.bg_img = saved_bg
            self._gain = saved_gain
        # LD-421 — register magic clip (asset_type='magic_clip')
        self._maybe_register(output_path, asset_type='magic_clip', kind='video')
        return output_path

    def render_ld469_on_background(self, output_path=None) -> str:
        """LD-469 on still/image: trail at gain=1.0, RGB screen onto self.bg_img.

        Same trail + composite contract as handle_magic_video (not legacy additive).
        """
        if output_path is None:
            output_path = os.path.join(self.output_dir, f"magic_{self.label}.mp4")
        bg_arr = np.array(self.bg_img.convert("RGB")).astype(np.float32)
        saved_gain = self._gain
        self._gain = 1.0
        print(
            f"Rendering {self.n_frames} LD-469 frames (gain=1.0, screen_rgb, path_interp={self.path_interp})...",
            flush=True,
        )
        try:
            frames = []
            for i in range(self.n_frames):
                trail = self._make_trail(i)
                frames.append(composite_screen_rgb(bg_arr, trail))
                if i % 12 == 0:
                    t = i / (self.n_frames - 1) if self.n_frames > 1 else 0
                    print(f"  frame {i}/{self.n_frames}  t={t:.2f}", flush=True)
            print("Writing video...", flush=True)
            iio.imwrite(output_path, frames, plugin="pyav", codec="h264", fps=self.fps)
            print(f"Done → {output_path}  ({os.path.getsize(output_path):,} bytes)", flush=True)
        finally:
            self._gain = saved_gain
        self._maybe_register(output_path, asset_type='magic_clip', kind='video')
        return output_path

    # ── Internal ────────────────────────────────────────────────────────────

    def _sample_path_luminance(self, bg_source) -> float:
        """Average Rec.601 luminance along path on PIL image or float32 (H,W,3) array."""
        lums = []
        for i in range(20):
            t = i / 19
            fx, fy = self._path_at(t)
            px = min(self.W - 1, max(0, int(fx * self.W)))
            py = min(self.H - 1, max(0, int(fy * self.H)))
            if isinstance(bg_source, np.ndarray):
                r, g, b = bg_source[py, px]
            else:
                r, g, b = bg_source.getpixel((px, py))
            lums.append(0.299 * r + 0.587 * g + 0.114 * b)
        return float(np.mean(lums))

    def set_path_luminance_from_array(self, bg_arr: np.ndarray) -> None:
        """Update path luminance from a decoded video frame (magic_video uses black ref at init)."""
        self._bg_lum_sample = bg_arr.astype(np.float32)
        lums = []
        for i in range(20):
            t = i / 19
            fx, fy = self._path_at(t)
            px = min(self.W - 1, max(0, int(fx * self.W)))
            py = min(self.H - 1, max(0, int(fy * self.H)))
            r, g, b = self._bg_lum_sample[py, px]
            lums.append(0.299 * r + 0.587 * g + 0.114 * b)
        self._path_bg_lum = float(np.mean(lums))
        bright_frac = sum(1 for x in lums if x > BRIGHT_STONE_LUM_THRESHOLD) / len(lums)
        mode = "bright_stone" if bright_stone_ambient_from_lums(lums) else "standard"
        print(
            f"  Path bg luminosity (video frame): mean={self._path_bg_lum:.0f}/255 "
            f"bright_frac={bright_frac:.2f} → {mode}",
            flush=True,
        )

    def _pixel_luminance(self, px: int, py: int) -> float:
        if self._bg_lum_sample is None:
            return 0.0
        r, g, b = self._bg_lum_sample[py, px]
        return 0.299 * r + 0.587 * g + 0.114 * b

    def _bright_stone_ambient(self) -> bool:
        """Widen ambient pool when a meaningful share of the path crosses bright stone."""
        if self._bg_lum_sample is None:
            return False
        lums = []
        for i in range(20):
            t = i / 19
            fx, fy = self._path_at(t)
            px = min(self.W - 1, max(0, int(fx * self.W)))
            py = min(self.H - 1, max(0, int(fy * self.H)))
            lums.append(self._pixel_luminance(px, py))
        return bright_stone_ambient_from_lums(lums)

    def _mixed_path_sparkle_guard(self) -> bool:
        if self._bg_lum_sample is None:
            return False
        lums = []
        for i in range(20):
            t = i / 19
            fx, fy = self._path_at(t)
            px = min(self.W - 1, max(0, int(fx * self.W)))
            py = min(self.H - 1, max(0, int(fy * self.H)))
            lums.append(self._pixel_luminance(px, py))
        return mixed_path_sparkle_guard_from_lums(lums)

    def _calibrate_brightness(self) -> float:
        """
        Sample background luminosity along path. Return gain multiplier so
        magic reads on both dark and bright backgrounds.
        Dark bg (lum~50) → ~0.85x  (magic shows easily, no boost needed)
        Bright bg (lum~180) → ~1.55x (needs extra push to show on stone floor)
        """
        avg = self._sample_path_luminance(self.bg_img)
        self._path_bg_lum = avg
        mult = float(np.clip(0.7 + (avg / 128.0) * 0.6, 0.5, 2.0))
        print(f"  Path bg luminosity: {avg:.0f}/255 → gain multiplier {mult:.2f}", flush=True)
        return mult

    def _build_particles(self) -> list:
        """Pre-place all particles. Positions never change between frames."""
        s   = self.s
        rng = random.Random(self.seed)
        pool = []
        for color, w in zip(s["palette"], s["palette_weights"]):
            pool.extend([color] * w)

        pts = []
        for _ in range(s["n_particles"]):
            blo, bhi = s["bright_range"]
            tlo, thi = s["twinkle_range"]
            pts.append((
                rng.random(),                      # ts: position along path
                rng.gauss(0, 1.0),                 # sx_norm
                rng.gauss(0, 1.0),                 # sy_norm
                rng.uniform(0, 2*math.pi),         # twinkle_phase
                rng.uniform(tlo, thi),             # twinkle_speed
                rng.uniform(blo, bhi),             # bright_max
                rng.choice(s["dot_sizes"]),        # dot_size
                rng.choice(pool),                  # color
            ))
        pts.sort(key=lambda p: p[0])  # sorted by ts for early-exit
        return pts

    def _make_trail(self, frame_idx: int) -> np.ndarray:
        """Render trail layer as float32 numpy array (H, W, 3)."""
        s      = self.s
        W, H   = self.W, self.H
        t_head = frame_idx / (self.n_frames - 1) if self.n_frames > 1 else 0.0
        if t_head <= 0:
            return np.zeros((H, W, 3), dtype=np.float32)

        g = self._gain
        bright_ambient = self._bright_stone_ambient()
        mixed_guard = self._mixed_path_sparkle_guard()
        amb_blur_yx = list(BRIGHT_STONE_AMB_BLUR_YX) if bright_ambient else s["ambient_blur_yx"]
        amb_mix = BRIGHT_STONE_AMB_MIX if bright_ambient else s["ambient_mix"]
        amb_gain_mult = BRIGHT_STONE_AMB_GAIN_MULT if bright_ambient else 1.0
        if mixed_guard and not bright_ambient:
            # Softer ambient pool on mixed paths (character + ground) — less harsh on fur.
            amb_blur_yx = list(BRIGHT_STONE_AMB_BLUR_YX)
            amb_mix = max(s["ambient_mix"], BRIGHT_STONE_AMB_MIX * 0.55)
            amb_gain_mult = max(1.0, BRIGHT_STONE_AMB_GAIN_MULT * 0.75)
        # Full bright-stone OR mixed face/stone crossings: ambient river only, no sparkle dots.
        suppress_all_sparkle = bright_ambient or mixed_guard

        sp_acc  = np.zeros((H, W, 3), dtype=np.float32)
        amb_acc = np.zeros((H, W, 3), dtype=np.float32)

        for (ts, sx_n, sy_n, tw_ph, tw_sp, bmax, dsz, col) in self._particles:
            if ts > t_head:
                break
            age     = (t_head - ts) / max(t_head, 1e-6)
            fade    = 1.0 - age * s["fade_tail"]
            twinkle = 0.35 + 0.65 * math.sin(frame_idx * tw_sp + tw_ph)
            alpha   = bmax * fade * twinkle
            if alpha < 0.04:
                continue

            fx, fy = self._path_at(ts)
            pw     = self._path_width(fy)
            px     = int(fx * W + sx_n * pw * s["scatter_x_frac"])
            py     = int(fy * H + sy_n * pw * s["scatter_y_frac"])
            if not (0 <= px < W and 0 <= py < H):
                continue

            if not suppress_all_sparkle:
                px_lum = self._pixel_luminance(px, py)
                sparkle_scale = sparkle_strength_for_bg_lum(
                    px_lum,
                    bright_stone_mode=False,
                )
                if sparkle_scale > 0.01:
                    val = alpha * s["sparkle_gain"] * g * sparkle_scale
                    r   = dsz
                    y0, y1 = max(0, py-r), min(H, py+r+1)
                    x0, x1 = max(0, px-r), min(W, px+r+1)
                    for c in range(3):
                        sp_acc[y0:y1, x0:x1, c] += col[c] * val / 255.0

            av = alpha * s["ambient_gain"] * g * amb_gain_mult
            if bright_ambient or mixed_guard:
                px_lum = self._pixel_luminance(px, py)
                if px_lum > BRIGHT_STONE_LUM_THRESHOLD:
                    amb_scale = max(0.0, min(1.0, (170.0 - px_lum) / 40.0))
                    av *= amb_scale
            for c in range(3):
                amb_acc[py, px, c] += col[c] * av / 255.0

        if suppress_all_sparkle:
            sp_bl = np.zeros((H, W, 3), dtype=np.float32)
        else:
            sp_bl = gaussian_filter(sp_acc, sigma=[s["sparkle_blur"], s["sparkle_blur"], 0])
        sy, sx = amb_blur_yx
        for c in range(3):
            amb_acc[:, :, c] = gaussian_filter(amb_acc[:, :, c], sigma=[sy, sx])

        return np.clip(sp_bl + amb_acc * amb_mix, 0, 255)

    def _composite(self, trail: np.ndarray) -> Image.Image:
        bg = np.array(self.bg_img).astype(np.float32)
        if self.s["blend"] == "additive":
            result = np.clip(bg + trail, 0, 255).astype(np.uint8)
        elif self.s["blend"] == "screen":
            result = np.clip(255 - (255 - bg) * (255 - trail) / 255, 0, 255).astype(np.uint8)
        else:
            raise ValueError(f"Unknown blend: {self.s['blend']}")
        return Image.fromarray(result)

    def _path_at(self, t: float) -> tuple:
        if self.path_interp == "bezier":
            return self._bezier(t)
        return self._polyline(t)

    def _polyline(self, t: float) -> tuple:
        """Walk path_pts in order with straight segments (matches path_picker lineTo)."""
        pts = self.path_pts
        if not pts:
            return (0.0, 0.0)
        if len(pts) == 1:
            return pts[0]
        t = max(0.0, min(1.0, float(t)))
        n_seg = len(pts) - 1
        pos = t * n_seg
        idx = min(int(pos), n_seg - 1)
        local = pos - idx
        x0, y0 = pts[idx]
        x1, y1 = pts[idx + 1]
        return (x0 + (x1 - x0) * local, y0 + (y1 - y0) * local)

    def _bezier(self, t: float) -> tuple:
        p = list(self.path_pts)
        while len(p) > 1:
            p = [(p[i][0]*(1-t)+p[i+1][0]*t,
                  p[i][1]*(1-t)+p[i+1][1]*t) for i in range(len(p)-1)]
        return p[0]

    def _aspect_correct(self, path_pts, authored):
        """Remap path_pts when draw-surface dims differ from compositor canvas."""
        if not authored or "width" not in authored or "height" not in authored:
            return path_pts
        pw = int(float(authored.get("width", 0)))
        ph = int(float(authored.get("height", 0)))
        if pw <= 0 or ph <= 0:
            return path_pts
        pw = pw - (pw % 2)
        ph = ph - (ph % 2)
        if pw == self.W and ph == self.H:
            return path_pts
        corrected = []
        for (fx, fy) in path_pts:
            px = fx * pw
            py = fy * ph
            corrected.append((px / self.W, py / self.H))
        print(
            f"  [aspect_correct] authored {pw}x{ph} -> compositor {self.W}x{self.H}: "
            f"remapped {len(corrected)} pts",
            flush=True,
        )
        return corrected

    def _path_width(self, y_frac: float) -> int:
        y_near = max(p[1] for p in self.path_pts)
        y_far  = min(p[1] for p in self.path_pts)
        t = max(0.0, min(1.0, (y_frac - y_far) / max(y_near - y_far, 1e-6)))
        return max(10, int(self.W * (t * 0.055 + 0.015)))


# ── Pre-configured scene geometry (locked) ────────────────────────────────

def _dropbox():
    """Resolve project root cross-platform. Prefers MINDFULNEST_PROJECT_ROOT env var,
    falls back to platform default per LD-367 (mirrors docx_confirmation_hook.py)."""
    return _PROJECT_ROOT


# scene_registry.yaml uses string IDs like "m1", "e1" — map to Directus integer FKs.
# prod_modules FK mapping: id 3 = M4 Ember, id 5 = M3 Benson (table is NOT in M-number order).
_SCENE_M_TO_MODULE_ID = {
    "m1": 1,  # Tessa
    "m2": 2,  # Luna
    "m3": 5,  # Benson
    "m4": 3,  # Ember
    "m5": 6,  # Bork
    "m6": 4,  # Bramble
}


def _scene_to_ids(scene: dict) -> tuple:
    """Map scene_registry.yaml string IDs to (module_id:int, event_id:int).
    Returns (None, None) if mapping fails — caller should skip registration."""
    m_str = (scene.get("module_id") or "").lower()
    e_str = (scene.get("event_id") or "").lower()
    module_id = _SCENE_M_TO_MODULE_ID.get(m_str)
    event_id = None
    if e_str.startswith("e"):
        try:
            event_id = int(e_str[1:])
        except ValueError:
            event_id = None
    return module_id, event_id


# Event 1 Heartwood resolution — path geometry locked 2026-04-22
# (0.47, 0.670) = altar STEP EDGE. (0.51, 0.60) was altar top = floats above floor.
EVENT1_HEARTWOOD_PATH = [
    # Confirmed via path_picker.html 2026-04-24 (Kim-approved v6).
    # Origin: left stone tile floor (y≈0.79 foreground).
    # Target: altar outer step edge (y≈0.73).
    (0.000, 0.790),
    (0.133, 0.775),
    (0.267, 0.760),
    (0.400, 0.730),
]


def render_magic(scene_key: str, bg_still: str = None, preview_only: bool = False,
                 output_dir: str = None, seed: int = 99) -> dict:
    """
    Primary entry point for the magic-path-picker skill.

    Reads manual_path from scene_registry.yaml, renders preview + optional video.
    Returns dict with keys: preview_path, video_path (None if preview_only).

    Usage:
        from magic_compositor import render_magic
        result = render_magic("m1_e1_res_beat_01_heartwood", preview_only=True)
        print(result["preview_path"])
    """
    import yaml as _yaml
    # LD-505 Phase C: anchor scene_registry.yaml on the runtime DROPBOX_ROOT
    # via lib/paths (env-aware: MN_DROPBOX_ROOT first, then platform default).
    # Was `_Path(__file__).parent / ...` which resolved to the tooling tree.
    # CODE tree — finding Production/lib/paths.py (sibling Python module).
    import sys as _sys, os as _os
    _lib_parent = _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
    if _lib_parent not in _sys.path:
        _sys.path.insert(0, _lib_parent)
    from Production.lib.paths import DROPBOX_ROOT as _DR
    reg_path = _DR / "Production" / "tools" / "scene_registry.yaml"
    registry = _yaml.safe_load(reg_path.read_text()) or {}
    scene = registry.get(scene_key)
    if scene is None:
        raise ValueError(
            f"Scene key '{scene_key}' not found in scene_registry.yaml. "
            f"Run the magic-path-picker skill to register it first."
        )

    # Resolve path_pts — manual_path takes absolute priority
    if scene.get("manual_path"):
        path_pts = [tuple(float(v) for v in pt) for pt in scene["manual_path"]]
    else:
        raise ValueError(
            f"Scene '{scene_key}' has no manual_path. "
            f"Run the magic-path-picker skill (path_picker.html) to set one first."
        )

    style = scene.get("style", "tessa_ori")

    # Resolve background still
    if bg_still is None:
        db = _dropbox()
        # Try to resolve from well-known locations
        candidates = [
            os.path.join(db, "Production", "Event_1", "resolution_stills",
                         "heartwood_3q_left_1456.png"),
        ]
        for c in candidates:
            if os.path.exists(c):
                bg_still = c
                break
        if bg_still is None:
            raise ValueError(
                "bg_still not provided and could not be auto-resolved. "
                "Pass bg_still='/path/to/background.png' explicitly."
            )

    out_dir = output_dir or os.path.join(os.path.dirname(bg_still), "..", "kling_clips")
    out_dir = os.path.normpath(out_dir)

    # LD-421 — map scene_registry string IDs to Directus integer FKs for registration
    module_id, event_id = _scene_to_ids(scene)
    beat_id = scene.get("beat")  # e.g. "res_beat_01"

    mc = MagicCompositor(
        background_path=bg_still,
        path_pts=path_pts,
        style=style,
        duration=3.5,
        fps=24,
        seed=seed,
        output_dir=out_dir,
        label=f"{scene_key}_approved",
        module_id=module_id,
        event_id=event_id,
        beat_id=beat_id,
        scene_key=scene_key,
        tags=["magic", "compositor", style, scene_key],
    )

    total_frames = int(mc.duration * mc.fps)
    preview_path = mc.render_preview(frame_idx=total_frames - 2)

    video_path = None
    if not preview_only:
        video_path = mc.render_video()

    return {"preview_path": preview_path, "video_path": video_path}


# Event 1 Body Stone (runestone) — magic arrives from left, lands on orange stone
# Orange stone (Body Stone) is at upper-left of basket, center ~(0.26, 0.41).
# Path enters from left edge, curves upward to terminate on the stone.
EVENT1_RUNESTONE_BODY_PATH = [
    (0.00, 0.65),   # enter from left edge at mid-basket height
    (0.08, 0.58),   # curving upward
    (0.18, 0.51),   # rising into basket
    (0.28, 0.46),   # approaching stone
    (0.36, 0.44),   # orange Body Stone center (pixel-verified: 608,413 / 1677x938)
]

# Tessa exit-right trail — starts at foot position, exits bottom-right
# Approved 2026-04-23 in beat01_tessa_exit_stitched_v1.mp4
EVENT1_TESSA_EXIT_PATH = [
    (0.52, 0.968),
    (0.62, 0.972),
    (0.74, 0.982),
    (0.86, 0.995),
    (0.96, 1.010),
    (1.04, 1.025),
]

# Heartwood wide clearing trail — enters left, crosses mid-height, exits right
# Approved 2026-04-23 in beat02_heartwood_magic_v1.mp4
EVENT1_HEARTWOOD_WIDE_PATH = [
    (-0.05, 0.60),
    ( 0.15, 0.58),
    ( 0.35, 0.57),
    ( 0.55, 0.58),
    ( 0.75, 0.60),
    ( 1.05, 0.62),
]


# ── Known scenes registry ─────────────────────────────────────────────────
# Pre-calibrated path geometries for approved scenes.
# source_frame_sha: sha256[:16] of frame 0 of source clip at calibration time.
# None = not yet computed; set on first use via magic_position_finder.py --sha.
# When the skill loads a known scene, it verifies the incoming clip's SHA matches
# before trusting stored geometry — detects if the source was re-rendered.

KNOWN_SCENES = {
    "tessa_exit_right": {
        "style": "tessa_ori",
        "path": EVENT1_TESSA_EXIT_PATH,
        "source_clip": "beat01_tessa_exit_stitched_v1.mp4",
        "source_frame_sha": None,
        "timing": {"T_TRAIL_COMPLETE": 0.70, "T_FADEOUT_START": 0.75, "T_FADEOUT_END": 1.00},
    },
    "heartwood_wide_trail": {
        "style": "wide_ori",
        "path": EVENT1_HEARTWOOD_WIDE_PATH,
        "source_clip": "beat02_heartwood_animated_v1.mp4",
        "source_frame_sha": None,
        "timing": {"T_TRAIL_COMPLETE": 0.70, "T_FADEOUT_START": 0.75, "T_FADEOUT_END": 1.00},
    },
    "runestone_activation_burst": {
        "style": "burst",
        "path_center": (0.29, 0.22),
        "source_clip": "beat02_runestone_activation_v1.mp4",
        "source_frame_sha": None,
        "timing": {"BURST_PEAK_FRAMES": 6, "BURST_FADE_FRAMES": 30},
    },
    "heartwood_resolution_3q": {
        "style": "tessa_ori",
        "path": EVENT1_HEARTWOOD_PATH,
        "source_clip": "heartwood_3q_left_1456.png",
        "source_frame_sha": None,
        "timing": {"T_TRAIL_COMPLETE": 0.70, "T_FADEOUT_START": 0.75, "T_FADEOUT_END": 1.00},
    },
}


# ── Stitch enforcement gate ───────────────────────────────────────────────

import json as _json_mod
from pathlib import Path as _Path


def resolve_stitch_clips(clip_list: list, registry_path: str) -> list:
    """
    Stitch enforcement gate. For each clip in clip_list, checks
    magic_clip_registry.json for a status="approved" magic version.
    Substitutes approved magic clip for base clip. Never substitutes "pending".

    Usage (before any ffmpeg concat or imageio stitch):
        from magic_compositor import resolve_stitch_clips
        clips = resolve_stitch_clips(input_clips, "Production/tools/magic_clip_registry.json")
    """
    reg_path = _Path(registry_path)
    if not reg_path.exists():
        print(f"[stitch-gate] No registry at {registry_path} — using clips as-is")
        return list(clip_list)

    registry = _json_mod.loads(reg_path.read_text())
    lookup = {}
    for entry in registry:
        if entry.get("status") == "approved" and entry.get("source_clip"):
            src_base = _Path(entry["source_clip"]).name
            lookup[src_base] = entry["magic_clip"]

    result = []
    for clip in clip_list:
        base = _Path(clip).name
        if base in lookup:
            magic_name = lookup[base]
            magic_path = _Path(clip).parent / magic_name
            if magic_path.exists():
                print(f"[stitch-gate] SUBSTITUTED {base} → {magic_name}")
                result.append(str(magic_path))
            else:
                print(f"[stitch-gate] WARNING: magic clip {magic_name} not found — using base")
                result.append(clip)
        else:
            print(f"[stitch-gate] No approved magic for {base} — using base")
            result.append(clip)
    return result


def get_preview_frame_idx(n_frames: int, T_TRAIL_COMPLETE: float = 0.70) -> int:
    """Return frame index where the trail first reaches full completion."""
    return min(int(T_TRAIL_COMPLETE * n_frames), n_frames - 1)


def make_event1_runestone(output_dir=None, preview_only=False, seed=42):
    """
    Factory for Event 1 Body Stone (orange runestone) magic arrival trail.
    Uses wide_ori style — wide beam, not floor-flat.
    Quick usage:
        python3 -c "from magic_compositor import make_event1_runestone; make_event1_runestone(preview_only=True)"
    """
    db  = _dropbox()
    bg  = os.path.join(db, "Production", "Event_1", "resolution_stills",
                       "still_3_body_stone_glow_v9.png")
    out = output_dir or os.path.join(db, "Production", "Event_1", "kling_clips")
    mc  = MagicCompositor(
        bg, EVENT1_RUNESTONE_BODY_PATH, style="wide_ori",
        duration=3.5, fps=24,
        output_dir=out, label="beat02_runestone_magic_v2", seed=seed,
        # LD-421 registration metadata
        module_id=1, event_id=1, beat_id="res_beat_02",
        scene_key="m1_e1_res_beat_02_runestone",
        tags=["magic", "compositor", "wide_ori", "runestone", "body_stone"],
    )
    mc.render_preview(frame_idx=82)   # t≈0.99 — trail fully at orange stone
    if not preview_only:
        mc.render_video()
    return mc


def make_event1_resolution(output_dir=None, preview_only=False, seed=99):
    """
    Factory for Event 1 Heartwood resolution magic trail.
    Quick usage:
        python3 -c "from magic_compositor import make_event1_resolution; make_event1_resolution(preview_only=True)"
    """
    db  = _dropbox()
    bg  = os.path.join(db, "Production", "Event_1", "resolution_stills",
                       "heartwood_3q_left_1456.png")
    out = output_dir or os.path.join(db, "Production", "Event_1", "kling_clips")
    mc  = MagicCompositor(
        bg, EVENT1_HEARTWOOD_PATH, style="tessa_ori",
        output_dir=out, label="event1_resolution",
        # LD-421 registration metadata
        module_id=1, event_id=1, beat_id="res_beat_01",
        scene_key="m1_e1_res_beat_01_heartwood",
        tags=["magic", "compositor", "tessa_ori", "heartwood", "resolution"],
    )
    mc.render_preview()
    if not preview_only:
        mc.render_video()
    return mc


# ── CLI ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="MagicCompositor — traveling magic trail")
    p.add_argument("--background",   help="Path to background still image")
    p.add_argument("--style",        default="tessa_ori")
    p.add_argument("--duration",     type=float, default=3.5)
    p.add_argument("--fps",          type=int,   default=24)
    p.add_argument("--seed",         type=int,   default=99)
    p.add_argument("--preview-only", action="store_true")
    p.add_argument("--output-dir",   default=None)
    p.add_argument("--label",        default=None)
    p.add_argument("--path",         nargs="+",
                   help="Control points as x,y  e.g. 0.01,0.745 0.47,0.670")
    # LD-421 registration metadata (optional — when set, output registers via wrapper)
    p.add_argument("--module-id",    type=int, default=None,
                   help="prod_modules FK (1=Tessa,2=Luna,3=Ember,4=Bramble,5=Benson,6=Bork)")
    p.add_argument("--event-id",     type=int, default=None, help="Event integer (e.g. 1)")
    p.add_argument("--beat-id",      default=None, help="Beat string (e.g. 'res_beat_01')")
    p.add_argument("--scene-key",    default=None, help="scene_registry.yaml key for traceability")
    args = p.parse_args()

    if not args.background:
        # Default: Event 1 Heartwood
        make_event1_resolution(
            output_dir=args.output_dir,
            preview_only=args.preview_only,
            seed=args.seed,
        )
    else:
        pts = (
            [tuple(float(v) for v in pt.split(",")) for pt in args.path]
            if args.path else EVENT1_HEARTWOOD_PATH
        )
        mc = MagicCompositor(
            background_path=args.background,
            path_pts=pts,
            style=args.style,
            duration=args.duration,
            fps=args.fps,
            seed=args.seed,
            output_dir=args.output_dir,
            label=args.label,
            module_id=args.module_id,
            event_id=args.event_id,
            beat_id=args.beat_id,
            scene_key=args.scene_key,
        )
        mc.render_preview()
        if not args.preview_only:
            mc.render_video()
