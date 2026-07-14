param(
    [string]$IssFile = "E:\AUTO_REVIEW\packaging\inno\MrTris_AUTO.iss",
    [string]$OutputDir = "E:\AUTO_REVIEW\build\installer",
    [int]$MaxWaitMinutes = 60
)

$Result = @{ Phase = "build_installer"; Status = "PASS"; Errors = @(); Details = @() }
function Write-Log { param([string]$Msg) $Result.Details += $Msg; Write-Host $Msg }

# Kill any stale ISCC processes before starting
try {
    $stale = Get-Process -Name "ISCC" -ErrorAction SilentlyContinue
    if ($stale) { $stale | Stop-Process -Force; Write-Log "Killed $(($stale | Measure-Object).Count) stale ISCC process(es)"; Start-Sleep -Seconds 2 }
} catch {}

Write-Log "=== Phase 1: Build Installer ==="

if (-not (Test-Path $IssFile)) {
    $Result.Status = "FAIL"; $Result.Errors += "ISS file not found: $IssFile"; return $Result
}

$iscc = (Get-Command ISCC -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $iscc = "C:\ProgramData\chocolatey\bin\ISCC.exe"
    if (-not (Test-Path $iscc)) {
        $Result.Status = "FAIL"; $Result.Errors += "ISCC not found at $iscc"; return $Result
    }
}
Write-Log "ISCC: $iscc"

$buildStart = Get-Date

# --- Attempt 1: cmd.exe /c redirect ---
$logFile = "$env:TEMP\iscc_build_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
Write-Log "ISCC log (attempt 1): $logFile"
$cmdArgs = "/c `"$iscc`" `"$IssFile`" > `"$logFile`" 2>&1"
$proc = Start-Process -FilePath "cmd.exe" -ArgumentList $cmdArgs -PassThru -WindowStyle Hidden
Write-Log "ISCC started via cmd.exe (PID: $($proc.Id)), polling up to $MaxWaitMinutes min..."

$elapsed = 0; $sleep = 30
while ($elapsed -lt ($MaxWaitMinutes * 60)) {
    if ($proc.HasExited) {
        Write-Log "ISCC process exited."
        break
    }
    Start-Sleep -Seconds $sleep; $elapsed += $sleep
    Write-Log "Still building... ($elapsed sec elapsed)"
}

if (-not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force
    $Result.Status = "FAIL"; $Result.Errors += "ISCC timed out after $MaxWaitMinutes min"
    return $Result
}

# Check log file; if cmd.exe redirect didn't create it, fall back
$logText = $null
if (Test-Path $logFile) {
    $logText = Get-Content $logFile -Raw
} else {
    Write-Log "cmd.exe redirect: log file not found. Trying Start-Process -RedirectStandardOutput fallback..."
    $logFile = "$env:TEMP\iscc_build_fallback_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
    Write-Log "ISCC log (fallback): $logFile"
    $buildStart = Get-Date
    $proc2 = Start-Process -FilePath $iscc -ArgumentList "`"$IssFile`"" -PassThru -WindowStyle Hidden -RedirectStandardOutput $logFile
    Write-Log "ISCC fallback started (PID: $($proc2.Id)), polling up to $MaxWaitMinutes min..."
    $elapsed2 = 0; $sleep2 = 30
    while ($elapsed2 -lt ($MaxWaitMinutes * 60)) {
        if ($proc2.HasExited) { break }
        Start-Sleep -Seconds $sleep2; $elapsed2 += $sleep2
        Write-Log "Still building... ($elapsed2 sec elapsed)"
    }
    if (-not $proc2.HasExited) {
        Stop-Process -Id $proc2.Id -Force
        $Result.Status = "FAIL"; $Result.Errors += "ISCC fallback timed out after $MaxWaitMinutes min"
        return $Result
    }
    $exitCode = if ($null -ne $proc2.ExitCode) { $proc2.ExitCode } else { 0 }
    Write-Log "ISCC fallback exited with code $exitCode"
    if (Test-Path $logFile) {
        $logText = Get-Content $logFile -Raw
        if ($exitCode -ne 0) {
            $Result.Status = "FAIL"; $Result.Errors += "ISCC fallback exit code: $($proc2.ExitCode)"
        }
    } else {
        $Result.Status = "FAIL"; $Result.Errors += "ISCC fallback log file still not found"
        return $Result
    }
}

if ($logText -match "Successful compile") {
    Write-Log "ISCC compile: SUCCESS"
} else {
    $Result.Status = "FAIL"; $Result.Errors += "ISCC log does not contain 'Successful compile'"
    $logLines = $logText -split "`r`n"
    $logLines[-20..-1] | ForEach-Object { Write-Log "LOG: $_" }
    return $Result
}

$exeFiles = Get-ChildItem -Path $OutputDir -Filter "*.exe" | Sort-Object LastWriteTime -Descending
$latestExe = $exeFiles | Select-Object -First 1
if (-not $latestExe) {
    $Result.Status = "FAIL"; $Result.Errors += "No .exe found in $OutputDir"; return $Result
}

# Freshness check: installer must be newer than build start
if ($latestExe.LastWriteTime -lt $buildStart) {
    $Result.Status = "FAIL"; $Result.Errors += "Installer $($latestExe.Name) is stale (from before this build)"
    return $Result
}

$exePath = $latestExe.FullName
Write-Log "Output: $($latestExe.Name) ($([math]::Round($latestExe.Length / 1MB, 2)) MB)"

# Check MZ header (first 2 bytes)
$stream = [System.IO.File]::OpenRead($exePath); $buf = New-Object byte[] 2
$stream.Read($buf, 0, 2) | Out-Null; $stream.Close()
if ($buf[0] -ne 0x4D -or $buf[1] -ne 0x5A) {
    $Result.Status = "FAIL"; $Result.Errors += "MZ header missing"
}

# Check Inno Setup signature (search first 2MB, signer data can be far in)
$stream2 = [System.IO.File]::OpenRead($exePath); $buf2 = New-Object byte[] 2097152
$stream2.Read($buf2, 0, 2097152) | Out-Null; $stream2.Close()
$text = [System.Text.Encoding]::ASCII.GetString($buf2)
if ($text -notmatch 'Inno Setup Setup Data') {
    $Result.Status = "FAIL"; $Result.Errors += "Inno Setup signature missing in first 2MB"
}

if ($latestExe.Length -lt 700MB) {
    $Result.Status = "FAIL"; $Result.Errors += "Installer too small: $($latestExe.Length) bytes (expected > 700 MB)"
}

if ($Result.Status -eq "PASS") { Write-Log "Installer validation: ALL PASS" }
Write-Log "=== Result: $($Result.Status) ==="
return @{ Phase = "build_installer"; Status = $Result.Status; Errors = $Result.Errors; Details = $Result.Details; ExePath = $exePath }
