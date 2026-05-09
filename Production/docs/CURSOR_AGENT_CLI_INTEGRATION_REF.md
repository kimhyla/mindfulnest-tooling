# Cursor Agent CLI Integration — Reference

**Authored:** 2026-05-09
**Status:** ACTIVE reference doc
**Discovered by:** Claude Opus 4.7 session (gallant-bouman-804b4f) on 2026-05-09 after Kim noticed Cursor offers Anthropic API as a model option and asked "can we cut me out of this wheelhouse?"
**Related LD:** LD-N (`CURSOR_AGENT_HEADLESS_INTEGRATION_FORMALIZED_V1`) — see Directus

---

## What this is

Cursor (the IDE) ships a headless agent CLI binary `cursor-agent` that accepts prompts and produces responses programmatically. This means **Claude (running in `claude` CLI) can drive Cursor directly via Bash, eliminating the human copy-paste relay between the two systems.**

Before this discovery: Kim had to copy prompts from Claude → paste into Cursor IDE → wait for Cursor's response → copy response → paste back into Claude. ~30-60 sec relay per round, plus cognitive overhead of tracking which session is running which workstream.

After this discovery: Claude calls `cursor-agent` via Bash, captures JSON output, processes it, sends follow-up turns as needed. Kim is out of the loop unless an action requires her judgment.

---

## Setup (one-time)

```bash
# Install cursor-agent (auto-installed by Cursor.app on first invocation, but here's the explicit path)
/Applications/Cursor.app/Contents/Resources/app/bin/cursor agent --help
# This auto-downloads cursor-agent to ~/.local/bin/cursor-agent

# One-time auth (opens browser, sign in to Cursor)
cursor-agent login

# Verify
cursor-agent status   # should show authenticated
cursor-agent models   # should list available models
```

---

## Primary pattern: ITERATIVE conversation (preferred)

Use this pattern for any non-trivial work. Claude and Cursor go back and forth until the work is done.

```bash
# 1. Create a new chat session, capture the chat ID
CHAT_ID=$(cursor-agent create-chat 2>&1 | grep -oE '[a-f0-9-]{20,}')

# 2. First turn — send the initial prompt
cursor-agent --print --output-format json --resume "$CHAT_ID" --trust \
  --workspace "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files" \
  "Implement the foo from spec X. Output Y format."

# 3. Claude reviews response, finds issues, sends follow-up via SAME chat ID
cursor-agent --print --output-format json --resume "$CHAT_ID" --trust \
  "Bug at line 47 — the regex doesn't match top-level files because **/X requires intermediate dir. Fix and re-run tests."

# 4. Continue iterating until Claude verifies the work is clean
# Then commit, file LD, move on
```

**Why iteration matters:** Cursor wrote the code, so Cursor has full context. Sending bugs back to Cursor (instead of Claude fixing them via Edit tool) keeps Cursor in the driver's seat and avoids context fragmentation.

---

## One-shot pattern (for simple, well-specified tasks)

Use only when the work is small enough that iteration is unlikely to be needed.

```bash
cursor-agent --print --output-format json --trust \
  --workspace "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files" \
  --model opus \
  "Add type hints to Production/lib/foo.py. Don't change behavior."
```

---

## Critical flags

| Flag | What it does | When to use |
|------|--------------|-------------|
| `--print` / `-p` | Headless mode — prints responses to stdout | ALWAYS for programmatic use |
| `--output-format json` | Structured JSON response | Pair with `--print`; allows reliable parsing |
| `--workspace <path>` | Sets workspace directory | ALWAYS — pin to project root |
| `--trust` | Don't prompt for workspace trust | ALWAYS for headless |
| `--model <name>` | Pin model (opus, sonnet, etc.) | When quality matters |
| `--resume <chatId>` | Continue an existing chat | For iterative pattern |
| `--continue` | Resume the latest chat | When chat ID isn't tracked |
| `--mode plan` | Read-only planning mode | When you want a plan, not edits |
| `--mode ask` | Q&A only | When you want explanation, not action |
| `-w <name>` / `--worktree` | Run in isolated git worktree | For risky/exploratory work |
| `--api-key <key>` | Auth via API key (or `CURSOR_API_KEY` env var) | If browser auth not available |

---

## When Claude SHOULD use cursor-agent

