# SYSTEM DESIGN — AI Video Rewriter & Video Rebuilder

## 0. Purpose

This document is the Single Source Of Truth for the current system design. Any future code change must preserve or intentionally update this document first.

The system is an AI-assisted video rewriting and rebuilding tool. It generates Gemini prompts, validates Gemini JSON output, and renders a rebuilt video using an Edit Decision List (EDL) architecture.

---

## 1. Product Vision

The product helps users transform an original YouTube video into a rewritten, subtitle-synchronized, rebuilt video.

Core goals:

- Generate a structured prompt for Gemini.
- Require Gemini to act as both writer and video editor.
- Receive a strict JSON payload from Gemini.
- Validate the payload before rendering.
- Render video based on shot-level EDL decisions.
- Ensure visual segments and subtitles stay synchronized.

The current architecture intentionally replaces the old `clips[] + timeline[]` model with `video_segments[]` because clips can be much longer than subtitle ranges and cause visual/subtitle drift.

---

## 2. User Flow

1. User opens the React frontend.
2. User enters a YouTube URL.
3. User selects a preset or manually configures rewriting options.
4. User clicks **Xuất Prompt Gemini**.
5. Frontend calls `POST /api/generate-prompt`.
6. Backend returns a Gemini prompt.
7. User copies the prompt to Gemini.
8. Gemini returns JSON matching the EDL contract.
9. User pastes JSON into the frontend JSON Validator.
10. User validates JSON.
11. User clicks **Render Video**.
12. Frontend starts an async render job via `POST /api/render-jobs`.
13. Frontend polls `GET /api/render-jobs/{job_id}`.
14. Backend downloads source video, cuts segments, concatenates, creates subtitles, burns subtitles, and writes output artifacts.
15. User receives final output paths.

---

## 3. Data Flow

High-level data flow:

```text
User Config + YouTube URL
  -> PromptGenerateRequest
  -> PromptGenerator
  -> Gemini Prompt
  -> Gemini JSON EDL
  -> JsonValidator / Pydantic Models
  -> RenderJob
  -> RenderPipeline
  -> yt-dlp source video
  -> FFmpeg segment cuts
  -> FFmpeg concat
  -> SRT generation
  -> subtitle burn
  -> output artifacts
```

Persistent data:

- Presets are stored in SQLite.

Filesystem data:

- Temporary render workspaces are stored under `temp/`.
- Final render outputs are stored under `outputs/`.
- Logs are stored under `logs/`.

---

## 4. Prompt Builder Flow

Backend entry point:

- `POST /api/generate-prompt`

Request model:

- `PromptGenerateRequest`

Fields:

- `youtube_url`
- `preset_name`
- `rewrite_style`
- `target_audience`
- `tone`
- `target_duration`
- `retention_mode`
- `hook_style`
- `clip_strategy`
- `reuse_level`
- `content_density`

Service:

- `PromptGenerator.generate()`

Prompt requirements:

- Gemini must rewrite the script.
- Gemini must generate SRT.
- Gemini must act as a professional video editor.
- Gemini must return EDL in `video_segments[]`.
- Gemini must not return `clips[]` or `timeline[]`.
- Gemini must enforce max 2 seconds difference between video segment duration and subtitle range duration.

---

## 5. Gemini Integration Contract

Current integration mode:

- Manual copy/paste.
- Backend does not call Gemini directly.
- Backend generates a prompt for the user to use in Gemini.

Gemini output must be:

- Valid JSON only.
- Parseable by Python `json.loads()`.
- No Markdown.
- No triple backticks.
- No explanations.
- No comments.

Gemini role:

- Script writer.
- Subtitle generator.
- Professional video editor.
- EDL decision maker.

---

## 6. JSON Schema Contract

Root object:

```json
{
  "metadata": {},
  "sources": [],
  "rewrite_script": {},
  "srt": [],
  "video_segments": []
}
```

### metadata

```json
{
  "video_title": "",
  "rewrite_style": "",
  "target_audience": "",
  "tone": "",
  "target_duration": "",
  "target_language": "",
  "target_market": "",
  "localization_level": "",
  "adaptation_mode": "",
  "narrator_persona": ""
}
```

### sources[]

```json
{
  "source_id": "src1",
  "youtube_url": "https://youtube.com/watch?v=...",
  "local_video_path": null,
  "label": "Main source"
}
```

- `source_id`: unique identifier referenced by `video_segments[].source_id`.
- `youtube_url`: source YouTube link (used by yt-dlp downloader).
- `local_video_path`: alternative local file path (mutually exclusive with youtube_url).
- `label`: human-readable label for display.

### rewrite_script

```json
{
  "full_text": ""
}
```

