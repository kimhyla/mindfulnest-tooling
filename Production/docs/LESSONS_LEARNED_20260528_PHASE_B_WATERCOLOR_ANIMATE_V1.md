# Lessons Learned — Phase B Watercolor Animate (hands_rubbing fix)

**Date:** 2026-05-28  
**Session:** Storyboard v59 Phase B overlay preview + animate pipeline  
**Status:** RESOLVED — Kim verified visually (“IT WORKED!!!!”)  
**Canonical implementation:** `WATERCOLOR_ANIMATE_PROCEDURAL_TECH_SPEC_v2.md`  
**Locked decision:** `WATERCOLOR_ANIMATE_PIL_RENDERER_V1` (supersedes Claude-era `WATERCOLOR_ANIMATE_PROCEDURAL_V1` / LD-470)  
**Recipe pin:** `wc_v13_hand_only_split` (`ffmpeg_stitch.WATERCOLOR_OVERLAY_RECIPE_VERSION`)

---

## Executive summary

Phase B watercolor “Animate this” must produce a **short MP4** where:

1. The **white paper frame stays fixed** (no bounce, no shear, no slice).
2. Only **hand pigment** moves — center-split, opposite-direction rub along the path axis.
3. The compositor (`Preview with Overlay` / Stitcher) chromakeys magenta and overlays at `frame_x`/`frame_y`.

The May 27–28 regressions came from treating the animate step as “move the whole PNG” or “split everything that isn’t pure white.” Both recreate v2-class bugs.

---

## LL-WCA-1 — LD-470 intent ≠ “move whole PNG along path”

**What happened:** Commit `169d570` (May 27) made PIL translate the **entire** watercolor PNG along the drawn path on a 2× magenta canvas. The compositor then scaled the whole bounding box → white card bounced, wrong scale, magenta fringe.

**Lesson:** Path points define **placement on the fireplace** (compositor `frame_x`/`frame_y`) and **rub axis direction** — not travel distance for the encode clip.

**Permanent rule:** Encode clip = tight crop around asset; motion = small offset **inside** the clip only.

---

## LL-WCA-2 — LD-470 original spec was “split frame” (Claude+ffmpeg), not whole-image translate

**What happened:** Pre-`5a09000`, `handle_watercolor_animate` called Claude to emit ffmpeg `filter_complex`. The system prompt example for hands rub:

> split frame at line, vflip lower half, oscillate y-translation sinusoidally

**May 27 replacement** (`5a09000`) dropped Claude for reliability but initially implemented **fade/sweep / whole-PNG translate** — losing center-split rub semantics.

**Lesson:** Reliability fix must **preserve motion semantics**, not drop them. Deterministic PIL should implement the same geometry Claude was asked for.

---

## LL-WCA-3 — “Not pure white = hand” misclassifies ~222k pixels (frame slice bug)

**What happened:** Classifier `if not (r>245 and g>245 and b>245): hand` on `hands_rubbing.png` tagged:

| Class | Pixels | Must move? |
|-------|--------|------------|
| Cream paper texture | ~147k | **NO** |
| Black border | ~75k | **NO** |
| Actual hand pigment | ~205k | **YES** |

Left/right “hand” halves included cream + border → **entire white card sheared ~±36px** (top edge shifted relative to bottom). Kim: “entire frame got sliced in half instead of just the hands.”

**Permanent rule (wc_v13):** Three-layer encode:

1. **Solid white underlay** — full matte bbox (fills rub gaps; prevents chromakey holes).
2. **Fixed frame layer** — cream + border + pure white from source (never moves).
3. **Split hand pigment only** — center seam at hand-bbox center; opposite oscillation along path axis.

**Pixel rules:**

```text
border:  r,g,b < 80
paper:   r,g,b > 245 (all channels)
cream:   (r+g+b) > 700 AND max-min < 35
hand:    everything else with alpha ≥ 20
```

---

## LL-WCA-4 — Paper mask excluding hands → chromakey holes (transparent spots)

**What happened:** wc_v10 split “fixed paper” vs “moving hands” by **excluding hand pixels from paper mask**. When hand halves moved, vacated areas had **magenta only** → compositor chromakey → Cedric visible through white (“little transparent spots”).

