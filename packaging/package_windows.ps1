param(
  [string]$Version = "1.0.4",
  [string]$OutputRoot = "build\package",
  [string]$PythonVersion = "3.12.10",
  [string]$NodeVersion = "22.21.1",
  [switch]$SkipFrontendBuild,
  [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PackageRoot = Join-Path $RepoRoot $OutputRoot
$AppRoot = Join-Path $PackageRoot "MrTris_AUTO"

function Copy-Tree($Source, $Destination) {
  if (!(Test-Path -LiteralPath $Source)) { throw "Missing source: $Source" }
  New-Item -ItemType Directory -Force -Path $Destination | Out-Null
  Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force
  }
}

function New-PortablePython($RuntimeRoot) {
  $PythonRoot = Join-Path $RuntimeRoot "python"
  $CacheRoot = Join-Path $RepoRoot "build\cache"
  $ZipPath = Join-Path $CacheRoot "python-$PythonVersion-embed-amd64.zip"
  $DownloadUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
  New-Item -ItemType Directory -Force -Path $CacheRoot | Out-Null
  if (!(Test-Path -LiteralPath $ZipPath)) {
    Write-Host "Downloading Python embeddable runtime $PythonVersion..."
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $ZipPath
  }
  if (Test-Path -LiteralPath $PythonRoot) { Remove-Item -LiteralPath $PythonRoot -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $PythonRoot | Out-Null
  Expand-Archive -LiteralPath $ZipPath -DestinationPath $PythonRoot -Force

  $SitePackages = Join-Path $PythonRoot "Lib\site-packages"
  New-Item -ItemType Directory -Force -Path $SitePackages | Out-Null
  $PthFile = Get-ChildItem -LiteralPath $PythonRoot -Filter "python*._pth" | Select-Object -First 1
  if (!$PthFile) { throw "Python embeddable _pth file not found in $PythonRoot" }
  @(
    "python312.zip",
    ".",
    "Lib\site-packages",
    "import site"
  ) | Set-Content -LiteralPath $PthFile.FullName -Encoding ASCII

  $ReqBase = Join-Path $RepoRoot "backend\requirements.txt"
  $ReqRuntime = Join-Path $CacheRoot "requirements-runtime.txt"
  Get-Content -LiteralPath $ReqBase | Where-Object { $_.Trim() -and $_.Trim() -notmatch '^pytest==' } | Set-Content -LiteralPath $ReqRuntime -Encoding ASCII
  Write-Host "Installing backend dependencies into portable runtime..."
  $PipPython = if (Test-Path (Join-Path $RepoRoot ".venv312\Scripts\python.exe")) { Join-Path $RepoRoot ".venv312\Scripts\python.exe" } else { "python" }
  & $PipPython -m pip install --upgrade --target $SitePackages -r $ReqRuntime
  if ($LASTEXITCODE -ne 0) { throw "Failed to install backend dependencies into portable runtime." }

  # Install Playwright + Chromium in portable Python
  $PortablePython = Join-Path $PythonRoot "python.exe"
  Write-Host "Installing Playwright Chromium into portable runtime..."
  & $PortablePython -m playwright install chromium
  if ($LASTEXITCODE -ne 0) { throw "Portable playwright install chromium failed." }
  Write-Host "Playwright Chromium installed into portable runtime."

  & $PortablePython -c "import fastapi, uvicorn, sqlalchemy, pydantic, yt_dlp, webview, edge_tts; print('portable python ok; edge tts ok; pywebview ok')"
  if ($LASTEXITCODE -ne 0) { throw "Portable Python import smoke test failed." }

  # Verify Playwright + Chromium launch inside portable Python
  Write-Host "Verifying Playwright Chromium can launch headless..."
  & $PortablePython -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop(); print('playwright+chromium headless OK')"
  if ($LASTEXITCODE -ne 0) { throw "Portable Python Playwright Chromium smoke test failed." }
}

function New-PortableNode($RuntimeRoot) {
  $NodeRoot = Join-Path $RuntimeRoot "node"
  $CacheRoot = Join-Path $RepoRoot "build\cache"
  $ZipPath = Join-Path $CacheRoot "node-v$NodeVersion-win-x64.zip"
  $DownloadUrl = "https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-win-x64.zip"
  New-Item -ItemType Directory -Force -Path $CacheRoot | Out-Null
  if (!(Test-Path -LiteralPath $ZipPath)) {
    Write-Host "Downloading Node.js portable runtime $NodeVersion..."
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $ZipPath
  }
  if (Test-Path -LiteralPath $NodeRoot) { Remove-Item -LiteralPath $NodeRoot -Recurse -Force }
  $ExtractRoot = Join-Path $CacheRoot "node-v$NodeVersion-win-x64"
  if (Test-Path -LiteralPath $ExtractRoot) { Remove-Item -LiteralPath $ExtractRoot -Recurse -Force }
  Expand-Archive -LiteralPath $ZipPath -DestinationPath $CacheRoot -Force
  Copy-Tree $ExtractRoot $NodeRoot
  & (Join-Path $NodeRoot "node.exe") --version
  if ($LASTEXITCODE -ne 0) { throw "Portable Node smoke test failed." }
}

function Resolve-RealTool($CommandName, $ChocolateyRelativePath) {
  $command = Get-Command $CommandName -ErrorAction SilentlyContinue
  if (!$command) { return $null }
  $source = $command.Source
  $chocoShimRoot = Join-Path $env:ProgramData "chocolatey\bin"
  if ($source.StartsWith($chocoShimRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    $chocoReal = Join-Path $env:ProgramData $ChocolateyRelativePath
    if (Test-Path -LiteralPath $chocoReal) { return $chocoReal }
  }
  return $source
}

function Copy-PlaywrightBrowsers($RuntimeRoot) {
  $PlaywrightSrc = Join-Path $env:USERPROFILE "AppData\Local\ms-playwright"
  $PlaywrightDst = Join-Path $RuntimeRoot "playwright-browsers"
  if (!(Test-Path -LiteralPath $PlaywrightSrc)) {
    Write-Host "WARNING: No ms-playwright directory at $PlaywrightSrc. Chromium will download on first launch."
    return
  }
  Write-Host "Copying Playwright browsers from $PlaywrightSrc to $PlaywrightDst ..."
  New-Item -ItemType Directory -Force -Path $PlaywrightDst | Out-Null
  # Only copy chromium, chromium_headless_shell, ffmpeg, and winldd (skip firefox, webkit)
  Get-ChildItem -LiteralPath $PlaywrightSrc -Directory | Where-Object {
    $_.Name -match '^chromium-\d+$|^chromium_headless_shell-\d+$|^ffmpeg-\d+$|^winldd-\d+$'
  } | ForEach-Object {
    Write-Host "  -> $($_.Name)"
    Copy-Tree $_.FullName (Join-Path $PlaywrightDst $_.Name)
  }
  # Also copy .links (playwright uses it to resolve correct browser path)
  $LinksSrc = Join-Path $PlaywrightSrc ".links"
  if (Test-Path -LiteralPath $LinksSrc) {
    Copy-Tree $LinksSrc (Join-Path $PlaywrightDst ".links")
  }
  Write-Host "Playwright browsers copied."
}

if (!$SkipTests) {
  Push-Location $RepoRoot
  python -m pytest tests/ -x -v
  if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Backend tests failed." }
  Pop-Location
}

if (!$SkipFrontendBuild) {
  Push-Location (Join-Path $RepoRoot "frontend")
  npm run build
  if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Frontend build failed." }
  Pop-Location
}

if (Test-Path -LiteralPath $AppRoot) { Remove-Item -LiteralPath $AppRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $AppRoot | Out-Null

Copy-Tree (Join-Path $RepoRoot "backend") (Join-Path $AppRoot "backend")
Copy-Tree (Join-Path $RepoRoot "frontend\dist") (Join-Path $AppRoot "frontend\dist")
Copy-Tree (Join-Path $RepoRoot "packaging\launcher") (Join-Path $AppRoot "launcher_src")
Copy-Tree (Join-Path $RepoRoot "packaging\tools") (Join-Path $AppRoot "tools")

$RuntimeRoot = Join-Path $AppRoot "runtime"
New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null

New-PortablePython $RuntimeRoot
New-PortableNode $RuntimeRoot

$FfmpegDir = Join-Path $RuntimeRoot "ffmpeg"
New-Item -ItemType Directory -Force -Path $FfmpegDir | Out-Null
$ffmpeg = Resolve-RealTool "ffmpeg" "chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffmpeg.exe"
$ffprobe = Resolve-RealTool "ffprobe" "chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffprobe.exe"
if ($ffmpeg) { Copy-Item -LiteralPath $ffmpeg -Destination (Join-Path $FfmpegDir "ffmpeg.exe") -Force } else { throw "ffmpeg.exe not found on PATH. Install FFmpeg or add it to PATH before packaging." }
if ($ffprobe) { Copy-Item -LiteralPath $ffprobe -Destination (Join-Path $FfmpegDir "ffprobe.exe") -Force } else { throw "ffprobe.exe not found on PATH. Install FFmpeg or add it to PATH before packaging." }
& (Join-Path $FfmpegDir "ffmpeg.exe") -version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Packaged ffmpeg.exe smoke test failed." }
& (Join-Path $FfmpegDir "ffprobe.exe") -version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Packaged ffprobe.exe smoke test failed." }

$YtDlpDir = Join-Path $RuntimeRoot "yt-dlp"
New-Item -ItemType Directory -Force -Path $YtDlpDir | Out-Null
$ytdlp = Get-Command yt-dlp -ErrorAction SilentlyContinue
if ($ytdlp) { Copy-Item -LiteralPath $ytdlp.Source -Destination (Join-Path $YtDlpDir "yt-dlp.exe") -Force } else { throw "yt-dlp.exe not found on PATH. Install yt-dlp or add it to PATH before packaging." }
$PackagedPython = Join-Path $RuntimeRoot "python\python.exe"
& $PackagedPython -m yt_dlp --js-runtimes node --remote-components ejs:github --version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Packaged python -m yt_dlp runtime smoke test failed." }

$TtsDir = Join-Path $RuntimeRoot "tts"
New-Item -ItemType Directory -Force -Path $TtsDir | Out-Null
if (Test-Path -LiteralPath (Join-Path $RepoRoot "models")) { Copy-Tree (Join-Path $RepoRoot "models") (Join-Path $TtsDir "models") }
if (Test-Path -LiteralPath (Join-Path $RepoRoot "voices")) { Copy-Tree (Join-Path $RepoRoot "voices") (Join-Path $TtsDir "voices") }

# Copy Playwright browsers into runtime for offline use
Copy-PlaywrightBrowsers $RuntimeRoot

# Clean up stale preset files no longer in the voice list
$StalePresetsDir = Join-Path $AppRoot "backend\app\services\tts_voices\presets"
$StalePresets = @("thai_son")
foreach ($stale in $StalePresets) {
  $stalePath = Join-Path $StalePresetsDir $stale
  if (Test-Path -LiteralPath $stalePath) {
    Write-Host "Removing stale preset: $stale"
    Remove-Item -LiteralPath $stalePath -Recurse -Force
  }
}

# Set environment for portable Python smoke tests
$PortablePython = Join-Path $RuntimeRoot "python\python.exe"
$PwBrowsers = Join-Path $RuntimeRoot "playwright-browsers"
if (Test-Path -LiteralPath $PwBrowsers) {
  $env:PLAYWRIGHT_BROWSERS_PATH = $PwBrowsers
}
# Final comprehensive smoke test
Write-Host "Running final comprehensive smoke tests..."
& $PortablePython -c "import fastapi, uvicorn, sqlalchemy, pydantic, yt_dlp, webview, edge_tts; print('critical imports OK')"
if ($LASTEXITCODE -ne 0) { throw "Portable Python critical imports failed." }

& $PortablePython -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop(); print('playwright chromium headless OK')"
if ($LASTEXITCODE -ne 0) { throw "Portable Python Playwright smoke test failed." }

$LauncherTarget = Join-Path $AppRoot "MrTris_AUTO.py"
Copy-Item -LiteralPath (Join-Path $RepoRoot "packaging\launcher\mrtris_auto_launcher.py") -Destination $LauncherTarget -Force
$DiagTarget = Join-Path $AppRoot "MrTris_AUTO_Diagnostics.py"
Copy-Item -LiteralPath (Join-Path $RepoRoot "packaging\tools\diagnostics.py") -Destination $DiagTarget -Force
$RepairTarget = Join-Path $AppRoot "MrTris_AUTO_Repair.py"
Copy-Item -LiteralPath (Join-Path $RepoRoot "packaging\tools\repair.py") -Destination $RepairTarget -Force

# Package additional assets
Copy-Item -LiteralPath (Join-Path $RepoRoot "icon.ico") -Destination (Join-Path $AppRoot "icon.ico") -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "version.json") -Destination (Join-Path $AppRoot "version.json") -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "update_tool.bat") -Destination (Join-Path $AppRoot "update_tool.bat") -Force
$ScriptsDest = Join-Path $AppRoot "scripts"
New-Item -ItemType Directory -Force -Path $ScriptsDest | Out-Null
Copy-Item -LiteralPath (Join-Path $RepoRoot "scripts\update_tool.ps1") -Destination (Join-Path $ScriptsDest "update_tool.ps1") -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "scripts\update_manifest.example.json") -Destination (Join-Path $ScriptsDest "update_manifest.example.json") -Force
$DocsDest = Join-Path $AppRoot "docs"
New-Item -ItemType Directory -Force -Path $DocsDest | Out-Null
Copy-Item -LiteralPath (Join-Path $RepoRoot "docs\UPDATER.md") -Destination (Join-Path $DocsDest "UPDATER.md") -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "docs\RELEASE_SKILL.md") -Destination (Join-Path $DocsDest "RELEASE_SKILL.md") -Force

$PrivateKeyLeak = Get-ChildItem -LiteralPath $AppRoot -Recurse -Force | Where-Object { $_.Name -match 'private_key|private\.pem|private_key\.b64' }
if ($PrivateKeyLeak) { throw "Private license key leaked into customer package: $($PrivateKeyLeak[0].FullName)" }
$KeygenLeak = Get-ChildItem -LiteralPath $AppRoot -Recurse -Force | Where-Object { $_.Name -match '^keygen$|MrTris_Keygen' }
if ($KeygenLeak) { throw "Internal keygen leaked into customer package: $($KeygenLeak[0].FullName)" }

$Readme = Join-Path $AppRoot "README_USER.txt"
@"
MrTris_AUTO $Version beta

Start app: run MrTris_AUTO.py with the bundled Python runtime, or use the installed shortcut.
Default output folder: %USERPROFILE%\Videos\AutoReview
Logs: %LOCALAPPDATA%\MrTris_AUTO\logs

This beta installer is unsigned. Windows SmartScreen may show a warning.
"@ | Set-Content -LiteralPath $Readme -Encoding UTF8

Write-Host "Package staged at: $AppRoot"
Write-Host "Next: build installer with packaging\inno\MrTris_AUTO.iss"
