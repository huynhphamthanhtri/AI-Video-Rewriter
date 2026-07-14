import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app.core.config import _default_gemini_session_path
from app.core.config import settings
from app.api import routes
from app.services.gemini_automation import GeminiAutomationService, GeminiAutomationTask


class FakeLocator:
    def __init__(self, count: int, visible: bool | None = None):
        self._count = count
        self._visible = count > 0 if visible is None else visible
        self.clicked = False

    @property
    def first(self):
        return self

    async def count(self) -> int:
        return self._count

    async def is_visible(self, *args, **kwargs) -> bool:
        return self._visible

    async def click(self, *args, **kwargs) -> None:
        self.clicked = True


class FakePage:
    def __init__(self, counts: dict[str, int | tuple[int, bool]], url: str = "https://gemini.google.com"):
        self.counts = counts
        self._url = url
        self.locators: dict[str, FakeLocator] = {}

    @property
    def url(self) -> str:
        return self._url

    def locator(self, selector: str) -> FakeLocator:
        if selector in self.locators:
            return self.locators[selector]
        value = self.counts.get(selector, 0)
        if isinstance(value, tuple):
            loc = FakeLocator(value[0], value[1])
        else:
            loc = FakeLocator(value)
        self.locators[selector] = loc
        return loc

    async def wait_for_load_state(self, state: str, *args, **kwargs) -> None:
        return None

    def is_closed(self) -> bool:
        return False


class FakeClosedPage(FakePage):
    def __init__(self):
        super().__init__({})

    def is_closed(self) -> bool:
        return True


class FakeContext:
    def __init__(self, cookies: list[dict] | None = None, fail_save: bool = False):
        self._cookies = cookies or []
        self.fail_save = fail_save
        self.saved_paths: list[str] = []

    async def cookies(self) -> list[dict]:
        return self._cookies

    async def storage_state(self, path: str) -> None:
        if self.fail_save:
            raise OSError("cannot write session")
        self.saved_paths.append(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({"cookies": self._cookies}), encoding="utf-8")


def _detect(page: FakePage, context: FakeContext) -> dict:
    return asyncio.run(GeminiAutomationService()._detect_gemini_login_state(page, context))


def test_click_first_visible_clicks_signin_selector():
    page = FakePage({"button:has-text('Sign in')": 1})
    clicked = asyncio.run(GeminiAutomationService()._click_first_visible(page, ["missing", "button:has-text('Sign in')"]))

    assert clicked == "button:has-text('Sign in')"
    assert page.locators["button:has-text('Sign in')"].clicked is True


def test_click_google_account_if_available_uses_existing_account_only():
    page = FakePage({"div[data-identifier]": 1})
    clicked = asyncio.run(GeminiAutomationService()._click_google_account_if_available(page))

    assert clicked == "div[data-identifier]"
    assert page.locators["div[data-identifier]"].clicked is True


def test_packaged_gemini_session_path_resolves_to_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("MRTRIS_AUTO_PACKAGED", "1")
    monkeypatch.setenv("MRTRIS_AUTO_APPDATA", str(tmp_path / "MrTris_AUTO"))

    path = _default_gemini_session_path()

    assert path == tmp_path / "MrTris_AUTO" / "data" / "gemini_session.json"


def test_detect_gemini_login_state_cookie_only_is_not_enough():
    state = _detect(FakePage({}), FakeContext([{"name": "SAPISID", "value": "x"}]))

    assert state["logged_in"] is False
    assert state["method"] == "unknown"
    assert state["needs_login"] is True
    assert state["cookie_ok"] is True


def test_detect_gemini_login_state_by_cookies_with_chat_area():
    state = _detect(FakePage({"[role='textbox']": 1}), FakeContext([{"name": "SAPISID", "value": "x"}]))

    assert state["logged_in"] is True
    assert state["method"] == "cookies"
    assert state["needs_login"] is False
    assert state["cookie_ok"] is True


