param(
    [string]$InstallDir = "$env:ProgramFiles\MrTris_AUTO",
    [int]$MaxWaitSeconds = 30
)

$AppName = "MrTris_AUTO"
$LogDir = "$env:LOCALAPPDATA\$AppName\logs"
$Result = @{ Phase = "test_installed"; Status = "PASS"; Errors = @(); Details = @() }

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

Write-Log "=== Phase 3: Test Installed App ==="

if (-not (Test-Path $InstallDir)) {
    $Result.Status = "FAIL"; $Result.Errors += "Install dir not found: $InstallDir"; return $Result
}

Kill-ByPortRange; Start-Sleep -Seconds 2
if (Test-Path $LogDir) {
    Remove-Item "$LogDir\launcher.log" -Force -ErrorAction SilentlyContinue
    Remove-Item "$LogDir\crash.log" -Force -ErrorAction SilentlyContinue
    Remove-Item "$LogDir\startup_diagnostics.txt" -Force -ErrorAction SilentlyContinue
}

$launcherCandidates = @("$InstallDir\mrtris_auto_launcher.py", "$InstallDir\MrTris_AUTO.py")
$launcherPath = $null
foreach ($c in $launcherCandidates) { if (Test-Path $c) { $launcherPath = $c; break } }
if (-not $launcherPath) {
    $Result.Status = "FAIL"; $Result.Errors += "Launcher script not found"; return $Result
}

$pythonwExe = "$InstallDir\runtime\python\pythonw.exe"
if (-not (Test-Path $pythonwExe)) {
    $Result.Status = "FAIL"; $Result.Errors += "pythonw.exe not found at $pythonwExe"; return $Result
}

$LauncherProc = Start-Process -FilePath $pythonwExe -ArgumentList "`"$launcherPath`"" -WindowStyle Hidden -WorkingDirectory $InstallDir -PassThru
$LauncherPid = $LauncherProc.Id
Write-Log "Installed launcher started (PID: $LauncherPid)"

$portFound = $false
foreach ($port in @(8000, 8001, 8002, 8003, 8004)) {
    if (WaitForPort -Port $port -Timeout $MaxWaitSeconds) {
        $portFound = $true
        Write-Log "Backend started on port $port"
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/gemini/session-status" -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -eq 200) { Write-Log "API probe: HTTP 200" } else { Write-Log "API probe: HTTP $($r.StatusCode)" }
        } catch { Write-Log "API probe error: $_" }
        # TTS status probe
        try {
            $tts = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/tts/status" -UseBasicParsing -TimeoutSec 5
            $ttsJson = $tts.Content | ConvertFrom-Json
            Write-Log "TTS status: $($ttsJson.status)"
        } catch { Write-Log "TTS status probe error: $_" }
        break
    }
}
if (-not $portFound) {
    $Result.Status = "FAIL"; $Result.Errors += "Backend did not start from installed location"
}

Start-Sleep -Seconds 2
if (Test-Path "$LogDir\launcher.log") {
    $lc = Get-Content "$LogDir\launcher.log" -Raw
    Write-Log "launcher.log: $((Get-Item "$LogDir\launcher.log").Length) bytes"
    if ($lc -match "Pre-flight import OK") { Write-Log "Pre-flight: PASS" }
    else { $Result.Status = "FAIL"; $Result.Errors += "Pre-flight check missing" }
} else {
    $Result.Status = "FAIL"; $Result.Errors += "launcher.log not found"
}

if (Test-Path "$LogDir\crash.log") {
    $Result.Status = "FAIL"; $Result.Errors += "crash.log exists - launcher crashed"
}

# Validate HF_HOME is NOT in Program Files
if (Test-Path "$LogDir\startup_diagnostics.txt") {
    $diag = Get-Content "$LogDir\startup_diagnostics.txt" -Raw
    if ($diag -match "env\.HF_HOME=.*AppData\\Local\\MrTris_AUTO\\huggingface") {
        Write-Log "HF_HOME validation: PASS (appdata path)"
    } elseif ($diag -match "HF_HOME=.*Program Files.*") {
        $Result.Status = "FAIL"; $Result.Errors += "HF_HOME points to Program Files: $diag"
    } else {
        Write-Log "HF_HOME validation: unexpected path"
    }
    if ($diag -match "TTS model cache ready at") {
        Write-Log "TTS cache check: PASS (pre-copied)"
    } elseif ($diag -match "will copy on first use") {
        Write-Log "TTS cache check: should have copied at first run"
    }
} else {
    Write-Log "startup_diagnostics.txt not found, skipping HF_HOME validation"
}

# Cleanup
Kill-ByPortRange
if ($LauncherPid) {
    try { Stop-Process -Id $LauncherPid -Force -ErrorAction SilentlyContinue } catch {}
    Start-Sleep -Seconds 3
    Write-Log "Killed launcher PID $LauncherPid"
}
Write-Log "=== Result: $($Result.Status) ==="
return $Result
