# ARCHITECTURE DIAGRAMS

This document provides diagram-level views of the AI Video Rewriter & Video Rebuilder system.

Diagrams use Mermaid syntax.

---

## 1. Component Diagram

```mermaid
flowchart TB
    User[User]
    Browser[React Frontend]
    API[FastAPI Backend]
    Prompt[PromptGenerator]
    Validator[JsonValidator]
    JobManager[In-memory Render Job Manager]
    Pipeline[RenderPipeline]
    Downloader[VideoDownloader / yt-dlp]
    Cutter[VideoCutter / FFmpeg]
    Concat[VideoConcatenator / FFmpeg]
    Subs[SubtitleGenerator / pysubs2]
    Burner[SubtitleBurner / FFmpeg]
    DB[(SQLite app.db)]
    Temp[(temp/ workspaces)]
    Outputs[(outputs/ artifacts)]
    Logs[(logs/)]
    Gemini[Gemini]

    User --> Browser
    Browser --> API
    Browser -. copy prompt .-> Gemini
    Gemini -. JSON EDL .-> Browser

    API --> Prompt
    API --> Validator
    API --> JobManager
    API --> DB
    API --> Logs

    JobManager --> Pipeline
    Pipeline --> Downloader
    Pipeline --> Cutter
    Pipeline --> Concat
    Pipeline --> Subs
    Pipeline --> Burner

    Downloader --> Temp
    Cutter --> Temp
    Concat --> Outputs
    Subs --> Outputs
    Burner --> Outputs
```

---

## 2. Prompt Generation Sequence

```mermaid
sequenceDiagram
    actor User
    participant FE as React Frontend
    participant API as FastAPI
    participant PG as PromptGenerator
    participant Gemini

    User->>FE: Enter YouTube URL and prompt settings
    User->>FE: Click Generate Prompt
    FE->>API: POST /api/generate-prompt
    API->>PG: generate(PromptGenerateRequest)
    PG-->>API: prompt string
    API-->>FE: { prompt }
    FE-->>User: Show prompt
    User->>Gemini: Paste prompt
    Gemini-->>User: JSON EDL payload
    User->>FE: Paste JSON EDL
```

---

## 3. JSON Validation Sequence

```mermaid
sequenceDiagram
    actor User
    participant FE as React Frontend
    participant API as FastAPI
    participant Validator as JsonValidator
    participant Schema as GeminiPayloadSchema

    User->>FE: Paste Gemini JSON
    User->>FE: Click Validate JSON
    FE->>API: POST /api/validate-json
    API->>Validator: validate_with_auto_fix(payload)
    Validator->>Schema: model_validate(payload)

    alt valid
        Schema-->>Validator: parsed model
        Validator-->>API: valid=true
        API-->>FE: { valid: true, errors: [] }
    else duration mismatch fixable
        Validator->>Validator: auto_fix_duration_mismatch()
        Validator->>Schema: model_validate(fixed_payload)
        Schema-->>Validator: parsed model
        Validator-->>API: valid=true + AUTO FIX warning
        API-->>FE: { valid: true, errors: [AUTO FIX...] }
    else invalid
        Schema-->>Validator: validation errors
        Validator-->>API: valid=false + errors
        API-->>FE: { valid: false, errors: [...] }
    end
```

---

## 4. Async Render Job Sequence

```mermaid
sequenceDiagram
    actor User
    participant FE as React Frontend
    participant API as FastAPI
    participant Jobs as Render Job Manager
    participant Validator as JsonValidator
    participant Pipeline as RenderPipeline
    participant YTDLP as yt-dlp
    participant FFMPEG as FFmpeg
    participant FS as Filesystem

    User->>FE: Click Render Video
    FE->>API: POST /api/render-jobs
    API->>Jobs: create job_id status=queued
    API-->>FE: { job_id, status=queued }

    API->>Jobs: background task starts
    Jobs->>Validator: validate_with_auto_fix(payload)
    Validator-->>Jobs: parsed EDL or errors

    alt validation error
        Jobs->>Jobs: status=error step=Validate EDL
    else validation success
        Jobs->>Pipeline: render(payload, job_id)
        Pipeline->>FS: create temp/job workspace
        Pipeline->>YTDLP: download best quality source
        YTDLP->>FS: temp/job/source.mp4
        Pipeline->>FFMPEG: cut video_segments
        FFMPEG->>FS: temp/job/segments/*.mp4
        Pipeline->>FFMPEG: concat segments
        FFMPEG->>FS: outputs/.../*_raw.mp4
        Pipeline->>FS: write *_subtitle.srt
        Pipeline->>FFMPEG: burn subtitles
        FFMPEG->>FS: outputs/.../*_final.mp4
        Pipeline->>FS: write *_render_plan.json
        Pipeline-->>Jobs: result paths
        Jobs->>Jobs: status=done step=Export result
    end

    loop every 2 seconds
        FE->>API: GET /api/render-jobs/{job_id}
        API->>Jobs: read status
        Jobs-->>API: status/result/errors
        API-->>FE: RenderJobStatusResponse
        FE-->>User: Update progress UI
    end
```