### srt[]

```json
{
  "index": 1,
  "start": "00:00:00,000",
  "end": "00:00:08,000",
  "text": ""
}
```

Timestamp format:

- SRT timestamps use `HH:MM:SS,mmm`.

### video_segments[]

```json
{
  "segment_id": 1,
  "order": 1,
  "source_id": "src1",
  "source_start": "00:00:05.000",
  "source_end": "00:00:13.000",
  "subtitle_start": 1,
  "subtitle_end": 1,
  "scene_description": "",
  "importance_score": 95
}
```

Timestamp format:

- Source timestamps use `HH:MM:SS.mmm`.

---

## 7. Video Segment EDL Architecture

The system uses `video_segments[]` as the Edit Decision List.

Each segment is a precise editing decision:

- Which source video range to show.
- Which subtitle index or subtitle range it corresponds to.
- The segment order in the final video.

Rules:

1. `source_start < source_end`.
2. `subtitle_start <= subtitle_end`.
3. `subtitle_start` and `subtitle_end` must exist in `srt[]`.
4. `duration(source_start -> source_end)` must approximately equal `duration(subtitle_start -> subtitle_end)`.
5. Maximum allowed duration difference is 2 seconds.

Deprecated model:

- `clips[]`
- `timeline[]`

These must not be used in new payloads.

---

## 8. JSON Validator Architecture

Main service:

- `JsonValidator`

Model:

- `GeminiPayloadSchema`

Validation layers:

1. Pydantic field validation.
2. Timestamp format validation.
3. Segment range validation.
4. Subtitle reference validation.
5. Segment/subtitle duration comparison.

Auto-fix behavior:

- `validate_with_auto_fix()` first validates normally.
- If validation fails, `auto_fix_duration_mismatch()` attempts to align `source_end` with subtitle duration.
- If fixed payload validates, validation succeeds with an AUTO FIX warning.

Current limitation:

- Auto-fix only adjusts `source_end`.
- It does not yet split segments or find alternative visual ranges.

---

## 9. Video Renderer Architecture

Main pipeline:

- `RenderPipeline` (`backend/app/services/render_pipeline.py`)

Renderer components:

- `VideoDownloader`
- `VideoCutter`
- `VideoConcatenator`
- `SubtitleGenerator`
- `SubtitleBurner`
- `RenderOptions` — unified config object controlling all render behaviors

### RenderOptions

| Field | Type | Values | Description |
|---|---|---|---|
| `vertical_mode` | VerticalMode | `none`, `blur_fit`, `center_crop` | Handle vertical/wide source |
| `quality` | RenderQuality | `fast`, `balanced`, `high` | CRF encode quality |
| `output_resolution` | OutputResolution | `auto`, `720p`, `1080p` | Target resolution |
| `subtitle_mode` | SubtitleMode | `burn`, `srt_only`, `none` | Subtitle handling |
| `stability` | RenderStability | `fast`, `stable`, `max_quality` | Encoding stability |
| `video_encoder` | VideoEncoderMode | `auto`, `cpu`, `nvenc`, `qsv`, `amf` | HW encoding |
| `segment_fps` | SegmentFps | `auto`, `30`, `60` | Segment FPS |
| `blur_mode` | BlurMode | `none`, `review` | Blur processing mode |
| `tts_mode` | TtsMode | `none`, `voiceover` | TTS voiceover mode |
| `title_mode` | TitleMode | `none`, `auto`, `custom` | Title overlay mode |
| `title_style` | TitleStyle | 4 styles | Badge/line style |
| `subtitle_style` | SubtitleStyle | 6 styles | ASS style key |
| `original_audio_mode` | OriginalAudioMode | `lower_fixed`, `mute` | Background audio |
| `artifact_retention` | ArtifactRetention | `smart`, `keep_all` | Temp cleanup policy |

### Enhanced Render Steps

1. Create unique workspace under `temp/<job_id>/`.
2. Download/copy source video to `source.mp4`.
3. Cut each `video_segments[]` item into `segment_{segment_id}.mp4`.
4. Write `concat.txt` in segment order.
5. Concatenate segments into raw video.
6. Generate subtitle file from `srt[]`.
7. **Apply Title Overlay** if `title_mode != "none"` — uses `TitleLayoutEngine` to render ASS draw shapes (badge + header lines).
8. **Apply Blur Regions** if `blur_mode != "none"` — uses FFmpeg `geq` + `boxblur` filter on blur keyframe regions.
9. **Burn subtitle** if `subtitle_mode == "burn"` — uses `subtitle_styler` for ASS formatting.
10. **Apply TTS voiceover** if `tts_mode == "voiceover"` — generates via `TtsVoiceoverService`, mixes with original audio.
11. Write render plan JSON.
12. Return output paths.

