<#
.SYNOPSIS
    MrTris_AUTO Updater — checks for updates via GitHub Releases manifest,
    downloads, verifies, backs up, and applies updates safely.

.DESCRIPTION
    -DryRun : Print update plan without executing.
    -Force  : Skip process check and update even if app processes are running.
    -FromUI : Called from the app UI. Detects and shuts down only ProjectRoot-related
              processes before updating. Does not kill unrelated global processes.
    -RestartAfterUpdate : After successful update, restart the app via the detected
                          launcher (packaged: runtime\python\python.exe + MrTris_AUTO.py;
                          dev: python + packaging\launcher\mrtris_auto_launcher.py).

    Exit codes:
        0 = already up to date or successful update
        1 = error
#>

param(
    [switch]$DryRun,
    [switch]$Force,
    [switch]$FromUI,
    [switch]$RestartAfterUpdate
)

# -------------------- CONFIGURATION --------------------
$ManifestUrl = "https://raw.githubusercontent.com/huynhphamthanhtri/MrTris_AUTO_UPDATES/main/manifest.json"
$ProjectRoot = $null
$BackupRoot = $null

# Update target paths (relative to project root)
$UpdateTargets = @(
    "backend",
    "frontend\dist",
    "scripts",
    "docs",
    "README.md",
    "SYSTEM_DESIGN.md",
    "ARCHITECTURE_DIAGRAM.md",
    "AGENTS.md",
    "review_preset.md"
)

# Preserved paths (never backed up, never restored, never overwritten)
# Wildcards (*.db, *.sqlite, *.sqlite3) match files inside any target directory.
$PreservedPaths = @(
    "data\creator_dna.md",
    "data\cookies",
    "outputs",
    "temp",
    ".env",
    "logs",
    "backend\app.db",
    "*.db",
    "*.sqlite",
    "*.sqlite3"
)

# Processes that indicate the app is running
$AppProcesses = @("python", "uvicorn", "node", "MrTris_AUTO")

