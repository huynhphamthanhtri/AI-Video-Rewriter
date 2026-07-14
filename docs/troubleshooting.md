# Troubleshooting

## Backend Startup

**Backend won't start / port already in use**: Dev port is 8007 (`backend/run_dev.py`). Packaged launcher uses ports 8000–8004. Kill competing processes or change port.

**"VieNeu Turbo chưa được cài"**: Run `scripts/install_tts.ps1`, then restart backend. This error appears when TTS is required but optional package is missing. Non-TTS features continue to work.

**FFmpeg/ffprobe not found**: Ensure FFmpeg is on PATH, or set `MRTRIS_AUTO_FFMPEG_BINARY` / `MRTRIS_AUTO_FFPROBE_BINARY` env vars.

**Database errors**: Delete `backend/app.db` (dev) or `%LOCALAPPDATA%\MrTris_AUTO\data\app.db` (packaged). It will be recreated and presets re-seeded.

## Frontend

**Blank page at localhost:5173**: Check that backend is running. The Vite dev server proxies API calls to `http://127.0.0.1:8007`. If backend is on a different port, set `VITE_API_BASE_URL`.

**API calls fail with 404**: Ensure backend is running on port 8007. Check network tab — the correct API base is `/api` by default.

**"Không tải được danh sách preset"**: Backend may not have started fully. Wait for DB creation and preset seeding. Check backend console logs.

## TTS

**"VieNeu Turbo chưa được cài" on every rebuild**: Add TTS deps (`vieneu==2.7.0`, `llama-cpp-python==0.3.16`, `librosa==0.11.0`) to `backend/requirements.txt`, or run `scripts/install_tts.ps1` after each `pip install -r requirements.txt`.

**TTS preview plays nothing**: Check `temp/tts_voices/` for generated audio. FFmpeg must be available for audio probe. Check TTS status in Runtime Health.

**"VieNeu không tìm thấy preset voice"**: Voice name mismatch between `VIENEU_TURBO_VOICES` and available modèle. Reinstall TTS package.

## FFmpeg / yt-dlp

**Video download fails**: Check `cookies.txt` is valid YouTube cookies. Check yt-dlp logs under `temp/` or `logs/`. Test yt-dlp directly: `yt-dlp --verbose 'https://youtube.com/watch?v=...'`.

**Render fails at cut/concat**: Check FFmpeg is functional: `ffmpeg -version`. Check source video is accessible and not corrupted. Check `temp/` disk space.

**Encoder detection fails**: Backend auto-selects encoder (nvenc > qsv > amf > cpu). If hardware encoding fails, it falls back to CPU. Check `RuntimeHealth.video_encoder_auto_result`.

## Gemini

**"Cannot run prompt — no Gemini session"**: Open Gemini browser via the UI button. You must be logged into `gemini.google.com` in the Playwright browser.

**Auto pipeline stuck at "wait_login"**: The browser window opened. Log into your Google account, and the pipeline will continue automatically. Check that the browser is not minimized behind other windows.

**Gemini response not parseable**: The retry mechanism will attempt up to 3 times. If all fail, check the raw response in browser. Consider adjusting the prompt or JSON schema.

## WebSocket

**Auto pipeline progress not updating**: WebSocket at `/api/gemini/status/{task_id}` might be disconnected. Check browser console for WebSocket errors. Do not use `uvicorn --reload` in production — WebSocket reconnection issues occur.

## Render Jobs

**Render stuck at 0%**: Check `temp/` disk space. Check yt-dlp download. Check FFmpeg process is running.

**ETA is inaccurate**: ETA is computed by phase-based estimation. It improves as more phases complete. Paused jobs (blur review) stop the ETA timer.

**Job queue not processing**: Background render worker runs as a thread. Check if another job is already running. Jobs are processed sequentially.

## Packaging

**Installer fails**: Ensure all runtime binaries (ffmpeg, ffprobe, yt-dlp) are on PATH. Run `packaging\package_windows.ps1 -SkipTests -SkipFrontendBuild` first to debug staging, then run ISCC.

**Runtime health shows missing tools**: Packaged launcher sets `MRTRIS_AUTO_PACKAGED=1`. Check `%LOCALAPPDATA%\MrTris_AUTO\logs\startup_diagnostics.txt`.

**Upgrade install fails**: Kill all running MrTris_AUTO processes (Python, uvicorn, node) before installing. The installer attempts to stop processes under `{app}`, but some `.pyd` files may remain locked.
