# POV motion — Kling O3 Pro image-to-video runbook v1

**Status:** Validated (Jun 2026) — wand POV windshield-wiper clip  
**Script:** `Production/tools/scripts/run_o3_pov_motion_i2v.py`  
**Not for:** Avatar Pro speak, Element native `@Image1` dialogue, Still Insert Ken Burns

---

## What this is

Short **motion-only** clips from a **single POV still**: child’s hand + wand move; background locked. Uses **Kling O3 Pro image-to-video (single start frame)** via WaveSpeed — same vendor family as Omni, but **not** the speak/lipsync stack.

---

## Quality & settings (locked recipe)

| Setting | Value | Why |
|---------|-------|-----|
| Model | `kling-video-o3-pro/image-to-video` | Pro tier (`tier=pro`) — best motion fidelity |
| Mode | `o3_image_to_video_single` | One PNG in; no `@Image1` Element, no end frame |
| Duration | **5s** | ~2 windshield-wiper cycles |
| Sound | **false** | Silent clip (mux Lorelai TTS later if needed) |
| `shot_type` | `customize` | WaveSpeed API default in client |
| Input still | **1280×720** LANCZOS upscale | Source was 1024×576; shortest side &lt; 600px rule |
| Delivery | `voice_first_upscale` + **sharpen** | 1280×720 H.264 ≤1.9 Mbps +faststart (same as Beat Gen ship path) |
| Raw Kling output | Typically **1920×1080** @ 24fps | Downloaded before delivery encode |

**Do not use:** Avatar Pro, Element native O3 speak, Still Insert / Ken Burns (no articulated wand motion).

---

## One-command reproduce

From `mindfulnest-tooling/Production/tools`:

```bash
python3 scripts/run_o3_pov_motion_i2v.py \
  --image "/path/to/pov_still.png" \
  --out-dir "$HOME/Projects/MindfulNest/.runtime_wand_wiper" \
  --duration 5 \
  --tier pro
```

Outputs under `--out-dir`:

- `pov_start_1280x720.png` — prepared input
- `manifest.json` — full settings + task_id + prompt
- `pov_motion_o3_pro_<ts>_raw.mp4` — Kling download
- `pov_motion_o3_pro_<ts>_delivery.mp4` — ship-quality encode

Preview: open `index.html` in that folder (or `python3 -m http.server` in the dir).

---

## Prompt (copy-paste)

```
First-person POV shot. Camera completely locked — no zoom, no pan, no camera move, no parallax drift. Child's hand at bottom-right of frame grips a magic wand with a large glowing green crystal tip. The hand and wand sweep smoothly left and right in wide arcs like windshield wipers — two full back-and-forth cycles over the clip. Enchanted forest background with mossy tree trunks, turquoise river, and stone pillars stays perfectly static. Subtle magical glow pulses from the green crystal on each pass. Hand anatomy stable; wand is rigid gnarled wood with small green leaves. No dialogue, no voice, no music, no ambient sound. No face visible. Avoid: camera movement, zoom, morphing trees, bending wand, extra hands, talking.
```

**Send the full composite as-is** — do not split hand/wand from background for v1.

**Plan B** if motion is weak: paint start + end stills (wand at opposite arc) and use `kling_o3_client.run_startend_generation()` instead.

---

## Import into Beat Gen (video container)

Slots **0–2** are fixed containers (`slot_index` on each `kling_o3_options` row).

```bash
python3 scripts/run_o3_pov_motion_i2v.py \
  --delivery-mp4 "/path/to/pov_motion_o3_pro_*_delivery.mp4" \
  --import-beat bg_arc1_event3b_full_beat_12 \
  --slot 0 \
  --milestone milestone1_arc1 \
  --event-dir Event_1 \
  --label "POV wand wiper (O3 i2v)"
```

**UI vs sidecar beat numbers:** Storyboard labels beats **1–11** in list order. There is no `beat_05` or `beat_11` in event3b_full, so **UI Beat 10 = `bg_arc1_event3b_full_beat_12`** (POV wand stage direction) — **not** `beat_10` (Oliver dialogue, UI Beat 9).

- Copies clip to `Event_1/kling_o3_clips/<beat_id>_gN_pov_wand_wiper_delivery.mp4`
- Appends option with `source: o3_pov_motion_i2v`
- **Default:** does **not** change the active/approved pointer (`--make-active` to select)

Hard-refresh Storyboard after import.

---

## Validated run (Jun 25 2026)

| Field | Value |
|-------|-------|
| Source still | Kim’s POV wand PNG (1024×576) |
| Task ID | `1ad4301ec1df4893b5755e94eceb851a` |
| Raw | 1920×1080 · 5.04s · ~14 Mbps |
| Delivery | 1280×720 · 5.04s · ~1.88 Mbps |
| Local artifacts | `MindfulNest/.runtime_wand_wiper/` |

---

## Optional Lorelai “whoa…”

Generate **silent** motion first. Mux ElevenLabs TTS under the delivery mp4 with ffmpeg — do not route through Avatar Pro (no on-screen portrait).

---

## Dependencies

- WaveSpeed API key in Dropbox `Production/API_KEYS_MASTER.md` (`load_api_keys()`)
- Python deps: `PIL`, tooling `kling_o3_client`, `video_delivery`, `beat_generator`
- Milestone sidecar: `Production/Milestones/milestone1_arc1/beat_generator_sidecar.json`
