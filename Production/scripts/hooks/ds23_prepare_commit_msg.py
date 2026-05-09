"""
DS-23 prepare-commit-msg hook — post-fix pattern sweep gate.

Normative design: Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v3.md
§7.1.1-v3-E (HALTED_FILES live consultation), §3.2-v3 (both-grammar acceptance),
§11.7 (DS-24 halt mechanism PIN), §11.7-v3-C (3-tier escalation).

Behavior (exit codes contractual):
  0 — gate passed (sweep block appended OR gate not applicable for this commit)
  1 — gate failed (security-adjacent file modified, no sweep evidence, no bypass)

Contract surfaces:
  - Reads pattern from Production/scripts/ds23_pattern_config.txt (canonical default
    embedded as fallback — Phase A creates the file).
  - Identifies security-adjacent paths in `git diff --cached --name-only`
    using SECURITY_GLOBS (top-level + nested coverage per §6.5 AT21/AF11).
  - Consults prod_blockers for DS_24_FP_LOOP_SUSPECTED_<F> rows (§11.7) — files
    matched are skipped from DS-24 sweep but STILL run DS-23 (separate halt class).
  - Greps staged file contents for the canonical regex.
  - On match: appends `Swept: <files>` + `Verified: <count>` to commit message
    (short-form grammar — v2 hook-generated form per §3.2-v3 option b).
  - On no match (security file touched but no pattern hit): require pre-existing
    sweep block via union regex `^Swept(:| .+ for `)` OR exit 1.
  - MN_SKIP_DS23_GATE=1 bypass: append `DS-23 sweep waived` notice; exit 0.
    Caller MUST follow up with a DS_23_GATE_BYPASSED activity-log row carrying
    `details.commit_sha` (CI's nested-key jsonb filter validates per §7.1.2).

NO urllib/requests direct calls — uses DirectusAdminClient (DS-30) when available;
falls back to graceful degradation when offline (e.g. PR2OK fence pre-commit, no
network) — degradation surfaces a stderr notice and treats HALTED_FILES as empty.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

# Production root resolution — supports both in-repo and standalone install.
_PRODUCTION_ROOT = Path(__file__).resolve().parents[2]
if str(_PRODUCTION_ROOT) not in sys.path:
    sys.path.insert(0, str(_PRODUCTION_ROOT))

# Lazy import — DirectusAdminClient is only needed when the hook actually fires
# AND credentials are available. Tests inject mock clients; hook caller may run
# offline (no Directus reachable) — in that case the halt list is empty + a
# stderr notice is emitted (§11.7 step 3 pre-fetch is per-commit, not crash-on-error).


# ---------------------------------------------------------------------------
# Config — canonical regex + globs (§7.1.1 v3-E)
# ---------------------------------------------------------------------------

# §7.1.1 v3-D + v3-E: BOTH top-level and nested patterns required.
# Bash `**/*.ts` does NOT match `functions/src/index.ts` (top-level entry —
# canonical Firebase Functions entry-point file). Verified empirically.
SECURITY_GLOBS: tuple[str, ...] = (
    "production_server.py",
    "Production/lib/*.py",
    "firestore/rules/*",
    "functions/src/*.ts",         # v3-D top-level
    "functions/src/**/*.ts",      # v3-A nested
    "functions/src/*.js",         # v3-D top-level
    "functions/src/**/*.js",      # v3-A nested
)

# §7.1.1 v3-D + v3-C: explicit allow-list, word-boundary bounded.
# Lives in Production/scripts/ds23_pattern_config.txt; this is the embedded
# fallback used when the config file is absent (allows hook to ship before
# Phase A creates the file; Phase A's G14 gate verifies the file exists).
CANONICAL_PATTERN_DEFAULT = (
    r"\b(secret|credential|token|password|api[_-]?key|auth|authn|authz"
    r"|authentication|authorization|jwt|bearer|oauth|saml|sso"
    r"|session[_-]?(?:id|key|token))\b"
)

# §3.2-v3 / §7.1.2 v3: union regex matches BOTH legacy and short-form grammars.
# legacy: `Swept <FILE> for `<PATTERN>`:`
# short:  `Swept: <FILE_LIST>`
SWEPT_UNION_RE = re.compile(r"^Swept(:| .+ for `)", re.MULTILINE)


# ---------------------------------------------------------------------------
# IO helpers — pure functions; tests inject deterministic substitutes.
# ---------------------------------------------------------------------------


def load_pattern_config(config_path: Path) -> str:
    """Return the active regex pattern.

    Strips `#` comments + blank lines; first non-comment line wins.
    Falls back to CANONICAL_PATTERN_DEFAULT when the file is absent (so the
    hook is shippable before Phase A creates the file). When the file exists
    but contains only comments/blanks, raise — that's a malformed config that
    G14 should catch.
    """
    if not config_path.exists():
        return CANONICAL_PATTERN_DEFAULT

    for raw in config_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        return line

    raise RuntimeError(
        f"FATAL DS-23: pattern config {config_path} exists but contains no non-comment line."
    )


def get_staged_files(repo_root: Path) -> list[str]:
    """Run `git diff --cached --name-only` from repo_root."""
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        check=False,
    )
    if proc.returncode != 0:
        # git may be unavailable in tests; treat as empty staged set.
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def matches_glob(path: str, pattern: str) -> bool:
    """True when `path` matches `pattern` using bash-style ** semantics.

    Critical: bash `functions/src/**/*.ts` matches ONLY depth >= 2 (e.g.
    `functions/src/nested/foo.ts`) and NOT top-level `functions/src/index.ts`.
    We replicate that here so SECURITY_GLOBS remains source-of-truth. The
    top-level companion `functions/src/*.ts` catches the index.ts case
    (G16 / AT21 / AF11 enforcement).
    """
    return _bash_glob_match(path, pattern)


def _bash_glob_match(path: str, pattern: str) -> bool:
    """
    Re-implement bash `extglob`-style ** matching.

    Rules (matching bash behavior we exploit in §7.1.1):
      - `*`           — any sequence of chars EXCLUDING `/`
      - `**`          — any sequence including `/` (>= 1 char), but here we
                        require `**/` separator → matches one or more dirs
                        (so `a/**/b` matches `a/x/b` and `a/x/y/b`, NOT `a/b`).
      - non-glob chars match literally.
    """
    # Translate to anchored regex
    out: list[str] = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                # `**/` consumes one or more path segments
                if i + 2 < len(pattern) and pattern[i + 2] == "/":
                    out.append(r"(?:[^/]+/)+")
                    i += 3
                    continue
                # Bare `**` (no trailing slash) — match everything
                out.append(r".*")
                i += 2
                continue
            out.append(r"[^/]*")
            i += 1
            continue
        if c == "?":
            out.append(r"[^/]")
            i += 1
            continue
        if c in r".+()[]{}^$|\\":
            out.append(re.escape(c))
            i += 1
            continue
        out.append(c)
        i += 1
    return re.fullmatch("".join(out), path) is not None


def grep_pattern_in_files(files: Iterable[str], pattern: str, repo_root: Path) -> tuple[list[str], int]:
    """Return (files_with_match, total_match_count).

    Reads file contents directly (tests inject; production resolves against repo_root).
    """
    matched_files: list[str] = []
    total = 0
    pat = re.compile(pattern, re.IGNORECASE)
    for rel in files:
        path = repo_root / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        hits = pat.findall(text)
        if hits:
            matched_files.append(rel)
            total += len(hits)
    return matched_files, total


# ---------------------------------------------------------------------------
# DS-24 halt-list lookup (§11.7 / §11.7-v3-C Tier 1)
# ---------------------------------------------------------------------------


def fetch_halted_files(client: Optional[Any]) -> set[str]:
    """Read prod_blockers for active DS_24_FP_LOOP_SUSPECTED_<F> rows.

    Returns the set of file paths currently halted from DS-24 sweep.
    Empty set on any failure (offline, missing creds, schema drift) — failure
    surfaces as a stderr warning but does NOT block the commit (§11.7 Tier 1
    semantics: halt is observable, not destructive).
    """
    if client is None:
        return set()
    try:
        rows = client.get_items(
            "prod_blockers",
            filters={
                "blocker_type": {"_starts_with": "DS_24_FP_LOOP_SUSPECTED_"},
                "is_resolved": {"_eq": False},
            },
            fields=["blocker_type"],
        )
    except Exception as exc:  # pragma: no cover — offline path
        sys.stderr.write(
            f"DS_23_HOOK_NOTICE: prod_blockers fetch failed ({type(exc).__name__}); "
            "halt list treated as empty.\n"
        )
        return set()

    halted: set[str] = set()
    prefix = "DS_24_FP_LOOP_SUSPECTED_"
    for row in rows or []:
        bt = row.get("blocker_type") if isinstance(row, dict) else None
        if isinstance(bt, str) and bt.startswith(prefix):
            halted.add(bt[len(prefix):])
    return halted


# ---------------------------------------------------------------------------
# Core gate — pure function; CLI is a thin wrapper.
# ---------------------------------------------------------------------------


class GateResult:
    """Structured outcome — exposed for tests + CLI exit-mapping."""

    __slots__ = (
        "exit_code",
        "appended_lines",
        "halted_files",
        "swept_files",
        "verified_count",
        "fail_reason",
        "stderr_lines",
    )

    def __init__(
        self,
        exit_code: int,
        appended_lines: list[str],
        halted_files: list[str],
        swept_files: list[str],
        verified_count: int,
        fail_reason: Optional[str],
        stderr_lines: list[str],
    ) -> None:
        self.exit_code = exit_code
        self.appended_lines = appended_lines
        self.halted_files = halted_files
        self.swept_files = swept_files
        self.verified_count = verified_count
        self.fail_reason = fail_reason
        self.stderr_lines = stderr_lines


def run_gate(
    *,
    commit_msg_text: str,
    staged_files: list[str],
    pattern: str,
    halted_files: set[str],
    grep_fn,
    bypass_env: bool,
) -> GateResult:
    """Pure-functional gate: takes inputs, returns structured outcome.

    Args:
        commit_msg_text: current contents of the commit message file.
        staged_files: list of paths from `git diff --cached --name-only`.
        pattern: canonical regex (already loaded from config).
        halted_files: set of paths under active DS_24_FP_LOOP_SUSPECTED halt.
        grep_fn: callable(files, pattern) -> (matched_files, total_count).
                 Injected so tests don't need real files on disk.
        bypass_env: True when MN_SKIP_DS23_GATE=1.
    """
    appended: list[str] = []
    stderr_lines: list[str] = []

    if bypass_env:
        appended.append("")
        appended.append(
            "DS-23 sweep waived (MN_SKIP_DS23_GATE=1; see DS_23_GATE_BYPASSED audit row)"
        )
        return GateResult(
            exit_code=0,
            appended_lines=appended,
            halted_files=[],
            swept_files=[],
            verified_count=0,
            fail_reason=None,
            stderr_lines=stderr_lines,
        )

    # Identify security-adjacent paths via SECURITY_GLOBS (§7.1.1 v3-D 2-pattern coverage).
    security_files: list[str] = []
    halted_in_set: list[str] = []
    for staged in staged_files:
        for glob in SECURITY_GLOBS:
            if matches_glob(staged, glob):
                security_files.append(staged)
                # §7.1.1 v3-E HIGH-1 FIX: actually consult HALTED_FILES per staged path.
                # File still added to security_files so DS-23 sweep continues; the
                # halt is a DS-24 concern (separate halt class per §11.7-v3-C).
                if staged in halted_files:
                    halted_in_set.append(staged)
                break

    # §7.1.1 v3-E: emit DS_24_HALTED_BY_BLOCKER notice for each halted file.
    for halted in halted_in_set:
        stderr_lines.append(
            f"DS_24_HALTED_BY_BLOCKER: {halted} skipped from DS-24 sweep "
            "per active prod_blockers row"
        )

    if not security_files:
        # No security-adjacent files touched — DS-23 N/A; pass through.
        return GateResult(
            exit_code=0,
            appended_lines=[],
            halted_files=halted_in_set,
            swept_files=[],
            verified_count=0,
            fail_reason=None,
            stderr_lines=stderr_lines,
        )

    swept_files, verified_count = grep_fn(security_files, pattern)

    if swept_files:
        # §3.2-v3 / §7.1.2 v3: append short-form grammar.
        appended.append("")
        appended.append("Swept: " + " ".join(swept_files))
        appended.append(f"Verified: {verified_count}")
        return GateResult(
            exit_code=0,
            appended_lines=appended,
            halted_files=halted_in_set,
            swept_files=swept_files,
            verified_count=verified_count,
            fail_reason=None,
            stderr_lines=stderr_lines,
        )

    # Security file modified, no pattern hit — require pre-existing sweep block.
    if SWEPT_UNION_RE.search(commit_msg_text):
        return GateResult(
            exit_code=0,
            appended_lines=[],
            halted_files=halted_in_set,
            swept_files=[],
            verified_count=0,
            fail_reason=None,
            stderr_lines=stderr_lines,
        )

    fail_reason = (
        "FATAL DS-23: security-adjacent file modified, no Swept block in commit message.\n"
        "  Either accept the canonical short form via the hook's auto-append,\n"
        "  OR hand-author the legacy form (`Swept <FILE> for `pattern`:`),\n"
        "  OR set MN_SKIP_DS23_GATE=1 + write DS_23_GATE_BYPASSED audit row "
        "with details.commit_sha=<sha>."
    )
    return GateResult(
        exit_code=1,
        appended_lines=[],
        halted_files=halted_in_set,
        swept_files=[],
        verified_count=0,
        fail_reason=fail_reason,
        stderr_lines=stderr_lines,
    )


# ---------------------------------------------------------------------------
# CLI entrypoint (prepare-commit-msg signature: $1 = commit message file path)
# ---------------------------------------------------------------------------


def _resolve_repo_root() -> Path:
    """Find repo root via `git rev-parse`; fall back to cwd."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            top = proc.stdout.strip()
            if top:
                return Path(top)
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.cwd()


