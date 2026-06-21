param(
  [ValidateSet("Turbo")]
  [string]$Mode = "Turbo"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VenvPython = Join-Path $Root ".venv312\Scripts\python.exe"
$Python = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { "python" }

Write-Host "Installing VieNeu TTS optional dependencies ($Mode)..."
& $Python -m pip install -r (Join-Path $Root "backend\requirements-tts.txt") --extra-index-url https://pnnbao97.github.io/llama-cpp-python-v0.3.16/cpu/

Write-Host "Testing VieNeu import..."
& $Python -c "from vieneu import Vieneu; print('VieNeu import OK')"

Write-Host "VieNeu Turbo TTS setup completed. Restart backend before using TTS."
