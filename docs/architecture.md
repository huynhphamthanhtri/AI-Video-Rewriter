# Kiến trúc

Hệ thống được chia thành các service độc lập: `PromptGenerator`, `JsonValidator`, `VideoDownloader`, `VideoCutter`, `VideoConcatenator`, `SubtitleGenerator`, `SubtitleBurner`, `RenderPipeline`, `PresetService`.

Kiến trúc cho phép thay thế lớp AI provider trong tương lai mà không ảnh hưởng pipeline dựng video.

## Runtime Topology

- Backend: FastAPI app served via uvicorn (`backend/run_dev.py` port 8007, or `app/main.py`).
- Frontend: Vite dev server on port 5173 in dev, or built into `frontend/dist/` served by FastAPI.
- Database: SQLite via SQLAlchemy 2.0 (`backend/app.db` in dev, or `%LOCALAPPDATA%\MrTris_AUTO\data\app.db` packaged).
- External tools: FFmpeg, ffprobe, yt-dlp (on PATH or bundled in `runtime/`).
- TTS engine: VieNeu Turbo (optional, `scripts/install_tts.ps1`).
- Gemini: Playwright-based Chromium automation.

## Backend Composition

| Layer | Location | Role |
|---|---|---|
| Entry + SPA mount | `backend/app/main.py` | `create_app()` — mounts router at `/api`, serves `frontend/dist/`, seeds presets, creates DB tables |
| Routes | `backend/app/api/routes.py` | ~60 endpoints organized by feature (presets, prompt, render, blur, TTS, Gemini, storage, update) |
| Schemas | `backend/app/schemas/` | Pydantic v2 request/response models: `render.py`, `prompt.py`, `preset.py`, `batch.py`, `subtitle.py`, `common.py` |
| Services | `backend/app/services/` | Feature logic, FFmpeg wrappers, Gemini automation, TTS synthesis, license, updater |
| Config | `backend/app/core/config.py` | `Settings` pydantic-settings class, env overridable via `MRTRIS_AUTO_*` vars |
| Database | `backend/app/core/database.py` | SQLAlchemy engine, session, migration helpers |
| CLI | `backend/app/cli.py` | (Planned/reserved for admin commands) |

### Render Job Model

Render jobs are stored in-memory (`render_jobs: dict[str, dict]` with `Lock`), not in DB. Lifecycle: `queued -> running -> waiting_blur -> done | error | cancelled`. ETA computed from phase-based plan.

### Gemini Automation

`GeminiAutomationService` manages Playwright tasks with `GeminiAutomationTask` state machine (init, browser, navigate, login, submit, wait, extract, validate, retry, render). Status pushed via WebSocket at `/api/gemini/status/{task_id}`.

## Frontend Composition

| File | Role |
|---|---|
| `src/App.tsx` | Main UI — state, tabs, orchestrator for all features |
| `src/api.ts` | Fetch wrappers for all backend endpoints, mock support |
| `src/types.ts` | TypeScript types mirroring backend Pydantic schemas |
| `src/components/*.tsx` | Feature panels: BlurTool, TitleTool, TtsPanel, SubtitleGallery, AutoPipelineProgress, BatchPipelineProgress, etc. |
| `src/constants/options.ts` | Preset/option dropdown values |
| `src/schemas/geminiJson.ts` | Zod schema for Gemini EDL JSON validation |
| `src/utils/time.ts` | Timestamp formatting utilities |

Tabs: `workflow | edl | blur | title | tts | presets | maintenance`.

## EDL / Shot-based editing

Video Rebuilder V2 dùng Edit Decision List thay cho thiết kế `clips[]` + `timeline[]` cũ.

### Payload chính

```json
{
  "metadata": {},
  "rewrite_script": { "full_text": "" },
  "srt": [
    { "index": 1, "start": "00:00:00,000", "end": "00:00:08,000", "text": "" }
  ],
  "video_segments": [
    {
      "segment_id": 1,
      "order": 1,
      "source_start": "00:00:05.000",
      "source_end": "00:00:13.000",
      "subtitle_start": 1,
      "subtitle_end": 1,
      "scene_description": "",
      "importance_score": 95
    }
  ]
}
```

### Luồng render

1. `JsonValidator` validate payload EDL.
2. Nếu lệch duration, `validate_with_auto_fix()` thử điều chỉnh `source_end` theo duration subtitle.
3. `SubtitleGenerator` sinh SRT từ `srt[]`.
4. `VideoCutter` cắt từng `video_segments[].source_start/source_end` thành `segment_{id}.mp4`.
5. `VideoConcatenator` ghép segment theo `order`.
6. `SubtitleBurner` burn subtitle nếu được bật.

### Validation rules

- `source_start < source_end`.
- `subtitle_start <= subtitle_end`.
- `subtitle_start/subtitle_end` phải tồn tại trong `srt[]`.
- `duration(video_segment)` phải gần bằng `duration(subtitle_range)`, sai số tối đa 2 giây.

## Storage & Runtime Layout

| Path | Purpose |
|---|---|
| `backend/` | Python source |
| `frontend/dist/` | Built SPA (auto-served if present) |
| `outputs/` | Final render videos |
| `temp/` | Intermediate artifacts (segments, TTS audio, blur videos) |
| `logs/` | Log files |
| `data/` | Gemini session JSON |
| `build/package/MrTris_AUTO/` | Staged portable package |
| `build/installer/` | Final Inno Setup installer `.exe` |
| `frontend/node_modules/` | NPM deps (dev only) |

In packaged mode (`MRTRIS_AUTO_PACKAGED=1`):
- User data → `%LOCALAPPDATA%\MrTris_AUTO`
- Output videos → `%USERPROFILE%\Videos\AutoReview`
- DB → `%LOCALAPPDATA%\MrTris_AUTO\data\app.db`

## External Tools

- **FFmpeg**: Required for all video operations (cut, concat, encode, blur, subtitle burn, TTS mix).
- **ffprobe**: Metadata probe, audio duration check.
- **yt-dlp**: YouTube/online video download.
- **Playwright/Chromium**: Gemini automation.
- **VieNeu Turbo**: Optional TTS engine via `vieneu` Python package.

## Packaging Boundary

Packaging is Windows-only via `packaging/package_windows.ps1` + Inno Setup. The launcher (`mrtris_auto_launcher.py`) handles port fallback (8000–8004), DB init, and auto-open browser. Private license keys must never be included.
