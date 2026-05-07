# Visible Magic Production — Lessons Learned v3
## Complete Reference · 2026-04-24
### Supersedes: LESSONS_LEARNED_magic_path_compositor_20260422.md, LESSONS_LEARNED_magic_compositor_session2_20260422.md, and the unreleased v2 placeholder

**Sources parsed for this document:**
- ~12 heartwood compositor iterations (Session 2026-04-22 morning)
- Tessa exit-right positioning iterations (Session 2026-04-23)
- Runestone activation positioning iterations (Session 2026-04-23)
- Full-sequence v1 stitch (approved) and v2 stitch (failed) post-mortems
- Agent scrape of full session thread (2026-04-23 evening)
- Visible magic skill build debate + spec (2026-04-23)
- `tessa_exit_right_v3.py`, `tessa_trail_stitch.py`, `runestone_activation.py`
- Both prior lessons-learned docs (Event_1/)

---

## Part 1 — Rendering Physics

### 1.1 Blend Mode: Additive Only, Screen Banned

**Rule: ALWAYS use additive composite. Screen blend is banned for all MindfulNest visible magic.**

```python
result = np.clip(base.astype(np.float32) + trail_layer, 0, 255).astype(np.uint8)
```

**Why screen fails on daytime backgrounds:**
Screen blend formula: `out = 255 - (255-bg) * (255-magic) / 255`

| bg pixel | magic pixel | screen result | additive result |
|----------|-------------|---------------|-----------------|
| 180 | 100 | 210 (+30) | 255 (capped, visible) |
| 80 | 100 | 152 (+72) | 180 (+100) |
| 30 | 200 | 224 (+194) | 230 (+200) |

On the bright daytime heartwood background (bg ~150–200), screen adds only +30–60 brightness — invisible. On the darker path corridor (~80 luminosity), it works somewhat — but additive is still more reliable and consistent across all scene types.

**Screen compounding bug (do not reintroduce):** If you screen-blend N trail layers sequentially (each dim at opacity x), the result compounds to near-white: `1 - (1-x)^N`. With N=60 and x=0.1: result = 0.998 ≈ white. Always accumulate all layers into a single float32 array, then do ONE composite with the background.

**Do not use:** `PIL.ImageChops.screen()`, multiply, overlay, or any other blend mode. All were tried and rejected.

---

### 1.2 Two-Layer Trail Architecture

The trail layer is built from two sub-layers before composite:

```python
sp_arr  = [crisp sparkle dots — small PIL ellipses, 1–3px]
amb_arr = [same sparkle layer, blurred via Gaussian to create ambient glow]

trail = np.clip(sp_arr + amb_arr * AMBIENT_MIX, 0, 255)
# AMBIENT_MIX = 2.4 (approved)

result = np.clip(base + trail, 0, 255).astype(np.uint8)
```

The crisp dots give the "sparkle" look. The ambient layer gives the warm glow halo around the sparkles. Neither alone achieves the approved look — they must be combined.

---

### 1.3 Ambient Blur Radius Rules

**Approved value: `radius = 6px` for all ground-level trails. Do not deviate upward without a specific scene reason.**

Why 6px:
- At 6px, Gaussian spread is ±12px maximum — keeps ambient glow hugging the sparkle dots, perceived as emanating from the ground.
- At 22px (the failed value), spread extends 44–66px vertically — glow pixels land in sky zones, trail appears to float 6 inches above ground.

**Asymmetric blur (scipy — preferred for ground trails):**
```python
AMBIENT_BLUR_YX = [6.0, 28.0]  # tessa_ori style — narrow Y, wide X
# Blurs mostly horizontal → light pools laterally across floor, not upward
```

**Isotropic blur (PIL — simpler, acceptable for some scripts):**
```python
GaussianBlur(radius=6)
```

**Wide-beam exception (wide_ori style):**
```python
AMBIENT_BLUR_YX = [8.0, 32.0]  # elevated beam, wider x spread acceptable
```

**Rule: Y-sigma ≤ 8px for any ground-level trail. If Y-sigma > 8px, the trail will appear to float.**

---

### 1.4 scipy gaussian_filter Peak Reduction (Important Math)

`gaussian_filter` preserves total SUM, not peak values. A point value V blurred with sigma σ has peak:

`peak = V / (2π × σ²)`

