"""Watercolor overlay geometry must match production_server frame constants."""
import re
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def _parse_server_phase_bbox() -> dict[str, dict[str, int]]:
    server = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    frame_x = re.search(r"_PHASE_FRAME_X\s*=\s*\{([^}]+)\}", server)
    frame_y = re.search(r"_PHASE_FRAME_Y\s*=\s*(\d+)", server)
    frame_max_w = re.search(r"_PHASE_FRAME_MAX_W\s*=\s*\{([^}]+)\}", server)
    frame_max_h = re.search(r"_PHASE_FRAME_MAX_H\s*=\s*\{([^}]+)\}", server)
    assert frame_x and frame_y and frame_max_w and frame_max_h

    def parse_pair_map(blob: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for part in blob.split(","):
            if ":" not in part:
                continue
            k, v = part.split(":", 1)
            out[k.strip().strip('"\'')] = int(v.strip())
        return out

    xs = parse_pair_map(frame_x.group(1))
    ws = parse_pair_map(frame_max_w.group(1))
    hs = parse_pair_map(frame_max_h.group(1))
    y = int(frame_y.group(1))
    return {
        phase: {
            "frameX": xs[phase],
            "frameY": y,
            "maxW": ws[phase],
            "maxH": hs[phase],
        }
        for phase in ("a", "b")
    }


def _parse_ts_server_bbox() -> dict[str, dict[str, int]]:
    geom = (
        TOOLS / "storyboard-v2/src/components/phase/phaseWatercolorOverlayGeometry.ts"
    ).read_text(encoding="utf-8")
    blocks = re.findall(
        r"b:\s*\{ frameX: (\d+), frameY: (\d+), maxW: (\d+), maxH: (\d+) \}",
        geom,
    )
    a_blocks = re.findall(
        r"a:\s*\{ frameX: (\d+), frameY: (\d+), maxW: (\d+), maxH: (\d+) \}",
        geom,
    )
    assert blocks and a_blocks
    b = blocks[0]
    a = a_blocks[0]
    return {
        "b": {"frameX": int(b[0]), "frameY": int(b[1]), "maxW": int(b[2]), "maxH": int(b[3])},
        "a": {"frameX": int(a[0]), "frameY": int(a[1]), "maxW": int(a[2]), "maxH": int(a[3])},
    }


def test_watercolor_overlay_canvas_relative_percentages() -> None:
    """v17 full-bleed rounded bbox 368×508 at (64, 64) Phase B."""
    bbox_b = _parse_ts_server_bbox()["b"]
    assert bbox_b["frameX"] == 64
    assert bbox_b["frameY"] == 64
    assert bbox_b["maxW"] == 368
    assert bbox_b["maxH"] == 508
    assert abs((bbox_b["maxH"] / 720) * 100 - 70.555555) < 0.01


def test_watercolor_overlay_geometry_matches_production_server() -> None:
    server = _parse_server_phase_bbox()
    ts = _parse_ts_server_bbox()
    assert ts == server


def test_watercolor_overlay_recipe_version_wc_v17() -> None:
    """Preview cache bust must track canonical bbox — bump invalidates stale phase_*_preview hashes."""
    stitch = (TOOLS / "credentials_lib/ffmpeg_stitch.py").read_text(encoding="utf-8")
    assert 'WATERCOLOR_OVERLAY_RECIPE_VERSION = "wc_v17_fullbleed_rounded_canonical"' in stitch
    bbox_a = _parse_ts_server_bbox()["a"]
    assert bbox_a["frameX"] == 870
    assert bbox_a["frameY"] == 64


def test_watercolor_overlay_max_height_is_seventy_percent_of_frame() -> None:
    """508/720 server frame_max_h — operator red-box canonical."""
    bbox = _parse_ts_server_bbox()
    for phase in ("a", "b"):
        pct = (bbox[phase]["maxH"] / 720) * 100
        assert abs(pct - 70.555555) < 0.01