def test_detect_gemini_login_state_by_chat_area_alone_is_not_enough():
    state = _detect(FakePage({"[role='textbox']": 1}), FakeContext())

    assert state["logged_in"] is False
    assert state["method"] == "unknown"
    assert state["chat_area_ok"] is True
    assert state["needs_login"] is True


def test_detect_gemini_login_state_by_avatar_alone_is_not_enough():
    state = _detect(FakePage({"[data-test-id='user-avatar']": 1}), FakeContext())

    assert state["logged_in"] is False
    assert state["method"] == "unknown"
    assert state["avatar_ok"] is True
    assert state["needs_login"] is True


def test_detect_gemini_login_state_stale_cookie_with_signin_requires_login():
    state = _detect(
        FakePage({"button:has-text('Sign in')": 1}),
        FakeContext([{"name": "SAPISID", "value": "x"}]),
    )

    assert state["logged_in"] is False
    assert state["method"] == "signin"
    assert state["needs_login"] is True
    assert state["cookie_ok"] is True


def test_detect_gemini_login_state_ignores_accounts_google_link_after_login():
    state = _detect(
        FakePage({"[role='textbox']": 1, "a[href*='accounts.google.com']": 1}),
        FakeContext([{"name": "SAPISID", "value": "x"}]),
    )

    assert state["logged_in"] is True
    assert state["method"] == "cookies"
    assert state["signin_indicator"] is False


def test_detect_gemini_login_state_hidden_signin_does_not_override_login():
    state = _detect(
        FakePage({"[role='textbox']": 1, "button:has-text('Sign in')": (1, False)}),
        FakeContext([{"name": "SAPISID", "value": "x"}]),
    )

    assert state["logged_in"] is True
    assert state["method"] == "cookies"
    assert state["signin_indicator"] is False


def test_detect_gemini_login_state_signin_requires_login():
    state = _detect(FakePage({"button:has-text('Sign in')": 1}), FakeContext())

    assert state["logged_in"] is False
    assert state["method"] == "signin"
    assert state["needs_login"] is True
    assert state["signin_indicator"] is True


def test_detect_gemini_login_state_unknown_requires_login():
    state = _detect(FakePage({}), FakeContext())

    assert state["logged_in"] is False
    assert state["method"] == "unknown"
    assert state["needs_login"] is True


def test_signout_indicator_with_cookie_is_logged_in():
    state = _detect(FakePage({"a[href*='SignOut']": 1}), FakeContext([{"name": "SAPISID", "value": "x"}]))

    assert state["logged_in"] is True
    assert state["method"] == "cookies"
    assert state["signin_indicator"] is False


def test_push_state_coalesces_same_step():
    task = GeminiAutomationTask("task-coalesce-1")
    task.update("init", "Starting...")
    assert len(task.states) == 1

    task.update("init", "Still initializing...")
    assert len(task.states) == 1, "Same step should not create new state"

    task.update("navigate_gemini", "Navigating...")
    assert len(task.states) == 2, "Different step should create new state"
    assert task.states[0]["status"] == "done"
    assert task.states[0]["step"] == "init"
    assert task.states[1]["step"] == "navigate_gemini"
    assert task.states[1]["status"] == "running"


def test_push_state_does_not_coalesce_after_mark_done():
    task = GeminiAutomationTask("task-coalesce-2")
    task.update("init", "Starting...")
    task.mark_done({"ok": True})
    assert task.states[0]["status"] == "done"

    task.update("navigate_gemini", "Navigating...")
    assert len(task.states) == 2


def test_push_state_does_not_coalesce_different_step_reentry():
    task = GeminiAutomationTask("task-coalesce-3")
    # init state at index 0
    task.update("submitting_prompt", "Finding input...")
    task.update("submitting_prompt", "Typing...")
    task.update("submitting_prompt", "Sending...")
    assert len(task.states) == 2, "Same step coalesced (init + submitting_prompt)"
    task.update("waiting_response", "Waiting...")
    assert len(task.states) == 3, "Different step pushes new state"
    assert task.states[1]["status"] == "done"