### Subtitle Burn Order (Phase C integration)

```text
FFmpeg filter chain when subtitle_mode=burn:
  [video] -> drawtext? (watermark) -> ass (styled subtitles) -> [output]
```

Styled subtitles use pysubs2 to write `.ass` files, then FFmpeg `ass=` filter for burn-in. The `subtitle_styler` maps 6 presets to ASS `Style` definitions.

### Downloader quality strategy

```text
bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best
```

yt-dlp options:

- `--force-overwrites`
- `--no-continue`
- `--merge-output-format mp4`
- `--remux-video mp4`

### Output naming

```text
outputs/<safe_video_title>_<timestamp>/
  <safe_video_title>_raw.mp4
  <safe_video_title>_final.mp4
  <safe_video_title>_subtitle.srt
  <safe_video_title>_subtitle.ass       (styled subtitle when style != default)
  <safe_video_title>_render_plan.json
  <safe_video_title>_voiceover.mp3      (if TTS voiceover enabled)
  tts_plan.json                          (if TTS voiceover enabled)
  blur_regions.json                      (if blur regions applied)
```

---

## 9A. Title Overlay System (Phase A)

Service: `TitleLayoutEngine` (`backend/app/services/title_layout.py`)

### Layout computation

Given a `RenderOptions` with `title_mode != "none"`, the engine computes pixel-perfect title positions:

```
Positions:        Alignments:
  top              left
  upper_third      center
  center           right
  bottom
```

Font sizes: `auto`, `small`, `medium` (default), `large`

### Multi-line Y stacking

When title text is long, the engine splits into lines and stacks them vertically with configurable line gap (default 8px). Each line has its own background box drawn with ASS draw shapes (`m n l n b n s n` commands).

### Safe margins

Default 120px top (for YouTube info cards), 80px bottom (for subtitle area). Configurable via `safe_margin_px` / `header_height_px`.

### Preview API

`POST /api/title/layout-preview` returns pixel coordinates for each line and badge:

```json
{
  "lines": [{"text": "...", "x_px": 100, "y_px": 50, "width_px": 300, "height_px": 40, "font_size": 28, "font_color": "#FFFFFF", "has_background": true}],
  "badge": {"text": "REWRITTEN", "x_px": 100, "y_px": 10, ...},
  "safe_margin_px": 120,
  "header_height_px": 80
}
```

### Debounced frontend preview

`TitleTool.tsx` calls the preview API with 300ms debounce. If API unavailable, falls back to inline estimation using canvas `measureText()`.

---

## 9B. Blur Tool (Phase B)

Service: `BlurToolService` (`backend/app/services/blur_tools.py`)
Schema: `BlurRegion`, `BlurKeyframe` (`backend/app/schemas/render.py`)

### Keyframe model

Each blur region is defined by:
- `start` / `end` — time range in seconds
- `keyframes[]` — 1+ snapshots of the blur box at specific times
- `interpolate` — whether to smooth-interpolate between keyframes

Each `BlurKeyframe`:
- `time` — timestamp (seconds)
- `x`, `y` — normalized center (0.0-1.0)
- `width`, `height` — normalized size (0.0-1.0)
- `strength` — blur intensity (1-30, default 12)

### Normalization

All coordinate values are internally normalized to 0.0-1.0 before storage. The service provides `normalize_region()` and `denormalize_region(video_width, video_height)` helpers.

### Interpolation

When `interpolate=true`, keyframes are linearly interpolated to produce smooth box movement. `interpolate_keyframes(region, target_fps=30)` generates per-frame values.

### Render

FFmpeg filter: `geq` + `boxblur` applied per region. Multiple regions in overlapping time ranges are stacked.

### Frontend

`BlurTool.tsx` provides:
- Custom video controls (play/pause, seek)
- Draggable/resizable blur boxes over video canvas
- Add/delete keyframes on timeline
- Keyboard shortcuts: Space (play/pause), K (add keyframe), Delete (remove keyframe)

---

## 9C. Subtitle Styling System (Phase C)

Service: `SubtitleStyler` (`backend/app/services/subtitle_styler.py`)

### ASS Style Presets (6 styles)

| Key | Fontname | Fontsize | Outline | Shadow | BorderStyle | BackColour |
|---|---|---|---|---|---|---|
| `default` | Arial | 48 | 2 | 1 | 1 | `&H99000000` |
| `shorts_bold` | Arial | 52 | 4 | 2 | 1 | `&H99000000` |
| `documentary` | Tahoma | 42 | 2 | 1 | 1 | `&H99000000` |
| `minimal` | Arial | 36 | 0 | 0 | 0 | `&H00000000` |
| `news` | Tahoma | 46 | 2 | 1 | 1 | `&H99000000` |
| `high_contrast` | Arial | 50 | 5 | 3 | 1 | `&HBB000000` |

