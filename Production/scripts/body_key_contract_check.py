#!/usr/bin/env python3
"""body_key_contract_check.py — Counter-B Option B CI grep gate.

Closes prod_blockers id=140. Detects body-key contract mismatches between the
storyboard-v2 client (pathappPatch / runMutation callers) and the server
(_handle_* functions in production_server.py) that have caused 4 silent
no-op bugs in 4 days (e.g. client sends `delay_seconds`, server reads
`audio_delay`).

CONTRACT
--------
For each mutation endpoint we collect:
  * Server reads — the union of literal keys passed to body.get("KEY"),
    body.get("KEY", ...), and body["KEY"] inside the _handle_* function bound
    to that endpoint's URL path in production_server.py.
  * Client sends — the union of object-literal keys passed to
    pathappPatch(scope, '<endpoint_name>', { K: ..., ... }) and
    runMutation('label', '<endpoint_name>', { K: ..., ... }) across every
    storyboard-v2/src/**/*.tsx file. Auto-injected baseline keys from
    pathappPatch are always added, plus runMutation auto-injects beat_id.

A mismatch is:
  CLIENT_EXTRA  — client sends KEY, no body.get("KEY")/body["KEY"] on server.
  SERVER_EXTRA  — server reads KEY, no client sends KEY for this endpoint.

ALLOWLIST
---------
Two annotation styles, both consumed:
  * Inline on a server line:
      raw = body.get("audio_delay")  # BODY_KEY_ALLOW: audio_delay (legacy back-compat)
  * Or above the _handle_* def or anywhere inside the handler body:
      # BODY_KEY_ALLOW: audio_delay legacy back-compat name retained
  * For client-extra exemptions, annotate near the call site:
      // BODY_KEY_ALLOW: scope_video_role auto-injected
A line of the form `# BODY_KEY_ALLOW: KEY <reason>` (Python) or
`// BODY_KEY_ALLOW: KEY <reason>` (TSX) declares one allowance for that key
within the same handler/file. The <reason> portion is required (>= 4 chars).

USAGE
-----
  python3 Production/scripts/body_key_contract_check.py [--root <path>] [--json]

Exit codes:
  0 — contract clean OR only allowlisted mismatches.
  1 — at least one un-allowlisted mismatch.
  2 — usage / parse / infrastructure error (Rule 19 — never silent).

CONTRIBUTING
------------
If pathappPatch gets a new wrapper helper, add the helper to
``CLIENT_WRAPPER_CALLEES`` so the regex extracts its body literal.
If a body literal cannot be statically extracted (computed key, spread of
non-literal variable, ternary key), the script will emit
UNANALYZABLE_CLIENT_CALL — these MUST be either refactored to a literal or
allowlisted with a justification.

Authority: prod_blockers id=140, LD `BODY_KEY_CONTRACT_CI_GREP_GATE_V1`.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVER_PATH_REL = "Production/tools/production_server.py"
CLIENT_GLOB_REL = "Production/tools/storyboard-v2/src"
ENDPOINTS_FILE_REL = "Production/tools/storyboard-v2/src/api/endpoints.ts"

# Client helpers whose body argument we extract. Each entry is (callee_name,
# arg_index_for_endpoint, arg_index_for_body, auto_injected_keys).
#
#   pathappPatch(scope, endpoint, body, opts?)   — endpoint=1, body=2
#   runMutation(label, endpoint, body)           — endpoint=1, body=2
#     runMutation also spreads { beat_id: beatId, ...body } so we auto-add beat_id.
CLIENT_WRAPPER_CALLEES: Dict[str, Dict[str, object]] = {
    "pathappPatch": {
        "endpoint_arg_index": 1,
        "body_arg_index": 2,
        # pathappPatch baseline payload (see src/api/pathappPayload.ts):
        #   scope_video_role, scope_target_video, beat_id, ...body,
        #   scope_event_id, scope_version, scope_milestone_id (when milestone scope active).
        "auto_keys": frozenset(
            {
                "scope_video_role",
                "scope_target_video",
                "beat_id",
                "scope_event_id",
                "scope_version",
                "scope_milestone_id",
            }
        ),
    },
    "runMutation": {
        "endpoint_arg_index": 1,
        "body_arg_index": 2,
        # runMutation wraps pathappPatch and pre-injects beat_id (line 210):
        #   pathappPatch(scope, endpoint, { beat_id: beatId, ...body })
        # So the wire body includes the pathappPatch baseline + beat_id.
        "auto_keys": frozenset(
            {
                "scope_video_role",
                "scope_target_video",
                "beat_id",
                "scope_event_id",
                "scope_version",
                "scope_milestone_id",
            }
        ),
    },
}

# Infrastructure keys: auto-injected by pathappPatch (scope routing,
# generation lock, M1 snapshot context). The server reads these via the
# generic `_scope_body` helper — not via per-handler body.get() — so they
# would otherwise generate noisy CLIENT_EXTRA findings on every endpoint.
# Globally exempt them from the contract check.
INFRASTRUCTURE_KEYS: frozenset[str] = frozenset(
    {
        "scope_event_id",
        "scope_version",
        "scope_video_role",
        "scope_target_video",
        "scope_milestone_id",
        "beat_id",           # auto-injected by runMutation + pathappPatch
    }
)

# Body-key allowance comment marker — case-sensitive.
ALLOW_RE = re.compile(
    r"BODY_KEY_ALLOW:\s*([A-Za-z_][A-Za-z0-9_]*)\s+(.{4,})"
)

# Regex used to extract object-literal keys from a TSX body argument once we
# have isolated the matching brace span. Keys can be:
#   identifier:           foo:
#   single-quoted:        'foo':
#   double-quoted:        "foo":
#   shorthand identifier (foo,  -> key=foo  same as foo: foo)
# We extract via a tolerant regex on a balanced { ... } slice — not a full
# parser. Keys involving computed expressions ([expr]:) or spreads (...x) are
# flagged separately so they cannot pass silently.
KEY_RE = re.compile(
    r"""
    (?:^|[,{])                     # boundary
    \s*
    (?:
        (?P<bare>[A-Za-z_$][\w$]*)\s*[:,}]     # ident: OR shorthand ident,
        |
        '(?P<sq>[^'\\]+)'\s*:
        |
        "(?P<dq>[^"\\]+)"\s*:
    )
    """,
    re.VERBOSE | re.MULTILINE,
)

# Computed key / spread / ternary key patterns — bail on these for that body.
UNANALYZABLE_RE = re.compile(r"\[\s*[A-Za-z_$][\w$]*\s*\]\s*:|\.\.\.[A-Za-z_$]")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ServerEndpoint:
    handler_name: str           # e.g. "_handle_beat_delay"
    url_paths: List[str]        # one handler may serve multiple paths
    body_keys: Set[str] = field(default_factory=set)
    allowed_keys: Set[str] = field(default_factory=set)
    source_line: int = 0        # first line of def
    file: str = SERVER_PATH_REL


@dataclass
class ClientCall:
    file: str
    line: int
    endpoint_name: str          # e.g. "beat_delay" — keyof MUTATION_ENDPOINTS
    body_keys: Set[str] = field(default_factory=set)
    allowed_keys: Set[str] = field(default_factory=set)
    unanalyzable: bool = False


@dataclass
class Mismatch:
    kind: str                   # CLIENT_EXTRA | SERVER_EXTRA | UNANALYZABLE_CLIENT_CALL
    endpoint_name: str
    url_path: str
    key: str
    client_loc: Optional[str] = None
    server_loc: Optional[str] = None
    note: str = ""


# ---------------------------------------------------------------------------
# Endpoint-name → URL-path map (parsed from endpoints.ts)
# ---------------------------------------------------------------------------

MUT_BLOCK_RE = re.compile(
    r"export\s+const\s+MUTATION_ENDPOINTS\s*=\s*\{(.*?)\}\s*as\s+const",
    re.DOTALL,
)
MUT_ENTRY_RE = re.compile(
    r"^\s*([A-Za-z_][\w]*)\s*:\s*`\$\{SERVER_BASE\}([^`]+)`",
    re.MULTILINE,
)


class ParseError(Exception):
    """Raised when MUTATION_ENDPOINTS cannot be located/parsed — caller maps
    this to exit code 2 (Rule 19: never silently succeed on parse failure)."""


def parse_mutation_endpoints(endpoints_path: Path) -> Dict[str, str]:
    """endpoint_name -> URL path (without the SERVER_BASE prefix)."""
    src = endpoints_path.read_text(encoding="utf-8")
    m = MUT_BLOCK_RE.search(src)
    if not m:
        raise ParseError(
            f"could not find MUTATION_ENDPOINTS block in {endpoints_path}"
        )
    out: Dict[str, str] = {}
    for em in MUT_ENTRY_RE.finditer(m.group(1)):
        name, url = em.group(1), em.group(2)
        out[name] = url
    if not out:
        raise ParseError(
            f"parsed 0 entries from MUTATION_ENDPOINTS in {endpoints_path}"
        )
    return out


# ---------------------------------------------------------------------------
# Server parsing — production_server.py AST walk
# ---------------------------------------------------------------------------

PATH_ROUTE_RE_TEMPLATES = [
    # if path == "/api/foo":
    re.compile(r'^\s*if\s+path\s*==\s*"([^"]+)"\s*:', re.MULTILINE),
    re.compile(r'^\s*elif\s+path\s*==\s*"([^"]+)"\s*:', re.MULTILINE),
]
HANDLER_CALL_RE = re.compile(r"self\._handle_([A-Za-z_][\w]*)\s*\(")
# BEATGEN_SCOPE_LAYER1_V1 — router passes handler ref without call parens:
#   return self._in_beatgen_scope(self._handle_bg_update_beat, body)
BEATGEN_SCOPE_HANDLER_RE = re.compile(
    r"_in_beatgen_scope\(self\._handle_([A-Za-z_][\w]*)\s*,"
)


def parse_server_routes(server_path: Path) -> Dict[str, List[str]]:
    """url_path -> list of handler names invoked for that path.

    Walks the do_POST router by scanning for the pattern:
        if path == "/api/xxx":
            return self._handle_xxx(body)

    We pair each `if path == "..."` with the next handler reference in its
    dispatch block — either ``self._handle_xxx(body)`` or
    ``self._in_beatgen_scope(self._handle_xxx, body)`` (Layer 1 scope wrapper).
    """
    src = server_path.read_text(encoding="utf-8")
    routes: Dict[str, List[str]] = {}
    # Collect (line, path) tuples for both `if` and `elif`.
    path_matches: List[Tuple[int, str]] = []
    for pat in PATH_ROUTE_RE_TEMPLATES:
        for m in pat.finditer(src):
            line = src.count("\n", 0, m.start()) + 1
            path_matches.append((line, m.group(1)))
    path_matches.sort(key=lambda x: x[0])

    # Collect handler invocations and their line numbers.
    handler_matches: List[Tuple[int, str]] = []
    for m in HANDLER_CALL_RE.finditer(src):
        line = src.count("\n", 0, m.start()) + 1
        handler_matches.append((line, "_handle_" + m.group(1)))
    for m in BEATGEN_SCOPE_HANDLER_RE.finditer(src):
        line = src.count("\n", 0, m.start()) + 1
        handler_matches.append((line, "_handle_" + m.group(1)))

    # Pair each path with the FIRST handler call appearing in its dispatch
    # block — i.e. between this `if path == "..."` (or `elif path ==`) and
    # the next path match in source order. The previous fixed 6-line window
    # silently dropped routes whose dispatch had inline validation that
    # exceeded 6 lines (e.g. /api/beat/swap_to_a's V59 multi-line error
    # return). Block-scoped search degrades gracefully: if no handler call
    # appears before the next path branch, the route is omitted (same
    # conservative behavior as before, just with a correct block boundary).
    handler_matches.sort(key=lambda x: x[0])
    next_path_line_after: Dict[int, int] = {}
    last = None
    for plineno, _ in reversed(path_matches):
        next_path_line_after[plineno] = last if last is not None else 10**9
        last = plineno
    for plineno, ppath in path_matches:
        block_end = next_path_line_after.get(plineno, 10**9)
        for hline, hname in handler_matches:
            if hline <= plineno:
                continue
            if hline >= block_end:
                break
            routes.setdefault(ppath, []).append(hname)
            break
    return routes


class HandlerBodyKeyExtractor(ast.NodeVisitor):
    """Inside one _handle_* function, collect every literal key passed to
    body.get('KEY')/body.get('KEY', default) and body['KEY']."""

    def __init__(self) -> None:
        self.keys: Set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        # body.get("KEY") or (body or {}).get("KEY")
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and self._is_body_like(node.func.value)
        ):
            self.keys.add(node.args[0].value)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if self._is_body_like(node.value):
            sl = node.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                self.keys.add(sl.value)
        self.generic_visit(node)

    @staticmethod
    def _is_body_like(node: ast.AST) -> bool:
        # `body` or `(body or {})` or `(body or {})`
        if isinstance(node, ast.Name) and node.id == "body":
            return True
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            return any(
                isinstance(v, ast.Name) and v.id == "body" for v in node.values
            )
        return False


def parse_server_handlers(
    server_path: Path, routes: Dict[str, List[str]]
) -> Dict[str, ServerEndpoint]:
    """handler_name -> ServerEndpoint with body_keys + allowed_keys.

    V59 Phase 4 (handler split) update: handlers extracted from
    production_server.py now live in Production/tools/server_handlers/*.py
    as free functions named `handle_X` (no leading underscore), while
    production_server.py keeps a 2-line shim `def _handle_X(self, body):`
    that delegates. This function walks BOTH locations:
      1. production_server.py — picks up any handlers still defined there
         (legacy + non-extracted) AND scans shim sources for BODY_KEY_ALLOW.
      2. server_handlers/*.py — picks up extracted free functions; matches
         them to `_handle_X` route entries by name (handle_X → _handle_X).
    """
    needed_handlers: Set[str] = set()
    for handlers in routes.values():
        needed_handlers.update(handlers)

    by_handler: Dict[str, ServerEndpoint] = {}
    handler_to_paths: Dict[str, List[str]] = {}
    for url, hlist in routes.items():
        for h in hlist:
            handler_to_paths.setdefault(h, []).append(url)

    def _walk_file(path: Path, name_xform=None):
        src = path.read_text(encoding="utf-8")
        src_lines = src.splitlines()
        tree = ast.parse(src, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            display_name = node.name
            if name_xform:
                display_name = name_xform(node.name)
            if display_name not in needed_handlers:
                continue
            extractor = HandlerBodyKeyExtractor()
            extractor.visit(node)
            allowed: Set[str] = set()
            start = node.lineno - 1
            end = getattr(node, "end_lineno", start + 1)
            for raw in src_lines[start:end]:
                am = ALLOW_RE.search(raw)
                if am:
                    allowed.add(am.group(1))
            ep = by_handler.get(display_name)
            if ep is None:
                ep = ServerEndpoint(
                    handler_name=display_name,
                    url_paths=handler_to_paths.get(display_name, []),
                    body_keys=set(extractor.keys),
                    allowed_keys=set(allowed),
                    source_line=node.lineno,
                )
                by_handler[display_name] = ep
            else:
                ep.body_keys.update(extractor.keys)
                ep.allowed_keys.update(allowed)

    # Pass 1: production_server.py (catches non-extracted handlers + shim ALLOW comments)
    _walk_file(server_path)

    # Pass 2: server_handlers/*.py (catches extracted handler bodies)
    # Phase 4 free-function names are handle_X → match to route entry _handle_X
    handlers_dir = server_path.parent / "server_handlers"
    if handlers_dir.is_dir():
        for mod_path in sorted(handlers_dir.glob("*.py")):
            if mod_path.name.startswith("_"):
                continue  # skip _base.py, __init__.py
            _walk_file(mod_path, name_xform=lambda n: f"_{n}" if n.startswith("handle_") or n.startswith("serve_") else n)

    return by_handler


# ---------------------------------------------------------------------------
# Client parsing — storyboard-v2/src/**/*.tsx
# ---------------------------------------------------------------------------

