"""Functional equivalence tests for inline realpath+startswith path-injection gate.

LD CODEQL_PATH_INJECTION_NATIVE_PATTERN_REFACTOR_V1 — supersedes LD-702/706.
Verifies the inline pattern landed at production_server.py:10037, 10605, 11475
behaves identically to the legacy is_path_under_library_root helper.
"""
from __future__ import annotations
import os
import tempfile
from pathlib import Path


def inline_safe_check(abs_path, roots):
    """Exact copy of the inline pattern landed in production_server.py."""
    _abs_resolved = os.path.realpath(abs_path) if isinstance(abs_path, str) and abs_path else ""
    _safe = False
    if _abs_resolved:
        for _r in roots:
            if _r and (_abs_resolved == _r or _abs_resolved.startswith(_r + os.sep)):
                _safe = True
                break
    return _safe


def helper_safe_check(abs_path, roots):
    """Reference helper logic (mirrors AppContext.is_path_under_library_root)."""
    if not isinstance(abs_path, str) or not abs_path:
        return False
    try:
        resolved = os.path.realpath(abs_path)
    except (OSError, ValueError):
        return False
    for root in roots:
        if not root:
            continue
        try:
            common = os.path.commonpath([resolved, root])
        except ValueError:
            continue
        if common == root:
            return True
    return False


class TestInlinePathInjectionGate:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp(prefix="codeql_path_inline_")
        self.root_a = os.path.realpath(os.path.join(self.tmpdir, "stills"))
        self.root_b = os.path.realpath(os.path.join(self.tmpdir, "stills", "sources"))
        self.root_c = os.path.realpath(os.path.join(self.tmpdir, "stills", "crops"))
        self.root_d = os.path.realpath(os.path.join(self.tmpdir, "Character_Assets"))
        for r in (self.root_a, self.root_b, self.root_c, self.root_d):
            os.makedirs(r, exist_ok=True)
        self.roots = [self.root_a, self.root_b, self.root_c, self.root_d]
        self.f_under_a = os.path.join(self.root_a, "foo.png")
        Path(self.f_under_a).write_bytes(b"x")
        self.f_under_b_nested = os.path.join(self.root_b, "deep", "x.png")
        os.makedirs(os.path.dirname(self.f_under_b_nested), exist_ok=True)
        Path(self.f_under_b_nested).write_bytes(b"x")
        self.f_outside = os.path.join(self.tmpdir, "evil.png")
        Path(self.f_outside).write_bytes(b"x")
        self.symlink_outside = os.path.join(self.root_a, "evil_link.png")
        try:
            os.symlink(self.f_outside, self.symlink_outside)
            self.have_symlink = True
        except (OSError, NotImplementedError):
            self.have_symlink = False

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _assert_equiv(self, abs_path):
        a = inline_safe_check(abs_path, self.roots)
        b = helper_safe_check(abs_path, self.roots)
        assert a == b, f"divergence for {abs_path!r}: inline={a} helper={b}"

    def test_accept_path_directly_under_root(self):
        assert inline_safe_check(self.f_under_a, self.roots) is True
        self._assert_equiv(self.f_under_a)

    def test_accept_path_in_nested_subdir(self):
        assert inline_safe_check(self.f_under_b_nested, self.roots) is True
        self._assert_equiv(self.f_under_b_nested)

    def test_reject_path_outside_roots(self):
        assert inline_safe_check(self.f_outside, self.roots) is False
        self._assert_equiv(self.f_outside)

    def test_reject_etc_passwd(self):
        assert inline_safe_check("/etc/passwd", self.roots) is False
        self._assert_equiv("/etc/passwd")

    def test_reject_traversal_escape(self):
        traversal = os.path.join(self.root_a, "..", "..", "etc", "passwd")
        assert inline_safe_check(traversal, self.roots) is False
        self._assert_equiv(traversal)

    def test_reject_empty_string(self):
        assert inline_safe_check("", self.roots) is False
        self._assert_equiv("")

    def test_reject_none(self):
        assert inline_safe_check(None, self.roots) is False
        self._assert_equiv(None)

    def test_reject_non_string(self):
        assert inline_safe_check(12345, self.roots) is False
        self._assert_equiv(12345)

    def test_reject_symlink_pointing_outside(self):
        if not self.have_symlink:
            return
        assert inline_safe_check(self.symlink_outside, self.roots) is False
        self._assert_equiv(self.symlink_outside)

    def test_reject_prefix_lookalike(self):
        lookalike = self.root_a + "_evil"
        os.makedirs(lookalike, exist_ok=True)
        attack = os.path.join(lookalike, "x.png")
        Path(attack).write_bytes(b"x")
        assert inline_safe_check(attack, self.roots) is False
        self._assert_equiv(attack)

    def test_accept_exact_root(self):
        assert inline_safe_check(self.root_a, self.roots) is True
        self._assert_equiv(self.root_a)


if __name__ == "__main__":
    import sys
    t = TestInlinePathInjectionGate()
    passed = failed = 0
    for m in [x for x in dir(t) if x.startswith("test_")]:
        t.setup_method()
        try:
            getattr(t, m)()
            print(f"PASS {m}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL {m}: {e}")
            failed += 1
        finally:
            t.teardown_method()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