### Alignment mapping

```python
ALIGNMENT_MAP = {"bottom": 2, "center": 8, "top": 5}
```

### Integration

When `RenderOptions.subtitle_style` is set, `SubtitleStyler.create_styled_ass()` generates a `.ass` file instead of plain `.srt`. The subtitle burner then uses FFmpeg's `ass=` filter to burn the styled subtitles directly into the video.

---

## 9D. TTS Integration

Engine: **VieNeu Turbo** (`vieneu_turbo`)

### TTS Options (in RenderOptions)

| Field | Values | Default |
|---|---|---|
| `tts_mode` | `none`, `voiceover` | `none` |
| ~~`tts_language`~~ | ~~`auto`, `vi`, `en`, `vi_en`~~ | ~~`auto`~~ (removed — dead code, vendor auto-detects) |
| `tts_persona` | `neutral`, `sports_commentator`, `drama_storyteller`, `news_anchor`, `funny_reviewer`, `podcast_host` | `neutral` |
| `tts_voice_region` | `auto`, `vi_north`, `vi_south` | `auto` |
| `tts_voice_gender` | `auto`, `female`, `male` | `female` |
| `tts_voice_id` | `auto`, `ly`, `ngoc`, `tuyen`, `binh`, `doan`, `vinh` | `auto` |
| `tts_voice_mode` | `preset`, `clone` | `preset` |
| `tts_emotion` | `natural`, `storytelling` | `natural` |
| `tts_fit_policy` | `segment_uniform` | — |
| `tts_max_speed` | 1.0-2.0 | 1.5 |
| `tts_temperature` | 0.1-1.2 | 0.4 |
| `tts_top_k` | 1-200 | 50 |
| `tts_max_chars` | 80-600 | 256 |

### Pipeline integration

When `tts_mode == "voiceover"`:
1. Requires `tts` license (checked at render start)
2. During `_finalize_blur_job()`, `TtsVoiceoverService().generate_voiceover()` produces voiceover audio
3. `mix_voiceover()` blends voiceover with original audio
4. Output: `voiceover_path` + `tts_plan_path` in render result

---

## 10. API Contract

Base prefix:

```text
/api
```

### Presets

| Method | Path | Description |
|---|---|---|
| GET | `/presets` | List all presets (seeds built-in) |
| GET | `/presets/sync-status` | Get builtin sync status |
| POST | `/presets/sync` | Sync builtin presets |
| POST | `/presets/validate-conflicts` | Validate preset conflicts |
| POST | `/presets` | Create a new preset |
| PUT | `/presets/{preset_id}` | Update a preset |
| DELETE | `/presets/{preset_id}` | Delete a preset |

### Prompt / Telemetry / Recommendation

| Method | Path | Description |
|---|---|---|
| POST | `/generate-prompt` | Generate prompt text from form data |
| POST | `/prompt/health-score` | Score preset health |
| POST | `/prompt/recommend` | Recommend preset based on video title/URL |
| POST | `/prompt/runs` | Record prompt run telemetry (privacy-safe) |
| GET | `/prompt/runs/stats` | Get prompt run aggregate statistics |

### JSON Validation

| Method | Path | Description |
|---|---|---|
| POST | `/validate-json` | Validate Gemini JSON EDL payload (auto-fix) |
| POST | `/validate-json/strict` | Strict validation (reject extra fields) |

### Render

| Method | Path | Description |
|---|---|---|
| POST | `/render` | Synchronous render (requires `render` license) |
| POST | `/render-jobs` | Start async render job (queued) |
| GET | `/render-jobs` | List all render jobs |
| GET | `/render-jobs/{job_id}` | Get specific render job status |
| POST | `/render-jobs/{job_id}/cancel` | Cancel a render job |
| POST | `/render-jobs/{job_id}/blur/skip` | Skip blur and finalize |
| POST | `/render-jobs/{job_id}/blur/apply` | Apply blur regions and finalize |

### Title Layout

| Method | Path | Description |
|---|---|---|
| POST | `/title/layout-preview` | Get title layout preview (lines, badge, margins in px) |

### Blur

| Method | Path | Description |
|---|---|---|
| POST | `/blur/upload-video` | Upload video for blur processing |
| GET | `/blur/preview` | Stream/return blur preview video |
| POST | `/blur/render` | Apply blur regions (requires `blur` license) |

### TTS

