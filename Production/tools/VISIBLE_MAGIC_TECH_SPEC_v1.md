# Visible Magic Skill — Full Technical Specification v1
**Date:** 2026-04-24  
**Status:** Draft — awaiting implementation  
**Produced by:** Three-agent diagnostic debate + synthesis (Opus × 3)  
**Based on:** VISIBLE_MAGIC_LESSONS_LEARNED_v4.md, all prior lessons-learned docs, SKILL.md, governance file, all compositor scripts v1–v11, full session histories 2026-04-22 through 2026-04-24  

---

## 0. Purpose and Scope

This document is the complete technical specification for a **"produce visible magic → first time works"** system for MindfulNest. It supersedes the ad-hoc compositor scripts, replaces the fragile `magic_clip_registry.json`, and defines the target architecture that the current `magic_compositor.py` and `visible-magic` SKILL.md must be refactored to match.

**Scope:** All 54-module V1 catalog. All 6 creatures. All scene archetypes that require a visible magic trail, burst, or activation effect.

**Out of scope:** Phase B tile magic (handled by `build_phase_b_tile.py`). Ambient background particle effects not triggered by a specific character spell. Runtime app-side effects (all magic is baked into atomic MP4 per APP_ARCHITECTURE_MASTER).

---

## 1. Success Criteria

"First time works" is defined as:
- Kim sees preview PNG #1 and says "approve" OR says "brighter/dimmer" exactly once before approving
- Zero position iteration (no red-circle coordinate hunt)
- Zero aesthetic iteration (no sigma, gain, or density tuning)
- Stitch auto-resolves to approved source clips via Directus (zero filename-matching)
- Total wall-clock time from "produce visible magic" to approved full-clip: ≤15 minutes

Approved visual targets (derived from Kim approvals):

| Attribute | Required value |
|---|---|
| Palette | Warm golden-white: `(255,255,238)/(255,252,200)/(255,240,155)` for Ori style |
| Shape | Floor-flat "sparkle river" — wide X, thin Y |
| Particle form | 1–3px crisp dots only |
| Vertical anchor | Trail hugs floor; `scatter_y_frac ≤ 0.032`, effective `SIGMA_Y ≤ 8px` after background-class routing |
| Blend mode | Additive only |
| Motion | Smooth; no per-frame particle pop |
| Position accuracy | ≤10px from pixel-verified target |
| Preview time | ≤2 min from command invocation |
| Full video render | ≤5 min |

---

## 2. System Architecture Overview

```
Kim says: "produce visible magic"
           ↓
    render_magic(scene_key)          ← single entry point
           ↓
   ┌────────────────────────────────────────────────┐
   │  1. resolve_source_clip(scene_key)             │
   │     → query prod_visual_assets (Directus)      │
   │     → return approved source clip path          │
   ├────────────────────────────────────────────────┤
   │  2. geometry_detector.infer(scene_key, clip)   │
   │     → archetype lookup → run detector method   │
   │     → return path_pts [(x,y)...]               │
   ├────────────────────────────────────────────────┤
   │  3. background_classifier.classify(bg_frame)   │
   │     → measure luminance + saturation on path   │
   │     → return class: daytime-warm / nighttime / │
   │       indoor / daytime-cool                     │
   ├────────────────────────────────────────────────┤
   │  4. MagicCompositor(bg, path_pts, style, ...)  │
   │     → apply locked params for class+style      │
   │     → render preview PNG at T_TRAIL_COMPLETE   │
   ├────────────────────────────────────────────────┤
   │  5. open_preview(png)                          │
   │     → Kim: approve / brighter / dimmer /       │
   │       lower / reposition / reject              │
   └────────────────────────────────────────────────┘
           ↓ (approved)
   render_full_video()
           ↓
   register_to_directus(prod_magic_clips)
           ↓
   assemble_magic_sequence(kling_clip, magic_still)
           ↓
   register_output_to_directus(prod_visual_assets)
```

---

## 3. Entry Point API

### `render_magic(scene_key, style="auto", preview_only=True, gain_override=None, draft=False)`

**Parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `scene_key` | str | required | Matches a key in `SCENE_REGISTRY` (Directus or local YAML). Example: `"m1_e1_res_beat_01_heartwood"` |
| `style` | str | `"auto"` | Style name (`"tessa_ori"`, `"wide_ori"`) or `"auto"` to infer from scene archetype |
| `preview_only` | bool | `True` | Render one PNG preview frame only; skip full video until Kim approval |
| `gain_override` | float | `None` | Multiplier applied to auto-calibrated gain. Only set after Kim says "brighter" (1.3) or "dimmer" (0.75) |
| `draft` | bool | `False` | If True, allow draft/unvalidated styles. If False, raise RuntimeError on non-approved styles |

**Returns:** `MagicRenderResult` with fields: `preview_path`, `video_path` (None until approved), `coords_used`, `background_class`, `gain_applied`, `directus_asset_id`

**CLI wrapper:**
```bash
python3 Production/tools/magic_compositor.py --scene m1_e1_res_beat_01_heartwood
python3 Production/tools/magic_compositor.py --scene m1_e1_res_beat_01_heartwood --gain 1.3
python3 Production/tools/magic_compositor.py --scene m1_e1_res_beat_01_heartwood --preview-only
```

---

## 4. Scene Registry

Replaces the coordinate-based `KNOWN_SCENES` dict in the current compositor.

### 4.1 Schema

```yaml
# Production/tools/scene_registry.yaml
# Each entry stores a RECIPE (archetype + semantic anchors), NOT pixel coordinates.
# Coordinates are auto-detected at render time from the actual source clip.

m1_e1_res_beat_01_heartwood:
  archetype: "ground_left_to_target"
  description: "Magic travels left across floor to Heartwood altar step"
  style: "tessa_ori"
  color_target: "orange"          # stone color for detect_stone_center()
  direction: "left"               # origin side for detect_exit_vector()
  source_asset_query:             # Directus query to resolve source clip
    collection: "prod_visual_assets"
    filter:
      module_id: "m1"
      event_id: "e1"
      shot_role: "res_beat_01_base"
      status: "approved"

m1_e1_res_beat_01_tessa_exit:
  archetype: "character_exit_ground"
  description: "Tessa walks right off-frame with ground trail"
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
  description: "Runestone activation burst at orange stone centroid"
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
```

### 4.2 Registration protocol for new scenes
When a new scene is identified:
1. Add entry to `scene_registry.yaml` with archetype + semantic anchors only
2. Run `geometry_detector.py --scene <key> --confirm` → generates debug image with detected coords overlaid
3. Kim confirms debug image (one click / "yes that's right")
4. Confirmation logged to `prod_magic_clips` with `geometry_confirmed_at` timestamp
5. Future renders of the same scene: zero confirmation needed (geometry auto-detected fresh each time from source clip)

---

## 5. Geometry Detector

New module: `Production/tools/geometry_detector.py`

### 5.1 Interface

```python
class GeometryDetector:
    def infer(self, scene_key: str, source_clip: Path) -> list[tuple[float, float]]:
        """Main entry. Looks up archetype in registry, dispatches to correct detector."""
        
    def detect_foot_contact(self, clip: Path) -> tuple[float, float]:
        """Ground trail origin: character alpha-mask bottom edge, mid-frame."""
        
    def detect_exit_vector(self, clip: Path, direction: str) -> list[tuple[float, float]]:
        """Character-exit trail: optical flow last 10 frames → normalized exit direction.
        Returns 3-point path: [foot_contact, midpoint, off_screen_exit]."""
        
    def detect_stone_center(self, bg_frame: np.ndarray, color: str) -> tuple[float, float]:
        """Target stone centroid: color-channel thresholding.
        Colors: orange, purple, yellow, red, blue, green.
        Reuses 6 lambdas from magic_position_finder.py."""
        
    def detect_horizon_line(self, bg_frame: np.ndarray) -> float:
        """Wide-clearing trail: bright/dark luminance band transition.
        Returns y fractional coordinate of detected horizon."""
        
    def render_debug_image(self, bg_frame: np.ndarray, path_pts: list, output_path: Path) -> Path:
        """Overlay detected path_pts as red circles on bg_frame.
        Used for Kim's one-time confirmation on novel archetypes."""
```

### 5.2 Archetype → detector dispatch table

