# Start dedicated Event_N storyboard server(s) on Windows.
#
# EVENT_DEDICATED_PORT_V1 - Event_N -> http://localhost:(5110+N)/?event=Event_N
# WINDOWS_EVENT_SERVER_START_V1 - no launchd; one python process per port
#   (same shape as the live Event_6 :5116 process on this PC).
#
# Why this exists:
#   Mac uses start_event_server.sh + launchd. On Windows, opening
#   http://localhost:5113 while Event_3 is not running -> ERR_CONNECTION_REFUSED.
#   Agents must run this (or verify the port) BEFORE telling Kim to open a URL.
#
# Usage:
#   powershell -File Production/scripts/start_event_server.ps1 Event_3
#   powershell -File Production/scripts/start_event_server.ps1 Event_2 Event_3
#
# Status:
#   powershell -File Production/scripts/status_event_servers.ps1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$EventIds
)

$ErrorActionPreference = "Stop"

function Get-ToolingRoot {
    if ($env:MN_TOOLING_ROOT) { return (Resolve-Path $env:MN_TOOLING_ROOT).Path }
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Get-DropboxRoot {
    if ($env:MN_DROPBOX_ROOT) { return (Resolve-Path $env:MN_DROPBOX_ROOT).Path }
    $candidate = Join-Path $env:USERPROFILE "Dropbox\Claude Mindfulnest Project Files"
    if (-not (Test-Path -LiteralPath $candidate)) {
        throw "Dropbox Production root missing: $candidate (set MN_DROPBOX_ROOT)"
    }
    return (Resolve-Path $candidate).Path
}

function Get-EventPort([string]$EventId) {
    if ($EventId -notmatch '^Event_(\d+)$') {
        throw "Expected Event_<number>, got $EventId"
    }
    return 5110 + [int]$Matches[1]
}

function Test-EventServerHealthy([int]$Port, [string]$EventId) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/event/current" -UseBasicParsing -TimeoutSec 5
        if ($resp.StatusCode -ne 200) { return $false }
        $json = $resp.Content | ConvertFrom-Json
        return ($json.ok -eq $true -and $json.event_id -eq $EventId)
    } catch {
        return $false
    }
}

function Stop-ListenerOnPort([int]$Port) {
    $owners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $owners) {
        if ($procId -and $procId -gt 0) {
            Write-Host "[start] freeing :$Port (pid $procId)"
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Start-OneEvent([string]$EventId) {
    $port = Get-EventPort $EventId
    $url = "http://localhost:$port/?event=$EventId"
    $eventDir = Join-Path $script:DropboxRoot "Production\$EventId"
    if (-not (Test-Path -LiteralPath $eventDir)) {
        throw "Missing event dir: $eventDir"
    }

    if (Test-EventServerHealthy $port $EventId) {
        Write-Host "[start] $EventId already healthy on :$port - $url"
        return
    }

    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        Stop-ListenerOnPort $port
        Start-Sleep -Seconds 1
    }

    $serverPy = Join-Path $script:ToolingRoot "Production\tools\production_server.py"
    if (-not (Test-Path -LiteralPath $serverPy)) {
        throw "Missing $serverPy"
    }

    $logDir = Join-Path $script:ToolingRoot "Production"
    $outLog = Join-Path $logDir ("{0}_server_{1}.log" -f $EventId, $port)
    $errLog = Join-Path $logDir ("{0}_server_{1}.err.log" -f $EventId, $port)

    $env:PRODUCTION_SERVER_SINGLE_MACHINE = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $prodRoot = Join-Path $script:ToolingRoot "Production"
    $toolsRoot = Join-Path $prodRoot "tools"
    $libRoot = Join-Path $prodRoot "lib"
    $env:PYTHONPATH = "$prodRoot;$toolsRoot;$libRoot"

    $argList = @(
        "`"$serverPy`"",
        "--event-dir",
        "`"$eventDir`"",
        "--storyboard",
        "storyboard_v59_prod.html",
        "--event-id",
        $EventId,
        "--port",
        "$port"
    )

    Write-Host "[start] launching $EventId on :$port"
    $proc = Start-Process -FilePath "python" -ArgumentList $argList `
        -WorkingDirectory $toolsRoot `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru

    $deadline = (Get-Date).AddMinutes(6)
    while ((Get-Date) -lt $deadline) {
        if (Test-EventServerHealthy $port $EventId) {
            Write-Host "  OK  $EventId -> $url  (pid $($proc.Id))"
            return
        }
        if ($proc.HasExited) {
            throw "Server exited early for $EventId. See $errLog"
        }
        Start-Sleep -Seconds 2
    }
    throw "Timed out waiting for $EventId on :$port. See $outLog / $errLog"
}

$script:ToolingRoot = Get-ToolingRoot
$script:DropboxRoot = Get-DropboxRoot

Write-Host "=== Windows dedicated event servers (5110+N) ==="
Write-Host "tooling=$script:ToolingRoot"
Write-Host "dropbox=$script:DropboxRoot"
foreach ($eid in $EventIds) {
    Start-OneEvent $eid
}
Write-Host ""
Write-Host "Bookmark each tab to its URL. Do not flip events via the dropdown on dedicated ports."