def test_checking_login_label_exists():
    from app.services.gemini_automation import STEP_LABELS
    assert "checking_login" in STEP_LABELS
    assert STEP_LABELS["checking_login"] == "Kiểm tra đăng nhập Gemini"


def test_headless_not_logged_in_fails_fast_without_waiting(tmp_path):
    service = GeminiAutomationService()
    task = GeminiAutomationTask("task-1")

    asyncio.run(service._handle_login_if_needed(task, FakePage({}), FakeContext(), tmp_path / "session.json", headless=True))

    assert task.status == "error"
    assert "Open Browser" in task.error


def test_session_save_failure_is_surfaced_in_auto_pipeline(tmp_path):
    service = GeminiAutomationService()
    task = GeminiAutomationTask("task-1")
    page = FakePage({"[role='textbox']": 1})
    context = FakeContext([{"name": "SAPISID", "value": "x"}], fail_save=True)

    asyncio.run(service._handle_login_if_needed(task, page, context, tmp_path / "session.json", headless=False))

    assert task.status == "error"
    assert "không thể lưu session" in task.error


def test_session_status_without_file_does_not_overclaim_live_login(tmp_path, monkeypatch):
    session_path = tmp_path / "gemini_session.json"
    monkeypatch.setattr(settings, "gemini_session_path", session_path)

    status = GeminiAutomationService().get_session_status()

    assert status["exists"] is False
    assert status["session_file_exists"] is False
    assert status["has_auth_cookies"] is False
    assert status["live_checked"] is False
    assert "Chưa có session Gemini." in status["message"]


def test_session_status_with_auth_cookie_does_not_overclaim_live_login(tmp_path, monkeypatch):
    session_path = tmp_path / "gemini_session.json"
    session_path.write_text(json.dumps({"cookies": [{"name": "SAPISID", "value": "x"}]}), encoding="utf-8")
    monkeypatch.setattr(settings, "gemini_session_path", session_path)

    status = GeminiAutomationService().get_session_status()

    assert status["exists"] is False
    assert status["session_file_exists"] is True
    assert status["has_auth_cookies"] is True
    assert status["live_checked"] is False
    assert "xác minh" in status["message"]


def test_live_session_status_marks_expired_session_needing_login(tmp_path, monkeypatch):
    session_path = tmp_path / "gemini_session.json"
    session_path.write_text(json.dumps({"cookies": [{"name": "SAPISID", "value": "x"}]}), encoding="utf-8")
    monkeypatch.setattr(settings, "gemini_session_path", session_path)
    service = GeminiAutomationService()

    service._set_live_session_status(session_path, {"logged_in": False, "cookie_ok": True, "method": "signin"})
    status = service.get_session_status()

    assert status["exists"] is False
    assert status["session_file_exists"] is True
    assert status["has_auth_cookies"] is True
    assert status["live_checked"] is True
    assert status["needs_login"] is True
    assert "hết hạn" in status["message"] or "đăng nhập lại" in status["message"]


def test_live_session_status_marks_verified_login(tmp_path, monkeypatch):
    session_path = tmp_path / "gemini_session.json"
    monkeypatch.setattr(settings, "gemini_session_path", session_path)
    service = GeminiAutomationService()
    service._browsers = {}

    service._set_live_session_status(session_path, {"logged_in": True, "cookie_ok": True, "method": "cookies"})
    status = service.get_session_status()

    assert status["exists"] is True
    assert status["live_checked"] is True
    assert status["needs_login"] is False
    assert status["method"] == "cookies"


