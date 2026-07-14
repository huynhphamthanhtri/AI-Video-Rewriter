param(
    [int]$MaxIterations = 10
)

$PipelineRoot = "E:\AUTO_REVIEW"
$ScriptsDir = "$PipelineRoot\scripts"
$LogBase = "$PipelineRoot\temp\pipeline_logs"

function Write-Step { param([string]$Msg) Write-Host "`n>> $Msg" -ForegroundColor Cyan }

function Invoke-Phase {
    param([string]$ScriptName, [hashtable]$Args = @{})
    $attemptDir = "$LogBase\attempt_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    New-Item -ItemType Directory -Path $attemptDir -Force -ErrorAction SilentlyContinue | Out-Null

    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "Running: $ScriptName" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    $scriptPath = "$ScriptsDir\$ScriptName.ps1"
    if (-not (Test-Path $scriptPath)) {
        $err = @{ Phase = $ScriptName; Status = "FAIL"; Errors = @("Script not found: $scriptPath"); Details = @() }
        return $err
    }

    try {
        $result = & $scriptPath @Args
        $result | ConvertTo-Json -Depth 3 | Out-File "$attemptDir\$ScriptName.json" -Encoding utf8
        if ($result.Status -eq "PASS") {
            Write-Host "RESULT: PASS" -ForegroundColor Green
        } else {
            Write-Host "RESULT: FAIL" -ForegroundColor Red
            foreach ($err in $result.Errors) { Write-Host "  ERROR: $err" -ForegroundColor Red }
        }
        return $result
    } catch {
        $err = @{ Phase = $ScriptName; Status = "FAIL"; Errors = @("Script error: $_"); Details = @() }
        $err | ConvertTo-Json -Depth 3 | Out-File "$attemptDir\$ScriptName.json" -Encoding utf8
        Write-Host "RESULT: FAIL (exception: $_)" -ForegroundColor Red
        return $err
    }
}

function Kill-ByPortRange {
    $ports = @(8000, 8001, 8002, 8003, 8004, 8007, 5173)
    foreach ($p in $ports) {
        $match = netstat -ano | Select-String ":$p" | Select-String "LISTENING"
        if ($match) {
            $targetPid = $match.ToString() -replace '^.*\s+(\d+)\s*$', '$1'
            if ($targetPid) { try { Stop-Process -Id $targetPid -Force -ErrorAction Stop; Write-Host "Killed PID $targetPid on port $p" } catch {} }
        }
    }
}

Write-Host "########################################" -ForegroundColor Yellow
Write-Host "  MrTris_AUTO Test Pipeline" -ForegroundColor Yellow
Write-Host "  Max iterations: $MaxIterations" -ForegroundColor Yellow
Write-Host "  Log base: $LogBase" -ForegroundColor Yellow
Write-Host "########################################" -ForegroundColor Yellow

New-Item -ItemType Directory -Path $LogBase -Force -ErrorAction SilentlyContinue | Out-Null

for ($attempt = 1; $attempt -le $MaxIterations; $attempt++) {
    Write-Host "`n########################################" -ForegroundColor Yellow
    Write-Host "  ATTEMPT $attempt of $MaxIterations" -ForegroundColor Yellow
    Write-Host "########################################" -ForegroundColor Yellow

    $rPackage = Invoke-Phase -ScriptName "package_windows"
    if ($rPackage.Status -ne "PASS") { Kill-ByPortRange; Write-Step "Package step FAILED. Logs at $LogBase"; continue }

    $r0 = Invoke-Phase -ScriptName "test_portable"
    if ($r0.Status -ne "PASS") { Kill-ByPortRange; Write-Step "Portable validation FAILED. Logs at $LogBase"; continue }

    $r1 = Invoke-Phase -ScriptName "build_installer"
    if ($r1.Status -ne "PASS") { Kill-ByPortRange; Write-Step "Build installer FAILED"; continue }
    $exePath = $r1.ExePath

    $r2 = Invoke-Phase -ScriptName "test_install" -Args @{ ExePath = $exePath }
    if ($r2.Status -ne "PASS") { Kill-ByPortRange; Write-Step "Install test FAILED"; continue }

    $r3 = Invoke-Phase -ScriptName "test_installed"
    if ($r3.Status -ne "PASS") { Kill-ByPortRange; Write-Step "Installed app test FAILED"; continue }

    Write-Host "`n########################################" -ForegroundColor Green
    Write-Host "  ALL PHASES PASSED on attempt $attempt" -ForegroundColor Green
    Write-Host "  Installer: $exePath" -ForegroundColor Green
    Write-Host "########################################" -ForegroundColor Green
    return
}

Kill-ByPortRange
Write-Host "`nFAILED after $MaxIterations attempts" -ForegroundColor Red
exit 1
