# Workflows

## Prompt Generation

1. User fills form in Workflow tab (`App.tsx`).
2. `handleGeneratePrompt` calls `POST /api/generate-prompt`.
3. `PromptGenerator` assembles blocks (intent, strategy, localization, voice, story_beat_budget, output_schema, validation) into prompt text.
4. Returns generated prompt (not submitted to Gemini yet).

## JSON Validation

1. User pastes Gemini JSON or imports from file.
2. `handleValidate` calls `POST /api/validate-json`.
3. `JsonValidator` checks structure, timestamp alignment, duration match, auto-fixes if needed.
4. On success, EDL payload is stored in state for rendering.

## Manual Render

1. User has validated JSON payload and configured render options.
2. `startRenderJob` calls `POST /api/render-jobs`.
3. Backend creates in-memory job (queued), background worker runs `RenderPipeline`.
4. Steps: validate → download sources → cut segments → concat → transform → TTS → burn subtitle → speed → export.
5. Poll `GET /api/render-jobs/{job_id}` for progress and ETA.
6. If blur_mode == "review", job pauses at "waiting_blur" for user review.
7. User reviews/applies/skips blur via Blur Tool tab.
8. Final video written to `outputs/`.

## Auto Pipeline (Gemini → Render)

1. User clicks "Auto Pipeline" in Workflow tab.
2. `POST /api/gemini/auto-submit` creates `GeminiAutomationTask`.
3. Playwright opens `gemini.google.com`, submits prompt, waits for response, extracts JSON.
4. If JSON invalid, retries up to `gemini_retry_count` times.
5. On valid JSON, creates render job automatically.
6. Progress pushed via WebSocket `/api/gemini/status/{task_id}`.
7. Frontend `AutoPipelineProgress` shows step-by-step states.

## Batch Multi-YouTube Pipeline

1. User provides multiple YouTube URLs.
2. `POST /api/gemini/batch-auto-submit` starts `BatchPipelineService`.
3. For each URL sequentially: generate prompt → auto-submit to Gemini → wait for JSON → submit render job → poll render completion.
4. Progress tracked per URL item.
5. All items run within one batch context. Cancel affects entire batch.

## TTS Voiceover Duration Planning

1. During render, if `tts_mode == "voiceover"`:
2. `TtsVoiceoverService` generates `TtsCuePlan` per SRT item.
3. For each cue: synthesize TTS audio, probe duration, apply speed adjustment to fit slot.
4. Mix with original audio (lower_fixed or mute).
5. Final audio track blended into output video.

## Blur Review

1. Render job reaches "waiting_blur" status.
2. Backend produces intermediate video (`pre_blur_video_path`).
3. User opens Blur Tool tab with review workspace.
4. User adds blur regions, adjusts keyframes, then:
   - "Apply blur and continue" → `POST /api/render-jobs/{job_id}/blur/apply`
   - "Skip blur, continue final" → `POST /api/render-jobs/{job_id}/blur/skip`
5. Job proceeds to final export.

## Packaging Windows Installer

1. Run `packaging\package_windows.ps1` from repo root.
2. Script: runs backend tests, builds frontend, downloads Python embed + Node.js, copies FFmpeg/yt-dlp, TTS packages, stages all files under `build\package\MrTris_AUTO`.
3. Run ISCC.exe with `packaging\inno\MrTris_AUTO.iss` to build installer `.exe`.
4. Installer output: `build\installer\MrTris_AUTO_Setup_v1.0.0_beta.exe`.