| Method | Path | Description |
|---|---|---|
| GET | `/tts/status` | TTS engine status |
| GET | `/tts/voices` | List preset voices |
| GET | `/tts/clones` | List cloned voices |
| POST | `/tts/clone/upload` | Upload reference audio to create clone |
| POST | `/tts/clones/{clone_id}/preview` | Preview cloned voice |
| DELETE | `/tts/clones/{clone_id}` | Delete cloned voice |
| GET | `/tts/audio` | Stream/download TTS audio file |

### License

| Method | Path | Description |
|---|---|---|
| GET | `/license/status` | Get license status |
| POST | `/license/activate` | Activate license with key |
| POST | `/license/clear` | Clear local license |

### Storage / Cleanup

| Method | Path | Description |
|---|---|---|
| GET | `/storage/stats` | Storage statistics (outputs + temp) |
| POST | `/storage/cleanup` | Cleanup old files (temp/outputs/all) |

### Cookies / App Settings

| Method | Path | Description |
|---|---|---|
| POST | `/upload-cookies` | Upload YouTube cookies.txt |
| GET | `/app-settings/cookies` | Saved cookies metadata |
| DELETE | `/app-settings/cookies` | Delete saved cookies |
| GET | `/app-settings/render-preferences` | Get saved render preferences |
| PUT | `/app-settings/render-preferences` | Save render preferences |

### Files / System

| Method | Path | Description |
|---|---|---|
| POST | `/open-folder` | Open folder in OS file explorer |
| GET | `/files/download` | Download file from outputs dir |
| GET | `/runtime/health` | Full health check (FFmpeg, node, yt-dlp, TTS) |

### Render Job Response Schema

```json
{
  "job_id": "uuid",
  "status": "queued|running|done|error",
  "step": "Validate EDL|Download/Cut/Concat|Export result|Render",
  "message": "...",
  "result": {},
  "errors": []
}
```

Current limitation:

- Render jobs are stored in memory.
- Jobs are lost when backend restarts.

---

## 11. Frontend Architecture

Frontend stack:

- React
- Vite
- TypeScript
- TailwindCSS-like utility classes

Main files:

- `frontend/src/App.tsx`
- `frontend/src/api.ts`
- `frontend/src/types.ts`
- `frontend/src/styles.css`

UI areas:

1. Prompt Builder
2. JSON Validator
3. EDL Preview
4. Render Progress
5. Render Result
6. Preset Manager

Render UI flow:

1. Parse JSON.
2. Validate EDL.
3. Start render job.
4. Poll job status every 2 seconds.
5. Display done/error result.

---

## 12. Preset Architecture

### Preset System

Presets define reusable prompt configuration.

Built-in presets:

- Seeded at application startup.
- Cannot be deleted.

Custom presets:

- Created by user.
- Stored in SQLite.
- Can be updated/deleted.

Preset fields:

- `name`
- `description`
- `rewrite_style`
- `target_audience`
- `tone`
- `target_duration`
- `retention_mode`
- `hook_style`
- `clip_strategy`
- `reuse_level`
- `content_density`
- `is_builtin`
- `target_language`, `target_market`, `localization_level` (localization)
- `rename_characters`, `adapt_culture`, `adapt_currency`, `adapt_units`, `adapt_company_names`
- `adaptation_mode`, `narrator_persona`
- `preset_schema_version`, `prompt_template_version`, `json_output_schema_version`

### Prompt Builder (PromptBlocks + PromptComposer)

Directory: `backend/app/services/prompt_blocks/`

#### PromptBlock (ABC)

Abstract base class with method `render(data: PromptGenerateRequest) -> str`. Each block renders one section of the Gemini prompt.

| Block | Output section |
|---|---|
| `IntentBlock` | Preset name, rewrite style, audience, tone, duration |
| `StrategyBlock` | Retention mode, hook style, clip strategy, reuse level, content density |
| `LocalizationBlock` | Language, market, level, character renaming, culture/currency/units adaptation |
| `ValidationBlock` | Strict JSON format rules, field constraints, timestamp rules, EDL segment-subtitle matching |
| `OutputSchemaBlock` | Exact JSON output contract template for metadata/sources/rewrite_script/srt/video_segments |

#### PromptComposer

Orchestrator that assembles the full prompt from all blocks plus:
- Intro (role definition)
- Subtitle constraints
- Content quality guidelines
- Hook instruction
- Task description
- Alignment rules
- Domain-specific rules

### Prompt Health Score

Service: `PromptHealthScore` (`POST /api/prompt/health-score`)

Computes a 0-100 quality score based on:
- Field completeness (required preset fields)
- Field diversity (are values non-default?)
- Duration configuration validity
- Audience/tone alignment
- Localization configuration completeness

