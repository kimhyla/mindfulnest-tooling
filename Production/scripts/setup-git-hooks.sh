#!/usr/bin/env bash
# setup-git-hooks.sh — one-shot installer for ALL MindfulNest tooling-repo
# git hooks. Idempotent. Cross-machine (Mac + Windows via Git-Bash).
#
# Per LD GIT_HOOK_INFRASTRUCTURE_CROSS_MACHINE_V1.
#
# Run once after a fresh clone:
#     bash Production/scripts/setup-git-hooks.sh
#
# Installs:
#   .git/hooks/pre-commit  <- Production/scripts/git_hooks/pre-commit
#   .git/hooks/pre-push    <- Production/scripts/git_hooks/pre-push
#
# Idempotent: re-running on an already-installed clone is a no-op (reports
# "already installed" and exits 0). If an existing hook differs from the
# tracked template, the existing hook is backed up before overwrite.
#
# Bypasses (emergency only, document in commit msg):
#   MN_SKIP_DROPBOX_EDIT_GATE=1 git commit ...   # bypass pre-commit
#   git push --no-verify                          # bypass pre-push
#
# Cross-platform notes:
#   - Mac / Linux: works out of the box.
#   - Windows: run inside Git-Bash (ships with Git for Windows). The hook
#     bodies use only bash + git + awk/grep/sed/cmp which are all present
#     in Git-Bash. `npx --no-install tsc -b` requires Node.js on PATH on
#     whichever machine runs `git push`; if Node is absent, the tsc check
#     is skipped (printed "SKIPPED" — does not block push).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
    echo "FATAL: not inside a git repo. cd into your mindfulnest-tooling clone first." >&2
    exit 1
fi

SOURCE_DIR="$REPO_ROOT/Production/scripts/git_hooks"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

if [[ ! -d "$SOURCE_DIR" ]]; then
    echo "FATAL: source hooks dir not found at $SOURCE_DIR" >&2
    echo "  Are you on the right branch? This installer expects tracked" >&2
    echo "  hook templates at Production/scripts/git_hooks/." >&2
    exit 1
fi

if [[ ! -d "$HOOKS_DIR" ]]; then
    echo "FATAL: .git/hooks dir not found at $HOOKS_DIR" >&2
    echo "  Is this a shallow clone or worktree without the hooks dir? Run" >&2
    echo "  mkdir -p \"$HOOKS_DIR\" and re-run this installer." >&2
    exit 1
fi

# Hooks to install. Add new hook names here and drop the template in SOURCE_DIR.
HOOKS=("pre-commit" "pre-push")

INSTALLED=0
NOOP=0
BACKED_UP=0

for HOOK in "${HOOKS[@]}"; do
    SOURCE="$SOURCE_DIR/$HOOK"
    TARGET="$HOOKS_DIR/$HOOK"

    if [[ ! -f "$SOURCE" ]]; then
        echo "[setup-git-hooks] WARN: template missing for $HOOK at $SOURCE — skipping"
        continue
    fi

    if [[ -f "$TARGET" ]]; then
        if cmp -s "$SOURCE" "$TARGET"; then
            echo "[setup-git-hooks] $HOOK: already installed at $TARGET (no-op)"
            NOOP=$((NOOP + 1))
            continue
        fi
        BACKUP="$TARGET.bak.$(date -u +%Y%m%dT%H%M%SZ)"
        cp "$TARGET" "$BACKUP"
        echo "[setup-git-hooks] $HOOK: existing hook backed up to $BACKUP"
        BACKED_UP=$((BACKED_UP + 1))
    fi

    cp "$SOURCE" "$TARGET"
    chmod +x "$TARGET"
    echo "[setup-git-hooks] $HOOK: installed at $TARGET"
    INSTALLED=$((INSTALLED + 1))
done

echo ""
echo "[setup-git-hooks] summary: installed=$INSTALLED  noop=$NOOP  backed_up=$BACKED_UP"
echo "[setup-git-hooks] bypass env vars:"
echo "    MN_SKIP_DROPBOX_EDIT_GATE=1 git commit ...   # bypass pre-commit"
echo "    git push --no-verify                          # bypass pre-push"