def _find_call_brace_span(src: str, callee: str) -> Iterable[Tuple[int, int, int]]:
    """Yield (call_start_index, body_open_brace_idx, body_close_brace_idx) for
    each call to ``callee(...)`` where the body argument is an object literal.

    Uses brace-balancing inside the call's outer paren so embedded objects,
    strings, and templates are handled. Returns indices into ``src``.
    """
    n = len(src)
    i = 0
    needle = callee
    while True:
        idx = src.find(needle, i)
        if idx < 0:
            return
        # Token boundary check (avoid matching `mypathappPatch`).
        before_ok = idx == 0 or not (src[idx - 1].isalnum() or src[idx - 1] == "_")
        after_idx = idx + len(needle)
        if after_idx >= n or not before_ok:
            i = after_idx
            continue
        # Skip whitespace, expect '('.
        j = after_idx
        while j < n and src[j].isspace():
            j += 1
        if j >= n or src[j] != "(":
            i = after_idx
            continue
        # Walk arguments at depth 1 (relative to the call's '('), tracking
        # commas to identify arg boundaries. Skip over string literals,
        # template literals, line + block comments.
        depth = 1
        arg_idx = 0
        arg_starts = [j + 1]
        body_brace_open: Optional[int] = None
        body_brace_close: Optional[int] = None
        k = j + 1
        while k < n and depth > 0:
            c = src[k]
            if c in ('"', "'", "`"):
                quote = c
                k += 1
                while k < n and src[k] != quote:
                    if src[k] == "\\":
                        k += 2
                        continue
                    if quote == "`" and src[k] == "$" and k + 1 < n and src[k + 1] == "{":
                        # Template expression — track nested braces.
                        k += 2
                        td = 1
                        while k < n and td > 0:
                            if src[k] == "{":
                                td += 1
                            elif src[k] == "}":
                                td -= 1
                            k += 1
                        continue
                    k += 1
                k += 1
                continue
            if c == "/" and k + 1 < n and src[k + 1] == "/":
                k = src.find("\n", k)
                if k < 0:
                    k = n
                continue
            if c == "/" and k + 1 < n and src[k + 1] == "*":
                end = src.find("*/", k + 2)
                k = (end + 2) if end >= 0 else n
                continue
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            elif c == "{":
                if depth == 1 and arg_idx == 2 and body_brace_open is None:
                    body_brace_open = k
                # Walk balanced braces.
                bd = 1
                k += 1
                while k < n and bd > 0:
                    bc = src[k]
                    if bc in ('"', "'", "`"):
                        # Reuse string skip.
                        quote = bc
                        k += 1
                        while k < n and src[k] != quote:
                            if src[k] == "\\":
                                k += 2
                                continue
                            if quote == "`" and src[k] == "$" and k + 1 < n and src[k + 1] == "{":
                                k += 2
                                td = 1
                                while k < n and td > 0:
                                    if src[k] == "{":
                                        td += 1
                                    elif src[k] == "}":
                                        td -= 1
                                    k += 1
                                continue
                            k += 1
                        k += 1
                        continue
                    if bc == "/" and k + 1 < n and src[k + 1] == "/":
                        nl = src.find("\n", k)
                        k = nl if nl >= 0 else n
                        continue
                    if bc == "/" and k + 1 < n and src[k + 1] == "*":
                        end = src.find("*/", k + 2)
                        k = (end + 2) if end >= 0 else n
                        continue
                    if bc == "{":
                        bd += 1
                    elif bc == "}":
                        bd -= 1
                        if bd == 0:
                            if depth == 1 and arg_idx == 2 and body_brace_close is None:
                                body_brace_close = k
                            k += 1
                            break
                    k += 1
                continue
            elif c == "," and depth == 1:
                arg_idx += 1
                arg_starts.append(k + 1)
            k += 1
        yield (idx, body_brace_open or -1, body_brace_close or -1)
        i = k + 1


