<#
.SYNOPSIS
    MrTris_AUTO Update Package Builder — creates a patch zip
    with SHA256 manifest for GitHub Releases upload.

.PARAMETER TargetVersion
    Version string for the update (e.g., "1.0.1").
    If omitted, reads from version.json.

.PARAMETER OutputDir
    Output directory for the zip and manifest.
    Default: <project>\build\update
#>

param(
    [string]$TargetVersion,
    [string]$OutputDir
)

# -------------------- CONFIGURATION --------------------
$ProjectRoot = Split-Path -Parent $PSScriptRoot

# Items to include in the update package (relative to project root)
$IncludePaths = @(
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

# Exclusion patterns for directories/files inside included paths
$ExcludePatterns = @(
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "node_modules",
    ".venv",
    ".venv312",
    ".git",
    ".pytest_cache",
    "*.log",
    "*.db",
    "*.sqlite",
    "*.sqlite3"
)

# User data/cache dirs to exclude entirely (even if matched by IncludePaths)
$ExcludeDirs = @(
    "data\cookies",
    "outputs",
    "temp",
    "build\installer"
)

# -------------------- HELPER FUNCTIONS --------------------
function Write-Step($Message) {
    Write-Host ">>> $Message" -ForegroundColor Cyan
}

function Write-Info($Message) {
    Write-Host "    $Message" -ForegroundColor Gray
}

function Write-Success($Message) {
    Write-Host "    $Message" -ForegroundColor Green
}

# -------------------- MAIN --------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  MrTris_AUTO Update Package Builder" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 1. Determine version
if (-not $TargetVersion) {
    $versionFile = Join-Path $ProjectRoot "version.json"
    if (-not (Test-Path -LiteralPath $versionFile -PathType Leaf)) {
        Write-Host "ERROR: version.json not found and -TargetVersion not specified." -ForegroundColor Red
        exit 1
    }
    try {
        $verObj = Get-Content -LiteralPath $versionFile -Encoding UTF8 -Raw | ConvertFrom-Json
        $TargetVersion = $verObj.version
        Write-Info "Using version from version.json: $TargetVersion"
    } catch {
        Write-Host "ERROR: Failed to parse version.json: $_" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Info "Target version: $TargetVersion (from parameter)"
}

# 2. Determine output directory
if (-not $OutputDir) {
    $OutputDir = Join-Path (Join-Path $ProjectRoot "build") "update"
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
Write-Info "Output directory: $OutputDir"

# 3. Build zip path
$zipName = "MrTris_AUTO_$TargetVersion`_patch.zip"
$zipPath = Join-Path $OutputDir $zipName
Write-Step "Creating package: $zipName"

# 4. Build excluded paths list (full paths)
$excludeFullPaths = @()
foreach ($ed in $ExcludeDirs) {
    $full = Join-Path $ProjectRoot $ed
    $excludeFullPaths += $full
}

# 5. Compress using built-in Compress-Archive
$compressItems = @()
foreach ($relPath in $IncludePaths) {
    $fullPath = Join-Path $ProjectRoot $relPath
    if (Test-Path -LiteralPath $fullPath) {
        # Check if this is an excluded dir
        $isExcluded = $false
        foreach ($ex in $excludeFullPaths) {
            $resolvedEx = (Resolve-Path -LiteralPath $ex -ErrorAction SilentlyContinue).Path
            $resolvedFull = (Resolve-Path -LiteralPath $fullPath -ErrorAction SilentlyContinue).Path
            if ($resolvedEx -and $resolvedFull -and $resolvedFull.StartsWith($resolvedEx, [StringComparison]::OrdinalIgnoreCase)) {
                $isExcluded = $true
                break
            }
        }
        if (-not $isExcluded) {
            $compressItems += @{Path = $fullPath; RelativePath = $relPath}
            Write-Info "  Including: $relPath"
        } else {
            Write-Info "  Excluding (user data/cache): $relPath"
        }
    } else {
        Write-Info "  Skipping (not found): $relPath"
    }
}

# 6. Remove old zip if exists
Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue

# 7. Create zip
try {
    # Build a temp staging folder to control exact zip structure
    $stageDir = Join-Path $env:TEMP "MrTris_AUTO_pkg_$([System.IO.Path]::GetRandomFileName())"
    New-Item -ItemType Directory -Path $stageDir -Force | Out-Null

    # Helper: recursive directory copy with exclusion patterns
    function Copy-DirWithExclusions {
        param([string]$Source, [string]$Dest)
        if (-not (Test-Path -LiteralPath $Dest -PathType Container)) {
            New-Item -ItemType Directory -Path $Dest -Force | Out-Null
        }
        # Copy files and dirs one level at a time
        Get-ChildItem -LiteralPath $Source | ForEach-Object {
            $relName = $_.Name
            $targetPath = Join-Path $Dest $relName
            $excluded = $false
            # Check exclusion patterns
            foreach ($pat in $ExcludePatterns) {
                if ($relName -like $pat) {
                    $excluded = $true; break
                }
            }
            # Check excluded full paths
            if (-not $excluded) {
                $full = $_.FullName
                foreach ($fullEx in $excludeFullPaths) {
                    $resolvedEx = (Resolve-Path -LiteralPath $fullEx -ErrorAction SilentlyContinue).Path
                    $resolvedFull = (Resolve-Path -LiteralPath $full -ErrorAction SilentlyContinue).Path
                    if ($resolvedEx -and $resolvedFull -and $resolvedFull.StartsWith($resolvedEx, [StringComparison]::OrdinalIgnoreCase)) {
                        $excluded = $true; break
                    }
                }
            }
            if ($excluded) { return }
            if ($_.PSIsContainer) {
                Copy-DirWithExclusions $_.FullName $targetPath
            } else {
                Copy-Item -LiteralPath $_.FullName -Destination $targetPath -Force
            }
        }
    }

    foreach ($item in $compressItems) {
        $dest = Join-Path $stageDir $item.RelativePath
        $destParent = Split-Path -Parent $dest
        New-Item -ItemType Directory -Path $destParent -Force | Out-Null

        if (Test-Path -LiteralPath $item.Path -PathType Container) {
            Copy-DirWithExclusions $item.Path $dest
        } else {
            Copy-Item -LiteralPath $item.Path -Destination $dest -Force
        }
    }

    # Explicitly exclude version.json from staging
    $stageVersion = Join-Path $stageDir "version.json"
    Remove-Item -LiteralPath $stageVersion -Force -ErrorAction SilentlyContinue

    # Explicitly exclude creator_dna.md
    $stageDna = Join-Path (Join-Path $stageDir "data") "creator_dna.md"
    Remove-Item -LiteralPath $stageDna -Force -ErrorAction SilentlyContinue

    Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $zipPath -Force
    Write-Success "Created: $zipPath"

    # Cleanup stage
    Remove-Item -LiteralPath $stageDir -Recurse -Force -ErrorAction SilentlyContinue
} catch {
    Write-Host "ERROR: Failed to create zip: $_" -ForegroundColor Red
    Remove-Item -LiteralPath $stageDir -Recurse -Force -ErrorAction SilentlyContinue
    exit 1
}

# 8. Calculate SHA256
Write-Step "Calculating SHA256"
try {
    $hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLower()
    Write-Success "SHA256: $hash"
} catch {
    Write-Host "ERROR: Failed to calculate hash: $_" -ForegroundColor Red
    exit 1
}

# 9. Generate manifest
$manifestPath = Join-Path $OutputDir "MrTris_AUTO_${TargetVersion}_manifest.json"
$manifestContent = @{
    version               = $TargetVersion
    channel               = "stable"
    published_at          = (Get-Date -Format "yyyy-MM-dd")
    min_supported_version = "1.0.0"
    download_url          = "https://github.com/huynhphamthanhtri/MrTris_AUTO_RELEASES/releases/download/v$TargetVersion/$zipName"
    sha256                = $hash
    notes                 = @(
        "v1.0.7 TTS Studio hotfix",
        "Fix: TTS Studio session state persists across tab switches",
        "Fix: TTS Studio generated filenames are readable (tts_{voice}_{text}_{timestamp}_{id})",
        "Fix: Preserve generating/result/error UI after returning to TTS tab",
        "New: Clear stale result only when user changes text, voice, locale, or format"
    )
}
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($manifestPath, ($manifestContent | ConvertTo-Json -Depth 4), $Utf8NoBom)
Write-Success "Manifest: $manifestPath"

# 10. Print summary
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Package created successfully!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Package: $zipPath" -ForegroundColor Gray
Write-Host "  Size: $((Get-Item -LiteralPath $zipPath).Length / 1MB) MB" -ForegroundColor Gray
Write-Host "  SHA256: $hash" -ForegroundColor Gray
Write-Host "  Manifest: $manifestPath" -ForegroundColor Gray
Write-Host ""
Write-Host "  GitHub Release checklist:" -ForegroundColor Yellow
Write-Host "    1. Create a new release on GitHub: v$TargetVersion" -ForegroundColor Yellow
Write-Host "    2. Upload: $zipName" -ForegroundColor Yellow
Write-Host "    3. Upload: MrTris_AUTO_${TargetVersion}_manifest.json" -ForegroundColor Yellow
Write-Host "    4. Update manifest URL in scripts/update_tool.ps1" -ForegroundColor Yellow
Write-Host "    5. Publish release" -ForegroundColor Yellow
Write-Host ""
exit 0
