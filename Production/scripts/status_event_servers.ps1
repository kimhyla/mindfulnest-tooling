# Status for dedicated Event_N storyboard ports on Windows.
# Companion to start_event_server.ps1 (WINDOWS_EVENT_SERVER_START_V1).

[CmdletBinding()]
param(
    [int[]]$Ports = @(5111, 5112, 5113, 5114, 5115, 5116)
)

$ErrorActionPreference = "Continue"

foreach ($port in $Ports) {
    $eventId = "Event_$($port - 5110)"
    $listen = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if (-not $listen) {
        Write-Host ("{0,-8} :{1}  DOWN" -f $eventId, $port)
        continue
    }
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/event/current" -UseBasicParsing -TimeoutSec 5
        $json = $resp.Content | ConvertFrom-Json
        $served = $json.event_id
        $ok = ($json.ok -eq $true -and $served -eq $eventId)
        $mark = if ($ok) { "OK" } else { "MISMATCH served=$served" }
        Write-Host ("{0,-8} :{1}  {2}  {3}" -f $eventId, $port, $mark, "http://localhost:$port/?event=$eventId")
    } catch {
        Write-Host ("{0,-8} :{1}  LISTEN_BUT_HTTP_FAIL" -f $eventId, $port)
    }
}
