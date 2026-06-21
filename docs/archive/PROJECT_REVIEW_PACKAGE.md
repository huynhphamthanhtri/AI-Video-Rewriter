# Project Review Package — AI Video Rewriter & Video Rebuilder

---

## Section 1 — Executive Summary

| Item | Value |
|---|---|
| **Product name** | MrTris AUTO (AI Video Rewriter & Video Rebuilder) |
| **Current version** | 1.0.0-rc1 |
| **Current status** | Release Candidate 1 — feature frozen, bug fixes only |
| **Target users** | YouTube content creators, video editors, social media producers |
| **Platform** | Windows (packaged installer). Backend serves frontend as SPA. |
| **Core value proposition** | Semi-automated video rewriting: user supplies YouTube URL + Gemini prompt, system downloads source, cuts/concatenates segments per EDL, burns styled subtitles, applies blur regions, overlays titles, mixes TTS voiceover, and outputs a rebuilt video — all on local hardware without cloud rendering. |
| **Main workflows** | (1) YouTube URL → Generate Prompt → Gemini → Paste JSON → Render. (2) Blur tool: upload video → place blur keyframes → render. (3) Preset recommendation: auto-detect content type from title. |
| **Major features** | Title overlay (4 positions, 3 alignments, 4 font sizes, multi-line stacking), Blur tool (keyframe-based, interpolatable regions, draggable timeline), Subtitle styling (6 ASS presets), Prompt telemetry (privacy-safe, 7-day stats), Preset recommendation (14 keyword rules, yt-dlp fallback), TTS voiceover (VieNeu Turbo, voice cloning), License enforcement (feature-gating), Async render jobs with progress polling. |

---

## Section 2 — Product Overview

### User problem

Content creators who repurpose YouTube videos face a manual, repetitive workflow:
1. Watch the source video.
2. Decide which segments to keep and in what order (EDL).
3. Rewrite the script for the target format.
4. Generate and time subtitles.
5. Apply visual effects (blur faces/logos, overlay titles).
6. Generate voiceover.
7. Render the final video.

Steps 1–3 are creative decisions that benefit from AI assistance (Gemini). Steps 4–7 are mechanical and should be automated.

### Solution

The system provides a semi-automated pipeline:
- **Prompt generation** — converts user preferences + preset into a structured Gemini prompt that outputs a strict JSON EDL.
- **Validation** — validates Gemini output against the EDL contract, with auto-fix for minor duration mismatches.
- **Rendering** — fully automated: download source, cut segments per EDL, concatenate, apply blur, overlay titles, style subtitles, mix TTS voiceover, encode final video.
- **Presets** — 15 built-in (Mặc Định, TikTok Viral 60s, Review Công Nghệ, Tin Tức Nhanh, etc.) + unlimited custom presets.
- **Recommendation** — auto-detects content type from video title or yt-dlp metadata and suggests the best preset.

### Typical user journey

```
YouTube URL
    ↓
[Enter URL + select preset]
    ↓
Generate Prompt  ──→  Copy prompt text
    ↓                      ↓
Gemini (external)  ←──  Paste into Gemini
    ↓
Gemini returns JSON EDL
    ↓
Paste JSON into validator
    ↓
Validate (auto-fix duration mismatches)
    ↓
Configure render options (blur, title, subtitles, TTS)
    ↓
Start render job
    ↓
Poll progress (every 2s)
    ↓
Download output video
```

---

## Section 3 — Tech Stack

| Layer | Technology | Version | Notes |
|---|---|---|---|
| **Backend Framework** | FastAPI | (latest) | Python 3.12+ async web framework |
| **Python** | CPython | 3.12.10 | Embeddable distribution for packaging |
| **ORM** | SQLAlchemy | 2.0 | Declarative mappings, FluentSession |
| **Validation** | Pydantic | v2 | `model_validate`, `Field` constraints |
| **Database** | SQLite | — | Single-file `data/app.db` |
| **Frontend Framework** | React | 19 | Functional components, hooks |
| **Build Tool** | Vite | 6 | Fast HMR, TypeScript transpilation |
| **TypeScript** | — | 5.x | Strict mode |
| **CSS** | TailwindCSS | 4+ | Utility-first |
| **Video Engine** | FFmpeg | system | Segment cut, concat, blur, subtitle burn, title overlay, speed change, encoding |
| **Downloader** | yt-dlp | latest | YouTube video/audio download with JS runtime (Node) |
| **Subtitle** | pysubs2 | — | ASS subtitle generation for styled burn-in |
| **TTS Engine** | VieNeu Turbo | — | Vietnamese-optimized neural TTS, voice cloning |
| **Packaging** | PyInstaller | — | Bundles Python runtime + dependencies |
| **Installer** | Inno Setup | 6.x | Windows installer (.exe) |
| **Testing** | pytest | — | 155 tests across 13 files |
| **License** | Custom offline activation | — | RSA-signed license keys, feature-gating |
| **Package runtime** | Node.js | 22.21.1 | Portable, for yt-dlp JS components |

---

## Section 4 — Repository Structure

