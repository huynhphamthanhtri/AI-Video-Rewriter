# Batch Multi-YouTube Sequential Pipeline Build Report

## Phase 2 - Design

### Approval
- User approved proceeding despite RC feature freeze.
- Reason: this is an isolated, user-approved feature required for current validation.

### Scope Controls
- Preserve existing single-video Auto Pipeline path.
- Single URL continues to call existing `POST /gemini/auto-submit`.
- Multiple URLs use new batch-only endpoints.
- No database schema changes.
- No WebSocket handler changes.
- No manual render changes.
- No SegmentPlanner or TTS voice-duration logic changes.
- No browser reuse in this phase; each item uses existing `gemini_service.start()`.

### API Design
- `POST /gemini/batch-auto-submit`
  - Starts a new batch from `form_data.youtube_urls`.
  - Returns `batch_id`, `status`, and initial item states.
- `GET /gemini/batch/{batch_id}`
  - Returns full batch progress.
- `POST /gemini/batch/{batch_id}/cancel`
  - Best-effort cancellation of current item and marks pending items cancelled.

### Batch State
- Batch fields: `batch_id`, `status`, `total_items`, `current_index`, `items`, `started_at`, `ended_at`, `error`.
- Item fields: `index`, `source_url`, `status`, `task_id`, `job_id`, `states`, `result`, `error`, `started_at`, `ended_at`.
- Batch status values: `pending`, `running`, `done`, `error`, `cancelled`.
- Item status values: `pending`, `running`, `done`, `error`, `cancelled`.

### Sequential Execution Rules
- Run one item at a time only.
- Do not start item N+1 until item N reaches render `done`, `error`, or `cancelled`.
- If one item errors, mark only that item error and continue the next item.
- Batch is `done` if all items are processed and at least one item succeeded.
- Batch is `error` only if all processed items failed, or a fatal batch-level error occurs.
- Batch is `cancelled` if user cancels before completion.

### Frontend Design
- Existing single URL behavior remains unchanged.
- `handleAutoPipeline()` detects URL count.
- One URL: use existing `startAutoPipeline()`.
- Multiple URLs: use new `startBatchAutoPipeline()` and poll `fetchBatchProgress()`.
- New `BatchPipelineProgress` component displays overall batch status and per-item progress.

### Required Validation
- Backend tests for creation, sequential execution, error continuation, cancellation, and old auto-submit regression.
- Frontend build.
- Smoke/E2E checks for single URL old path, multiple URL batch path, error continuation, cancel batch, and manual render unaffected.

## Phase 3 - Implementation

### Backend Implementation
- Added `backend/app/schemas/batch.py` for batch and item progress response schemas.
- Added `backend/app/services/batch_pipeline.py` with isolated `BatchPipelineService`.
- Added routes:
  - `POST /gemini/batch-auto-submit`
  - `GET /gemini/batch/{batch_id}`
  - `POST /gemini/batch/{batch_id}/cancel`
- Batch service uses existing `gemini_service.start()` per item; no browser reuse.
- Batch service polls existing render-job status through an injected getter; manual render code remains unchanged.
- Existing `POST /gemini/auto-submit` route remains unchanged.

### Frontend Implementation
- Added batch types to `frontend/src/types.ts`.
- Added batch API helpers to `frontend/src/api.ts`:
  - `startBatchAutoPipeline()`
  - `fetchBatchProgress()`
  - `cancelBatch()`
- Added `frontend/src/components/BatchPipelineProgress.tsx`.
- Updated `handleAutoPipeline()` in `frontend/src/App.tsx`:
  - One URL continues to use existing `startAutoPipeline()`.
  - Multiple URLs use `startBatchAutoPipeline()` and poll `GET /gemini/batch/{batch_id}`.
- Added best-effort batch cancel from UI.