def test_verified_live_session_is_not_downgraded_by_transient_unknown(tmp_path, monkeypatch):
    session_path = tmp_path / "gemini_session.json"
    monkeypatch.setattr(settings, "gemini_session_path", session_path)
    service = GeminiAutomationService()

    service._browsers["browser-1"] = {"status": "open"}
    service._set_live_session_status(session_path, {"logged_in": True, "cookie_ok": True, "method": "cookies"}, browser_id="browser-1")
    service._set_live_session_status(session_path, {"logged_in": False, "cookie_ok": True, "method": "unknown"}, browser_id="browser-1")
    status = service.get_session_status()

    assert status["exists"] is True
    assert status["live_checked"] is True
    assert status["needs_login"] is False
    assert status["browser_open"] is True
    assert status["browser_id"] == "browser-1"

    service._mark_standalone_browser_closed("browser-1")
    status = service.get_session_status()

    assert status["exists"] is False
    assert status["needs_login"] is True
    assert status["browser_open"] is False
    assert status["browser_id"] is None


def test_verified_live_session_is_downgraded_by_signin_indicator(tmp_path, monkeypatch):
    session_path = tmp_path / "gemini_session.json"
    monkeypatch.setattr(settings, "gemini_session_path", session_path)
    service = GeminiAutomationService()

    service._browsers["browser-1"] = {"status": "open"}
    service._set_live_session_status(session_path, {"logged_in": True, "cookie_ok": True, "method": "cookies"}, browser_id="browser-1")

    status = service.get_session_status()
    assert status["exists"] is True
    assert status["needs_login"] is False

    service._set_live_session_status(session_path, {"logged_in": False, "cookie_ok": True, "method": "signin", "signin_indicator": True}, browser_id="browser-1")
    status = service.get_session_status()

    assert status["exists"] is False
    assert status["live_checked"] is True
    assert status["needs_login"] is True
    assert status["method"] == "signin"
    assert "hết hạn" in status["message"] or "đăng nhập lại" in status["message"]

    service._mark_standalone_browser_closed("browser-1")
    status = service.get_session_status()

    assert status["exists"] is False
    assert status["needs_login"] is True
    assert status["browser_open"] is False
    assert status["browser_id"] is None


def test_verified_live_session_is_downgraded_by_force_unknown(tmp_path, monkeypatch):
    session_path = tmp_path / "gemini_session.json"
    monkeypatch.setattr(settings, "gemini_session_path", session_path)
    service = GeminiAutomationService()
    service._browsers["browser-1"] = {"status": "open"}

    service._set_live_session_status(session_path, {"logged_in": True, "cookie_ok": True, "method": "cookies"}, browser_id="browser-1")
    status = service.get_session_status()
    assert status["exists"] is True
    assert status["needs_login"] is False

    service._set_live_session_status(session_path, {"logged_in": False, "cookie_ok": True, "method": "unknown"}, browser_id="browser-1", force=True)
    status = service.get_session_status()
    assert status["exists"] is False
    assert status["live_checked"] is True
    assert status["needs_login"] is True


def test_verified_live_session_resets_on_browser_close(tmp_path, monkeypatch):
    session_path = tmp_path / "gemini_session.json"
    monkeypatch.setattr(settings, "gemini_session_path", session_path)
    service = GeminiAutomationService()
    service._browsers["browser-1"] = {"status": "open"}

    service._set_live_session_status(session_path, {"logged_in": True, "cookie_ok": True, "method": "cookies"}, browser_id="browser-1")
    status = service.get_session_status()
    assert status["exists"] is True
    assert status["needs_login"] is False
    assert status["live_checked"] is True

    service._mark_standalone_browser_closed("browser-1")
    status = service.get_session_status()
    assert status["exists"] is False
    assert status["live_checked"] is False
    assert status["needs_login"] is True
    assert status["browser_open"] is False
    assert status["browser_id"] is None


