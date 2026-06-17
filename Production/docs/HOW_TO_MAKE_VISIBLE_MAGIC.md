# How to Make Visible Magic

**Contract version:** `LD-469-VISIBLE-MAGIC-V2`  
**Code source of truth:** `Production/tools/magic_render_contract.py`  
**Compositor:** `Production/tools/magic_compositor.py`  
**Handlers:** `Production/tools/server_handlers/background.py` → `handle_magic_still`, `handle_magic_video`

This document is the permanent operator + agent reference. If visible magic looks wrong on **any** event, arc, intro, or resolution beat, start here — not in old one-off scripts under `Event_1/`.

---

## The one pipeline (forever)

Kim presses one of two Storyboard buttons. Both must produce the **same golden sparkle river** look (beat 1 approved):

| Button | API | Handler | Render path |
|--------|-----|---------|-------------|
| **Add magic on still** | `POST /api/storyboard/magic_still` | `handle_magic_still` | `MagicCompositor.render_ld469_on_background()` |
| **Add magic on video** | `POST /api/storyboard/magic_video` | `handle_magic_video` | numpy `composite_screen_rgb()` per frame |

### Non‑negotiable invariants

1. **Style:** `tessa_ori` (golden Ori river). `wide_ori` is opt-in via `scene_registry.yaml` + `force_wide_ori: true` only — never the default.
2. **Path interpolation:** `polyline` — matches `path_picker.html` `lineTo` knots. **Never bezier** for production buttons.
3. **Gain:** `1.0` at composite time. Do not calibrate gain on the black ref used for magic-on-video dimension probe.
4. **Composite:** RGB **screen** in numpy (`composite_screen_rgb`). **Not** legacy additive `_composite()`, **not** ffmpeg `blend=screen` on YUV (magenta disaster).
5. **Video luminance:** `handle_magic_video` samples the **first decoded source frame** via `set_path_luminance_from_array()` before `_make_trail()`. Black ref is dimensions only.
6. **Bright stone:** When ≥25% of path samples exceed lum 130, suppress **all sparkle dots** and use widened ambient pool only (see contract constants). Prevents white square pixels on nest stone / light paving while keeping beat‑1 look on dark forest paths.

---

## What “correct” looks like

**Golden oracle (never delete):**  
`Production/Event_1/magic_video_beat_01_20260605-211951.mp4`

- Soft **golden diffuse river** along the path on dark backgrounds  
- Crisp 1–3px sparkles visible only where background is dark enough  
- On **bright stone** (resolution beat 21 nest ring): same golden **ambient pool**, **no** blocky white squares

---

## Storyboard wiring (survives UI rewrites)

Buttons live in `Production/tools/storyboard-v2/src/components/BeatMagicButtons.tsx`:

- Still → `/magic?mode=magic_still&return_endpoint=/api/storyboard/magic_still`
- Video → `/magic?mode=magic_video&return_endpoint=/api/storyboard/magic_video`
- Both pass `scope_event_id` + `scope_video_role` (intro / resolution / phase_a / phase_b — **required**, no default to intro)

Path picker writes `magic_manual_path` + `magic_path_authored_against` back through the handler into `production_state.json` and Beat Gen sidecar.

---

## All events and arcs

The contract is **global** — not Event_1-specific:

- Any `Event_N`, any arc, intro or resolution: same compositor branch logic  
- Per-beat overrides allowed only in `scene_registry.yaml`: `style`, `duration_s`, `manual_path` pin — **not** a second compositor code path  
- Style resolver: `beat_generator.resolve_magic_style_for_render()` → defaults `tessa_ori`

Deploy Python changes tooling → Dropbox → parity → restart. See `mindfulnest-operator-workflow.mdc`.

---

## Forbidden (causes regressions)

| Do not | Why |
|--------|-----|
| `render_video(black_bg=True)` + ffmpeg screen overlay in handlers | YUV magenta; wrong luminance; June 2026 regression |
| `path_interp="bezier"` on production buttons | Misses path_picker interior knots on orbital paths |
| Additive `bg + trail` on bright stone | Clips to harsh white squares |
| Calibrate `_gain` on black ref for magic-on-video | Attenuates ambient pool → blocky pixels |
| Pin `wide_ori` for nest without explicit approval | Wrong thicker beam look |
| Use `composite_magic_path_tessa.py` / v6 scripts in production | Reference-only; not wired to buttons |
| Skip `set_path_luminance_from_array` on video | Bright-stone branch never fires |

---

## Verify before saying “done”

```bash
# From mindfulnest-tooling repo root (Kim does not run — agent runs):
bash Production/scripts/verify_visible_magic_contract.sh
bash Production/scripts/verify_o3_intro_contract.sh   # includes magic suite
python3 Production/scripts/verify_tooling_dropbox_parity.py  # after mirror
```

User-path proof after deploy:

1. `curl -s -o /dev/null -w "%{http_code}" http://localhost:5111/` → 200  
2. Re-render one bright-stone beat (e.g. resolution beat 21) via magic-on-video  
3. Visual: soft golden arc on stone, no white square trail  

---

## CI / durability gates

| Gate | What it enforces |
|------|------------------|
| `test_magic_render_contract_durability.py` | Handler wiring, forbidden patterns, bright-stone behavior |
| `test_magic_golden_beat01_replay.py` | Beat 1 golden replay within threshold |
| `verify_visible_magic_contract.sh` | Runs magic pytest subset on every tooling deploy |
| `.cursor/rules/visible-magic-contract.mdc` | Agent always applies contract when touching magic |
| `verify_tooling_dropbox_parity.py` | `magic_compositor.py`, `magic_render_contract.py`, `background.py` sha match |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| White square pixels on stone | Sparkle layer on bright bg | Confirm bright-stone branch fires; video must sample real frame lum |
| Magenta overlay | ffmpeg YUV screen | Use numpy `composite_screen_rgb` only |
| Wrong path vs picker | bezier or missing `path_authored_against` | polyline + dimension match |
| Too faint on stone | amb_mix too low for bright branch | Tune `BRIGHT_STONE_AMB_MIX` in contract module + test |
| Too blocky on forest | sparkle not suppressed incorrectly | Check `BRIGHT_STONE_PATH_FRACTION` — beat 1 must stay standard |
| “Fixed in tooling only” | Dropbox not mirrored | rsync + parity + restart |

---

## Change process

1. Edit `magic_render_contract.py` constants (not scattered magic numbers)  
2. Update `magic_compositor.py` to import from contract  
3. Extend `test_magic_render_contract_durability.py` if behavior changes  
4. Update this doc if invariants change  
5. Full QA: pytest + mirror + parity + restart + visual proof on bright **and** dark path beats  

**Never merge a magic fix without a contract test that would have caught the June 2026 regression.**
