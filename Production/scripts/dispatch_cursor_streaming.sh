#!/usr/bin/env bash
# Dispatch cursor-agent with REAL-TIME streaming output.
#
# Problem this solves: `cursor-agent -p --output-format=text` BATCHES output
# until task completion. For long-running tasks (Phase 4 handler split,
# security sweep, large refactors) that means 5-15 minutes of zero stdout
# while the task is actively working. Looks like a "silent hang" to any
# monitoring tool — couldn't distinguish "working" from "deadlocked".
#
# Fix: `--output-format=stream-json --stream-partial-output` emits
# delta-level events as they happen:
#   - {"type":"thinking","subtype":"delta","text":"..."}
#   - {"type":"tool_call","subtype":"started","tool_call":{...}}
#   - {"type":"tool_call","subtype":"completed","tool_call":{...}}
# Each line is one JSON event. Use jq to filter for what you care about.
#
# Cross-reference: feedback_cursor_agent_shell_block_hybrid_pattern.md —
# cursor's shell commands are sandbox-blocked in headless mode. Briefs must
# explicitly say "write files only — no shell commands" or cursor will
# retry shell-execute forever (a different silent-hang class this script
# does NOT solve; the brief discipline does).
#
# Usage:
#   ./dispatch_cursor_streaming.sh < /tmp/brief.md
#   ./dispatch_cursor_streaming.sh --raw < /tmp/brief.md   # raw stream
#   ./dispatch_cursor_streaming.sh --quiet < /tmp/brief.md # only final
#
# Default: filters to tool_call + assistant + final events.

# NOTE: stdbuf not available on macOS by default; relying on cursor-agent's
# own line-buffered streaming via --stream-partial-output. Use `set -uo pipefail`
# (no -e) so jq parse glitches don't abort the whole pipeline.
set -uo pipefail

MODE="${1:-filtered}"

# Pipe input (the brief) through cursor-agent with streaming flags.
cursor-agent -p \
    --output-format=stream-json \
    --stream-partial-output \
    --model=auto \
    2>&1 | \
    if [ "$MODE" = "--raw" ]; then
        cat
    elif [ "$MODE" = "--quiet" ]; then
        # Only print the final "result" event (assistant's final answer)
        jq -r 'select(.type == "result") | .result // ""' 2>/dev/null || cat
    else
        # Default: filter to tool_call + thinking-completed + result events
        # showing meaningful progress without flooding.
        jq -r '
            select(
                (.type == "tool_call" and .subtype == "completed") or
                (.type == "thinking" and .subtype == "completed") or
                (.type == "result") or
                (.type == "user" and .subtype == null)
            ) |
            if .type == "tool_call" then
                "[" + ((.tool_call | (.shellToolCall // .editToolCall // .writeToolCall // .readToolCall // .globToolCall // .grepToolCall // {} | (.args.description // .args.command // .args.file_path // .args.path // .args.globPattern // .args.pattern // ""))) | tostring) + "]"
            elif .type == "thinking" then
                "[thinking-step]"
            elif .type == "result" then
                "RESULT: " + (.result // "ok")
            else
                ""
            end
        ' 2>/dev/null || cat
    fi
