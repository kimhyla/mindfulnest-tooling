# Arlo green Path A — Gate 0 cutout recipe (v1)

**Status:** FINAL — closed-mouth Gate0 Kim-approved 2026-07-31; **open-mouth Gate0 Kim-approved 2026-08-05** (`gate0_openmouth_LOOK_AT_THIS.png`).  
**Do not** re-run the vA–vI fringe experiment ladder.  
**Code authority:** `Production/tools/arlo_green_path_a_assets.py` → `spillkill_warm_edge_vj` + `composite_trimmed_still_on_plate`  
**One-shot CLI:** `Production/tools/arlo_green_path_a_gate0_trim.py`

### STOP — do not restart green motion-idle circles (Kim 2026-08-08 / 2026-08-11)

Gate0 **still trim on green** is proven and kept.  
**Kling start/end motion idle on green → Kling LipSync on that full-character green video** is a **failed path**. Do not re-run it.

| What we tried | What happened |
|---------------|---------------|
| Green still → Kling motion idle | Kling **re-adds dark cutout trim** (esp. tail). Weeks of choke/deoutline. |
| LipSync on that green motion idle (full body) | Kling **redraws whole squirrel** at **832×464**: wrong finger counts, wrong hand colors, weird side faces, bad mouths. Full stem failed hard. |
| Sealed **MOUTH LOCK** idle for lipsync | Mouths stay shut / snap — Beat Gen uses **mouth relaxed**, not lock. |
| “Pin body totally still” full-body | Kim rejected unless it’s a **headshot** (body cropped out). |
| Headshot **A** frozen still → LipSync only | Mouths **worked** (2026-08-11). No motion idle involved. |

**Keep:** Gate0 still recipe + plate composite. Headshot A lipsync proof.  
**Do not:** green motion idle → LipSync loops; Avatar Pro (Chinese hallucinations); wire Phase A Send on failed full-body path.

---

## What this is for

Path A needs a **spill-clean green character still** (screen kept) so later chromakey over the static room plate has **no neon green fringe** on fur/tail/ears.

Lipsync Send stills must be **open-mouth / mouth-relaxed**. Closed-mouth Gate0 trim is **archive only**.

---

## What ultimately worked (after ~10 false starts)

| Step | Name | What it does |
|------|------|----------------|
| 0 | Size lock | Still and plate both **1920×1080**, same 16:9. If source is smaller 16:9 (e.g. 1672×941), **Lanczos** up to plate — never stretch a wrong aspect. |
| 1 | Measure key | Corner-median RGB of the green screen (closed-mouth pin was `(3,241,5)`; open-mouth ChatGPT Jul 31 measured `(2,234,8)`). **Always re-measure** per still. |
| 2 | Soft spillkill | On whole image: `G = min(G, max(R,B))`. Kills pure neon channel. |
| 3 | Aggressive G-crush (edge only) | If `G > R+5`: `G = min(G, R)` — **only** on screen-adjacent character ring. Never on interior (protects bandana teal). |
| 4 | Re-pin screen | Where `dist(pixel, key) < 55` → set pixel to **exact key**. |
| 5 | Warm-edge a* (vJ) | Character ring: where `a* < -2`: force `a* ≥ 8`, `b* += 5`. |
| 6 | Fringe choke | Peel greenish screen-touching silhouette into key (`STILL_FRINGE_CHOKE_PX=5`). |
| 7 | Hard matte + inward scrub | Erode matte (`COMPOSITE_MATTE_ERODE_PX=3`). **No soft green ring.** Scrub greenish pixels up to `COMPOSITE_INNER_SCRUB_PX=5` inside the matte → plate (protects bandana blue). |

**Judge fringe on the plate composite**, not on the green still (green PNG always shows green next to fur tips).

**Failed approaches (do not resurrect):** blue remap only; ffmpeg despill-before-key alone; nuclear erode of whole silhouette; rectangular right-half erode; whole-image aggressive `G=min(G,R)` (destroys bandana); soft-alpha green rings on plate; Avatar Pro.

---

## Operator checklist (new green still)

1. Drop source PNG into  
   `Production/NEW STYLE CHARACTERS/ARLO/`  
   (open-mouth example: `ChatGPT Image Jul 31, 2026, 01_52_54 PM.png`).
2. Confirm plate exists:  
   `arlo_room_plate_background_full_size_3_1920x1080_v1.png`.
3. Run from tooling repo:

```bash
cd /path/to/mindfulnest-tooling
export PYTHONPATH=Production:Production/tools
python3 Production/tools/arlo_green_path_a_gate0_trim.py \
  --production-root "$DROPBOX_PRODUCTION" \
  --source "NEW STYLE CHARACTERS/ARLO/ChatGPT Image Jul 31, 2026, 01_52_54 PM.png" \
  --mode openmouth
```

4. **Judge fringe on the plate composite, not on the green still.**  
   The trimmed green PNG keeps a solid chroma background. Fine fur tips will always look green-adjacent on that file — same as the closed-mouth archive Kim already approved. That is not a failed trim.  
   Look at proofs under `Production/Event_6/_proof_arlo_green_path_a/`:
   - `gate0_<mode>_LOOK_AT_THIS.png` — full composite on room plate (**this** is the fringe check)
   - `gate0_<mode>_tail_4x.png` — fringe zoom on plate
   - `gate0_<mode>_mouth_zoom.png` — mouth state
5. If QC fails (tail G−R > 3 **on the plate composite**), **stop** — do not invent a new variant in chat; fix source still or file a SHORTCUT against the recipe constants in code.
6. **Do not** auto-proceed to green Kling motion idle + LipSync (failed path — see STOP section above). Next speak method is a separate product decision (headshot lipsync lineage, etc.).

---

## Output filenames

| Mode | Trimmed still | Alias | Approved composite |
|------|---------------|-------|--------------------|
| `closed` (archive) | `arlo_still_green_trimmed_1920x1080_v1.png` | `arlo_still_green_trimmed.png` | `arlo_gate0_approved_composite_trimmed_v1.png` |
| `openmouth` (Send) | `arlo_still_green_openmouth_trimmed_1920x1080_v1.png` | `arlo_still_green_openmouth_trimmed.png` | `arlo_gate0_approved_composite_openmouth_trimmed_v1.png` |

Never overwrite the closed-mouth archive when trimming open-mouth.

---

## Idle outline (archive note — not the speak path)

Kling start/end on green **re-adds** a dark cutout stroke (esp. tail). Topology-safe
``choke_kling_idle_outline`` was built for that. That does **not** make
green-motion-idle → LipSync a good Phase A speak route (anatomy invent + 832×464).

See STOP section at top.

---

## QC oracle (closed-mouth, do not overwrite)

- Composite: `arlo_gate0_approved_composite_trimmed_v1.png`
- Proof: `Event_6/_proof_arlo_green_path_a/gate0_LOOK_AT_THIS_no_fringe.png` / `gate0_vJ_warm_edges.png`
- Tail crop max G−R on approved path: **≤ 3**

Open-mouth composites must meet the same numeric fringe gate.

---

## History (why this doc exists)

Gate 0 took many chat iterations (vA–vJ). The only durable fix is this frozen recipe + CLI. Rediscovering fringe fixes in thread is forbidden.
