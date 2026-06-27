"""Phase B watercolor asset URLs — canonical lib/watercolor_assets contract."""
from __future__ import annotations

import urllib.parse
from pathlib import Path


def test_serve_watercolor_unquotes_path_segment():
    src = Path(__file__).resolve().parents[1] / "production_server.py"
    text = src.read_text(encoding="utf-8")
    assert "urllib.parse.unquote(path[len(\"/api/phase_b/watercolor/\"):])" in text
    assert "resolve_watercolor_path" in text.split("def _serve_watercolor", 1)[1].split("\n    def ", 1)[0]


def test_cr_library_merges_watercolor_tier():
    src = Path(__file__).resolve().parents[1] / "server_handlers" / "cropper.py"
    text = src.read_text(encoding="utf-8")
    assert "list_watercolor_items(event_watercolors_dir" in text
    assert 'upload_watercolor_filename(filename)' in text


def test_list_api_uses_watercolor_assets_module():
    src = Path(__file__).resolve().parents[1] / "server_handlers" / "phases.py"
    text = src.read_text(encoding="utf-8")
    assert "list_watercolor_items(wc_dir)" in text
    assert "urllib.parse.unquote(key_list[0])" in text


def test_client_watercolor_assets_module_exists():
    ts = (
        Path(__file__).resolve().parents[1]
        / "storyboard-v2"
        / "src"
        / "utils"
        / "watercolorAssets.ts"
    )
    text = ts.read_text(encoding="utf-8")
    assert "watercolorFileUrl" in text
    assert "encodeURIComponent" in text
    assert "SERVER_BASE" in text


def test_encoded_key_roundtrip():
    key = "ChatGPT Image Jun 19, 2026, 11_27_38 PM"
    encoded = urllib.parse.quote(key)
    assert urllib.parse.unquote(encoded) == key
