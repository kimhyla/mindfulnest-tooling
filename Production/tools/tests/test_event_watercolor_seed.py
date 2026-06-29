"""EVENT_WC_SEED_V1 — empty events inherit template watercolor library."""
from __future__ import annotations

import tempfile
from pathlib import Path

from lib.event_library import (
    ensure_event_library_dirs,
    event_watercolors_dir,
    seed_event_watercolors_if_empty,
)


def test_seed_skips_when_target_has_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        template = root / "Event_1"
        target = root / "Event_4"
        ensure_event_library_dirs(template)
        ensure_event_library_dirs(target)
        (event_watercolors_dir(template) / "hands_rubbing.png").write_bytes(b"\x89PNG\r\n")
        (event_watercolors_dir(target) / "existing.png").write_bytes(b"\x89PNG\r\n")
        n = seed_event_watercolors_if_empty(target, prod_root=root)
        assert n == 0
        assert not (event_watercolors_dir(target) / "hands_rubbing.png").exists()


def test_seed_copies_from_first_non_empty_template():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        template = root / "Event_1"
        target = root / "Event_4"
        ensure_event_library_dirs(template)
        ensure_event_library_dirs(target)
        (event_watercolors_dir(template) / "spell_title.png").write_bytes(b"\x89PNG\r\n")
        (event_watercolors_dir(template) / "hands_rubbing.png").write_bytes(b"\x89PNG\r\n")
        n = seed_event_watercolors_if_empty(target, prod_root=root)
        assert n == 2
        assert (event_watercolors_dir(target) / "spell_title.png").is_file()
        assert (event_watercolors_dir(target) / "hands_rubbing.png").is_file()