def _extract_endpoint_arg(src: str, call_start: int) -> Optional[str]:
    """Extract the 2nd argument (index 1) of the call starting at ``call_start``
    if it is a string literal; else None."""
    # Find the call's '(' .
    j = src.find("(", call_start)
    if j < 0:
        return None
    # First arg ends at top-level comma. Skip first arg.
    depth = 1
    k = j + 1
    arg_idx = 0
    arg_start = k
    n = len(src)
    while k < n and depth > 0:
        c = src[k]
        if c in ('"', "'", "`"):
            quote = c
            k += 1
            while k < n and src[k] != quote:
                if src[k] == "\\":
                    k += 2
                    continue
                k += 1
            k += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                break
        elif c == "{" or c == "[":
            opener, closer = c, "}" if c == "{" else "]"
            d = 1
            k += 1
            while k < n and d > 0:
                if src[k] == opener:
                    d += 1
                elif src[k] == closer:
                    d -= 1
                k += 1
            continue
        elif c == "," and depth == 1:
            arg_idx += 1
            if arg_idx == 1:
                # The 2nd arg starts here.
                arg_start = k + 1
            elif arg_idx == 2:
                # End of 2nd arg.
                seg = src[arg_start:k].strip()
                return _strip_string_literal(seg)
        k += 1
    return None