| Archetype | Origin detector | Target detector | Path shape |
|---|---|---|---|
| `ground_left_to_target` | `detect_stone_center(color_target)` inverted | `detect_stone_center(color_target)` | Bezier arc, 3 control points, floor-hugging |
| `character_exit_ground` | `detect_foot_contact()` | `detect_exit_vector(direction)` | Straight path to off-screen |
| `stone_activation` | `detect_stone_center(color_target)` | same (burst from centroid outward) | Radial from centroid |
| `wide_clearing_cross` | Left edge at `detect_horizon_line()` y | Right edge at same y | Horizontal straight |

### 5.3 Confidence scoring
Each detector returns a `(coords, confidence: float 0-1)` tuple.
- `confidence ≥ 0.8`: auto-proceed, no Kim confirmation
- `0.5 ≤ confidence < 0.8`: render debug image, ask Kim to confirm
- `confidence < 0.5`: STOP, ask Kim to specify scene archetype manually

Confidence is computed from: pixel count at detected target (stone), gradient strength at detected boundary (foot), optical flow magnitude (exit vector).

---

## 6. Background Classifier

New module: `Production/tools/background_classifier.py`

### 6.1 Interface

```python
class BackgroundClassifier:
    def classify(self, bg_frame: np.ndarray, path_pts: list) -> str:
        """Measure luminance + saturation along path centerline.
        Returns: 'daytime-warm' | 'daytime-cool' | 'nighttime' | 'indoor'"""
        
    def get_params(self, bg_class: str, base_style: str) -> dict:
        """Return class-appropriate parameter overrides for MagicCompositor."""
```

### 6.2 Classification thresholds

| Class | Mean luminance | Mean saturation | Typical scenes |
|---|---|---|---|
| `daytime-warm` | ≥ 120 | ≥ 80 | Heartwood, Everdale exterior |
| `daytime-cool` | ≥ 120 | < 80 | Sky-heavy shots, Cliffside |
| `nighttime` | < 60 | any | Luna garden, Luminara |
| `indoor` | 60–119 | any | Bork cave, interior scenes |

### 6.3 Parameter routing table

| Class | `SIGMA_Y` override | `AMBIENT_BLUR_YX` | Palette shift | Gain floor |
|---|---|---|---|---|
| `daytime-warm` | 6.0 | [6.0, 28.0] | None (locked Ori) | 0.7 |
| `daytime-cool` | 6.0 | [6.0, 28.0] | Slight warm shift | 0.8 |
| `nighttime` | 12.0 | [10.0, 40.0] | None (Ori still correct) | 0.5 |
| `indoor` | 8.0 | [8.0, 30.0] | None | 0.6 |

Note: Palette is never changed for V1 — all V1 magic is warm-gold Ori. The shift column is reserved for future arc-specific styles (not yet validated).

---

## 7. Style Registry and Locked Parameters

### 7.1 `tessa_ori` — APPROVED (LD-398 `MAGIC_STYLE_TESSA_ORI_V1`)

```python
STYLES = {
    "tessa_ori": {
        "status": "approved",
        "directus_ld": 398,             # was null/TODO — MUST be set
        "description": "Warm golden floor-flat sparkle river. The only approved V1 style.",
        
        # Particle system — LOCKED, never expose as tunable
        "n_particles": 1800,
        "dot_sizes": [1, 1, 1, 2, 2, 3],   # never larger
        "bright_range": [0.72, 1.0],
        "twinkle_range": [0.85, 1.0],
        "palette": [(255,255,238), (255,252,200), (255,240,155)],
        "palette_weights": [0.5, 0.3, 0.2],
        "seed": 42,
        
        # Geometry — LOCKED
        "scatter_x_frac": 0.18,
        "scatter_y_frac": 0.032,       # floor-flat; never increase
        "scatter_distribution": "symmetric_gaussian",  # NOT abs(gauss)
        
        # Blend — LOCKED
        "blend_mode": "additive",      # NEVER screen
        "sparkle_gain": 1.0,           # auto-calibrated; this is pre-calibration
        "ambient_gain": 0.6,
        "ambient_mix": 2.4,
        "sparkle_blur": 0.8,
        
        # Blur — LOCKED; overridden by background_classifier for non daytime-warm
        "AMBIENT_BLUR_YX": [6.0, 28.0],
        
        # Timing — LOCKED
        "T_TRAIL_COMPLETE": 0.70,
        "T_FADEOUT_START": 0.75,
        "T_FADEOUT_END": 0.95,
        "T_DISSOLVE_START": 0.70,
        "T_DISSOLVE_END": 0.90,
    },
    
    "wide_ori": {
        "status": "draft",             # NOT approved — block in production
        "directus_ld": None,
        "description": "Wide horizontal clearing cross. Awaiting Kim approval.",
        # ... params TBD after first validated render
    },
    
    "burst": {
        "status": "pending",           # Does not yet exist
        "directus_ld": None,
        "description": "Stone activation radial burst. Not yet implemented.",
    }
}
```

