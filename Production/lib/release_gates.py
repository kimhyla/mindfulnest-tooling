"""
release_gates.py — Phase B + Phase D release-blocker gates for the
V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md pipeline.

Authored: Phase B (2026-05-10) per spec §3.3 R3 — execution-time gate that
greps the MindfulNest app repo for `digestStringAsync` call sites and refuses
to advance to Phase D `r2_atomic_publish` if any call uses
`CryptoEncoding.Base64` as the OUTPUT encoding (which would invalidate the
single-hex-hash R3 strategy).

Governing LDs:
  - LD-404 MANIFEST_SCHEMA_V1 (hex-only content_hash pattern ^[a-f0-9]{64}$)
  - LD-432 CDN_CLOUDFLARE_R2_V1 (R2 cutover)
  - Spec §3.3 + §15.7 (gate intent + app repo path policy)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional


# Default MindfulNest app repo location per spec §15.7. Callers may override.
DEFAULT_APP_REPO_PATH = Path("/Users/kimberlysmith/Projects/MindfulNest")

# File extensions to scan for digestStringAsync usage.
_APP_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")

# Directories to skip when scanning (test mocks + vendored deps).
_SKIP_DIR_NAMES = {"node_modules", "__tests__", ".git", "dist", "build"}


class ReleaseBlockerError(RuntimeError):
    """Raised when a release-blocker condition is detected by a gate.

    The `gate` attribute names which gate fired (e.g. ``"verify_app_hash_encoding"``)
    so callers can log structured audit rows.
    """

    def __init__(self, gate: str, message: str, evidence: Optional[List[dict]] = None):
        self.gate = gate
        self.evidence = evidence or []
        super().__init__(f"[{gate}] {message}")


class AppRepoNotAccessibleError(RuntimeError):
    """Raised when verify_app_hash_encoding cannot reach the app repo.

    Distinct from ReleaseBlockerError because an inaccessible app repo is
    not a release blocker — it's an execution-environment gap (the gate
    should be re-run on a machine that has the repo cloned). Per spec
    §15.7 + brief's DS-18 fallback: in execution contexts where the app
    repo is intentionally absent (CI containers, sandboxed agents), the
    caller may treat this as a WARNING and proceed, but production
    `r2_atomic_publish` MUST fail-CLOSED on this.
    """


def _iter_app_source_files(app_repo_path: Path) -> List[Path]:
    """Yield .ts/.tsx/.js/.jsx files under app_repo_path/src, skipping test/mock dirs.

    Restricting to `src/` mirrors the spec's intent — the gate concerns
    production runtime calls, not test mocks or build artifacts. If
    `src/` doesn't exist (e.g. monorepo with a different layout), falls
    back to the repo root with the same skip rules.
    """
    root = app_repo_path / "src"
    if not root.exists() or not root.is_dir():
        root = app_repo_path

    matches: List[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in _APP_EXTENSIONS:
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        matches.append(path)
    return matches


def _extract_call_arg_block(text: str, call_start: int) -> str:
    """Given an index at the opening '(' of a call, return the parenthesized
    argument block (including the outer parens).

    Naive paren-balanced scan; ignores string-literal nesting. Robust enough
    for the digestStringAsync signature which is always a 3-arg call.
    Returns empty string if the call is unterminated.
    """
    if call_start >= len(text) or text[call_start] != "(":
        return ""
    depth = 0
    i = call_start
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[call_start : i + 1]
        i += 1
    return ""


# Match `digestStringAsync(` at a call site (allow whitespace between name + paren).
_DIGEST_CALL_RE = re.compile(r"digestStringAsync\s*\(")

# Match the OUTPUT encoding param specifically — a Base64 OUTPUT (which the gate
# rejects). The INPUT param `base64` (a variable name holding a string) is fine
# because R1's compute_app_compat_content_hash() hashes the same raw-byte form.
# We look for the pattern `CryptoEncoding.Base64` anywhere inside the call args,
# which catches both `{ encoding: Crypto.CryptoEncoding.Base64 }` and the
# unqualified-import form `{ encoding: CryptoEncoding.Base64 }`.
_BASE64_OUTPUT_RE = re.compile(r"CryptoEncoding\s*\.\s*Base64")


def verify_app_hash_encoding(
    app_repo_path: Optional[Path] = None,
) -> dict:
    """Phase B + Phase D execution-time gate: ensure the app's expo-crypto
    digestStringAsync calls use HEX (not Base64) as OUTPUT encoding.

    Per spec §3.3 R3:
      - Step 2: grep `digestStringAsync` calls in the app repo.
      - Step 3: If all calls use HEX (or default) → return success.
      - Step 4: If any call uses `CryptoEncoding.Base64` as output encoding
        → raise ReleaseBlockerError. Caller (Phase D r2_atomic_publish) MUST
        abort publish.

    The gate is intentionally precise: it matches `CryptoEncoding.Base64`
    only, not `EncodingType.Base64` which is the FileSystem read-as-base64
    INPUT form (legitimate — bytes-as-base64 input + HEX output is what
    `compute_app_compat_content_hash` already produces post-R3).

    Args:
        app_repo_path: Path to the MindfulNest app repo. Defaults to
            DEFAULT_APP_REPO_PATH per spec §15.7.

    Returns:
        Dict with the gate result on PASS:
            {
                "gate": "verify_app_hash_encoding",
                "result": "pass",
                "files_scanned": int,
                "digest_call_count": int,
                "evidence": [{"file": str, "snippet": str}, ...]
            }

    Raises:
        AppRepoNotAccessibleError: app_repo_path does not exist or is unreadable.
        ReleaseBlockerError: at least one digestStringAsync call uses Base64
            output encoding. Caller MUST abort r2_atomic_publish.
    """
    path = Path(app_repo_path) if app_repo_path is not None else DEFAULT_APP_REPO_PATH

    if not path.exists() or not path.is_dir():
        raise AppRepoNotAccessibleError(
            f"verify_app_hash_encoding: app repo not found at {path}. "
            f"Per spec §15.7, set app_repo_path explicitly or clone the app repo "
            f"to {DEFAULT_APP_REPO_PATH}."
        )

    files = _iter_app_source_files(path)
    blocker_evidence: List[dict] = []
    pass_evidence: List[dict] = []
    digest_call_count = 0

    for src in files:
        try:
            text = src.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for match in _DIGEST_CALL_RE.finditer(text):
            digest_call_count += 1
            call_block = _extract_call_arg_block(text, match.end() - 1)
            uses_base64_output = bool(_BASE64_OUTPUT_RE.search(call_block))
            evidence_entry = {
                "file": str(src),
                "snippet": call_block[:300] if call_block else "<unterminated call>",
                "uses_base64_output": uses_base64_output,
            }
            if uses_base64_output:
                blocker_evidence.append(evidence_entry)
            else:
                pass_evidence.append(evidence_entry)

    if blocker_evidence:
        raise ReleaseBlockerError(
            gate="verify_app_hash_encoding",
            message=(
                f"Found {len(blocker_evidence)} digestStringAsync call(s) using "
                f"CryptoEncoding.Base64 OUTPUT encoding. This invalidates the "
                f"R3 single-hex-hash strategy per spec §3.3. Either change the "
                f"app to CryptoEncoding.HEX (preferred) or fall back to dual-form "
                f"per spec §13 Open Kim Decision 3."
            ),
            evidence=blocker_evidence,
        )

    return {
        "gate": "verify_app_hash_encoding",
        "result": "pass",
        "files_scanned": len(files),
        "digest_call_count": digest_call_count,
        "evidence": pass_evidence,
    }