- V=2000, σ=0.7 → peak = 650 (clips to 255, OK)
- V=2000, σ=3.5 → peak = 26 (nearly invisible)
- V=2000, σ=14 → peak = 1.6 (completely invisible)

**Implication:** Sparse sparkle dots blurred with large sigma = invisible. Solutions:
1. Small sigma (0.7–1.5) for crisp 2–3px dots (preferred — the tessa_ori approach)
2. Very high accumulation values (×50–100) to survive larger blur
3. Dense sparkles (5000+) so density fills the path even after blur

Approach 1 is what all approved scripts use.

---

## Part 2 — Particle and Sparkle System

### 2.1 Pre-Placed Seeded Particles Eliminate All Jerkiness

**The jerkiness root cause:** Computing `n_samples = int(t_head * 50)` each frame means a new particle pops into existence at a new position every ~1.7 frames. The "pop" is visible and looks like jitter.

**The fix:** Generate ALL particles at init time with a fixed random seed. Store as sorted list. Each frame just filters by t_head — no position ever changes.

```python
# At init — runs ONCE
rng = np.random.default_rng(seed=42)
PARTICLES = []
for _ in range(N_PARTICLES):
    ts = rng.random()          # position along path (fixed forever)
    tw_ph = rng.random() * 2 * math.pi  # twinkle phase (fixed)
    tw_sp = rng.uniform(2, 6)  # twinkle speed (fixed)
    dot_r = rng.choice([1,1,1,2,2,3])   # dot size (fixed)
    PARTICLES.append((ts, tw_ph, tw_sp, dot_r))
PARTICLES.sort(key=lambda p: p[0])   # sort by ts for early-exit

# Per frame — just filter
for (ts, tw_ph, tw_sp, dot_r) in PARTICLES:
    if ts > t_head:
        break  # sorted — safe to break early
    # draw particle at bezier(ts) position
```

Same seed = same output always. Fully deterministic.

---

### 2.2 Dot Sizes: 1–3px Only

**Locked invariant: `DOT_SIZES = [1, 1, 1, 2, 2, 3]` — never larger.**

Why:
- Dots larger than 3px look like blobs, not sparkles.
- The 4:1 ratio of 1px to 3px gives natural variation without any particle looking "fat."
- No GaussianBlur per-particle — just the post-accumulation ambient blur on the entire layer. Per-particle blur creates 3D puffball look and is also very slow.

---

### 2.3 Trail Brightness Floor: 0.25

**Formula: `brightness = (0.25 + 0.75 × tail_frac) × alpha_mult`**

Where:
- `tail_frac` = position along trail from origin (0.0) to head (1.0)
- `alpha_mult` = overall trail opacity at this frame (1.0 fully visible → 0.0 faded out)

**Why 0.25, not 0.0:** Pure linear fade makes the trail origin invisible at `tail_frac=0`. The trail appears to start in the middle of nowhere — no origin anchor. The 0.25 floor ensures the trail always has at least 25% brightness at its origin point, anchoring it visually to the character's foot / contact point.

---

### 2.4 Symmetric Gaussian Scatter (abs() is Banned)

**The hard horizontal slice bug:** Using `abs(gauss(0, sigma))` for Y scatter gives a half-normal distribution — all particles scatter UPWARD from the path centerline. This creates a visible hard horizontal slice at the bottom of the trail.

**The fix:**
```python
# WRONG — creates hard slice
scatter_y = abs(gauss(0, path_width * 0.04))

# CORRECT — symmetric scatter above and below centerline
scatter_y = gauss(0, path_width * 0.032)
```

`scatter_y_frac = 0.032` = 3.2% of path width. This is what makes the magic appear to lie flat ON the floor. The tight Y-compression combined with wide X-spread creates the "floor pool" look.

---

### 2.5 Y-Compression for Floor-Flat Appearance

Three things working together create the floor-flat look:

1. **Tight Y scatter:** `scatter_y = gauss(0, path_width × 0.032)` — only 3.2% vertical spread
2. **Flat ellipses:** where drawn, use `ry = rx × 0.07` (7% of horizontal radius)
3. **Anisotropic blur:** `gaussian_filter(sigma=[2.5, 18.0])` — wide X, narrow Y → light pools sideways like a floor spill

**Do not round-trip to isotropic:** Once the floor-flat effect is dialed in, do not apply any subsequent blur that treats X and Y equally. That will bloat the trail upward and undo the floor-flat work.

---