def test_stale_closed_page_does_not_keep_browser_open(tmp_path, monkeypatch):
    session_path = tmp_path / "gemini_session.json"
    monkeypatch.setattr(settings, "gemini_session_path", session_path)
    service = GeminiAutomationService()
    service._browsers = {}
    service._browser_tasks = {}
    service._last_session_status = None

    service._browsers["browser-1"] = {"status": "open", "page": FakeClosedPage()}
    service._set_live_session_status(session_path, {"logged_in": True, "cookie_ok": True, "method": "cookies"}, browser_id="browser-1")
    status = service.get_session_status()

    assert status["exists"] is False
    assert status["needs_login"] is True
    assert status["browser_open"] is False
    assert status["browser_id"] is None
    assert "browser-1" not in service._browsers


def test_verify_live_session_no_file_after_close_uses_disk_info(tmp_path, monkeypatch):
    session_path = tmp_path / "gemini_session.json"
    monkeypatch.setattr(settings, "gemini_session_path", session_path)
    service = GeminiAutomationService()
    service._browsers["browser-1"] = {"status": "open"}

    service._set_live_session_status(session_path, {"logged_in": True, "cookie_ok": True, "method": "cookies"}, browser_id="browser-1")
    status = service.get_session_status()
    assert status["exists"] is True
    assert status["live_checked"] is True

    service._mark_standalone_browser_closed("browser-1")
    status = service.get_session_status()
    assert status["session_file_exists"] is False
    assert status["has_auth_cookies"] is False
    assert status["needs_login"] is True
    assert "Chưa có session Gemini." in status["message"]


def test_verify_live_session_with_saved_file_after_close_shows_saved(tmp_path, monkeypatch):
    session_path = tmp_path / "gemini_session.json"
    session_path.write_text(json.dumps({"cookies": [{"name": "SAPISID", "value": "x"}]}), encoding="utf-8")
    monkeypatch.setattr(settings, "gemini_session_path", session_path)
    service = GeminiAutomationService()
    service._browsers["browser-1"] = {"status": "open"}

    service._set_live_session_status(session_path, {"logged_in": True, "cookie_ok": True, "method": "cookies"}, browser_id="browser-1")
    status = service.get_session_status()
    assert status["exists"] is True
    assert status["live_checked"] is True

    service._mark_standalone_browser_closed("browser-1")
    status = service.get_session_status()
    assert status["session_file_exists"] is True
    assert status["has_auth_cookies"] is True
    assert status["needs_login"] is False
    assert status["exists"] is False
    assert status["live_checked"] is False
    assert "xác minh" in status["message"]


def test_get_session_status_pending_checking_on_launch(monkeypatch):
    service = GeminiAutomationService()
    session_path = Path("session.json")
    monkeypatch.setattr(settings, "gemini_session_path", session_path)
    service._browsers["browser-1"] = {"status": "open"}
    service._set_pending_status(session_path, "browser-1")

    status = service.get_session_status()
    assert status["exists"] is False
    assert status["live_checked"] is False
    assert status["browser_open"] is True
    assert status["browser_id"] == "browser-1"
    assert status["method"] == "checking"
    assert "Đang kiểm tra" in status["message"]


def test_detect_gemini_login_state_accounts_google_url_returns_signin():
    page = FakePage({}, url="https://accounts.google.com/signin/oauth")
    context = FakeContext()
    state = asyncio.run(GeminiAutomationService()._detect_gemini_login_state(page, context))

    assert state["logged_in"] is False
    assert state["method"] == "signin"
    assert state["signin_indicator"] is True


def test_detect_gemini_login_state_service_login_url_returns_signin():
    page = FakePage({}, url="https://accounts.google.com/ServiceLogin")
    context = FakeContext()
    state = asyncio.run(GeminiAutomationService()._detect_gemini_login_state(page, context))

    assert state["logged_in"] is False
    assert state["method"] == "signin"
    assert state["signin_indicator"] is True