Levels: `excellent` (85-100), `good` (70-84), `risky` (50-69), `weak` (0-49)

### Prompt Reset / Clear

When user changes YouTube URL or switches preset, relevant form fields are reset:
- `youtube_url` → reset all youtube-dependent fields
- `preset_name` → reload preset values from database

---

## 13. Database Schema

Database:

- SQLite (file: `data/app.db`)
- SQLAlchemy ORM

### Table: `presets`

| Column | Type | Notes |
|---|---|---|
| `id` | String(64) | Primary key |
| `name` | String(255) | Unique, required |
| `description` | String(500) | Optional |
| `rewrite_style` | String(100) | Required |
| `target_audience` | String(100) | Required |
| `tone` | String(100) | Required |
| `target_duration` | String(100) | Required |
| `retention_mode` | String(100) | Required |
| `hook_style` | String(100) | Required |
| `clip_strategy` | String(100) | Required |
| `reuse_level` | String(100) | Required |
| `content_density` | String(100) | Required |
| `is_builtin` | Boolean | Default false |
| `target_language` | String(100) | Default "Tiếng Việt" |
| `target_market` | String(100) | Default "Việt Nam" |
| `localization_level` | String(50) | Default "medium" |
| `rename_characters` | Boolean | Default True |
| `adapt_culture` | Boolean | Default True |
| `adapt_currency` | Boolean | Default True |
| `adapt_units` | Boolean | Default True |
| `adapt_company_names` | Boolean | Default False |
| `adaptation_mode` | String(50) | Default "localized" |
| `narrator_persona` | String(100) | Default "drama_storyteller" |
| `preset_schema_version` | Integer | Versioned schema |
| `prompt_template_version` | Integer | Versioned template |
| `json_output_schema_version` | Integer | Versioned output schema |

### Table: `prompt_runs`

| Column | Type | Notes |
|---|---|---|
| `id` | String(64) | Primary key (UUID) |
| `created_at` | Float | Indexed, Unix timestamp |
| `status` | String(16) | Indexed: `success`, `error` |
| `prompt_chars` | Integer | Nullable, character count |
| `prompt_hash` | String(64) | Nullable, SHA-256 hex digest |
| `health_score` | Integer | Nullable, 0-100 |
| `health_level` | String(16) | Nullable: `excellent`, `good`, `risky`, `weak` |
| `error_message` | Text | Nullable |
| `preset_name` | String(255) | Indexed, nullable |
| `rewrite_style` | String(100) | Nullable |
| `duration_ms` | Float | Nullable, processing time |
| `form_snapshot_json` | Text | Nullable, sanitized form data |
| `preset_schema_version` | Integer | Nullable |
| `prompt_template_version` | Integer | Nullable |
| `json_output_schema_version` | Integer | Nullable |

**Note:** `prompt_text` is NEVER stored (privacy constraint). Only `prompt_chars` + `prompt_hash`.

### Table: `app_settings`

| Column | Type | Notes |
|---|---|---|
| `key` | String(100) | Primary key |
| `value_json` | Text | JSON-encoded value |
| `updated_at` | Float | Unix timestamp |

---

## 14. Error Handling Strategy

Validation errors:

- Converted to Vietnamese messages where possible.
- Returned as `errors[]`.

API errors:

- Use `HTTPException` for invalid requests.
- Render jobs store status `error` and error list.

Subprocess errors:

- yt-dlp and FFmpeg use `subprocess.run(..., check=True)`.
- Subtitle burn wraps FFmpeg stderr into a `RuntimeError`.

Frontend errors:

- Displayed in render result section.
- Render steps turn red on failure.

---

## 15. Logging Strategy

Current logging setup:

- Configured in `backend/app/core/logging.py`.
- Files:
  - `logs/download.log`
  - `logs/render.log`
  - `logs/validation.log`
  - `logs/error.log`

Current limitation:

- Logging is attached at root logger level.
- Service-specific structured logs are not yet fully implemented.

Recommended future logging:

- Log every render job lifecycle event.
- Log yt-dlp command outcome.
- Log FFmpeg command outcome.
- Log validation auto-fix decisions.
- Include `job_id`, `video_title`, `output_dir`, and `workspace_dir` in render logs.

---

## 16. Future Extension Strategy

Planned extensions:

1. Direct Gemini API integration.
2. Persistent render job table instead of in-memory job store.
3. Queue worker system such as Celery/RQ/Arq.
4. Advanced EDL auto-fix:
   - trim
   - split
   - extend
   - reassign neighboring segments
5. User-selectable download quality.
6. Video preview player in frontend.
7. Multi-source video support.
8. Structured observability dashboard.

Completed in RC-1:

