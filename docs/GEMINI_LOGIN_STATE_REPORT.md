# Gemini Login State Report

## Phase 1 — Current Flow

### API liên quan

- `POST /api/gemini/open-browser`: mở Chromium để user đăng nhập Gemini và lưu Playwright `storage_state`.
- `GET /api/gemini/session-status`: kiểm tra file session đã lưu.
- `POST /api/gemini/auto-submit`: tạo prompt và chạy auto pipeline qua Gemini.
- `WS /api/gemini/status/{task_id}`: stream trạng thái auto pipeline.

### Function liên quan

- `GeminiAutomationService.open_standalone_browser()`
- `GeminiAutomationService._run_standalone_browser()`
- `GeminiAutomationService.start()`
- `GeminiAutomationService._run_pipeline()`
- `GeminiAutomationService._handle_login_if_needed()`
- `GeminiAutomationService.get_session_status()`

### Cách check login trước đây

- `get_session_status()` chỉ đọc `settings.gemini_session_path` và kiểm tra cookie auth trong file.
- Auto pipeline mở Gemini, sau đó `_handle_login_if_needed()` kiểm tra cookie/DOM inline.
- Standalone browser lưu session bằng vòng lặp mỗi 10 giây.

### Rủi ro trước đây

- Session file tồn tại không đồng nghĩa Gemini session còn sống.
- Cookie auth có thể stale hoặc hết hạn server-side.
- Logic check login bị phân tán, khó đảm bảo auto pipeline luôn live-check.
- User có thể đăng nhập xong rồi đóng standalone browser quá nhanh trước khi vòng lưu 10 giây chạy.

## Phase 2 — Implementation

### Files changed

- `backend/app/services/gemini_automation.py`
- `tests/test_gemini_login_state.py`
- `docs/GEMINI_LOGIN_STATE_REPORT.md`

### Helper added

Added internal helper:

```python
async def _detect_gemini_login_state(page, context) -> dict:
    ...
```

Return shape:

```json
{
  "logged_in": true,
  "method": "cookies|chat_area|avatar|signin|unknown",
  "needs_login": false,
  "cookie_ok": true,
  "chat_area_ok": true,
  "avatar_ok": false,
  "signin_indicator": false
}
```

Detection order:

1. Auth cookies in Playwright context: `SAPISID`, `__Secure-3PSAPISID`, `OSID`
2. Gemini chat area/textbox with no sign-in indicator
3. User avatar/profile indicator
4. Sign-in indicator
5. Unknown / needs login

### New code path

Auto pipeline:

```text
_run_pipeline()
→ page.goto(settings.gemini_url)
→ _handle_login_if_needed()
→ _detect_gemini_login_state()
→ if logged_in: save storage_state immediately, continue
→ if not logged_in: wait_login, poll live state, save storage_state immediately after login
→ submit prompt only after live login detection succeeds
```

Standalone browser:

```text
_run_standalone_browser()
→ page.goto(settings.gemini_url)
→ _detect_gemini_login_state()
→ if logged_in: save storage_state immediately
→ background loop polls every 2s and saves immediately when login is detected
```

`session-status` endpoint semantics:

```json
{
  "exists": true,
  "session_file_exists": true,
  "has_auth_cookies": true,
  "live_checked": false,
  "path": "...",
  "message": "Session file exists but live Gemini login is verified during auto pipeline."
}
```

The endpoint remains backward-compatible via `exists`, but does not overclaim live login.

## Phase 3 — Validation

### Case 1 — Session file exists but live check fails

Expected:

```text
auto pipeline waits for login
```

Validation:

- `_detect_gemini_login_state()` returns `logged_in=false`, `method=signin|unknown`, `needs_login=true` when no live login signal exists.
- `_handle_login_if_needed()` uses this helper before prompt submission and moves to `wait_login` when not logged in.

### Case 2 — Live check succeeds by chat area

Expected:

```text
storage_state saved immediately
pipeline continues
```

Validation:

- Unit test verifies chat area detection returns `logged_in=true`, `method=chat_area`.
- `_handle_login_if_needed()` saves `storage_state` immediately for logged-in state.

### Case 3 — Standalone browser login

Expected:

```text
```

Validation:

- `_run_standalone_browser()` now checks login after `page.goto()` and saves immediately if logged in.
- Background save loop polls every 2 seconds and saves as soon as login is detected.

### Case 4 — session-status endpoint

Expected:

```text
```

Validation:

- Unit tests verify `live_checked=false` for both missing and existing session files.
- Response message explicitly states live Gemini login is verified during auto pipeline.

## Tests

Command:

```powershell
python.exe -m pytest tests/test_gemini_login_state.py -q
```

Result:

```text
7 passed
```

Full suite command:

```powershell
python.exe -m pytest tests/ -q
```

Result:

```text
283 passed
```
