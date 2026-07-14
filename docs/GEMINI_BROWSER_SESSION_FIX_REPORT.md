   # Gemini Browser Session Fix Report

   ## 1. Root Cause

   The Gemini browser/session flow had several issues that could make login appear successful while the saved session was missing or stale.

   - The default session path was `ROOT_DIR / "data" / "gemini_session.json"`.
   - In an installed build, `ROOT_DIR` resolves under `C:\Program Files\MrTris_AUTO`, which is not writable for a normal user.
   - `context.storage_state()` failures were swallowed in both standalone browser and auto pipeline paths.
   - Login detection trusted auth cookies alone, even when Gemini showed a sign-in screen.
   - `a[href*='SignOut']` was incorrectly treated as a sign-in indicator.
   - Headless auto pipeline could wait for manual login even though the user could not see the browser.
   - Standalone browser did not load the saved session file before navigating to Gemini.

   ## 2. Fixes Implemented

   ### Config Path

   `backend/app/core/config.py` now resolves the default Gemini session path to app data when packaged:

   ```text
   %LOCALAPPDATA%\MrTris_AUTO\data\gemini_session.json
   ```

   Development mode still uses:

   ```text
   <repo>\data\gemini_session.json
   ```

   Environment overrides still work through Pydantic settings.

   ### Session Save Error Handling

   Added `_save_session_state()` in `GeminiAutomationService`.

   - Creates the parent directory before saving.
   - Logs warning with the session path and exception if save fails.
   - Auto pipeline surfaces save failure as an error instead of silently continuing.
   - Standalone browser logs failures and continues running.

   ### Stricter Login Detection

   `_detect_gemini_login_state()` no longer trusts cookies alone.

   Login is true only when Gemini does not show a sign-in indicator and one of these is present:

   - auth cookie plus chat area/avatar
   - chat area
   - avatar/signout indicator

   If a clear sign-in indicator is present, login is false even if auth cookies exist.

   ### SignOut Selector

   `a[href*='SignOut']` was removed from `sign_in_indicators` and added to logged-in/profile detection.

   ### Headless Behavior

   When the auto pipeline runs headless and live login check fails, it now fails fast with:

   ```text
   Gemini session is not logged in. Please use Open Browser to login first.
   ```

   It does not wait 5 minutes for a manual login that cannot happen in headless mode, and it does not submit the prompt.

   ### Standalone Session Loading

   Standalone browser now loads `gemini_session.json` with Playwright `storage_state` when the session file exists and no Chrome profile auth cookies are injected.

   After `page.goto(settings.gemini_url)`, it live-checks login and saves the session immediately if login is confirmed.

   ## 3. Tests

   Commands run:

   ```powershell
   python.exe -m pytest tests/test_gemini_login_state.py -q
   ```

   Result:

   ```text
   13 passed
   ```

   ```powershell
   python.exe -m pytest tests/ -q
   ```

   Result:

   ```text
   289 passed
   ```

   Tests added/updated cover:

   - Packaged session path resolves to appdata.
   - Cookie-only state is not enough to claim login.
   - Stale cookie plus sign-in DOM returns `logged_in=false`.
   - Chat area without sign-in returns `logged_in=true`.
   - Avatar/signout indicator without sign-in returns `logged_in=true`.
   - `SignOut` is not treated as sign-in.
   - Headless missing login fails fast.
   - Auto pipeline session save failure is surfaced.

   ## 4. Manual Validation Steps

   1. Delete existing `gemini_session.json`.
   2. Open browser from the app.
   3. Login Gemini.
   4. Confirm session saved in appdata path:

      ```text
      %LOCALAPPDATA%\MrTris_AUTO\data\gemini_session.json
      ```

   5. Close app.
   6. Reopen app.
   7. Run auto pipeline.
   8. Confirm it does not request login again.
   9. Confirm prompt submission only starts after live login detection succeeds.

   ## 5. Remaining Risks

   - Gemini DOM selectors are still heuristic and may need updates if Google changes the Gemini UI.
   - Cookie presence remains a supporting signal only; live DOM state is required before submission.
   - `session-status` remains file-based and intentionally reports `live_checked=false`; live validation happens inside the browser pipeline.

   ## Status

   ```text
   READY FOR LOCAL INSTALLER REBUILD
   NOT PUBLISHED
   ```