- ✅ Artifact download endpoints (`GET /api/files/download`)
- ✅ Audio mixing and voiceover support (TTS integration, Phase D)
- ✅ Preset versioning (schema versions in `versions.py`)
- ✅ Preset recommendation engine (Phase E)

---

## 17. Prompt Telemetry System (Phase D)

Service: `PromptTelemetry` (`backend/app/services/prompt_telemetry.py`)

### Privacy-safe recording

| Field | Stored? | Purpose |
|---|---|---|
| `prompt_text` | **NEVER stored** | Privacy guarantee |
| `prompt_chars` | ✅ Stored | Character count (size metric) |
| `prompt_hash` | ✅ Stored | SHA-256 digest (dedup/anomaly detection) |

### Data sanitization

`_sanitize_form_data()` strips sensitive fields before storing `form_snapshot_json`:
- `youtube_url`
- `youtube_urls`  
- `ytdlp_cookies_file`

### Stats endpoint

`GET /api/prompt/runs/stats` returns 7-day window:

```json
{
  "total_runs": 154,
  "success_count": 150,
  "error_count": 4,
  "avg_health_score": 82.5,
  "top_presets": [
    {"key": "Review Công Nghệ", "count": 45},
    {"key": "TikTok Viral 60s", "count": 32}
  ],
  "top_rewrite_styles": [
    {"key": "Viral", "count": 60},
    {"key": "Chuyên gia phân tích", "count": 40}
  ],
  "daily_counts": [
    {"date": "2026-06-01", "count": 22},
    {"date": "2026-06-02", "count": 18}
  ],
  "last_7d_count": 154,
  "prev_7d_count": 120
}
```

### Error resilience

- Telemetry failure does NOT break prompt generation.
- Errors are caught, logged as warnings, and the prompt generation continues normally.

---

## 18. Preset Recommendation System (Phase E)

Service: `PresetRecommender` (`backend/app/services/preset_recommender.py`)

### Keyword→Preset rules (14 rules)

The recommender matches video title text against keyword patterns to suggest the most relevant preset:

| Title keywords | Recommended preset | Description |
|---|---|---|
| `review`, `unboxing`, `cong-nghe`, `smartphone`, `laptop`, `gadget`, `tech` | `Review Công Nghệ` | Technology reviews and unboxings |
| `viral`, `trend`, `shorts`, `tiktok`, `reels`, `xu-huong`, `meme`, `challenge` | `TikTok Viral 60s` | Short-form viral content |
| `review`, `shorts`, `sport`, `football`, `highlight`, `game`, `tournament` | `YouTube Shorts Review` | Short-form reviews + sports |
| `podcast`, `interview`, `phong-van`, `talk`, `discussion`, `episode` | `Podcast Tóm Tắt` | Podcast summaries |
| `documentary`, `tai-lieu`, `phong-su`, `explore`, `history`, `lich-su` | `Documentary Mini` | Short documentaries |
| `news`, `tin-tuc`, `thoi-su`, `current`, `ban-tin`, `headline` | `Tin Tức Nhanh` | Quick news updates |
| `drama`, `story`, `cau-chuyen`, `ke-chuyen`, `tale`, `plot`, `twist` | `Drama Kể Chuyện` | Story-driven dramatic content |
| `analysis`, `phan-tich`, `expert`, `chuyen-gia`, `deep-dive`, `insight` | `Phân Tích Chuyên Gia` | Expert analysis |
| `education`, `hoc`, `giao-duc`, `course`, `lesson`, `kien-thuc`, `tutorial` | `Content Giáo Dục` | Educational content |
| `finance`, `invest`, `stock`, `dau-tu`, `chung-khoan`, `crypto`, `bitcoin` | `Nhà Đầu Tư` | Financial analysis |
| `marketing`, `business`, `brand`, `startup`, `case-study`, `kinh-doanh` | `Marketing Case Study` | Business case studies |
| `funny`, `comedy`, `hai-huoc`, `mem`, `meme`, `humor`, `joke`, `reaction` | `Reaction Hài Hước` | Humorous reactions |
| `debate`, `argument`, `phan-bien`, `tranh-luan`, `opinion`, `goc-nhin` | `Tranh Luận/Góc Nhìn Trái Chiều` | Debates & opposing views |
| `bodycam`, `police`, `cops`, `crime`, `true-crime`, `hinh-su`, `canh-sat` | `US COPS Documentary` | Police / true crime |

### Fallback strategy

1. If video title is available: match via keyword rules → return best match with confidence score.
2. If only YouTube URL (no title): use yt-dlp to extract video info and get title → then apply keyword rules.
3. If yt-dlp fails or no match: return `null` (no recommendation).