def _strip_string_literal(seg: str) -> Optional[str]:
    seg = seg.strip()
    if len(seg) >= 2 and seg[0] in ("'", '"', "`") and seg[-1] == seg[0]:
        # Reject template strings with interpolation.
        body = seg[1:-1]
        if "${" in body:
            return None
        return body
    return None


def _extract_keys_from_body(body_src: str) -> Tuple[Set[str], bool]:
    """Returns (keys, unanalyzable). unanalyzable=True if the body uses a
    computed key or spreads a non-literal variable."""
    if UNANALYZABLE_RE.search(body_src):
        return set(), True
    keys: Set[str] = set()
    for m in KEY_RE.finditer(body_src):
        for grp in ("bare", "sq", "dq"):
            v = m.group(grp)
            if v:
                # Skip JavaScript keywords / common false positives.
                if v in {"true", "false", "null", "undefined", "if", "for", "let", "const"}:
                    continue
                keys.add(v)
    return keys, False


def _strip_comments_preserving_offsets(src: str) -> str:
    """Replace // line and /* block */ comments with spaces of equal length,
    keeping every other byte at its original offset. Lets downstream regex/
    brace-scanners ignore comment content without shifting line numbers."""
    out = list(src)
    n = len(src)
    i = 0
    while i < n:
        c = src[i]
        if c in ('"', "'", "`"):
            # Skip string literals (including templates).
            quote = c
            i += 1
            while i < n and src[i] != quote:
                if src[i] == "\\":
                    i += 2
                    continue
                if quote == "`" and src[i] == "$" and i + 1 < n and src[i + 1] == "{":
                    i += 2
                    td = 1
                    while i < n and td > 0:
                        if src[i] == "{":
                            td += 1
                        elif src[i] == "}":
                            td -= 1
                        i += 1
                    continue
                i += 1
            i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            if j < 0:
                j = n
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            j = j + 2 if j >= 0 else n
            for k in range(i, j):
                if src[k] != "\n":
                    out[k] = " "
            i = j
            continue
        i += 1
    return "".join(out)