```
E:\AUTO_REVIEW\
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py           # All 40+ API endpoints
│   │   ├── core/
│   │   │   ├── config.py           # AppSettings via pydantic-settings
│   │   │   ├── database.py         # SQLAlchemy engine + migrations
│   │   │   ├── logging.py          # Logging configuration
│   │   │   └── versions.py         # Schema version constants
│   │   ├── models/
│   │   │   ├── preset.py           # PresetORM (26 columns)
│   │   │   └── prompt_run.py       # PromptRunORM (15 columns)
│   │   ├── schemas/
│   │   │   ├── common.py           # Shared timestamp validators
│   │   │   ├── preset.py           # PresetBase, PresetRead (3-tier computed fields)
│   │   │   ├── prompt.py           # PromptGenerateRequest, PromptRun* schemas
│   │   │   └── render.py           # RenderOptions (50 fields), GeminiPayload, Blur*
│   │   ├── services/
│   │   │   ├── blur_tools.py       # BlurService — keyframe blur render
│   │   │   ├── license_service.py  # LicenseService — offline activation
│   │   │   ├── preset_recommender.py # 14-rule keyword recommender
│   │   │   ├── preset_service.py   # Preset CRUD + 15 built-in seeds
│   │   │   ├── prompt_blocks/      # PromptBlock ABC + 5 block implementations
│   │   │   ├── prompt_generator.py # PromptGenerator orchestrator
│   │   │   ├── prompt_telemetry.py # PromptRunService (privacy-safe recording)
│   │   │   ├── render_pipeline.py  # RenderPipeline — main render orchestrator
│   │   │   ├── subtitle_styler.py  # SubtitleStyler — 6 ASS style presets
│   │   │   ├── title_layout.py     # TitleLayoutEngine — pixel-precise title positioning
│   │   │   └── ...                 # VideoDownloader, VideoCutter, etc.
│   │   └── main.py                 # FastAPI app factory, router mount at /api
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx                 # Main app component
│   │   ├── api.ts                  # API client (fetch wrappers)
│   │   ├── types.ts                # TypeScript type definitions
│   │   ├── components/
│   │   │   ├── BlurTool.tsx        # Custom video controls + keyframe timeline
│   │   │   ├── EdlInspector.tsx    # EDL visualization
│   │   │   ├── PresetRecommendationCard.tsx  # Debounced recommendation UI
│   │   │   ├── PromptTelemetryCard.tsx       # Telemetry stats display
│   │   │   ├── SubtitleStyleSelector.tsx     # Style dropdown/selector
│   │   │   ├── TitleTool.tsx       # Title preview with debounced API
│   │   │   └── common.tsx          # Shared UI utilities
│   │   └── styles.css
│   └── dist/                       # Production build (served by backend)
├── tests/
│   ├── test_title_layout.py        # 23 tests
│   ├── test_preset_recommender.py  # 19 tests
│   ├── test_render_pipeline.py     # 18 tests
│   ├── test_subtitle_styler.py     # 17 tests
│   ├── test_prompt_generator.py    # 15 tests
│   ├── test_json_validator.py      # 11 tests
│   ├── test_prompt_telemetry.py    # 11 tests
│   ├── test_preset_service.py      # 10 tests
│   ├── test_tts_tools.py           # 10 tests
│   ├── test_blur_tools.py          # 8 tests
│   ├── test_prompt_health.py       # 7 tests
│   ├── test_license_service.py     # 5 tests
│   └── test_subtitle_generator.py  # 1 test
├── packaging/
│   ├── package_windows.ps1         # Build portable package (Python/Node/FFmpeg/yt-dlp)
│   ├── launcher/
│   │   └── mrtris_auto_launcher.py # Application launcher (port fallback, DB init)
│   └── inno/
│       └── MrTris_AUTO.iss         # Inno Setup installer definition
├── docs/
├── data/                           # SQLite database location
├── outputs/                        # Rendered video outputs
├── temp/                           # Temporary render workspaces
├── logs/                           # Application logs
├── build/                          # Build cache + staged package output
├── docker/                         # Docker configuration
├── scripts/                        # Utility scripts
├── AGENTS.md                       # Agent coding instructions
├── SYSTEM_DESIGN.md                # Single source of truth (system design)
├── ARCHITECTURE_DIAGRAM.md         # Mermaid diagrams
├── README.md                       # Onboarding documentation
└── review_preset.md                # Preset system documentation
```

---

## Section 5 — Architecture Overview

### High-level flow

```
Browser (React SPA on Vite dev server or dist/)
    │  HTTP REST
    ▼
FastAPI (Python 3.12+)
    │
    ├─── PromptGenerator ──── PromptBlocks (Intent, Strategy, Localization, Validation, OutputSchema)
    ├─── JsonValidator ────── GeminiPayloadSchema (Pydantic)
    ├─── PresetService ────── PresetORM (SQLite)
    ├─── PromptTelemetry ──── PromptRunORM (SQLite)
    ├─── PresetRecommender ── Keyword matching or yt-dlp fallback
    ├─── LicenseService ──── Encrypted license file
    │
    └─── RenderPipeline ──── (async via background thread)
         │
         ├── VideoDownloader   → yt-dlp → source.mp4
         ├── VideoCutter       → FFmpeg segment cuts
         ├── VideoConcatenator → FFmpeg concat
         ├── TitleLayoutEngine → ASS draw shapes
         ├── BlurService       → FFmpeg boxblur
         ├── SubtitleStyler    → pysubs2 → ASS file
         ├── TtsVoiceoverService → VieNeu Turbo
         └── RenderJobManager  → In-memory job state + polling
```

### Key services

| Service | File | Responsibility |
|---|---|---|
| `PromptGenerator` | `prompt_generator.py` | Orchestrates prompt block composition |
| `PromptComposer` | `prompt_blocks/composer.py` | Joins 5 blocks into final Gemini prompt |
| `JsonValidator` | `json_validator.py` | Validates Gemini JSON against EDL contract |
| `PresetService` | `preset_service.py` | CRUD + built-in seeding + conflict validation |
| `PresetRecommender` | `preset_recommender.py` | 14-rule keyword → preset matching |
| `PromptRunService` | `prompt_telemetry.py` | Privacy-safe telemetry recording |
| `RenderPipeline` | `render_pipeline.py` | Full render orchestration (download → output) |
| `TitleLayoutEngine` | `title_layout.py` | Pixel-precise title position computation |
| `BlurService` | `blur_tools.py` | Keyframe-based blur region FFmpeg rendering |
| `SubtitleStyler` | `subtitle_styler.py` | 6-style ASS generation |
| `TtsVoiceoverService` | `tts_service.py` | TTS voiceover generation + audio mixing |
| `LicenseService` | `license_service.py` | Offline activation, feature-gating |

---

## Section 6 — Database Schema

Database: **SQLite** (`data/app.db`), SQLAlchemy 2.0 ORM.

### Table: `presets`

**Purpose:** Store built-in + custom prompt presets (26 columns).

| Column | Type | Notes |
|---|---|---|
| `id` | String(64) PK | UUID or builtin slug |
| `name` | String(255) UK | Unique, required |
| `description` | String(500) | Default `""` |
| `rewrite_style` | String(100) | Required |
| `target_audience` | String(100) | Required |
| `tone` | String(100) | Required |
| `target_duration` | String(100) | Required |
| `retention_mode` | String(100) | Required |
| `hook_style` | String(100) | Required |
| `clip_strategy` | String(100) | Required |
| `reuse_level` | String(100) | Required |
| `content_density` | String(100) | Required |
| `target_language` | String(100) | Default `"Tiếng Việt"` |
| `target_market` | String(100) | Default `"Việt Nam"` |
| `localization_level` | String(50) | Default `"medium"` |
| `rename_characters` | Boolean | Default `True` |
| `adapt_culture` | Boolean | Default `True` |
| `adapt_currency` | Boolean | Default `True` |
| `adapt_units` | Boolean | Default `True` |
| `adapt_company_names` | Boolean | Default `False` |
| `adaptation_mode` | String(50) | Default `"localized"` |
| `narrator_persona` | String(100) | Default `"drama_storyteller"` |
| `is_builtin` | Boolean | Default `False` |
| `preset_schema_version` | Integer | Default `CURRENT_PRESET_SCHEMA_VERSION` (1) |
| `prompt_template_version` | Integer | Default `CURRENT_PROMPT_TEMPLATE_VERSION` (1) |
| `json_output_schema_version` | Integer | Default `CURRENT_JSON_OUTPUT_SCHEMA_VERSION` (1) |

### Table: `prompt_runs`

**Purpose:** Privacy-safe telemetry for prompt generation events (15 columns). `prompt_text` is NEVER stored.

