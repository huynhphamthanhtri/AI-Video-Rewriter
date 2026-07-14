# Local Build Test Report

> **STATUS: LOCAL BUILD ONLY — NOT PUBLISHED**

## 1. Build Context

| Field | Value |
|-------|-------|
| Commit hash | `bde403f` |
| Branch | `main` |
| Test count | `289 passed` |
| Version built | `1.0.2` |
| Built at | 2026-06-23 |

## 2. Validation Commands

### pytest

```powershell
python.exe -m pytest tests/ -q
```

Result:

```text
289 passed in 6.81s
```

### TypeScript

```powershell
npx tsc --noEmit
```

Result:

```text
PASS — no output, no errors
```

### Frontend Build

```powershell
npm run build
```

Result:

```text
vite v6.4.3 building for production...
1852 modules transformed.
dist/index.html                 0.64 kB | gzip:   0.40 kB
dist/assets/index-B_MZDgGQ.css 37.94 kB | gzip:   7.05 kB
dist/assets/index-CxzAy3GP.js 437.09 kB | gzip: 123.04 kB
built in 3.22s
```

## 3. Package Output

| Item | Path |
|------|------|
| Zip | `E:\AUTO_REVIEW\build\update\MrTris_AUTO_1.0.2_patch.zip` |
| Manifest | `E:\AUTO_REVIEW\build\update\MrTris_AUTO_1.0.2_manifest.json` |
| Zip size | `0.33 MB` / `345,797 bytes` |
| Entries | `85` |

## 4. SHA256

```text
f5c087892c8a989079194cafc28859eb88314140db20201eeff40a8a61364e72
```

## 5. Zip Safety Inspection

Result: **PASS**

No forbidden files found.

| Forbidden pattern | Result |
|-------------------|--------|
| `version.json` | Not found |
| `data\creator_dna.md` | Not found |
| `data\cookies\` | Not found |
| `outputs\` | Not found |
| `temp\` | Not found |
| `.env` | Not found |
| `logs\` | Not found |
| `backend\app.db` | Not found |
| `*.db`, `*.sqlite`, `*.sqlite3` | Not found |

## 6. DryRun Result

Command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\update_tool.ps1 -DryRun
```

Result:

```text
Project root: E:\AUTO_REVIEW
Local version: 1.0.4 (stable)
Remote version: 1.0.4 (channel: stable)
Already up to date. (local: 1.0.4, remote: 1.0.4)
```

Limitation:

DryRun reads the production remote manifest. This local package `1.0.2` was not published and the production manifest was not updated.

## 7. Local Test Instructions

Use this package only on a copied project folder, not the main dev folder.

Suggested local test copy:

```powershell
Copy-Item -Recurse -Path "E:\AUTO_REVIEW" -Destination "E:\AUTO_REVIEW_TEST"
```

Preserved files to verify after local update testing:

```text
data\creator_dna.md
data\cookies\
outputs\
.env
logs\
backend\app.db
```

Gemini session validation after installing/running app:

```text
1. Delete existing gemini_session.json.
2. Open browser from the app.
3. Login Gemini.
4. Confirm session saved under %LOCALAPPDATA%\MrTris_AUTO\data\gemini_session.json.
5. Close app.
6. Reopen app.
7. Run auto pipeline.
8. Confirm it does not request login again.
```

## 8. Release Status

```text
LOCAL BUILD ONLY
NOT PUBLISHED
MANIFEST NOT UPDATED
GITHUB RELEASE NOT CREATED
```

## Summary

| Check | Result |
|-------|--------|
| pytest | PASS — `289 passed` |
| TypeScript | PASS |
| Frontend build | PASS |
| Package created | PASS |
| Zip safety | PASS |
| DryRun | PASS — no changes made |
| Safe for local testing | YES |
