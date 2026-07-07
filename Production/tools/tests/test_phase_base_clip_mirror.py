"""Base-clip id top-level / nested mirror parity."""
from server_handlers.phases import (
    apply_phase_base_clip_id_patch,
    heal_phase_base_clip_id_mirror,
)


def test_apply_phase_a_clip_mirrors_nested_and_flags_regen_on_change() -> None:
    state: dict = {
        "phase_a_chipper_sitting_clip_id": "arlo_idle_wizard_desk_v7",
        "phase_a": {"phase_a_chipper_sitting_clip_id": "arlo_idle_wizard_desk_v7"},
    }
    apply_phase_base_clip_id_patch(state, "phase_a_chipper_sitting_clip_id", "arlo_idle_wizard_desk_v8")
    assert state["phase_a_chipper_sitting_clip_id"] == "arlo_idle_wizard_desk_v8"
    assert state["phase_a"]["phase_a_chipper_sitting_clip_id"] == "arlo_idle_wizard_desk_v8"
    assert state["phase_a_lipsync_requires_regen"] is True
    assert state["phase_a"]["phase_a_lipsync_requires_regen"] is True


def test_heal_syncs_nested_to_top() -> None:
    state: dict = {
        "phase_a_chipper_sitting_clip_id": "arlo_idle_wizard_desk_v8",
        "phase_a": {"phase_a_chipper_sitting_clip_id": "arlo_idle_wizard_desk_v7"},
    }
    assert heal_phase_base_clip_id_mirror(state) is True
    assert state["phase_a"]["phase_a_chipper_sitting_clip_id"] == "arlo_idle_wizard_desk_v8"
