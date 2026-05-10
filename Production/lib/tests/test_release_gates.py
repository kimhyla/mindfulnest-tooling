"""
Tests for Production/lib/release_gates.py — verify_app_hash_encoding gate.

Per V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md §4.2 Step 6 (DS-2 strict TDD).

Run with:
    python3 -m unittest Production.lib.tests.test_release_gates -v

Strategy: build synthetic .ts source files in a temp dir mimicking the
MindfulNest app structure, then point verify_app_hash_encoding at the temp
dir. This makes the gate testable offline (no dependency on Kim's actual
app repo) while exercising the same regex extraction the gate uses on the
real repo.

Coverage:
  - pass case: digestStringAsync called with CryptoEncoding.HEX → returns dict
  - pass case: multiple HEX calls + ts + tsx scanned → passes
  - blocker case: single CryptoEncoding.Base64 OUTPUT → raises ReleaseBlockerError
  - blocker case: ReleaseBlockerError carries evidence list with file + snippet
  - skip case: __tests__ directory is excluded (mock files don't trigger blocker)
  - skip case: node_modules is excluded
  - input-base64 false-positive guard: EncodingType.Base64 (file-read input form)
    does NOT trigger; only CryptoEncoding.Base64 (output encoding) triggers
  - app repo missing → AppRepoNotAccessibleError (NOT ReleaseBlockerError)
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# Make Production.lib.release_gates importable when run directly or via -m unittest.
_TOOLING_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_TOOLING_REPO))

from Production.lib.release_gates import (  # noqa: E402
    AppRepoNotAccessibleError,
    ReleaseBlockerError,
    verify_app_hash_encoding,
)


HEX_USAGE_TS = """\
import * as Crypto from 'expo-crypto';
import * as FileSystem from 'expo-file-system';

export async function verifyAsset(localPath: string, expected: string) {
  const base64 = await FileSystem.readAsStringAsync(localPath, {
    encoding: FileSystem.EncodingType.Base64,
  });
  const actual = await Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    base64,
    { encoding: Crypto.CryptoEncoding.HEX },
  );
  return actual.toLowerCase() === expected.toLowerCase();
}
"""

BASE64_OUTPUT_USAGE_TS = """\
import * as Crypto from 'expo-crypto';
import * as FileSystem from 'expo-file-system';

export async function badHash(localPath: string) {
  const base64 = await FileSystem.readAsStringAsync(localPath, {
    encoding: FileSystem.EncodingType.Base64,
  });
  // THIS IS THE PROBLEM: OUTPUT encoding is base64, not hex.
  const actual = await Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    base64,
    { encoding: Crypto.CryptoEncoding.Base64 },
  );
  return actual;
}
"""

MIXED_USAGE_TSX = """\
import * as Crypto from 'expo-crypto';

