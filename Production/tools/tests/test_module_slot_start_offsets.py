"""Module preview slot seek offsets — black-pause boundary math."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
CRED = TOOLS / "credentials_lib"
if str(CRED) not in sys.path:
    sys.path.insert(0, str(CRED))

from ffmpeg_stitch import module_slot_start_offsets_ms  # noqa: E402


def test_offsets_include_black_pause_between_slots() -> None:
    durs = [30000, 50000, 100000, 30000]
    pair_fades = [3800, 3800, 3800]
    starts = module_slot_start_offsets_ms(durs, pair_fades)
    assert starts[0] == 0
    assert starts[1] == 32600  # 30s intro + 2600ms black hold (3800 pair budget)
    assert starts[2] == starts[1] + 50000 + 2600
    assert starts[3] == starts[2] + 100000 + 2600


def test_offsets_without_dissolves_is_cumulative() -> None:
    durs = [10000, 20000, 30000]
    starts = module_slot_start_offsets_ms(durs, [0, 0])
    assert starts == [0, 10000, 30000]