def test_get_session_status_stale_cache_no_browser_does_not_claim_login(tmp_path, monkeypatch):
    session_path = tmp_path / "gemini_session.json"
    monkeypatch.setattr(settings, "gemini_session_path", session_path)
    service = GeminiAutomationService()
    service._browsers = {}
    service._browser_tasks = {}

    last_status = {
        "exists": True, "session_file_exists": True, "has_auth_cookies": True,
        "live_checked": True, "needs_login": False,
        "browser_open": True, "browser_id": "browser-1",
        "path": str(session_path), "method": "cookies",
        "message": "Đã xác minh đăng nhập Gemini thành công.",
    }
    service._last_session_status = last_status

    status = service.get_session_status()
    assert status["exists"] is False
    assert status["live_checked"] is False
    assert status["browser_open"] is False
    assert status["needs_login"] is True
    assert "Chưa có session Gemini." in status["message"]


def test_get_session_status_stale_cache_no_browser_with_file_shows_saved(tmp_path, monkeypatch):
    session_path = tmp_path / "gemini_session.json"
    session_path.write_text(json.dumps({"cookies": [{"name": "SAPISID", "value": "x"}]}), encoding="utf-8")
    monkeypatch.setattr(settings, "gemini_session_path", session_path)
    service = GeminiAutomationService()
    service._browsers = {}
    service._browser_tasks = {}

    last_status = {
        "exists": True, "session_file_exists": True, "has_auth_cookies": True,
        "live_checked": True, "needs_login": False,
        "browser_open": True, "browser_id": "browser-1",
        "path": str(session_path), "method": "cookies",
        "message": "Đã xác minh đăng nhập Gemini thành công.",
    }
    service._last_session_status = last_status

    status = service.get_session_status()
    assert status["exists"] is False
    assert status["live_checked"] is False
    assert status["browser_open"] is False
    assert status["browser_id"] is None
    assert status["session_file_exists"] is True
    assert status["has_auth_cookies"] is True
    assert status["needs_login"] is False
    assert "xác minh" in status["message"]


def test_open_standalone_browser_reuses_active_browser(monkeypatch):
    service = GeminiAutomationService()
    service._browsers = {}
    service._browser_tasks = {}
    service._browsers["browser-1"] = {"status": "open"}

    async def run() -> str:
        return await service.open_standalone_browser()

    browser_id = asyncio.run(run())

    assert browser_id == "browser-1"
    assert "browser-1" in service._browsers


def test_open_standalone_browser_ignores_stale_closed_page(monkeypatch):
    service = GeminiAutomationService()
    service._browsers = {}
    service._browser_tasks = {}
    service._browsers["browser-1"] = {"status": "open", "page": FakeClosedPage()}

    async def fake_run(browser_id: str, user_data_dir: str | None = None, launch_ready: asyncio.Future[None] | None = None) -> None:
        if launch_ready and not launch_ready.done():
            launch_ready.set_result(None)
        return None

    monkeypatch.setattr(service, "_run_standalone_browser", fake_run)

    async def run() -> str:
        return await service.open_standalone_browser()

    browser_id = asyncio.run(run())

    assert browser_id != "browser-1"
    assert "browser-1" not in service._browsers


def test_open_standalone_browser_waits_for_launch_success(monkeypatch):
    service = GeminiAutomationService()
    service._browsers = {}
    service._browser_tasks = {}
    launch_started = False

    async def fake_run(browser_id: str, user_data_dir: str | None = None, launch_ready: asyncio.Future[None] | None = None) -> None:
        nonlocal launch_started
        launch_started = True
        await asyncio.sleep(0)
        service._browsers[browser_id] = {"status": "open"}
        if launch_ready and not launch_ready.done():
            launch_ready.set_result(None)

    monkeypatch.setattr(service, "_run_standalone_browser", fake_run)

    async def run() -> str:
        return await service.open_standalone_browser()

    browser_id = asyncio.run(run())

    assert launch_started is True
    assert service._browsers[browser_id]["status"] == "open"