| Column | Type | Notes |
|---|---|---|
| `id` | String(64) PK | UUID |
| `created_at` | Float (indexed) | Unix timestamp |
| `status` | String(16) (indexed) | `"success"`, `"error"` |
| `prompt_chars` | Integer | Character count (not text) |
| `prompt_hash` | String(64) | SHA-256 of prompt text |
| `health_score` | Integer | 0–100 |
| `health_level` | String(16) | `excellent`, `good`, `risky`, `weak` |
| `error_message` | Text | Error details |
| `preset_name` | String(255) (indexed) | Preset used |
| `rewrite_style` | String(100) | Style selected |
| `duration_ms` | Float | Processing time |
| `form_snapshot_json` | Text | Sanitized form data (sensitive fields stripped) |
| `preset_schema_version` | Integer | Version at time of run |
| `prompt_template_version` | Integer | Version at time of run |
| `json_output_schema_version` | Integer | Version at time of run |

### Table: `app_settings`

**Purpose:** Key-value store for application settings (3 columns).

| Column | Type | Notes |
|---|---|---|
| `key` | String(100) PK | Setting name |
| `value_json` | Text | JSON-encoded value |
| `updated_at` | Float | Unix timestamp |

---

## Section 7 — Render Pipeline

The render pipeline executes sequentially as a background thread. Each step produces intermediate files in `temp/<job_id>/`.

### Step 1: Validate EDL

| | |
|---|---|
| **Input** | Gemini EDL payload (JSON) |
| **Service** | `JsonValidator.validate_with_auto_fix()` |
| **Output** | Validated/auto-fixed `GeminiPayloadSchema` or error |
| **Auto-fix** | Aligns `source_end` to match subtitle duration if mismatch ≤ 2s |

### Step 2: Download source video

| | |
|---|---|
| **Input** | `sources[].youtube_url` |
| **Service** | `VideoDownloader` (wraps yt-dlp) |
| **Output** | `temp/<job_id>/source.mp4` |
| **Quality** | `bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best` |

### Step 3: Cut segments

| | |
|---|---|
| **Input** | `source.mp4` + `video_segments[]` |
| **Service** | `VideoCutter` (FFmpeg `-ss -to -c copy`) |
| **Output** | `temp/<job_id>/segments/segment_{id}.mp4` per segment |

### Step 4: Concatenate

| | |
|---|---|
| **Input** | All segment files |
| **Service** | `VideoConcatenator` (FFmpeg concat demuxer) |
| **Output** | `temp/<job_id>/concatenated_raw.mp4` |

### Step 5: Generate SRT

| | |
|---|---|
| **Input** | `srt[]` from EDL |
| **Service** | `SubtitleGenerator` (pysubs2) |
| **Output** | `temp/<job_id>/subtitles.srt` |

### Step 6: Apply blur regions (if `blur_mode != "none"`)

| | |
|---|---|
| **Input** | Concatenated video + `BlurRegion[]` |
| **Service** | `BlurService.apply_blur()` |
| **FFmpeg filter** | For each region interval: `crop=w:h:x:y, boxblur=strength:1, overlay=x:y` with keyframe interpolation |
| **Output** | `temp/<job_id>/blurred.mp4` |

### Step 7: Generate TTS voiceover (if `tts_mode == "voiceover"`)

| | |
|---|---|
| **Input** | `srt[].text` per segment |
| **Service** | `TtsVoiceoverService.generate_voiceover()` + `mix_voiceover()` |
| **Output** | `temp/<job_id>/voiceover.mp3` + `temp/<job_id>/tts_plan.json` |
| **Mix** | Blends voiceover with original audio at configurable volumes |

### Step 8: Overlay title (if `title_mode != "none"`)

| | |
|---|---|
| **Input** | Video + `RenderOptions.title_*` fields |
| **Service** | `TitleLayoutEngine` + ASS draw shapes |
| **FFmpeg filter** | `ass=` filter with dynamically generated ASS file containing badge + header lines |
| **Output** | `temp/<job_id>/titled.mp4` (or apply to blurred video) |

### Step 9: Burn styled subtitles (if `subtitle_mode == "burn"`)

| | |
|---|---|
| **Input** | Video + subtitle style |
| **Service** | `SubtitleStyler.srt_to_ass()` → styled `.ass` file |
| **FFmpeg filter** | `ass=subtitles_styled.ass` |
| **Output** | `temp/<job_id>/subtitled.mp4` |

### Step 10: Apply speed (if `video_speed != 1.0`)

| | |
|---|---|
| **Input** | Final video |
| **FFmpeg filter** | `setpts=PTS/{speed}` for video, `atempo={speed}` for audio |
| **Output** | `outputs/<title>_<timestamp>/<title>_final.mp4` |

### Step 11: Write artifacts

| Artifact | Location |
|---|---|
| Final video | `outputs/<title>_<timestamp>/<title>_final.mp4` |
| Raw concatenated video | `outputs/<title>_<timestamp>/<title>_raw.mp4` |
| Styled subtitles (ASS) | `outputs/<title>_<timestamp>/<title>_subtitle.ass` |
| Plain subtitles (SRT) | `outputs/<title>_<timestamp>/<title>_subtitle.srt` |
| TTS voiceover | `outputs/<title>_<timestamp>/<title>_voiceover.mp3` |
| Render plan (JSON) | `outputs/<title>_<timestamp>/<title>_render_plan.json` |
| Blur regions (JSON) | `outputs/<title>_<timestamp>/blur_regions.json` |

### Render options (50 fields)

Key render controls available through `RenderOptions`:

| Category | Fields |
|---|---|
| **Quality** | `render_quality` (fast/balanced/high), `output_resolution` (auto/720p/1080p), `render_stability` (fast/stable/max_quality) |
| **Video** | `vertical_mode` (none/blur_fit/center_crop), `video_encoder` (auto/cpu/nvenc/qsv/amf), `segment_fps` (auto/30/60), `video_speed` (1.0–1.5) |
| **Subtitle** | `subtitle_style` (6 presets), `subtitle_font_size`, `subtitle_position`, `subtitle_text_align`, `subtitle_outline`/`shadow`/`box` |
| **Title** | `title_mode` (none/auto/custom), `title_style` (4 styles), `title_font_size`, `title_position` (4), `title_badge_mode` (none/auto/custom) |
| **Blur** | `blur_mode` (none/review) |
| **TTS** | `tts_mode` (none/voiceover), 13 TTS sub-fields (language, persona, voice, emotion, speed, etc.) |
| **Audio** | `original_audio_mode` (lower_fixed/mute), `original_audio_volume`, `voiceover_volume` |
| **Cleanup** | `artifact_retention` (smart/keep_all) |

---

## Section 8 — Title System

### Service

`TitleLayoutEngine` in `backend/app/services/title_layout.py`

### Positions (4)

```
top         — Aligned to top of safe area
upper_third — Upper-third broadcast-style
center      — Centered vertically
bottom      — Above subtitle area
```

### Text alignments (3)

```
left    — Left-aligned
center  — Center-aligned
right   — Right-aligned
```