# Wrapper-definition site exemptions — these are the bodies of pathappPatch /
# runMutation themselves, where the endpoint argument is a parameter (dynamic
# by construction). They are not real call sites of the contract.
WRAPPER_DEFINITION_SIGNATURES = (
    "export async function pathappPatch",
    "function pathappPatch",
    "const runMutation = async",
    "const runMutation =",
)


def _is_wrapper_definition_line(src: str, call_start: int) -> bool:
    """Heuristic: scan backward up to 4 lines for a wrapper-function definition
    signature. If found, this call is the wrapper recursing/forwarding into
    itself with a dynamic endpoint param — not a real contract caller."""
    # Find the start of the line containing call_start, then back up 3 more.
    line_start = src.rfind("\n", 0, call_start) + 1
    look_start = line_start
    for _ in range(4):
        look_start = src.rfind("\n", 0, look_start - 1) + 1
        if look_start <= 0:
            look_start = 0
            break
    window = src[look_start:call_start]
    return any(sig in window for sig in WRAPPER_DEFINITION_SIGNATURES)


def parse_client_calls(client_dir: Path) -> List[ClientCall]:
    """Scan src/**/*.tsx and *.ts for pathappPatch + runMutation calls."""
    calls: List[ClientCall] = []
    for path in sorted(list(client_dir.rglob("*.tsx")) + list(client_dir.rglob("*.ts"))):
        if "/node_modules/" in str(path):
            continue
        raw_src = path.read_text(encoding="utf-8")
        # File-scoped allowances must be read from raw (pre-strip) since the
        # ALLOW marker lives inside a // line comment.
        file_allows: Set[str] = set()
        for raw in raw_src.splitlines():
            if "//" in raw:
                am = ALLOW_RE.search(raw)
                if am:
                    file_allows.add(am.group(1))
        # Strip comments for the scanner so it doesn't match
        # `// pathappPatch(...)` mentions in prose.
        src = _strip_comments_preserving_offsets(raw_src)
        for callee, cfg in CLIENT_WRAPPER_CALLEES.items():
            auto_keys = cfg["auto_keys"]  # type: ignore[assignment]
            for call_start, bo, bc in _find_call_brace_span(src, callee):
                # Skip the wrapper's own definition body.
                if _is_wrapper_definition_line(src, call_start):
                    continue
                line = src.count("\n", 0, call_start) + 1
                endpoint = _extract_endpoint_arg(src, call_start)
                if endpoint is None:
                    # Endpoint arg is dynamic (variable). We can't bind to a
                    # specific endpoint — flag as unanalyzable for clarity.
                    calls.append(
                        ClientCall(
                            file=str(path),
                            line=line,
                            endpoint_name="<dynamic>",
                            body_keys=set(),
                            allowed_keys=set(file_allows),
                            unanalyzable=True,
                        )
                    )
                    continue
                if bo < 0 or bc < 0:
                    # Body arg missing or not an object literal — treat as
                    # empty body (some callers pass {} or no body at all).
                    body_keys: Set[str] = set()
                    unanalyzable = False
                else:
                    body_inner = src[bo + 1 : bc]
                    body_keys, unanalyzable = _extract_keys_from_body(body_inner)
                # Auto-inject baseline keys that pathappPatch always sends.
                body_keys |= set(auto_keys)  # type: ignore[arg-type]
                calls.append(
                    ClientCall(
                        file=str(path),
                        line=line,
                        endpoint_name=endpoint,
                        body_keys=body_keys,
                        allowed_keys=set(file_allows),
                        unanalyzable=unanalyzable,
                    )
                )
    return calls


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