def test_open_standalone_browser_propagates_launch_failure(monkeypatch):
    service = GeminiAutomationService()
    service._browsers = {}
    service._browser_tasks = {}

    async def fake_run(browser_id: str, user_data_dir: str | None = None, launch_ready: asyncio.Future[None] | None = None) -> None:
        if launch_ready and not launch_ready.done():
            launch_ready.set_exception(RuntimeError("launch failed"))

    monkeypatch.setattr(service, "_run_standalone_browser", fake_run)

    async def run() -> str:
        return await service.open_standalone_browser()

    with pytest.raises(RuntimeError, match="launch failed"):
        asyncio.run(run())

    assert service._browsers == {}
    assert service._browser_tasks == {}


def test_open_browser_endpoint_returns_error_when_launch_fails(monkeypatch):
    async def fake_open(user_data_dir: str | None = None) -> str:
        raise RuntimeError("launch failed")

    monkeypatch.setattr(routes.gemini_service, "open_standalone_browser", fake_open)

    async def run():
        return await routes.gemini_open_browser(routes.OpenBrowserRequest(user_data_dir=None))

    with pytest.raises(routes.HTTPException) as exc:
        asyncio.run(run())

    assert exc.value.status_code == 500
    assert "Không thể mở trình duyệt" in exc.value.detail
    assert "launch failed" in exc.value.detail


# --- _response_is_login_or_error ---


def test_response_is_login_or_error_short_text():
    assert not GeminiAutomationService._response_is_login_or_error("")


def test_response_is_login_or_error_less_than_200():
    assert not GeminiAutomationService._response_is_login_or_error("a" * 150)
    assert not GeminiAutomationService._response_is_login_or_error("a" * 300)


def test_response_is_login_or_error_detects_sign_in():
    assert GeminiAutomationService._response_is_login_or_error("Sign in to continue using Gemini" + "x" * 500)


def test_response_is_login_or_error_detects_dang_nhap():
    assert GeminiAutomationService._response_is_login_or_error("Vui lòng Đăng nhập để sử dụng Gemini" + "x" * 500)


def test_response_is_login_or_error_detects_something_went_wrong():
    assert GeminiAutomationService._response_is_login_or_error("Something went wrong. Please try again." + "x" * 500)


def test_response_is_login_or_error_passes_code_block():
    text = "Here is your JSON:\n```json\n{\"metadata\": {\"title\": \"test\"}}\n```\n" + "x" * 500
    assert not GeminiAutomationService._response_is_login_or_error(text)


def test_response_is_login_or_error_passes_large_json():
    text = "{\n  \"metadata\": {\"title\": \"test\"},\n  \"segments\": []\n}" + "x" * 500
    assert not GeminiAutomationService._response_is_login_or_error(text)


def test_response_is_login_or_error_passes_long_text_without_json():
    text = "x" * 3000
    assert not GeminiAutomationService._response_is_login_or_error(text)


def _mock_page(url: str = "https://gemini.google.com/app") -> Any:
    from unittest.mock import AsyncMock
    page = AsyncMock()
    page.url = url
    return page


def test_wait_for_response_timeout_raises(monkeypatch):
    from unittest.mock import AsyncMock

    service = GeminiAutomationService()
    task = GeminiAutomationTask("test-timeout")
    task.status = "running"

    monkeypatch.setattr(settings, "gemini_timeout_seconds", 2)
    monkeypatch.setattr(service, "_has_gemini_copy_button", AsyncMock(return_value=False))
    monkeypatch.setattr(service, "_read_gemini_response_snapshot", AsyncMock(return_value=("still thinking...", "body_fallback")))
    monkeypatch.setattr(service, "_extract_json", lambda text: "")
    monkeypatch.setattr(service, "_save_raw_debug", AsyncMock())

    async def run():
        with pytest.raises(TimeoutError, match="Gemini xử lý quá lâu"):
            await service._wait_for_response(task, _mock_page(), AsyncMock())

    asyncio.run(run())
    assert task.status == "running"