### Font sizes (4)

```
auto    — Automatic (based on video height)
small   — Small
medium  — Default
large   — Large
```

### Title styles (4)

| Style | Description |
|---|---|
| `yellow_highlight` | Yellow badge + white text, highlight style |
| `dark_badge` | Dark badge background, white text |
| `clean_white` | Minimal, white text, subtle outline |
| `breaking_yellow` | Breaking news style, bold yellow |

### Badge modes (3)

| Mode | Behavior |
|---|---|
| `none` | No badge |
| `auto` | Auto-generate badge text (e.g. "REWRITTEN", "REVIEW") |
| `custom` | Custom badge text from `title_badge_text` |

### Show duration (2)

| Mode | Behavior |
|---|---|
| `full` | Title visible for entire video |
| `intro_only` | Title visible only for first N seconds (`title_intro_seconds`) |

### Multi-line stacking

When title text exceeds `title_chars_per_line` (default 34), the engine wraps to additional lines up to `title_max_lines` (default 2, max 3). Lines stack vertically with configurable gap (default 8px). Each line and badge has individual background boxes drawn as ASS vector shapes.

### Preview API

`POST /api/title/layout-preview`

Request: `{ render_options, video_width, video_height, metadata? }`
Response: `{ lines: [{ text, x_px, y_px, font_size, width_px, height_px, has_background, background_color }], badge?, safe_margin_px, header_height_px }`

Frontend calls this with 300ms debounce. Falls back to inline canvas measurement if API unavailable.

### Known limitations

- No per-line styling (all lines share the same style).
- No animation (static position for duration of display).
- No word-level highlighting.

---

## Section 9 — Blur System

### Service

`BlurService` in `backend/app/services/blur_tools.py`

### Region model

A `BlurRegion` defines a time range during which blur is applied:

```python
class BlurRegion(BaseModel):
    start: float       # Start time in seconds
    end: float         # End time in seconds
    keyframes: list[BlurKeyframe]  # At least 1
    interpolate: bool  # Default False — smooth interpolation between keyframes
```

### Keyframe model

Each `BlurKeyframe` is a snapshot of the blur box at a specific time:

```python
class BlurKeyframe(BaseModel):
    time: float        # Timestamp in seconds (ge 0)
    x: float           # Normalized center X (0.0–1.0)
    y: float           # Normalized center Y (0.0–1.0)
    width: float       # Normalized width (0.0–1.0)
    height: float      # Normalized height (0.0–1.0)
    strength: int      # Blur intensity (1–30, default 12)
```

### Normalization

All coordinate values are normalized to 0.0–1.0 relative to video dimensions. The service provides normalization/denormalization helpers for frontend ↔ backend communication.

### Interpolation

When `interpolate=True`, keyframe positions and sizes are linearly interpolated to produce smooth box movement at `target_fps=30`.

### Rendering

FFmpeg filter chain per region:
```
For each unique time interval:
  crop=width:height:x:y, boxblur=strength:1, overlay=x:y
```

Multiple regions in overlapping time ranges are stacked.

### Frontend (`BlurTool.tsx`)

- Custom video controls (play/pause, seek)
- Draggable/resizable blur boxes overlaid on video canvas
- Add/delete keyframes on timeline
- Keyboard shortcuts: Space (play/pause), K (add keyframe), Delete (remove keyframe)

### Upload flow

1. `POST /api/blur/upload-video` — upload video file → returns `{ video_path, duration_seconds }`
2. `GET /api/blur/preview` — stream preview video for editing
3. `POST /api/blur/render` — apply blur regions → requires `blur` license

### Known limitations

- **No automatic face/object detection** — blur regions must be placed manually
- **No tracking** — keyframes must be set frame-by-frame; the system does not track moving objects
- **No OCR-based logo detection**
- Interpolation is linear only (no easing or bezier)
- Performance degrades with many overlapping regions

---

## Section 10 — Subtitle System

### Service

`SubtitleStyler` in `backend/app/services/subtitle_styler.py`

### ASS generation flow

```
SRT entries (from Gemini EDL)
    ↓
SubtitleStyler.srt_to_ass(srt_path, ass_path, options)
    ↓
Creates ASS file with:
  - [Script Info] section
  - [V4+ Styles] section with one Style definition
  - [Events] section with Dialogue lines
    ↓
FFmpeg ass= filter burns styled subtitles into video
```

### Available styles (6)

| Key | Label | Font | Size | Outline | Shadow | Style |
|---|---|---|---|---|---|---|
| `default` | Default | Arial | 48 | 2 | 1 | Background box |
| `shorts_bold` | Shorts Bold | Arial | 52 | 4 | 2 | Thick outline, bold |
| `documentary` | Documentary | Tahoma | 42 | 2 | 1 | Elegant |
| `minimal` | Minimal | Arial | 36 | 0 | 0 | No outline, no box |
| `news` | News | Tahoma | 46 | 2 | 1 | Clean, news-anchor |
| `high_contrast` | High Contrast | Arial | 50 | 5 | 3 | Maximum readability |

### Alignment mapping

```python
ALIGNMENT_MAP = {"bottom": 2, "center": 8, "top": 5}
```

### Per-subtitle controls (from RenderOptions)

| Option | Values | Default |
|---|---|---|
| `subtitle_style` | 6 presets | `"default"` |
| `subtitle_font_size` | `auto`, `small`, `medium`, `large` | `"auto"` |
| `subtitle_position` | `bottom`, `center`, `top` | `"bottom"` |
| `subtitle_text_align` | `center`, `left` | `"center"` |
| `subtitle_max_chars_per_line` | 20–80 | 40 |
| `subtitle_outline` | true/false | true |
| `subtitle_shadow` | true/false | false |
| `subtitle_box` | true/false | true |

---

## Section 11 — Prompt System

### 11.1 Presets

#### Built-in presets (15)

Seeded at startup via `PresetService.seed_builtin_presets()`. Stored in `presets` table with `is_builtin=True`. Cannot be deleted.

