$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VenvPython = Join-Path $Root ".venv312\Scripts\python.exe"
$Python = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { "python" }
$SystemPython = "C:\Users\huynh\AppData\Local\Programs\Python\Python312\python.exe"

Write-Host "Installing Edge TTS dependencies..."
& $Python -m pip install -r (Join-Path $Root "backend\requirements.txt")
if ((Test-Path -LiteralPath $SystemPython) -and ($SystemPython -ne $Python)) {
  & $SystemPython -m pip install edge-tts>=6.1.12
}

Write-Host "Testing Edge TTS import..."
& $Python -c "import edge_tts; print('Edge TTS import OK')"
if ((Test-Path -LiteralPath $SystemPython) -and ($SystemPython -ne $Python)) {
  & $SystemPython -c "import edge_tts; print('Edge TTS import OK (system python)')"
}

Write-Host "Edge TTS setup completed. Restart backend before using TTS."
