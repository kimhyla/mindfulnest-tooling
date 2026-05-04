#!/usr/bin/env python3
"""LD-474 audit: scan production_server.py for state['active_video'] reads
inside mutating handler paths.

LD-474 VIDEO_ROLE_PER_REQUEST_V1 forbids handlers from using
state['active_video'] for partition selection — only body['scope_video_role']
is allowed.

Strategy: tokenize via Python's tokenize module (skips comments + strings
automatically). Then for each match, find the enclosing function via AST walk
and check if it calls mutate_state / mutate_video_state. A read in a mutating
function = violation.

Authored in S5.5a2 closure as gate #8 of the post-migration verification.
Exit 0 = clean (CI green). Exit 1 = real violations (CI red). Exit 2 = parse
error.

Usage:
    python3 Production/scripts/ld474_audit_active_video.py
    python3 Production/scripts/ld474_audit_active_video.py --strict   # also fail on read-only refs
"""
from __future__ import annotations

import argparse
import ast
import io
import sys
import tokenize
from pathlib import Path

DEFAULT_TARGET = "Production/tools/production_server.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--target", default=DEFAULT_TARGET,
                        help="path to production_server.py (default: %(default)s)")
    parser.add_argument("--strict", action="store_true",
                        help="also fail on state['active_video'] reads in non-mutating functions")
    args = parser.parse_args(argv)

    path = Path(args.target)
    if not path.exists():
        print(f"target not found: {path}", file=sys.stderr)
        return 2

    src = path.read_text(encoding="utf-8")

    # 1) Tokenize and collect line numbers where state["active_video"] /
    #    s["active_video"] / state.get("active_video") appears OUTSIDE comments
    #    and strings.
    violations_by_line: dict[int, str] = {}
    try:
        tokens = list(tokenize.tokenize(io.BytesIO(src.encode()).readline))
    except tokenize.TokenizeError as e:
        print(f"tokenize error: {e}", file=sys.stderr)
        return 2

    for i, tok in enumerate(tokens):
        # Bracket form: NAME[ STRING ]
        if tok.type == tokenize.NAME and tok.string in ("state", "s"):
            j = i + 1
            if j < len(tokens) and tokens[j].type == tokenize.OP and tokens[j].string == "[":
                k = j + 1
                if (k < len(tokens) and tokens[k].type == tokenize.STRING
                        and tokens[k].string.strip("\"'") == "active_video"):
                    violations_by_line[tok.start[0]] = f'{tok.string}["active_video"]'
        # .get( form: NAME . get ( STRING
        if tok.type == tokenize.NAME and tok.string == "get":
            if i >= 2 and tokens[i - 1].type == tokenize.OP and tokens[i - 1].string == ".":
                if (tokens[i - 2].type == tokenize.NAME
                        and tokens[i - 2].string in ("state", "s")):
                    j = i + 1
                    if j < len(tokens) and tokens[j].type == tokenize.OP and tokens[j].string == "(":
                        k = j + 1
                        if (k < len(tokens) and tokens[k].type == tokenize.STRING
                                and tokens[k].string.strip("\"'") == "active_video"):
                            violations_by_line[tokens[i - 2].start[0]] = (
                                f'{tokens[i - 2].string}.get("active_video")'
                            )

    if not violations_by_line:
        print("LD-474 AUDIT PASS — no state['active_video'] reads in any code "
              "(zero violations).")
        return 0

    # 2) AST walk — for each function, check if its body contains
    #    mutate_state / mutate_video_state calls.
    tree = ast.parse(src, filename=str(path))
    fn_ranges: list[tuple[int, int, str, bool]] = []  # (start, end, name, has_mutate)

    def walk_fn(node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            has_mutate = False
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                    if sub.func.attr in ("mutate_state", "mutate_video_state"):
                        has_mutate = True
                        break
            # `arguments`/`keyword`/etc. AST nodes don't expose lineno reliably;
            # take only nodes that DO have it.
            line_candidates = [
                getattr(n, "end_lineno", None) or getattr(n, "lineno", None)
                for n in ast.walk(node)
            ]
            line_candidates = [ln for ln in line_candidates if ln is not None]
            end_line = max(line_candidates) if line_candidates else node.lineno
            fn_ranges.append((node.lineno, end_line, node.name, has_mutate))
        for child in ast.iter_child_nodes(node):
            walk_fn(child)

    walk_fn(tree)

    real_violations: list[tuple[int, str, str]] = []
    non_mutating: list[tuple[int, str, str]] = []
    for ln, label in sorted(violations_by_line.items()):
        enclosing = [(s, e, n, m) for s, e, n, m in fn_ranges if s <= ln <= e]
        if not enclosing:
            non_mutating.append((ln, "<module>", label))
            continue
        enclosing.sort(key=lambda x: x[1] - x[0])
        s, e, name, has_mutate = enclosing[0]
        if has_mutate:
            real_violations.append((ln, name, label))
        else:
            non_mutating.append((ln, name, label))

    if real_violations:
        print(f"LD-474 AUDIT FAILED — {len(real_violations)} violation(s):")
        for ln, fn, lbl in real_violations:
            print(f"  L{ln} in {fn}(): {lbl}")
        return 1

    if args.strict and non_mutating:
        print(f"LD-474 AUDIT FAILED (strict) — "
              f"{len(non_mutating)} read in non-mutating function(s):")
        for ln, fn, lbl in non_mutating:
            print(f"  L{ln} in {fn}(): {lbl}")
        return 1

    print(f"LD-474 AUDIT PASS — 0 violations in mutating functions.")
    if non_mutating:
        print(f"  {len(non_mutating)} read-only reference(s) (allowed by LD-474):")
        for ln, fn, lbl in non_mutating:
            print(f"    L{ln} in {fn}(): {lbl}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
