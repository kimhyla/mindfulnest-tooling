"""Durability tests for lib/watercolor_assets — keys, URLs, resolve, catalog merge."""
from __future__ import annotations

import tempfile
import urllib.parse
from pathlib import Path

import pytest

from lib.watercolor_assets import (
    list_watercolor_items,
    resolve_watercolor_path,
    slug_watercolor_key,
    upload_watercolor_filename,
    watercolor_file_api_path,
    watercolor_serve_api_path,
)


def test_slug_and_upload_filename():
    assert slug_watercolor_key("Breath Squeezer Spell.png") == "breath_squeezer_spell"
    assert upload_watercolor_filename("ChatGPT Image Jun 19, 2026, 11_27_38 PM.png") == (
        "chatgpt_image_jun_19_2026_11_27_38_pm.png"
    )


def test_url_helpers_encode_spaces():
    key = "ChatGPT Image Jun 19, 2026, 11_27_38 PM"
    path = watercolor_file_api_path(key)
    assert path.startswith("/api/phase/watercolor_file?key=")
    assert urllib.parse.unquote(path.split("key=", 1)[1]) == key
    serve = watercolor_serve_api_path(key)
    assert urllib.parse.unquote(serve.rsplit("/", 1)[-1]) == key


def test_resolve_spaced_legacy_filename():
    key = "ChatGPT Image Jun 19, 2026, 11_27_38 PM"
    with tempfile.TemporaryDirectory() as tmp:
        lib = Path(tmp)
        png = lib / f"{key}.png"
        png.write_bytes(b"\x89PNG\r\n")
        resolved = resolve_watercolor_path(lib, key, prefer_animation=False)
        assert resolved == png.resolve()
        encoded_key = urllib.parse.quote(key, safe="")
        resolved2 = resolve_watercolor_path(lib, encoded_key, prefer_animation=True)
        assert resolved2 == png.resolve()


def test_list_items_match_phase_and_cr_library_shape():
    with tempfile.TemporaryDirectory() as tmp:
        lib = Path(tmp)
        (lib / "hands_rubbing.png").write_bytes(b"\x89PNG\r\n")
        items = list_watercolor_items(lib)
        assert len(items) == 1
        row = items[0]
        assert row["key"] == "hands_rubbing"
        assert row["tier"] == "watercolor"
        assert "watercolor" in row["tags"]
        assert row["thumb_url"] == watercolor_file_api_path("hands_rubbing")
        assert row["abs_path"]


def test_prefer_animation_picks_mp4_when_both_exist():
    with tempfile.TemporaryDirectory() as tmp:
        lib = Path(tmp)
        (lib / "spell.png").write_bytes(b"\x89PNG\r\n")
        (lib / "spell.mp4").write_bytes(b"\x00\x00\x00\x18ftyp")
        static = resolve_watercolor_path(lib, "spell", prefer_animation=False)
        assert static.suffix == ".png"
        anim = resolve_watercolor_path(lib, "spell", prefer_animation=True)
        assert anim.suffix == ".mp4"