| ID | Name | Style | Tone | Duration |
|---|---|---|---|---|
| `builtin-mac-dinh` | Mặc Định | Storytelling | Thân thiện | 3-5 phút |
| `builtin-tiktok-viral-60s` | TikTok Viral 60s | Viral | Năng lượng cao | 1-3 phút |
| `builtin-youtube-shorts-review` | YouTube Shorts Review | Review chuyên sâu | Thân thiện | 1-3 phút |
| `builtin-review-cong-nghe` | Review Công Nghệ | Chuyên gia phân tích | Chuyên nghiệp | 5-10 phút |
| `builtin-podcast-tom-tat` | Podcast Tóm Tắt | Podcast | Thân thiện | 10-20 phút |
| `builtin-documentary-mini` | Documentary Mini | Documentary | Nghiêm túc | 5-10 phút |
| `builtin-tin-tuc-nhanh` | Tin Tức Nhanh | Tin tức | Chuyên nghiệp | 1-3 phút |
| `builtin-us-cops-documentary` | US COPS Documentary | Điều tra | Nghiêm túc | 5-10 phút |
| `builtin-reaction-hai-huoc` | Reaction Hài Hước | Hài hước | Hài hước | 3-5 phút |
| `builtin-drama-ke-chuyen` | Drama Kể Chuyện | Drama | Cảm xúc | 5-10 phút |
| `builtin-phan-tich-chuyen-gia` | Phân Tích Chuyên Gia | Chuyên gia phân tích | Chuyên nghiệp | 5-10 phút |
| `builtin-content-giao-duc` | Content Giáo Dục | Storytelling | Thân thiện | 5-10 phút |
| `builtin-nha-dau-tu` | Nhà Đầu Tư | Chuyên gia phân tích | Chuyên nghiệp | 5-10 phút |
| `builtin-marketing-case-study` | Marketing Case Study | Storytelling | Chuyên nghiệp | 3-5 phút |
| `builtin-tranh-luan-goc-nhin-trai-chieu` | Tranh Luận/Góc Nhìn Trái Chiều | Tranh luận | Năng lượng cao | 5-10 phút |

#### Custom presets

Created by user via `POST /api/presets`. Stored in same table with `is_builtin=False`. Full CRUD (built-in presets are protected from update/delete).

#### Versioning

Each preset has 3 version fields (single source of truth in `backend/app/core/versions.py`):

```python
CURRENT_PRESET_SCHEMA_VERSION: int = 1
CURRENT_PROMPT_TEMPLATE_VERSION: int = 1
CURRENT_JSON_OUTPUT_SCHEMA_VERSION: int = 1
```

### 11.2 Prompt Blocks

Located in `backend/app/services/prompt_blocks/`.

#### Architecture

```
PromptComposer
  ├── IntentBlock         → Preset name, style, audience, tone, duration
  ├── StrategyBlock       → Retention, hook, clip, reuse, density
  ├── LocalizationBlock   → Language, market, level, adaptation, persona
  ├── ValidationBlock     → Strict JSON rules, timestamp constraints
  └── OutputSchemaBlock   → Exact JSON output template
```

Each block implements the `PromptBlock` ABC with a single `render(data: PromptGenerateRequest) -> str` method.

`PromptComposer.compose()` assembles: intro → intent → strategy → localization → subtitle constraints → content quality → hook → task → alignment → domain rules → validation → output schema.

### 11.3 Health Score

**Endpoint:** `POST /api/prompt/health-score`

**Model:** `PromptHealthResponse { score: int, level: PromptHealthLevel, warnings: string[], strengths: string[] }`

**Levels:**

| Score Range | Level | Description |
|---|---|---|
| 85–100 | `excellent` | All fields well-configured |
| 70–84 | `good` | Minor improvement opportunities |
| 50–69 | `risky` | Notable gaps in configuration |
| 0–49 | `weak` | Significant missing or conflicting fields |

**Scoring factors:**
- **Strengths** (+10 each): specific hook, high retention, specialized audience, complete localization, non-default persona, specific rewrite_style
- **Warnings** (-10 each): conflict validator warnings, unselected duration, default tone

### 11.4 Preset Recommendation

**Endpoint:** `POST /api/prompt/recommend`

**Request:** `{ youtube_url?: string, video_title?: string }`
**Response:** `{ title: string|null, title_source: "provided"|"extracted"|"none", recommendations: PresetRecommendationItem[] }`

#### Recommendation rules (14 rules)

Matching is case-insensitive, matches against both title text and keywords.

| Keywords | Recommended preset |
|---|---|
| `review`, `unboxing`, `cong-nghe`, `smartphone`, `laptop`, `gadget`, `tech` | Review Công Nghệ |
| `viral`, `trend`, `shorts`, `tiktok`, `reels`, `xu-huong`, `meme`, `challenge` | TikTok Viral 60s |
| `review`, `shorts`, `sport`, `football`, `highlight`, `game`, `tournament` | YouTube Shorts Review |
| `podcast`, `interview`, `phong-van`, `talk`, `discussion`, `episode` | Podcast Tóm Tắt |
| `documentary`, `tai-lieu`, `phong-su`, `explore`, `history`, `lich-su` | Documentary Mini |
| `news`, `tin-tuc`, `thoi-su`, `current`, `ban-tin`, `headline` | Tin Tức Nhanh |
| `drama`, `story`, `cau-chuyen`, `ke-chuyen`, `tale`, `plot`, `twist` | Drama Kể Chuyện |
| `analysis`, `phan-tich`, `expert`, `chuyen-gia`, `deep-dive`, `insight` | Phân Tích Chuyên Gia |
| `education`, `hoc`, `giao-duc`, `course`, `lesson`, `kien-thuc`, `tutorial` | Content Giáo Dục |
| `finance`, `invest`, `stock`, `dau-tu`, `chung-khoan`, `crypto`, `bitcoin` | Nhà Đầu Tư |
| `marketing`, `business`, `brand`, `startup`, `case-study`, `kinh-doanh` | Marketing Case Study |
| `funny`, `comedy`, `hai-huoc`, `mem`, `meme`, `humor`, `joke`, `reaction` | Reaction Hài Hước |
| `debate`, `argument`, `phan-bien`, `tranh-luan`, `opinion`, `goc-nhin` | Tranh Luận/Góc Nhìn Trái Chiều |
| `bodycam`, `police`, `cops`, `crime`, `true-crime`, `hinh-su`, `canh-sat` | US COPS Documentary |

#### Confidence model

Each recommendation has:
- `confidence` (float): matching score based on keyword overlap
- `confidence_label`: `"strong"` | `"medium"` | `"weak"` | `"none"`
- `matched_keywords[]`: list of trigger keywords found in title

#### Fallback strategy

1. If `video_title` is provided: match via keyword rules.
2. If only `youtube_url`: use yt-dlp to extract title → match.
3. If yt-dlp fails or no match: return empty recommendations with `title_source: "none"`.

#### Frontend debounce

`PresetRecommendationCard.tsx` calls API with **800ms debounce** on URL input change. Displays suggestion card with Apply button.

### 11.5 Prompt Telemetry

**Service:** `PromptRunService` in `backend/app/services/prompt_telemetry.py`

#### Privacy model

| Data | Stored? | Rationale |
|---|---|---|
| `prompt_text` | **NEVER** | Privacy guarantee — content not saved |
| `prompt_chars` | ✅ | Character count for size metrics |
| `prompt_hash` | ✅ | SHA-256 for dedup/anomaly detection |
| `form_data` | ✅ (sanitized) | `_sanitize_form_data()` strips `youtube_url`, `youtube_urls`, `ytdlp_cookies_file` |

#### Stored telemetry fields

`id`, `created_at`, `status`, `prompt_chars`, `prompt_hash`, `health_score`, `health_level`, `error_message`, `preset_name`, `rewrite_style`, `duration_ms`, `form_snapshot_json`, 3 version fields.