def test_wait_for_response_no_break_when_no_json(monkeypatch):
    from unittest.mock import AsyncMock

    service = GeminiAutomationService()
    task = GeminiAutomationTask("test-no-json")
    task.status = "running"

    monkeypatch.setattr(settings, "gemini_timeout_seconds", 2)
    monkeypatch.setattr(service, "_has_gemini_copy_button", AsyncMock(return_value=False))
    monkeypatch.setattr(service, "_read_gemini_response_snapshot", AsyncMock(return_value=("x" * 10000, "body_fallback")))
    monkeypatch.setattr(service, "_extract_json", lambda text: "")
    monkeypatch.setattr(service, "_save_raw_debug", AsyncMock())

    async def run():
        with pytest.raises(TimeoutError, match="Gemini xử lý quá lâu"):
            await service._wait_for_response(task, _mock_page(), AsyncMock())

    asyncio.run(run())


def test_wait_for_response_returns_when_json_ready_and_stable(monkeypatch):
    from unittest.mock import AsyncMock

    service = GeminiAutomationService()
    task = GeminiAutomationTask("test-json-ready")
    task.status = "running"

    valid_json = json.dumps({
        "metadata": {"video_title": "Test", "rewrite_style": "Drama"},
        "rewrite_script": {"full_text": "Hello"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Hello"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Test", "importance_score": 50}],
    })

    monkeypatch.setattr(settings, "gemini_timeout_seconds", 60)
    monkeypatch.setattr(service, "_has_gemini_copy_button", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "_read_gemini_response_snapshot", AsyncMock(return_value=(valid_json, "response_selector")))
    monkeypatch.setattr(service, "_extract_json", lambda text: text if "video_segments" in text else "")
    monkeypatch.setattr(service, "_finalize_response_text", AsyncMock(return_value=valid_json))

    async def run():
        result = await service._wait_for_response(task, _mock_page(), AsyncMock())
        assert "video_segments" in result

    asyncio.run(run())


def test_extract_json_passes_response_with_login_keyword_in_content():
    """Regression: _extract_json must return JSON even if response text contains
    'đăng nhập' or 'sign in' inside the script content, not as a login page."""
    svc = GeminiAutomationService()
    response = (
        '{\n'
        '  "metadata": {"video_title": "Test"},\n'
        '  "sources": [{"source_id": "source_1", "youtube_url": "https://youtube.com/watch?v=abc123", "label": "The label"}],\n'
        '  "rewrite_script": {"full_text": "Edward yêu cầu tôi đăng nhập vào tài khoản ngân hàng."},\n'
        '  "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:05,000", "text": "Please sign in to continue"}],\n'
        '  "video_segments": [{"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:05.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "A scene"}]'
        '\n}'
    )
    result = svc._extract_json(response)
    assert result, "extract_json should not be blocked by login keywords inside Gemini content"
    parsed = json.loads(result)
    assert "đăng nhập" in parsed["rewrite_script"]["full_text"]
    assert "sign in" in parsed["srt"][0]["text"]


def test_extract_json_still_rejects_short_login_page():
    """Response that is actually a login page (short, no JSON shape) must still fail extraction."""
    svc = GeminiAutomationService()
    response = "Vui lòng đăng nhập để sử dụng Gemini"
    result = svc._extract_json(response)
    assert not result, "Short login text should not extract as JSON"


def test_extract_json_still_rejects_real_login_page():
    """Longer login page text without a valid Gemini EDL root must still fail extraction."""
    svc = GeminiAutomationService()
    login_content = "Sign in to continue using Gemini\nPlease enter your credentials\n" + "x" * 300
    result = svc._extract_json(login_content)
    assert not result, "Login page without JSON shape should not extract"
