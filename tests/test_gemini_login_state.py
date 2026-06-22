import asyncio
import json
from pathlib import Path

from app.core.config import settings
from app.services.gemini_automation import GeminiAutomationService


class FakeLocator:
    def __init__(self, count: int):
        self._count = count

    async def count(self) -> int:
        return self._count


class FakePage:
    def __init__(self, counts: dict[str, int]):
        self.counts = counts

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self.counts.get(selector, 0))


class FakeContext:
    def __init__(self, cookies: list[dict] | None = None):
        self._cookies = cookies or []
        self.saved_paths: list[str] = []

    async def cookies(self) -> list[dict]:
        return self._cookies

    async def storage_state(self, path: str) -> None:
        self.saved_paths.append(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({"cookies": self._cookies}), encoding="utf-8")


def _detect(page: FakePage, context: FakeContext) -> dict:
    return asyncio.run(GeminiAutomationService()._detect_gemini_login_state(page, context))


def test_detect_gemini_login_state_by_cookies():
    state = _detect(FakePage({}), FakeContext([{"name": "SAPISID", "value": "x"}]))

    assert state["logged_in"] is True
    assert state["method"] == "cookies"
    assert state["needs_login"] is False
    assert state["cookie_ok"] is True


def test_detect_gemini_login_state_by_chat_area():
    state = _detect(FakePage({"[role='textbox']": 1}), FakeContext())

    assert state["logged_in"] is True
    assert state["method"] == "chat_area"
    assert state["chat_area_ok"] is True


def test_detect_gemini_login_state_by_avatar():
    state = _detect(FakePage({"[data-test-id='user-avatar']": 1}), FakeContext())

    assert state["logged_in"] is True
    assert state["method"] == "avatar"
    assert state["avatar_ok"] is True


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


def test_session_status_without_file_does_not_overclaim_live_login(tmp_path, monkeypatch):
    session_path = tmp_path / "gemini_session.json"
    monkeypatch.setattr(settings, "gemini_session_path", session_path)

    status = GeminiAutomationService().get_session_status()

    assert status["exists"] is False
    assert status["session_file_exists"] is False
    assert status["has_auth_cookies"] is False
    assert status["live_checked"] is False
    assert "No saved" in status["message"]


def test_session_status_with_auth_cookie_does_not_overclaim_live_login(tmp_path, monkeypatch):
    session_path = tmp_path / "gemini_session.json"
    session_path.write_text(json.dumps({"cookies": [{"name": "SAPISID", "value": "x"}]}), encoding="utf-8")
    monkeypatch.setattr(settings, "gemini_session_path", session_path)

    status = GeminiAutomationService().get_session_status()

    assert status["exists"] is True
    assert status["session_file_exists"] is True
    assert status["has_auth_cookies"] is True
    assert status["live_checked"] is False
    assert "live Gemini login is verified during auto pipeline" in status["message"]
