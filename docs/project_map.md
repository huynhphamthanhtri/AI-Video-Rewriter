# Project Map

## Root

| Path | Description |
|---|---|
| `backend/` | FastAPI Python backend |
| `frontend/` | React + Vite + TypeScript frontend |
| `tests/` | pytest test suite |
| `docs/` | Architecture, reports, harness |
| `scripts/` | Utility scripts: `install_tts.ps1`, `update_tool.ps1`, etc. |
| `packaging/` | Windows portable package + Inno Setup installer |
| `build/` | Output: staged package + installer |
| `data/` | Runtime data (Gemini session) |
| `outputs/` | Final rendered videos |
| `temp/` | Intermediate render artifacts |
| `logs/` | Log files |
| `skills/` | Task-specific agent harness guides |
| `plans/` | Plan templates |
| `reviews/` | Review checklists |
| `.venv312/` | Python virtual environment (dev) |
| `frontend/node_modules/` | NPM packages (dev) |

## Backend (`backend/`)

| Path | Description |
|---|---|
| `app/main.py` | FastAPI app factory: DB init, route mount, SPA serve |
| `app/api/routes.py` | All 60+ endpoints organized by feature |
| `app/api/deps.py` | FastAPI dependency injection |
| `app/core/config.py` | `Settings` pydantic-settings, env overrides |
| `app/core/database.py` | SQLAlchemy engine, session, migration helpers |
| `app/core/logging.py` | Logging configuration |
| `app/schemas/render.py` | `RenderOptions`, `GeminiPayloadSchema`, job request/response models, timestamp converters |
| `app/schemas/prompt.py` | Prompt generate, health, preview, run, recommendation, Gemini auto-submit schemas |
| `app/schemas/preset.py` | Preset CRUD, compare schemas |
| `app/schemas/batch.py` | Batch progress item/response schemas |
| `app/schemas/subtitle.py` | Subtitle preview style schemas |
| `app/schemas/common.py` | `MessageResponse`, timestamp utilities |
| `app/services/video_tools.py` | `RenderPipeline`, `VideoDownloader`, `VideoCutter`, `VideoConcatenator`, `SubtitleBurner`, `TitleOverlay`, encoder detection, FFmpeg wrappers |
| `app/services/gemini_automation.py` | `GeminiAutomationService`, `GeminiAutomationTask`, Playwright browser automation, selectors, state machine |
| `app/services/batch_pipeline.py` | `BatchPipelineService`: async multi-URL pipeline |
| `app/services/tts_tools.py` | `VieneuTurboSynthesizer`, `TtsVoiceoverService`, voice listing, clone management |
| `app/services/json_validator.py` | `JsonValidator`: EDL validation + auto-fix |
| `app/services/prompt_generator.py` | `PromptGenerator`: prompt assembly from blocks |
| `app/services/prompt_blocks/` | Prompt block modules: `intent`, `strategy`, `localization`, `voice`, `story_beat_budget`, `output_schema`, `validation`, `base`, `composer` |
| `app/services/prompt_health.py` | `score_preset_health()`: preset quality scoring (0–100) |
| `app/services/prompt_preview.py` | `PromptPreviewService`: preview text generation |
| `app/services/prompt_telemetry.py` | `PromptRunService`: privacy-safe telemetry |
| `app/services/preset_service.py` | `PresetService`: CRUD, seed, validate conflicts, sync |
| `app/services/preset_recommender.py` | `PresetRecommender`: ML-rule-based preset suggestion |
| `app/services/preset_compare.py` | `compare_presets()`: field-by-field comparison |
| `app/services/blur_tools.py` | `BlurService`: region keyframe model, FFmpeg blur filter |
| `app/services/title_layout.py` | Title position/size computation, font fallback |
| `app/services/subtitle_generator.py` | `SubtitleGenerator`: SRT generation from EDL |
| `app/services/subtitle_styler.py` | `SubtitleStyler`: 6 ASS style presets |
| `app/services/subtitle_preview.py` | Subtitle style preview image |
| `app/services/segment_planner.py` | `SegmentPlanner`: segment duration planning |
| `app/services/license_service.py` | Ed25519 offline license check, activate, hardware ID |
| `app/services/updater_service.py` | Version compare, manifest fetch, launcher trigger |
| `app/services/creator_dna.py` | Creator DNA profile loading |
| `app/services/fingerprint.py` | Browser fingerprint generation for Gemini |
| `app/services/app_settings.py` | Persisted app settings (cookies, render preferences) |
| `app/models/` | SQLAlchemy ORM models |
| `run_dev.py` | Dev server entry: uvicorn reload on port 8007 |
| `requirements.txt` | Core Python dependencies |
| `requirements-tts.txt` | Optional TTS dependencies (vieneu, llama-cpp-python, librosa) |
| `pyproject.toml` | Pytest config |

## Frontend (`frontend/`)

