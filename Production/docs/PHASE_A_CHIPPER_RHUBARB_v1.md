# Phase A Chipper — Rhubarb Tier B Pipeline v1

**Status:** ACTIVE (Kim session 2026-06-08)  
**Scope:** Module 1 Event 1 — frozen body plate + Preston Blair beak sprites  
**Replaces:** Kling/ByteDance full-frame lipsync on bird close-up

---

## Classification (verified Jun 8 2026)

Source folder: `Production/NEW STYLE CHARACTERS/CHIPPER/`  
Files: `ChatGPT Image Jun 7, 2026, 11_17_* PM (1–6).png` (1254×1254 bust stills)

| Phoneme | Source file suffix | Mouth shape | Rhubarb mapping |
|---------|-------------------|-------------|-----------------|
| **A** | `11_17_46 PM (1).png` | Closed / rest | M,B,P,rest; **X→A** (silence) |
| **B** | `11_17_46 PM (2).png` | Slightly parted | F,V |
| **C** | `11_17_47 PM (3).png` | Open medium + tongue | open; **G→C** |
| **D** | `11_17_47 PM (4).png` | Wide open | ah/oh vowels; **H→D** |
| **E** | `11_17_48 PM (5).png` | Small round O | oo,w |
| **F** | `11_17_48 PM (6).png` | Lower beak down | L,TH |

Manifest: `Event_1/chipper_beak_classification.json`

---

## Assets (Event_1)

| File | Role |
|------|------|
| `phase_a_chipper_body_plate_v1.png` | Frozen middle frame (1280×960) |
| `chipper_beak_sprites/chipper_beak_{A-F}.png` | Cropped beak overlays |
| `chipper_beak_config.json` | Placement fractions |
| `phase_a_voice_stem_*.mp3` | TTS audio (Rhubarb input via wav convert) |

---

## CLI pipeline (zero API cost)

```bash
# 1. One-time: build arm64 Rhubarb (Kim Mac)
bash Production/scripts/setup_rhubarb_arm64.sh

# 2. Prep sprites from ChatGPT stills
python3 Production/tools/phase_a_chipper_beak_prep.py

# 3. Composite middle segment
python3 Production/tools/phase_a_chipper_rhubarb_composite.py

# 4. Pin + restitch (server on :5111)
python3 Production/tools/phase_a_v3_execute_fix.py \
  --stitch-only chipper_lipsync_rhubarb_<ts>.mp4
```

---

## Beak placement

Measured from body plate dark-beak centroid:

- `beak_cx_frac`: 0.535  
- `beak_cy_frac`: 0.460  
- `sprite_w_frac`: 0.22  
- `sprite_h_frac`: 0.14  

Tune in `chipper_beak_config.json` if overlay sits high/low.

---

## QA checklist

1. `pytest Production/tools/tests/test_rhubarb_processor.py -v`
2. `pytest Production/tools/tests/test_phase_a_stitch_resolve.py -v`
3. Composite duration ≈ voice stem duration (~43.4s)
4. Wings static (frozen plate — no regen)
5. Deploy: `bash Production/scripts/deploy_storyboard_v59.sh`
6. Preview: `localhost:5111` → Phase A stitched player

---

## Rejected (do not reintroduce)

- Kling/ByteDance full-frame bird lipsync (teeth, wing-hands)
- AI face composite with static polygon mask (ghost artifacts)
