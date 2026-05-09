# Stop-hook CD-prefix Variant — Install Proof Report

- **Date:** 2026-05-08
- **LD:** LD-589 STOP_HOOK_CD_PREFIX_VARIANT_V1
- **Activity log row:** prod_activity_log id=1786
- **Spec anchor:** STOP_HOOK_CD_PREFIX_VARIANT_V1
- **Companion hook:** `~/.claude/hooks/stop_state_claim_scan.py` (state-claim variant)
- **Self-classification:** STANDARD (mirrors existing Stop-hook pattern; no novel infra)
- **Branch / worktree:** `claude/gallant-bouman-804b4f`

---

## 1. Mission

Author a new Stop-hook variant that scans Claude's last assistant turn for `bash` code blocks and warns if the first non-comment line of any block isn't `cd "<canonical project root>"`. Reinforces Kim's 2026-05-08 rule (`feedback_terminal_prompts_cd_first.md`) mechanically when working in CLI.

Pattern mirrored from existing `stop_state_claim_scan.py` (DS-22, LD-551).

---

## 2. Verbatim hook script

Path: `/Users/kimberlysmith/.claude/hooks/stop_cd_prefix_scan.py`
Mode: `0755`
Size: 7269 bytes
`py_compile`: **OK**

```python
#!/usr/bin/env python3
"""
Stop-hook bash-block CD-prefix scanner.

Mirrors feedback_terminal_prompts_cd_first.md (Kim 2026-05-08) at turn-end.
Reads the session transcript, finds the last assistant text message, extracts
all bash code fences, and warns if the first non-comment / non-blank line of
any block is NOT a `cd "<path>"` command.

This reinforces the CD-first paste-block rule mechanically when working in
the CLI. Always exits 0 - never blocks.

Companion to: stop_state_claim_scan.py (state-claim variant).
Spec: STOP_HOOK_CD_PREFIX_VARIANT_V1 (2026-05-08).
"""
from __future__ import annotations
import json
import os
import re
import sys

# Canonical Mindfulnest project root - Dropbox path (DS-27 root #1).
PROJECT_ROOT_DROPBOX = "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"

# Bash code fence pattern. Captures the body between ```bash ... ```.
# Tolerates ```bash, ```sh, ```shell - all shell-like fences. Non-greedy.
BASH_FENCE_RE = re.compile(
    r"```(?:bash|sh|shell)\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)

# A line that starts with `cd ` followed by a quoted or unquoted path.
# Accepts: cd "...", cd '...', cd /abs/path, cd ~/..., cd $VAR
CD_LINE_RE = re.compile(r"""^\s*cd\s+(?:"[^"]+"|'[^']+'|\S+)""")

# "Example only" / documentation marker - suppresses warning for that block.
DOC_MARKER_RE = re.compile(
    r"#\s*(?:example only|docs?[:\s]|illustrative|reference only)",
    re.IGNORECASE,
)

# Same-turn suppression markers (Rule 24 tags).
TAG_MARKERS = ("[CONFIRMED", "[INFERRED", "[GUESSED")

# Per-message text cap to bound CPU on huge messages.
MAX_SCAN_BYTES = 500_000

UNKNOWN_TS = "(unknown)"


def _color(s: str, code: str) -> str:
    if os.environ.get("NO_COLOR") or not sys.stderr.isatty():
        return s
    return f"\033[{code}m{s}\033[0m"


def _read_last_turn(transcript_path: str):
    """Return (assistant_text, turn_ts).

    Walks the JSONL bottom-up. For the most recent turn (delimited by the
    user message before the final assistant block), collects assistant
    text content blocks.
    """
    if not transcript_path or not os.path.exists(transcript_path):
        return "", ""
    try:
        with open(transcript_path, "rb") as f:
            data = f.read()
    except OSError:
        return "", ""
    lines = data.splitlines()

    assistant_texts = []
    turn_ts = ""
    for raw in reversed(lines):
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            continue
        et = entry.get("type")
        if et == "user":
            break
        if et != "assistant":
            continue
        turn_ts = turn_ts or entry.get("timestamp", "")
        msg = entry.get("message", {}) or {}
        content = msg.get("content", []) or []
        if not isinstance(content, list):
            continue
        for blk in content:
            if not isinstance(blk, dict):
                continue
            if blk.get("type") == "text":
                txt = blk.get("text", "") or ""
                if txt:
                    assistant_texts.append(txt)
    full = "\n".join(reversed(assistant_texts))
    if len(full.encode("utf-8", errors="ignore")) > MAX_SCAN_BYTES:
        full = full.encode("utf-8", errors="ignore")[:MAX_SCAN_BYTES].decode("utf-8", errors="ignore")
    return full, turn_ts


def _is_single_absolute_oneliner(body: str) -> bool:
    """Suppress: block is a single command using only absolute paths."""
    real_lines = [l for l in body.splitlines() if l.strip() and not l.strip().startswith("#")]
    if len(real_lines) != 1:
        return False
    line = real_lines[0]
    if re.search(r"(?:^|\s)(?:\./|\.\./)", line):
        return False
    if re.search(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_-]*)/", line):
        return False
    return True


