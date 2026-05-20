"""Unit tests for tools/sanitize.py per LD-760 spec.

16 tests: 8 leak-pattern stripping + 8 no-spurious-stripping (reverse).
"""
import os
import sys
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
MCP_ROOT = THIS_DIR.parent
sys.path.insert(0, str(MCP_ROOT))

from tools.sanitize import (  # noqa: E402
    sanitize_string,
    sanitize_payload,
    find_earliest_leak_position,
)


class TestLeakPatternsStripping(unittest.TestCase):
    """Each pattern must be stripped + WARN logged (logging not asserted here)."""

    def test_1_open_parameter_tag_stripped(self):
        s = 'real content here<parameter name="foo">leaked stuff'
        cleaned, patterns = sanitize_string(s, "test_field")
        self.assertEqual(cleaned, "real content here")
        self.assertEqual(patterns, ["open_parameter_tag"])

    def test_2_close_parameter_tag_stripped(self):
        s = "legitimate prose</parameter>garbage after"
        cleaned, _ = sanitize_string(s, "test_field")
        self.assertEqual(cleaned, "legitimate prose")

    def test_3_directus_field_closing_tag_stripped(self):
        # `</decision_text>` matches the field-shape pattern.
        s = "real decision body </decision_text>next garbage"
        cleaned, _ = sanitize_string(s, "test_field")
        self.assertEqual(cleaned, "real decision body")

    def test_4_html_escaped_open_parameter_stripped(self):
        s = "ok content &lt;parameter name=&quot;x&quot;&gt;leak"
        cleaned, _ = sanitize_string(s, "test_field")
        self.assertEqual(cleaned, "ok content")

    def test_5_html_escaped_close_parameter_stripped(self):
        s = "good prose &lt;/parameter&gt;trash"
        cleaned, _ = sanitize_string(s, "test_field")
        self.assertEqual(cleaned, "good prose")

    def test_6_html_escaped_field_close_stripped(self):
        s = "preserved body &lt;/decision_text&gt;trash"
        cleaned, _ = sanitize_string(s, "test_field")
        self.assertEqual(cleaned, "preserved body")

    def test_7_truncate_at_earliest_position(self):
        # Two leak tokens; should truncate at earliest.
        s = "before<parameter name='a'>middle</parameter>after"
        cleaned, _ = sanitize_string(s, "test_field")
        self.assertEqual(cleaned, "before")

    def test_8_empty_list_element_dropped(self):
        payload = {"related_files": ["valid_path.py", "<parameter name='leak'>polluted only", "other.py"]}
        cleaned = sanitize_payload(payload, "test")
        # The middle element becomes empty after strip → dropped.
        self.assertEqual(cleaned["related_files"], ["valid_path.py", "other.py"])


class TestNoSpuriousStripping(unittest.TestCase):
    """Reverse tests: legitimate content with angle brackets MUST pass through."""

    def test_9_html_code_sample_pass_through(self):
        # Generic HTML elements that don't match the narrow patterns.
        s = "Here's a <div> example with </div> tags."
        cleaned, patterns = sanitize_string(s, "test_field")
        self.assertEqual(cleaned, s)
        self.assertEqual(patterns, [])

    def test_10_math_comparison_pass_through(self):
        s = "if x < 5 and y > 3 then do something"
        cleaned, _ = sanitize_string(s, "test_field")
        self.assertEqual(cleaned, s)

    def test_11_opening_tag_no_slash_pass_through(self):
        # Opening tags WITHOUT closing slash are NOT stripped.
        s = "Use <button> elements but only when needed."
        cleaned, patterns = sanitize_string(s, "test_field")
        self.assertEqual(cleaned, s)
        self.assertEqual(patterns, [])

    def test_12_escaped_prose_pass_through(self):
        # Single-letter "tags" are NOT field-shape (need 2+ chars inside <>).
        s = "Mark with </a> or use <b> for bold"
        cleaned, _ = sanitize_string(s, "test_field")
        # </a> is 1 char inside brackets — should NOT match (regex needs {1,} after first char = 2+ total)
        # Actually our regex is [a-z][a-z0-9_]{1,} which is 2+ total chars. </a> has only 'a' = 1 char.
        self.assertEqual(cleaned, s)

    def test_13_no_leak_passes_through_unchanged(self):
        s = "Normal sentence with no leak tokens."
        cleaned, patterns = sanitize_string(s, "test_field")
        self.assertEqual(cleaned, s)
        self.assertEqual(patterns, [])

    def test_14_empty_string_pass_through(self):
        cleaned, patterns = sanitize_string("", "test_field")
        self.assertEqual(cleaned, "")
        self.assertEqual(patterns, [])

    def test_15_nested_dict_recursive(self):
        payload = {
            "outer": {
                "inner": "real content<parameter name='x'>leak",
                "list": ["safe", "</parameter>polluted"],
            },
            "keep": "untouched",
        }
        cleaned = sanitize_payload(payload, "root")
        self.assertEqual(cleaned["outer"]["inner"], "real content")
        self.assertEqual(cleaned["outer"]["list"], ["safe"])  # polluted dropped (becomes empty)
        self.assertEqual(cleaned["keep"], "untouched")

    def test_16_non_string_types_pass_through(self):
        payload = {"int": 42, "bool": True, "none": None, "float": 3.14}
        cleaned = sanitize_payload(payload, "root")
        self.assertEqual(cleaned, payload)


class TestFindEarliestLeakPosition(unittest.TestCase):
    """Direct primitive tests."""

    def test_returns_none_when_no_leak(self):
        self.assertIsNone(find_earliest_leak_position("safe content"))

    def test_returns_position_and_pattern(self):
        r = find_earliest_leak_position("safe<parameter name='x'>leak")
        self.assertIsNotNone(r)
        pos, pat = r
        self.assertEqual(pos, 4)
        self.assertEqual(pat, "open_parameter_tag")


if __name__ == "__main__":
    unittest.main(verbosity=2)
