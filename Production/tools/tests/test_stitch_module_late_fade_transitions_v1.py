"""STITCH_MODULE_LATE_FADE_TRANSITIONS_V1 contract tests."""
from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from credentials_lib import ffmpeg_stitch as fs  # noqa: E402
from server_handlers import stitch_editor as se  # noqa: E402


def test_default_transitions_per_boundary_budgets() -> None:
    transitions = se.default_stitch_transitions()
    assert [t["fade_ms"] for t in transitions] == [2800, 3800, 3800]
    assert all(t["audio_xfade_ms"] == 0 for t in transitions)
    assert all(t["kind"] == "dissolve" for t in transitions)


def test_late_fade_budget_black_in_middle() -> None:
    out_ms, in_ms, black_ms = fs.allocate_pair_fade_budget(
        3800,
        visual_out_ms=se.STITCH_MODULE_VISUAL_OUT_MS,
        visual_in_ms=se.STITCH_MODULE_VISUAL_IN_MS,
    )
    assert out_ms == 200
    assert in_ms == 200
    assert black_ms == 3400


def test_phase_b_to_resolution_no_outgoing_visual_fade() -> None:
    outs = se.module_boundary_visual_out_ms_by_pair(3, 600)
    assert outs == [200, 200, 0]
    out_ms, in_ms, black_ms = fs.allocate_pair_fade_budget(
        3800,
        visual_out_ms=outs[2],
        visual_in_ms=se.STITCH_MODULE_VISUAL_IN_MS,
    )
    assert out_ms == 0
    assert in_ms == 200
    assert black_ms == 3600


def test_plan_module_lipsync_reframe_always_v3_on_720p(tmp_path: Path) -> None:
    from phase_module_lipsync_delivery import plan_module_lipsync_reframe  # noqa: PLC0415

    src = tmp_path / "delivered.mp4"
    subprocess = __import__("subprocess")
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=24:duration=0.4",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=0.4",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(src),
        ],
        check=True,
        timeout=60,
    )
    plan = plan_module_lipsync_reframe(src)
    assert plan["mode"] == "canonical_v3"