def _first_real_line(body: str) -> str:
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        return s
    return ""


def _block_has_doc_marker(body: str) -> bool:
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("#") and DOC_MARKER_RE.search(s):
            return True
    return False


def _emit_warning(offenders, turn_ts: str) -> None:
    border = _color("=" * 70, "33")
    header = _color(
        "[CD-PREFIX SCANNER] bash block(s) missing leading cd in last turn",
        "1;31",
    )
    print(border, file=sys.stderr)
    print(header, file=sys.stderr)
    print(border, file=sys.stderr)
    print(
        "Source: stop-hook (mirrors feedback_terminal_prompts_cd_first.md, Kim 2026-05-08)",
        file=sys.stderr,
    )
    ts_display = turn_ts if turn_ts else UNKNOWN_TS
    print(f"Turn:   {ts_display}", file=sys.stderr)
    print(f"Offenders: {len(offenders)} bash block(s)", file=sys.stderr)
    for i, (idx, first_line, preview) in enumerate(offenders[:10], 1):
        print(f"  {i}. block #{idx}: first real line = {first_line!r}", file=sys.stderr)
        plines = preview.splitlines()[:2]
        for pl in plines:
            print(f"     | {pl}", file=sys.stderr)
    if len(offenders) > 10:
        print(f"  ... and {len(offenders) - 10} more.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Per the CD-first rule, every paste-block should start with:", file=sys.stderr)
    expected = '  cd "' + PROJECT_ROOT_DROPBOX + '" && \\'
    print(expected, file=sys.stderr)
    print(
        "(or an explicit cd to a different canonical root, e.g. ~/Projects/mindfulnest-tooling/).",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    print(
        "This is a WARN-ONLY scan. The turn already shipped. Re-emit with cd in next turn.",
        file=sys.stderr,
    )
    print(border, file=sys.stderr)


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        try:
            payload = json.loads(raw)
        except ValueError:
            return 0
        if not isinstance(payload, dict):
            return 0
        if payload.get("stop_hook_active"):
            return 0
        transcript_path = payload.get("transcript_path", "")
        text, turn_ts = _read_last_turn(transcript_path)
        if not text:
            return 0

        suppress_all = any(marker in text for marker in TAG_MARKERS)

        offenders = []
        for idx, m in enumerate(BASH_FENCE_RE.finditer(text), 1):
            body = m.group(1)
            if not body.strip():
                continue
            if _block_has_doc_marker(body):
                continue
            if _is_single_absolute_oneliner(body):
                continue
            first = _first_real_line(body)
            if not first:
                continue
            if CD_LINE_RE.match(first):
                continue
            preview = body.strip()
            offenders.append((idx, first, preview))

        if not offenders:
            return 0
        if suppress_all:
            return 0
        _emit_warning(offenders, turn_ts)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

---

## 3. Verbatim settings.json diff

Backup: `/Users/kimberlysmith/.claude/settings.json.bak.20260508_cd_hook` (4846 bytes pre-edit)

```diff
     "Stop": [
       {
         "hooks": [
           {
             "type": "command",
             "command": "/usr/bin/python3 \"/Users/kimberlysmith/.claude/hooks/stop_state_claim_scan.py\""
+          },
+          {
+            "type": "command",
+            "command": "/usr/bin/python3 \"/Users/kimberlysmith/.claude/hooks/stop_cd_prefix_scan.py\""
           }
         ]
       }
     ]
```

Post-edit live (lines 82-95 of `/Users/kimberlysmith/.claude/settings.json`):

```json
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/usr/bin/python3 \"/Users/kimberlysmith/.claude/hooks/stop_state_claim_scan.py\""
          },
          {
            "type": "command",
            "command": "/usr/bin/python3 \"/Users/kimberlysmith/.claude/hooks/stop_cd_prefix_scan.py\""
          }
        ]
      }
    ]
```

JSON validation: **PASS** (re-parsed via `json.loads` immediately after write).
Multipass re-Read: **PASS** (line-numbered confirmation).

---

## 4. Subcase test outputs (5 required + 2 bonus)

All cases run by piping a synthesized JSON Stop payload to the hook with a planted minimal `transcript.jsonl` containing one user message + one assistant message. `NO_COLOR=1` set to make stderr greppable.

### Subcase A — bash block missing cd → expect banner

Input assistant text:
````
Here's the command:

```bash
ls Production/
echo done
```
````

Result: **PASS** — exit 0, banner emitted on stderr.
Banner (verbatim):
```
======================================================================
[CD-PREFIX SCANNER] bash block(s) missing leading cd in last turn
======================================================================
Source: stop-hook (mirrors feedback_terminal_prompts_cd_first.md, Kim 2026-05-08)
Turn:   2026-05-08T12:00:01Z
Offenders: 1 bash block(s)
  1. block #1: first real line = 'ls Production/'
     | ls Production/
     | echo done

Per the CD-first rule, every paste-block should start with:
  cd "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files" && \
(or an explicit cd to a different canonical root, e.g. ~/Projects/mindfulnest-tooling/).

This is a WARN-ONLY scan. The turn already shipped. Re-emit with cd in next turn.
======================================================================
```

### Subcase B — bash block with cd → expect silence

Input contains a `cd "<root>" && \` prefix.
Result: **PASS** — exit 0, stderr empty.

### Subcase C — bash block all comments + cd → expect silence

Input bash body starts with two `#` comment lines, then `cd "<root>" && \`.
Result: **PASS** — exit 0, stderr empty. (Comment-stripping logic in `_first_real_line` works.)

### Subcase D — no bash block at all → expect silence

Input assistant text contains no fenced code blocks.
Result: **PASS** — exit 0, stderr empty.

### Subcase E — malformed transcript → expect silence (graceful)

Input transcript contains a `{not valid json` line and a `\x00\x01garbage` line interleaved with a well-formed assistant entry whose bash block is compliant. Hook gracefully skips malformed lines.
Result: **PASS** — exit 0, stderr empty.

### Subcase F (bonus) — `# Example only` doc marker → expect silence

Input bash body has `# Example only - illustrative` header followed by `ls Production/`.
Result: **PASS** — exit 0, stderr empty. Doc-marker suppression works.

### Subcase G (bonus) — single absolute one-liner → expect silence

Input bash body is `ls /Users/kimberlysmith/Documents` (one line, no relative paths).
Result: **PASS** — exit 0, stderr empty. Single-absolute-oneliner suppression works.

**Summary: 7/7 PASS.**

---

## 5. Activity log row

- **Collection:** `prod_activity_log`
- **id:** `1786`
- **action:** `stop_hook_cd_prefix_scanner_installed`
- **performed_by:** `claude_autonomous_hook_install`
- **details:** JSON dict containing hook_path, settings_path, settings_backup, hook count before/after, companion hook reference, rule_source, spec_anchor, behavior, scan_target, fence_languages, suppression_rules, all 7 subcase test results, DS-27 third-canonical-anchor note, py_compile/json_validate flags, ts.
- **Read-back:** verified (Rule 35) — fields match what was written; details parses as JSON; subcase_tests dict has 7 entries.

---

## 6. Locked decision

- **decision_key:** `STOP_HOOK_CD_PREFIX_VARIANT_V1`
- **id:** LD-589
- **severity:** SOFT
- **task_category:** ci_cd
- **enforcement_type:** linter
- **scope_domain:** infra
- **enforcement_artifact_ref:** `/Users/kimberlysmith/.claude/hooks/stop_cd_prefix_scan.py`
- **related_files:** the hook script, settings.json, this report
- **Cache rebuilt:** 550 active LDs → `~/.claude/mindfulnest-cache/locked_decisions.cache.json`

---

## 7. DS-27 third-canonical-anchor note

DS-27 dual-canonical-paths previously named two anchors:

1. Dropbox project root: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`
2. Projects-rooted tooling repo: `/Users/kimberlysmith/Projects/mindfulnest-tooling/`

This install introduces a **third anchor**:

3. `~/.claude/` — user-level Claude harness configuration (settings.json, hooks/, mindfulnest-cache/, mindfulnest-context/, projects/)

This anchor is governed by the harness, not the project repo. Both Stop hooks (`stop_state_claim_scan.py` and `stop_cd_prefix_scan.py`) live here. Hooks reference back to the Dropbox project root via absolute paths (no `cd` needed because hook-side commands are themselves absolute).

Operational implication: changes to `~/.claude/` files cannot use `Write`/`Edit` tools (sandbox-restricted per `feedback_skill_edits_via_python.md`). Use `Bash` + Python (`Path.write_text` / `shutil.copy`) instead. This was hit and routed correctly during this install.

LD-589 records this expansion of the canonical-anchor set.

---

## 8. Confidence tags (Rule 24)

- **[CONFIRMED 2026-05-08]** Hook compiles cleanly (`/usr/bin/python3 -m py_compile` → OK).
- **[CONFIRMED 2026-05-08]** All 7 subcase tests PASS (A banner emitted; B/C/D/E/F/G silent + exit 0).
- **[CONFIRMED 2026-05-08]** `settings.json` re-parses as valid JSON post-edit; Stop array now contains 2 hook entries; multipass re-Read confirms exact text.
- **[CONFIRMED 2026-05-08]** `prod_activity_log` id=1786 created and read back successfully (Rule 35 satisfied).
- **[CONFIRMED 2026-05-08]** LD-589 created via `lock_decision.py lock`; cache rebuilt to 550 active LDs.
- **[CONFIRMED 2026-05-08]** Hook is mode `0755` and owned by user.
- **[INFERRED 2026-05-08]** When the hook runs in production against real transcripts, the scan boundary (last assistant turn, walked bottom-up until a `user` entry) will match what `stop_state_claim_scan.py` already does in production — the `_read_last_turn` helper is structurally identical except for the dropped `had_tool_use` flag (not needed for cd-prefix logic). Production behavior parity not yet observed in a live session.
- **[INFERRED 2026-05-08]** Settings.json edits via `Bash`+Python are picked up by Claude Code on the next session start (consistent with the existing state-claim hook entry, which was added the same way per LD-551).
- **[GUESSED]** Banner display in Kim's terminal will use ANSI color when stderr is a tty; this depends on terminal emulator. Hook auto-disables color when `NO_COLOR` env var is set or when stderr is non-tty (matches existing hook behavior).

---

## 9. Self-classification

**STANDARD.** Mirrors the established `stop_state_claim_scan.py` pattern: same Stop-hook contract (stdin JSON payload → exit 0 always → optional stderr banner), same transcript-walk approach, same warn-only doctrine, same settings.json wiring slot. No new infrastructure, no new dependencies, no schema changes. The only novel artifact is the third-canonical-anchor note (DS-27 amendment), which is documentation, not infra.

---

## 10. Files touched

| Path | Action | Note |
|------|--------|------|
| `/Users/kimberlysmith/.claude/hooks/stop_cd_prefix_scan.py` | CREATED | new Stop-hook variant, 7269 bytes, mode 0755 |
| `/Users/kimberlysmith/.claude/settings.json` | EDITED | added second Stop hook entry; backup at `.bak.20260508_cd_hook` |
| `/Users/kimberlysmith/.claude/settings.json.bak.20260508_cd_hook` | CREATED | pre-edit snapshot |
| `~/.claude/mindfulnest-cache/locked_decisions.cache.json` | UPDATED | rebuilt by `lock_decision.py` (550 LDs) |
| Directus `prod_activity_log` row 1786 | CREATED | install record + 7-subcase test results |
| Directus `prod_locked_decisions` LD-589 | CREATED | STOP_HOOK_CD_PREFIX_VARIANT_V1 |
| `Production/docs/STOP_HOOK_CD_PREFIX_VARIANT_REPORT_20260508.md` | CREATED | this report |

---

## 11. Observations / minor follow-ups (not blocking)

- The existing `stop_state_claim_scan.py` references `Production/docs/Q1_PART1_STOP_HOOK_SPEC_v1.md`. There is no analogous standalone spec doc for the cd-prefix variant — this report serves as the de-facto spec, with LD-589 as the canonical anchor.
- `feedback_terminal_prompts_cd_first.md` was not amended in-place (per the original mission's "either…or" language). The hook itself + LD-589 + this report constitute the mechanical reinforcement; the memory note retains its narrative form.
- Hook does not currently track per-block byte offsets in the transcript, so the offender preview is the bash body itself rather than a transcript-position pointer. Consistent with how `stop_state_claim_scan.py` reports matches (snippet around regex match).