## Part 3 — Path Geometry and Positioning

### 3.1 Never Eyeball Coordinates from a Thumbnail

**This failure caused a ~130px positioning error on the runestone (0.08 in both x and y on a 1676px-wide frame). That is visually miles off — the burst landed nowhere near the stone.**

Eyeball positioning from a thumbnail has no reliable resolution. A thumbnail pixel represents 4–8 actual pixels; a 1% coordinate error at 1676px wide = 17px real error.

**The correct workflow (mandatory — enforced by visible-magic skill governance):**
1. Run `magic_position_finder.py --debug-image <clip_or_still>` → generates a labeled 5% grid image
2. Open the debug image in Finder
3. Kim draws a red circle over the target location in Preview
4. Claude reads the pixel coordinates from Kim's circle and converts to fractions: `x_frac = px / W, y_frac = py / H`
5. Use those fractions as the path endpoint
6. Run `magic_position_finder.py --detect <clip> --target-hint "orange crystal"` for automatic color-threshold detection (use as second check, not primary)

**For runestones specifically:** The color-threshold detector in `magic_position_finder.py` has pre-tuned lambdas for all 6 stones. It reliably finds the stone centroid even in complex backgrounds, but still requires Kim red-circle confirmation before committing to a coordinate.

---

### 3.2 Path Geometry: Endpoint at the Step Edge, Not the Platform Top

A lesson from the heartwood 3/4-left scene (heartwood_3q_left_1456.png):

The Heartwood has a raised circular altar platform. The path endpoint must be at the **altar STEP EDGE** (y≈0.670), not the altar TOP (y≈0.60). Landing at the top puts the magic floating visually above the floor plane:

```python
# WRONG — magic appears to float in air
PATH_PTS = [(0.01, 0.73), (0.22, 0.74), (0.40, 0.70), (0.51, 0.60)]

# CORRECT — hugs floor, ends at step edge
PATH_PTS = [(0.01, 0.745), (0.18, 0.755), (0.35, 0.735), (0.47, 0.670)]
```

**General principle:** The path must track the actual floor geometry of the scene. At elevation changes (steps, altar edges), drop the endpoint to where the floor-level surface meets the raised element, not to the top of the raised element.

---

### 3.3 Source Clip SHA Validation

When reusing a KNOWN_SCENES entry across sessions, the source clip may have been re-rendered with different framing. Re-rendered clips shift the floor geometry, invalidating the stored path coordinates.

**The fix:** `magic_position_finder.py --sha <clip>` computes SHA256[:16] of frame 0. Compare against `source_frame_sha` stored in KNOWN_SCENES. If mismatch: warn, offer re-calibration. Never silently reuse stale coordinates.

---

## Part 4 — Clip Timing and Animation Phases

### 4.1 t_head Decoupling (Critical Bug Pattern)

**The bug:** Tying `t_head` (how far the trail has traveled) directly to `t_frac` (position in clip timeline):
```python
t_head = t_frac  # WRONG — no room for hold or fade phases
```

If T_TRAIL_COMPLETE = 0.70, the trail is still traveling when the clip ends, leaving no room for hold or fade.

**The fix:**
```python
t_head = min(1.0, t_frac / T_TRAIL_COMPLETE)  # correct — decoupled
```

This creates four clean phases in one clip:
- **0 → T_TRAIL_COMPLETE**: trail grows from origin to endpoint
- **T_TRAIL_COMPLETE → T_FADEOUT_START**: trail holds fully formed at endpoint
- **T_FADEOUT_START → T_FADEOUT_END**: trail dissolves
- **T_DISSOLVE_START → T_DISSOLVE_END** (runestone only): stone lights up after trail fades

**Guard against zero-divide:**
```python
t_head = min(1.0, t_frac / T_TRAIL_COMPLETE) if T_TRAIL_COMPLETE > 0 else 1.0
```

**Approved timing values (registered in clip registry):**
```python
T_TRAIL_COMPLETE  = 0.70
T_FADEOUT_START   = 0.75
T_FADEOUT_END     = 1.00
```

---

### 4.2 Tessa Stitch Workflow: Kling Magic Dissipates First, Then Ground Trail

**The problem Kim described:** Tessa's Kling-generated clip has AI-rendered shell magic that lasts the full 5 seconds. Compositing our ground trail ON TOP of that produces 5 seconds of overlapping magic, which looks cluttered and wrong.

