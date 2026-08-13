"""Library Add to Element UI + classification regression."""
from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
STORYBOARD = TOOLS / "storyboard-v2" / "src"
UTIL = STORYBOARD / "utils" / "libraryElementPose.ts"
LIBRARY = STORYBOARD / "components" / "LibraryPanel.tsx"
BG = TOOLS / "server_handlers" / "background.py"


def test_library_element_pose_util_exported():
    text = UTIL.read_text(encoding="utf-8")
    assert "export const ELEMENT_SPEAKERS" in text
    assert "'Oliver'" in text
    assert "export function libraryItemCanAddToElement" in text
    assert "still_delivery" in text
    assert "canonical_image" in text


def test_library_panel_wires_add_to_element_preview():
    text = LIBRARY.read_text(encoding="utf-8")
    assert "libraryItemCanAddToElement" in text
    assert "from '../utils/libraryElementPose'" in text
    assert "bg_add_element_pose" in text
    assert "library-add-element-btn" in text
    assert "library-element-speaker" in text
    assert "speaker: elementSpeaker" in text
    assert "abs_path: preview.item.abs_path" in text


def test_library_add_element_pose_accepts_library_path_without_beat():
    text = BG.read_text(encoding="utf-8")
    block = text.split("def handle_bg_add_element_pose")[1].split("\ndef handle_bg_set_element_identity")[0]
    assert "speaker = (body.get(\"speaker\")" in block
    assert "abs_path = (body.get(\"abs_path\")" in block
    assert "materialize_char_ref_abs_path" in block
    assert "add_element_pose" in block
    assert "promote_frontal" not in block


def test_bg_tab_add_element_pose_sends_display_char_ref_speaker_and_path():
    text = (STORYBOARD / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "displayCharRef(beat)" in text
    assert "abs_path: absPath" in text
    assert "promote_frontal" not in text
    assert "'bg_add_element_pose', { beat_id: beatId }" not in text


def test_bg_tab_set_element_identity_confirm_modal():
    text = (STORYBOARD / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "bg_set_element_identity" in text
    assert "set-element-identity" in text
    assert "Set as Element identity" in text
    assert "executeSetElementIdentity" in text
    assert "canonBeatSpeaker(beat?.speaker)" in text
    assert r"replace(/[\s:：.;,]+$/" in text
    assert "Setting identity" in text
    assert "submitting: true" in text


def test_library_add_element_pose_binds_prod_root_via_init_bg_paths():
    """Regression: handler must not reference AppContext._prod_root (500)."""
    text = BG.read_text(encoding="utf-8")
    block = text.split("def handle_bg_add_element_pose")[1].split("\ndef handle_bg_set_element_identity")[0]
    assert "_prod_root" not in block
    assert "rebind_bg_paths_from_app(h.app)" in block


def test_library_element_pose_classification_rules():
    """Document expected allow/deny matrix (mirrors libraryElementPose.ts)."""
    text = UTIL.read_text(encoding="utf-8")
    assert "asset_type === 'element_pose'" in text
    assert "tags.includes('element')" in text
    assert "tags.includes('char_ref')" in text
    assert "tier === 'canonical'" in text


def test_library_element_add_css_present():
    css = (STORYBOARD / "app.css").read_text(encoding="utf-8")
    assert ".mn-library-element-add" in css
    assert ".mn-library-element-add-btn" in css
    assert ".mn-bg-ref-set-identity-btn" in css