### 7.2 Style enforcement

```python
def _validate_style(style_name: str, draft_mode: bool) -> None:
    style = STYLES.get(style_name)
    if style is None:
        raise RuntimeError(f"Unknown style: {style_name}")
    if style["status"] != "approved" and not draft_mode:
        raise RuntimeError(
            f"Style '{style_name}' is not approved for production (status: {style['status']}). "
            f"Use --draft flag to force, or wait for Kim approval."
        )
    if style["directus_ld"] is None and not draft_mode:
        raise RuntimeError(
            f"Style '{style_name}' has no Directus LD linked. "
            f"Link LD before production use."
        )
```

---

## 8. Auto-Calibration

### 8.1 Gain calibration (existing, keep)

```python
def _calibrate_brightness(self, bg: np.ndarray, path_pts: list) -> float:
    """Sample luminosity along path centerline. Compute gain scalar."""
    samples = self._sample_path_centerline(bg, path_pts, n=20)
    avg_lum = np.mean([_luminosity(px) for px in samples])
    gain = 0.7 + (avg_lum / 128) * 0.6   # range: 0.7 (dark bg) → 1.3 (bright bg)
    return gain
```

### 8.2 Gain override (Kim feedback)

```python
GAIN_ADJUSTMENTS = {
    "brighter": 1.30,
    "dimmer": 0.75,
    "much_brighter": 1.60,
    "much_dimmer": 0.55,
}
```

When Kim says "brighter": `gain_override = GAIN_ADJUSTMENTS["brighter"]`. This is the ONLY parameter Claude should adjust in response to Kim feedback. All other parameters stay locked.

### 8.3 Position adjustment (Kim feedback: "lower")

```python
def _adjust_path_vertical(self, path_pts: list, delta_y: float = 0.02) -> list:
    """Shift all path points down by delta_y fractional units.
    Only called when Kim says 'lower'. Maximum two calls before stopping and asking."""
    return [(x, y + delta_y) for (x, y) in path_pts]
```

---

## 9. Compositing Pipeline (per-frame)

```python
def _render_frame(self, bg: np.ndarray, t_frac: float) -> np.ndarray:
    """
    t_frac: 0.0 → 1.0 over full clip duration
    
    Phase 1 (0.0 → T_TRAIL_COMPLETE=0.70): trail grows
    Phase 2 (0.70 → T_FADEOUT_START=0.75): trail holds at full extent
    Phase 3 (0.75 → T_FADEOUT_END=0.95): trail fades
    Phase 4 (T_DISSOLVE_START=0.70 → T_DISSOLVE_END=0.90): activation burst (if applicable)
    """
    frame = bg.astype(np.float32).copy()
    
    # Determine trail head position
    t_head = min(1.0, t_frac / self.T_TRAIL_COMPLETE)
    
    # Fade multiplier
    if t_frac > self.T_FADEOUT_START:
        fade = 1.0 - (t_frac - self.T_FADEOUT_START) / (self.T_FADEOUT_END - self.T_FADEOUT_START)
        fade = max(0.0, fade)
    else:
        fade = 1.0
    
    # Accumulate sparkle layer (float32)
    sparkle_layer = np.zeros_like(frame)
    
    for particle in self.particles:  # pre-placed, seeded, sorted by ts
        if particle.ts > t_head:
            break   # particles after head not yet visible
        
        # Tail fade: brightness floor at 25%
        tail_frac = 1.0 - (t_head - particle.ts)
        brightness = (0.25 + 0.75 * tail_frac) * particle.alpha * fade
        brightness *= self.gain  # auto-calibrated
        
        # Twinkle
        brightness *= np.random.uniform(*self.twinkle_range)
        
        # Place dot (1–3px, crisp)
        self._place_dot(sparkle_layer, particle.x, particle.y, particle.dot_size, 
                        particle.color, brightness)
    
    # Sparkle blur (very light)
    sparkle_blurred = gaussian_filter(sparkle_layer, sigma=self.sparkle_blur)
    
    # Ambient glow from sparkles
    ambient = gaussian_filter(sparkle_blurred, sigma=self.AMBIENT_BLUR_YX) * self.ambient_mix
    
    # Composite: additive blend (NEVER screen)
    result = frame + self.sparkle_gain * sparkle_blurred + self.ambient_gain * ambient
    result = np.clip(result, 0, 255).astype(np.uint8)
    
    return result
```

