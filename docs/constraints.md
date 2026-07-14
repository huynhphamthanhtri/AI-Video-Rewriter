# Constraints

## Scope Rules

- Do not change route contracts (`/api/*`) without explicit approval. The frontend `api.ts` mirrors these contracts.
- Do not move or rename persisted app data paths (outputs, temp, logs, data). These are configurable via `MRTRIS_AUTO_*` env vars.
- Do not refactor service names or class interfaces unless the change is scoped in the task.
- Do not add new dependencies without review. The app runs with minimal deps in both dev and packaged modes.
- Do not change database schema (SQLAlchemy models) without approval. Migration helpers are lightweight and manual.

## Runtime Files

- All runtime files (`outputs/`, `temp/`, `logs/`, `data/`) are gitignored and must never be committed.
- `.env` and `.env.*` files must never be committed.
- `cookies.txt` (YouTube cookies) must never be committed.
- `gemini_session.json` must never be committed.

## External Tools

- FFmpeg and ffprobe are required for all video operations. They must be on PATH or configured via `MRTRIS_AUTO_FFMPEG_BINARY` / `MRTRIS_AUTO_FFPROBE_BINARY`.
- yt-dlp is required for YouTube downloads. Configure via `YTDLP_BINARY` or PATH.
- Playwright and its browser binaries are required for Gemini automation.
- Node.js is required for launcher updater and packaging runtime.

## Optional TTS

- VieNeu Turbo is optional. If not installed, TTS features will not work, but all other features remain functional.
- The error "VieNeu Turbo chưa được cài" is expected when TTS is missing. Run `scripts/install_tts.ps1` to install.
- TTS status is checked at runtime; do not gate non-TTS features behind TTS availability.

## Packaging Constraints

- Private license keys (private_key.b64, private.pem) must never be included in builds or zips.
- The packaging script (`package_windows.ps1`) validates against keygen/private key leaks and fails if detected.
- The portable Python runtime does not include `pythonw.exe` — the launcher handles this.

## No-Refactor Rules

Unless explicitly asked:
- Do not rename files or APIs.
- Do not change route contracts.
- Do not restructure project directories.
- Do not upgrade dependencies.
- Do not change FFmpeg/yt-dlp CLI arguments.
- Do not change Gemini selector strings.
