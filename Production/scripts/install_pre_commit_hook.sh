#!/usr/bin/env bash
# install_pre_commit_hook.sh — install the V59 gap-fix Phase G pre-commit hook
# into THIS clone of the tooling repo. Hook is local-only (lives in
# .git/hooks/pre-commit, NOT tracked in the repo) per spec §3 + LD
# PRE_COMMIT_DROPBOX_EDIT_GATE_V1 — solo-dev scope, no Husky/lefthook needed.
#
# Idempotent. Safe to run multiple times.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
    echo "FATAL: not inside a git repo. cd into your mindfulnest-tooling clone first." >&2
    exit 1
fi

HOOK_PATH="$REPO_ROOT/.git/hooks/pre-commit"
SOURCE_DIR="$REPO_ROOT/Production/scripts/git_hooks"
SOURCE_HOOK="$SOURCE_DIR/pre-commit"

if [[ ! -f "$SOURCE_HOOK" ]]; then
    echo "FATAL: source hook not found at $SOURCE_HOOK" >&2
    echo "  This installer expects the hook body to be tracked at" >&2
    echo "  Production/scripts/git_hooks/pre-commit so it can be reviewed." >&2
    exit 1
fi

if [[ -f "$HOOK_PATH" ]]; then
    if cmp -s "$SOURCE_HOOK" "$HOOK_PATH"; then
        echo "[install_pre_commit_hook] already installed at $HOOK_PATH (no-op)"
        exit 0
    fi
    BACKUP="$HOOK_PATH.bak.$(date -u +%Y%m%dT%H%M%SZ)"
    cp "$HOOK_PATH" "$BACKUP"
    echo "[install_pre_commit_hook] existing hook backed up to: $BACKUP"
fi

cp "$SOURCE_HOOK" "$HOOK_PATH"
chmod +x "$HOOK_PATH"
echo "[install_pre_commit_hook] installed: $HOOK_PATH"
echo "[install_pre_commit_hook] override env var: MN_SKIP_DROPBOX_EDIT_GATE=1"
