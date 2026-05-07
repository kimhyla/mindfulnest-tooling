#!/usr/bin/env python3
"""Offline coverage for Production/tools/build_storyboard.py.

task_id = LD-260-pytest-3-pipeline-scripts-20260418
preflight = 72
LD coverage = LD-260 PIPELINE_PYTEST_3_CRITICAL_SCRIPTS

Scope: import surface, pure-function behavior (_parse_module_id,
_compute_aspect_ratio), argparse --help boot. No network, no Directus.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


class BuildStoryboardImportTests(unittest.TestCase):
    """Module must import cleanly without executing main()."""

    def test_module_imports(self) -> None:
        import build_storyboard  # noqa: F401
        self.assertTrue(hasattr(build_storyboard, "main"))
        self.assertTrue(hasattr(build_storyboard, "build_storyboard"))
        self.assertTrue(hasattr(build_storyboard, "query_registry_images"))


class ParseModuleIdTests(unittest.TestCase):
    """build_storyboard._parse_module_id accepts many forms, returns int|None."""

    def setUp(self) -> None:
        import build_storyboard
        self.fn = build_storyboard._parse_module_id

    def test_m_prefix_uppercase(self) -> None:
        self.assertEqual(self.fn("M1"), 1)
        self.assertEqual(self.fn("M5"), 5)

    def test_m_prefix_lowercase(self) -> None:
        self.assertEqual(self.fn("m3"), 3)

    def test_embedded_in_slug(self) -> None:
        self.assertEqual(self.fn("arc1_m1_event1"), 1)

    def test_int_passthrough(self) -> None:
        self.assertEqual(self.fn(7), 7)

    def test_plain_numeric_string(self) -> None:
        self.assertEqual(self.fn("42"), 42)

    def test_none_returns_none(self) -> None:
        self.assertIsNone(self.fn(None))

    def test_unparseable_returns_none(self) -> None:
        self.assertIsNone(self.fn("not-a-module"))


class ComputeAspectRatioTests(unittest.TestCase):
    """_compute_aspect_ratio uses gcd reduction; returns 'unknown' on 0/None."""

    def setUp(self) -> None:
        import build_storyboard
        self.fn = build_storyboard._compute_aspect_ratio

    def test_standard_16_9(self) -> None:
        self.assertEqual(self.fn(1920, 1080), "16:9")

    def test_standard_4_3(self) -> None:
        self.assertEqual(self.fn(1024, 768), "4:3")

    def test_square(self) -> None:
        self.assertEqual(self.fn(2048, 2048), "1:1")

    def test_zero_dimension(self) -> None:
        self.assertEqual(self.fn(0, 100), "unknown")
        self.assertEqual(self.fn(100, 0), "unknown")

    def test_none_dimension(self) -> None:
        self.assertEqual(self.fn(None, 1080), "unknown")


class BuildStoryboardCliTests(unittest.TestCase):
    """CLI boots without error — catches argparse config regressions."""

    def test_help_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(TOOLS / "build_storyboard.py"), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("--registry", result.stdout)
        self.assertIn("--smoke-test", result.stdout)


if __name__ == "__main__":
    unittest.main()
