# Q1 — Part 1: Stop-Hook State-Claim Scanner — Spec v1

**Status:** Spec authored 2026-05-07. Build follows in same agent run.
**Authority:** Kim's Q1 directive (state-claim verification stack — Part 1 of 3).
**Pairs with:** `.claude/skills/mn-context/SKILL.md` Step 2.5b (DS-22 / LD 551).

---

## 1. Goal

Catch unverified state claims in assistant turns at the moment the turn ends — not minutes later at SAVE — by running the same regex scan defined in `mn-context` Step 2.5b against the most recent assistant message and surfacing a stderr warning banner inline with the claim. This shortens the discovery loop for false claims like "X is wired to Y" or "Phase 0.7 reads LD 565" from "next SAVE" to "this turn end."

## 2. Scope

**Catches:**
- State-claim verb + state-claim mechanism patterns in the most recent assistant text (per Step 2.5b regex).
- Patterns appearing without a same-turn Rule 24 confidence tag (`[CONFIRMED…]` / `[INFERRED…]` / `[GUESSED…]`).
- Patterns appearing without a same-turn verification action (grep / read / Directus query / curl probe — proxied by the presence of tool_use blocks earlier in the turn or explicit verification phrases).

**Does NOT catch:**
- False claims in user messages (out of scope — only assistant output is scanned).
- False claims in tool_result blocks (out of scope — assistant text only).
- Semantic falseness — this is a regex scan, not a fact checker. It flags *un-verified* claims (no tag, no verification call), not *false* claims per se. Part 2 (Opus reviewer) is the semantic layer.
- Claims about non-state things (e.g., "this code is elegant") — only state/wiring/mechanism patterns.

**Behavior:** warn-only, exit 0 always. Never blocks the turn. See §8 rationale.

## 3. File location

- **Hook script:** `~/.claude/hooks/stop_state_claim_scan.py` (new directory; `~/.claude/hooks/` does not currently exist on this machine — confirmed by `ls -la ~/.claude/` 2026-05-07: no `hooks/` entry. Build will create it.)
- **Settings wiring:** `~/.claude/settings.json` — append a new `Stop` array under `hooks` (no Stop hook currently exists — confirmed by reading `settings.json` 2026-05-07).
- **Backup of settings.json before edit:** `~/.claude/settings.json.backup_q1_part1_stop_hook_<ISO>` (mirrors existing backup convention).

## 4. Settings.json wiring

Existing `hooks` block (verbatim from 2026-05-07 read) contains: `PreToolUse`, `PostToolUse`, `SessionStart`, `PreCompact`. **No `Stop` array exists.**

Merge plan: add a new top-level key `Stop` inside `hooks`, alongside the existing arrays. Do NOT touch any other key.

Snippet to add (will be inserted into the `hooks` object, peer to `PreCompact`):

```json
"Stop": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "/usr/bin/python3 \"/Users/kimberlysmith/.claude/hooks/stop_state_claim_scan.py\""
      }
    ]
  }
]
```

Pattern matches `PreCompact` (no matcher key — Stop has no tool to match against). Uses absolute path to `/usr/bin/python3` and absolute path to the hook (matches the convention of every other hook in the file). One hook entry per the array's first element, mirroring `PreCompact`.

Merge procedure (executed in build phase):
1. Backup current settings.json to `settings.json.backup_q1_part1_stop_hook_<ISO>`.
2. Use `python3 -c "import json; ..."` to load, mutate, dump — never hand-edit JSON.
3. After write, re-read and `python3 -c "import json; json.load(open(...))"` to confirm valid JSON.
4. Confirm the new Stop key is present and existing keys (PreToolUse, PostToolUse, SessionStart, PreCompact) are bytewise unchanged via diff against the backup.

## 5. Hook input contract

Claude Code passes a JSON object to the hook on stdin. Based on existing MindfulNest hook scripts (`session_event_logger.py`, `precompact_save_trigger.py`, `preflight_hook.py`) and the `~/.claude/projects/<project>/<session>.jsonl` transcript format observed 2026-05-07:

**[INFERRED — Stop-hook-specific keys]** the documented stable keys for any hook are:

- `session_id` (string) — current session UUID.
- `transcript_path` (string) — absolute path to the session JSONL file under `~/.claude/projects/<project_slug>/<session_id>.jsonl`.
- `cwd` (string) — current working directory.
- `hook_event_name` (string) — for Stop, value is `"Stop"`.

For Stop specifically (vs PreToolUse/PostToolUse), there are no `tool_name` / `tool_input` / `tool_response` keys, because Stop fires on turn completion, not on a tool call. The hook can additionally receive a `stop_hook_active` boolean (true if Stop hook was triggered by a previous Stop hook continuation — defensive flag to prevent infinite loops).

