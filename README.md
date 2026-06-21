# AI Video Rewriter & Video Rebuilder

## Giới thiệu

Hệ thống hỗ trợ tạo prompt Gemini, kiểm tra JSON đầu ra và tái dựng video bằng yt-dlp + FFmpeg + pysubs2. Kiến trúc EDL (Edit Decision List): Gemini trả `video_segments[]` với `sources[]`, mỗi segment gắn với subtitle index để hình ảnh luôn đồng bộ với phụ đề.

**RC-1 Status**: ✅ PASS — 155 tests, 5/5 phases validated, installer sẵn sàng.

## Tech Stack

| Layer | Công nghệ |
|---|---|
| Backend | FastAPI, Python 3.12+, SQLite, SQLAlchemy 2.0, Pydantic v2, Typer |
| Frontend | React 19, Vite 6, TypeScript, TailwindCSS |
| Video | FFmpeg, yt-dlp |
| Subtitle | pysubs2 (ASS format) |
| Test | pytest (backend, 155 tests), tsc + vite build (frontend) |
| Packaging | PyInstaller (portable Python), Inno Setup (installer) |
| TTS | VieNeu Turbo engine |

## Main Features (Phase A-E)

| Phase | Feature | Backend | Frontend |
|---|---|---|---|
| A | **Title Overlay Quality** | `title_layout.py` — 4 positions, 3 alignments, 4 font sizes | `TitleTool.tsx` — debounced preview + inline fallback |
| B | **Blur Tool UX** | `blur_tools.py` — keyframe model, normalize, interpolate | `BlurTool.tsx` — draggable timeline, keyboard shortcuts |
| C | **Subtitle Styles** | `subtitle_styler.py` — 6 ASS presets (default/shorts_bold/documentary/minimal/news/high_contrast) | `SubtitleStyleSelector.tsx` |
| D | **Prompt Telemetry** | `prompt_telemetry.py` — privacy-safe (no prompt_text), 7-day stats | `PromptTelemetryCard.tsx` |
| E | **Preset Recommendation** | `preset_recommender.py` — 14 keyword→preset rules, yt-dlp fallback | `PresetRecommendationCard.tsx` — 800ms debounce |

## Quick Start

### Backend

```powershell
# PowerShell (repo root)
$env:PYTHONPATH = "E:\AUTO_REVIEW\backend"
pip install -r backend/requirements.txt
uvicorn app.main:app --port 8007 --reload
```

Swagger UI: http://localhost:8007/docs

### Frontend (dev mode)

```powershell
cd frontend
npm install
npm run dev
```

Dev server: http://localhost:5173 (proxies API to backend)

### Build frontend cho production

```powershell
cd frontend
npm run build
# Output: frontend/dist/ — backend serve tự động
```

## Testing

```powershell
# Full backend test suite
python -m pytest tests/ -q

# Chạy test theo module
python -m pytest tests/test_title_layout.py -q    # 23 tests
python -m pytest tests/test_blur_tools.py -q      # 8 tests
python -m pytest tests/test_subtitle_styler.py -q # 17 tests
python -m pytest tests/test_prompt_telemetry.py -q # 11 tests
python -m pytest tests/test_preset_recommender.py -q # 19 tests
python -m pytest tests/test_license_service.py -q # 5 tests
python -m pytest tests/test_preset_service.py -q  # 10 tests
python -m pytest tests/test_render_pipeline.py -q # 18 tests
python -m pytest tests/test_json_validator.py -q  # 11 tests
python -m pytest tests/test_prompt_generator.py -q # 15 tests
python -m pytest tests/test_prompt_health.py -q   # 7 tests
python -m pytest tests/test_subtitle_generator.py -q # 1 test
python -m pytest tests/test_tts_tools.py -q       # 10 tests

# Frontend type-check + build
cd frontend; npm run build
```

## Packaging (Windows installer)

```powershell
# Stage portable package
.\packaging\package_windows.ps1 -Version "1.0.0-rc1"

# Compile Inno Setup installer (cần ISCC.exe)
ISCC.exe "packaging\inno\MrTris_AUTO.iss"

# Output: build\installer\MrTris_AUTO_Setup_v1.0.0_rc1.exe
```

Launcher (`mrtris_auto_launcher.py`) xử lý port fallback 8000-8004, DB init, browser auto-open.

## API Endpoints

Router prefix: `/api` (defined in `backend/app/main.py:33`). Full 40 routes below.

### Presets

| Method | Path | Mô tả |
|---|---|---|
| GET | `/presets` | List all presets (auto-seed builtin) |
| GET | `/presets/sync-status` | Trạng thái builtin sync |
| POST | `/presets/sync` | Force re-sync builtin |
| POST | `/presets/validate-conflicts` | Validate conflict rules |
| POST | `/presets` | Tạo custom preset |
| PUT | `/presets/{preset_id}` | Sửa preset (builtin bị chặn) |
| DELETE | `/presets/{preset_id}` | Xóa preset (builtin bị chặn) |

### Prompt / Telemetry / Recommendation

| Method | Path | Mô tả |
|---|---|---|
| POST | `/generate-prompt` | Generate prompt từ form + preset fields |
| POST | `/prompt/health-score` | Đánh giá chất lượng preset (0-100) |
| POST | `/prompt/recommend` | Gợi ý preset theo video title/URL |
| POST | `/prompt/runs` | Ghi telemetry (privacy-safe) |
| GET | `/prompt/runs/stats` | Thống kê telemetry 7 ngày |

