# MrTris_AUTO Release Skill

## Purpose

This document defines the repeatable process for publishing a new MrTris_AUTO update using the RC-1A updater system.

## Golden Rule

Never update `manifest.json` to a new version before the matching zip has been uploaded to GitHub Releases and its SHA256 has been verified.

If `manifest.json` points to a missing zip or wrong SHA256, real users may receive failed updates.

## Standard Release Flow

1. Implement code changes.
2. Run validation:

   ```powershell
   python -m pytest tests/ -q
   npx tsc --noEmit
   npm run build
   ```
3. Choose next version (example: `1.0.2`).
4. Run package script:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\make_update_package.ps1 -TargetVersion 1.0.2
   ```
5. Confirm outputs:

   - `build\update\MrTris_AUTO_1.0.2_patch.zip`
   - `build\update\MrTris_AUTO_1.0.2_manifest.json`
6. Inspect package safety — verify exclusions:

   - `version.json` not in zip
   - `data\creator_dna.md` not in zip
   - `data\cookies\` not in zip
   - `outputs\` not in zip
   - `temp\` not in zip
   - `.env` not in zip
   - `logs\` not in zip
   - `backend\app.db` not in zip
   - `*.db`, `*.sqlite`, `*.sqlite3` not in zip
7. Upload zip to GitHub Release:

   - Repo: `MrTris_AUTO_RELEASES`
   - Tag: `v1.0.2`
   - Asset: `MrTris_AUTO_1.0.2_patch.zip`
8. Verify release zip URL downloads correctly.
9. Update `manifest.json` in `MrTris_AUTO_UPDATES` repo:

   - `version`
   - `published_at`
   - `download_url`
   - `sha256`
   - `notes`
10. Verify raw manifest URL opens as JSON.
11. Run updater DryRun:

    ```powershell
    powershell -ExecutionPolicy Bypass -File scripts\update_tool.ps1 -DryRun
    ```
12. Run live update test on a **copied** project folder, never the main dev folder.
13. Verify preserved files unchanged:

    - `data\creator_dna.md`
    - `data\cookies\`
    - `outputs\`
    - `.env`
    - `logs\`
    - `backend\app.db`
14. Only after all checks pass, announce the update.

## Live URLs

| Resource | URL |
|----------|-----|
| Manifest (raw) | `https://raw.githubusercontent.com/huynhphamthanhtri/MrTris_AUTO_UPDATES/main/manifest.json` |
| Release repo | `https://github.com/huynhphamthanhtri/MrTris_AUTO_RELEASES` |
| Current release | `v1.0.1` |
| Current SHA256 | `23fc7c4081284e4587b55c91bf39a1a061e979ecc9b4875140a0b45d80bfb996` |

## Agent Checklist

When asked to prepare a release, the agent should:

- Package locally
- Report zip size
- Report SHA256
- Inspect zip exclusions
- Run tests / build
- Draft manifest content
- Wait for human GitHub upload steps
- Then verify raw manifest and live updater

The agent must **not** assume GitHub upload is complete unless the user confirms it.

## Human-only Steps

The human usually performs:

- Create GitHub release
- Upload zip asset
- Edit / upload `manifest.json`
- Confirm browser can open zip URL and raw manifest URL

## Failure Rules

| Condition | Action |
|-----------|--------|
| SHA256 mismatch | Stop. Do not tell users to update. Regenerate package or correct manifest. |
| Manifest points to unavailable zip | Revert manifest to previous working version immediately. |
| Updater overwrites preserved files | Block release. Fix updater before publishing. |

## Close Criteria

A release is closed only when:

- Package generated
- Zip uploaded
- Manifest updated
- SHA256 verified
- DryRun passes
- Real update test passes on copied folder
- Preserved files remain unchanged
- App validation passes