- Multi-file refactors where IDE awareness helps
- Implementation work from a spec (Cursor's strength: writing code that follows project conventions)
- Code-block bug fixes Claude flags (send back to Cursor instead of Claude doing Edit)
- Anything where Cursor's project rules / linter integration / codebase-wide search adds value

## When Claude should NOT use cursor-agent

- Operations Kim must approve directly (financial transactions, sending messages, deletions, etc.)
- Destructive ops (`rm -rf`, force push, dropping prod tables)
- Anything with real-world side effects beyond the codebase
- Trivial fixes Claude can do faster via Edit tool (rename a constant, fix a typo)
- Reading + analyzing files (Claude's Read tool is faster than spawning a Cursor agent)

## When Kim should still be in the loop

- Architectural decisions
- UX/content judgment calls
- Pricing / strategy
- Anything affecting child users (COPPA, content tone, gameplay correctness)

---

## Blast radius rules

1. **Never run `cursor-agent` against a production database without read-only mode pinned.** The CLI has access to ALL TOOLS including shell and write — same blast radius as a Claude session with full permissions.
2. **Always pin `--workspace`** to the intended project root. Do not let cursor-agent auto-detect from cwd if the cwd might be wrong.
3. **Use `-w` (worktree) for risky exploratory work** so changes can be discarded if the agent's plan is wrong.
4. **Capture every cursor-agent invocation in the activity log** if it makes Directus mutations — same Rule 35 read-back-after-write applies.
5. **Don't chain cursor-agent calls without verification between turns.** Each turn's output should be parsed + sanity-checked before the next turn fires.

---

## Discovery context (for future maintainers)

This capability was discovered 2026-05-09 by accident — Kim noticed Cursor's model picker offers Anthropic Opus 4.7 as a model option and asked if Claude and Cursor could talk directly. Claude initially answered "no public API" but then dug into actual Cursor binaries and found `cursor agent` subcommand which auto-installs `cursor-agent` CLI. The CLI supports headless `--print` mode with `--output-format json` and stateful `--resume` for iteration.

**Pre-discovery workflow** (DO NOT use anymore):
- Claude drafts prompt in chat
- Kim copies prompt to Cursor IDE chat box
- Cursor responds in IDE
- Kim copies response back to Claude chat
- ~30-60 sec relay per round + cognitive overhead

**Post-discovery workflow** (PREFERRED):
- Claude drafts prompt + invokes `cursor-agent --print --resume ...` via Bash
- Captures JSON output
- Reviews + sends follow-up via same chat ID
- Iterates until done
- Surfaces final result + LD ids to Kim
- Kim only handles: commits, PR merges, judgment calls

---

## Reference invocations

### Sanity test (after `cursor-agent login`)
```bash
cursor-agent --print --output-format json --trust \
  --workspace "$(pwd)" \
  "echo hello and list the files in the current directory"
```

### Implementation handoff (single-shot)
```bash
PROMPT_FILE=/tmp/cursor_prompt_$(date +%s).txt
cat > "$PROMPT_FILE" <<'EOF'
[full prompt text here, including spec references, file paths, conventions]
EOF
cursor-agent --print --output-format json --trust \
  --workspace "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files" \
  --model opus \
  "$(cat "$PROMPT_FILE")"
rm "$PROMPT_FILE"
```

### Iterative session
```bash
# Turn 1: dispatch
CHAT_ID=$(cursor-agent create-chat | grep -oE '[a-f0-9-]{20,}' | head -1)
echo "Chat ID: $CHAT_ID"

cursor-agent --print --output-format json --resume "$CHAT_ID" --trust \
  --workspace "$WORKSPACE" \
  "[initial prompt]" > /tmp/cursor_response_1.json

# Claude parses /tmp/cursor_response_1.json, finds issues

# Turn 2: follow-up (same chat)
cursor-agent --print --output-format json --resume "$CHAT_ID" --trust \
  "[follow-up: 'Bug at X line Y. Please fix and re-run tests.']" > /tmp/cursor_response_2.json

# Continue until clean
```

---

## Failure modes

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Not logged in` | Auth missing | `cursor-agent login` |
| `No models available` | Auth not yet propagated OR account doesn't have model access | Wait + retry; check `cursor-agent status` |
| Output truncated mid-response | Token / context limit | Use shorter prompts; break work into smaller chunks |
| Cursor sandbox can't reach Directus / external services | Cursor's background agent runs in a sandboxed environment with restricted network | File LDs from Claude session (which has full network); have Cursor focus on code-only work |
| Iteration drifts from spec | Cursor lost context across turns | Re-anchor: paste relevant spec section back into the chat as a refresher |

---

## See also

- `~/.claude/projects/.../memory/reference_cursor_agent_cli.md` — quick-recall memory entry
- LD `CURSOR_AGENT_HEADLESS_INTEGRATION_FORMALIZED_V1` — governance trail
- `cursor-agent --help` — full CLI reference
- https://cursor.com/install — official cursor-agent docs (URL surfaced during install)
