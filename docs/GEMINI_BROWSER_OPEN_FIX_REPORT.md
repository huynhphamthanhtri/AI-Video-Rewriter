# GEMINI BROWSER OPEN FIX REPORT

## Root Cause

The `/api/gemini/open-browser` endpoint returned success immediately after scheduling `_run_standalone_browser()` as a background task.

If Playwright or Chromium failed after task creation, the exception stayed inside the background task and the UI still showed a success toast. This made the UI report that Chromium opened even when no browser window was actually launched.

## Files Changed

* `backend/app/services/gemini_automation.py`
* `frontend/src/api.ts`
* `tests/test_gemini_login_state.py`
* `tests/test_frontend_gemini_browser_smoke.py`
* `docs/GEMINI_BROWSER_OPEN_FIX_REPORT.md`

## Exact Fix

* `open_standalone_browser()` now creates a launch confirmation future and waits for it before returning `browser_id`.
* `_run_standalone_browser()` now resolves that future only after Playwright launches Chromium and stores an open browser/page entry.
* Launch failures now set an exception on the confirmation future so the API returns an error instead of success.
* Launch confirmation is bounded by a 30 second timeout. Timeout and cancellation paths clean stale browser registry entries.
* The requested `user_data_dir` is resolved and created before launch.
* Backend logs now include:
  * resolved `user_data_dir`
  * Chromium executable path when available
  * channel (`default`)
  * `headless=False`
  * launch errors via `logger.exception()`
* `frontend/src/api.ts` now always sends a valid JSON body to `/gemini/open-browser`: `{ "user_data_dir": null }` when no profile path is provided. This avoids a `Content-Type: application/json` request with an undefined body.
* Frontend behavior uses `toast.success()` only after `openGeminiBrowser()` returns successfully, and `toast.error()` when the API request fails.

## Unsupported Content Type Investigation

Observed error: `Bad Request: {"detail":"Unsupported content type"}`.

Findings:

* App backend code does not define this error string.
* Backend access logs did not show a `400 Bad Request` for `/api/gemini/open-browser`; open-browser requests showed `200` before the fix and `500` after the fix when Chromium launch could not be confirmed in the current environment.
* Direct `/api/gemini/open-browser` reproduction with a valid JSON body did not produce `Unsupported content type`.
* The only repository match for the exact string is in `.venv312/Lib/site-packages/huggingface_hub/inference/_common.py`, not in this app's API handlers.
* Upload endpoints (`/api/upload-cookies`, `/api/blur/upload-video`) require multipart/form-data and return FastAPI validation errors when called with JSON, not this exact error.

Conclusion:

* The observed `Unsupported content type` is not confirmed as an open-browser backend error.
* The open-browser frontend request was still hardened by always sending a JSON body with the JSON content type.
* If the error reappears, capture the Network tab request URL/method to identify the exact endpoint before expanding scope.

## Test Commands/Results

Targeted tests:

```powershell
python -m pytest tests/test_gemini_login_state.py tests/test_frontend_gemini_browser_smoke.py -q
```

Result: `26 passed`.

Full backend tests:

```powershell
python -m pytest tests/ -q
```

Result: `311 passed`.

Frontend build:

```powershell
npm run build
```

Result: PASS (`tsc -b && vite build`).

Manual smoke:

```powershell
POST http://127.0.0.1:8007/api/gemini/open-browser
Body: {"user_data_dir": null}
```

Result in current environment: HTTP 500 with clear backend error detail instead of false success: `Không thể mở trình duyệt Gemini. Xem log backend để biết chi tiết.`

## Remaining Limitations

* Manual smoke test depends on local Playwright/Chromium availability and OS ability to show a browser window.
* This fix verifies Chromium launch before returning success; it does not guarantee Gemini login completes.
* Existing auto pipeline, batch pipeline, DB schema, WebSocket flow, and manual render flow were not changed.
