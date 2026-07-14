param(
    [string]$ExePath = "",
    [string]$ExpectedInstallDir = "$env:ProgramFiles\MrTris_AUTO",
    [int]$MaxWaitSeconds = 300
)

$Result = @{ Phase = "test_install"; Status = "PASS"; Errors = @(); Details = @() }
function Write-Log { param([string]$Msg) $Result.Details += $Msg; Write-Host $Msg }

Write-Log "=== Phase 2: Silent Install ==="

if (-not $ExePath -or -not (Test-Path $ExePath)) {
    $Result.Status = "FAIL"; $Result.Errors += "Installer not found: $ExePath"; return $Result
}

$installLog = "$env:TEMP\mrtris_install_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
Write-Log "Installing: $ExePath"
Write-Log "Install log: $installLog"

$installArgs = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=`"$installLog`""
try {
    $proc = Start-Process -FilePath $ExePath -ArgumentList $installArgs -PassThru -Wait -NoNewWindow -ErrorAction Stop
    Write-Log "Installer exited with code $($proc.ExitCode)"
    if ($proc.ExitCode -ne 0) {
        $Result.Status = "FAIL"; $Result.Errors += "Installer exit code: $($proc.ExitCode)"
    }
} catch {
    Write-Log "Normal install failed, trying with RunAs admin..."
    try {
        $proc = Start-Process -FilePath $ExePath -ArgumentList $installArgs -Verb RunAs -PassThru -Wait -ErrorAction Stop
        Write-Log "Installer (RunAs) exited with code $($proc.ExitCode)"
        if ($proc.ExitCode -ne 0) {
            $Result.Status = "FAIL"; $Result.Errors += "Installer exit code: $($proc.ExitCode)"
        }
    } catch {
        $Result.Status = "FAIL"; $Result.Errors += "Install launch failed: $_"
    }
}

if (-not (Test-Path $installLog)) {
    $Result.Status = "FAIL"; $Result.Errors += "Install log not created at $installLog"
} else {
    $logContent = Get-Content $installLog -Raw
    if ($logContent -match "Installation process succeeded") {
        Write-Log "Install log: SUCCESS"
    } elseif ($logContent -match "Error|Failed|Aborted") {
        $Result.Status = "FAIL"; $Result.Errors += "Install log contains errors"
    } else {
        $Result.Status = "FAIL"; $Result.Errors += "Install log missing success/failure markers"
    }
    $copyDir = "E:\AUTO_REVIEW\temp\pipeline_logs"
    New-Item -ItemType Directory -Path $copyDir -Force -ErrorAction SilentlyContinue | Out-Null
    Copy-Item $installLog -Destination "$copyDir\install_$(Get-Date -Format 'yyyyMMdd_HHmmss').log" -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 3
$checkFiles = @(
    "$ExpectedInstallDir\mrtris_auto_launcher.py",
    "$ExpectedInstallDir\runtime\python\python.exe",
    "$ExpectedInstallDir\runtime\python\pythonw.exe",
    "$ExpectedInstallDir\backend\app\main.py",
    "$ExpectedInstallDir\frontend\dist\index.html",
    "$ExpectedInstallDir\runtime\node\node.exe",
    "$ExpectedInstallDir\runtime\ffmpeg\ffmpeg.exe",
    "$ExpectedInstallDir\runtime\yt-dlp\yt-dlp.exe"
)

$allFound = $true
foreach ($f in $checkFiles) {
    if (Test-Path $f) { Write-Log "  EXISTS: $f" }
    else { $Result.Status = "FAIL"; $Result.Errors += "Missing: $f"; $allFound = $false }
}

if ($allFound) { Write-Log "All required files: PRESENT" }
Write-Log "=== Result: $($Result.Status) ==="
return $Result
