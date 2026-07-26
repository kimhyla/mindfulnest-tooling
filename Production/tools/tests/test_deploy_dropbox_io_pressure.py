"""Deploy must not grind the Dropbox File Provider, and gates must fail readably.

Two regressions from the 2026-07-26 cold-boot incident are locked here:

1. The tooling -> Dropbox mirror re-stat'd ~3.9k node_modules files on every
   deploy (~45 min observed for 3 changed files). That traffic is the same
   File Provider pressure that produced the errno 11 crash-loop across the
   Event fleet, so the mirror must exclude regenerable build inputs.

2. Gate scripts fetched Dropbox-backed JSON endpoints with `curl -sf` and piped
   the result straight into json.loads. A slow cold library walk yielded an
   empty body and an opaque JSONDecodeError with no URL, which is what killed
   the deploy at the library panel gate.

Both are exercised for real -- the rsync flags are read out of the deploy
script and run against a fixture tree, and event_curl_json is run against live
local HTTP servers -- so behaviour is locked rather than script wording.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "scripts" / "deploy_storyboard_v59.sh"
PORT_LIB = REPO / "scripts" / "event_server_port.sh"

# Regenerable build inputs the Dropbox runtime never reads. dist/index.html is
# copied explicitly by deploy step (c) and is deliberately not in this set.
BUILD_INPUTS = ("node_modules", ".vite", "__pycache__", ".venv")


def _mirror_rsync_excludes() -> list[str]:
    """Pull the exclude flags off the real mirror rsync in the deploy script."""
    text = DEPLOY.read_text(encoding="utf-8")
    marker = 'rsync -a --delete \\'
    start = text.index(marker)
    block = text[start : text.index('"$SRC_TOOLING/$sub/"', start)]
    return re.findall(r"--exclude '([^']+)'", block)


def test_mirror_excludes_regenerable_build_inputs() -> None:
    excludes = _mirror_rsync_excludes()
    for name in BUILD_INPUTS:
        assert name in excludes, (
            f"deploy mirror must exclude {name!r}; mirroring it re-stats "
            f"thousands of files through Dropbox every deploy. got={excludes}"
        )


def test_mirror_still_excludes_runtime_stitch_state() -> None:
    """The pre-existing runtime-data exclusion must survive the new ones."""
    assert "stitch_editor_state.json" in _mirror_rsync_excludes()


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync required")
def test_mirror_flags_skip_and_preserve_node_modules(tmp_path: Path) -> None:
    """Run the deploy script's own exclude set against a fixture tree.

    Covers both halves of the fix: node_modules is not pushed, and an existing
    Dropbox-side copy is left alone rather than torn down by --delete (an
    excluded path is protected from deletion).
    """
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    (src / "storyboard-v2" / "node_modules" / "left-pad").mkdir(parents=True)
    (src / "storyboard-v2" / "node_modules" / "left-pad" / "index.js").write_text(
        "module.exports = 1;\n", encoding="utf-8"
    )
    (src / "production_server.py").write_text("print('real code')\n", encoding="utf-8")

    (dest / "storyboard-v2" / "node_modules" / "stale-pkg").mkdir(parents=True)
    (dest / "storyboard-v2" / "node_modules" / "stale-pkg" / "index.js").write_text(
        "module.exports = 0;\n", encoding="utf-8"
    )

    cmd = ["rsync", "-a", "--delete"]
    for name in _mirror_rsync_excludes():
        cmd += ["--exclude", name]
    cmd += [f"{src}/", f"{dest}/"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr

    assert (dest / "production_server.py").is_file(), "real code must still mirror"
    assert not (dest / "storyboard-v2" / "node_modules" / "left-pad").exists(), (
        "node_modules must not be pushed into Dropbox"
    )
    assert (dest / "storyboard-v2" / "node_modules" / "stale-pkg" / "index.js").is_file(), (
        "--delete must not tear down an excluded Dropbox-side node_modules"
    )


def _run_event_curl_json(url: str, *, max_time: str = "10", attempts: str = "1") -> subprocess.CompletedProcess:
    script = textwrap.dedent(
        f"""
        set -euo pipefail
        source {PORT_LIB!s}
        event_curl_json "$1" "{max_time}" "{attempts}"
        """
    )
    return subprocess.run(["bash", "-c", script, "bash", url], capture_output=True, text=True)


class _Server:
    """Tiny local HTTP server so the helper is tested against real sockets."""

    def __init__(self, handler_body: str) -> None:
        self._body = handler_body
        self._proc: subprocess.Popen | None = None
        self.port = 0

    def __enter__(self) -> "_Server":
        code = (
            "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
            "class H(BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            + textwrap.indent(self._body, " " * 8)
            + "\n"
            "    def log_message(self, *a):\n"
            "        pass\n"
            'srv = HTTPServer(("127.0.0.1", 0), H)\n'
            "print(srv.server_port, flush=True)\n"
            "srv.serve_forever()\n"
        )
        self._proc = subprocess.Popen(
            [sys.executable, "-c", code], stdout=subprocess.PIPE, text=True
        )
        assert self._proc.stdout is not None
        self.port = int(self._proc.stdout.readline().strip())
        return self

    def __exit__(self, *exc) -> None:
        if self._proc is not None:
            self._proc.terminate()
            self._proc.wait(timeout=10)


def test_event_curl_json_returns_body_on_success() -> None:
    body = textwrap.dedent(
        """
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"images": [1, 2, 3]}')
        """
    ).strip()
    with _Server(body) as srv:
        res = _run_event_curl_json(f"http://127.0.0.1:{srv.port}/api/cr/library")
    assert res.returncode == 0, res.stderr
    assert '"images"' in res.stdout


def test_event_curl_json_fails_readably_on_empty_body() -> None:
    """The exact deploy-killing shape: 200-with-nothing must not reach json.loads."""
    body = textwrap.dedent(
        """
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"")
        """
    ).strip()
    with _Server(body) as srv:
        url = f"http://127.0.0.1:{srv.port}/api/cr/library"
        res = _run_event_curl_json(url)
    assert res.returncode != 0
    assert "JSONDecodeError" not in res.stderr, "must not surface a raw traceback"
    assert "[event-curl-json] FAIL" in res.stderr
    assert url in res.stderr, "failure must name the URL that failed"


def test_event_curl_json_fails_readably_on_http_error() -> None:
    body = textwrap.dedent(
        """
        self.send_response(500)
        self.end_headers()
        self.wfile.write(b"THUMB_GENERATION_FAILED")
        """
    ).strip()
    with _Server(body) as srv:
        res = _run_event_curl_json(f"http://127.0.0.1:{srv.port}/api/cr/library")
    assert res.returncode != 0
    assert "http=500" in res.stderr


def test_event_curl_json_retries_before_giving_up() -> None:
    """A cold Dropbox walk can fail once and succeed on the warm retry."""
    body = textwrap.dedent(
        """
        H.hits = getattr(H, "hits", 0) + 1
        if H.hits == 1:
            self.send_response(503)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"images": []}')
        """
    ).strip()
    with _Server(body) as srv:
        res = _run_event_curl_json(
            f"http://127.0.0.1:{srv.port}/api/cr/library", attempts="2"
        )
    assert res.returncode == 0, res.stderr
    assert '"images"' in res.stdout


def test_dropbox_timeout_default_clears_observed_cold_walk() -> None:
    """Cold Event_4 library list measured ~70s; gates must not sit at 30-60s."""
    res = subprocess.run(
        ["bash", "-c", f'source {PORT_LIB!s}; echo "$EVENT_DROPBOX_CURL_MAX_SECONDS"'],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    assert int(res.stdout.strip()) >= 120


def test_event_load_pin_waits_on_shared_cold_boot_budget() -> None:
    """g.5 gave up after ~3 min while a 4-5 min fleet cold boot was still
    reconciling; the server answered 200 moments after the deploy died. The
    pin must first wait on event_server_wait_http (EVENT_SERVER_COLD_BOOT_
    ATTEMPTS budget) instead of its own short retry loop."""
    text = DEPLOY.read_text(encoding="utf-8")
    pin = text.index("(g.5) post-restart event/load pin")
    load_call = text.index("/api/event/load", pin)
    wait = text.find("event_server_wait_http", pin)
    assert wait != -1 and wait < load_call, (
        "g.5 must call event_server_wait_http before attempting event/load"
    )


def test_json_sidecar_lock_lives_off_dropbox(tmp_path: Path, monkeypatch) -> None:
    """Third missed site of the locks-off-Dropbox invariant: milestone scope
    forces JSON sidecar authority, and its flock file sat next to the sidecar
    on Dropbox. open() on that File Provider path wedged uninterruptibly in
    the kernel (35+ min observed) while holding event_load_lock, hanging every
    scope-touching request on the port. Exercises the real lock context."""
    sys.path.insert(0, str(REPO / "tools"))
    import beat_generator as bg

    fake_sidecar = tmp_path / "Dropbox" / "Milestones" / "m1" / "beat_generator_sidecar.json"
    fake_sidecar.parent.mkdir(parents=True)
    fake_sidecar.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(fake_sidecar))

    with bg._legacy_json_sidecar_file_lock(timeout_s=5.0):
        dropbox_side = fake_sidecar.with_name(fake_sidecar.name + ".lock")
        assert not dropbox_side.exists(), (
            "sidecar lock file must never be created on the Dropbox side"
        )

    lock_path = Path(bg._local_sidecar_lock_path(str(fake_sidecar)))
    assert lock_path.exists()
    assert str(lock_path).startswith(str(Path.home() / ".mindfulnest" / "locks")), (
        f"sidecar lock must live under ~/.mindfulnest/locks, got {lock_path}"
    )
    other = bg._local_sidecar_lock_path(str(fake_sidecar.with_name("other.json")))
    assert other != str(lock_path), "each sidecar path needs its own lock file"


def test_file_sha256_hashes_each_file_once(tmp_path: Path, monkeypatch) -> None:
    """Speaker heals hash the same Element/pose images once per beat; on a cold
    Dropbox provider that held the sidecar lock for tens of minutes and hung
    every scope swap behind it. A (size, mtime)-keyed cache must answer repeat
    calls from a stat, and re-hash only when the content actually changes."""
    sys.path.insert(0, str(REPO / "tools"))
    import kling_character_registry as reg

    monkeypatch.setattr(reg, "_SHA_CACHE_PATH", tmp_path / "cache" / "sha.json")
    monkeypatch.setattr(reg, "_SHA_CACHE", None)
    monkeypatch.setattr(reg, "_SHA_CACHE_UNSAVED", 0)
    monkeypatch.setattr(reg, "_SHA_CACHE_FLUSH_EVERY", 1)

    img = tmp_path / "tessa_neutral.png"
    img.write_bytes(b"pose bytes v1")

    opens = []
    real_open = Path.open

    def _counting_open(self, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if self == img and "r" in mode:
            opens.append(mode)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _counting_open)

    first = reg.file_sha256(img)
    again = reg.file_sha256(img)
    assert first == again == hashlib_sha256(b"pose bytes v1")
    assert len(opens) == 1, f"repeat call must be served from cache, opens={len(opens)}"

    # Fresh process (cold in-memory cache) must hit the persisted cache too.
    monkeypatch.setattr(reg, "_SHA_CACHE", None)
    assert reg.file_sha256(img) == first
    assert len(opens) == 1, "persisted cache must survive process restarts"

    img.write_bytes(b"pose bytes v2 re-registered")
    os_utime_bump(img)
    changed = reg.file_sha256(img)
    assert changed == hashlib_sha256(b"pose bytes v2 re-registered")
    assert len(opens) == 2, "content change must force exactly one re-hash"


def hashlib_sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def os_utime_bump(p: Path) -> None:
    """Guarantee a distinct mtime_ns even on coarse filesystem clocks."""
    import os

    st = p.stat()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))


def test_find_pose_rel_by_hash_indexes_dir_once(tmp_path: Path, monkeypatch) -> None:
    """Sidecar migrate heals every beat; each heal used to re-hash every pose file.
    A fingerprint-keyed index must rebuild once per poses-dir change, not per call."""
    sys.path.insert(0, str(REPO / "tools"))
    import kling_character_registry as reg

    monkeypatch.setattr(reg, "_SHA_CACHE_PATH", tmp_path / "cache" / "sha.json")
    monkeypatch.setattr(reg, "_SHA_CACHE", None)
    monkeypatch.setattr(reg, "_POSE_HASH_INDEX", {})
    monkeypatch.setattr(reg, "prod_root", lambda: tmp_path)

    poses = tmp_path / "Tessa" / "poses"
    poses.mkdir(parents=True)
    (poses / "a.png").write_bytes(b"pose-a")
    (poses / "b.png").write_bytes(b"pose-b")
    probe = tmp_path / "library_copy.png"
    probe.write_bytes(b"pose-b")

    opens: list[str] = []
    real_open = Path.open

    def _counting_open(self, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if self.parent == poses and "r" in mode:
            opens.append(self.name)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _counting_open)

    first = reg.find_pose_rel_by_hash("Tessa", str(probe))
    assert first == "Tessa/poses/b.png"
    first_opens = len(opens)
    assert first_opens >= 2, "first call must hash the poses dir"

    again = reg.find_pose_rel_by_hash("Tessa", str(probe))
    assert again == first
    assert len(opens) == first_opens, (
        f"repeat call must use the index (opens {first_opens} -> {len(opens)})"
    )


def test_infer_char_ref_skips_pose_dir_under_heal_path() -> None:
    """infer_char_ref_registry_speaker must not enable pose-dir fallback — that
    path runs under the sidecar lock during migrate and re-hashed every poses/
    dir for every beat (deploy hang class, 2026-07-26)."""
    src = (REPO / "tools" / "beat_generator.py").read_text(encoding="utf-8")
    start = src.index("def infer_char_ref_registry_speaker")
    end = src.index("\ndef ", start + 1)
    block = src[start:end]
    assert "allow_pose_dir_fallback=False" in block
    assert "allow_pose_dir_fallback=True" not in block


def test_library_panel_gate_uses_shared_fetch_helper() -> None:
    """The gate that failed the deploy must go through the hardened helper."""
    gate = (REPO / "scripts" / "verify_library_panel_contract_durability.sh").read_text(
        encoding="utf-8"
    )
    assert "event_curl_json" in gate
    assert "curl -sf --max-time 60" not in gate, "short raw curl reintroduced"