| Path | Description |
|---|---|
| `src/App.tsx` | Main component: state, tabs (`workflow|edl|blur|title|tts|presets|maintenance`), all feature handlers |
| `src/api.ts` | All backend API calls, mock mode via `VITE_USE_MOCK_API`, WebSocket helper |
| `src/types.ts` | TypeScript types for all backend models, `RenderOptions`, `Preset`, `GeminiEdlPayload`, etc. |
| `src/components/common.tsx` | Shared UI: `Card`, `Pill`, `SectionTitle`, `Stat` |
| `src/components/BlurTool.tsx` | Video blur region editor with canvas overlay, drag handles, keyframe timeline |
| `src/components/TitleTool.tsx` | Title layout preview tool |
| `src/components/TtsPanel.tsx` | TTS configuration panel: voice selection, persona, emotion, volume, clone manager |
| `src/components/TtsCloneManager.tsx` | Clone voice upload/preview/delete UI |
| `src/components/SubtitleGallery.tsx` | Subtitle style preview gallery |
| `src/components/SubtitleStyleSelector.tsx` | Subtitle style picker |
| `src/components/SubtitlePreviewCard.tsx` | Single subtitle preview card |
| `src/components/AutoPipelineProgress.tsx` | Auto pipeline step-by-step progress UI |
| `src/components/BatchPipelineProgress.tsx` | Batch pipeline progress per item |
| `src/components/PresetCompareCard.tsx` | Preset comparison display |
| `src/components/PresetRecommendationCard.tsx` | Preset recommendation card |
| `src/components/PromptTelemetryCard.tsx` | Prompt run telemetry stats |
| `src/components/PromptPreviewCard.tsx` | Prompt preview display |
| `src/components/EdlInspector.tsx` | EDL payload viewer |
| `src/constants/options.ts` | Dropdown options for localization, switches, preset names, option groups |
| `src/schemas/geminiJson.ts` | Zod EDL schema for client-side validation |
| `src/utils/time.ts` | Timestamp formatting (`fmt`, `parseClipTime`, `parseSrtTime`) |
| `src/utils/download.ts` | `downloadTextFile` helper |
| `src/main.tsx` | React entry point |
| `src/styles.css` | Global CSS with Tailwind |
| `public/fonts/` | Outfit font files |
| `vite.config.ts` | Vite config |
| `tsconfig.json` | TypeScript config |
| `tailwind.config.js` | Tailwind CSS config |
| `postcss.config.js` | PostCSS config |
| `package.json` | NPM dependencies |

## Tests (`tests/`)

| File | Tests | Focus |
|---|---|---|
| `test_render_pipeline.py` | 18 | FFmpeg pipeline, segment cut, concat, ETA, quality |
| `test_json_validator.py` | 11 | EDL validation rules, auto-fix |
| `test_prompt_generator.py` | 15 | Prompt assembly, all blocks |
| `test_prompt_health.py` | 7 | Health scoring, level detection |
| `test_preset_service.py` | 10 | Preset CRUD, builtin seeding, conflict validation |
| `test_preset_recommender.py` | 19 | Keyword → preset rules |
| `test_preset_compare.py` | – | Preset comparison |
| `test_blur_tools.py` | 8 | Blur region keyframe model |
| `test_title_layout.py` | 23 | Title position/size computations |
| `test_subtitle_styler.py` | 17 | ASS style generation |
| `test_subtitle_preview.py` | – | Subtitle preview |
| `test_subtitle_generator.py` | 1 | SRT generation |
| `test_tts_tools.py` | 10 | TTS cue planning, duration estimation |
| `test_voice_duration_pipeline.py` | – | Voice duration pipeline |
| `test_voice_duration_mock_e2e.py` | – | Mock end-to-end TTS flow |
| `test_voice_block.py` | – | Prompt voice block |
| `test_license_service.py` | 5 | License check, activate, hardware ID |
| `test_updater.py` | – | Update manifest parsing |
| `test_batch_pipeline.py` | – | Batch pipeline orchestration |
| `test_gemini_login_state.py` | – | Gemini login state detection |
| `test_frontend_gemini_browser_smoke.py` | – | Playwright browser E2E |
| `test_frontend_batch_smoke.py` | – | Frontend + batch smoke |
| `test_creator_dna.py` | – | Creator DNA loading |
| `test_prompt_preview.py` | – | Prompt preview |
| `test_prompt_health_details.py` | – | Health detail factors |
| `test_prompt_telemetry.py` | 11 | Telemetry recording |

## Packaging (`packaging/`)

| Path | Description |
|---|---|
| `package_windows.ps1` | Build staged portable package: Python embed, Node.js, FFmpeg, yt-dlp, TTS, app source |
| `launcher/mrtris_auto_launcher.py` | Production launcher: port fallback, DB init, browser auto-open, diagnostics logging |
| `launcher/` | Launcher source |
| `tools/diagnostics.py` | Diagnostics script for customer support |
| `tools/repair.py` | Repair script |
| `inno/MrTris_AUTO.iss` | Inno Setup installer script |
| `README_PACKAGING.md` | Packaging workflow, runtime layout, smoke tests, keygen rules |
