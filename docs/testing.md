# Testing

## Backend

Run all backend tests from repo root:

```powershell
python -m pytest tests/ -q
```

Run specific test file:

```powershell
python -m pytest tests/test_tts_tools.py -q -v
```

Generate coverage:

```powershell
python -m pytest tests/ --cov=backend/app --cov-report=term
```

### Feature Test Matrix

| Feature | Test File | Count | Notes |
|---|---|---|---|
| Render pipeline | `test_render_pipeline.py` | 18 | Mocks FFmpeg calls where possible |
| JSON validation | `test_json_validator.py` | 11 | EDL rules, auto-fix |
| Prompt generator | `test_prompt_generator.py` | 15 | All blocks, edge cases |
| Prompt health | `test_prompt_health.py` | 7 | Score levels |
| Preset service | `test_preset_service.py` | 10 | CRUD, builtin seeding |
| Preset recommender | `test_preset_recommender.py` | 19 | Keyword mapping |
| Blur tools | `test_blur_tools.py` | 8 | Region keyframe model |
| Title layout | `test_title_layout.py` | 23 | Position, size, margin calcs |
| Subtitle styler | `test_subtitle_styler.py` | 17 | 6 ASS presets |
| TTS tools | `test_tts_tools.py` | 10 | Cue planning, duration |
| License service | `test_license_service.py` | 5 | Activate, hardware ID |
| Prompt telemetry | `test_prompt_telemetry.py` | 11 | Recording, stats |
| Subtitle generator | `test_subtitle_generator.py` | 1 | SRT output |
| Batch pipeline | `test_batch_pipeline.py` | – | Orchestration |
| Gemini login state | `test_gemini_login_state.py` | – | Selector detection |

Browser-based (require Playwright + Gemini account):

```powershell
python -m pytest tests/test_frontend_gemini_browser_smoke.py -v
python -m pytest tests/test_frontend_batch_smoke.py -v
```

## Frontend

Type-check and build:

```powershell
cd frontend
npm run build
```

This runs `tsc -b` and `vite build`. Type errors fail the build.

Dev server (no build validation):

```powershell
cd frontend
npm run dev
```

## Packaging Smoke

```powershell
build\package\MrTris_AUTO\runtime\ffmpeg\ffmpeg.exe -version
build\package\MrTris_AUTO\runtime\python\python.exe -c "import fastapi, uvicorn, vieneu; print('ok')"
```

## When Not To Run Heavy Tests

- Skip tests that require Gemini accounts (browser smoke tests) during CI/CD without credentials.
- Voice duration pipeline tests may require VieNeu Turbo installed.
- Packaging tests require FFmpeg on PATH.