#### Stats endpoint

`GET /api/prompt/runs/stats` returns 7-day window:

```json
{
  "total_runs": 154,
  "success_count": 150,
  "error_count": 4,
  "avg_health_score": 82.5,
  "top_presets": [{"key": "Review Công Nghệ", "count": 45}],
  "top_rewrite_styles": [{"key": "Viral", "count": 60}],
  "daily_counts": [{"date": "2026-06-01", "count": 22}],
  "last_7d_count": 154,
  "prev_7d_count": 120
}
```

#### Error resilience

Telemetry failure does NOT break prompt generation. Errors are caught, logged as warnings, and generation continues normally.

---

## Section 12 — API Summary

All routes are mounted at `/api` prefix (defined in `backend/app/main.py:33`). Total: **40+ endpoints**.

### Presets (7 endpoints)

| Method | Path |
|---|---|
| GET | `/presets` |
| GET | `/presets/sync-status` |
| POST | `/presets/sync` |
| POST | `/presets/validate-conflicts` |
| POST | `/presets` |
| PUT | `/presets/{preset_id}` |
| DELETE | `/presets/{preset_id}` |

### Prompt & Telemetry (5 endpoints)

| Method | Path |
|---|---|
| POST | `/generate-prompt` |
| POST | `/prompt/health-score` |
| POST | `/prompt/recommend` |
| POST | `/prompt/runs` |
| GET | `/prompt/runs/stats` |

### JSON Validation (2 endpoints)

| Method | Path |
|---|---|
| POST | `/validate-json` |
| POST | `/validate-json/strict` |

### Render (7 endpoints)

| Method | Path |
|---|---|
| POST | `/render` |
| POST | `/render-jobs` |
| GET | `/render-jobs` |
| GET | `/render-jobs/{job_id}` |
| POST | `/render-jobs/{job_id}/cancel` |
| POST | `/render-jobs/{job_id}/blur/skip` |
| POST | `/render-jobs/{job_id}/blur/apply` |

### Title (1 endpoint)

| Method | Path |
|---|---|
| POST | `/title/layout-preview` |

### Blur (3 endpoints)

| Method | Path |
|---|---|
| POST | `/blur/upload-video` |
| GET | `/blur/preview` |
| POST | `/blur/render` |

### TTS (7 endpoints)

| Method | Path |
|---|---|
| GET | `/tts/status` |
| GET | `/tts/voices` |
| GET | `/tts/clones` |
| POST | `/tts/clone/upload` |
| POST | `/tts/clones/{clone_id}/preview` |
| DELETE | `/tts/clones/{clone_id}` |
| GET | `/tts/audio` |

### License (3 endpoints)

| Method | Path |
|---|---|
| GET | `/license/status` |
| POST | `/license/activate` |
| POST | `/license/clear` |

### Cookies & App Settings (5 endpoints)

| Method | Path |
|---|---|
| POST | `/upload-cookies` |
| GET | `/app-settings/cookies` |
| DELETE | `/app-settings/cookies` |
| GET | `/app-settings/render-preferences` |
| PUT | `/app-settings/render-preferences` |

### Storage (2 endpoints)

| Method | Path |
|---|---|
| GET | `/storage/stats` |
| POST | `/storage/cleanup` |

### Files & System (3 endpoints)

| Method | Path |
|---|---|
| POST | `/open-folder` |
| GET | `/files/download` |
| GET | `/runtime/health` |

---

## Section 13 — Packaging & Deployment

### Package script

`packaging/package_windows.ps1` builds a portable distribution:

| Step | Detail |
|---|---|
| 1. Tests | Runs `pytest tests/ -x -v` (unless `-SkipTests`) |
| 2. Frontend build | `npm run build` in `frontend/` |
| 3. Copy sources | `backend/`, `frontend/dist/`, `packaging/launcher/`, `packaging/tools/` |
| 4. Portable Python | Downloads embeddable Python 3.12.10 zip → `runtime/python/`, installs requirements |
| 5. Portable Node | Downloads Node 22.21.1 → `runtime/node/` (for yt-dlp JS runtime) |
| 6. FFmpeg | Copies `ffmpeg.exe` + `ffprobe.exe` to `runtime/ffmpeg/` |
| 7. yt-dlp | Copies `yt-dlp.exe` to `runtime/yt-dlp/` |
| 8. TTS models | Copies `models/` + `voices/` to `runtime/tts/` |
| 9. Launcher | Generates `MrTris_AUTO.py`, diagnostics, repair scripts |
| 10. Security scan | Fails if private keys / keygen files found in package |
| 11. README_USER | Generates usage instructions |

### Launcher (`mrtris_auto_launcher.py`)

| Feature | Detail |
|---|---|
| Port fallback | Tries 8000 → 8001 → 8002 → 8003 → 8004 |
| Runtime validation | Checks 7 paths (backend main, frontend dist, python, node, yt-dlp, ffmpeg, ffprobe) |
| Environment | Creates `%LOCALAPPDATA%\MrTris_AUTO\{data, cookies, temp, logs}`, sets env vars |
| DB init | Creates SQLite DB + seeds built-in presets |
| Health check | Polls `GET /api/runtime/health` every 1s, 45s timeout |
| Browser | Auto-opens `http://127.0.0.1:<port>` on successful startup |

### Inno Setup installer

`packaging/inno/MrTris_AUTO.iss` → `build/installer/MrTris_AUTO_Setup_v1.0.0_rc1.exe`

- Installs to `%LOCALAPPDATA%\Programs\MrTris_AUTO`
- Desktop shortcut + Start Menu entry

### Docker

Alternative deployment via `docker-compose.yml` and `Dockerfile`. Not primary deployment path — primarily for development/testing.

---

## Section 14 — Testing

| Metric | Value |
|---|---|
| **Total tests** | **155** |
| **Test files** | 13 |
| **conftest.py** | None (uses `tmp_path` / `monkeypatch`) |
| **Frontend tests** | None (only build validation via `npm run build`) |

### Test coverage by area

| Test file | Tests | Area |
|---|---|---|
| `test_title_layout.py` | 23 | Title position, font size, multi-line, badge, edge cases |
| `test_preset_recommender.py` | 19 | Keyword matching, confidence, yt-dlp fallback, edge cases |
| `test_render_pipeline.py` | 18 | Full render flow, segment cut, concat, output structure |
| `test_subtitle_styler.py` | 17 | All 6 presets, ASS generation, alignment, edge cases |
| `test_prompt_generator.py` | 15 | Prompt assembly, all 5 blocks, field encoding |
| `test_json_validator.py` | 11 | EDL validation, auto-fix, cross-ref checking |
| `test_prompt_telemetry.py` | 11 | Record, stats, sanitization, privacy guarantees |
| `test_preset_service.py` | 10 | CRUD, built-in seeding, sync, conflict validation |
| `test_tts_tools.py` | 10 | TTS generation, voice listing, error handling |
| `test_blur_tools.py` | 8 | Region normalization, interpolation, filter generation |
| `test_prompt_health.py` | 7 | Health score computation, level thresholds |
| `test_license_service.py` | 5 | Activation, status, feature gating |
| `test_subtitle_generator.py` | 1 | Basic SRT generation |