**Lesson:** Same bug class as v2 **green chromakey edge-eating** (`5d69c18` audit): keyed-out pixels where opaque matte should remain.

**Permanent rule:** Solid white underlay under **all** hand-rub travel; never rely on paper mask alone under moving pigment.

---

## LL-WCA-5 — `motion_description` is read by **server PIL**, not Claude

**What happened:** `path_picker.html` still said “Used by Claude API to generate ffmpeg filter chain” (stale from LD-470 Claude era). Kim reasonably assumed the animator text drove Claude/ffmpeg.

**Actual behavior (2026-05-28):** `motion_description` is POSTed to `/api/watercolor/animate` and parsed **deterministically** in `background.py`:

| Keywords in description | `_osc_freq` | Effect |
|-------------------------|-------------|--------|
| rub, friction, heat, warm, brisk, quick, fast, opposite, up and down, … | 2.5 Hz | Fast rub |
| gentle, slow, soft, drift, float, sway, pulse, breathe, … | 0.75 Hz | Slow drift |
| (default) | 1.5 Hz | Moderate |

Path geometry sets **rub direction** (vertical path → left/right hand halves rub on Y).

**Permanent rule:** UI copy must say server-side PIL renderer, not Claude. See tech spec §4.

---

## LL-WCA-6 — Compositor must not pan animated video cues

**What happened:** `gentle_pan` on video cues moved the whole keyed tile (wc_v8 fix: static `x` for `cue_type=="video"`).

**Permanent rule:** All rub motion is **baked in the MP4**; compositor only chromakeys + scales + overlays at fixed `(frame_x, frame_y)`.

---

## LL-WCA-7 — Recipe version bump invalidates stale preview cache

**What happened:** Fixed encode but Kim still saw old behavior until **re-animate** + new preview (cached `phase_b_preview_*.mp4` keyed on `WATERCOLOR_OVERLAY_RECIPE_HASH`).

**Permanent rule:** Any change to `handle_watercolor_animate` or `render_watercolor_overlay` filter semantics → bump `WATERCOLOR_OVERLAY_RECIPE_VERSION` and re-animate affected assets.

---

## LL-WCA-8 — Kim verification gate

**Rule:** No animate/compositor fix is “done” until Kim runs **Preview with Overlay** at cue time and approves visually. API/frame metrics are supplementary.

---

## Regression checklist (run after any animate/compositor change)

1. Re-animate test asset: `hands_rubbing` with vertical path + “hands rubbing together vertically for warmth”.
2. Encode metrics on vacated hand pixels (frame 0→6): magenta count **≈ 0**, white count high.
3. Frame shear: top vs bottom white edge `x` shift **≈ 0 px** (was ±36px pre-v13).
4. Composited preview at cue: no stone-wall bleed through white margins; hands rub in opposite phase.
5. `WATERCOLOR_OVERLAY_RECIPE_VERSION` bumped; preview cache miss confirmed.

---

## Related locked decisions & docs

| Artifact | Role |
|----------|------|
| `WATERCOLOR_ANIMATE_PIL_RENDERER_V1` | Locked implementation contract (supersedes Claude LD-470) |
| `WATERCOLOR_ANIMATE_PROCEDURAL_TECH_SPEC_v2.md` | Full technical spec |
| `background.py` → `handle_watercolor_animate` | Deterministic encoder |
| `ffmpeg_stitch.py` → `wc_v13_hand_only_split` | Compositor recipe pin |
| `path_picker.html` | Motion description UI (must match server behavior) |

---

## v2 parallel (why Kim said “same trouble as v2”)

| v2 symptom | 2026-05-28 root cause | wc_v13 fix |
|------------|----------------------|------------|
| White box bouncing | Whole PNG / paper translated | Fixed frame + hand-only motion |
| Holes in white | Magenta under hands / chromakey | Solid white underlay |
| Frame sliced in half | Cream+border classified as “hand” | Strict pixel classes; fixed frame layer |
| multiply ate white (CSS) | `mix-blend-mode: multiply` | `normal` (e1ccbb7) — browser lipsync preview only |
| Green chromakey ate edges | Green canvas + tight similarity | Magenta canvas + 0.25 similarity (wc_v4/v5) |

---

**Filed:** 2026-05-28 — register in `prod_reference_docs` + `prod_locked_decisions` per Rule 15 / Rule 18.
