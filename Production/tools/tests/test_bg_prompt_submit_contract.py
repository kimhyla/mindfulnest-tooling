"""Prompt-box submit contract — textarea text is the only O3 Generate source."""
from __future__ import annotations

from pathlib import Path

import beat_generator as bg

TOOLS = Path(__file__).resolve().parent.parent
BGTAB = TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
PROMPT_FIELD = TOOLS / "storyboard-v2" / "src" / "hooks" / "useProtectedPromptField.ts"
PROMPT_REGISTRY = TOOLS / "storyboard-v2" / "src" / "state" / "promptEditRegistry.ts"


def test_validate_o3_submit_accepts_full_element_prompt() -> None:
    prompt = (
        "@Image1 (Ember). Scene from @Image2.\n\n"
        "Camera: static locked shot.\n\n"
        'Ember speaks: "Hello there."\n\n'
        "Children's illustrated fantasy storybook style."
    )
    ok, code, _msg = bg.validate_o3_submit_prompt_for_mode(
        prompt,
        bg.O3_GENERATE_MODE_ELEMENT_NATIVE,
    )
    assert ok
    assert code == ""


def test_on_generate_batch_never_falls_back_to_sidecar_prompt() -> None:
    src = BGTAB.read_text(encoding="utf-8")
    block = src.split("const onGenerateBatch = async", 1)[1].split("\n  const handleO3SubmitResult", 1)[0]
    o3_branch = block.split("if (isO3VoiceBeat(beat))", 1)[1]
    assert "beatPromptText(beat" not in o3_branch.split("await submitO3Voice", 1)[0]


def test_on_generate_batch_skips_second_save_when_prompt_already_persisted() -> None:
    src = BGTAB.read_text(encoding="utf-8")
    block = src.split("const onGenerateBatch = async", 1)[1].split("\n  const handleO3SubmitResult", 1)[0]
    assert "promptAlreadyPersisted" in block
    assert "opts?.promptAlreadyPersisted" in block
    assert "onBeginGenerateSubmit" in src
    assert "promptAlreadyPersisted: true" in src


def test_submit_o3_voice_skips_pre_mutation_snapshot() -> None:
    src = BGTAB.read_text(encoding="utf-8")
    block = src.split("const submitO3Voice = async", 1)[1].split("\n  const confirmVoiceDriftSubmit", 1)[0]
    assert "skipSnapshot: true" in block


def test_delete_beat_flushes_unsaved_prompt_before_sidecar_delete() -> None:
    src = BGTAB.read_text(encoding="utf-8")
    fn = src.split("const executeDeleteBeat = async", 1)[1].split("\n  const onUpdateBeatText", 1)[0]
    assert "readPromptEditText(beatId)" in fn
    assert "onUpdateBeatText(beatId, unsavedPrompt)" in fn
    assert "bg_delete_beat" in fn.split("onUpdateBeatText", 1)[1]
    assert "clearPromptEdit(beatId)" in fn


def test_protected_prompt_field_dom_authority_over_stale_server() -> None:
    src = PROMPT_FIELD.read_text(encoding="utf-8")
    effect = src.split("// Adopt server text only when the user is not actively editing.", 1)[1]
    assert "domText.trim().length > externalText.trim().length" in effect
    assert "dirtyRef.current = true" in effect


def test_prompt_edit_registry_exports_unsaved_helpers() -> None:
    src = PROMPT_REGISTRY.read_text(encoding="utf-8")
    assert "export function readPromptEditText" in src
    assert "export function hasUnsavedPromptEdit" in src