---

## Section 15 — Performance Snapshot

> Note: No formal benchmarks exist. Numbers below are from code constants and runtime observations.

| Operation | Latency / Timeout | Notes |
|---|---|---|
| **Preset recommendation** | **5s timeout** (`RECOMMENDATION_TIMEOUT`) | Includes yt-dlp title extraction if only URL provided |
| **Health score** | Instant (<10ms) | Local computation only, no I/O |
| **Prompt generation** | <500ms | Measured via telemetry `duration_ms` field |
| **Layout preview** | <100ms | Local computation, light |
| **FFmpeg subprocess** | 20s timeout for checks | Version/health checks |
| **yt-dlp subprocess** | 20s timeout for checks | Version/health checks |
| **Blur upload rewrap** | 120s timeout | FFmpeg `+faststart` for MP4 |
| **Startup health wait** | **45s max** | Polls every 1s |
| **Render polling** | Every 2s | Frontend polls `GET /render-jobs/{id}` |
| **Full render** | **UNKNOWN** | Depends on source video length, resolution, blur/title/subtitle complexity, hardware (GPU vs CPU encoding). Ranges observed from 27s to 10min for sample videos. |
| **TTS generation** | **UNKNOWN** | CPU-bound, varies with voiceover duration |

---

## Section 16 — Known Limitations

### Functional

| Issue | Impact | Workaround |
|---|---|---|
| `videoTitle` prop in `PresetRecommendationCard` not wired from `App.tsx` | Component receives `youtubeUrl` only, not `videoTitle` | Falls back to URL-only recommendation (yt-dlp extracts title server-side) |
| Staged `README_USER.txt` version = `1.0.0-beta` | Cosmetic version mismatch in installer | Rebuild with correct `-Version` parameter |
| Render jobs stored in-memory only | Jobs lost on backend restart | None |
| No direct Gemini API call | Manual copy/paste required | Future integration planned |
| No automatic face/object detection for blur | Blur regions must be placed manually | — |
| No tracking for blur keyframes | Keyframes must be set frame-by-frame; no object tracking | — |
| No OCR-based logo detection | Logos must be blurred manually | — |
| Linear-only blur interpolation | No easing or bezier curves for smooth keyframe transitions | — |
| No per-line title styling | All title lines share same style | — |
| No title animation | Static position for title display duration | — |
| No word-level subtitle highlighting | Entire subtitle line shares same style | — |
| Recommendation keyword matching is simple | Rule-based, no NLP/LLM-based content classification | — |
| No multi-language subtitle support | SRT/ASS is single-language | — |

### Technical debt

| Area | Issue |
|---|---|
| **In-memory job store** | Jobs lost on restart; no persistence across backend sessions |
| **Sequential render pipeline** | No parallelization; each step waits for previous |
| **Single-threaded yt-dlp** | Download is network-bound, single-threaded |
| **No benchmark suite** | No formal performance benchmarks or regression tracking |
| **No frontend tests** | Frontend validated only via build (`npm run build`) |
| **No E2E tests** | No integration/E2E tests covering full user journey |
| **Subtitle generator testing** | Only 1 test for subtitle generator |
| **No structured logging** | Logging is file-based, not structured (JSON/syslog) |
| **No render job history** | No persistent table for historical render results |

### Security & compliance

| Area | Note |
|---|---|
| **License keys** | Offline activation with RSA signatures; keys are client-validated |
| **Telemetry privacy** | `prompt_text` explicitly NOT stored; sensitive fields stripped from form data |
| **Cookie storage** | YouTube cookies stored in `cookies/` directory; accessible via API |
| **No user auth** | Single-user desktop app; no multi-tenant authentication |

---

## Section 17 — Competitive Positioning

### Competitor landscape

| Product | Positioning | Strengths | Weaknesses |
|---|---|---|---|
| **CapCut** | Free all-in-one video editor | Automated captions, effects, templates; massive user base; cloud + desktop | Not focused on video rewriting/repurposing; limited Gemini-like AI integration |
| **OpusClip** | AI clip generator | Auto-highlight extraction; virality scoring; multi-platform export | No custom EDL control; limited subtitle styling; no blur/title overlay |
| **Vizard** | AI video repurposing | Auto-clipping, reframing, captions; social media optimization | Cloud-only; no local rendering; limited customization |
| **Submagic** | AI subtitle tool | High-quality auto-captions; emoji/styling; fast | Subtitle-only; no video editing, blur, or rendering pipeline |

### MrTris AUTO differentiators

| Strength | Detail |
|---|---|
| **Local rendering** | All processing happens on user's hardware. No cloud costs, no upload bandwidth, no privacy concerns about source video content. |
| **Full pipeline automation** | From YouTube URL to final rendered video: download, cut, concat, blur, title, subtitle, TTS, encode — all in one pipeline. |
| **EDL architecture** | Gemini acts as video editor, producing a structured edit decision list. User maintains creative control over segment selection. |
| **Preset system** | 15 built-in presets + custom presets encode complete content strategies (style, audience, tone, localization). |
| **Vietnamese-first TTS** | VieNeu Turbo engine with Vietnamese-optimized neural voices, regional accents (North/South), voice cloning. |
| **Offline licensing** | No always-on internet requirement. License is validated once, works offline thereafter. |
| **Keyframe blur** | Manual but precise keyframe-based blur with interpolation — unlike competitors that only offer auto face blur or static blur. |

### Weaknesses

| Weakness | Context |
|---|---|
| **Manual blur** | No automatic face/object detection. Competitors like CapCut offer auto face blur. |
| **No auto-clipping** | Unlike OpusClip/Vizard, user must define segments via EDL (no AI highlight extraction built-in). |
| **Single-user desktop** | No cloud sync, no team collaboration, no web UI. |
| **No mobile app** | Windows desktop only; no iOS/Android. |
| **No auto-captions** | Captions come from Gemini EDL, not from ASR (speech-to-text). |
| **Vietnamese-centric** | TTS, localization, and presets are optimized for Vietnamese content. English support exists but is not the primary focus. |

---

## Section 18 — Roadmap Candidates

> Items from `SYSTEM_DESIGN.md` §16 Future Extension Strategy and observed gaps. Not a new roadmap design.

### High ROI (from planned extensions)

1. **Direct Gemini API integration** — Eliminate manual copy/paste. Call Gemini API directly from backend with automatic retry and response validation.
2. **Persistent render job table** — Replace in-memory job store with SQLite-backed table. Survive backend restarts, enable job history.
3. **Advanced EDL auto-fix** — Beyond `source_end` adjustment: split segments, extend, reassign neighboring segments, trim.
4. **Video preview player in frontend** — Play rendered output in-browser before download.

