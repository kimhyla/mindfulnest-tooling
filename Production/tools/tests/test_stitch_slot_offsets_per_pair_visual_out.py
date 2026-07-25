"""Slot start offsets must agree with the timeline the render actually builds.

`expand_clips_with_black_pause_boundaries` sizes each black hold from a
*per-boundary* outgoing fade (`visual_out_ms_by_pair`). `module_slot_start_offsets_ms`
only accepted a uniform `visual_out_ms`, so:

  * `stitch_editor` passing `visual_out_ms_by_pair=` raised TypeError, taking
    /api/stitch_editor/preview down with HTTP 500, and
  * had it not raised, every offset after a boundary with a non-default
    outgoing fade would have drifted from the rendered video.

These tests pass explicit per-pair lists rather than calling
`module_boundary_visual_out_ms_by_pair`, so they pin the offset arithmetic
independently of what any particular boundary map decides.
"""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from credentials_lib.ffmpeg_stitch import (  # noqa: E402
    allocate_pair_fade_budget,
    module_slot_start_offsets_ms,
)


def _expected_offsets(
    durations: list[int],
    pair_fades: list[int],
    outs_by_pair: list[int] | None,
    visual_out_ms: int,
    visual_in_ms: int,
) -> list[int]:
    """Independent model of the concat the render produces.

    Bodies keep full duration (fades are applied in place), so the timeline is
    the clip durations plus each inserted black hold.
    """
    starts = [0]
    acc = 0
    for i in range(len(durations) - 1):
        acc += durations[i]
        pair = pair_fades[i] if i < len(pair_fades) else 0
        if pair > 0:
            out = (
                outs_by_pair[i]
                if outs_by_pair is not None and i < len(outs_by_pair)
                else visual_out_ms
            )
            _, _, black = allocate_pair_fade_budget(
                pair, visual_out_ms=out, visual_in_ms=visual_in_ms,
            )
            acc += black
        starts.append(acc)
    return starts


def test_accepts_per_pair_visual_out_without_raising() -> None:
    """The exact call shape stitch_editor uses — previously a TypeError."""
    offsets = module_slot_start_offsets_ms(
        [4000, 5000, 6000, 7000],
        [1200, 1200, 1200],
        visual_out_ms=600,
        visual_in_ms=600,
        visual_out_ms_by_pair=[600, 600, 0],
    )
    assert len(offsets) == 4
    assert offsets[0] == 0
    assert offsets == sorted(offsets)


def test_zero_outgoing_fade_lengthens_the_black_hold() -> None:
    """A boundary with no outgoing dim spends that budget on black instead."""
    durations = [4000, 5000, 6000, 7000]
    pair_fades = [1200, 1200, 1200]

    uniform = module_slot_start_offsets_ms(
        durations, pair_fades, visual_out_ms=600, visual_in_ms=600,
    )
    per_pair = module_slot_start_offsets_ms(
        durations,
        pair_fades,
        visual_out_ms=600,
        visual_in_ms=600,
        visual_out_ms_by_pair=[600, 600, 0],
    )

    # Boundaries 0 and 1 are unchanged, so the first three starts match.
    assert per_pair[:3] == uniform[:3]
    # Boundary 2 drops its 600ms outgoing fade into the black hold instead.
    assert per_pair[3] > uniform[3], (per_pair, uniform)


def test_offsets_match_rendered_timeline_for_module_boundary_map() -> None:
    durations = [4321, 5678, 6543, 7890]
    pair_fades = [1200, 1500, 1200]
    outs = [600, 600, 0]

    got = module_slot_start_offsets_ms(
        durations,
        pair_fades,
        visual_out_ms=600,
        visual_in_ms=600,
        visual_out_ms_by_pair=outs,
    )
    assert got == _expected_offsets(durations, pair_fades, outs, 600, 600)


def test_omitting_per_pair_preserves_previous_behaviour() -> None:
    durations = [4000, 5000, 6000]
    pair_fades = [1200, 1200]

    got = module_slot_start_offsets_ms(
        durations, pair_fades, visual_out_ms=600, visual_in_ms=600,
    )
    explicit_none = module_slot_start_offsets_ms(
        durations,
        pair_fades,
        visual_out_ms=600,
        visual_in_ms=600,
        visual_out_ms_by_pair=None,
    )
    assert got == explicit_none
    assert got == _expected_offsets(durations, pair_fades, None, 600, 600)


def test_short_per_pair_list_falls_back_to_uniform() -> None:
    """Render falls back to visual_out_ms past the end of the list; match it."""
    durations = [4000, 5000, 6000]
    pair_fades = [1200, 1200]
    outs = [0]

    got = module_slot_start_offsets_ms(
        durations,
        pair_fades,
        visual_out_ms=600,
        visual_in_ms=600,
        visual_out_ms_by_pair=outs,
    )
    assert got == _expected_offsets(durations, pair_fades, outs, 600, 600)


def test_empty_and_single_slot_are_stable() -> None:
    assert module_slot_start_offsets_ms([], [], visual_out_ms_by_pair=[0]) == []
    assert module_slot_start_offsets_ms([5000], [], visual_out_ms_by_pair=[0]) == [0]


def test_zero_pair_fade_inserts_no_black() -> None:
    got = module_slot_start_offsets_ms(
        [4000, 5000],
        [0],
        visual_out_ms=600,
        visual_in_ms=600,
        visual_out_ms_by_pair=[0],
    )
    assert got == [0, 4000]