**The approved workflow:**
1. Take the base Kling clip WITHOUT AI shell magic (the raw `beat01_tessa_exit_right_v3.mp4`)
2. Composite the ground trail magic onto it: trail grows under her feet and travels right
3. Stitch: `[Kling animated clip (5s)] + [magic trail on still frame (4s)]`
4. The Kling clip shows Tessa walking; the still+magic clip shows the trail traveling off-screen after she exits

**Why this ordering:** The Kling AI animation has Tessa moving. Once she exits frame, a still frame continuation with the magic trail is natural — the motion stops, the magic continues. This is cleaner than having both AI and rendered magic compete simultaneously.

**The held-still portion:** The last frame of the Kling clip is extracted and used as the static background for the magic-trail-only portion. This ensures no visual discontinuity at the stitch point.

---

### 4.3 Runestone: Magic Completes Before Burst

**The timing rule Kim stated:** "Wait till the rendered magic completes its way ALL the way to the runestone, and THEN have it burst into light after the magic rendering has STOPPED."

This is enforced in the clip by:
1. Trail travel phase ends and trail holds at runestone (T_TRAIL_COMPLETE = 0.70)
2. Short hold: trail fully formed on stone (0.70 → 0.75)
3. Trail fades (0.75 → 1.00 of trail clip)
4. Cut to runestone-awake image — the burst reads as a consequence of the magic arrival, not a simultaneous event

**Do not run burst and trail simultaneously.** The burst should visually feel like the trail "delivered" energy that then ignites the stone.

---

## Part 5 — Stitch Gate and Clip Registry

### 5.1 The v2 Full Sequence Failure — Root Cause

**What happened:** A full 17-second sequence (`beat02_event1_full_sequence_v2.mp4`) was assembled using:
- Clip 1: `beat01_tessa_exit_stitched_v1.mp4` — this IS the approved magic stitch ✓
- Clip 2: `beat02_heartwood_magic_v1.mp4` — also correct ✓
- Clip 3: `beat02_runestone_magic_v3.mp4` — base clip, pending status ✗

