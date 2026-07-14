# MrTris_AUTO Windows Packaging

Target release:
- App name: `MrTris_AUTO`
- Installer: `MrTris_AUTO_Setup_v1.0.0_beta.exe`
- Install folder: `C:\Program Files\MrTris_AUTO`
- User data: `%LOCALAPPDATA%\MrTris_AUTO`
- Output videos: `%USERPROFILE%\Videos\AutoReview`
- UI: PyWebView desktop window loading `http://127.0.0.1:<port>`, fallback to browser if WebView2 unavailable
- OS: Windows 10/11 (WebView2 runtime recommended)
- Beta signing: unsigned

## Build Staging Package

From repo root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\package_windows.ps1
```

This creates:

```text
build\package\MrTris_AUTO\
```

The script runs backend tests and frontend build unless skipped:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\package_windows.ps1 -SkipTests -SkipFrontendBuild
```

## Required Runtime Files

Before building the installer, verify the staged folder contains:

```text
runtime\python\python.exe
runtime\python\pythonw.exe (optional — for console-free main shortcut)
runtime\python\python312.dll
runtime\python\python312.zip
runtime\ffmpeg\ffmpeg.exe
runtime\ffmpeg\ffprobe.exe
runtime\yt-dlp\yt-dlp.exe
runtime\node\node.exe
runtime\tts\...
backend\app\main.py
frontend\dist\index.html
MrTris_AUTO.py
MrTris_AUTO_Diagnostics.py
MrTris_AUTO_Repair.py
```

Note: the embedded Python runtime from python.org does **not** include `pythonw.exe`. The main shortcut will show a console window unless you manually add `pythonw.exe` to `runtime\python\`. If `pythonw.exe` is absent, the installer creates a second "(console)" shortcut and the normal shortcut uses `python.exe`.

VieNeu Turbo files must be present under `runtime\tts` or otherwise available to the bundled Python environment. If TTS is missing, the app should still open but TTS status will report unavailable.

## Verified Packaging Baseline

This baseline was tested successfully on a customer Windows machine. Review this section before every future packaging run.

Known-good installer:

```text
build\installer\MrTris_AUTO_Setup_v1.0.0_beta.exe
SHA256: 53F4DF1DC75112A55B2EE2E32E51246B7D753DFB250E6D97DCED1392FCBF1EF5
Size: 241,491,953 bytes
```

Licensed installer baseline:

```text
build\installer\MrTris_AUTO_Setup_v1.0.0_beta.exe
SHA256: 23997B1DF1D22D1E86681C85903F4A7F3B21F25059013CA8E9F7C6D6F93CD5DB
Size: 245,434,897 bytes
License enforcement: enabled by packaged launcher
Built: 2026-06-06
Keygen/private key: moved outside app workspace to E:\MrTris_Keygen_Internal
Packaged frontend API base: relative /api, verified after upgrade install on port 8001
```

Installer upgrade behavior:

```text
Before copying files, the installer stops processes whose executable path is under {app}.
This prevents rollback when an existing backend keeps Python .pyd files locked.
Verified by reinstalling while MrTris_AUTO was running: Installation process succeeded.
```

Runtime layout must include:

```text
runtime\python\python.exe
runtime\python\python312.dll
runtime\python\python312.zip
runtime\node\node.exe
runtime\ffmpeg\ffmpeg.exe
runtime\ffmpeg\ffprobe.exe
runtime\yt-dlp\yt-dlp.exe
frontend\dist\index.html
backend\app\main.py
MrTris_AUTO.py
MrTris_AUTO_Diagnostics.py
MrTris_AUTO_Repair.py
```

FFmpeg packaging rule:

```text
Do not copy Chocolatey shim binaries from:
C:\ProgramData\chocolatey\bin\ffmpeg.exe
C:\ProgramData\chocolatey\bin\ffprobe.exe