### Medium ROI

5. **Queue worker system** (Celery/RQ/Arq) — Enable concurrent renders, priority queues, better resource management.
6. **User-selectable download quality** — Let user choose source video resolution for bandwidth/storage control.
7. **Multi-source video support** — Beyond single YouTube URL; multiple URLs, local files, playlists.

### Low ROI / Future

8. **Structured observability dashboard** — Metrics, log aggregation, render performance tracking.
9. **Render job history UI** — Browse past renders, re-download, re-render with different settings.
10. **Auto face/logo detection for blur** — Computer vision integration (OpenCV, MediaPipe) for automated blur region detection.
11. **Speech-to-text auto-captions** — Generate SRT from source audio via ASR, reducing dependency on Gemini for subtitle generation.
12. **Multi-language subtitle support** — Bilingual or multi-language subtitle tracks.
13. **Title animation** — Animated title entrance/exit, scrolling, typewriter effect.

---

## Section 19 — Important Files (40 files)

### Backend core (15 files)

| # | Path | Purpose |
|---|---|---|
| 1 | `backend/app/main.py` | FastAPI app factory. Mounts router at `/api`. |
| 2 | `backend/app/api/routes.py` | All 40+ API endpoint definitions. |
| 3 | `backend/app/core/config.py` | Pydantic-settings AppSettings. |
| 4 | `backend/app/core/database.py` | SQLAlchemy engine, session factory, migrations. |
| 5 | `backend/app/core/versions.py` | Schema version constants (single source of truth). |
| 6 | `backend/app/core/logging.py` | Logging configuration (file-based). |
| 7 | `backend/app/models/preset.py` | PresetORM — 26-column SQLAlchemy model. |
| 8 | `backend/app/models/prompt_run.py` | PromptRunORM — 15-column telemetry model. |
| 9 | `backend/app/schemas/preset.py` | PresetBase, PresetRead (3-tier computed fields), enums. |
| 10 | `backend/app/schemas/prompt.py` | PromptGenerateRequest, PromptRun*, PromptHealth* schemas. |
| 11 | `backend/app/schemas/render.py` | RenderOptions (50 fields), GeminiPayload, BlurRegion, Title* schemas. |
| 12 | `backend/app/schemas/common.py` | Shared timestamp validators (SRT, clip format). |
| 13 | `backend/app/services/render_pipeline.py` | Full render pipeline orchestrator. |
| 14 | `backend/app/services/prompt_generator.py` | Prompt generator (delegates to PromptComposer). |
| 15 | `backend/app/services/json_validator.py` | EDL validation + auto-fix. |

### Backend features (10 files)

| # | Path | Purpose |
|---|---|---|
| 16 | `backend/app/services/title_layout.py` | Title overlay position computation + ASS draw shape generation. |
| 17 | `backend/app/services/blur_tools.py` | Keyframe blur region FFmpeg filter generation. |
| 18 | `backend/app/services/subtitle_styler.py` | 6 ASS style preset definitions + SRT→ASS conversion. |
| 19 | `backend/app/services/preset_service.py` | Preset CRUD, built-in seeding (15 presets), conflict validation. |
| 20 | `backend/app/services/preset_recommender.py` | 14-rule keyword→preset recommendation engine. |
| 21 | `backend/app/services/prompt_telemetry.py` | Privacy-safe telemetry recording + stats queries. |
| 22 | `backend/app/services/license_service.py` | Offline license activation, verification, feature-gating. |
| 23 | `backend/app/services/prompt_blocks/composer.py` | PromptComposer — assembles all blocks into final prompt. |
| 24 | `backend/app/services/prompt_blocks/intent_block.py` | Intent section prompt block. |
| 25 | `backend/app/services/prompt_blocks/output_schema_block.py` | JSON output contract prompt block. |

### Frontend (8 files)

| # | Path | Purpose |
|---|---|---|
| 26 | `frontend/src/App.tsx` | Main React component; mounts all sub-components. |
| 27 | `frontend/src/api.ts` | API client functions (fetch wrappers). |
| 28 | `frontend/src/types.ts` | TypeScript type definitions. |
| 29 | `frontend/src/components/BlurTool.tsx` | Blur region editor: custom video controls, draggable boxes, keyframe timeline. |
| 30 | `frontend/src/components/TitleTool.tsx` | Title preview with 300ms debounced layout API. |
| 31 | `frontend/src/components/PresetRecommendationCard.tsx` | Debounced (800ms) recommendation suggestion card. |
| 32 | `frontend/src/components/SubtitleStyleSelector.tsx` | 6-style dropdown selector. |
| 33 | `frontend/src/components/PromptTelemetryCard.tsx` | Telemetry stats display. |

### Packaging & tools (7 files)

| # | Path | Purpose |
|---|---|---|
| 34 | `packaging/package_windows.ps1` | Build portable distribution (Python, Node, FFmpeg, yt-dlp). |
| 35 | `packaging/launcher/mrtris_auto_launcher.py` | App launcher: port fallback (8000-8004), DB init, browser open. |
| 36 | `packaging/inno/MrTris_AUTO.iss` | Inno Setup installer definition. |
| 37 | `docker-compose.yml` | Docker deployment config. |
| 38 | `Dockerfile` | Docker build definition. |

### Documentation (5 files)

| # | Path | Purpose |
|---|---|---|
| 39 | `SYSTEM_DESIGN.md` | Single source of truth for system architecture. |
| 40 | `README.md` | Onboarding documentation. |
| — | `ARCHITECTURE_DIAGRAM.md` | Mermaid component/sequence/deployment diagrams. |
| — | `AGENTS.md` | AI agent instructions (commands, constraints). |
| — | `review_preset.md` | Preset system deep-dive (15 built-in, 3-tier grouping, conflict rules). |

---

## Section 20 — Review Package Metadata

| Item | Value |
|---|---|
| **Project** | MrTris AUTO — AI Video Rewriter & Video Rebuilder |
| **Package file** | `PROJECT_REVIEW_PACKAGE.md` |
| **Prepared from** | Code audit + documentation review |
| **Source of truth** | Code at `E:\AUTO_REVIEW\backend` |
| **Build version** | `1.0.0-rc1` |
| **Release status** | Release Candidate 1 (feature frozen) |
| **Total tests** | 155 (13 files) |
| **API endpoints** | 40+ |
| **DB tables** | 3 (presets, prompt_runs, app_settings) |
| **Built-in presets** | 15 |
| **Recommendation rules** | 14 |
| **Subtitle styles** | 6 |
| **Frontend components** | 7 |
| **Installer** | Inno Setup (.exe) |
| **Package size** | UNKNOWN (depends on Python runtime + TTS models) |
| **Docs consistency status** | CONSISTENT (verified via 42-checkpoint audit) |
| **Review intended for** | Architecture Review, CTO Review, Product Review, Commercial Review, Technical Debt Review, Roadmap Planning, Scalability Review, UX Review |