def compare(
    endpoints_map: Dict[str, str],
    server_handlers: Dict[str, ServerEndpoint],
    routes: Dict[str, List[str]],
    client_calls: List[ClientCall],
) -> List[Mismatch]:
    out: List[Mismatch] = []
    # Group client calls by endpoint_name (union of body keys).
    by_endpoint: Dict[str, Set[str]] = {}
    by_endpoint_locs: Dict[str, List[str]] = {}
    by_endpoint_allows: Dict[str, Set[str]] = {}
    for cc in client_calls:
        if cc.unanalyzable:
            out.append(
                Mismatch(
                    kind="UNANALYZABLE_CLIENT_CALL",
                    endpoint_name=cc.endpoint_name,
                    url_path="?",
                    key="",
                    client_loc=f"{cc.file}:{cc.line}",
                    note="dynamic endpoint or computed/spread body key",
                )
            )
            continue
        by_endpoint.setdefault(cc.endpoint_name, set()).update(cc.body_keys)
        by_endpoint_locs.setdefault(cc.endpoint_name, []).append(
            f"{cc.file}:{cc.line}"
        )
        by_endpoint_allows.setdefault(cc.endpoint_name, set()).update(cc.allowed_keys)

    # Walk every endpoint defined in MUTATION_ENDPOINTS.
    for endpoint_name, url_path in endpoints_map.items():
        client_keys = by_endpoint.get(endpoint_name, set())
        handlers = routes.get(url_path, [])
        # Union body_keys + allowed_keys across all handlers serving this URL.
        server_keys: Set[str] = set()
        server_allows: Set[str] = set()
        server_locs: List[str] = []
        for h in handlers:
            ep = server_handlers.get(h)
            if ep is None:
                continue
            server_keys.update(ep.body_keys)
            server_allows.update(ep.allowed_keys)
            server_locs.append(f"{ep.file}:{ep.source_line} ({h})")
        client_allows = by_endpoint_allows.get(endpoint_name, set())
        # CLIENT_EXTRA: client sends KEY, server does not read it.
        for k in sorted(client_keys - server_keys):
            if k in server_allows or k in client_allows or k in INFRASTRUCTURE_KEYS:
                continue
            out.append(
                Mismatch(
                    kind="CLIENT_EXTRA",
                    endpoint_name=endpoint_name,
                    url_path=url_path,
                    key=k,
                    client_loc="; ".join(by_endpoint_locs.get(endpoint_name, [])),
                    server_loc="; ".join(server_locs) or "(no handler bound)",
                )
            )
        # SERVER_EXTRA: server reads KEY, client never sends it.
        for k in sorted(server_keys - client_keys):
            if k in server_allows or k in client_allows or k in INFRASTRUCTURE_KEYS:
                continue
            out.append(
                Mismatch(
                    kind="SERVER_EXTRA",
                    endpoint_name=endpoint_name,
                    url_path=url_path,
                    key=k,
                    client_loc="; ".join(by_endpoint_locs.get(endpoint_name, []))
                    or "(no client caller)",
                    server_loc="; ".join(server_locs),
                )
            )
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(root: Path) -> Tuple[int, Dict[str, object]]:
    server_path = root / SERVER_PATH_REL
    endpoints_path = root / ENDPOINTS_FILE_REL
    client_dir = root / CLIENT_GLOB_REL

    if not server_path.exists():
        print(f"FATAL: server file not found: {server_path}", file=sys.stderr)
        return 2, {}
    if not endpoints_path.exists():
        print(f"FATAL: endpoints file not found: {endpoints_path}", file=sys.stderr)
        return 2, {}
    if not client_dir.exists():
        print(f"FATAL: client dir not found: {client_dir}", file=sys.stderr)
        return 2, {}

    try:
        endpoints_map = parse_mutation_endpoints(endpoints_path)
    except ParseError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2, {}
    routes = parse_server_routes(server_path)
    server_handlers = parse_server_handlers(server_path, routes)
    client_calls = parse_client_calls(client_dir)

    mismatches = compare(endpoints_map, server_handlers, routes, client_calls)

    # Skip endpoints with no client callers at all — these are legitimately
    # server-only (admin endpoints, scope_snapshot, etc.). Only flag them as
    # SERVER_EXTRA when at least one client sends a DIFFERENT key (which the
    # compare logic already does — no client keys means client_keys=empty
    # means SERVER_EXTRA fires on every server key). Suppress these here.
    callers_by_endpoint: Dict[str, int] = {}
    for cc in client_calls:
        if not cc.unanalyzable:
            callers_by_endpoint[cc.endpoint_name] = (
                callers_by_endpoint.get(cc.endpoint_name, 0) + 1
            )
    filtered = [
        m for m in mismatches
        if m.kind == "UNANALYZABLE_CLIENT_CALL"
        or callers_by_endpoint.get(m.endpoint_name, 0) > 0
    ]

    summary = {
        "total_endpoints": len(endpoints_map),
        "client_callers_observed": len(callers_by_endpoint),
        "mismatches": len(filtered),
        "items": [
            {
                "kind": m.kind,
                "endpoint": m.endpoint_name,
                "url": m.url_path,
                "key": m.key,
                "client_loc": m.client_loc,
                "server_loc": m.server_loc,
                "note": m.note,
            }
            for m in filtered
        ],
    }
    exit_code = 1 if filtered else 0
    return exit_code, summary