### JSON Validation

| Method | Path | Mô tả |
|---|---|---|
| POST | `/validate-json` | Validate Gemini JSON EDL + auto-fix |
| POST | `/validate-json/strict` | Strict validation (reject extra fields) |

### Render

| Method | Path | Mô tả |
|---|---|---|
| POST | `/render` | Đồng bộ (cần `render` license) |
| POST | `/render-jobs` | Tạo async render job |
| GET | `/render-jobs` | Danh sách tất cả jobs |
| GET | `/render-jobs/{job_id}` | Poll trạng thái job |
| POST | `/render-jobs/{job_id}/cancel` | Hủy job |
| POST | `/render-jobs/{job_id}/blur/skip` | Bỏ qua blur, finalize |
| POST | `/render-jobs/{job_id}/blur/apply` | Apply blur + finalize |

### Title Layout

| Method | Path | Mô tả |
|---|---|---|
| POST | `/title/layout-preview` | Preview title (lines, badge, margins in px) |

### Blur

| Method | Path | Mô tả |
|---|---|---|
| POST | `/blur/upload-video` | Upload video cho Blur Tool |
| GET | `/blur/preview` | Stream preview video |
| POST | `/blur/render` | Apply blur regions (cần `blur` license) |

### TTS

| Method | Path | Mô tả |
|---|---|---|
| GET | `/tts/status` | Engine status |
| GET | `/tts/voices` | Danh sách preset voices |
| GET | `/tts/clones` | Danh sách cloned voices |
| POST | `/tts/clone/upload` | Upload audio tạo clone |
| POST | `/tts/clones/{clone_id}/preview` | Preview cloned voice |
| DELETE | `/tts/clones/{clone_id}` | Xóa clone |
| GET | `/tts/audio` | Stream/download TTS audio |

### License

| Method | Path | Mô tả |
|---|---|---|
| GET | `/license/status` | License status |
| POST | `/license/activate` | Activate key |
| POST | `/license/clear` | Clear local license |

### Cookies & App Settings

| Method | Path | Mô tả |
|---|---|---|
| POST | `/upload-cookies` | Upload YouTube cookies.txt |
| GET | `/app-settings/cookies` | Saved cookies metadata |
| DELETE | `/app-settings/cookies` | Xóa cookies |
| GET | `/app-settings/render-preferences` | Render preferences |
| PUT | `/app-settings/render-preferences` | Save render preferences |

### Storage

| Method | Path | Mô tả |
|---|---|---|
| GET | `/storage/stats` | Storage statistics (outputs + temp) |
| POST | `/storage/cleanup` | Cleanup files (temp/outputs/all) |

### Files & System

| Method | Path | Mô tả |
|---|---|---|
| POST | `/open-folder` | Open folder in OS explorer |
| GET | `/files/download` | Download file từ outputs |
| GET | `/runtime/health` | Health check (FFmpeg, node, yt-dlp, TTS) |

## Ví dụ JSON hợp lệ (Gemini EDL contract)

```json
{
  "metadata": {
    "video_title": "Video mẫu",
    "rewrite_style": "Viral",
    "target_audience": "Đại chúng",
    "tone": "Năng lượng cao",
    "target_duration": "1-3 phút",
    "target_language": "Tiếng Việt",
    "target_market": "Việt Nam",
    "localization_level": "medium",
    "adaptation_mode": "localized",
    "narrator_persona": "neutral_narrator"
  },
  "sources": [
    {
      "source_id": "src1",
      "youtube_url": "https://youtube.com/watch?v=...",
      "label": "Main source"
    }
  ],
  "rewrite_script": {
    "full_text": "Xin chào các bạn"
  },
  "srt": [
    {
      "index": 1,
      "start": "00:00:00,000",
      "end": "00:00:03,000",
      "text": "Xin chào các bạn"
    }
  ],
  "video_segments": [
    {
      "segment_id": 1,
      "order": 1,
      "source_id": "src1",
      "source_start": "00:00:00.000",
      "source_end": "00:00:03.000",
      "subtitle_start": 1,
      "subtitle_end": 1,
      "scene_description": "Đoạn mở đầu hấp dẫn",
      "importance_score": 95
    }
  ]
}
```

## Known Warnings (RC-1)

1. **videoTitle prop chưa wire**: `PresetRecommendationCard` nhận `videoTitle` + `youtubeUrl` props, nhưng `App.tsx` chỉ pass `youtubeUrl`. Component fallback về URL-only mode.
2. **README_USER.txt version**: Trong staged package (`build/package/MrTris_AUTO/`), file `README_USER.txt` ghi `1.0.0-beta` (cosmetic, non-functional).

## Key Docs

| File | Mô tả |
|---|---|
| `SYSTEM_DESIGN.md` | Kiến trúc chi tiết, data flow, API contract, DB schema |
| `ARCHITECTURE_DIAGRAM.md` | Sơ đồ Mermaid: components, sequences, deployment |
| `AGENTS.md` | Hướng dẫn AI agent: commands, constraints, release checklist |
| `review_preset.md` | Preset system: 15 built-in, 3-tier grouping, conflict rules |
| `backend/app/core/versions.py` | Version constants (single source of truth) |
