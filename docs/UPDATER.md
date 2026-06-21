# MrTris_AUTO Updater

## Update Model

MrTris_AUTO uses a **patch-based update model**:

1. **Developer** runs `scripts/make_update_package.ps1` to create a `.zip` patch + `manifest.json`.
2. **Developer** uploads both files to a **GitHub Release**.
3. **User** runs `update_tool.bat` (or `scripts/update_tool.ps1` directly) to download and apply the update.

### Why GitHub Releases?

- **Reliable direct-download URLs** — `https://github.com/.../releases/download/...` works consistently.
- **No auth required** for public repos.
- **Built-in versioning** via Git tags.
- **Avoids Google Drive** instability (redirects, rate limits, cookie requirements).

---

## For Developers: Creating an Update Package

### Prerequisites

- Windows PowerShell 5.1+
- Project root with `version.json` (at `E:\AUTO_REVIEW\version.json`)

### Steps

1. **Update the version number** in `version.json` (or pass `-TargetVersion`):

```json
{
  "version": "1.0.1",
  "channel": "stable"
}
```

2. **Run the packaging script**:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\make_update_package.ps1 -TargetVersion 1.0.1
```

This produces:

| File | Description |
|------|-------------|
| `build\update\MrTris_AUTO_1.0.1_patch.zip` | Update package (excludes user data, caches) |
| `build\update\MrTris_AUTO_1.0.1_manifest.json` | Manifest with SHA256 ready for upload |

3. **Create a GitHub Release**:

   - Tag: `v1.0.1`
   - Title: `v1.0.1`
   - Attach:
     - `MrTris_AUTO_1.0.1_patch.zip`
     - `MrTris_AUTO_1.0.1_manifest.json`

4. **Update the manifest URL** in `scripts/update_tool.ps1`:

```powershell
$ManifestUrl = "https://raw.githubusercontent.com/YOUR_ORG/MrTris_AUTO_UPDATES/main/manifest.json"
```

### What's Included in the Package

| Included | Excluded |
|----------|----------|
| `backend/` | `version.json` (written by updater) |
| `frontend/dist/` | `data/creator_dna.md` (preserved) |
| `scripts/` | `data/cookies/` (user data) |
| `docs/` | `outputs/` (user data) |
| `README.md` | `temp/` (cache) |
| `SYSTEM_DESIGN.md` | `__pycache__/`, `*.pyc`, `*.pyo` |
| `ARCHITECTURE_DIAGRAM.md` | `node_modules/` |
| `AGENTS.md` | `.venv/`, `.venv312/` |
| `review_preset.md` | `.git/`, `.pytest_cache/` |
| | `build/installer/` |
| | `*.log` |
| | `*.db`, `*.sqlite`, `*.sqlite3` — local database files |

---

## For Users: Running the Updater

### Option 1: Double-click `update_tool.bat`

Found at the project root:

```
update_tool.bat
```

This opens a console window, runs the updater, and pauses so you can read the output.

### Option 2: Run PowerShell directly

```powershell
powershell -ExecutionPolicy Bypass -File scripts\update_tool.ps1
```

### DryRun Mode

Preview what the update would do without actually downloading or changing anything:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\update_tool.ps1 -DryRun
```

Output example:

```
  MrTris_AUTO Update Plan (DryRun)
  ============================================
  Project root:    E:\AUTO_REVIEW
  Local version:   1.0.0 (stable)
  Remote version:  1.0.1 (stable)
  Download URL:    https://github.com/.../MrTris_AUTO_1.0.1_patch.zip
  Min supported:   1.0.0
  Published:       2026-06-10

  Update targets:
    - backend
    - frontend\dist
    - scripts
    - docs
    - README.md
    - ...

  Preserved (never touched):
    - data\creator_dna.md
    - data\cookies
    - outputs
    - ...
```

### Force Mode

