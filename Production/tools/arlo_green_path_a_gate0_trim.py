#!/usr/bin/env python3
"""One-shot Gate 0 cutout — exact Kim-approved vJ recipe. No variants.

See Production/docs/ARLO_GREEN_PATH_A_GATE0_CUTOUT_RECIPE_v1.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

# Allow `python3 Production/tools/arlo_green_path_a_gate0_trim.py`
_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from arlo_green_path_a_assets import (  # noqa: E402
    APPROVED_COMPOSITE_REL,
    CLOSED_MOUTH_TRIMMED_REL,
    PLATE_REL,
    TRIMMED_STILL_ALIAS_REL,
    TRIMMED_STILL_REL,
    canonicalize_still_to_plate,
    composite_trimmed_still_on_plate,
    spillkill_warm_edge_vj,
)

# Closed-mouth oracle gate (Kim 2026-07-31). Tail crop must stay this clean.
TAIL_CROP = (slice(200, 650), slice(1400, 1620))
MAX_TAIL_G_MINUS_R = 3
# HIS-right body edge (viewer left): count neon-ish crumbs on character edge only.
# Do NOT use raw max G-R on the crop — wizard-hat greens live there on the plate.
HIS_RIGHT_REGION = (slice(400, 850), slice(700, 920))
MAX_HIS_RIGHT_EDGE_NEON = 30


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tail_max_gr(rgb: np.ndarray) -> int:
    crop = rgb[TAIL_CROP]
    return int((crop[:, :, 1].astype(int) - crop[:, :, 0].astype(int)).max())


def _his_right_edge_neon_count(comp: np.ndarray, still_rgb: np.ndarray, key_rgb) -> int:
    """Neon crumbs on character edge in HIS-right region (not plate hat greens)."""
    from scipy.ndimage import binary_dilation, binary_erosion

    from arlo_green_path_a_assets import _residual_neon_edge_mask

    key = np.array(key_rgb, dtype=np.float32)
    dist = np.linalg.norm(still_rgb.astype(np.float32) - key.reshape(1, 1, 3), axis=2)
    char = dist >= 55.0
    struct = np.ones((3, 3), dtype=bool)
    edge = binary_dilation(char, structure=struct, iterations=2) & ~binary_erosion(
        char, structure=struct, iterations=1
    )
    region = np.zeros(comp.shape[:2], dtype=bool)
    region[HIS_RIGHT_REGION] = True
    neon = _residual_neon_edge_mask(comp.astype(np.float32))
    # Also Lab-green fringe (closed archive had olive edge with low G-R but a*<−2)
    from skimage.color import rgb2lab

    a_star = rgb2lab(comp.astype(np.float64) / 255.0)[:, :, 1]
    greenish = neon | ((a_star < -2.0) & (comp[:, :, 0] < 140))
    return int((edge & region & greenish).sum())


def _mouth_zoom(rgb: np.ndarray, out: Path, label: str) -> None:
    h, w = rgb.shape[:2]
    crop = rgb[int(h * 0.42) : int(h * 0.58), int(w * 0.42) : int(w * 0.58)]
    z = Image.fromarray(crop).resize(
        (crop.shape[1] * 3, crop.shape[0] * 3), Image.Resampling.NEAREST
    )
    canvas = Image.new("RGB", (z.width, z.height + 28), (20, 20, 20))
    canvas.paste(z, (0, 28))
    ImageDraw.Draw(canvas).text((6, 6), label, fill=(255, 255, 255))
    canvas.save(out)


def run_gate0(
    *,
    production_root: Path,
    source_rel_or_abs: str,
    mode: str,
) -> dict:
    if mode not in ("openmouth", "closed"):
        raise ValueError("mode must be openmouth or closed")

    root = Path(production_root).expanduser().resolve()
    plate = root / PLATE_REL
    if not plate.is_file():
        raise FileNotFoundError(plate)

    src = Path(source_rel_or_abs)
    if not src.is_file():
        src = root / source_rel_or_abs
    if not src.is_file():
        raise FileNotFoundError(source_rel_or_abs)

    if mode == "openmouth":
        out_still = root / TRIMMED_STILL_REL
        out_alias = root / TRIMMED_STILL_ALIAS_REL
        out_comp = root / APPROVED_COMPOSITE_REL
        closed = root / CLOSED_MOUTH_TRIMMED_REL
        if out_still.resolve() == closed.resolve():
            raise RuntimeError("refusing to overwrite closed-mouth archive")
        if "openmouth" not in out_still.name:
            raise RuntimeError("openmouth mode must write *openmouth* filename")
    else:
        out_still = root / CLOSED_MOUTH_TRIMMED_REL
        out_alias = root / "NEW STYLE CHARACTERS/ARLO/arlo_still_green_trimmed.png"
        out_comp = root / (
            "NEW STYLE CHARACTERS/ARLO/arlo_gate0_approved_composite_trimmed_v1.png"
        )

    proof = root / "Event_6/_proof_arlo_green_path_a"
    proof.mkdir(parents=True, exist_ok=True)

    # Steps 0–5 (recipe doc)
    rgb = canonicalize_still_to_plate(src, plate)
    trimmed, key = spillkill_warm_edge_vj(rgb)
    Image.fromarray(trimmed).save(out_still)
    shutil.copy2(out_still, out_alias)

    # Step 6 — composite + QC
    comp = composite_trimmed_still_on_plate(out_still, plate)
    Image.fromarray(comp).save(out_comp)
    tail_gr = _tail_max_gr(comp)
    if tail_gr > MAX_TAIL_G_MINUS_R:
        raise RuntimeError(
            f"Gate0 QC FAIL: tail max G-R={tail_gr} > {MAX_TAIL_G_MINUS_R}. "
            "Do not invent new variants — see ARLO_GREEN_PATH_A_GATE0_CUTOUT_RECIPE_v1.md"
        )
    his_right_neon = _his_right_edge_neon_count(comp, trimmed, key)
    if his_right_neon > MAX_HIS_RIGHT_EDGE_NEON:
        raise RuntimeError(
            f"Gate0 QC FAIL: HIS-right char-edge greenish count={his_right_neon} "
            f"> {MAX_HIS_RIGHT_EDGE_NEON}."
        )
    his_right = comp[HIS_RIGHT_REGION]

    look = proof / f"gate0_{mode}_LOOK_AT_THIS.png"
    Image.fromarray(comp).save(look)
    tail = comp[TAIL_CROP]
    Image.fromarray(tail).resize(
        (tail.shape[1] * 4, tail.shape[0] * 4), Image.Resampling.NEAREST
    ).save(proof / f"gate0_{mode}_tail_4x.png")
    _mouth_zoom(trimmed, proof / f"gate0_{mode}_mouth_zoom.png", f"{mode} trimmed mouth")
    _mouth_zoom(comp, proof / f"gate0_{mode}_mouth_zoom_on_plate.png", f"{mode} on plate")
    Image.fromarray(his_right).resize(
        (his_right.shape[1] * 2, his_right.shape[0] * 2), Image.Resampling.NEAREST
    ).save(proof / f"gate0_{mode}_HIS_RIGHT_2x.png")

    # Face crop for quick glance
    Image.fromarray(comp[220:620, 700:1220]).save(proof / f"gate0_{mode}_face_crop.png")

    # Bandana crop vs source (color fidelity)
    ban = comp[480:620, 820:1100]
    Image.fromarray(ban).resize(
        (ban.shape[1] * 2, ban.shape[0] * 2), Image.Resampling.NEAREST
    ).save(proof / f"gate0_{mode}_bandana_2x.png")

    meta = {
        "recipe": "spillkill_G_clamp + warm_edge_a*_vJ",
        "recipe_doc": "Production/docs/ARLO_GREEN_PATH_A_GATE0_CUTOUT_RECIPE_v1.md",
        "mode": mode,
        "source": str(src),
        "source_sha256": _sha256(src),
        "trimmed": str(out_still),
        "trimmed_sha256": _sha256(out_still),
        "composite": str(out_comp),
        "composite_sha256": _sha256(out_comp),
        "key_rgb": list(key),
        "qc_tail_max_g_minus_r": tail_gr,
        "qc_his_right_edge_greenish": his_right_neon,
        "qc_tail_max_allowed": MAX_TAIL_G_MINUS_R,
        "qc_his_right_edge_max_allowed": MAX_HIS_RIGHT_EDGE_NEON,
        "qc_pass": True,
        "look_at_this": str(look),
    }
    meta_path = proof / f"gate0_{mode}_trim_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    # Manifest (best-effort)
    man_path = root / "NEW STYLE CHARACTERS/ARLO/arlo_layered_assets_v1.json"
    if man_path.is_file():
        man = json.loads(man_path.read_text())
        man.setdefault("assets", {})
        role = (
            "green_still_openmouth_spillcleaned_warm_edges_v1"
            if mode == "openmouth"
            else "green_still_spillcleaned_warm_edges_v1"
        )
        man["assets"][
            "green_still_openmouth_trimmed" if mode == "openmouth" else "green_still_trimmed"
        ] = {
            "path": f"NEW STYLE CHARACTERS/ARLO/{out_still.name}",
            "role": role,
            "sha256": meta["trimmed_sha256"],
            "key_rgb": list(key),
        }
        man["gate0_openmouth" if mode == "openmouth" else "gate0"] = {
            "status": "trimmed",
            "composite_recipe": meta["recipe"],
            "key_rgb": list(key),
            "qc_tail_max_g_minus_r": tail_gr,
            "recipe_doc": "docs/ARLO_GREEN_PATH_A_GATE0_CUTOUT_RECIPE_v1.md",
        }
        man_path.write_text(json.dumps(man, indent=2) + "\n")

    return meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--production-root",
        required=True,
        help="Dropbox Production/ root",
    )
    ap.add_argument(
        "--source",
        required=True,
        help="Source green still (abs path or relative to production-root)",
    )
    ap.add_argument(
        "--mode",
        choices=("openmouth", "closed"),
        default="openmouth",
    )
    args = ap.parse_args()
    meta = run_gate0(
        production_root=Path(args.production_root),
        source_rel_or_abs=args.source,
        mode=args.mode,
    )
    print(json.dumps(meta, indent=2))
    print("QC PASS — look at:", meta["look_at_this"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