def _mismatch_signature(item: dict) -> str:
    """Stable signature for baseline comparison. Path-free, so a file move
    doesn't generate spurious deltas."""
    return f"{item['kind']}|{item['endpoint']}|{item['url']}|{item['key']}"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[2]),
        help="Project root (default: derived from script location)",
    )
    ap.add_argument("--json", action="store_true", help="Emit JSON report on stdout")
    ap.add_argument(
        "--baseline",
        default=None,
        help=(
            "Path to a baseline JSON of known fossil mismatches. CI passes when "
            "the current findings == the baseline (no new fossils). Fails when "
            "any NEW mismatch is detected. Use --write-baseline to refresh it."
        ),
    )
    ap.add_argument(
        "--write-baseline",
        action="store_true",
        help=(
            "Write the current findings to the path given by --baseline and "
            "exit 0. Intended for one-shot maintenance — every refresh should "
            "be reviewed in a PR with rationale per Rule 19."
        ),
    )
    args = ap.parse_args(argv)
    rc, summary = run(Path(args.root))

    # Baseline mode — compare current findings vs the recorded fossil set.
    if args.baseline:
        baseline_path = Path(args.baseline)
        current_sigs: Set[str] = {
            _mismatch_signature(i) for i in summary.get("items", [])  # type: ignore[arg-type]
        }
        if args.write_baseline:
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            baseline_path.write_text(
                json.dumps(
                    {
                        "generated_by": "Production/scripts/body_key_contract_check.py",
                        "ld": "BODY_KEY_CONTRACT_CI_GREP_GATE_V1",
                        "mismatches": sorted(current_sigs),
                        "items": summary.get("items", []),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            print(
                f"Baseline written: {len(current_sigs)} known fossil mismatches "
                f"→ {baseline_path}"
            )
            return 0
        if not baseline_path.exists():
            print(
                f"FATAL: --baseline {baseline_path} does not exist. Run with "
                "--write-baseline once to seed it.",
                file=sys.stderr,
            )
            return 2
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline_sigs: Set[str] = set(baseline.get("mismatches", []))
        new_sigs = current_sigs - baseline_sigs
        gone_sigs = baseline_sigs - current_sigs
        if args.json:
            print(
                json.dumps(
                    {
                        "baseline_path": str(baseline_path),
                        "baseline_size": len(baseline_sigs),
                        "current_size": len(current_sigs),
                        "new": sorted(new_sigs),
                        "resolved": sorted(gone_sigs),
                    },
                    indent=2,
                )
            )
        if new_sigs:
            print(
                f"FAIL — {len(new_sigs)} NEW body-key contract violation(s) "
                f"not in baseline {baseline_path}:",
                file=sys.stderr,
            )
            for sig in sorted(new_sigs):
                print(f"  {sig}", file=sys.stderr)
            print(
                "\nResolution: either fix the contract or, if intentional, "
                "refresh the baseline with --write-baseline and explain in "
                "the PR description per Rule 19.",
                file=sys.stderr,
            )
            return 1
        if gone_sigs:
            # Resolved fossils — not a failure, but worth a note. CI can grep
            # for "RESOLVED FOSSIL" to nudge a baseline refresh.
            print(
                f"INFO — {len(gone_sigs)} baseline mismatch(es) RESOLVED. "
                "Consider refreshing the baseline.",
                file=sys.stderr,
            )
            for sig in sorted(gone_sigs):
                print(f"  RESOLVED FOSSIL: {sig}", file=sys.stderr)
        print(
            f"OK — no new body-key contract violations "
            f"(baseline: {len(baseline_sigs)}, current: {len(current_sigs)})."
        )
        return 0

    # Non-baseline (full audit) mode — original behavior.
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        if rc == 0:
            print(
                f"OK — body-key contract clean across "
                f"{summary['client_callers_observed']}/{summary['total_endpoints']} "
                f"endpoints (others have no client callers)."
            )
        else:
            print(
                f"FAIL — {summary['mismatches']} body-key contract violation(s):",
                file=sys.stderr,
            )
            for item in summary["items"]:  # type: ignore[index]
                print(
                    f"  [{item['kind']}] {item['endpoint']} ({item['url']}) "
                    f"key={item['key']!r}",
                    file=sys.stderr,
                )
                if item.get("client_loc"):
                    print(f"      client: {item['client_loc']}", file=sys.stderr)
                if item.get("server_loc"):
                    print(f"      server: {item['server_loc']}", file=sys.stderr)
                if item.get("note"):
                    print(f"      note:   {item['note']}", file=sys.stderr)
            print(
                "\nResolution: either fix the contract (rename one side, OR "
                "have the server read both keys for back-compat) OR add an "
                "allowlist comment near the offending line: "
                "`# BODY_KEY_ALLOW: <key> <reason>` (server) or "
                "`// BODY_KEY_ALLOW: <key> <reason>` (client).",
                file=sys.stderr,
            )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