def _build_client():
    """Instantiate DirectusAdminClient — return None on failure (offline path)."""
    try:
        from lib.directus_admin_client import DirectusAdminClient

        return DirectusAdminClient()
    except Exception as exc:
        sys.stderr.write(
            f"DS_23_HOOK_NOTICE: DirectusAdminClient unavailable ({type(exc).__name__}); "
            "halt list treated as empty.\n"
        )
        return None


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write(
            "DS-23 prepare-commit-msg: missing commit-msg file path arg.\n"
        )
        return 1

    commit_msg_path = Path(argv[1])
    if not commit_msg_path.exists():
        sys.stderr.write(
            f"DS-23 prepare-commit-msg: commit-msg file {commit_msg_path} not found.\n"
        )
        return 1

    repo_root = _resolve_repo_root()
    config_path = repo_root / "Production" / "scripts" / "ds23_pattern_config.txt"
    pattern = load_pattern_config(config_path)
    bypass = os.environ.get("MN_SKIP_DS23_GATE") == "1"
    staged = get_staged_files(repo_root)

    client = None if bypass else _build_client()
    halted = fetch_halted_files(client)

    def grep_fn(files, pat):
        return grep_pattern_in_files(files, pat, repo_root)

    commit_msg_text = commit_msg_path.read_text(encoding="utf-8", errors="replace")
    result = run_gate(
        commit_msg_text=commit_msg_text,
        staged_files=staged,
        pattern=pattern,
        halted_files=halted,
        grep_fn=grep_fn,
        bypass_env=bypass,
    )

    for line in result.stderr_lines:
        sys.stderr.write(line + "\n")

    if result.appended_lines:
        with commit_msg_path.open("a", encoding="utf-8") as fh:
            for line in result.appended_lines:
                fh.write(line + "\n")

    if result.exit_code != 0 and result.fail_reason:
        sys.stderr.write(result.fail_reason + "\n")

    return result.exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
