# install_windows.ps1 — set up MindfulNest Directus MCP server on Windows.
#
# Idempotent: re-running is safe.
#
# Prerequisites:
# - Python 3.12+ installed (https://www.python.org/downloads/) and on PATH
# - Doppler CLI installed (https://docs.doppler.com/docs/install-cli)
# - Claude Code CLI installed
# - Doppler logged in + project configured for Directus credentials
#
# Windows validation status: deferred per
# `SHORTCUT_DIRECTUS_MCP_WINDOWS_VALIDATION_PENDING_V1` (LD-671) — not yet run
# on a Windows machine as of 2026-05-10. Closure protocol on first work-PC
# session is documented in the LD's notes field; the user-memory file
# `project_directus_mcp_windows_install_pending.md` fires the reminder.

$ErrorActionPreference = "Stop"

$ServerDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvDir = Join-Path $ServerDir ".venv"
$PythonMin = "3.12"

Write-Host "[install] MindfulNest Directus MCP server install (Windows)"
Write-Host "[install] Server dir: $ServerDir"

# Verify Python
$PyVer = python --version 2>&1
if ($PyVer -notmatch "Python 3\.(1[0-9]|[2-9][0-9])") {
    Write-Error "[install] Python 3.10+ required. Found: $PyVer"
    exit 1
}

# Verify Doppler
$UseDoppler = 1
try {
    doppler --version | Out-Null
} catch {
    Write-Warning "[install] doppler CLI not found. Falling back to API_KEYS_MASTER.md per LD-227."
    $UseDoppler = 0
}

# venv + deps
if (-not (Test-Path (Join-Path $VenvDir "Scripts/python.exe"))) {
    Write-Host "[install] Creating venv..."
    python -m venv $VenvDir
}
$VenvPython = Join-Path $VenvDir "Scripts/python.exe"
$VenvPip = Join-Path $VenvDir "Scripts/pip.exe"

Write-Host "[install] Installing fastmcp + pydantic..."
& $VenvPip install --upgrade pip --quiet
& $VenvPip install --quiet fastmcp pydantic

# Smoke import
& $VenvPython -c "import fastmcp, pydantic; print('[install] fastmcp', getattr(fastmcp,'__version__','OK'), '/ pydantic', pydantic.VERSION)"

# Claude Code MCP config
$ClaudeCmd = Get-Command claude -ErrorAction SilentlyContinue
if ($ClaudeCmd) {
    Write-Host "[install] Adding to Claude Code..."
    claude mcp remove directus 2>$null
    if ($UseDoppler -eq 1) {
        claude mcp add directus -- doppler run -- $VenvPython (Join-Path $ServerDir "server.py")
    } else {
        claude mcp add directus -- $VenvPython (Join-Path $ServerDir "server.py")
    }
    claude mcp list | Select-String "^directus"
} else {
    Write-Host "[install] claude CLI not found — skipping Claude Code config."
}

# Print Claude Desktop snippet (Windows path)
$DesktopConfig = "$env:APPDATA\Claude\claude_desktop_config.json"
Write-Host ""
Write-Host "[install] Claude Desktop config — add to: $DesktopConfig"
Write-Host ""
Write-Host '  "mcpServers": {'
Write-Host '    "directus": {'
if ($UseDoppler -eq 1) {
    Write-Host '      "command": "doppler",'
    Write-Host "      `"args`": [`"run`", `"--`", `"$VenvPython`", `"$(Join-Path $ServerDir 'server.py')`"]"
} else {
    Write-Host "      `"command`": `"$VenvPython`","
    Write-Host "      `"args`": [`"$(Join-Path $ServerDir 'server.py')`"]"
}
Write-Host "    }"
Write-Host "  }"
Write-Host ""
Write-Host "[install] Done."