If the app is running and you want to update anyway (not recommended):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\update_tool.ps1 -Force
```

---

## Rollback Behavior

If any step fails after backup (download verification, extraction, file copy), the updater:

1. Restores **only update-target paths** from the timestamped backup.
2. **Never touches** preserved user data (`data/`, `outputs/`, `temp/`, `.env`, database files, etc.).
3. **Leaves `version.json` unchanged** — it still shows the old version.
4. Prints a clear error message and exits with code 1.

### Backup Location

```
%LOCALAPPDATA%\MrTris_AUTO\backups\YYYY-MM-DD_HHmmss\
```

Each backup is timestamped. Previous backups are never deleted automatically.

### Manual Rollback

If you need to manually restore:

```powershell
$backup = Get-ChildItem "$env:LOCALAPPDATA\MrTris_AUTO\backups" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Copy-Item -LiteralPath "$($backup.FullName)\*" -Destination "E:\AUTO_REVIEW" -Recurse -Force
```

---

## Files Never Modified by the Updater

| Path | Reason |
|------|--------|
| `data/creator_dna.md` | Creator DNA — user content |
| `data/cookies/` | User authentication data |
| `outputs/` | Rendered videos |
| `temp/` | Temporary files |
| `.env` | User configuration |
| `license` files | License keys |
| `logs/` | Diagnostic logs |
| `backend/app.db` | Local database — never overwritten |
| `*.db`, `*.sqlite`, `*.sqlite3` | Local database files anywhere in the project |
| User-generated media | Any file outside `backend/`, `frontend/dist/`, `scripts/`, `docs/` |

---

## Troubleshooting

### Execution Policy Blocks the Script

If PowerShell says "execution of scripts is disabled":

```powershell
powershell -ExecutionPolicy Bypass -File scripts\update_tool.ps1
```

Or double-click `update_tool.bat` which already includes `-ExecutionPolicy Bypass`.

### "App-related processes still running"

Close MrTris_AUTO (including the browser tab and backend) before updating. Or use `-Force`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\update_tool.ps1 -Force
```

### SHA256 Hash Mismatch

The downloaded `.zip` does not match the expected hash. This could mean:

- Download was corrupted → try again.
- Manifest is out of date → contact the developer.
- Security issue → do not run the update; contact the developer.

Check the manifest at the download URL and verify the hash manually:

```powershell
Get-FileHash MrTris_AUTO_1.0.1_patch.zip -Algorithm SHA256
```

### Network / Download Failure

- Check your internet connection.
- Verify the manifest URL is correct (`$ManifestUrl` in `scripts\update_tool.ps1`).
- Try opening the `download_url` in a browser.
- Corporate firewalls may block GitHub; use a personal network.

### "Local version is below minimum supported"

Your installation is too old for this patch. You need a full reinstall from the installer.

### Where is the Backup?

```
%LOCALAPPDATA%\MrTris_AUTO\backups\
```

Check this folder for timestamped backup directories.

---

## Customizing the Manifest URL

Edit this constant at the top of `scripts\update_tool.ps1`:

```powershell
$ManifestUrl = "https://raw.githubusercontent.com/YOUR_NAME/MrTris_AUTO_UPDATES/main/manifest.json"
```

You can point it to any URL that returns valid JSON with the manifest structure.

---

## Architecture Overview

```
version.json              ← local version file (read at start, written on success)
scripts/
├── update_tool.ps1       ← user-side updater
├── make_update_package.ps1 ← developer-side packager
├── update_manifest.example.json ← reference manifest
update_tool.bat            ← batch wrapper (double-click friendly)
docs/UPDATER.md            ← this file
```

**Update flow:**

```
User runs update_tool.bat
  → update_tool.ps1 reads version.json
  → downloads manifest from GitHub
  → compares versions
  → downloads patch zip
  → verifies SHA256
  → backs up current files
  → extracts & copies new files
  → writes new version.json
  → done
```

**On error at any step:**

```
  → restore backup (if backup was created)
  → keep version.json unchanged
  → print error
  → exit 1
```