But the rendered v2 also had the Tessa clip with no visible magic (the trail wasn't showing), and the heartwood clip was wrong. This happened because:

1. No registry gate — the stitch script pulled clips by filename pattern, not from the approved registry
2. The Tessa filename in the script happened to point to a base clip (no magic), not the approved magic stitch
3. The runestone clip was pending, not approved — should never have been stitched

**The fix (now locked into the system):** `resolve_stitch_clips()` in `magic_compositor.py` MUST be called before any ffmpeg concat or imageio stitch operation. It:
- Loads `magic_clip_registry.json`
- Builds a lookup: `source_clip_filename → magic_clip` (approved entries only)
- Substitutes approved magic clips for any matching source clip in the stitch list
- Logs each substitution
- Leaves clips with `status="pending"` as-is (does not substitute)

**Never assemble a sequence from filenames alone. Always go through the registry.**

---

### 5.2 Registry Gate: Always Approved Status Only

The registry has three statuses: `approved`, `pending`, `none`.

- `approved`: Kim has explicitly confirmed the clip. May be used in stitched sequences.
- `pending`: Rendered but not yet approved. NEVER auto-substitute into a stitch.
- (no entry): Base clip. Will be used as-is unless an approved magic version exists.

**The runestone burst (`beat02_runestone_magic_v3.mp4`) is currently `pending`.** Kim said "ok thats good enough approved" about the runestone clip during the session, but this was in the context of the isolated preview, not the stitched sequence. The registry must be manually updated after Kim's explicit approval of each clip in context.

---

### 5.3 Full Sequence Registry Entry

The approved full sequence (`beat02_event1_full_sequence_v1.mp4`) is registered as a composite entry:
```json
{
  "scene_key": "full_sequence_beat02_event1",
  "source_clip": null,
  "magic_clip": "beat02_event1_full_sequence_v1.mp4",
  "status": "approved",
  "notes": "Do not re-stitch without explicit instruction."
}
```

`source_clip: null` means there is no single source clip — this is the output of a multi-clip assembly. The `resolve_stitch_clips()` function guards against `Path(None)` with an `and entry.get("source_clip")` check.

---

## Part 6 — Production Workflow

### 6.1 Preview Before Full Render (Mandatory)

**Never render a full video without Kim seeing a preview first.** A full render takes 2–5 minutes. If the aesthetics are wrong, that time is wasted.

**The preview gate:**
1. Render ONE frame at `T_TRAIL_COMPLETE` (the frame where the trail is fully formed)
2. Save as PNG
3. Show Kim the PNG
4. Only proceed to full video render after Kim approves the preview

The `get_preview_frame_idx(n_frames, T_TRAIL_COMPLETE=0.70)` helper in `magic_compositor.py` computes the right frame index.

---

### 6.2 Kim Feedback Delta Table (Max 2 Iterations Before Asking)

Do not guess at parameter changes when Kim gives qualitative feedback. Use this table:

| Kim says | Parameter change |
|----------|-----------------|
| "too bright" | `sparkle_gain × 0.75`, `ambient_gain × 0.80` |
| "too faint / can't see it" | `sparkle_gain × 1.30`, `ambient_gain × 1.25` |
| "too high / floating" | `SCATTER_Y × 0.65`, `blur_yx[0] × 0.65` |
| "too wide" | `SCATTER_X × 0.75`, `blur_yx[1] × 0.75` |
| "too fast" | `T_TRAIL_COMPLETE × 1.25` (slower travel) |
| "too slow" | `T_TRAIL_COMPLETE × 0.75` (faster travel) |
| "blobby / not sparkly" | reduce `dot_sizes` max, reduce `amb_arr × AMBIENT_MIX` |
| "jerky / popping" | verify pre-placed particle system; check for per-frame recomputation |

**After 2 iterations with no approval: STOP and ask Kim exactly what she wants changed, rather than guessing a third time.**

---

### 6.3 Style Status and Lock Protocol

New magic styles must follow this path before production use:

1. Add to `STYLES` dict in `magic_compositor.py` with `status: "draft"`
2. Render preview → show Kim
3. If approved: update `status: "approved"`, register in Directus `prod_locked_decisions`
4. Add to `KNOWN_SCENES` with source_clip and source_frame_sha
5. Register in `magic_clip_registry.json` with `status: "approved"`

**Current style status:**
| Style | Status | Directus LD |
|-------|--------|-------------|
| `tessa_ori` | **approved** | id=398 |
| `wide_ori` | draft | none |
| `burst` | pending | none |

Do not use draft or pending styles in production sequences.

---

### 6.4 No API Cost for Compositor Work

The entire visible magic compositor (PIL, numpy, scipy) runs locally with zero API cost. No FLUX, Kling, or ElevenLabs is involved.

**Therefore:** Do not spawn Opus agents for compositor work. Do not defer compositor iteration to a new session "to save credits." There are no credits to save. Run directly in the current session.

---

## Part 7 — Known Failure Modes (Complete Table)

| Symptom | Root cause | Fix |
|---------|-----------|-----|
| Magic invisible on bright background | Screen blend used | Switch to additive: `np.clip(base + trail, 0, 255)` |
| Magic invisible even with additive | Ambient blur radius too large (22px+) | Set `radius = 6px` or `AMBIENT_BLUR_YX = [6.0, 28.0]` |
| Trail washes to pure white | Screen blend compounding on N layers | Accumulate all into float32, one composite at end |
| Trail "floating" above floor | `blur_yx[0] > 8px` or `SCATTER_Y > 5%` | Reduce Y-sigma and scatter_y_frac |
| Hard horizontal slice in trail | `abs(gauss)` scatter — half-normal distribution | Use symmetric `gauss(0, sigma)` |
| Dots look like blobs | `dot_sizes` contains values > 3 | Enforce `[1,1,1,2,2,3]` |
| Jerky / popping particles | Particles re-placed each frame | Use pre-placed seeded particles, sorted by ts |
| Magic 130px off target | Eyeball positioning from thumbnail | Use `magic_position_finder.py` + Kim red-circle confirm |
| Trail cuts off / no hold phase | `t_head = t_frac` (not decoupled) | `t_head = min(1.0, t_frac / T_TRAIL_COMPLETE)` |
| `frame_idx` NameError | Missing parameter in make_trail() | Add `frame_idx=0` as default parameter |
| Wrong clip in stitched sequence | No registry gate — clips pulled by filename | Call `resolve_stitch_clips()` before any concat |
| Pending clip in approved sequence | Registry not checked for status | Filter: approved-only substitutions |
| `Path(None)` TypeError in resolver | Full-sequence registry entry has `source_clip=null` | Guard: `and entry.get("source_clip")` before Path() |
| Tessa magic + ground trail competing | Compositing on top of Kling AI magic | Use base clip (no AI magic), composite ground trail only |
| Burst happens simultaneously with trail | No sequencing — both in same frame range | Trail completes and fades before burst cut |
| Re-rendered clip uses stale path coordinates | No SHA validation | Check `source_frame_sha` before reusing KNOWN_SCENES entry |
| Directus POST 400 error on ref-doc registration | Wrong field name (`title` vs `doc_title`) | Use: `doc_title`, `doc_version`, `doc_category`, `status`, `is_current` |

---

## Part 8 — Locked Invariants (Do Not Change Without Kim + LD)

These are non-negotiable. They represent explicit Kim approvals after rejected alternatives.

| Parameter | Locked value | Why locked |
|-----------|-------------|------------|
| `DOT_SIZES` | `[1, 1, 1, 2, 2, 3]` | Larger = blobs, not sparkles |
| Blend mode | Additive only | Screen fails on bright bg; all other modes rejected |
| Scatter | Symmetric `gauss(0, sigma)` | `abs(gauss)` creates hard slice |
| `SCATTER_Y_FRAC` | 0.032 (3.2%) | Floor-flat appearance; higher = floating |
| `PALETTE` | Core=(255,255,238), Bright=(255,252,200), Mid=(255,240,155) | Warm golden-white Ori — Kim approved, teal/blue rejected |
| `AMBIENT_MIX` | 2.4 | Calibrated for glow without blowout |
| Y-sigma (ground trail) | ≤ 6px (PIL) or ≤ 8px (scipy) | Higher = floating |
| `T_TRAIL_COMPLETE` | 0.70 | Standard approved timing |
| `T_FADEOUT_START` | 0.75 | Standard approved timing |

---

## Part 9 — Tool Quick Reference

| Tool | Purpose | CLI usage |
|------|---------|-----------|
| `Production/tools/magic_compositor.py` | Rendering engine — MagicCompositor class, KNOWN_SCENES, resolve_stitch_clips() | Imported by render scripts |
| `Production/tools/magic_position_finder.py` | Debug grid + pixel detection | `--debug-image clip.mp4 --output /tmp/debug.png` |
| `Production/tools/magic_position_finder.py` | Color-threshold auto-detect | `--detect clip.mp4 --target-hint "orange crystal" --output /tmp/confirm.png` |
| `Production/tools/magic_position_finder.py` | SHA frame validation | `--sha clip.mp4` |
| `Production/tools/magic_clip_registry.json` | Approved clip lookup | Read by `resolve_stitch_clips()` |
| `.claude/skills/visible-magic/SKILL.md` | Behavioral protocol for the skill | Read at skill invocation |
| `Production/governance/visible-magic_governance.md` | Pre-flight checklist | Read at skill startup per Rule 17 |

**Trigger phrase for the skill:**
> "Use our usual process for making visible magic"

This invokes the `visible-magic` skill which reads SKILL.md, runs governance checklist, and follows the 5-phase protocol (classify → position → style → render → output).

---

## Part 10 — What Still Needs Work

1. **`wide_ori` style** — draft status only. Needs Kim preview + approval + Directus LD before production use. Path geometry for the wide heartwood clearing is in `KNOWN_SCENES` but not locked.

2. **`burst` style** — pending. `beat02_runestone_magic_v3.mp4` was described as "good enough" in isolation but was never formally approved in the stitched sequence context. Registry status remains `pending`.

3. **SHA population** — all four `KNOWN_SCENES` entries have `source_frame_sha: null`. The `--sha` command of `magic_position_finder.py` needs to be run on each source clip and the values populated. Without SHA validation, re-renders of source clips won't be detected.

4. **The "farting" perception** — Kim noted the Tessa trail starting under her feet and traveling off-screen right looks slightly like she's emitting it from below. This is partially aesthetic (the trail origin is at foot-level by design) and partially addressable by ensuring the trail starts PRECISELY at foot contact point and not mid-body. The approved version was close enough and Kim approved it; but this should be revisited when making similar ground-trail scenes with characters.

5. **Storyboard integration** — the stitch group / animation selector UI was specced out (advocate + counter-agent debate complete) but not yet built. When it is built, it must call `resolve_stitch_clips()` as its registry gate before generating any ffmpeg concat commands.
