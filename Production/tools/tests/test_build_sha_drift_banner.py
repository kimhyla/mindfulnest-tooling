"""BUILD_SHA_DRIFT_V1 — persistent banner + silent mutation errors when tab is stale."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "storyboard-v2" / "src"


def _text_between(src: str, start: str, end: str) -> str:
    i = src.index(start)
    j = src.index(end, i + 1)
    return src[i:j]


def test_build_sha_drift_banner_wired_in_app() -> None:
    app = (ROOT / "app.tsx").read_text(encoding="utf-8")
    assert "BuildShaDriftBanner" in app
    assert "<BuildShaDriftBanner />" in app


def test_mutation_errors_suppresses_stale_toast_text() -> None:
    text = (ROOT / "api" / "mutationErrors.ts").read_text(encoding="utf-8")
    assert "isClientBundleStaleError" in text
    assert "return '';" in text or "return ''" in text


def test_bgtab_skips_stale_error_toasts() -> None:
    text = (ROOT / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "isClientBundleStaleError(result)" in text
    assert "if (!msg) return false" in text


def test_replace_slot_reverts_on_failed_save() -> None:
    bgtab = (ROOT / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    block = _text_between(bgtab, "const onSetReplaceSlot", "const onRenderStillClip")
    assert "priorSlot" in block
    assert "!result.ok && priorSlot !== slotIndex" in block


def test_ref_drop_skips_stale_error_toast() -> None:
    bgtab = (ROOT / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    idx = bgtab.index("source: 'bg-ref-drop-error'")
    block = bgtab[max(0, idx - 900):idx + 80]
    assert "isClientBundleStaleError(result)" in block
    assert "bg-ref-drop-error" in block
    stale_pos = block.index("isClientBundleStaleError(result)")
    toast_pos = block.index("pushToast")
    assert stale_pos < toast_pos


def test_mutation_toast_sources_use_format_mutation_error() -> None:
    bgtab = (ROOT / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    for source in (
        "bg-delete-error",
        "bg-submit-error",
        "bg-still-clip-error",
        "bg-set-context",
        "bg-accept-all-error",
    ):
        idx = bgtab.index(f"source: '{source}'")
        block = bgtab[max(0, idx - 400):idx + 60]
        assert "formatMutationError" in block, source
        assert "if (msg)" in block, source


def test_storyboard_mutation_toast_sources_use_format_mutation_error() -> None:
    sb = (ROOT / "components" / "StoryboardTab.tsx").read_text(encoding="utf-8")
    for source in (
        "beat-${label}-error",
        "beat-Regen Audio-error",
        "beat-animate-error",
        "sb-delete-error",
        "sb-add-error",
    ):
        if source == "beat-${label}-error":
            idx = sb.index("source: `beat-${label}-error`")
        else:
            idx = sb.index(f"source: '{source}'")
        block = sb[max(0, idx - 400):idx + 60]
        assert "formatMutationError" in block, source
        assert "if (msg)" in block, source


def test_enrich_beats_job_busy_clears_terminal_pointers_in_memory() -> None:
    bg_handlers = Path(__file__).resolve().parent.parent / "server_handlers" / "background.py"
    enrich = bg_handlers.read_text(encoding="utf-8").split("def _enrich_beats_job_busy", 1)[1].split("\ndef ", 1)[0]
    assert "clear_o3_pointer_if_terminal" in enrich
    assert enrich.index("clear_o3_pointer_if_terminal") < enrich.index("_resolve_beat_job_busy_for_session")
