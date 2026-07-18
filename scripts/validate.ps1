param(
    [ValidateSet("quick", "integration", "live", "benchmark")]
    [string]$Level = "quick",
    [switch]$RequireLockedBenchmark
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv312\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }
$PytestTemp = Join-Path $Root "temp"

function Invoke-Checked {
    param([string]$Name, [scriptblock]$Command)
    Write-Host "`n>> $Name" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
}

Invoke-Checked "Benchmark manifest" {
    $manifestArgs = @("$Root\scripts\benchmark_manifest.py")
    if ($RequireLockedBenchmark) { $manifestArgs += "--require-locked" }
    & $Python @manifestArgs
}
Invoke-Checked "Baseline report" { & $Python "$Root\scripts\baseline_report.py" }
Invoke-Checked "Backend tests" { & $Python -m pytest -q --basetemp "$PytestTemp\pytest_full" }
Invoke-Checked "Frontend build" {
    Push-Location "$Root\frontend"
    try { npm.cmd run build } finally { Pop-Location }
}

if ($Level -in @("integration", "live", "benchmark")) {
    Invoke-Checked "Deterministic media integration" {
        & $Python -m pytest -q --basetemp "$PytestTemp\pytest_integration" tests/test_voice_duration_mock_e2e.py
    }
}
if ($Level -in @("live", "benchmark")) {
    Invoke-Checked "Gemini HTTP/WebSocket smoke" { & $Python -m pytest -q --basetemp "$PytestTemp\pytest_live" tests/test_gemini_ws_http.py }
}
if ($Level -eq "benchmark") {
    $manifestData = Get-Content "$Root\benchmark\manifest.json" -Raw | ConvertFrom-Json
    $allIds = @($manifestData.sources | ForEach-Object { $_.id })
    $styleIds = @($manifestData.sources | Where-Object { $_.style_pair -eq $true } | ForEach-Object { $_.id })
    $autoOutput = "$Root\temp\benchmark\qualification_auto_latest.json"
    $promptedOutput = "$Root\temp\benchmark\qualification_prompted_latest.json"
    Invoke-Checked "Live Gemini corpus" {
        & $Python "$Root\scripts\live_benchmark.py" --ids @allIds --timeout 900 --output $autoOutput
    }
    Invoke-Checked "Prompted style pairs" {
        & $Python "$Root\scripts\live_benchmark.py" --prompted --ids @styleIds --timeout 900 --output $promptedOutput
    }
    Invoke-Checked "Benchmark qualification" {
        & $Python "$Root\scripts\benchmark_qualification.py" --auto-files $autoOutput --prompted-file $promptedOutput --output "$Root\temp\benchmark\qualification.json"
    }
    Invoke-Checked "Live two-link render queue" {
        & $Python "$Root\scripts\live_batch_e2e.py" --output "$Root\temp\benchmark\live_batch_e2e.json"
    }
}
Write-Host "`nVALIDATION PASS ($Level)" -ForegroundColor Green