### API flow

`POST /api/prompt/recommend`:
- Request: `{ youtube_url?: string, video_title?: string }`
- Response:
```json
{
  "title": "Video Title",
  "title_source": "provided|extracted|none",
  "recommendations": [
    {
      "preset_name": "Review Công Nghệ",
      "confidence": 0.9,
      "confidence_label": "strong",
      "matched_keywords": ["review", "smartphone"]
    }
  ]
}
```

### Frontend integration

- `PresetRecommendationCard.tsx` calls API with 800ms debounce on URL input change.
- Displays a suggestion card with preset name and match reason.
- "Apply" button sets the preset in the form.

---

## 19. License System

Service: `LicenseService` (`backend/app/services/license_service.py`)

### Features

- Offline activation with license key
- Local encrypted storage of license data
- Feature-gating: `render`, `youtube_download`, `tts`, `voice_clone`, `blur`
- Health check includes license status

### Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/license/status` | Current license status |
| POST | `/license/activate` | Activate with `{ license_key }` |
| POST | `/license/clear` | Clear local license data |

### Integration

- Render pipeline checks `render` license before starting.
- Blur render checks `blur` license.
- TTS clone upload checks `voice_clone` license.
- License failure → clear HTTP error response with descriptive message.

---

## 20. Packaging & Deployment

### Windows Portable Package

Script: `packaging/package_windows.ps1`

| Step | Component | Description |
|---|---|---|
| 1 | Backend tests | Runs `pytest tests/ -x -v` (unless `-SkipTests`) |
| 2 | Frontend build | Runs `npm run build` in frontend/ (unless `-SkipFrontendBuild`) |
| 3 | Copy sources | `backend/`, `frontend/dist/`, `packaging/launcher/`, `packaging/tools/` |
| 4 | Portable Python | Downloads embeddable Python 3.12.10 + installs requirements |
| 5 | Portable Node | Downloads Node 22.21.1 (for yt-dlp JS runtime) |
| 6 | FFmpeg | Copies ffmpeg.exe + ffprobe.exe |
| 7 | yt-dlp | Copies yt-dlp.exe |
| 8 | TTS models | Copies models/ + voices/ to runtime/tts/ |
| 9 | Launcher | Generates `MrTris_AUTO.py`, diagnostics, repair scripts |
| 10 | Security scan | Fails if private keys / keygen files leak into package |
| 11 | README_USER | Generates usage instructions |

### Launcher (`mrtris_auto_launcher.py`)

| Feature | Description |
|---|---|
| Port fallback | Tries 8000 → 8001 → ... → 8004 |
| Runtime validation | Checks 7 paths: backend main, frontend dist, python, node, yt-dlp, ffmpeg, ffprobe |
| Environment setup | AppData dirs, outputs, temp, logs, SQLite URL, FRONTEND_DIST_DIR, FFmpeg/yt-dlp PATH |
| Auto-init | SQLite DB creation + preset seeding (built-in presets) |
| Health wait | Polls `/api/runtime/health` every 1s, up to 45s timeout |
| Browser auto-open | Opens `http://127.0.0.1:<port>` on success |

### Inno Setup Installer

Script: `packaging/inno/MrTris_AUTO.iss`

- Compiles staged package into Windows installer `.exe`
- Installs to `%LOCALAPPDATA%\Programs\MrTris_AUTO`
- Creates desktop shortcut + Start Menu entry
- Output: `build\installer\MrTris_AUTO_Setup_v<version>.exe`

---

## 21. Known Limitations (RC-1)

### Functional

| Issue | Impact | Workaround |
|---|---|---|
| `videoTitle` prop in `PresetRecommendationCard` not wired from `App.tsx` | Component gets `youtubeUrl` only, not `videoTitle` | Component falls back to URL-only recommendation mode |
| Staged `README_USER.txt` version = `1.0.0-beta` | Cosmetic version mismatch | Rebuild with correct `-Version` parameter |
| Render jobs in-memory only | Jobs lost on backend restart | None |
| No direct Gemini API call | Manual copy/paste required | Future integration planned |

### Performance

| Area | Known limit | Note |
|---|---|---|
| yt-dlp download | Single-threaded, network-bound | Depends on source |
| Render pipeline | Sequential steps, no parallelization | Each step waits for previous |
| FFmpeg HW encoding | GPU encoder must be available | Falls back to CPU encoding |
| TTS generation | CPU-bound for voiceover generation | May add latency to renders |

---

## Change Control Rule

Before changing code behavior, update this document if the change affects:

- JSON contract
- EDL rules
- renderer behavior
- API contract
- frontend flow
- database schema
- error handling
- logging
- future extension assumptions