### 9.1 Particle pre-placement (init, not per-frame)

```python
def _place_particles(self) -> list[Particle]:
    """All particles placed at __init__ time. Deterministic (seed=42)."""
    rng = np.random.default_rng(self.seed)
    particles = []
    
    for i in range(self.n_particles):
        ts = rng.uniform(0, 1)           # position along trail timeline
        path_pos = self._interpolate_path(ts)
        
        # Symmetric gaussian scatter (NOT abs — that creates half-normal floating band)
        dx = rng.normal(0, self.scatter_x_frac) * self.width
        dy = rng.normal(0, self.scatter_y_frac) * self.height
        
        x = path_pos[0] + dx
        y = path_pos[1] + dy
        
        color = rng.choice(self.palette, p=self.palette_weights)
        dot_size = rng.choice(self.dot_sizes)
        alpha = rng.uniform(*self.bright_range)
        
        particles.append(Particle(ts=ts, x=x, y=y, color=color, 
                                   dot_size=dot_size, alpha=alpha))
    
    particles.sort(key=lambda p: p.ts)   # sort for efficient per-frame filter
    return particles
```

---

## 10. Preview Gate

```python
def render_preview(self) -> Path:
    """Render single frame at T_TRAIL_COMPLETE (trail fully extended).
    Kim approves this before full video render begins."""
    t_frac = self.T_TRAIL_COMPLETE
    frame = self._render_frame(self.bg_frame, t_frac)
    preview_path = self.output_dir / f"preview_{self.scene_key}.png"
    Image.fromarray(frame).save(preview_path)
    
    # Open in Preview.app
    subprocess.run(["open", "-a", "Preview", str(preview_path)])
    return preview_path
```

**Kim's response options (presented as 5 fixed buttons in the skill):**
- `approve` → proceed to full video render
- `brighter` → set `gain_override=1.30`, re-render preview (one additional render max)
- `dimmer` → set `gain_override=0.75`, re-render preview
- `lower` → call `_adjust_path_vertical(delta_y=0.02)`, re-render preview
- `reposition` → surface debug image with detected coords, ask Kim to point to correct location
- `reject` → log to Directus `prod_magic_clips` with `status="rejected"`, stop

**Hard stop rule:** If Kim is not satisfied after 3 preview renders, STOP and ask Kim to describe in words what is wrong. Do not guess a 4th parameter adjustment.

---

## 11. Directus Integration

### 11.1 `prod_magic_clips` collection (new — replaces `magic_clip_registry.json`)

```
Collection: prod_magic_clips
Fields:
  id                    int (auto)
  scene_key             string (unique, matches scene_registry.yaml)
  archetype             string
  source_asset_id       FK → prod_visual_assets (the base clip being composited on)
  magic_asset_id        FK → prod_visual_assets (the composited output clip)
  status                enum: pending | approved | rejected
  background_class      string (daytime-warm | nighttime | indoor | daytime-cool)
  gain_applied          float
  path_pts_detected     json (coords used, for audit trail)
  geometry_confirmed_at datetime (null until Kim confirms debug image)
  style_name            string
  directus_ld           int FK → prod_locked_decisions
  approved_at           datetime
  notes                 string
  created_at            datetime
```

### 11.2 `resolve_stitch_clips(scene_key)` — rewritten

