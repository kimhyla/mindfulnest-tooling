"""
Regression test for the pre-existing combined-run test-isolation bug flagged by
the Phase D BUILD chip (prod_activity_log id=3324) and re-confirmed by the
session 2026-05-11 closure (CROSS_SESSION_STATE_SUMMARY_20260511_0910_V1_ALL_MERGES_SESSION_CLOSURE).

Bug class: `fixture_setdefault_conflict`.

Root cause (read this before changing this file):
  `Production/tools/registered_write.py` imports `DROPBOX_ROOT` from
  `Production/lib/paths.py`, which resolves `MN_DROPBOX_ROOT` AT IMPORT TIME and
  freezes it into `_PROJECT_ROOT`. Two test modules
  (`test_assemble_module.py`, `test_register_asset.py`) used to install DIFFERENT
  tempdir roots into `MN_DROPBOX_ROOT` at module-load time. Whichever module
  loaded first won the freeze; the other module then created files under a
  PATH OUTSIDE the frozen root and `register_asset` rejected them with
  ``Sub-agent sandboxed paths cannot be registered``.

Fix shape:
  Both test modules use an idempotent "get-or-create" pattern against
  `MN_DROPBOX_ROOT` so that whichever module is imported first creates the
  shared root, and subsequent modules pick it up. The `_FIXTURE_ROOT` symbol
  in each module is bound to the value actually present in the env var, which
  is the same value `registered_write._PROJECT_ROOT` captured.

This regression test is order-independent: pytest can collect it in any
position and the invariant ``os.environ["MN_DROPBOX_ROOT"]`` ==
``registered_write._PROJECT_ROOT`` ==
``test_assemble_module._FIXTURE_ROOT`` ==
``test_register_asset._FIXTURE_ROOT`` MUST hold.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_TOOLING_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_TOOLING_REPO))


class TestFixtureRootIsolation(unittest.TestCase):
    """Both phase-B and phase-C test fixture roots MUST resolve to the same path."""

    def test_test_modules_share_one_fixture_root(self):
        """Importing both test modules must NOT produce conflicting roots."""
        # Import order intentionally matches the failing combined-run order
        # (assemble_module first, register_asset second) — Order A from the
        # 2026-05-11 reproduction.
        from Production.tools.tests import test_assemble_module
        from Production.tools.tests import test_register_asset

        assemble_root = test_assemble_module._FIXTURE_ROOT
        register_root = test_register_asset._FIXTURE_ROOT

        self.assertEqual(
            assemble_root,
            register_root,
            (
                f"Phase-C fixture root ({assemble_root}) and Phase-B fixture root "
                f"({register_root}) must agree. Pre-fix: they were two different "
                "tempdirs and whichever imported first won MN_DROPBOX_ROOT, "
                "breaking the other module's tests in combined runs."
            ),
        )

    def test_env_var_matches_registered_write_project_root(self):
        """MN_DROPBOX_ROOT env var MUST match registered_write._PROJECT_ROOT."""
        from Production.tools import registered_write
        from Production.tools.tests import test_assemble_module  # noqa: F401  ensure import side-effects

        env_root = os.environ.get("MN_DROPBOX_ROOT")
        captured_root = registered_write._PROJECT_ROOT

        self.assertIsNotNone(env_root, "MN_DROPBOX_ROOT must be set by test modules")
        self.assertEqual(
            env_root,
            captured_root,
            (
                f"env MN_DROPBOX_ROOT={env_root} and registered_write._PROJECT_ROOT="
                f"{captured_root} must match. Mismatch means registered_write was "
                "imported BEFORE the test module that set the env var — fixture "
                "ordering is broken."
            ),
        )

    def test_phase_b_files_pass_validation_under_shared_root(self):
        """Files created under the shared root must pass register_asset path validation."""
        import tempfile
        from Production.tools import registered_write
        from Production.tools.tests import test_register_asset  # noqa: F401

        # _make_test_file writes under _FIXTURE_ROOT.
        path = test_register_asset._make_test_file()
        try:
            # _validate_path will raise ValueError if path is outside _PROJECT_ROOT.
            resolved = registered_write._validate_path(path)
            self.assertTrue(
                resolved.startswith(registered_write._PROJECT_ROOT),
                f"{resolved} must start with {registered_write._PROJECT_ROOT}",
            )
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
