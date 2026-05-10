#!/usr/bin/env bash
# install_macos.sh — set up MindfulNest Directus MCP server on macOS.
#
# Idempotent: re-running is safe. Will not clobber existing venv or config.
#
# Prerequisites:
# - Homebrew installed (https://brew.sh)
# - pyenv installed via Homebrew (brew install pyenv)
# - Doppler CLI installed (brew install dopplerhq/cli/doppler)
# - Claude Code CLI installed
# - Doppler logged in + project configured for Directus credentials

set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
VENV_DIR="$SERVER_DIR/.venv"
PYTHON_VERSION="3.12.7"

echo "[install] MindfulNest Directus MCP server install (macOS)"
echo "[install] Server dir: $SERVER_DIR"

# Verify pyenv
if ! command -v pyenv >/dev/null 2>&1; then
    if [[ -x /opt/homebrew/bin/pyenv ]]; then
        export PATH="/opt/homebrew/bin:$PATH"
    else
        echo "[install] ERROR: pyenv not found. Run: brew install pyenv"
        exit 1
    fi
fi

eval "$(pyenv init -)"

# Verify Python version
if ! pyenv versions --bare | grep -q "^${PYTHON_VERSION}$"; then
    echo "[install] Python ${PYTHON_VERSION} not installed via pyenv. Installing..."
    pyenv install "$PYTHON_VERSION"
fi

cd "$SERVER_DIR"
pyenv local "$PYTHON_VERSION"

# Verify Doppler
if ! command -v doppler >/dev/null 2>&1; then
    echo "[install] WARNING: doppler CLI not found. Server will fall back to API_KEYS_MASTER.md"
    echo "[install]          per LD-227 (SHORTCUT_CREDSTORE_MD_FALLBACK_20260418)."
    echo "[install]          To install: brew install dopplerhq/cli/doppler"
    USE_DOPPLER=0
else
    USE_DOPPLER=1
fi

# venv + deps
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "[install] Creating venv..."
    python -m venv "$VENV_DIR"
fi
echo "[install] Installing fastmcp + pydantic..."
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install --quiet fastmcp pydantic

# Smoke import
"$VENV_DIR/bin/python" -c "import fastmcp, pydantic; print('[install] fastmcp', getattr(fastmcp,'__version__','OK'), '/ pydantic', pydantic.VERSION)"

# Claude Code MCP config
if command -v claude >/dev/null 2>&1; then
    if [[ "$USE_DOPPLER" == "1" ]]; then
        echo "[install] Adding to Claude Code at user scope (-s user) via doppler run with explicit project..."
        claude mcp remove directus -s user 2>/dev/null || true
        claude mcp remove directus 2>/dev/null || true  # also remove project scope if present
        # User scope = available in ALL Claude Code sessions on this machine (any cwd).
        # --project and --config explicit because doppler can't infer project from
        # arbitrary cwd (Claude Code may be launched from any dir for user-scope MCPs).
        claude mcp add -s user directus -- /opt/homebrew/bin/doppler run --project mindfulnest --config dev -- "$VENV_DIR/bin/python" "$SERVER_DIR/server.py"
    else
        echo "[install] Adding to Claude Code at user scope (no Doppler — relies on API_KEYS_MASTER.md fallback)..."
        claude mcp remove directus -s user 2>/dev/null || true
        claude mcp remove directus 2>/dev/null || true
        claude mcp add -s user directus -- "$VENV_DIR/bin/python" "$SERVER_DIR/server.py"
    fi
    claude mcp list | grep -E "^directus" || echo "[install] WARN: claude mcp list did not show directus"
else
    echo "[install] claude CLI not found in PATH — skipping Claude Code config."
    echo "[install] Add manually: claude mcp add directus -- doppler run -- $VENV_DIR/bin/python $SERVER_DIR/server.py"
fi

# Print Claude Desktop snippet
echo ""
echo "[install] Claude Desktop config — add to:"
echo "  ~/Library/Application Support/Claude/claude_desktop_config.json"
echo ""
echo "  \"mcpServers\": {"
echo "    \"directus\": {"
if [[ "$USE_DOPPLER" == "1" ]]; then
    echo "      \"command\": \"/opt/homebrew/bin/doppler\","
    echo "      \"args\": [\"run\", \"--project\", \"mindfulnest\", \"--config\", \"dev\", \"--\", \"$VENV_DIR/bin/python\", \"$SERVER_DIR/server.py\"]"
else
    echo "      \"command\": \"$VENV_DIR/bin/python\","
    echo "      \"args\": [\"$SERVER_DIR/server.py\"]"
fi
echo "    }"
echo "  }"
echo ""
echo "[install] Done."