```python
def resolve_stitch_clips(scene_key: str) -> StitchManifest:
    """
    Query Directus for approved source and magic clips for a scene.
    NEVER resolve by filename. Only approved status counts.
    
    Returns StitchManifest with:
      - base_clip: Path to approved Kling source clip (no magic)
      - magic_clip: Path to approved composited magic still-segment
      - stitch_order: ['base_clip', 'magic_clip']
      - ffmpeg_durations: [base_duration, magic_duration]
    
    Raises ValueError if any clip is missing or not approved.
    """
    registry = directus.items("prod_magic_clips").filter(
        scene_key=scene_key,
        status="approved"
    ).first()
    
    if registry is None:
        raise ValueError(f"No approved magic clip registered for scene '{scene_key}'. "
                         f"Run render_magic('{scene_key}') and get Kim approval first.")
    
    source = directus.items("prod_visual_assets").get(registry.source_asset_id)
    magic = directus.items("prod_visual_assets").get(registry.magic_asset_id)
    
    if source is None or magic is None:
        raise ValueError(f"Directus asset record missing for scene '{scene_key}'.")
    
    return StitchManifest(
        base_clip=Path(source.file_path),
        magic_clip=Path(magic.file_path),
        stitch_order=["base_clip", "magic_clip"],
        ffmpeg_durations=[source.duration_s, magic.duration_s]
    )
```

### 11.3 Registration on approval

```python
def register_approved_magic(scene_key: str, magic_clip_path: Path, 
                             gain_applied: float, bg_class: str,
                             path_pts: list, style_name: str) -> int:
    """Two-write rule: (1) write prod_visual_assets row, (2) write prod_magic_clips row."""
    
    # Write 1: asset file
    asset_row = directus.create("prod_visual_assets", {
        "module_id": scene_registry[scene_key]["module_id"],
        "shot_role": f"magic_{scene_key}",
        "file_path": str(magic_clip_path),
        "file_size_bytes": magic_clip_path.stat().st_size,
        "status": "approved",
        "role": "magic_composite",
        "created_at": datetime.utcnow().isoformat(),
    })
    
    # Write 2: magic registry
    magic_row = directus.create("prod_magic_clips", {
        "scene_key": scene_key,
        "magic_asset_id": asset_row["id"],
        "source_asset_id": resolve_source_asset_id(scene_key),
        "status": "approved",
        "background_class": bg_class,
        "gain_applied": gain_applied,
        "path_pts_detected": json.dumps(path_pts),
        "style_name": style_name,
        "directus_ld": STYLES[style_name]["directus_ld"],
        "approved_at": datetime.utcnow().isoformat(),
    })
    
    # Activity log
    directus.create("prod_activity_log", {
        "action": "magic_approved",
        "scene_key": scene_key,
        "asset_id": asset_row["id"],
        "notes": f"gain={gain_applied:.2f}, class={bg_class}, style={style_name}",
    })
    
    return magic_row["id"]
```

---

## 12. Canonical Stitch Pattern

The stitch (Kling-animated segment + compositor-magic-still segment) is the **correct and permanent** production pattern. It is not a workaround. It is required because the compositor takes PNG stills, not video.

```python
def assemble_magic_sequence(scene_key: str, output_path: Path) -> Path:
    """
    Canonical stitch: [Kling base clip] + [compositor magic on held still]
    Source resolution always via Directus, never filename patterns.
    """
    manifest = resolve_stitch_clips(scene_key)
    
    # Build ffmpeg concat list
    concat_list = output_path.parent / "concat_list.txt"
    with open(concat_list, "w") as f:
        f.write(f"file '{manifest.base_clip}'\n")
        f.write(f"file '{manifest.magic_clip}'\n")
    
    # Concat with normalization (LD-284: all clips must be normalized before concat)
    normalized_base = normalize_clip(manifest.base_clip)
    normalized_magic = normalize_clip(manifest.magic_clip)
    
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(output_path)
    ], check=True)
    
    # Register to Directus
    register_assembled_sequence(scene_key, output_path)
    
    return output_path
```

**Normalization spec (LD-284 `NORMALIZATION_BEFORE_CONCAT_V1`):**
All clips normalized to: `H.264 High / yuv420p / 1280×720 / 24fps / AAC 128kbps mono 44.1kHz / +faststart` before concat.

---

## 13. Skill Entry Point (SKILL.md behavior)

When Kim says **"produce visible magic"** or **"usual process for making visible magic"**:

1. Read `scene_registry.yaml` — identify which scene key(s) are in scope (infer from conversation context: which beat, which module, which event)
2. Call `render_magic(scene_key)` for each scene
3. Present preview PNG(s) to Kim
4. Accept Kim feedback: approve / brighter / dimmer / lower / reposition / reject
5. On approval: call `render_full_video()` → `register_approved_magic()` → `assemble_magic_sequence()`
6. Report: "Done. `beat_NN_magic_final.mp4` registered in Directus (asset id=XXX). Ready for normalization and concat."

