# Gemini Login State False-Positive Fix Report

## Root Cause

**`_set_live_session_status()` had a downgrade‑protection guard that permanently prevented a cached "verified logged‑in" status from ever being downgraded, even when live detection later found a visible Sign‑In button.**

---

## Old Detection Logic (Broken)

### `_set_live_session_status()` (lines 397–411)

```python
if previous_verified and not logged_in:
    current = dict(self._last_session_status or {})
    current.update({...browser_state...})
    self._last_session_status = current
    return   # ← never downgrades
```

Once the session was marked as `exists=True, live_checked=True` (verified logged‑in), ALL subsequent `logged_in=False` calls were silently discarded. The status remained "Đã đăng nhập" indefinitely until server restart.

This affected two flows:
1. **User signs out while browser is open** — `_save_loop` detects sign‑in button → `_set_live_session_status(logged_in=False)` → **ignored**.
2. **User re‑opens browser after session expiry** — initial detection finds sign‑in page → `_set_live_session_status(logged_in=False)` → **ignored** because cache from previous open still says verified.

### `get_session_status()`

Always returned the cached `_last_session_status` without re-checking the session file or running a new detection. The only live‑check happens inside `_run_standalone_browser()` / `_save_loop` — which was neutered by the guard above.

### Detection Logic (`_detect_gemini_login_state`)

```python
if cookie_ok and (chat_area_ok or avatar_ok):   →  logged_in=True  (method="cookies")
elif chat_area_ok:                                →  logged_in=True  (method="chat_area")
elif avatar_ok:                                   →  logged_in=True  (method="avatar")
elif signin_indicator:                            →  logged_in=False (method="signin")
else:                                             →  logged_in=False (method="unknown")
```

This logic was already correct — it requires both auth cookies AND a chat/avatar element to consider cookies sufficient, and explicitly treats sign‑in buttons as NOT logged in. The problem was entirely in the caching layer, not the detection.

---

## New Detection Logic (Fixed)

### `_set_live_session_status()` — downgrade protection changed

```python
if previous_verified and not logged_in:
    if method == "signin":
        # Allow downgrade — sign‑in page is explicitly visible
        logger.info("Live check detects sign‑in page — downgrading...")
    else:
        # Transient / unknown state — keep previous verified status
        current = dict(self._last_session_status or {})
        current.update({...browser_state...})
        self._last_session_status = current
        return
```

**Key change:** Only protect when `method="unknown"` (transient loading/navigation state). When `method="signin"` (Sign‑In button is visible on page), the status **is** downgraded.

### Logging Added

In `_run_standalone_browser()`:
- Before navigation: logs `session_path` and `session_path.exists()`
- After `_detect_gemini_login_state()`: logs `logged_in`, `method`, `cookie_ok`, `chat_area_ok`, `avatar_ok`, `signin_indicator`

In `_set_live_session_status()`:
- On downgrade: logs `session_path`, `method`, `signin_indicator`

### Status Field Semantics

| Scenario | `exists` | `live_checked` | `needs_login` | `browser_open` | UI shows |
|---|---|---|---|---|---|
| No session file | false | false | true | false | "Chưa login" |
| Session file exists (unverified) | false | false | false* | false | "Có session đã lưu" |
| Browser open, sign‑in detected | false | true | true | true | "Session hết hạn" |
| Browser open, verified logged‑in | true | true | false | true | "Đã đăng nhập" |
| After sign‑in detected + browser closed | false | true | true | false | "Session hết hạn" |
| After verified + browser closed | true | true | false | false | "Đã đăng nhập" |

*\* `needs_login` is false when `has_auth_cookies=true` but not live‑checked (legacy; UI ignores this field for non‑live cases)*

---

## Files Changed

| File | Change |
|---|---|
| `backend/app/services/gemini_automation.py` | Modified `_set_live_session_status()` to allow downgrade on `method="signin"`; added logging for session path, existence, and detection result. |
| `tests/test_gemini_login_state.py` | Renamed old transient‑signin test to `test_verified_live_session_is_not_downgraded_by_transient_unknown` with `method="unknown"`; added new `test_verified_live_session_is_downgraded_by_signin_indicator`. |
| `docs/GEMINI_LOGIN_STATE_REPORT.md` | This report. |

---

## Tests

### Targeted Login‑State Tests (25 tests)

```bash
python -m pytest tests/test_gemini_login_state.py -q
```

`25 passed in 0.75s`

### Full Backend Suite (312 tests)

```bash
python -m pytest tests/ -q
```

`312 passed in 5.43s`

### Frontend Build

```bash
npm run build
```

`build success` — no UI changes required.

---

## Test Coverage Added

| Test | Verifies |
|---|---|
| `test_verified_live_session_is_downgraded_by_signin_indicator` | After verified logged‑in, a subsequent `method="signin"` detection correctly downgrades to `exists=False, needs_login=True`. After browser close, `needs_login` stays True. |
| `test_verified_live_session_is_not_downgraded_by_transient_unknown` | After verified logged‑in, a `method="unknown"` detection (transient) keeps the existing verified status. |

### Existing Relevant Tests

| Test | Verifies |
|---|---|
| `test_detect_gemini_login_state_stale_cookie_with_signin_requires_login` | Cookie exists but sign‑in visible → `logged_in=False` |
| `test_detect_gemini_login_state_signin_requires_login` | Only sign‑in visible → `logged_in=False` |
| `test_detect_gemini_login_state_by_chat_area` | Chat area visible → `logged_in=True` |
| `test_detect_gemini_login_state_by_avatar` | Avatar visible (incl. SignOut link) → `logged_in=True` |
| `test_signout_indicator_is_not_treated_as_signin` | SignOut link treated as avatar (logged‑in), not sign‑in indicator |
| `test_session_status_without_file_does_not_overclaim_live_login` | No file → `exists=False, live_checked=False` |
| `test_session_status_with_auth_cookie_does_not_overclaim_live_login` | File exists → `live_checked=False` (conservative) |
| `test_live_session_status_marks_expired_session_needing_login` | After live check with `logged_in=False` → `needs_login=True` |
| `test_live_session_status_marks_verified_login` | After live check with `logged_in=True` → `exists=True` |

---

## Remaining Limitations

1. **No live re‑verification when browser is closed.** After the browser closes, `get_session_status()` returns the last known live‑checked state without re‑opening a headless browser. If the session expires while the browser is closed, the cached "Đã đăng nhập" will persist until the user opens the browser again (at which point the fix correctly downgrades).

2. **Transient `method="unknown"` is still protected.** During navigation or page transitions, `_detect_gemini_login_state()` may return `method="unknown"`. This will not downgrade the status, preventing false‑positive "Session hết hạn" glitches.

3. **No cookie expiry check.** The session file's auth cookies are not checked for expiration. If a cookie has an expiry date, the code could detect it without needing a live browser visit. This is a future enhancement beyond the current scope.