export async function multi(s1: string, s2: string) {
  const h1 = await Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    s1,
    { encoding: Crypto.CryptoEncoding.HEX },
  );
  const h2 = await Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    s2,
  );  // default encoding (HEX per docs) — also fine
  return { h1, h2 };
}
"""

MOCK_TS = """\
// Test-only mock of expo-crypto. digestStringAsync returns a stubbed value
// with the unsafe Base64 encoding — but this file is in __tests__ and must
// be SKIPPED by the gate.
export const digestStringAsync = jest.fn(
  async () => 'aa' + 'aa'.repeat(31),
);
const ignoreMe = { encoding: 'CryptoEncoding.Base64' };
"""


def _write(parent: Path, rel_path: str, content: str) -> Path:
    p = parent / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


class TestVerifyAppHashEncodingPass(unittest.TestCase):

    def test_hex_only_returns_pass_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "src/services/downloadManager.ts", HEX_USAGE_TS)

            result = verify_app_hash_encoding(root)
            self.assertEqual(result["gate"], "verify_app_hash_encoding")
            self.assertEqual(result["result"], "pass")
            self.assertEqual(result["digest_call_count"], 1)
            self.assertGreaterEqual(result["files_scanned"], 1)

    def test_multiple_hex_calls_across_ts_tsx_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "src/services/downloadManager.ts", HEX_USAGE_TS)
            _write(root, "src/components/HashView.tsx", MIXED_USAGE_TSX)

            result = verify_app_hash_encoding(root)
            self.assertEqual(result["result"], "pass")
            # 1 (downloadManager.ts) + 2 (HashView.tsx) = 3 calls total
            self.assertEqual(result["digest_call_count"], 3)

    def test_tests_dir_is_excluded(self):
        """Mock files in __tests__/ must not trigger the gate."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "src/services/__tests__/__mocks__/expoCrypto.ts", MOCK_TS)
            _write(root, "src/services/downloadManager.ts", HEX_USAGE_TS)

            # Should pass — mock file is skipped because __tests__ is in its path.
            result = verify_app_hash_encoding(root)
            self.assertEqual(result["result"], "pass")
            # Only the production file's 1 call should be counted.
            self.assertEqual(result["digest_call_count"], 1)

    def test_node_modules_is_excluded(self):
        """Vendored deps in node_modules/ must not trigger the gate."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root,
                "node_modules/some-pkg/dist/index.ts",
                BASE64_OUTPUT_USAGE_TS,  # would normally trigger
            )
            _write(root, "src/services/downloadManager.ts", HEX_USAGE_TS)

            result = verify_app_hash_encoding(root)
            self.assertEqual(result["result"], "pass")

    def test_filesystem_encoding_base64_input_is_not_a_false_positive(self):
        """EncodingType.Base64 (file-read INPUT) must NOT trigger the gate."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # HEX_USAGE_TS uses FileSystem.EncodingType.Base64 for the file READ
            # but Crypto.CryptoEncoding.HEX for the digest OUTPUT — that's the
            # correct legitimate pattern. Gate must distinguish them.
            _write(root, "src/services/downloadManager.ts", HEX_USAGE_TS)
            result = verify_app_hash_encoding(root)
            self.assertEqual(result["result"], "pass")


class TestVerifyAppHashEncodingBlocker(unittest.TestCase):

    def test_base64_output_raises_release_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "src/services/badHash.ts", BASE64_OUTPUT_USAGE_TS)

            with self.assertRaises(ReleaseBlockerError) as cm:
                verify_app_hash_encoding(root)

            self.assertEqual(cm.exception.gate, "verify_app_hash_encoding")
            self.assertEqual(len(cm.exception.evidence), 1)
            ev = cm.exception.evidence[0]
            self.assertIn("badHash.ts", ev["file"])
            self.assertTrue(ev["uses_base64_output"])
            self.assertIn("CryptoEncoding.Base64", ev["snippet"])

    def test_mixed_hex_and_base64_still_blocker(self):
        """If even ONE call uses Base64 output, gate fires regardless of HEX siblings."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "src/services/good.ts", HEX_USAGE_TS)
            _write(root, "src/services/bad.ts", BASE64_OUTPUT_USAGE_TS)

            with self.assertRaises(ReleaseBlockerError) as cm:
                verify_app_hash_encoding(root)
            self.assertEqual(len(cm.exception.evidence), 1)
            self.assertIn("bad.ts", cm.exception.evidence[0]["file"])

    def test_blocker_message_carries_gate_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "src/x.ts", BASE64_OUTPUT_USAGE_TS)
            try:
                verify_app_hash_encoding(root)
                self.fail("expected ReleaseBlockerError")
            except ReleaseBlockerError as e:
                self.assertIn("verify_app_hash_encoding", str(e))


class TestVerifyAppHashEncodingMissingRepo(unittest.TestCase):

    def test_missing_repo_raises_app_repo_not_accessible(self):
        with self.assertRaises(AppRepoNotAccessibleError):
            verify_app_hash_encoding(Path("/nonexistent/mindfulnest-app-repo"))

    def test_file_path_raises_app_repo_not_accessible(self):
        """Passing a file (not a dir) must raise AppRepoNotAccessibleError."""
        with tempfile.NamedTemporaryFile() as tmpfile:
            with self.assertRaises(AppRepoNotAccessibleError):
                verify_app_hash_encoding(Path(tmpfile.name))


if __name__ == "__main__":
    unittest.main()
