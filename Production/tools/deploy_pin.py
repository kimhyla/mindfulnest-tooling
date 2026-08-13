#!/usr/bin/env python3
"""DEPLOY_PIN_V1 — freeze the deploy identity at start.

Tonight's class: Option B verify re-read `git rev-parse HEAD` after another
agent switched the checkout, then FATALed a live fleet that was serving the
sha we actually deployed.

One pin for the whole deploy. Build, X-Tooling-Sha, and verify all use it.
Never re-read live HEAD after capture.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

_BUILD_SHA_META = re.compile(
    r'name="build-sha"\s+content="([^"]+)"', re.IGNORECASE
)

MARKER = "DEPLOY_PIN_V1"
PIN_FILENAME = ".deploy_pin"

# UI bundle identity — Python/scripts-only commits must not fleet-restart.
BUNDLE_PREFIXES: tuple[str, ...] = (
    "Production/tools/storyboard-v2/src/",
    "Production/tools/storyboard-v2/index.html",
    "Production/tools/storyboard-v2/vite.config.ts",
    "Production/tools/storyboard-v2/vite.config.js",
    "Production/tools/storyboard-v2/package.json",
    "Production/tools/storyboard-v2/package-lock.json",
    "Production/tools/storyboard-v2/public/",
)

BUNDLE_GIT_PATHSPECS: tuple[str, ...] = (
    "Production/tools/storyboard-v2/src",
    "Production/tools/storyboard-v2/index.html",
    "Production/tools/storyboard-v2/vite.config.ts",
    "Production/tools/storyboard-v2/vite.config.js",
    "Production/tools/storyboard-v2/package.json",
    "Production/tools/storyboard-v2/package-lock.json",
    "Production/tools/storyboard-v2/public",
)


def pin_file_for(tooling_root: Path) -> Path:
    return Path(tooling_root) / PIN_FILENAME


def _first_line(text: str) -> str:
    return (text or "").strip().splitlines()[0].strip() if text else ""


def resolve_expect_sha(
    *,
    env: dict[str, str] | None = None,
    pin_path: Path | None = None,
    git_head: str = "",
) -> str:
    """Return the frozen deploy sha.

    Priority: MN_EXPECT_BUILD_SHA / MN_DEPLOY_PINNED_SHA → pin file → git_head.
    git_head is last-resort for a standalone verify with no pin (operator
    rerun). Deploy itself must capture before any long gate so later HEAD
    drift cannot impersonate the identity we shipped.
    """
    env = env if env is not None else dict(os.environ)
    for key in ("MN_EXPECT_BUILD_SHA", "MN_DEPLOY_PINNED_SHA"):
        val = (env.get(key) or "").strip()
        if val:
            return val
    if pin_path is not None:
        try:
            if pin_path.is_file():
                val = _first_line(pin_path.read_text(encoding="utf-8"))
                if val:
                    return val
        except OSError:
            pass
    head = (git_head or "").strip()
    if head:
        return head
    raise SystemExit("FATAL: cannot resolve deploy sha (no pin, no env, no HEAD)")


def write_pin(pin_path: Path, sha: str) -> None:
    sha = sha.strip()
    if not sha:
        raise SystemExit("FATAL: cannot write empty deploy pin")
    pin_path.write_text(sha + "\n", encoding="utf-8")


def git_short_head(tooling_root: Path) -> str:
    out = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(tooling_root),
        text=True,
    )
    sha = out.strip()
    if not sha:
        raise SystemExit("FATAL: git rev-parse --short HEAD returned empty")
    return sha


def capture_pin(tooling_root: Path, pin_path: Path | None = None) -> str:
    sha = git_short_head(tooling_root)
    path = pin_path or pin_file_for(tooling_root)
    write_pin(path, sha)
    return sha


def path_is_bundle_source(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    for prefix in BUNDLE_PREFIXES:
        if prefix.endswith("/"):
            if normalized.startswith(prefix):
                return True
        elif normalized == prefix:
            return True
    return False


def bundle_source_changed(changed_paths: list[str]) -> bool:
    return any(path_is_bundle_source(p) for p in changed_paths if p.strip())


def _git_commit_exists(tooling_root: Path, sha: str) -> bool:
    if not sha:
        return False
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", f"{sha}^{{commit}}"],
        cwd=str(tooling_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


def read_html_build_sha(html_path: Path) -> str:
    try:
        text = Path(html_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    match = _BUILD_SHA_META.search(text)
    return match.group(1).strip() if match else ""


def git_bundle_paths_changed(
    tooling_root: Path, from_sha: str, to_sha: str
) -> bool:
    """True when storyboard UI source changed between two commits.

    Unknown / missing live sha → True (safe: fleet-restart). Same sha → False.
    """
    from_sha = (from_sha or "").strip()
    to_sha = (to_sha or "").strip()
    if not to_sha:
        return True
    if from_sha and from_sha == to_sha:
        return False
    if not from_sha or not _git_commit_exists(tooling_root, from_sha):
        return True
    if not _git_commit_exists(tooling_root, to_sha):
        return True
    out = subprocess.check_output(
        [
            "git",
            "diff",
            "--name-only",
            from_sha,
            to_sha,
            "--",
            *BUNDLE_GIT_PATHSPECS,
        ],
        cwd=str(tooling_root),
        text=True,
    )
    paths = [line.strip() for line in out.splitlines() if line.strip()]
    return bundle_source_changed(paths)


def _cmd_capture(args: argparse.Namespace) -> int:
    tooling = Path(args.tooling)
    pin_path = Path(args.pin_file) if args.pin_file else pin_file_for(tooling)
    print(capture_pin(tooling, pin_path))
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    tooling = Path(args.tooling)
    pin_path = Path(args.pin_file) if args.pin_file else pin_file_for(tooling)
    git_head = args.git_head
    if not git_head:
        try:
            git_head = git_short_head(tooling)
        except (OSError, subprocess.CalledProcessError):
            git_head = ""
    print(resolve_expect_sha(env=dict(os.environ), pin_path=pin_path, git_head=git_head))
    return 0


def _cmd_bundle_changed(args: argparse.Namespace) -> int:
    tooling = Path(args.tooling)
    if git_bundle_paths_changed(tooling, args.from_sha, args.to_sha):
        print("changed")
    else:
        print("unchanged")
    return 0


def _cmd_bundle_sha(args: argparse.Namespace) -> int:
    print(read_html_build_sha(Path(args.html)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DEPLOY_PIN_V1")
    sub = parser.add_subparsers(dest="cmd", required=True)

    cap = sub.add_parser("capture", help="Write .deploy_pin from current HEAD")
    cap.add_argument("--tooling", required=True)
    cap.add_argument("--pin-file", default="")
    cap.set_defaults(func=_cmd_capture)

    res = sub.add_parser("resolve", help="Resolve frozen sha (env > pin > HEAD)")
    res.add_argument("--tooling", required=True)
    res.add_argument("--pin-file", default="")
    res.add_argument("--git-head", default="")
    res.set_defaults(func=_cmd_resolve)

    bc = sub.add_parser("bundle-changed", help="changed|unchanged for UI source")
    bc.add_argument("--tooling", required=True)
    bc.add_argument("--from-sha", required=True, help="Live Dropbox HTML build-sha")
    bc.add_argument("--to-sha", required=True, help="Pinned deploy sha")
    bc.set_defaults(func=_cmd_bundle_changed)

    bs = sub.add_parser("bundle-sha", help="Read build-sha meta from an HTML file")
    bs.add_argument("--html", required=True)
    bs.set_defaults(func=_cmd_bundle_sha)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
