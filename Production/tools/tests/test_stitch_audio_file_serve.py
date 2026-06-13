"""Library audio preview — URL decode + sound_library lookup."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "tools" / "production_server.py"


def test_audio_file_route_unquotes_spaced_filenames() -> None:
    src = SERVER.read_text(encoding="utf-8")
    assert 'fname = urllib.parse.unquote(' in src
    assert "/api/stitch_editor/audio_file/" in src


def test_serve_stitch_audio_prefers_canonical_sound_library() -> None:
    src = SERVER.read_text(encoding="utf-8")
    block = src.split("def _serve_stitch_audio_file", 1)[1].split("\n    def ", 1)[0]
    assert "urllib.parse.unquote(fname)" in block
    assert "sound_library" in block and "ambient" in block
    ambient_idx = block.index("sound_library/ambient")
    legacy_idx = block.index("ambient_library")
    root_idx = block.index("project_root / safe")
    assert ambient_idx < legacy_idx < root_idx


def test_unquote_restores_ambient_filename_with_spaces() -> None:
    encoded = "Intro%20video%20ambient%20bed.mp3"
    assert unquote(encoded) == "Intro video ambient bed.mp3"