**Defensive read:** the hook must `json.loads(sys.stdin.read())` inside try/except and tolerate missing keys (use `.get()` everywhere). If the input is malformed or empty, the hook exits 0 silently — never blocks.

**Validation:** in-agent testing simulates this contract. Real Stop-hook semantics will be confirmed on Kim's first real-turn smoke test post-build (documented as a follow-up).

## 6. Regex pattern set

**Source of truth:** `.claude/skills/mn-context/SKILL.md` line 296 (Step 2.5b), read 2026-05-07. Pattern reused verbatim with NO modification:

```
\b(is|are|will be|gets?|gates?|surfaces?|fires?|runs?|executes?|reads?|writes?|cross-references?|hooks? into|enforces?|prevents?|catches?)\s+(wired|fired|surfaced|read|written|enforced|mechanically|automatically|by the [a-z\s]+|on [a-z\s]+|when [a-z\s]+|via [a-z\s]+|through [a-z\s]+)
```

**Justification for verbatim reuse:** Kim's spec mandates "do not invent new patterns; reuse existing ones." DS-22 and LD 551 define the pattern set; Part 1 must match the SAVE-time gate exactly so that a claim flagged by the Stop hook at turn end is the same claim the SAVE-time gate would catch later. Divergence would create false-positive / false-negative inconsistency between the two layers.

**No new patterns added.** The Step 2.5 verbal-deferral pattern (line 255 of SKILL.md) is intentionally NOT included — that's a separate gate concerning deferrals (TODO/FIXME/follow-up), not state claims. Folding both into the Stop hook is out of scope for Part 1 and would mix concerns.

**Compiled flags:** `re.IGNORECASE` to match Kim's authoring habits. The pattern uses `\b` anchors and lowercased verb alternatives, so case-insensitive matching is a strict superset of the SAVE-time scan.