**What Claude should NEVER do in response to Kim feedback:**
- Tune `n_particles`, `sigma`, `scatter_y_frac`, `dot_sizes`, `palette`, `blend_mode`, or `ambient_mix`
- Ask Kim what opacity, blur, or particle count she wants
- Run more than 3 preview renders before stopping and asking Kim to describe the problem

**What Claude should do in response to Kim feedback:**
- "brighter" → `gain_override=1.30`, one re-render
- "dimmer" → `gain_override=0.75`, one re-render
- "lower" → `_adjust_path_vertical(delta_y=0.02)`, one re-render
- "wrong position" / "reposition" → `detect_stone_center()` or `detect_foot_contact()` re-run + debug image, Kim confirms coords
- "reject" → log to Directus, stop

---

## 14. File and Module Map

### New files to create:
```
Production/tools/geometry_detector.py      ← Fix 1 (highest priority)
Production/tools/background_classifier.py  ← Fix 3
Production/tools/scene_registry.yaml       ← Fix 2 (replaces KNOWN_SCENES)
```

### Files to modify:
```
Production/tools/magic_compositor.py
  - Add render_magic() entry point
  - Wire geometry_detector.infer() for path_pts
  - Wire background_classifier.classify() for param routing
  - Fix STYLES["tessa_ori"]["directus_ld"] = 398
  - Add _validate_style() enforcement
  - Replace KNOWN_SCENES with scene_registry.yaml loader
  - Add register_approved_magic() two-write function
  - Rewrite resolve_stitch_clips() to query Directus
  - Add assemble_magic_sequence() as canonical stitch function
  - Add render_preview() gate
  - Add Kim-feedback adjustment functions (gain, vertical)
```

### Directus changes:
```
New collection: prod_magic_clips (schema in §11.1)
Delete: magic_clip_registry.json (after migration)
```

### Files that stay unchanged:
```
Production/tools/magic_position_finder.py  
  ← its 6 color-threshold lambdas migrate INTO geometry_detector.py
  ← keep as legacy fallback during transition
```

---

## 15. Known Limitations (V1)

1. **Still-to-video compositor:** The compositor produces magic on PNG stills only. The stitch pattern (§12) is the permanent solution. Future arcs: same pattern always applies.

2. **tessa_ori only:** `wide_ori` and `burst` are not validated. They MUST NOT be used in production until Kim approves a reference render for each.

3. **Background classifier initial values:** The luminance thresholds in §6.2 are estimates based on known Heartwood scene values. They should be verified against Luna, Bork, and Ember source stills before those arcs enter production.

4. **Optical flow exit-vector detector:** Novel implementation — not yet validated. On first use for a character-exit-ground scene, run with `--confirm` and show Kim the debug image regardless of confidence score.

5. **Directus `prod_magic_clips` collection:** Must be created before this spec can be fully implemented. Until then, `resolve_stitch_clips()` can use the existing `magic_clip_registry.json` as a temporary bridge, with a deprecation warning logged.

---

## 16. Implementation Priority

| Priority | Task | Estimated effort | Unlocks |
|---|---|---|---|
| 1 | `geometry_detector.py` + 4 detectors | 3–4 hrs | Eliminates coordinate hunt forever |
| 2 | `scene_registry.yaml` + archetype-addressed KNOWN_SCENES | 1 hr | Eliminates SHA drift |
| 3 | `background_classifier.py` + routing table | 2 hrs | Luna/Bork/Ember arc readiness |
| 4 | Directus `prod_magic_clips` collection + migrate registry | 2 hrs | Eliminates JSON sync failure class |
| 5 | Wire all into `render_magic()` entry point | 2 hrs | "First time works" UX |
| 6 | `_validate_style()` enforcement + link LD-398 | 30 min | Prevents draft style production use |
| 7 | `assemble_magic_sequence()` as canonical function | 1 hr | Stitching is robust by design |

**Total estimated:** 11–12 hours of implementation work.

---

*This spec is the authoritative design document for the visible magic system. All implementation must conform to it. Questions or deviations require explicit Kim approval and a new Directus LD.*
