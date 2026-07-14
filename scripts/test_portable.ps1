param(
    [string]$PackageDir = "E:\AUTO_REVIEW\build\package\MrTris_AUTO",
    [string]$LauncherSource = "E:\AUTO_REVIEW\packaging\launcher\mrtris_auto_launcher.py",
    [int]$MaxWaitSeconds = 30
)

$AppName = "MrTris_AUTO"
$LogDir = "$env:LOCALAPPDATA\$AppName\logs"
$Result = @{ Phase = "test_portable"; Status = "PASS"; Errors = @(); Details = @() }

function Write-Log { param([string]$Msg) $Result.Details += $Msg; Write-Host $Msg }

function Kill-ByPortRange {
    param([int]$Start = 8000, [int]$End = 8004)
    for ($p = $Start; $p -le $End; $p++) {
        $match = netstat -ano | Select-String ":$p " | Select-String "LISTENING"
        if ($match) {
            $targetPid = $match.ToString() -replace '^.*\s+(\d+)\s*$', '$1'
            if ($targetPid) { try { Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue; Write-Log "Killed PID $targetPid on port $p" } catch {} }
        }
    }
}

function WaitForPort {
    param([int]$Port, [int]$Timeout)
    $elapsed = 0; $sleep = 2
    while ($elapsed -lt $Timeout) {
        $match = netstat -ano | Select-String ":$Port " | Select-String "LISTENING"
        if ($match) { return $true }
        Start-Sleep -Seconds $sleep; $elapsed += $sleep
    }
    return $false
}

Write-Log "=== Phase 0: Portable Validation ==="

Copy-Item -LiteralPath $LauncherSource -Destination "$PackageDir\mrtris_auto_launcher.py" -Force
if (-not (Test-Path "$PackageDir\mrtris_auto_launcher.py")) {
    $Result.Status = "FAIL"; $Result.Errors += "Failed to stage launcher"; return $Result
}
Write-Log "Launcher staged OK"

$hasGuard = Select-String -Path "$PackageDir\mrtris_auto_launcher.py" -Pattern 'if __name__ == "__main__":' -SimpleMatch
if (-not $hasGuard) {
    $Result.Status = "FAIL"; $Result.Errors += "if __name__ guard missing"; return $Result
}
Write-Log "if __name__ guard present"

Write-Log "Killing existing processes..."
Kill-ByPortRange; Start-Sleep -Seconds 2

if (Test-Path $LogDir) {
    Remove-Item "$LogDir\launcher.log" -Force -ErrorAction SilentlyContinue
    Remove-Item "$LogDir\crash.log" -Force -ErrorAction SilentlyContinue
    Remove-Item "$LogDir\startup_diagnostics.txt" -Force -ErrorAction SilentlyContinue
}

$pythonExe = "$PackageDir\runtime\python\python.exe"
if (-not (Test-Path $pythonExe)) {
    $Result.Status = "FAIL"; $Result.Errors += "Portable Python not found at $pythonExe"; return $Result
}
$script:LauncherProc = Start-Process -FilePath $pythonExe -ArgumentList "$PackageDir\mrtris_auto_launcher.py" -WindowStyle Hidden -WorkingDirectory $PackageDir -PassThru
$script:LauncherPid = $script:LauncherProc.Id
Write-Log "Launcher started (PID: $script:LauncherPid)"

$portFound = $false
foreach ($port in @(8000, 8001, 8002, 8003, 8004)) {
    if (WaitForPort -Port $port -Timeout $MaxWaitSeconds) {
        $portFound = $true
        Write-Log "Backend started on port $port"
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/gemini/session-status" -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -eq 200) { Write-Log "API probe: HTTP 200" } else { Write-Log "API probe: HTTP $($r.StatusCode)" }
        } catch { Write-Log "API probe error: $_" }
        break
    }
}
if (-not $portFound) {
    $Result.Status = "FAIL"; $Result.Errors += "Backend did not start in $MaxWaitSeconds seconds"
}

Start-Sleep -Seconds 2
if (Test-Path "$LogDir\launcher.log") {
    $lc = Get-Content "$LogDir\launcher.log" -Raw
    Write-Log "launcher.log: $((Get-Item "$LogDir\launcher.log").Length) bytes"
    if ($lc -match "Pre-flight import OK") { Write-Log "Pre-flight: PASS" }
    else { $Result.Status = "FAIL"; $Result.Errors += "Pre-flight check missing" }
    if ($lc -match "error|traceback|exception|fail") {
        Write-Log "WARN: potential errors in launcher.log"
    }
} else {
    $Result.Status = "FAIL"; $Result.Errors += "launcher.log not found"
}

if (Test-Path "$LogDir\crash.log") {
    $Result.Status = "FAIL"; $Result.Errors += "crash.log exists - launcher crashed"
}

# Cleanup: kill port listeners and launcher process
Kill-ByPortRange
if ($script:LauncherPid) {
    try { Stop-Process -Id $script:LauncherPid -Force -ErrorAction SilentlyContinue } catch {}
    Start-Sleep -Seconds 3
    Write-Log "Killed launcher PID $script:LauncherPid"
}
Write-Log "=== Result: $($Result.Status) ==="
return $Result