**Same-turn verification suppression** (mirrors Step 2.5b's "Rule 24 tag present in same turn → proceed silently"):
- If the same turn's text contains any of: `[CONFIRMED`, `[INFERRED`, `[GUESSED`, the regex match is suppressed (the claim is already tagged).
- If the same turn contains tool_use blocks (Read/Bash/Grep/Glob — observed earlier in the transcript turn), the match is suppressed (the claim was verified in-turn).
- If neither — emit warning.

## 7. Output format

**Channel:** stderr only. Stdout left empty so Claude Code does not interpret the output as a `systemMessage` or hook directive.

**Format:** ANSI-colored multi-line banner (yellow border, bold red header). ANSI escapes are visible in modern terminals (Kim's setup confirmed via existing `theme: dark-ansi` in settings.json). Plaintext fallback if `NO_COLOR` env is set or `not sys.stderr.isatty()`.

**Template:**

```
\033[33m======================================================================\033[0m
\033[1;31m[STATE-CLAIM SCANNER] Unverified state claim(s) in last assistant turn\033[0m
\033[33m======================================================================\033[0m
Source: stop-hook (Q1 Part 1, mirrors mn-context Step 2.5b / DS-22)
Turn:   <last assistant turn timestamp>
Matches:
  1. "<quoted phrase, max 200 chars surrounding>"
     verb: <captured group 1> | mechanism: <captured group 2>
  2. ...

Per DS-22, each must be either:
  (a) verified now (grep/read/query) and result attached, OR
  (b) tagged [CONFIRMED ...] / [INFERRED ...] / [GUESSED]

This is a WARN-ONLY scan. The turn already shipped. Re-verify in the next turn.
\033[33m======================================================================\033[0m
```

**Rationale:** stderr (not stdout) because stdout would be parsed by Claude Code as a hook directive (per the precompact pattern emitting `{systemMessage: "..."}` on stdout). Banner format mirrors the SAVE-time HALT message in SKILL.md so Kim's eye-pattern is consistent across both layers. Multi-line is acceptable for terminal output and matches the existing `Rule 19 / Phase 0 reminder` format already in settings.json.

## 8. Behavior on match

**Decision: warn-only. Always exit 0. NEVER block.**

Rationale (Kim's exact constraint, restated): "if it blocked, my message would be discarded and Kim would see nothing." Stop hook output that returns non-zero exit OR emits `{decision: "block"}` JSON to stdout causes Claude Code to either suppress the assistant message or trigger a continuation prompt. Either is worse than a stderr warning, because:
- The false claim has *already shipped* to Kim's display by the time Stop fires (turn-end means the message is rendered).
- Discarding the message would lose all the *correct* content alongside the unverified claim.
- A continuation loop could fire a second Opus generation just to "fix" the warning, which is expensive and may not actually verify anything.

So: Stop hook prints a banner to stderr, exits 0, and lets the turn complete. Kim sees the banner inline with her terminal, can decide whether to act, and the message remains intact.

## 9. Edge cases

| Case | Expected behavior |
|---|---|
| stdin empty / unreadable | exit 0, no stderr output. |
| stdin not valid JSON | exit 0, no stderr output. |
| `transcript_path` missing | exit 0, no stderr output. |
| `transcript_path` does not exist | exit 0, no stderr output. |
| transcript file empty | exit 0, no stderr output. |
| transcript has zero assistant messages | exit 0, no stderr output. |
| last assistant message has no text blocks (only tool_use / thinking) | exit 0, no stderr output. |
| last assistant text > 1 MB | read but cap regex scan to first 500 KB to bound CPU; warn at top of stderr if truncated. |
| Unicode / emoji in assistant text | use `re.UNICODE` (default in py3) and `\b` works on word chars; no special handling. |
| same-turn Rule 24 tag present | suppress emit (per §6 spec). |
| same-turn tool_use blocks (Read/Bash/Grep/Glob) | suppress emit (per §6). |
| transcript JSONL has malformed lines | skip malformed lines, continue scan. |
| `NO_COLOR` env set or stderr not a TTY | emit plaintext (no ANSI escapes). |
| hook script raises uncaught exception | wrap entire `main()` in try/except → exit 0, never propagate failure. |
| `stop_hook_active=true` (re-entrant Stop) | exit 0 immediately to avoid infinite scan loops. |

## 10. Test plan

Three planted-fixture subcases run in build phase, each piping a synthetic stdin payload to the hook:

**Subcase A — "claim" (positive):**
- Plant a transcript JSONL with one assistant text block containing "Phase 0.7 is wired by the Directus check" — matches verb=`is` mechanism=`by the directus check`.
- Pipe `{"transcript_path": "<fixture>", "session_id": "test", "hook_event_name": "Stop"}` to hook.
- Assert: exit 0, stderr contains the warning banner header `[STATE-CLAIM SCANNER]`, stderr quotes the matched phrase.

**Subcase B — "clean" (negative):**
- Plant a transcript with one assistant text block containing benign prose: "I read the file and the count was 47 lines."
- Pipe payload to hook.
- Assert: exit 0, stderr empty (or only contains a debug header if debug mode on — default is silent).

**Subcase C — "malformed" (resilience):**
- Pipe a non-JSON string to hook.
- Assert: exit 0, stderr empty (no traceback).

Subcase D (also performed): claim text WITH a `[CONFIRMED from <source>]` tag in the same turn — assert NO warning emitted (suppression works).

All fixtures live in `/tmp/q1_stop_hook_test_*.jsonl` and are deleted after test.

## 11. Rollback procedure

If the hook misfires or causes any visible problem:

**One-line disable** (no file edit, immediate effect):
```bash
chmod -x ~/.claude/hooks/stop_state_claim_scan.py
```
The hook will fail to execute at OS level, but settings.json invokes it via `/usr/bin/python3 <path>` so this won't actually skip it — it will return a Python error. Better:

**Settings.json removal** (clean rollback):
```bash
cp ~/.claude/settings.json.backup_q1_part1_stop_hook_<ISO> ~/.claude/settings.json
```
Restores the pre-Q1 settings.json verbatim. Backup path is logged at install time.

**Surgical removal** (preserve other later edits):
```bash
python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.claude/settings.json'
d = json.loads(p.read_text())
d['hooks'].pop('Stop', None)
p.write_text(json.dumps(d, indent=2))
"
```
Removes only the Stop key; leaves other hooks intact.

## 12. Multipass verification checklist

Performed AFTER build (Phase 2):

- [ ] `cat ~/.claude/hooks/stop_state_claim_scan.py | wc -l` — confirm script exists, ≤120 lines.
- [ ] `python3 -c "import ast; ast.parse(open('~/.claude/hooks/stop_state_claim_scan.py').read())"` — script parses.
- [ ] `python3 -c "import json; json.load(open('~/.claude/settings.json'))"` — settings.json is valid JSON.
- [ ] `python3 -c "import json; d=json.load(open('~/.claude/settings.json')); print(list(d['hooks']))"` — confirm `Stop` is in the keys list.
- [ ] `diff ~/.claude/settings.json.backup_q1_part1_stop_hook_<ISO> ~/.claude/settings.json` — confirm only the `Stop` block was added; PreToolUse/PostToolUse/SessionStart/PreCompact untouched.
- [ ] Run subcase A — assert positive match.
- [ ] Run subcase B — assert no false positive.
- [ ] Run subcase C — assert no traceback on malformed input.
- [ ] Run subcase D — assert tag suppression works.
- [ ] DS-13 Layer 6 demo: simulate the exploit-before string from this spec; confirm exploit-after stderr exactly matches the §7 template.

---

**End of spec.**
