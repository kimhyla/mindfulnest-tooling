"""Arlo canonical intro tail registry invariants."""
from __future__ import annotations

import json
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
TEMPLATES = TOOLS.parent / "templates"


def _arlo_registry_path() -> Path:
    return TEMPLATES / "arlo_teleport_intro" / "canonical_registry.json"


def test_arlo_registry_schema_when_present() -> None:
    path = _arlo_registry_path()
    if not path.is_file():
        return  # placeholder ok in tooling-only checkout; Dropbox build fills this
    reg = json.loads(path.read_text(encoding="utf-8"))
    assert reg.get("character") == "Arlo"
    assert reg.get("schema_version") == 1
    if reg.get("status") == "built":
        assert reg.get("single_canonical") is True
        variants = reg.get("variants") or []
        assert len(variants) >= 1
        slot0 = variants[0]
        assert slot0.get("slot") == 0
        assert slot0.get("intro_tail_rel")
        rel = str(slot0["intro_tail_rel"])
        tail = TOOLS.parent / rel if rel.startswith("Production/") else TEMPLATES / "arlo_teleport_intro" / rel
        # In CI the mp4 may not exist; path string must be well-formed
        assert "intro_tail" in str(tail)


def test_arlo_registry_does_not_reuse_chipper_template() -> None:
    path = _arlo_registry_path()
    if not path.is_file():
        return
    reg = json.loads(path.read_text(encoding="utf-8"))
    blob = json.dumps(reg)
    assert "chipper_teleport_intro/canonical/variant_0/intro_tail.mp4" not in blob


def test_guide_aware_registry_module_exports() -> None:
    import teleport_intro_canonical as tic  # noqa: WPS433

    assert callable(getattr(tic, "active_manifest_path", None))
    kit_src = (TOOLS / "teleport_intro_kit.py").read_text(encoding="utf-8")
    assert "active_manifest_path" in kit_src