### Tests Added
- Added `tests/test_batch_pipeline.py` covering:
  - Batch creation with two pending items.
  - Strict sequential execution.
  - First item error continues to second item.
  - Cancel behavior marks running/pending items cancelled.
  - Cancel behavior does not start the next pending item after cancellation.
  - Existing single auto-submit route remains registered.
  - Existing single auto-submit function uses `gemini_service.start()` and not batch service.
- Added `tests/test_frontend_batch_smoke.py` as a non-live frontend/API smoke check covering:
  - Frontend source keeps a single-URL path to existing `startAutoPipeline()`.
  - Frontend source routes multi-URL path to `startBatchAutoPipeline()`.
  - API helper strings target `/gemini/auto-submit`, `/gemini/batch-auto-submit`, `/gemini/batch/{batch_id}`, and `/gemini/batch/{batch_id}/cancel`.
  - Batch progress panel and cancel wiring are present.

### Validation Results
- Targeted backend tests: `python -m pytest tests/test_batch_pipeline.py -q`
  - Result: `6 passed`.
- Targeted batch/frontend smoke tests: `python -m pytest tests/test_batch_pipeline.py tests/test_frontend_batch_smoke.py -q`
  - Result: `9 passed`.
- Full backend/test suite: `python -m pytest tests/ -q`
  - Result: `306 passed`.
- Frontend build: `npm run build`
  - Result: passed.
- Route registration smoke:
  - Verified required routes are registered:
    - `/gemini/auto-submit`
    - `/gemini/batch-auto-submit`
    - `/gemini/batch/{batch_id}`
    - `/gemini/batch/{batch_id}/cancel`
    - `/render-jobs`

### E2E / Manual Smoke Notes
- Single URL old path:
  - Covered by unit regression asserting `gemini_auto_submit()` still calls `gemini_service.start()` and not `batch_service.start()`.
  - Covered by frontend static smoke verifying `startAutoPipeline()` remains after the `urls.length > 1` batch branch.
- Multiple URLs batch path:
  - Covered by batch service tests, route registration smoke, and frontend static smoke verifying `startBatchAutoPipeline()` / `/gemini/batch-auto-submit`.
- Batch error continues:
  - Covered by `test_first_item_error_does_not_stop_second_item`.
- Cancel batch:
  - Covered by `test_cancel_batch_marks_running_and_pending_items`.
  - Pending items become `cancelled`.
  - Next item is not started after cancellation.
  - Current Gemini task cancellation is best effort via existing `gemini_service.cancel()`.
- Manual render unaffected:
  - Full backend suite passed, including existing render pipeline tests.
- WebSocket handler unchanged:
  - No new WebSocket route was added; existing `/gemini/status/{task_id}` remains the only Gemini WebSocket path.
- DB schema unchanged:
  - No model or migration/schema file was changed for batch.
- SegmentPlanner/TTS logic unchanged:
  - Batch implementation does not modify `segment_planner.py`, `tts_tools.py`, or `video_tools.py`.
- Full live Gemini/YouTube E2E was not executed because it requires external Gemini login/browser automation and real YouTube downloads.

### Changed Files
- `backend/app/schemas/batch.py`
- `backend/app/services/batch_pipeline.py`
- `backend/app/api/routes.py`
- `frontend/src/types.ts`
- `frontend/src/api.ts`
- `frontend/src/components/BatchPipelineProgress.tsx`
- `frontend/src/App.tsx`
- `tests/test_batch_pipeline.py`
- `tests/test_frontend_batch_smoke.py`
- `docs/BATCH_MULTI_YOUTUBE_BUILD_REPORT.md`

### Known Limitations
- Batch progress uses polling, not WebSocket.
- Browser is not reused between items.
- Batch cancellation is best effort:
  - It cancels the current Gemini task if available.
  - It does not force-cancel an already-running render job to avoid unsafe interruption.
- Full live external E2E still needs to be run with a valid Gemini session and YouTube-download environment.

Status: implementation and validation complete; awaiting review before commit.
