"""Phase A Arlo base-clip contract tests."""
import unittest

from phase_a_arlo_contract import (
    PHASE_A_ARLO_BASE_CLIP_CANONICAL,
    coerce_phase_a_arlo_base_clip_id,
    phase_a_arlo_base_clip_deprecated,
)


class PhaseAArloContractTests(unittest.TestCase):
    def test_deprecated_ids_coerce_to_v4(self) -> None:
        for old in (
            "arlo_idle_wizard_desk_v1",
            "arlo_idle_wizard_desk_v2",
            "arlo_idle_wizard_desk_v3",
        ):
            self.assertTrue(phase_a_arlo_base_clip_deprecated(old))
            self.assertEqual(coerce_phase_a_arlo_base_clip_id(old), PHASE_A_ARLO_BASE_CLIP_CANONICAL)

    def test_canonical_not_deprecated(self) -> None:
        self.assertFalse(phase_a_arlo_base_clip_deprecated(PHASE_A_ARLO_BASE_CLIP_CANONICAL))
        self.assertEqual(
            coerce_phase_a_arlo_base_clip_id(PHASE_A_ARLO_BASE_CLIP_CANONICAL),
            PHASE_A_ARLO_BASE_CLIP_CANONICAL,
        )


if __name__ == "__main__":
    unittest.main()