---

## 5. Data Flow Diagram

```mermaid
flowchart LR
    A[YouTube URL + User Config] --> B[PromptGenerateRequest]
    B --> C[PromptGenerator]
    C --> D[Gemini Prompt]
    D --> E[Gemini]
    E --> F[JSON EDL]
    F --> G[JsonValidator]
    G --> H[GeminiPayloadSchema]
    H --> I[RenderJob]
    I --> J[RenderPipeline]
    J --> K[Source Video]
    K --> L[video_segments cuts]
    L --> M[Concatenated Raw Video]
    H --> N[SRT File]
    M --> O[Subtitle Burn]
    N --> O
    O --> P[Final Video]
    H --> Q[Render Plan JSON]

    P --> R[Output Directory]
    Q --> R
    N --> R
```

---

## 6. EDL Data Relationship

```mermaid
erDiagram
    GEMINI_PAYLOAD ||--|| METADATA : contains
    GEMINI_PAYLOAD ||--|| REWRITE_SCRIPT : contains
    GEMINI_PAYLOAD ||--o{ SRT_ITEM : contains
    GEMINI_PAYLOAD ||--o{ VIDEO_SEGMENT : contains

    SRT_ITEM {
        int index
        string start
        string end
        string text
    }

    VIDEO_SEGMENT {
        int segment_id
        int order
        string source_start
        string source_end
        int subtitle_start
        int subtitle_end
        string scene_description
        int importance_score
    }

    VIDEO_SEGMENT }o--o{ SRT_ITEM : references_by_subtitle_range
```

---

## 7. Preset Data Model

```mermaid
erDiagram
    PRESETS {
        string id PK
        string name UK
        string description
        string rewrite_style
        string target_audience
        string tone
        string target_duration
        string retention_mode
        string hook_style
        string clip_strategy
        string reuse_level
        string content_density
        boolean is_builtin
    }
```

---

## 8. Deployment View

```mermaid
flowchart TB
    subgraph LocalMachine[Local Machine]
        FE[Vite Dev Server / React]
        BE[Uvicorn / FastAPI]
        DB[(SQLite app.db)]
        FF[FFmpeg binary]
        YT[yt-dlp binary]
        OUT[(outputs/)]
        TMP[(temp/)]
        LOG[(logs/)]
    end

    FE --> BE
    BE --> DB
    BE --> FF
    BE --> YT
    BE --> OUT
    BE --> TMP
    BE --> LOG
```

---

## 9. Title Layout Sequence (Phase A)

```mermaid
sequenceDiagram
    actor User
    participant FE as TitleTool.tsx
    participant API as FastAPI
    participant Layout as TitleLayoutEngine
    participant Cache as LRU Cache

    User->>FE: Edit title text / position / font
    Note over FE: 300ms debounce
    FE->>API: POST /api/title/layout-preview
    API->>Layout: compute_layout(render_options, vw, vh)
    Layout->>Cache: check cache key
    alt Cache hit
        Cache-->>Layout: cached result
    else Cache miss
        Layout->>Layout: compute positions, lines, badge
        Layout->>Cache: store result
    end
    Layout-->>API: TitleLayoutPreviewResponse
    API-->>FE: { lines, badge, safe_margin_px, header_height_px }
    FE->>FE: render pixel-precise overlay on video preview
```

---

## 10. Blur Keyframe Sequence (Phase B)

```mermaid
sequenceDiagram
    actor User
    participant FE as BlurTool.tsx
    participant API as FastAPI
    participant Blur as BlurToolService
    participant FFMPEG as FFmpeg
    participant FS as Filesystem

    User->>FE: Upload video
    FE->>API: POST /api/blur/upload-video
    API->>FS: store uploaded file
    API-->>FE: { video_path }

    User->>FE: Pause at frame, draw blur box
    FE->>FE: Normalize coords (0-1)
    User->>FE: Add keyframe at time T
    FE->>FE: Store region = {start, end, keyframes: [{time,x,y,w,h,strength}], interpolate}

    User->>FE: Click Apply Blur
    FE->>API: POST /api/blur/render { regions, video_path }
    API->>Blur: normalize_regions()
    Blur->>FFMPEG: build boxblur filter chain
    FFMPEG->>FS: write blurred output
    Blur-->>API: render result
    API-->>FE: { output_path }
```

---

## 11. Subtitle Style Flow (Phase C)

```mermaid
flowchart LR
    A[RenderOptions.subtitle_style] --> B[SubtitleStyler]
    C[SRT entries] --> B
    B --> D[create_styled_ass]
    D --> E[ASS file with Style definitions]
    E --> F[FFmpeg ass= filter]
    G[Segment-concatenated video] --> F
    F --> H[Final video with styled subtitles]
```