# -------------------- HELPER FUNCTIONS --------------------
function Is-Preserved($ItemPath) {
    $rel = $ItemPath -replace [regex]::Escape($ProjectRoot + "\"), ""
    foreach ($pattern in $PreservedPaths) {
        if ($rel -like $pattern) { return $true }
        if ($rel -eq $pattern -or $rel.StartsWith($pattern + "\")) { return $true }
    }
    return $false
}
function Write-Step($Message) {
    Write-Host ">>> $Message" -ForegroundColor Cyan
}

function Write-Info($Message) {
    Write-Host "    $Message" -ForegroundColor Gray
}

function Write-Success($Message) {
    Write-Host "    $Message" -ForegroundColor Green
}

function Write-Warn($Message) {
    Write-Host "    WARNING: $Message" -ForegroundColor Yellow
}

function Write-ErrorExit($Message) {
    Write-Host "    ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Get-ProjectRoot {
    $dir = $PSScriptRoot
    if (-not $dir) {
        $dir = (Get-Location).Path
    }
    return (Get-Item -LiteralPath $dir).Parent.FullName
}

function Read-LocalVersion($Root) {
    $verFile = Join-Path $Root "version.json"
    if (-not (Test-Path -LiteralPath $verFile -PathType Leaf)) {
        Write-ErrorExit "version.json not found at $verFile"
    }
    try {
        $content = Get-Content -LiteralPath $verFile -Encoding UTF8 -Raw | ConvertFrom-Json
        return @{
            version = $content.version
            channel = $content.channel
        }
    } catch {
        Write-ErrorExit "Failed to parse version.json: $_"
    }
}

function Compare-Versions($Left, $Right) {
    try {
        $lv = [System.Version]::new($Left)
        $rv = [System.Version]::new($Right)
        return $lv.CompareTo($rv)
    } catch {
        Write-ErrorExit "Cannot compare versions: $Left vs $Right ($_)"
    }
}

function Get-MrTrisRelatedProcesses {
    param([string]$ProjectRoot)
    try {
        $norm = $ProjectRoot.Replace('/', '\').TrimEnd('\')
        $procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'node.exe' OR Name = 'MrTris_AUTO.exe'" -ErrorAction Stop
        $matched = @($procs | Where-Object {
            $_.ProcessId -ne $pid -and (
                ($_.ExecutablePath -and $_.ExecutablePath -like "$norm*") -or
                ($_.CommandLine -and $_.CommandLine -like "*$norm*")
            )
        })
        if ($matched.Count -gt 0) {
            Write-Info "MrTris_AUTO-related processes found:"
            foreach ($p in $matched) {
                $snippet = if ($p.CommandLine) { $p.CommandLine.Substring(0, [Math]::Min(120, $p.CommandLine.Length)) } else { $p.ExecutablePath }
                Write-Info "  [PID $($p.ProcessId)] $($p.Name) — $snippet"
            }
        }
        return $matched
    } catch {
        Write-Warn "Cannot inspect running processes via WMI: $_"
        return $null
    }
}

function Stop-MrTrisProcesses {
    param($Processes)
    Write-Host "  Waiting 5 seconds before shutdown to let the app finish..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
    Write-Step "Stopping MrTris_AUTO processes gracefully..."
    foreach ($p in $Processes) {
        Write-Info "  Stopping PID $($p.ProcessId) ($($p.Name))..."
        Stop-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 3
    $stillRunning = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'node.exe' OR Name = 'MrTris_AUTO.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessId -in $Processes.ProcessId }
    if ($stillRunning) {
        Write-Step "Force stopping remaining processes..."
        foreach ($p in $stillRunning) {
            Write-Info "  Force killing PID $($p.ProcessId) ($($p.Name))..."
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
    }
    Write-Success "All MrTris_AUTO processes stopped."
}

function Restart-App {
    param([string]$ProjectRoot)
    Write-Step "Detecting app launcher..."
    # 1. Packaged install: runtime\python\python.exe MrTris_AUTO.py
    $pythonExe = Join-Path $ProjectRoot "runtime\python\python.exe"
    $launcherPy = Join-Path $ProjectRoot "MrTris_AUTO.py"
    if ((Test-Path -LiteralPath $pythonExe -PathType Leaf) -and (Test-Path -LiteralPath $launcherPy -PathType Leaf)) {
        Write-Info "Detected launcher: packaged install"
        Write-Info "  $pythonExe"
        Write-Info "  $launcherPy"
        Write-Step "Restarting MrTris_AUTO..."
        Start-Process -FilePath $pythonExe -ArgumentList "`"$launcherPy`"" -WorkingDirectory $ProjectRoot
        Write-Success "Restart initiated."
        return
    }
    # 2. Dev fallback: python packaging\launcher\mrtris_auto_launcher.py
    $devLauncher = Join-Path $ProjectRoot "packaging\launcher\mrtris_auto_launcher.py"
    if (Test-Path -LiteralPath $devLauncher -PathType Leaf) {
        Write-Info "Detected launcher: dev launcher script"
        Write-Info "  python $devLauncher"
        Write-Step "Restarting MrTris_AUTO..."
        Start-Process -FilePath "python" -ArgumentList "`"$devLauncher`"" -WorkingDirectory $ProjectRoot
        Write-Success "Restart initiated."
        return
    }
    Write-Warn "Could not detect app launcher. Please restart MrTris_AUTO manually."
}

function Show-UpdatePlan($LocalVer, $Manifest, $Root) {
    Write-Host ""
    Write-Host "  MrTris_AUTO Update Plan start" -ForegroundColor Yellow
    Write-Host "  ============================================" -ForegroundColor Yellow
    Write-Host "  Project root:    $Root" -ForegroundColor White
    Write-Host "  Local version:   $($LocalVer.version) ($($LocalVer.channel))" -ForegroundColor White
    Write-Host "  Remote version:  $($Manifest.version) ($($Manifest.channel))" -ForegroundColor White
    Write-Host "  Download URL:    $($Manifest.download_url)" -ForegroundColor White
    Write-Host "  Min supported:   $($Manifest.min_supported_version)" -ForegroundColor White
    Write-Host "  Published:       $($Manifest.published_at)" -ForegroundColor White
    Write-Host "  ============================================" -ForegroundColor Yellow
    Write-Host "  Update targets:" -ForegroundColor White
    foreach ($t in $UpdateTargets) {
        Write-Host "    - $t"
    }
    Write-Host "  Preserved (never touched):" -ForegroundColor White
    foreach ($p in $PreservedPaths) {
        Write-Host "    - $p"
    }
    Write-Host ""
}

function Backup-UpdateTargets {
    $timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
    $backupDir = Join-Path $BackupRoot $timestamp
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    Write-Info "Backing up current files to $backupDir"
    foreach ($target in $UpdateTargets) {
        $source = Join-Path $ProjectRoot $target
        if (-not (Test-Path -LiteralPath $source)) { continue }
        if (Is-Preserved $source) {
            Write-Info "  Skipping preserved: $target"
            continue
        }
        $dest = Join-Path $backupDir $target
        $parent = Split-Path -Parent $dest
        if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        if (Test-Path -LiteralPath $source -PathType Container) {
            # Copy directory contents, skipping preserved files
            New-Item -ItemType Directory -Path $dest -Force | Out-Null
            $files = Get-ChildItem -LiteralPath $source -Recurse -File
            foreach ($f in $files) {
                $relPath = $f.FullName.Substring($source.Length + 1)
                if (Is-Preserved (Join-Path $dest $relPath)) {
                    Write-Info "    Skipping preserved: $relPath"
                    continue
                }
                $targetFile = Join-Path $dest $relPath
                $targetDir = Split-Path -Parent $targetFile
                if (-not (Test-Path -LiteralPath $targetDir -PathType Container)) {
                    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
                }
                Copy-Item -LiteralPath $f.FullName -Destination $targetFile -Force
            }
        } else {
            Copy-Item -LiteralPath $source -Destination $dest -Force
        }
    }
    Write-Success "Backup created at $backupDir"
    return $backupDir
}

function Restore-UpdateTargets($BackupPath) {
    Write-Warn "Rolling back update from $BackupPath"
    foreach ($target in $UpdateTargets) {
        $backupItem = Join-Path $BackupPath $target
        if (-not (Test-Path -LiteralPath $backupItem)) { continue }
        $dest = Join-Path $ProjectRoot $target
        if (Is-Preserved $dest) {
            Write-Info "  Skipping preserved: $target"
            continue
        }
        if (Test-Path -LiteralPath $dest -PathType Container) {
            # Remove non-preserved files only, then restore from backup
            $existingFiles = Get-ChildItem -LiteralPath $dest -Recurse -File
            foreach ($f in $existingFiles) {
                $relPath = $f.FullName.Substring($dest.Length + 1)
                if (-not (Is-Preserved (Join-Path $dest $relPath))) {
                    Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue
                }
            }
            # Restore files from backup (skipping preserved)
            if (Test-Path -LiteralPath $backupItem -PathType Container) {
                $backupFiles = Get-ChildItem -LiteralPath $backupItem -Recurse -File
                foreach ($f in $backupFiles) {
                    $relPath = $f.FullName.Substring($backupItem.Length + 1)
                    if (Is-Preserved (Join-Path $dest $relPath)) {
                        Write-Info "    Skipping preserved: $relPath"
                        continue
                    }
                    $targetFile = Join-Path $dest $relPath
                    $targetDir = Split-Path -Parent $targetFile
                    if (-not (Test-Path -LiteralPath $targetDir -PathType Container)) {
                        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
                    }
                    Copy-Item -LiteralPath $f.FullName -Destination $targetFile -Force
                }
            }
        } else {
            # Single file target
            if (Test-Path -LiteralPath $dest -PathType Container) {
                Remove-Item -LiteralPath $dest -Recurse -Force -ErrorAction SilentlyContinue
            }
            $parent = Split-Path -Parent $dest
            if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
                New-Item -ItemType Directory -Path $parent -Force | Out-Null
            }
            Copy-Item -LiteralPath $backupItem -Destination $dest -Force
        }
    }
    Write-Success "Rollback complete"
}

# -------------------- MAIN --------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  MrTris_AUTO Updater" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 1. Locate project root
$ProjectRoot = Get-ProjectRoot
Write-Info "Project root: $ProjectRoot"

# 2. Set backup root
$BackupRoot = Join-Path (Join-Path $env:LOCALAPPDATA "MrTris_AUTO") "backups"

# 3. Read local version
$LocalVer = Read-LocalVersion $ProjectRoot
Write-Info "Local version: $($LocalVer.version) ($($LocalVer.channel))"

# 4. Download remote manifest
Write-Step "Downloading manifest from $ManifestUrl"
$Manifest = $null
try {
    $response = Invoke-WebRequest -Uri $ManifestUrl -UseBasicParsing -TimeoutSec 30
    $Manifest = $response.Content | ConvertFrom-Json
    Write-Success "Remote version: $($Manifest.version) (channel: $($Manifest.channel))"
} catch {
    Write-ErrorExit "Failed to download manifest: $_"
}

# 5. Compare versions
$cmp = Compare-Versions $LocalVer.version $Manifest.version

if ($cmp -ge 0) {
    Write-Host ""
    Write-Success "Already up to date. (local: $($LocalVer.version), remote: $($Manifest.version))"
    exit 0
}

# 6. Show update plan (always)
Show-UpdatePlan $LocalVer $Manifest $ProjectRoot

# 7. DryRun check
if ($DryRun) {
    Write-Success "DryRun mode - no changes were made."
    Write-Host ""
    Write-Host "  MrTris_AUTO Update Plan end" -ForegroundColor Yellow
    exit 0
}

# 8. Check running processes
if ($FromUI) {
    Write-Step "FromUI mode: detecting MrTris_AUTO processes..."
    $mrTrisProcs = Get-MrTrisRelatedProcesses -ProjectRoot $ProjectRoot
    if ($mrTrisProcs -eq $null) {
        Write-Warn "Process inspection unavailable. Skipping shutdown. Update will continue without closing the app."
    } elseif ($mrTrisProcs.Count -gt 0) {
        Stop-MrTrisProcesses -Processes $mrTrisProcs
    } else {
        Write-Info "No MrTris_AUTO-related processes found. Proceeding with update."
    }
    Start-Sleep -Seconds 1
} elseif (-not $Force) {
    $running = @()
    $allProcs = Get-MrTrisRelatedProcesses -ProjectRoot $ProjectRoot
    if ($allProcs -eq $null) {
        Write-Warn "Cannot verify running processes. Close MrTris_AUTO manually before continuing."
        Write-Host ""
        $answer = Read-Host "Type 'yes' to continue or press Enter to cancel"
        if ($answer -ne 'yes') {
            Write-ErrorExit "Cancelled by user."
        }
    } elseif ($allProcs.Count -gt 0) {
        $names = ($allProcs | ForEach-Object { $_.Name }) -join ', '
        Write-ErrorExit "MrTris_AUTO-related processes still running: ($names). Close the app first, or use -Force to update anyway."
    }
}

# 9. Validate min_supported_version
if ($Manifest.min_supported_version) {
    $minCmp = Compare-Versions $LocalVer.version $Manifest.min_supported_version
    if ($minCmp -lt 0) {
        Write-ErrorExit "Local version $($LocalVer.version) is below minimum supported version $($Manifest.min_supported_version). Please reinstall."
    }
}

# 10. Download update zip
Write-Step "Downloading update from $($Manifest.download_url)"
$tempDir = Join-Path $env:TEMP "MrTris_AUTO_update"
if (Test-Path -LiteralPath $tempDir -PathType Container) {
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
$zipPath = Join-Path $tempDir "update.zip"
try {
    Invoke-WebRequest -Uri $Manifest.download_url -OutFile $zipPath -UseBasicParsing -TimeoutSec 120
    Write-Success "Downloaded: $zipPath"
} catch {
    Write-ErrorExit "Download failed: $_"
}

# 11. Verify SHA256
Write-Step "Verifying SHA256"
$expectedHash = $Manifest.sha256
if (-not $expectedHash -or $expectedHash -eq "PUT_SHA256_HERE") {
    Write-Warn "Manifest SHA256 is a placeholder - skipping verification"
} else {
    $actualHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLower()
    if ($actualHash -ne $expectedHash.ToLower()) {
        Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
        Write-ErrorExit "SHA256 mismatch. Expected: $expectedHash, Actual: $actualHash"
    }
    Write-Success "SHA256 verified"
}

# 12. Extract to temp
Write-Step "Extracting update package"
$extractPath = Join-Path $tempDir "extracted"
New-Item -ItemType Directory -Path $extractPath -Force | Out-Null
try {
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractPath -Force
    Write-Success "Extracted to $extractPath"
} catch {
    Write-ErrorExit "Extraction failed: $_"
}

# 13. Backup current files
$backupPath = Backup-UpdateTargets

# 14. Apply update
Write-Step "Applying update"
$backupCreated = $true
try {
    foreach ($target in $UpdateTargets) {
        $source = Join-Path $extractPath $target
        if (-not (Test-Path -LiteralPath $source)) { continue }
        $dest = Join-Path $ProjectRoot $target

        # Skip entire target if it matches a preserved pattern
        if (Is-Preserved $dest) {
            Write-Info "  Skipping preserved: $target"
            continue
        }

        if (Test-Path -LiteralPath $source -PathType Container) {
            # For directories, copy files individually to avoid deleting preserved files
            $files = Get-ChildItem -LiteralPath $source -Recurse -File
            foreach ($f in $files) {
                $relPath = $f.FullName.Substring($source.Length + 1)
                if (Is-Preserved (Join-Path $dest $relPath)) {
                    Write-Info "    Skipping preserved: $relPath"
                    continue
                }
                $targetFile = Join-Path $dest $relPath
                $targetDir = Split-Path -Parent $targetFile
                if (-not (Test-Path -LiteralPath $targetDir -PathType Container)) {
                    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
                }
                Copy-Item -LiteralPath $f.FullName -Destination $targetFile -Force
            }
            # Also ensure new directories from the package exist (for empty dirs)
            $dirs = Get-ChildItem -LiteralPath $source -Recurse -Directory
            foreach ($d in $dirs) {
                $relPath = $d.FullName.Substring($source.Length + 1)
                $targetDir = Join-Path $dest $relPath
                if (-not (Test-Path -LiteralPath $targetDir -PathType Container)) {
                    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
                }
            }
        } else {
            # Single file target
            $parent = Split-Path -Parent $dest
            if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
                New-Item -ItemType Directory -Path $parent -Force | Out-Null
            }
            Copy-Item -LiteralPath $source -Destination $dest -Force
        }
        Write-Info "  Updated: $target"
    }
    Write-Success "Update applied successfully"
} catch {
    # Rollback
    if ($backupPath) {
        Restore-UpdateTargets $backupPath
    }
    Write-ErrorExit "Update failed. Rolled back to previous version."
}

# 15. Write new version.json
$newVersionFile = Join-Path $ProjectRoot "version.json"
$versionObj = @{
    version = $Manifest.version
    channel = $Manifest.channel
} | ConvertTo-Json
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($newVersionFile, $versionObj, $Utf8NoBom)
Write-Success "version.json updated to $($Manifest.version)"

# 16. Cleanup temp
Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue

# 17. Restart if requested (FromUI mode)
if ($RestartAfterUpdate) {
    Write-Host ""
    Restart-App -ProjectRoot $ProjectRoot
}

# 18. Done
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Update successful!" -ForegroundColor Green
Write-Host "  Version $($Manifest.version) ($($Manifest.channel))" -ForegroundColor Green
if (-not $RestartAfterUpdate) {
    Write-Host "  Restart the app to apply changes." -ForegroundColor Green
}
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
exit 0