Copy the real binaries instead:
C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffmpeg.exe
C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffprobe.exe
```

The Chocolatey shim fails after relocation and may look for this invalid path:

```text
runtime\lib\ffmpeg\tools\ffmpeg\bin\ffmpeg.exe
```

yt-dlp execution rule:

```text
Use runtime\python\python.exe -m yt_dlp as the downloader command.
Keep runtime\yt-dlp\yt-dlp.exe only for diagnostics/fallback visibility.
```

Reason: on a customer machine, standalone `yt-dlp.exe` exited with code `1` while stdout/stderr were empty, but the Python module mode worked in staging.

Launcher/runtime environment baseline:

```text
MRTRIS_AUTO_PACKAGED=1
FFMPEG_BINARY={app}\runtime\ffmpeg\ffmpeg.exe
FFPROBE_BINARY={app}\runtime\ffmpeg\ffprobe.exe
IMAGEIO_FFMPEG_EXE={app}\runtime\ffmpeg\ffmpeg.exe
YTDLP_BINARY={app}\runtime\yt-dlp\yt-dlp.exe
YTDLP_JS_RUNTIMES=node
YTDLP_REMOTE_COMPONENTS=ejs:github
YTDLP_PREFER_H264=true
PATH={app}\runtime\ffmpeg;{app}\runtime\node;...
```

Backend packaged-mode safeguards must remain in place:

```text
If FFMPEG_BINARY or FFPROBE_BINARY points to a missing file, fallback to runtime\ffmpeg\*.exe.
If YTDLP_BINARY points to a missing file, fallback to runtime\yt-dlp\yt-dlp.exe.
Runtime Health must expose ffmpeg_version_status, ffprobe_version_status, and ytdlp_module_status.
```

License packaging rule:

```text
MrTris_AUTO customer installer contains only the public Ed25519 key.
MrTris_Keygen is internal only and lives outside this app workspace at E:\MrTris_Keygen_Internal.
The internal private key is E:\MrTris_Keygen_Internal\secrets\private_key.b64.
Never copy keygen, keygen\secrets, private_key.b64, private.pem, or any private license key into build\package\MrTris_AUTO.
E:\AUTO_REVIEW must not contain the production private key or internal keygen folder.
packaging\package_windows.ps1 must fail if a private key filename or keygen file/folder appears in the customer package.
```

Internal keygen rule:

```text
Run keygen from E:\MrTris_Keygen_Internal only:
python E:\MrTris_Keygen_Internal\MrTris_Keygen.py

Open http://127.0.0.1:8765.
Customer licenses generated by this internal keygen remain compatible with the public key bundled in MrTris_AUTO.
Do not commit, package, zip, or send E:\MrTris_Keygen_Internal to customers.
```

License mode baseline:

```text
Offline hardware-bound signed license.
Customer app shows short Hardware ID, e.g. 8F2A-19CD-77B1-42E9.
Keygen binds license to the short Hardware ID.
Trial: full features, 1 day from key generation.
Monthly: full features, 30 days from key generation.
Lifetime: full features, no expiry.
License key format: MRTRIS-V1-<payload>.<signature>.
```

Required smoke tests before compiling the installer:

```powershell
python -m pytest tests/ -x -v
npm run build
build\package\MrTris_AUTO\runtime\ffmpeg\ffmpeg.exe -version
build\package\MrTris_AUTO\runtime\ffmpeg\ffprobe.exe -version
build\package\MrTris_AUTO\runtime\node\node.exe --version
build\package\MrTris_AUTO\runtime\python\python.exe -c "import webview; print('pywebview ok')"
build\package\MrTris_AUTO\runtime\python\python.exe -m yt_dlp --js-runtimes node --remote-components ejs:github --version
```

Customer-machine test notes:

```text
Kill old backend/python/uvicorn processes before testing a new installer.
If runtime path problems persist, uninstall and delete C:\Program Files\MrTris_AUTO before reinstalling.
Check %LOCALAPPDATA%\MrTris_AUTO\logs\startup_diagnostics.txt after launch.
Check Runtime Health for ffmpeg_binary, ffprobe_binary, node_status, and ytdlp_module_status.
For YouTube failures, inspect ytdlp_preflight.log, ytdlp_stdout.log, ytdlp_stderr.log, and ytdlp.log.
```

## Build Installer

Install Inno Setup, then compile:

```powershell
iscc packaging\inno\MrTris_AUTO.iss
```

Output:

```text
build\installer\MrTris_AUTO_Setup_v1.0.0_beta.exe
```

Generate checksum:

```powershell
Get-FileHash build\installer\MrTris_AUTO_Setup_v1.0.0_beta.exe -Algorithm SHA256
```

## Clean Machine Smoke Test

Run on Windows 10/11 without Python or Node installed:

1. Install `MrTris_AUTO_Setup_v1.0.0_beta.exe`.
2. Launch `MrTris_AUTO` from Start Menu.
3. Desktop PyWebView window opens (or browser fallback if WebView2 is missing).
4. Runtime Health loads.
5. Preset sync status is OK or repair can sync it.
6. FFmpeg and FFprobe checks pass.
7. yt-dlp check passes.
8. TTS status is ready if VieNeu Turbo bundle is present.
9. Validate sample JSON.
10. Export SRT only.
11. Render a 5-10 second local sample video.
12. Confirm `breaking_yellow` title header renders.
13. Confirm badge auto renders `BODYCAM`, `CASE FILE`, or `TRUE CRIME`.
14. Confirm subtitle is not covered by title header.
15. Confirm Blur Review can finalize.
16. Confirm Smart Cleanup keeps final video.
17. Uninstall app and verify output videos are not deleted.

## Beta Unsigned Note

The beta installer is unsigned. Windows SmartScreen may show a warning. End users may need to choose `More info` then `Run anyway`.

Do not auto-download executables at runtime in beta builds.