---

## 12. Prompt Builder Flow (PromptComposer)

```mermaid
flowchart TB
    A[PromptGenerateRequest] --> B[PromptComposer]
    
    subgraph Blocks[Prompt Blocks]
        C[IntentBlock]
        D[StrategyBlock]
        E[LocalizationBlock]
        F[ValidationBlock]
        G[OutputSchemaBlock]
    end
    
    B --> C
    B --> D
    B --> E
    B --> F
    B --> G
    
    C --> H[Intro + Intent section]
    D --> H
    E --> H
    F --> I[Validation + Output Schema]
    G --> I
    
    H --> J[Full Gemini Prompt]
    I --> J
```

---

## 13. Prompt Telemetry Flow (Phase D)

```mermaid
flowchart LR
    A[Prompt Generated] --> B[PromptTelemetry.record_run]
    B --> C{Sanitize form data}
    C --> D[Strip: youtube_url, youtube_urls, ytdlp_cookies_file]
    D --> E[Compute prompt_hash SHA-256]
    D --> F[Count prompt_chars]
    E --> G[Write PromptRunORM to SQLite]
    F --> G
    G --> H{Success?}
    H -->|Yes| I[Return prompt to caller]
    H -->|No| J[Log warning, do NOT block]
    J --> I
```

---

## 14. Preset Recommendation Flow (Phase E)

```mermaid
sequenceDiagram
    actor User
    participant FE as PresetRecommendationCard
    participant API as FastAPI
    participant Rec as PresetRecommender

    User->>FE: Type/paste YouTube URL
    Note over FE: 800ms debounce
    FE->>API: POST /api/prompt/recommend { youtube_url }
    API->>Rec: recommend(youtube_url)

    alt has video_title
        Rec->>Rec: match keyword rules
        alt match found
            Rec-->>API: { title: "Video Title", title_source: "extracted", recommendations: [{ preset_name: "Review Công Nghệ", confidence: 0.9, confidence_label: "strong", matched_keywords: ["review"] }] }
        else no match
            Rec-->>API: { title: null, title_source: "none", recommendations: [] }
        end
    else URL only — no title
        Rec->>Rec: yt-dlp extract title
        Rec->>Rec: match keyword rules
        Rec-->>API: result
    end
    
    API-->>FE: recommendation result
    FE->>FE: show suggestion card
    User->>FE: Click Apply
    FE->>FE: set preset in form
```

---

## 15. Full Database Schema

```mermaid
erDiagram
    PRESETS {
        string id PK
        string name UK
        string description
        string rewrite_style
        string target_audience
        string tone
        string target_duration
        string retention_mode
        string hook_style
        string clip_strategy
        string reuse_level
        string content_density
        boolean is_builtin
        string target_language
        string target_market
        string localization_level
        boolean rename_characters
        boolean adapt_culture
        boolean adapt_currency
        boolean adapt_units
        boolean adapt_company_names
        string adaptation_mode
        string narrator_persona
        int preset_schema_version
        int prompt_template_version
        int json_output_schema_version
    }

    PROMPT_RUNS {
        string id PK
        float created_at
        string status
        int prompt_chars
        string prompt_hash
        int health_score
        string health_level
        string error_message
        string preset_name
        string rewrite_style
        float duration_ms
        string form_snapshot_json
        int preset_schema_version
        int prompt_template_version
        int json_output_schema_version
    }

    APP_SETTINGS {
        string key PK
        string value_json
        float updated_at
    }
```

---

## 16. Packaged Deployment View

```mermaid
flowchart TB
    subgraph AppDir[MrTris_AUTO]
        BACKEND[backend/]
        FRONTEND[frontend/dist/]
        LAUNCHER[MrTris_AUTO.py]
        DIAG[MrTris_AUTO_Diagnostics.py]
        
        subgraph Runtime[runtime/]
            PYTHON[python/ 3.12]
            NODE[node/ 22.21]
            FFMPEG[ffmpeg/]
            YTDLP[yt-dlp/]
            TTS[tts/ models + voices]
        end
    end
    
    subgraph AppData[%LOCALAPPDATA%\\MrTris_AUTO]
        DB[(data/app.db)]
        COOKIES[cookies/]
        TEMP[temp/]
        LOG[logs/]
    end
    
    subgraph Videos[%USERPROFILE%\\Videos\\AutoReview]
        OUTPUTS[outputs/]
    end

    LAUNCHER --> BACKEND
    LAUNCHER --> FRONTEND
    LAUNCHER --> PYTHON
    LAUNCHER --> NODE
    LAUNCHER --> FFMPEG
    LAUNCHER --> YTDLP
    LAUNCHER --> TTS
    BACKEND --> DB
    BACKEND --> COOKIES
    BACKEND --> TEMP
    BACKEND --> LOG
    BACKEND --> OUTPUTS
```
