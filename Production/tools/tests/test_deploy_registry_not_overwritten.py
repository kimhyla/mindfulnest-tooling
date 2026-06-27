"""Deploy must not overwrite runtime character_subjects.json on Dropbox."""
from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
SCRIPTS = TOOLS.parent / "scripts"


def test_deploy_manifest_excludes_character_subjects():
    text = (SCRIPTS / "deploy_storyboard_v59.sh").read_text(encoding="utf-8")
    manifest_block = text.split("for manifest in", 1)[1].split("done", 1)[0]
    assert "character_subjects.json" not in manifest_block


def test_parity_registry_warn_only_by_default():
    text = (SCRIPTS / "verify_tooling_dropbox_parity.py").read_text(encoding="utf-8")
    assert "REGISTRY_COMPARE_PATHS" in text
    assert "MN_REGISTRY_PARITY_STRICT" in text
