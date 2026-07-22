from __future__ import annotations

import asyncio
import math
import json
import logging
import os
import re
import sys
import time
import uuid
import urllib.parse
from pathlib import Path
from collections.abc import Awaitable
from typing import Any, Callable

from app.core.config import settings
from app.schemas.prompt import PromptGenerateRequest
from app.schemas.render import RenderOptions
from app.services.fingerprint import build_init_script, generate_fingerprint
from app.services.json_validator import JsonValidator, loads_json_with_repair
from app.services.prompt_generator import PromptGenerator
from app.services.pipeline_telemetry import PipelineTelemetry
from app.services.video_tools import ui_safe_error, write_playwright_storage_cookies_to_netscape

logger = logging.getLogger(__name__)

STEP_LABELS: dict[str, str] = {
    "init": "Khởi tạo",
    "init_browser": "Khởi tạo Chromium",
    "navigate_gemini": "Truy cập Gemini",
    "checking_login": "Kiểm tra đăng nhập Gemini",
    "wait_login": "Đăng nhập Gemini",
    "submitting_prompt": "Gửi prompt",
    "waiting_response": "Gemini trả lời",
    "analyzing_source": "Phân tích video",
    "validating_analysis": "Kiểm tra phân tích",
    "building_final_prompt": "Tạo prompt final",
    "scouting_timeline": "Lập timeline",
    "analyzing_chapter": "Phân tích chapter",
    "auditing_coverage": "Kiểm tra coverage",
    "planning_duration": "Lập strategy",
    "assembling_story": "Lập story assembly",
    "generating_chunk": "Tạo EDL chunk",
    "merging_final": "Ghép JSON final",
    "auditing_alignment": "Audit khớp cảnh",
    "repairing_chunk": "Repair chunk",
    "extracting_json": "Trích xuất dữ liệu",
    "cleanup_gemini": "Hoàn tất xử lý",
    "validating": "Kiểm tra dữ liệu",
    "auto_retry": "Thử lại",
    "submitting_render": "Tạo video",
    "cancelling": "Đang hủy",
}

# Minimum segments in Gemini response for it to be considered a real video plan.
# Fallback responses (Gemini could not access source video) typically return 1-4 segments.
MIN_GEMINI_RESPONSE_SEGMENTS = 5

GEMINI_SELECTORS = {
    "prompt_input": [
        "div[contenteditable='true']",
        "[role='textbox']",
        "textarea",
    ],
    "send_button": [
        "button[aria-label*='Send']",
        "button[aria-label*='Gửi']",
        "button[data-test-id='send-button']",
        "button.send-button",
        "button[class*='send']",
        "button:has(svg[data-icon='send'])",
        "button:has(svg[aria-label='Send'])",
    ],
    "stop_button": [
        "button[aria-label*='Stop']",
        "button[aria-label*='stop']",
        "button[aria-label*='Dừng']",
        "button[aria-label*='dừng']",
        "button:has-text('Stop')",
        "button:has-text('Dừng')",
        "button[class*='stop']",
        "[data-test-id='stop-generation']",
        "button:has(svg[data-icon='stop'])",
        "button:has(svg[aria-label='Stop'])",
    ],
    "sign_in_indicators": [
        "a[href*='signin']",
        "button:has-text('Sign in')",
        "button:has-text('Đăng nhập')",
        "button:has-text('Log in')",
        "a:has-text('Sign in')",
        "a:has-text('Đăng nhập')",
    ],
    "user_avatar": [
        "img[alt*='avatar']",
        "img[alt*='profile']",
        "button[data-test-id*='avatar']",
        "[data-test-id='user-avatar']",
        "a[href*='SignOut']",
    ],
    "chat_area": [
        "[role='textbox']",
        "div[contenteditable='true']",
        "textarea",
    ],
    "thinking_dropdown": [
        "[data-test-id='logo-pill-label-container']",
    ],
    "thinking_submenu_trigger": [
        "//gem-menu-item-content[.//span[@class='label' and contains(text(),'tư duy')]]",
        "gem-menu-item-content:has(span.label:text('tư duy'))",
    ],
    "thinking_item_extended": [
        "//gem-menu-item-content[.//span[@class='label' and contains(text(),'Mở rộng')]]",
        "gem-menu-item-content:has(span.label:text('Mở rộng'))",
    ],
    "thinking_verify_extended": [
        ".picker-secondary-text",
    ],
    "model_pill": [
        "span.picker-primary-text",
    ],
    "model_picker_button": [
        "[data-test-id='bard-mode-menu-button']",
    ],
    "model_verify": [
        "span.picker-primary-text",
    ],
}

GEMINI_MODEL_OPTIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "gemini-3.6-flash",
        "label": "3.6 Flash",
        "aliases": ("3.6 Flash",),
    },
    {
        "key": "gemini-3.5-flash-lite",
        "label": "3.5 Flash-Lite",
        "aliases": ("3.5 Flash-Lite",),
    },
    {
        "key": "gemini-3.1-pro",
        "label": "3.1 Pro",
        "aliases": ("3.1 Pro",),
    },
)

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"

_MODEL_BY_KEY: dict[str, dict[str, Any]] = {opt["key"]: opt for opt in GEMINI_MODEL_OPTIONS}

GEMINI_THINKING_MODE_LABELS: dict[str, list[str]] = {
    "extended": ["Mở rộng", "Extended"],
    "standard": ["Tiêu chuẩn", "Standard"],
}

GEMINI_THINKING_SECTION_LABELS: list[str] = [
    "Cấp độ tư duy",
    "Thinking level",
]


class GeminiAutomationTask:
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.step = "init"
        self.status = "running"
        self.message = "Đang khởi tạo..."
        self.detail: Any = None
        self.result: dict | None = None
        self.error: str | None = None
        self.cancel_requested = False
        self.gemini_model: str = DEFAULT_GEMINI_MODEL
        self.telemetry = PipelineTelemetry()
        self._render_job_id: str | None = None
        self._context: Any = None
        self.states: list[dict] = [
            {"step": "init", "label": "Khởi tạo", "status": "running", "start_ts": time.time(), "end_ts": None},
        ]
        self._event = asyncio.Event()

    def _push_state(self, step: str) -> None:
        now = time.time()
        if self.states:
            prev = self.states[-1]
            if prev["step"] == step and prev["status"] == "running":
                self._event.set()
                return
            if prev["end_ts"] is None:
                prev["end_ts"] = now
            if prev["status"] == "running":
                prev["status"] = "done"
        self.states.append({
            "step": step,
            "label": STEP_LABELS.get(step, step),
            "status": "running",
            "start_ts": now,
            "end_ts": None,
        })

    def update(self, step: str, message: str, detail: Any = None) -> None:
        self.step = step
        self.message = message
        self.detail = detail
        self._push_state(step)
        self._event.set()

    def mark_done(self, result: dict) -> None:
        self.status = "done"
        self.step = "complete"
        self.message = "Hoàn tất!"
        self.result = result
        if self.states:
            cur = self.states[-1]
            if cur["end_ts"] is None:
                cur["end_ts"] = time.time()
            if cur["status"] == "running":
                cur["status"] = "done"
        self._event.set()

    def _cancel_submitted_render(self, cancel_fn: Callable[[str], None] | None) -> None:
        if self._render_job_id and cancel_fn:
            try:
                cancel_fn(self._render_job_id)
                logger.warning("Cancelled render job %s for task %s", self._render_job_id, self.task_id)
            except Exception:
                logger.exception("Failed to cancel render job %s", self._render_job_id)
            self._render_job_id = None

    def mark_error(
        self,
        error: str,
        _cancel_render_fn: Callable[[str], None] | None = None,
        public_error: str | None = None,
    ) -> None:
        self._cancel_submitted_render(_cancel_render_fn)
        self.status = "error"
        self.step = "error"
        visible_error = public_error or error
        self.message = visible_error
        self.error = visible_error
        if self.states:
            cur = self.states[-1]
            if cur["end_ts"] is None:
                cur["end_ts"] = time.time()
            cur["status"] = "error"
        logger.error("Gemini task %s error [step=%s]: %s", self.task_id, self.step, error)
        self._event.set()

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "step": self.step,
            "status": self.status,
            "message": self.message,
            "detail": self.detail,
            "result": self.result,
            "error": self.error,
            "states": self.states,
            "telemetry": self.telemetry.snapshot(),
        }

    async def wait_for_update(self, timeout: float = 2.0) -> bool:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
            self._event.clear()
            return True
        except asyncio.TimeoutError:
            return False


class GeminiAutomationService:
    _tasks: dict[str, GeminiAutomationTask] = {}
    _submit_render_fn: Callable[[dict, str], Awaitable[str]] | None = None
    _cancel_render_fn: Callable[[str], None] | None = None
    _browsers: dict[str, dict] = {}
    _browser_tasks: dict[str, asyncio.Task] = {}
    _last_session_status: dict | None = None

    @staticmethod
    def _browser_entry_is_open(entry: dict) -> bool:
        if entry.get("status") not in {"launching", "open"}:
            return False
        page = entry.get("page")
        if page is not None:
            try:
                if page.is_closed():
                    return False
            except Exception:
                pass
        if entry.get("is_persistent"):
            context = entry.get("context")
            if context is not None:
                try:
                    if hasattr(context, "pages") and len(context.pages) == 0:
                        return False
                except Exception:
                    pass
            return True
        browser = entry.get("browser")
        if browser is not None:
            try:
                if hasattr(browser, "is_connected") and not browser.is_connected():
                    return False
            except Exception:
                pass
        return True

    def _active_standalone_browser_id(self) -> str | None:
        stale_browser_ids: list[str] = []
        for browser_id, entry in self._browsers.items():
            if self._browser_entry_is_open(entry):
                return browser_id
            stale_browser_ids.append(browser_id)
        for browser_id in stale_browser_ids:
            self._mark_standalone_browser_closed(browser_id)
            self._browsers.pop(browser_id, None)
            self._browser_tasks.pop(browser_id, None)
        return None

    def _current_browser_status(self, browser_id: str | None = None) -> tuple[bool, str | None]:
        if browser_id:
            entry = self._browsers.get(browser_id)
            if entry and self._browser_entry_is_open(entry):
                return True, browser_id
            if entry:
                self._mark_standalone_browser_closed(browser_id)
                self._browsers.pop(browser_id, None)
                self._browser_tasks.pop(browser_id, None)
            return False, None
        active_browser_id = self._active_standalone_browser_id()
        return active_browser_id is not None, active_browser_id

    def _browser_is_open(self, browser_id: str | None) -> bool:
        if not browser_id:
            return False
        entry = self._browsers.get(browser_id)
        return bool(entry and self._browser_entry_is_open(entry))

    def set_submit_render_fn(self, fn: Callable[[dict, str], Awaitable[str]]) -> None:
        self._submit_render_fn = fn

    def set_cancel_render_fn(self, fn: Callable[[str], None]) -> None:
        self._cancel_render_fn = fn

    def _get_user_data_dir(self) -> str | None:
        return settings.gemini_user_data_dir

    @staticmethod
    def _resolve_user_data_dir(path: str | None) -> str | None:
        if not path:
            return None
        resolved = Path(path).expanduser().resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        return str(resolved)

    @staticmethod
    def _profile_dir(path: str) -> Path | None:
        p = Path(path)
        if not p.is_dir():
            return None
        parts = p.parts
        for i, part in enumerate(parts):
            if part == "User Data" and i + 1 < len(parts):
                return Path(*parts[: i + 2])
        for sub in ("Default",):
            candidate = p / sub
            if candidate.is_dir():
                return candidate
        return p

    @staticmethod
    def _extract_auth_cookies(profile_dir: Path) -> list[dict]:
        cookies_file = profile_dir / "Network" / "Cookies"
        if not cookies_file.is_file():
            cookies_file = profile_dir / "Cookies"
        if not cookies_file.is_file():
            return []
        import tempfile, shutil, sqlite3
        tmp = Path(tempfile.mkdtemp()) / "Cookies"
        try:
            shutil.copy2(str(cookies_file), str(tmp))
        except Exception:
            return []
        try:
            conn = sqlite3.connect(str(tmp))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT host_key, name, value, path, expires_utc, is_secure, is_httponly, has_expires "
                "FROM cookies WHERE host_key LIKE '%google.com' "
                "AND name IN ('SAPISID', '__Secure-3PSAPISID', 'OSID')"
            )
            rows = cur.fetchall()
            conn.close()
            result = []
            for r in rows:
                domain = r["host_key"]
                if domain.startswith("."):
                    domain = domain
                elif domain == "google.com":
                    domain = ".google.com"
                c: dict[str, Any] = {
                    "name": r["name"],
                    "value": r["value"],
                    "domain": domain,
                    "path": r["path"],
                    "secure": bool(r["is_secure"]),
                    "httpOnly": bool(r["is_httponly"]),
                }
                if r["has_expires"] and r["expires_utc"] and r["expires_utc"] > 0:
                    c["expires"] = r["expires_utc"] / 1_000_000 - 11644473600
                result.append(c)
            return result
        except Exception:
            return []
        finally:
            try:
                import shutil as _su
                _su.rmtree(str(tmp.parent), ignore_errors=True)
            except Exception:
                pass

    @staticmethod
    def _stealth_seed(user_data_dir: str | None, auth_cookies: list[dict]) -> str:
        parts = [user_data_dir or str(settings.gemini_profile_path)]
        for c in auth_cookies:
            if c['name'] in ('SAPISID', '__Secure-3PSAPISID'):
                parts.append(c['value'][:16])
                break
        return '|'.join(parts)

    async def _launch_stealth_context(
        self,
        pw: Any,
        user_data_dir: str | None = None,
        auth_cookies: list[dict] | None = None,
        headless: bool = True,
        storage_state_path: str | Path | None = None,
        persistent: bool = False,
        persistent_profile_path: str | Path | None = None,
    ) -> tuple[Any, Any, Any]:

        ac = auth_cookies or []
        seed = self._stealth_seed(user_data_dir, ac)
        fp = generate_fingerprint(seed)
        stealth_js = build_init_script(fp)
        args = [
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
        ]
        if headless:
            args.append('--headless')

        if persistent:
            profile = str(persistent_profile_path or settings.gemini_profile_path)
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=profile,
                headless=headless,
                args=args,
                user_agent=fp['user_agent'],
                locale=fp['lang'],
            )
            page = context.pages[0] if context.pages else await context.new_page()
            page.set_default_timeout(60000)
            await context.add_init_script(stealth_js)
            if storage_state_path:
                try:
                    ss_data = json.loads(Path(storage_state_path).read_text(encoding="utf-8"))
                    ss_cookies = ss_data.get("cookies", [])
                    if ss_cookies:
                        await context.add_cookies(ss_cookies)
                    for origin_entry in ss_data.get("origins", []):
                        origin = origin_entry.get("origin")
                        storage = origin_entry.get("localStorage", [])
                        if origin and storage:
                            page_for_storage = page
                            try:
                                page_for_storage = context.pages[0] if context.pages else page
                                if page_for_storage.url == "about:blank":
                                    await page_for_storage.goto(origin, wait_until="domcontentloaded", timeout=10000)
                                for item in storage:
                                    await page_for_storage.evaluate(
                                        "({name, value}) => window.localStorage.setItem(name, value)", item
                                    )
                            except Exception:
                                pass
                except Exception as exc:
                    logger.warning("Failed to import storage_state into persistent context: %s", exc)
            elif ac:
                try:
                    await context.add_cookies(ac)
                except Exception as exc:
                    logger.warning("Failed to import auth cookies into persistent context: %s", exc)
            return None, context, page

        launch_kwargs: dict[str, Any] = {
            'headless': headless,
            'args': args,
        }
        browser = await pw.chromium.launch(**launch_kwargs)
        ctx_kwargs: dict[str, Any] = {
            'user_agent': fp['user_agent'],
            'viewport': {'width': fp['window_width'], 'height': fp['window_height']},
            'locale': fp['lang'],
        }
        if storage_state_path:
            ctx_kwargs['storage_state'] = str(storage_state_path)
        context = await browser.new_context(**ctx_kwargs)
        await context.add_init_script(stealth_js)
        if ac and not storage_state_path:
            await context.add_cookies(ac)
        page = await context.new_page()
        page.set_default_timeout(60000)
        return browser, context, page

    def get_session_status(self) -> dict:
        session_path = Path(settings.gemini_session_path)

        if self._last_session_status and self._last_session_status.get("path") == str(session_path):
            self._current_browser_status(self._last_session_status.get("browser_id"))

        disk = self._session_disk_info(session_path)
        browser_open, browser_id = self._current_browser_status()

        if self._last_session_status and self._last_session_status.get("path") == str(session_path):
            current = dict(self._last_session_status)
            current["browser_open"] = browser_open
            current["browser_id"] = browser_id
            current["session_file_exists"] = disk["session_file_exists"]
            current["has_auth_cookies"] = disk["has_auth_cookies"]
            current["auth_cookies_active"] = disk.get("auth_cookies_active", False)
            cached_browser_id = self._last_session_status.get("browser_id")
            if cached_browser_id and (not browser_open or cached_browser_id != browser_id):
                current["exists"] = False
                current["live_checked"] = False
                current["method"] = "unknown"
                current["needs_login"] = disk.get("needs_login", True)
                if disk.get("auth_cookies_active"):
                    current["message"] = "Đã có session Gemini đã lưu. Mở Gemini để xác minh lại đăng nhập."
                elif disk["session_file_exists"]:
                    current["message"] = "Session file exists but has invalid or expired cookies."
                else:
                    current["message"] = "Chưa có session Gemini."
            self._last_session_status = current
            return dict(self._last_session_status)

        result = {
            "exists": False,
            **disk,
            "live_checked": False,
            "browser_open": browser_open,
            "browser_id": browser_id,
            "path": str(session_path),
            "method": "unknown",
        }
        if not disk["session_file_exists"]:
            result["message"] = "Chưa có session Gemini."
        elif disk.get("auth_cookies_active"):
            result["message"] = "Đã có session Gemini đã lưu. Mở Gemini để xác minh lại đăng nhập."
        else:
            result["message"] = "Session file exists but has invalid or expired cookies."
        return result

    def _set_live_session_status(self, session_path: Path, login_state: dict, *, browser_id: str | None = None, force: bool = False) -> None:
        logged_in = bool(login_state.get("logged_in"))
        method = login_state.get("method", "unknown")
        previous_verified = bool(
            self._last_session_status
            and self._last_session_status.get("path") == str(session_path)
            and self._last_session_status.get("exists")
            and self._last_session_status.get("live_checked")
        )
        if previous_verified and not logged_in and not force:
            if method == "signin":
                logger.info(
                    "Live check detects sign-in page — downgrading session status. "
                    "session_path=%s method=%s signin_indicator=%s",
                    session_path, method, login_state.get("signin_indicator"),
                )
            else:
                current = dict(self._last_session_status or {})
                current.update({
                    "browser_open": self._current_browser_status(browser_id)[0],
                    "browser_id": self._current_browser_status(browser_id)[1],
                    "method": current.get("method", "verified"),
                })
                self._last_session_status = current
                return
        self._last_session_status = {
            "exists": logged_in,
            "session_file_exists": session_path.exists(),
            "has_auth_cookies": bool(login_state.get("cookie_ok")),
            "live_checked": True,
            "needs_login": not logged_in,
            "browser_open": self._browser_is_open(browser_id),
            "browser_id": browser_id,
            "path": str(session_path),
            "message": "Đã xác minh đăng nhập Gemini thành công." if logged_in else "Session Gemini đã lưu hết hạn hoặc chưa đăng nhập. Vui lòng đăng nhập lại trên trình duyệt vừa mở.",
            "method": method,
        }

    def _mark_standalone_browser_closed(self, browser_id: str) -> None:
        if browser_id in self._browsers:
            self._browsers[browser_id]["status"] = "closed"
        if not self._last_session_status:
            return
        current = dict(self._last_session_status)
        if current.get("browser_id") == browser_id:
            current["browser_open"] = False
            current["browser_id"] = None
            current["exists"] = False
            current["live_checked"] = False
            current["needs_login"] = True
            current["method"] = "unknown"
            disk = self._session_disk_info(Path(current.get("path", settings.gemini_session_path)))
            current.update(disk)
            current["needs_login"] = disk.get("needs_login", True)
            if disk["session_file_exists"]:
                current["message"] = "Đã có session Gemini đã lưu. Mở Gemini để xác minh lại đăng nhập."
            else:
                current["message"] = "Chưa có session Gemini."
            self._last_session_status = current

    def _mark_session_needs_reverify(self) -> None:
        if not self._last_session_status:
            return
        current = dict(self._last_session_status)
        current["exists"] = False
        current["live_checked"] = False
        current["needs_login"] = current.get("needs_login", True)
        current["method"] = "unknown"
        current["message"] = "Gemini timeout; cần xác minh lại session hoặc khôi phục từ Chrome profile."
        self._last_session_status = current

    async def _save_session_state(self, context: Any, session_path: Path, *, strict: bool = False) -> bool:
        try:
            session_path.parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(session_path))
            return True
        except Exception as exc:
            logger.warning("Failed to save Gemini session to %s: %s", session_path, exc)
            if strict:
                raise
            return False

    async def _capture_youtube_cookies(self, context: Any, session_path: Path) -> bool:
        """Navigate to YouTube in a hidden tab to capture YouTube cookies into session."""
        try:
            yt_page = await context.new_page()
            await yt_page.goto("https://www.youtube.com/", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1.5)
            await self._save_session_state(context, session_path)
            logger.info("YouTube cookie capture: session saved after navigating youtube.com")
            await yt_page.close()
            return True
        except Exception as exc:
            logger.warning("YouTube cookie capture failed (non-fatal): %s", exc)
            return False

    async def _export_youtube_cookies(self, session_path: Path) -> bool:
        """Convert Playwright storage_state to Netscape cookies.txt for yt-dlp."""
        try:
            output_path = Path(settings.outputs_dir).parent / "data" / "cookies" / "cookies.txt"
            health = write_playwright_storage_cookies_to_netscape(session_path, output_path)
            logger.info(
                "YouTube cookies export: valid=%s path=%s total=%d youtube=%d auth=%d strong=%s",
                health.valid, output_path, health.total_cookies,
                health.youtube_cookies, health.auth_cookies, health.has_strong_auth,
            )
            return health.valid
        except Exception as exc:
            logger.warning("YouTube cookies export failed (non-fatal): %s", exc)
            return False

    async def open_standalone_browser(self, user_data_dir: str | None = None) -> str:
        active_browser_id = self._active_standalone_browser_id()
        if active_browser_id:
            return active_browser_id
        browser_id = str(uuid.uuid4())
        self._browsers[browser_id] = {"status": "launching"}
        launch_ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        task = asyncio.create_task(self._run_standalone_browser(browser_id, user_data_dir, launch_ready))
        self._browser_tasks[browser_id] = task
        try:
            await asyncio.wait_for(launch_ready, timeout=30)
        except asyncio.TimeoutError as exc:
            logger.error("Timed out waiting for Gemini browser launch confirmation")
            if not task.done():
                task.cancel()
            self._mark_standalone_browser_closed(browser_id)
            self._browsers.pop(browser_id, None)
            self._browser_tasks.pop(browser_id, None)
            raise RuntimeError("Quá thời gian chờ mở trình duyệt Gemini.") from exc
        except Exception:
            if not task.done():
                task.cancel()
            self._mark_standalone_browser_closed(browser_id)
            self._browsers.pop(browser_id, None)
            self._browser_tasks.pop(browser_id, None)
            raise
        return browser_id

    async def _run_standalone_browser(
        self,
        browser_id: str,
        user_data_dir: str | None = None,
        launch_ready: asyncio.Future[None] | None = None,
    ) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.exception("playwright not installed")
            if launch_ready and not launch_ready.done():
                launch_ready.set_exception(RuntimeError("Playwright chưa được cài đặt."))
            return

        try:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                if asyncio.BaseEventLoop._make_subprocess_transport.__qualname__.startswith("BaseEventLoop"):
                    from asyncio.windows_events import ProactorEventLoop
                    asyncio.BaseEventLoop._make_subprocess_transport = ProactorEventLoop._make_subprocess_transport
            async with async_playwright() as pw:
                browsers_path = settings.playwright_browsers_path
                if browsers_path:
                    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path

                session_path = Path(settings.gemini_session_path)
                session_info = self._session_disk_info(session_path)
                profile_path = Path(settings.gemini_profile_path)
                profile_path.mkdir(parents=True, exist_ok=True)
                executable_path = getattr(pw.chromium, "executable_path", None)
                logger.info(
                    "Opening Gemini browser: profile=%s executable=%s headless=%s",
                    profile_path,
                    executable_path or "<default>",
                    False,
                )
                logger.info(
                    "Gemini session status before launch: session_path=%s exists=%s active=%s",
                    session_path, session_path.exists(), session_info.get("auth_cookies_active"),
                )

                auth_cookies: list[dict] = []
                resolved_user_data_dir = self._resolve_user_data_dir(user_data_dir)
                if resolved_user_data_dir and not session_info.get("auth_cookies_active"):
                    pd = self._profile_dir(resolved_user_data_dir)
                    if pd:
                        auth_cookies = self._extract_auth_cookies(pd)
                        logger.info("Extracted %d auth cookies from %s (fallback)", len(auth_cookies), pd)

                storage_state_path = session_path if session_info.get("auth_cookies_active") else None
                browser, context, page = await self._launch_stealth_context(
                    pw, resolved_user_data_dir, auth_cookies, headless=False,
                    storage_state_path=storage_state_path,
                    persistent=True,
                    persistent_profile_path=profile_path,
                )

                self._browsers[browser_id] = {
                    "status": "open",
                    "browser": browser,
                    "context": context,
                    "page": page,
                    "is_persistent": True,
                }
                if launch_ready and not launch_ready.done():
                    launch_ready.set_result(None)

                self._set_pending_status(session_path, browser_id)

                await page.goto(settings.gemini_url, wait_until="domcontentloaded")

                try:
                    await page.wait_for_load_state("load", timeout=10000)
                except Exception as exc:
                    if "Timeout" in type(exc).__name__:
                        logger.debug("Load wait timeout (continuing): %s", exc)
                    else:
                        logger.warning("Unexpected error during load wait: %s", exc)

                login_state = await self._detect_gemini_login_state(page, context)
                logger.info(
                    "Gemini live verification result: logged_in=%s method=%s cookie_ok=%s "
                    "chat_area_ok=%s avatar_ok=%s signin_indicator=%s",
                    login_state["logged_in"], login_state["method"],
                    login_state["cookie_ok"], login_state["chat_area_ok"],
                    login_state["avatar_ok"], login_state["signin_indicator"],
                )
                self._set_live_session_status(session_path, login_state, browser_id=browser_id, force=True)
                if login_state["logged_in"]:
                    await self._save_session_state(context, session_path)
                    await self._capture_youtube_cookies(context, session_path)
                    self._set_live_session_status(session_path, login_state, browser_id=browser_id)

                async def _save_loop():
                    saved_logged_in = login_state["logged_in"]
                    last_save = time.time() if saved_logged_in else 0.0
                    while True:
                        await asyncio.sleep(2)
                        try:
                            state = await self._detect_gemini_login_state(page, context)
                            self._set_live_session_status(session_path, state, browser_id=browser_id)
                            if state["logged_in"] and (not saved_logged_in or time.time() - last_save >= 30):
                                if await self._save_session_state(context, session_path):
                                    last_save = time.time()
                                self._set_live_session_status(session_path, state, browser_id=browser_id)
                                saved_logged_in = True
                        except Exception:
                            return

                save_task = asyncio.create_task(_save_loop())

                closed = asyncio.Event()
                context.on("close", lambda *args: closed.set())
                page.on("close", lambda *args: closed.set())
                await closed.wait()

                save_task.cancel()
                try:
                    await save_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
                await self._save_session_state(context, session_path)
                await self._export_youtube_cookies(session_path)
                try:
                    await context.close()
                except Exception:
                    pass

        except asyncio.CancelledError:
            if launch_ready and not launch_ready.done():
                launch_ready.set_exception(RuntimeError("Đã hủy mở trình duyệt Gemini."))
            pass
        except Exception:
            logger.exception("Standalone browser failed")
            if launch_ready and not launch_ready.done():
                launch_ready.set_exception(RuntimeError("Không thể mở trình duyệt Gemini. Xem log backend để biết chi tiết."))
        finally:
            self._mark_standalone_browser_closed(browser_id)
            self._browsers.pop(browser_id, None)
            self._browser_tasks.pop(browser_id, None)

    async def close_standalone_browser(self, browser_id: str) -> bool:
        entry = self._browsers.pop(browser_id, None)
        self._mark_standalone_browser_closed(browser_id)
        if entry:
            target = entry.get("context") if entry.get("is_persistent") else entry.get("browser")
            if target:
                try:
                    await target.close()
                    return True
                except Exception:
                    return False
        return False

    def start(self, task_id: str, prompt_text: str, render_payload: dict, user_data_dir: str | None = None,
              headless: bool | None = None, thinking_mode: str = "extended",
              model: str = DEFAULT_GEMINI_MODEL,
              form_data: dict | None = None,
              dry_run: bool = False) -> GeminiAutomationTask:
        task = GeminiAutomationTask(task_id)
        task.gemini_model = model
        self._tasks[task_id] = task
        ud = user_data_dir or self._get_user_data_dir()
        asyncio.create_task(self._run_pipeline(task, prompt_text, render_payload, ud, headless, thinking_mode, form_data, dry_run))
        return task

    def get_task(self, task_id: str) -> GeminiAutomationTask | None:
        return self._tasks.get(task_id)

    def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        # Cancel submitted render job regardless of task status
        if task._render_job_id and self._cancel_render_fn:
            try:
                self._cancel_render_fn(task._render_job_id)
                logger.warning("Cancelled render job %s for task %s", task._render_job_id, task.task_id)
                task._render_job_id = None
            except Exception:
                logger.exception("Failed to cancel render job %s", task._render_job_id)
        # Force-close Playwright context to release Chrome profile lock
        if task._context:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(task._context.close())
                else:
                    loop.run_until_complete(task._context.close())
            except Exception:
                logger.exception("Failed to close Playwright context on cancel")
        if task.status == "running":
            task.cancel_requested = True
            task.update("cancelling", "Đang hủy...")
        return True

    async def _run_pipeline(self, task: GeminiAutomationTask, prompt_text: str, render_payload: dict,
                            user_data_dir: str | None = None, headless: bool | None = None,
                            thinking_mode: str = "extended",
                            form_data: dict | None = None, dry_run: bool = False) -> None:
        # model is already set on task.gemini_model by start()
        browser = None
        context = None
        # Auto Pipeline never exposes its working browser. Interactive login is
        # handled separately by the explicit session-verification action.
        headless_resolved = True

        active_browser_id = self._active_standalone_browser_id()
        if active_browser_id:
            task.mark_error(
                "Gemini browser đang mở. Vui lòng đóng Gemini browser trước khi chạy Auto Pipeline."
            )
            return

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as pw:
                browsers_path = settings.playwright_browsers_path
                if browsers_path:
                    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path

                task.update("init_browser", "Đang khởi tạo Chromium...")
                if task.cancel_requested:
                    task.mark_done({"cancelled": True})
                    return

                session_path = Path(settings.gemini_session_path)
                session_info = self._session_disk_info(session_path)
                profile_path = Path(settings.gemini_profile_path)
                profile_path.mkdir(parents=True, exist_ok=True)

                needs_login_fallback = not session_info.get("auth_cookies_active") and not user_data_dir

                if session_info.get("auth_cookies_active"):
                    task.update("navigate_gemini", "Đang khởi tạo phiên làm việc đã lưu...")
                    logger.info("Pipeline using saved Gemini session from %s", session_path)
                    browser, context, page = await self._launch_stealth_context(
                        pw, user_data_dir, headless=headless_resolved,
                        storage_state_path=session_path,
                        persistent=True,
                        persistent_profile_path=profile_path,
                    )
                    task._context = context
                elif user_data_dir:
                    pd = self._profile_dir(user_data_dir)
                    auth_cookies = self._extract_auth_cookies(pd) if pd else []
                    logger.info("Pipeline extracted %d auth cookies from Chrome profile %s", len(auth_cookies), pd)
                    if auth_cookies:
                        task.update("navigate_gemini", "Đã nạp cookies từ Chrome profile.")
                        browser, context, page = await self._launch_stealth_context(
                            pw, user_data_dir, auth_cookies, headless=headless_resolved,
                            persistent=True,
                            persistent_profile_path=profile_path,
                        )
                        task._context = context
                    else:
                        task.update("navigate_gemini", "Đang khởi tạo phiên mới...")
                        browser, context, page = await self._launch_stealth_context(
                            pw, headless=headless_resolved,
                            persistent=True,
                            persistent_profile_path=profile_path,
                        )
                        task._context = context
                else:
                    task.mark_error(
                        "Gemini chưa được xác minh đăng nhập. Hãy bấm 'Mở trình duyệt Gemini' "
                        "để xác minh trước khi chạy Auto Pipeline."
                    )
                    return

                task.update("navigate_gemini", "Đang truy cập Gemini...")
                await page.goto(settings.gemini_url, wait_until="domcontentloaded")

                task.update("checking_login", "Đang kiểm tra phiên đăng nhập Gemini...")
                if headless_resolved and not needs_login_fallback:
                    try:
                        await page.wait_for_load_state("load", timeout=10000)
                    except Exception:
                        pass
                    login_state = await self._detect_gemini_login_state(page, context)
                    if not login_state["logged_in"]:
                        recovered = await self._recover_login_from_chrome_profile(
                            task, pw, page, context, session_path, profile_path, user_data_dir, headless_resolved
                        )
                        if recovered is not None:
                            browser, context, page = recovered
                            login_state = await self._detect_gemini_login_state(page, context)
                    if not login_state["logged_in"]:
                        activated = await self._auto_activate_gemini_login(
                            task, pw, context, session_path, profile_path, user_data_dir, headless_resolved
                        )
                        if activated is not None:
                            browser, context, page = activated
                            login_state = await self._detect_gemini_login_state(page, context)
                else:
                    await self._handle_login_if_needed(task, page, context, session_path, headless=False if needs_login_fallback else headless_resolved)
                    if task.status != "running":
                        return
                    login_state = await self._detect_gemini_login_state(page, context)
                if not login_state["logged_in"]:
                    task.mark_error(
                        "Gemini session hết hiệu lực và Chrome profile không cung cấp cookies đăng nhập usable. "
                        "Hãy bấm Open Browser một lần để xác minh lại."
                    )
                    return

                simple_pass_started = time.perf_counter()
                simple_submit_count = 1
                await self._submit_prompt(task, page, context, prompt_text, thinking_mode)
                if task.status != "running":
                    return

                response_text = await self._wait_for_response(task, page, context)
                await asyncio.sleep(0)  # yield → WS handler thấy "waiting_response"
                if not self._record_audit_exchange(task, prompt_text, response_text, "exchange_001"):
                    task.mark_error(
                        "GEMINI_AUDIT_PERSIST_FAILED: không thể lưu response Gemini vào backend audit storage.",
                        public_error="Không thể hoàn tất xử lý. Vui lòng thử lại.",
                    )
                    return

                json_str = ""
                fallback_detected = False
                fallback_segment_count = 0
                for submit_attempt in range(2):
                    should_resubmit = submit_attempt > 0 or not response_text
                    if should_resubmit:
                        if not response_text:
                            logger.warning(
                                "Gemini response wait returned empty for task %s; re-submitting prompt.",
                                task.task_id,
                            )
                            task.update("submitting_prompt", "Gemini vừa reload. Đang gửi lại prompt...")
                        await self._submit_prompt(task, page, context, prompt_text, thinking_mode)
                        simple_submit_count += 1
                        if task.status != "running":
                            return
                        response_text = await self._wait_for_response(task, page, context)
                        await asyncio.sleep(0)
                        if not self._record_audit_exchange(task, prompt_text, response_text, f"exchange_{submit_attempt + 1:03d}"):
                            task.mark_error(
                                "GEMINI_AUDIT_PERSIST_FAILED: không thể lưu response Gemini vào backend audit storage.",
                                public_error="Không thể hoàn tất xử lý. Vui lòng thử lại.",
                            )
                            return

                    for retry in range(3):
                        if task.status != "running":
                            return
                        msg = f"Đang trích xuất JSON (lần {retry + 1}/3)"
                        if submit_attempt > 0:
                            msg += f", gửi lại lần {submit_attempt + 1}/2"
                        task.update("extracting_json", f"{msg}...")
                        await asyncio.sleep(0)
                        if self._response_indicates_source_access_failure(response_text):
                            await self._save_raw_debug(task, response_text, "source_access_failure")
                            task.mark_error(
                                "Gemini có vẻ không xem được video nguồn mà đang suy luận từ URL/tiêu đề. "
                                "Đã dừng để tránh render sai. Hãy thử gửi lại hoặc kiểm tra Gemini có truy cập được video."
                            )
                            return
                        json_str = self._extract_json(response_text)
                        if json_str:
                            has_min_segments, segment_count = self._response_has_minimum_segments(json_str)
                            if has_min_segments:
                                break

                            fallback_detected = True
                            fallback_segment_count = segment_count
                            logger.warning(
                                "Gemini response for task %s has only %d video_segments (<%d); "
                                "treating as fallback, will retry.",
                                task.task_id,
                                segment_count,
                                MIN_GEMINI_RESPONSE_SEGMENTS,
                            )
                            await self._save_raw_debug(task, response_text, "too_few_segments")
                            if submit_attempt == 0:
                                task.update(
                                    "auto_retry",
                                    f"Gemini trả về quá ít segment ({segment_count}); đang gửi lại prompt...",
                                )
                            json_str = ""
                            break

                        if self._response_is_login_or_error(response_text):
                            if submit_attempt == 0 and retry == 0:
                                task.mark_error("Phản hồi từ Gemini không phải nội dung hợp lệ — có thể session đã hết hạn hoặc trang yêu cầu đăng nhập. Vui lòng mở trình duyệt và đăng nhập lại Gemini.", _cancel_render_fn=self._cancel_render_fn)
                            else:
                                task.mark_error("Phản hồi từ Gemini không phải nội dung hợp lệ — có thể session đã hết hạn hoặc trang yêu cầu đăng nhập.")
                            return

                        if retry < 2:
                            await asyncio.sleep(3)
                            response_text = await self._wait_for_response(task, page, context)

                    if json_str:
                        break

                if not json_str:
                    try:
                        debug_path = settings.temp_dir / "gemini_failed_response"
                        debug_path.mkdir(parents=True, exist_ok=True)
                        (debug_path / f"{task.task_id}_raw.txt").write_text(response_text[:10000] if response_text else "", encoding="utf-8")
                        logger.warning("Gemini JSON extraction failed for task %s. Raw response saved to %s", task.task_id, debug_path / f"{task.task_id}_raw.txt")
                    except Exception:
                        pass
                    if fallback_detected:
                        task.mark_error(
                            f"Gemini trả về nội dung quá ngắn ({fallback_segment_count} video segment) sau 2 lần thử. "
                            "Đây thường là dấu hiệu Gemini không xem được video nguồn hoặc đang trả về fallback. "
                            "Vui lòng kiểm tra URL/cookies/quyền truy cập video."
                        )
                    else:
                        task.mark_error("Không thể trích xuất JSON từ phản hồi Gemini sau 2 lần gửi prompt, mỗi lần 3 lần thử.")
                    return

                preflight_valid, preflight_errors, preflight_parsed = await self._validate_json_for_render(
                    task, json_str, render_payload
                )
                for repair_attempt in range(2):
                    if preflight_valid or task.status != "running":
                        break
                    repair_prompt = self._build_simple_edl_repair_prompt(preflight_errors)
                    task.update(
                        "auto_retry",
                        f"JSON chưa hợp lệ. Đang yêu cầu Gemini sửa (lần {repair_attempt + 1}/2)...",
                    )
                    await self._submit_prompt(task, page, context, repair_prompt, thinking_mode)
                    simple_submit_count += 1
                    if task.status != "running":
                        return
                    repaired_response = await self._wait_for_response(task, page, context)
                    await asyncio.sleep(0)
                    if not self._record_audit_exchange(
                        task,
                        repair_prompt,
                        repaired_response,
                        f"validation_repair_{repair_attempt + 1:03d}",
                    ):
                        task.mark_error(
                            "GEMINI_AUDIT_PERSIST_FAILED: không thể lưu response repair vào backend audit storage.",
                            public_error="Không thể hoàn tất xử lý. Vui lòng thử lại.",
                        )
                        return
                    repaired_json = self._extract_json(repaired_response)
                    if not repaired_json:
                        preflight_errors = ["Không thể trích xuất JSON hoàn chỉnh từ response repair."]
                        continue
                    json_str = repaired_json
                    response_text = repaired_response
                    preflight_valid, preflight_errors, preflight_parsed = await self._validate_json_for_render(
                        task, json_str, render_payload
                    )

                if preflight_valid and preflight_parsed is not None:
                    preflight_dump = (
                        preflight_parsed.model_dump()
                        if hasattr(preflight_parsed, "model_dump")
                        else preflight_parsed
                    )
                    if isinstance(preflight_dump, dict):
                        json_str = json.dumps(preflight_dump, ensure_ascii=False)

                if not self._record_audit_json(task, json_str):
                    task.mark_error(
                        "GEMINI_AUDIT_PERSIST_FAILED: không thể lưu JSON Gemini vào backend audit storage.",
                        public_error="Không thể hoàn tất xử lý. Vui lòng thử lại.",
                    )
                    return
                if dry_run:
                    await self._validate_without_render(task, json_str, render_payload)
                else:
                    await self._validate_and_render(task, json_str, render_payload)
                task.telemetry.record_gemini_pass(
                    name="simple_editor_edl",
                    attempt=simple_submit_count,
                    prompt_text=prompt_text,
                    response_text=response_text,
                    started_at=simple_pass_started,
                    valid=task.status == "done",
                    errors=[task.error] if task.error else [],
                )

        except asyncio.CancelledError:
            task.mark_error("Pipeline bị hủy.", _cancel_render_fn=self._cancel_render_fn)
        except TimeoutError as exc_to:
            self._mark_session_needs_reverify()
            msg = ui_safe_error(str(exc_to))
            task.mark_error(msg or "Gemini xử lý quá lâu, đã timeout an toàn.", _cancel_render_fn=self._cancel_render_fn)
        except Exception as exc:
            logger.exception("Gemini automation pipeline failed")
            msg = ui_safe_error(str(exc))
            if not msg:
                if isinstance(exc, NotImplementedError):
                    msg = "Không thể khởi động Playwright trên Windows khi backend chạy bằng uvicorn --reload. Hãy restart backend không dùng --reload."
                else:
                    msg = f"{type(exc).__name__}: lỗi nội bộ khi chạy Gemini automation."
            task.mark_error(msg, _cancel_render_fn=self._cancel_render_fn)
        finally:
            try:
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass
                elif browser:
                    try:
                        await browser.close()
                    except Exception:
                        pass
            finally:
                task._context = None

    async def _run_json_pass(
        self,
        task: GeminiAutomationTask,
        page: Any,
        context: Any,
        *,
        step: str,
        message: str,
        prompt_text: str,
        thinking_mode: str,
        extract_json_fn: Callable[[str], str],
        validate_fn: Callable[[object], tuple[bool, list[str], dict | None]],
        debug_prefix: str,
        attempts: int = 2,
    ) -> dict | None:
        response_text = ""
        last_errors: list[str] = []
        for submit_attempt in range(attempts):
            pass_started_at = time.perf_counter()
            effective_prompt = prompt_text
            if submit_attempt > 0 and last_errors:
                correction_lines = "\n".join(f"- {error}" for error in last_errors[:8])
                effective_prompt = (
                    f"{prompt_text}\n\n"
                    "CORRECTION REQUIRED — the previous JSON failed deterministic validation:\n"
                    f"{correction_lines}\n"
                    "Return the complete corrected JSON only. Preserve valid content, fix every listed error, "
                    "and do not add fields outside the requested schema."
                )
                await self._save_prompt_text(task, effective_prompt, f"{debug_prefix}_correction_{submit_attempt + 1}")
            task.update(step, f"{message} (lần {submit_attempt + 1}/{attempts})...")
            await self._submit_prompt(task, page, context, effective_prompt, thinking_mode)
            if task.status != "running":
                return None
            response_text = await self._wait_for_response(
                task,
                page,
                context,
                extract_json_fn=extract_json_fn,
                timeout_debug_reason=f"{debug_prefix}_timeout_raw",
            )
            await asyncio.sleep(0)
            if not self._record_audit_exchange(task, effective_prompt, response_text, f"{debug_prefix}_{submit_attempt + 1:03d}"):
                task.mark_error(
                    "GEMINI_AUDIT_PERSIST_FAILED: không thể lưu response Gemini vào backend audit storage.",
                    public_error="Không thể hoàn tất xử lý. Vui lòng thử lại.",
                )
                return None
            json_str = extract_json_fn(response_text)
            if json_str:
                try:
                    parsed = loads_json_with_repair(json_str)
                except (json.JSONDecodeError, ValueError) as exc:
                    last_errors = [f"JSON parse error: {exc}"]
                else:
                    valid, errors, fixed = validate_fn(parsed)
                    await self._save_raw_debug(task, response_text, f"{debug_prefix}_raw")
                    await self._save_json_debug(task, f"{debug_prefix}_extracted", fixed or parsed)
                    if valid and fixed is not None:
                        task.telemetry.record_gemini_pass(
                            name=debug_prefix,
                            attempt=submit_attempt + 1,
                            prompt_text=effective_prompt,
                            response_text=response_text,
                            started_at=pass_started_at,
                            valid=True,
                        )
                        return fixed
                    last_errors = errors
                    logger.warning("Gemini %s validation failed for task %s: %s", debug_prefix, task.task_id, errors[:5])
            task.telemetry.record_gemini_pass(
                name=debug_prefix,
                attempt=submit_attempt + 1,
                prompt_text=effective_prompt,
                response_text=response_text,
                started_at=pass_started_at,
                valid=False,
                errors=last_errors,
            )
            await self._save_raw_debug(task, response_text, f"{debug_prefix}_failed_raw")
        details = "; ".join(last_errors[:3]) if last_errors else f"Gemini không trả JSON {debug_prefix} hợp lệ."
        task.mark_error(f"{message} thất bại sau {attempts} lần thử: {details}")
        return None

    def _source_urls_from_prompt_req(self, prompt_req: PromptGenerateRequest) -> list[str]:
        urls = [str(url) for url in (prompt_req.youtube_urls or [])]
        if not urls and prompt_req.youtube_url:
            urls = [str(prompt_req.youtube_url)]
        return urls

    def _source_items_from_timeline(self, timeline_json: dict, prompt_req: PromptGenerateRequest) -> list[dict]:
        urls = self._source_urls_from_prompt_req(prompt_req)
        source_id = timeline_json.get("source_id") or "source_1"
        youtube_url = timeline_json.get("youtube_url") or (urls[0] if urls else None)
        item = {"source_id": source_id, "label": "Video nguồn chính"}
        if youtube_url:
            item["youtube_url"] = youtube_url
        return [item]

    async def _run_two_prompt_deep_pipeline(
        self,
        task: GeminiAutomationTask,
        page: Any,
        context: Any,
        prompt_req: PromptGenerateRequest,
        thinking_mode: str,
    ) -> dict | None:
        generator = PromptGenerator()
        analysis_prompt = generator.generate_analysis_prompt(prompt_req)
        await self._save_prompt_text(task, analysis_prompt, "prompt_1_analysis")
        analysis_json = await self._run_analysis_pass(task, page, context, analysis_prompt, thinking_mode)
        if task.status != "running" or analysis_json is None:
            return None
        await self._save_json_debug(task, "two_prompt_analysis", analysis_json)
        source_duration = analysis_latest_end_seconds(analysis_json)
        final_payload = await self._run_final_from_analysis_pass(
            task,
            page,
            context,
            prompt_req,
            thinking_mode,
            analysis_json,
            correction=None,
        )
        if task.status != "running" or final_payload is None:
            return None
        duration_ok, duration_info = two_prompt_duration_gate(source_duration, final_payload, prompt_req.user_instruction)
        await self._save_json_debug(task, "two_prompt_duration_gate", duration_info)
        if not duration_ok:
            final_payload = await self._run_final_from_analysis_pass(
                task,
                page,
                context,
                prompt_req,
                thinking_mode,
                analysis_json,
                correction=duration_info,
            )
            if task.status != "running" or final_payload is None:
                return None
            duration_ok, duration_info = two_prompt_duration_gate(source_duration, final_payload, prompt_req.user_instruction)
            await self._save_json_debug(task, "two_prompt_duration_gate_after_retry", duration_info)
            if not duration_ok:
                task.mark_error("Final vẫn quá ngắn sau 1 lần retry Prompt 2; dừng trước render để tránh output kém chất lượng.")
                return None
        await self._save_json_debug(task, "two_prompt_final", final_payload)
        return final_payload

    async def _run_final_from_analysis_pass(
        self,
        task: GeminiAutomationTask,
        page: Any,
        context: Any,
        prompt_req: PromptGenerateRequest,
        thinking_mode: str,
        analysis_json: dict,
        correction: dict | None = None,
    ) -> dict | None:
        prompt_text = PromptGenerator().generate_final_prompt_from_analysis(prompt_req, analysis_json)
        if correction:
            prompt_text += "\n\nDURATION CORRECTION:\n"
            prompt_text += f"Your previous final JSON was too short. Source duration: {correction.get('source_duration_seconds')} seconds. "
            prompt_text += f"Final duration: {correction.get('final_duration_seconds')} seconds. Minimum required final duration: {correction.get('min_required_seconds')} seconds.\n"
            prompt_text += "Rewrite the full final JSON with richer voiceover, more selected scene_beats, more context, and enough visual coverage. Do not pad with meaningless repetition. Keep voiceover-scene alignment. Return full final JSON only."
        await self._save_prompt_text(task, prompt_text, "prompt_2_final" if not correction else "prompt_2_final_retry")
        task.update("building_final_prompt", "Đang tạo JSON final từ bản phân tích cảnh và thoại..." if not correction else "Đang retry JSON final vì output quá ngắn...")
        await self._submit_prompt(task, page, context, prompt_text, thinking_mode)
        if task.status != "running":
            return None
        response_text = await self._wait_for_response(task, page, context)
        json_str = ""
        for retry in range(3):
            task.update("extracting_json", f"Đang trích xuất JSON final (lần {retry + 1}/3)...")
            json_str = self._extract_json(response_text)
            if json_str:
                try:
                    parsed = loads_json_with_repair(json_str)
                    normalized = JsonValidator().normalize_payload(parsed)
                    await self._save_json_debug(task, "two_prompt_final_retry" if correction else "two_prompt_final_extracted", normalized)
                    return normalized
                except Exception as exc:
                    logger.warning("Two-prompt final JSON parse/normalize failed for task %s: %s", task.task_id, exc)
            if retry < 2:
                await asyncio.sleep(3)
                response_text = await self._wait_for_response(task, page, context)
        await self._save_raw_debug(task, response_text, "two_prompt_final_failed_raw")
        task.mark_error("Không thể trích xuất JSON final hợp lệ từ Prompt 2.")
        return None

    def _beats_for_chunk(self, assembly_json: dict, chunk_name: str) -> list[dict]:
        selected = assembly_json.get("selected_beats") if isinstance(assembly_json, dict) else []
        if not isinstance(selected, list):
            return []
        normalized = chunk_name.lower()
        direct = [item for item in selected if isinstance(item, dict) and normalized in str(item.get("story_purpose", "")).lower()]
        if direct:
            return direct
        if normalized.startswith("progression"):
            return [item for item in selected if isinstance(item, dict) and "progress" in str(item.get("story_purpose", "")).lower()]
        return []

    def _chunk_names_from_assembly(self, assembly_json: dict) -> list[str]:
        flow = assembly_json.get("story_flow") if isinstance(assembly_json, dict) else []
        names: list[str] = []
        if isinstance(flow, list):
            for item in flow:
                name = str(item).strip().lower().replace(" ", "_")
                if name and name not in names:
                    names.append(name)
        if not names:
            names = ["opening", "setup", "progression", "climax", "ending"]
        selected = assembly_json.get("selected_beats") if isinstance(assembly_json, dict) else []
        if isinstance(selected, list) and len(selected) > 24 and "progression_2" not in names:
            names = [name if name != "progression" else "progression_1" for name in names]
            insert_at = names.index("progression_1") + 1 if "progression_1" in names else len(names)
            names.insert(insert_at, "progression_2")
        return names

    def _grouped_chunk_names(self, assembly_json: dict) -> list[str]:
        selected = assembly_json.get("selected_beats") if isinstance(assembly_json, dict) else []
        count = len(selected) if isinstance(selected, list) else 0
        if count <= 12:
            return ["chunk_1"]
        if count <= 24:
            return ["chunk_1", "chunk_2"]
        return ["chunk_1", "chunk_2", "chunk_3"]

    def _beats_for_grouped_chunk(self, assembly_json: dict, chunk_name: str) -> list[dict]:
        selected = assembly_json.get("selected_beats") if isinstance(assembly_json, dict) else []
        if not isinstance(selected, list):
            return []
        names = self._grouped_chunk_names(assembly_json)
        try:
            idx = names.index(chunk_name)
        except ValueError:
            return []
        size = max(1, (len(selected) + len(names) - 1) // len(names))
        return [item for item in selected[idx * size:(idx + 1) * size] if isinstance(item, dict)]

    def _limit_chapters_for_runtime(self, chapters: list[dict]) -> list[dict]:
        if len(chapters) <= 9:
            return chapters
        important_roles = {"hook", "opening", "setup", "climax", "ending", "payoff"}
        selected: list[dict] = []
        for chapter in (chapters[0], chapters[-1]):
            if chapter not in selected:
                selected.append(chapter)
        for chapter in chapters:
            role = str(chapter.get("story_role", "")).lower()
            if role in important_roles and chapter not in selected:
                selected.append(chapter)
            if len(selected) >= 9:
                break
        step = max(1, len(chapters) // 6)
        for index in range(0, len(chapters), step):
            if chapters[index] not in selected:
                selected.append(chapters[index])
            if len(selected) >= 9:
                break
        return sorted(selected[:9], key=lambda item: item.get("chapter_index", 0))

    def _relevant_analyses_for_selected_beats(self, chapter_analyses: list[dict], selected_beats: list[dict]) -> list[dict]:
        chapter_ids = {item.get("chapter_index") for item in selected_beats if isinstance(item, dict)}
        if not chapter_ids:
            return chapter_analyses[:2]
        return [analysis for analysis in chapter_analyses if analysis.get("chapter_index") in chapter_ids]

    async def _run_full_layered_deep_pipeline(
        self,
        task: GeminiAutomationTask,
        page: Any,
        context: Any,
        prompt_req: PromptGenerateRequest,
        thinking_mode: str,
    ) -> dict | None:
        generator = PromptGenerator()
        source_access = await self._run_json_pass(
            task,
            page,
            context,
            step="scouting_timeline",
            message="Đang kiểm tra Gemini có xem được video nguồn",
            prompt_text=generator.generate_source_access_check_prompt(prompt_req),
            thinking_mode=thinking_mode,
            extract_json_fn=self._extract_source_access_json,
            validate_fn=validate_source_access_payload,
            debug_prefix="source_access",
            attempts=1,
        )
        if task.status != "running" or source_access is None:
            return None
        if source_access.get("can_access_video") is False:
            await self._save_json_debug(task, "source_access_failed", source_access)
            task.mark_error(f"Gemini không xem được video nguồn: {source_access.get('reason', 'không rõ lý do')}")
            return None
        timeline_json = await self._run_json_pass(
            task,
            page,
            context,
            step="scouting_timeline",
            message="Đang lập timeline cấp chapter",
            prompt_text=generator.generate_timeline_scout_prompt(prompt_req),
            thinking_mode=thinking_mode,
            extract_json_fn=self._extract_timeline_json,
            validate_fn=validate_timeline_payload,
            debug_prefix="timeline",
        )
        if task.status != "running" or timeline_json is None:
            return None

        chapters = self._limit_chapters_for_runtime([item for item in timeline_json.get("chapters", []) if isinstance(item, dict)])
        if len(chapters) != len(timeline_json.get("chapters", [])):
            await self._save_json_debug(task, "timeline_runtime_limited_chapters", {"selected_chapters": chapters, "original_count": len(timeline_json.get("chapters", []))})
        chapter_analyses: list[dict] = []
        for chapter_position, chapter in enumerate(chapters, start=1):
            task.update(
                "analyzing_chapter",
                f"Đang phân tích chapter {chapter_position}/{len(chapters)}",
                {"current_item": chapter_position, "total_items": len(chapters), "chapter_index": chapter.get("chapter_index")},
            )
            prompt = generator.generate_chapter_analysis_prompt(prompt_req, timeline_json, chapter)

            def validate_requested_chapter(parsed: object, ch: dict = chapter) -> tuple[bool, list[str], dict | None]:
                if isinstance(parsed, dict) and isinstance(ch.get("chapter_index"), int):
                    parsed = {**parsed, "chapter_index": ch["chapter_index"]}
                return validate_chapter_analysis_payload(parsed, ch)

            chapter_json = await self._run_json_pass(
                task,
                page,
                context,
                step="analyzing_chapter",
                message=f"Đang phân tích chapter {chapter.get('chapter_index')}",
                prompt_text=prompt,
                thinking_mode=thinking_mode,
                extract_json_fn=self._extract_chapter_analysis_json,
                validate_fn=validate_requested_chapter,
                debug_prefix=f"chapter_{chapter.get('chapter_index', len(chapter_analyses) + 1)}",
                attempts=3,
            )
            if task.status != "running" or chapter_json is None:
                return None
            chapter_analyses.append(chapter_json)

        director_plan = await self._run_json_pass(
            task,
            page,
            context,
            step="assembling_story",
            message="Đang để Gemini lập director plan",
            prompt_text=generator.generate_director_plan_prompt(prompt_req, timeline_json, chapter_analyses),
            thinking_mode=thinking_mode,
            extract_json_fn=self._extract_director_plan_json,
            validate_fn=lambda parsed: validate_director_plan_payload(parsed, chapter_analyses, prompt_req.target_duration),
            debug_prefix="director_plan",
        )
        if task.status != "running" or director_plan is None:
            return None
        if isinstance(director_plan.get("coverage_assessment"), dict) and director_plan["coverage_assessment"].get("passed") is False:
            await self._save_json_debug(task, "director_plan_failed_coverage", director_plan)
            task.mark_error("Director plan đánh giá coverage chưa đủ để dựng video chất lượng; dừng trước render.")
            return None
        strategy_json = director_strategy(director_plan)
        assembly_json = director_plan

        chunk_names = self._grouped_chunk_names(assembly_json)
        chunks: list[dict] = []
        for chunk_name in chunk_names:
            selected_beats = self._beats_for_grouped_chunk(assembly_json, chunk_name)
            if not selected_beats:
                continue
            chunk_json = await self._run_json_pass(
                task,
                page,
                context,
                step="generating_chunk",
                message=f"Đang tạo EDL chunk {chunk_name}",
                prompt_text=generator.generate_final_chunk_prompt(prompt_req, chunk_name, selected_beats, self._relevant_analyses_for_selected_beats(chapter_analyses, selected_beats), strategy_json),
                thinking_mode=thinking_mode,
                extract_json_fn=self._extract_final_chunk_json,
                validate_fn=lambda parsed, beats=selected_beats: validate_final_chunk_against_selected_beats(parsed, beats),
                debug_prefix=f"chunk_{chunk_name}",
            )
            if task.status != "running" or chunk_json is None:
                return None
            chunks.append(chunk_json)
        if not chunks:
            task.mark_error("Story assembly không tạo được chunk EDL nào có selected beats.")
            return None

        task.update("merging_final", "Đang ghép các EDL chunk thành JSON final...")
        final_payload = merge_final_chunks(
            chunks,
            self._source_items_from_timeline(timeline_json, prompt_req),
            prompt_req.target_language,
            strategy=strategy_json,
        )
        await self._save_json_debug(task, "merged_final", final_payload)

        duration_ok, duration_info = duration_gate(final_payload, strategy_json)
        await self._save_json_debug(task, "duration_gate", duration_info)
        if not duration_ok:
            too_long = duration_info.get("over_by_seconds", 0) > 0
            narration_too_short = duration_info.get("narration_short_by_seconds", 0) > 0
            duration_problem = (
                f"Final duration {duration_info['final_duration_seconds']:.1f}s exceeds maximum threshold {duration_info['max_threshold_seconds']:.1f}s."
                if too_long else
                (
                    f"Narration density is too low: estimated spoken duration {duration_info['estimated_narration_seconds']:.1f}s is below minimum threshold {duration_info['threshold_seconds']:.1f}s."
                    if narration_too_short else
                    f"Final duration {duration_info['final_duration_seconds']:.1f}s is below Gemini minimum threshold {duration_info['threshold_seconds']:.1f}s."
                )
            )
            duration_repair = (
                "Shorten the final EDL to the Director Plan maximum. Remove redundant beats and compress narration while preserving hook, causal story flow, climax, ending, and scene-voice alignment."
                if too_long else
                (
                    "Expand narration density using concrete details from the existing selected beats. Add enough natural voiceover words to meet the estimated spoken-duration minimum while preserving timestamps, matching visuals, and story flow."
                    if narration_too_short else
                    "Expand the final EDL using the existing selected beats. Add enough natural voiceover and matching visual segments to meet the Director Plan minimum duration while preserving scene-voice alignment."
                )
            )
            audit_for_duration = {
                "alignment_audit_version": 1,
                "passed": False,
                "final_recommendation": "repair",
                "issues": [{
                    "severity": "high",
                    "chunk_name": chunks[-1].get("chunk_name", "chunk_1"),
                    "segment_index": 0,
                    "problem": duration_problem,
                    "repair_instruction": duration_repair,
                }],
            }
            repaired = await self._repair_one_chunk(
                task,
                page,
                context,
                prompt_req,
                thinking_mode,
                generator,
                chunks,
                audit_for_duration,
                assembly_json,
                chapter_analyses,
                strategy_json,
                timeline_json,
                director_plan,
            )
            if task.status != "running" or repaired is None:
                return None
            chunks, final_payload, _ = repaired
            duration_ok, duration_info = duration_gate(final_payload, strategy_json)
            await self._save_json_debug(task, "duration_gate_after_repair", duration_info)
            if not duration_ok:
                if duration_info.get("over_by_seconds", 0) > 0:
                    audit_for_duration["issues"][0]["problem"] = (
                        f"Final duration {duration_info['final_duration_seconds']:.1f}s still exceeds "
                        f"maximum threshold {duration_info['max_threshold_seconds']:.1f}s after the first repair."
                    )
                    audit_for_duration["issues"][0]["repair_instruction"] = (
                        "Shorten and compress this chunk aggressively so the merged final EDL is below the maximum threshold. "
                        "Remove redundant narration and reset SRT timestamps to a compact continuous timeline while preserving the strongest beats, story flow, and scene-voice alignment."
                    )
                else:
                    audit_for_duration["issues"][0]["problem"] = (
                        f"Final duration {duration_info['final_duration_seconds']:.1f}s is below "
                        f"Gemini minimum threshold {duration_info['threshold_seconds']:.1f}s after the first repair."
                    )
                repaired = await self._repair_one_chunk(
                    task,
                    page,
                    context,
                    prompt_req,
                    thinking_mode,
                    generator,
                    chunks,
                    audit_for_duration,
                    assembly_json,
                    chapter_analyses,
                    strategy_json,
                    timeline_json,
                    director_plan,
                )
                if task.status != "running" or repaired is None:
                    return None
                chunks, final_payload, _ = repaired
                duration_ok, duration_info = duration_gate(final_payload, strategy_json)
                await self._save_json_debug(task, "duration_gate_after_repair_2", duration_info)
            if not duration_ok:
                task.mark_error("Final vẫn ngắn hơn mức tối thiểu Gemini đã chọn sau 2 lần repair; dừng trước render.")
                return None

        audit_json = await self._run_json_pass(
            task,
            page,
            context,
            step="auditing_alignment",
            message="Đang để Gemini audit khớp cảnh và độ đủ ý",
            prompt_text=generator.generate_compact_alignment_audit_prompt(prompt_req, final_payload, director_plan),
            thinking_mode=thinking_mode,
            extract_json_fn=self._extract_alignment_audit_json,
            validate_fn=validate_alignment_audit_payload,
            debug_prefix="alignment_audit",
        )
        if task.status != "running" or audit_json is None:
            return None

        if audit_json.get("final_recommendation") == "repair" or (not audit_json.get("passed") and audit_json.get("final_recommendation") != "stop"):
            repaired = await self._repair_one_chunk(
                task,
                page,
                context,
                prompt_req,
                thinking_mode,
                generator,
                chunks,
                audit_json,
                assembly_json,
                chapter_analyses,
                strategy_json,
                timeline_json,
                director_plan,
            )
            if task.status != "running" or repaired is None:
                return None
            chunks, final_payload, audit_json = repaired
        elif audit_json.get("final_recommendation") == "stop":
            await self._save_json_debug(task, "quality_summary", pipeline_quality_summary(timeline_json, chapter_analyses, strategy_json, assembly_json, final_payload, audit_json))
            task.mark_error("Alignment audit yêu cầu dừng trước render: final chưa đủ chất lượng hoặc voice không khớp cảnh.")
            return None

        await self._save_json_debug(task, "alignment_audit_final", audit_json)
        await self._save_json_debug(task, "quality_summary", pipeline_quality_summary(timeline_json, chapter_analyses, strategy_json, assembly_json, final_payload, audit_json))
        return final_payload

    async def _repair_one_chunk(
        self,
        task: GeminiAutomationTask,
        page: Any,
        context: Any,
        prompt_req: PromptGenerateRequest,
        thinking_mode: str,
        generator: PromptGenerator,
        chunks: list[dict],
        audit_json: dict,
        assembly_json: dict,
        chapter_analyses: list[dict],
        strategy_json: dict,
        timeline_json: dict,
        director_plan: dict | None = None,
    ) -> tuple[list[dict], dict, dict] | None:
        issues = audit_json.get("issues") if isinstance(audit_json.get("issues"), list) else []
        issue = next((item for item in issues if isinstance(item, dict) and item.get("severity") == "high"), None)
        if issue is None:
            issue = next((item for item in issues if isinstance(item, dict)), {})
        chunk_name = str(issue.get("chunk_name") or (chunks[0].get("chunk_name") if chunks else "opening"))
        previous = next((chunk for chunk in chunks if chunk.get("chunk_name") == chunk_name), chunks[0] if chunks else None)
        if previous is None:
            return None
        selected_beats = self._beats_for_grouped_chunk(assembly_json, chunk_name)
        repair_instruction = str(issue.get("repair_instruction", "")).lower()
        previous_duration = final_duration_seconds(previous)
        previous_chars = sum(len(str(item.get("text", "")).strip()) for item in previous.get("srt", []) if isinstance(item, dict))

        def validate_repaired_chunk(parsed: object) -> tuple[bool, list[str], dict | None]:
            valid, errors, normalized = validate_final_chunk_against_selected_beats(parsed, selected_beats)
            if not valid or normalized is None:
                return valid, errors, normalized
            repaired_duration = final_duration_seconds(normalized)
            minimum_change = 3.0
            repaired_chars = sum(len(str(item.get("text", "")).strip()) for item in normalized.get("srt", []) if isinstance(item, dict))
            if "narration density" in repair_instruction and repaired_chars < previous_chars * 1.1:
                required_chars = math.ceil(previous_chars * 1.1)
                errors.append(
                    f"repair did not add enough narration: previous={previous_chars} chars, repaired={repaired_chars} chars; "
                    f"the corrected chunk must contain at least {required_chars} narration characters. "
                    "Add new concrete, non-repetitive narration aligned to the selected beats; returning the previous text unchanged is invalid."
                )
            elif "expand" in repair_instruction and repaired_duration < previous_duration + minimum_change:
                errors.append(
                    f"repair did not expand duration: previous={previous_duration:.1f}s, repaired={repaired_duration:.1f}s; add at least {minimum_change:.1f}s of aligned narration and visuals."
                )
            if any(word in repair_instruction for word in ("shorten", "compress", "remove redundant")) and repaired_duration > previous_duration - minimum_change:
                errors.append(
                    f"repair did not shorten duration: previous={previous_duration:.1f}s, repaired={repaired_duration:.1f}s; remove at least {minimum_change:.1f}s while preserving story flow."
                )
            return not errors, errors, normalized if not errors else None

        repaired_chunk = await self._run_json_pass(
            task,
            page,
            context,
            step="repairing_chunk",
            message=f"Đang repair một lần chunk {chunk_name}",
            prompt_text=generator.generate_repair_chunk_prompt(prompt_req, chunk_name, previous, audit_json, selected_beats, self._relevant_analyses_for_selected_beats(chapter_analyses, selected_beats), strategy_json),
            thinking_mode=thinking_mode,
            extract_json_fn=self._extract_final_chunk_json,
            validate_fn=validate_repaired_chunk,
            debug_prefix=f"repair_chunk_{chunk_name}",
            attempts=3,
        )
        if task.status != "running" or repaired_chunk is None:
            return None
        new_chunks = [repaired_chunk if chunk.get("chunk_name") == previous.get("chunk_name") else chunk for chunk in chunks]
        final_payload = merge_final_chunks(new_chunks, self._source_items_from_timeline(timeline_json, prompt_req), prompt_req.target_language, strategy=strategy_json)
        await self._save_json_debug(task, "merged_final_after_repair", final_payload)
        second_audit = await self._run_json_pass(
            task,
            page,
            context,
            step="auditing_alignment",
            message="Đang audit lại sau repair",
            prompt_text=generator.generate_compact_alignment_audit_prompt(prompt_req, final_payload, director_plan or assembly_json),
            thinking_mode=thinking_mode,
            extract_json_fn=self._extract_alignment_audit_json,
            validate_fn=validate_alignment_audit_payload,
            debug_prefix="alignment_audit_after_repair",
            attempts=1,
        )
        if task.status != "running" or second_audit is None:
            return None
        if second_audit.get("final_recommendation") != "render" or not second_audit.get("passed"):
            await self._save_json_debug(task, "quality_summary_after_failed_repair", pipeline_quality_summary(timeline_json, chapter_analyses, strategy_json, assembly_json, final_payload, second_audit))
            task.mark_error("Alignment audit vẫn fail sau 1 lần repair; dừng trước render để tránh video kém chất lượng.")
            return None
        return new_chunks, final_payload, second_audit

    @staticmethod
    def _cookie_now() -> float:
        return time.time()

    @staticmethod
    def _cookie_is_active(cookie: dict) -> bool:
        expires = cookie.get("expires")
        if expires is None or expires <= 0:
            return True
        return expires > time.time()

    @staticmethod
    async def _check_cookies_logged_in(context: Any) -> bool:
        cookies = await context.cookies()
        auth_names = {"SAPISID", "__Secure-3PSAPISID", "OSID"}
        return any(c["name"] in auth_names and GeminiAutomationService._cookie_is_active(c) for c in cookies)

    @staticmethod
    def _session_disk_info(session_path: Path) -> dict:
        _needs_login = True
        _has_auth = False
        _active = False
        _expired = False
        _near_expiry = False
        try:
            if session_path.exists():
                data = json.loads(session_path.read_text(encoding="utf-8"))
                cookies = data.get("cookies", [])
                auth_names = {"SAPISID", "__Secure-3PSAPISID", "OSID"}
                now = time.time()
                for c in cookies:
                    if c.get("name") in auth_names:
                        _has_auth = True
                        expires = c.get("expires")
                        if not expires or expires > now:
                            _active = True
                        if expires and expires <= now:
                            _expired = True
                        if expires and now < expires < now + 86400:
                            _near_expiry = True
                if _active:
                    _needs_login = False
        except Exception:
            pass
        if session_path.exists():
            return {
                "session_file_exists": True,
                "has_auth_cookies": _has_auth,
                "auth_cookies_active": _active,
                "auth_cookies_expired": _expired,
                "auth_cookies_near_expiry": _near_expiry,
                "needs_login": _needs_login,
            }
        return {
            "session_file_exists": False,
            "has_auth_cookies": False,
            "auth_cookies_active": False,
            "auth_cookies_expired": False,
            "auth_cookies_near_expiry": False,
            "needs_login": True,
        }

    def _set_pending_status(self, session_path: Path, browser_id: str) -> None:
        disk = self._session_disk_info(session_path)
        self._last_session_status = {
            "exists": False,
            **disk,
            "live_checked": False,
            "browser_open": True,
            "browser_id": browser_id,
            "path": str(session_path),
            "message": "Đang kiểm tra đăng nhập Gemini...",
            "method": "checking",
        }

    async def _detect_gemini_login_state(self, page: Any, context: Any) -> dict:
        cookie_ok = await self._check_cookies_logged_in(context)

        async def visible(sel: str) -> bool:
            locator = page.locator(sel).first
            try:
                if await locator.count() == 0:
                    return False
                return await locator.is_visible()
            except Exception:
                return False

        chat_area_ok = False
        for sel in GEMINI_SELECTORS["chat_area"]:
            if await visible(sel):
                chat_area_ok = True
                break

        avatar_ok = False
        for sel in GEMINI_SELECTORS["user_avatar"]:
            if await visible(sel):
                avatar_ok = True
                break

        signin_indicator = False
        for sel in GEMINI_SELECTORS["sign_in_indicators"]:
            if await visible(sel):
                signin_indicator = True
                break

        if not signin_indicator:
            try:
                current_url = page.url
                if any(p in current_url for p in ["accounts.google.com", "/signin", "/ServiceLogin", "/v3/signin"]):
                    signin_indicator = True
            except Exception:
                pass

        logged_in = False
        method = "unknown"
        if signin_indicator:
            method = "signin"
        elif cookie_ok and (chat_area_ok or avatar_ok):
            logged_in = True
            method = "cookies"

        return {
            "logged_in": logged_in,
            "method": method,
            "needs_login": not logged_in,
            "cookie_ok": cookie_ok,
            "chat_area_ok": chat_area_ok,
            "avatar_ok": avatar_ok,
            "signin_indicator": signin_indicator,
        }

    async def _handle_login_if_needed(
        self,
        task: GeminiAutomationTask,
        page: Any,
        context: Any,
        session_path: Path,
        headless: bool = False,
    ) -> None:
        try:
            await page.wait_for_load_state("load", timeout=10000)
        except Exception as exc:
            if "Timeout" in type(exc).__name__:
                logger.debug("Login check load timeout (continuing): %s", exc)
            else:
                logger.warning("Unexpected error in login check load wait: %s", exc)

        login_state = await self._detect_gemini_login_state(page, context)
        is_logged_in = login_state["logged_in"]

        if not is_logged_in:
            if headless:
                task.mark_error("Gemini session is not logged in. Please use Open Browser to login first.")
                return
            task.update("wait_login", "Vui lòng đăng nhập Gemini trên trình duyệt vừa mở. Bạn có 5 phút.", detail={"login_required": True, "login_state": login_state})
            try:
                deadline = time.time() + 300
                while time.time() < deadline:
                    await asyncio.sleep(2)
                    login_state = await self._detect_gemini_login_state(page, context)
                    if login_state["logged_in"]:
                        break
                else:
                    raise TimeoutError("Login timeout")
                task.update("wait_login", "Đã phát hiện đăng nhập thành công. Đang lưu phiên làm việc...")
                await self._save_session_state(context, session_path, strict=True)
                task.update("wait_login", "Phiên làm việc đã được lưu.")
            except TimeoutError:
                task.mark_error("Quá thời gian chờ đăng nhập Gemini. Vui lòng thử lại.")
            except Exception:
                task.mark_error("Đã đăng nhập Gemini nhưng không thể lưu session. Vui lòng kiểm tra quyền ghi thư mục dữ liệu ứng dụng.")
        else:
            if not await self._save_session_state(context, session_path):
                task.mark_error("Gemini đã đăng nhập nhưng không thể lưu session. Vui lòng kiểm tra quyền ghi thư mục dữ liệu ứng dụng.")

    async def _recover_login_from_chrome_profile(
        self,
        task: GeminiAutomationTask,
        pw: Any,
        page: Any,
        context: Any,
        session_path: Path,
        profile_path: Path,
        user_data_dir: str | None,
        headless: bool,
    ) -> tuple[Any, Any, Any] | None:
        recovery_dir = user_data_dir or self._get_user_data_dir()
        if not recovery_dir:
            return None
        profile_dir = self._profile_dir(recovery_dir)
        auth_cookies = self._extract_auth_cookies(profile_dir) if profile_dir else []
        if not auth_cookies:
            logger.warning("Gemini recovery skipped: no usable auth cookies from Chrome profile %s", profile_dir)
            return None
        task.update("checking_login", "Gemini session hết hạn. Đang thử khôi phục từ Chrome profile đã đăng nhập...")
        try:
            await context.close()
        except Exception:
            pass
        try:
            browser, new_context, new_page = await self._launch_stealth_context(
                pw,
                recovery_dir,
                auth_cookies,
                headless=headless,
                persistent=True,
                persistent_profile_path=profile_path,
            )
            await new_page.goto(settings.gemini_url, wait_until="domcontentloaded")
            try:
                await new_page.wait_for_load_state("load", timeout=10000)
            except Exception:
                pass
            login_state = await self._detect_gemini_login_state(new_page, new_context)
            if login_state["logged_in"]:
                await self._save_session_state(new_context, session_path)
                task.update("checking_login", "Đã khôi phục Gemini session từ Chrome profile.")
                return browser, new_context, new_page
            try:
                await new_context.close()
            except Exception:
                pass
        except Exception:
            logger.exception("Gemini Chrome profile recovery failed")
        return None

    async def _click_first_visible(self, page: Any, selectors: list[str], *, timeout_ms: int = 3000) -> str | None:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() == 0:
                    continue
                if not await loc.is_visible(timeout=1000):
                    continue
                await loc.click(timeout=timeout_ms)
                return sel
            except Exception:
                continue
        return None

    def _audit_task_dir(self, task: GeminiAutomationTask) -> Path:
        return Path(settings.gemini_audit_dir) / task.task_id

    def _write_audit_artifact(self, task: GeminiAutomationTask, name: str, content: str) -> Path:
        audit_dir = self._audit_task_dir(task)
        audit_dir.mkdir(parents=True, exist_ok=True)
        path = audit_dir / name
        path.write_text(content or "", encoding="utf-8")
        return path

    def _record_audit_exchange(
        self,
        task: GeminiAutomationTask,
        prompt_text: str,
        response_text: str,
        label: str,
    ) -> bool:
        if not settings.gemini_audit_enabled:
            return True
        try:
            audit_dir = self._audit_task_dir(task)
            audit_dir.mkdir(parents=True, exist_ok=True)
            prompt_path = self._write_audit_artifact(task, f"{label}_prompt.txt", prompt_text)
            response_path = self._write_audit_artifact(task, f"{label}_response_raw.txt", response_text)
            manifest_path = audit_dir / "manifest.json"
            manifest = {}
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    manifest = {}
            manifest.setdefault("task_id", task.task_id)
            manifest.setdefault("exchanges", []).append({
                "label": label,
                "prompt_file": prompt_path.name,
                "response_file": response_path.name,
                "prompt_chars": len(prompt_text),
                "response_chars": len(response_text),
                "created_at": time.time(),
            })
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception:
            logger.exception("Failed to persist Gemini audit exchange for task %s", task.task_id)
            return False

    def _record_audit_json(self, task: GeminiAutomationTask, json_text: str, label: str = "final") -> bool:
        if not settings.gemini_audit_enabled:
            return True
        try:
            self._write_audit_artifact(task, f"{label}_json.txt", json_text)
            return True
        except Exception:
            logger.exception("Failed to persist Gemini audit JSON for task %s", task.task_id)
            return False

    async def _click_google_account_if_available(self, page: Any) -> str | None:
        selectors = [
            "div[data-identifier]",
            "[role='link'][data-identifier]",
            "[role='button'][data-identifier]",
            "[role='button']:has-text('@')",
            "div:has-text('@gmail.com')",
            "button:has-text('Continue')",
            "button:has-text('Tiếp tục')",
        ]
        return await self._click_first_visible(page, selectors, timeout_ms=5000)

    async def _auto_activate_gemini_login(
        self,
        task: GeminiAutomationTask,
        pw: Any,
        old_context: Any,
        session_path: Path,
        profile_path: Path,
        user_data_dir: str | None,
        headless: bool,
    ) -> tuple[Any, Any, Any] | None:
        task.update("checking_login", "Gemini session hết hạn. Đang tự mở Gemini và bấm đăng nhập bằng profile đã lưu...")
        try:
            await old_context.close()
        except Exception:
            pass

        browser = None
        context = None
        try:
            browser, context, page = await self._launch_stealth_context(
                pw,
                user_data_dir,
                headless=False,
                persistent=True,
                persistent_profile_path=profile_path,
            )
            await page.goto(settings.gemini_url, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("load", timeout=15000)
            except Exception:
                pass

            clicked_login = False
            login_state = await self._detect_gemini_login_state(page, context)
            if not login_state["logged_in"]:
                clicked = await self._click_first_visible(page, GEMINI_SELECTORS["sign_in_indicators"], timeout_ms=5000)
                clicked_login = clicked is not None
                if clicked_login:
                    task.update("checking_login", "Đã bấm đăng nhập Gemini. Đang chờ Google profile tự xác thực...")
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass

            deadline = time.time() + 120
            clicked_account = False
            while time.time() < deadline:
                await asyncio.sleep(2)
                login_state = await self._detect_gemini_login_state(page, context)
                if login_state["logged_in"]:
                    if await self._save_session_state(context, session_path, strict=True):
                        task.update("checking_login", "Đã tự đăng nhập Gemini và lưu session. Đang chạy tiếp pipeline...")
                        try:
                            await context.close()
                        except Exception:
                            pass
                        return await self._launch_stealth_context(
                            pw,
                            user_data_dir,
                            headless=headless,
                            storage_state_path=session_path,
                            persistent=True,
                            persistent_profile_path=profile_path,
                        )
                    task.mark_error("Gemini đã đăng nhập nhưng không thể lưu session. Vui lòng kiểm tra quyền ghi thư mục dữ liệu ứng dụng.")
                    return None

                try:
                    current_url = page.url
                except Exception:
                    current_url = ""
                if not clicked_account and any(p in current_url for p in ["accounts.google.com", "/signin", "/ServiceLogin", "/v3/signin"]):
                    clicked = await self._click_google_account_if_available(page)
                    clicked_account = clicked is not None
                    if clicked_account:
                        task.update("checking_login", "Đã chọn Google account có sẵn. Đang chờ Gemini xác thực...")
                        try:
                            await page.wait_for_load_state("domcontentloaded", timeout=15000)
                        except Exception:
                            pass

            logger.warning(
                "Gemini auto activation timed out: clicked_login=%s clicked_account=%s url=%s",
                clicked_login, clicked_account, getattr(page, "url", ""),
            )
        except Exception:
            logger.exception("Gemini auto activation failed")
        finally:
            try:
                if context is not None:
                    await context.close()
            except Exception:
                pass
        return None

    async def _select_model(self, page: Any, model_key: str) -> bool:
        entry = _MODEL_BY_KEY.get(model_key)
        if not entry:
            logger.warning("Unknown model key: %s", model_key)
            return False
        try:
            await page.wait_for_selector("[role='menuitem']", timeout=5000)
        except Exception:
            pass
        items = page.locator("[role='menuitem']")
        count = await items.count()
        matched = None
        for i in range(count):
            raw = (await items.nth(i).text_content() or "").strip()
            norm = " ".join(raw.split()).replace("Mới", " ").strip()
            for alias in entry["aliases"]:
                if norm.startswith(alias) or norm.startswith(alias.replace(" ", "")):
                    matched = items.nth(i)
                    break
            if matched:
                break
        if not matched:
            logger.warning("Model '%s' not found in picker menuitems (key=%s)", entry["label"], model_key)
            return False
        await matched.click(force=True, timeout=3000)
        await asyncio.sleep(1.5)
        try:
            pill = page.locator(GEMINI_SELECTORS["model_pill"][0]).first
            if await pill.count() > 0:
                pill_text = (await pill.text_content() or "").strip()
                prefix = entry["label"].split()[0]
                if prefix in pill_text:
                    logger.info("Model '%s' selected and verified", entry["label"])
                    return True
                logger.warning("Model pill mismatch: expected prefix '%s', got '%s'", prefix, pill_text)
            else:
                logger.warning("No model pill found for verification")
        except Exception as e:
            logger.warning("Model verification exception: %s", e)
        return False

    async def _submit_prompt(self, task: GeminiAutomationTask, page: Any, context: Any, prompt_text: str,
                             thinking_mode: str = "extended") -> None:
        task.update("submitting_prompt", "Đang tìm ô nhập prompt...")

        input_element = page.locator('[contenteditable="true"]').first
        count = await input_element.count()
        if count == 0:
            for sel in GEMINI_SELECTORS["prompt_input"]:
                el = page.locator(sel).first
                cnt = await el.count()
                if cnt > 0:
                    input_element = el
                    break
            else:
                body_text = await page.evaluate("document.body.innerText")
                has_login_text = any(
                    word in body_text.lower()
                    for word in ["sign in", "sign-in", "đăng nhập", "log in", "login", "not signed in"]
                )
                if has_login_text:
                    task.mark_error("Gemini yêu cầu đăng nhập — session đã hết hạn. Vui lòng đăng nhập lại.")
                else:
                    task.mark_error("Không tìm thấy ô nhập prompt trên Gemini.")
                return

        task.update("submitting_prompt", "Đang nhập prompt...")
        await input_element.click()
        await asyncio.sleep(0.5)

        # ── Step 1: Open model picker popup (contains model + thinking level) ──
        model_picker_opened = False
        try:
            pill = page.locator(GEMINI_SELECTORS["model_pill"][0]).first
            if await pill.count() == 0:
                logger.warning("Model pill not found")
            else:
                # Click the parent button of the model pill text
                await page.evaluate("""(() => {
                    const s = document.querySelector('span.picker-primary-text');
                    if (s) {
                        let p = s.parentElement;
                        while (p && p.tagName !== 'BUTTON') p = p.parentElement;
                        if (p) { p.click(); return true; }
                    }
                    return false;
                })()""")
                await asyncio.sleep(2)

                picker_btn = page.locator(GEMINI_SELECTORS["model_picker_button"][0]).first
                if await picker_btn.count() > 0:
                    await picker_btn.click()
                    await asyncio.sleep(1.5)
                    model_picker_opened = True
                    logger.info("Model picker popup opened")
                else:
                    logger.warning("Model picker button not found after clicking pill")
        except Exception as e:
            logger.warning("Failed to open model picker: %s", e)

        # ── Step 2: Set thinking level (model picker path, supports VI/EN) ──
        thinking_set = False
        if thinking_mode not in GEMINI_THINKING_MODE_LABELS:
            thinking_mode = "extended"
        target_labels = GEMINI_THINKING_MODE_LABELS[thinking_mode]

        if model_picker_opened:
            try:
                thinking_label = None
                for label in GEMINI_THINKING_SECTION_LABELS:
                    candidate = page.locator(f'text="{label}"').first
                    if await candidate.count() > 0:
                        thinking_label = candidate
                        break
                if thinking_label is None:
                    thinking_label = page.locator('text="Tiêu chuẩn"').first
                    if await thinking_label.count() == 0:
                        thinking_label = page.locator('text="Standard"').first

                if thinking_label and await thinking_label.count() > 0:
                    await thinking_label.click()
                    await asyncio.sleep(1.5)
                    for label in target_labels:
                        selectors = [
                            f'[role="radio"]:has-text("{label}")',
                            f'[role="menuitem"]:has-text("{label}")',
                            f'text="{label}"',
                        ]
                        for selector in selectors:
                            item = page.locator(selector).first
                            if await item.count() > 0:
                                await item.click(force=True, timeout=3000)
                                await asyncio.sleep(0.5)
                                thinking_set = True
                                logger.info("Set thinking level to '%s' via model picker", thinking_mode)
                                break
                        if thinking_set:
                            break
                if not thinking_set:
                    logger.warning("Could not set thinking level in model picker, trying old approach")
            except Exception as e:
                logger.warning("Failed to set thinking level in model picker: %s", e)

        if not thinking_set:
            # Fallback: old thinking dropdown approach (bilingual labels)
            try:
                dropdown = page.locator(GEMINI_SELECTORS["thinking_dropdown"][0]).first
                if await dropdown.count() > 0:
                    await dropdown.click()
                    await asyncio.sleep(1)
                    trigger_sel = GEMINI_SELECTORS["thinking_submenu_trigger"][0]
                    trigger_item = page.locator(trigger_sel).first
                    if await trigger_item.count() > 0:
                        await trigger_item.click()
                        await asyncio.sleep(1)
                        for label in target_labels:
                            selectors = [
                                f'//gem-menu-item-content[.//span[@class="label" and contains(text(),"{label}")]]',
                                f'gem-menu-item-content:has(span.label:text("{label}"))',
                                f'[role="menuitem"]:has-text("{label}")',
                                f'text="{label}"',
                            ]
                            for selector in selectors:
                                item = page.locator(selector).first
                                if await item.count() > 0:
                                    await item.click(force=True, timeout=3000)
                                    thinking_set = True
                                    logger.info("Set thinking level to '%s' via old dropdown", thinking_mode)
                                    break
                            if thinking_set:
                                break
                    if not thinking_set:
                        await asyncio.sleep(0.5)
                        thinking_set = True
                        logger.info("Skipped thinking level selection (old dropdown, label not found)")
            except Exception as e:
                logger.warning("Failed to set thinking level (old approach): %s", e)

        # ── Step 3: Select model ──
        if model_picker_opened:
            if not await self._select_model(page, task.gemini_model):
                task.mark_error(
                    f"GEMINI_MODEL_SELECTION_FAILED: không tìm thấy hoặc verify được model '{task.gemini_model}' trong Gemini picker.",
                )
                return

        # ── Wait for any post-model-change navigation to settle ──
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        # If model change caused navigation away from Gemini, re-navigate
        current_url = page.url
        if "gemini.google.com" not in current_url:
            logger.warning(
                "Page navigated away after model picker (URL: %s). Re-navigating.",
                current_url,
            )
            await page.goto(settings.gemini_url, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

        if not thinking_set:
            task.message = f"Không set được thinking level ({thinking_mode}), vẫn tiếp tục submit..."

        # ── Re-acquire input element after model/thinking ops ──
        # Model picker modals may have stolen focus or page may have navigated
        input_element = page.locator('[contenteditable="true"]').first
        if await input_element.count() == 0:
            for sel in GEMINI_SELECTORS["prompt_input"]:
                el = page.locator(sel).first
                if await el.count() > 0:
                    input_element = el
                    break

        async def stop_button_is_visible() -> bool:
            for sel in GEMINI_SELECTORS["stop_button"]:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible(timeout=500):
                        return True
                except Exception:
                    continue
            return False

        async def clear_input() -> None:
            await input_element.click()
            await asyncio.sleep(0.2)
            try:
                await input_element.fill("")
            except Exception:
                pass
            try:
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")
            except Exception:
                pass

        async def paste_prompt() -> str:
            await input_element.click()
            try:
                await context.grant_permissions(["clipboard-read", "clipboard-write"])
            except Exception:
                pass
            try:
                await page.evaluate("(text) => navigator.clipboard.writeText(text)", prompt_text)
                await page.keyboard.press("Control+V")
                return "clipboard_paste"
            except Exception as exc:
                logger.warning("Clipboard paste failed for task %s, falling back to insert_text: %s", task.task_id, exc)
                await page.keyboard.insert_text(prompt_text)
                return "insert_text"

        await clear_input()
        paste_method = await paste_prompt()
        await asyncio.sleep(1.5)

        expected_len = len(prompt_text.strip())
        min_len = max(50, int(expected_len * 0.95))
        entered = await input_element.inner_text()
        entered_len = len(entered.strip())
        if entered_len < min_len:
            logger.warning(
                "Prompt paste length too short for task %s: method=%s entered=%d expected=%d. Retrying once.",
                task.task_id,
                paste_method,
                entered_len,
                expected_len,
            )
            await clear_input()
            paste_method = await paste_prompt()
            await asyncio.sleep(1.5)
            entered = await input_element.inner_text()
            entered_len = len(entered.strip())

        if entered_len == 0:
            logger.warning("Prompt input stayed empty for task %s; reloading Gemini and retrying paste once.", task.task_id)
            try:
                await page.goto(settings.gemini_url, wait_until="domcontentloaded")
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            input_element = page.locator('[contenteditable="true"]').first
            if await input_element.count() == 0:
                for sel in GEMINI_SELECTORS["prompt_input"]:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        input_element = el
                        break
            await clear_input()
            paste_method = await paste_prompt()
            await asyncio.sleep(1.5)
            try:
                entered = await input_element.inner_text()
                entered_len = len(entered.strip())
            except Exception:
                entered_len = 0

        if entered_len < min_len:
            task.mark_error(
                f"Gemini nhập prompt không đầy đủ ({entered_len}/{expected_len} ký tự). "
                "Đã dừng để tránh sinh kết quả sai."
            )
            return

        logger.info(
            "Prompt entered for task %s: method=%s entered=%d expected=%d url=%s",
            task.task_id,
            paste_method,
            entered_len,
            expected_len,
            page.url,
        )

        # Give Gemini's frontend time to process pasted YouTube links before sending.
        await asyncio.sleep(3)
        task.update("submitting_prompt", "Đang gửi prompt đến Gemini...")

        sent = False
        for sel in GEMINI_SELECTORS["send_button"]:
            try:
                send_btn = page.locator(sel).first
                if await send_btn.count() > 0 and await send_btn.is_visible():
                    await send_btn.click(timeout=3000)
                    logger.info(
                        "Send button clicked via selector: %s for task %s",
                        sel, task.task_id,
                    )
                    await asyncio.sleep(2)
                    sent = await stop_button_is_visible()
                    if not sent:
                        try:
                            text_after_send = await input_element.inner_text()
                            sent = len(text_after_send.strip()) < 50
                            logger.debug(
                                "After send-btn click: stop_btn=%s text_remaining=%d",
                                sent, len(text_after_send.strip()),
                            )
                        except Exception:
                            pass
                    break
            except Exception:
                continue

        if not sent:
            logger.warning("Send button did not submit task %s. Trying Enter fallback.", task.task_id)
            await input_element.click()
            await page.keyboard.press("Enter")
            await asyncio.sleep(2)
            sent = await stop_button_is_visible()
            logger.info(
                "Enter fallback result for task %s: stop_btn=%s",
                task.task_id, sent,
            )

        if not sent:
            text_after_submit = await input_element.inner_text()
            remaining = len(text_after_submit.strip())
            logger.info(
                "Submit result for task %s: sent=%s remaining=%d",
                task.task_id, sent, remaining,
            )
            if remaining < 50:
                logger.info(
                    "Prompt input cleared after submit for task %s; assuming Gemini accepted prompt.",
                    task.task_id,
                )
            else:
                task.mark_error(
                    f"Gemini không thể gửi prompt (URL: {page.url}). "
                    f"Nội dung còn lại: {remaining} ký tự. "
                    "Vui lòng kiểm tra trang Gemini trên trình duyệt và thử lại."
                )
                return

        task.update("waiting_response", "Đã gửi prompt. Đang chờ Gemini xử lý...")

    @staticmethod
    def _is_page_connection_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return (
            "connection closed" in msg
            or "target page, context or browser has been closed" in msg
            or "browser has been closed" in msg
        )

    async def _read_gemini_response_text(self, page: Any) -> str:
        text, _ = await self._read_gemini_response_snapshot(page)
        return text

    async def _read_gemini_response_snapshot(self, page: Any) -> tuple[str, str]:
        try:
            return await page.evaluate("""() => {
                const candidates = [
                    'div[data-test-id*="response-content"]',
                    'div.model-response-text',
                    '[data-message-author-role="model"]',
                    '[data-test-id*="turn"]:last-child',
                    '.conversation-turn:last-child',
                    'div[class*="response"]:last-of-type',
                    'div[class*="message-content"]:last-of-type',
                ];
                for (const sel of candidates) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const text = el.textContent || '';
                        if (text.trim().length > 200) return [text.trim(), "response_selector"];
                    }
                }
                const allText = document.body.innerText || '';
                if (allText.trim().length > 200) return [allText.trim(), "body_fallback"];
                return ["", "empty"];
            }""")
        except Exception as exc:
            if self._is_page_connection_error(exc):
                raise RuntimeError(
                    "Mất kết nối Chromium khi đọc phản hồi từ Gemini. "
                    "Vui lòng chạy lại auto pipeline."
                ) from exc
            raise

    @staticmethod
    def _is_gemini_generating(page: Any, stop_sel: str | None) -> bool:
        return stop_sel is not None

    async def _has_gemini_copy_button(self, page: Any) -> bool:
        try:
            copy_btn = page.locator('[data-test-id="copy-button"]').last
            count = await copy_btn.count()
            if count > 0:
                return await copy_btn.first.is_visible()
        except Exception:
            pass
        return False

    def _choose_final_response_text(self, dom_text: str, clipboard_text: str,
                                    extract_json_fn: Callable[[str], str] | None = None) -> str:
        extract_json_fn = extract_json_fn or self._extract_json
        clipboard_json = extract_json_fn(clipboard_text) if clipboard_text else ""
        dom_json = extract_json_fn(dom_text) if dom_text else ""
        if clipboard_json and not dom_json:
            logger.info("Using clipboard text (%d chars, has JSON) over DOM (%d chars, no JSON)", len(clipboard_text), len(dom_text))
            return clipboard_text
        if dom_json and not clipboard_json:
            logger.info("Using DOM response text (%d chars, has JSON) over clipboard (%d chars, no JSON)", len(dom_text), len(clipboard_text))
            return dom_text
        if clipboard_json and dom_json:
            logger.info("Both have JSON; clipboard (%d chars) vs DOM (%d chars)", len(clipboard_text), len(dom_text))
        if len(dom_text) >= len(clipboard_text):
            logger.info("Using DOM response text (%d chars) over clipboard (%d chars)", len(dom_text), len(clipboard_text))
            return dom_text
        else:
            logger.info("Using clipboard text (%d chars), DOM=%d chars", len(clipboard_text), len(dom_text))
            return clipboard_text or dom_text

    async def _finalize_response_text(self, context: Any, page: Any, dom_text: str,
                                      extract_json_fn: Callable[[str], str] | None = None) -> str:
        try:
            await context.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass
        clipboard_text = ""
        copy_btn = page.locator('[data-test-id="copy-button"]').last
        if await copy_btn.count() > 0:
            for _ in range(2):
                try:
                    await copy_btn.click(timeout=5000)
                    await asyncio.sleep(2)
                    clipboard_text = await page.evaluate("navigator.clipboard.readText()")
                    clipboard_text = (clipboard_text or "").strip()
                    if len(clipboard_text) > 100:
                        break
                except Exception:
                    pass
                await asyncio.sleep(1)
        return self._choose_final_response_text(dom_text, clipboard_text, extract_json_fn=extract_json_fn)

    async def _save_prompt_text(self, task: GeminiAutomationTask, prompt: str, stem: str) -> None:
        try:
            if settings.gemini_audit_enabled:
                self._write_audit_artifact(task, f"{stem}_prompt.txt", prompt)
            debug_path = settings.temp_dir / "gemini_failed_response"
            debug_path.mkdir(parents=True, exist_ok=True)
            path = debug_path / f"{task.task_id}_{stem}.txt"
            path.write_text(prompt, encoding="utf-8")
            logger.info("Saved prompt debug to %s", path)
        except Exception:
            pass

    async def _save_raw_debug(self, task: GeminiAutomationTask, response_text: str, reason: str) -> None:
        try:
            debug_path = settings.temp_dir / "gemini_failed_response"
            debug_path.mkdir(parents=True, exist_ok=True)
            path = debug_path / f"{task.task_id}_{reason}.txt"
            header = (
                f"task_id: {task.task_id}\n"
                f"reason: {reason}\n"
                f"length: {len(response_text)}\n"
                f"timeout_seconds: {settings.gemini_timeout_seconds}\n"
                f"{'=' * 60}\n"
            )
            path.write_text(header + response_text, encoding="utf-8")
            logger.warning("Gemini debug saved to %s (reason: %s)", path, reason)
        except Exception:
            pass

    async def _save_json_debug(self, task: GeminiAutomationTask, stem: str, payload: object) -> None:
        try:
            debug_path = settings.temp_dir / "gemini_failed_response"
            debug_path.mkdir(parents=True, exist_ok=True)
            path = debug_path / f"{task.task_id}_{stem}.json"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    async def _save_analysis_debug(self, task: GeminiAutomationTask, response_text: str, parsed: object, errors: list[str]) -> None:
        await self._save_raw_debug(task, response_text, "analysis_validation_failed")
        await self._save_json_debug(task, "analysis_extracted", parsed)
        segment_count = analysis_segment_count(parsed)
        latest_end = analysis_latest_end_seconds(parsed)
        roles = sorted({seg.get("story_role") for seg in parsed.get("segments", []) if isinstance(seg, dict) and seg.get("story_role")}) if isinstance(parsed, dict) else []
        has_setup = "setup" in roles
        has_climax_or_ending = bool({"climax", "ending"}.intersection(roles))
        minimum_required = minimum_analysis_segments(latest_end)
        await self._save_json_debug(task, "analysis_summary", {
            "segment_count": segment_count,
            "minimum_required": minimum_required,
            "preferred_long_video_segments": MIN_ANALYSIS_SEGMENTS_LONG if latest_end >= 600 else None,
            "latest_end_seconds": latest_end,
            "roles": roles,
            "has_setup": has_setup,
            "has_climax_or_ending": has_climax_or_ending,
            "role_complete": has_setup and has_climax_or_ending,
            "threshold_reason": "long_video_minimum" if latest_end >= 600 else "duration_dynamic_minimum",
            "would_pass_current_threshold": segment_count >= minimum_required and has_setup and has_climax_or_ending,
            "errors": errors,
        })

    async def _save_story_plan_debug(self, task: GeminiAutomationTask, response_text: str, parsed: object, errors: list[str]) -> None:
        if errors:
            await self._save_raw_debug(task, response_text, "story_plan_validation_failed")
        await self._save_json_debug(task, "story_plan_extracted", parsed)
        await self._save_json_debug(task, "story_plan_summary", story_plan_summary(parsed, errors))

    async def _save_timeout_summary(self, task: GeminiAutomationTask, response_text: str, reason: str, extract_json_fn: Callable[[str], str]) -> None:
        json_str = extract_json_fn(response_text)
        summary = {
            "reason": reason,
            "raw_length": len(response_text),
            "timeout_seconds": settings.gemini_timeout_seconds,
            "has_complete_json": bool(json_str),
            "has_metadata": "\"metadata\"" in response_text,
            "has_srt": "\"srt\"" in response_text,
            "has_video_segments": "\"video_segments\"" in response_text,
        }
        await self._save_json_debug(task, f"{reason}_summary", summary)
        if not json_str:
            candidate = response_text[response_text.find("{") : response_text.rfind("}") + 1] if "{" in response_text and "}" in response_text else ""
            if candidate:
                try:
                    debug_path = settings.temp_dir / "gemini_failed_response"
                    debug_path.mkdir(parents=True, exist_ok=True)
                    (debug_path / f"{task.task_id}_{reason}_partial_candidate.txt").write_text(candidate, encoding="utf-8")
                except Exception:
                    pass

    async def _wait_for_response(
        self,
        task: GeminiAutomationTask,
        page: Any,
        context: Any,
        extract_json_fn: Callable[[str], str] | None = None,
        timeout_debug_reason: str = "timeout_raw",
    ) -> str:
        extract_json_fn = extract_json_fn or self._extract_json

        async def _live_is_generating() -> bool:
            for sel in GEMINI_SELECTORS["stop_button"]:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible(timeout=300):
                        return True
                except Exception:
                    continue
            return False

        timeout_mins = max(1, round(settings.gemini_timeout_seconds / 60))
        task.update("waiting_response", f"Đang chờ Gemini trả kết quả... ({timeout_mins} phút tối đa)")

        timeout_seconds = settings.gemini_timeout_seconds
        deadline = time.monotonic() + timeout_seconds
        last_text = ""
        stable_since: float | None = None
        last_log_at = 0.0
        ever_generating = False

        while time.monotonic() < deadline:
            if task.status != "running" or task.cancel_requested:
                return ""

            # Detect if page navigated away from Gemini during wait
            try:
                current_url = page.url
                if not current_url or "gemini.google.com" not in current_url:
                    logger.warning(
                        "Page navigated away from Gemini during response wait "
                        "(URL: %s). Re-navigating and signalling re-submit.",
                        current_url,
                    )
                    await page.goto(settings.gemini_url, wait_until="domcontentloaded")
                    try:
                        await page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    try:
                        for sel in GEMINI_SELECTORS["prompt_input"]:
                            el = page.locator(sel).first
                            if await el.count() > 0:
                                await el.wait_for(state="visible", timeout=10000)
                                break
                    except Exception:
                        pass
                    return ""
            except Exception:
                pass

            copy_ready = await self._has_gemini_copy_button(page)
            generating = await _live_is_generating()
            if generating:
                ever_generating = True

            text, text_source = await self._read_gemini_response_snapshot(page)
            json_str = extract_json_fn(text)

            text_changed = text != last_text
            if text_changed:
                stable_since = time.monotonic()
                last_text = text
            else:
                await asyncio.sleep(0)
            stable_seconds = time.monotonic() - stable_since if stable_since else 0.0

            json_ready = bool(json_str)
            stable_ready = stable_seconds >= 12

            now = time.monotonic()
            elapsed = int(now - (deadline - timeout_seconds))
            fallback_ready = json_ready and stable_ready and elapsed >= 30
            done_indicator = copy_ready or fallback_ready

            if now - last_log_at >= 10:
                last_log_at = now
                logger.debug(
                    "waiting_response: elapsed=%ds text_len=%d stable=%.1fs "
                    "generating=%s copy_ready=%s json_ready=%s ever_generating=%s",
                    elapsed, len(text), stable_seconds, generating, copy_ready, json_ready, ever_generating,
                )

            # Fast-fail: no generation activity after 45s and no response text
            if elapsed >= 45 and not ever_generating and not text and not copy_ready:
                logger.warning(
                    "Gemini response wait fast-fail after %ds — no generation started for task %s",
                    elapsed, task.task_id,
                )
                return ""

            # A visible Copy button is a stronger completion signal than the
            # DOM snapshot, which can still contain the prompt and schema.
            # Read it after a short stability grace period so invalid/truncated
            # output reaches the existing retry flow instead of timing out.
            clipboard_probe_ready = copy_ready and stable_ready and elapsed >= 30
            if done_indicator and stable_ready and (json_ready or clipboard_probe_ready):
                final_text = await self._finalize_response_text(context, page, text, extract_json_fn=extract_json_fn)
                task.update("waiting_response", "Đã nhận kết quả từ Gemini.")
                return final_text

            await asyncio.sleep(2)

        elapsed = int(timeout_seconds)
        logger.warning("Gemini response timeout after %ds for task %s", elapsed, task.task_id)
        await self._save_raw_debug(task, last_text, timeout_debug_reason)
        await self._save_timeout_summary(task, last_text, timeout_debug_reason, extract_json_fn)
        raise TimeoutError(
            f"Gemini xử lý quá lâu (>{timeout_seconds}s), chưa có JSON hoàn chỉnh. "
            "Browser đã đóng sau timeout an toàn. Hãy thử lại hoặc tăng gemini_timeout_seconds."
        )

    @staticmethod
    def _looks_like_schema_template(parsed: object) -> bool:
        if not isinstance(parsed, dict):
            return False
        metadata = parsed.get("metadata")
        if not isinstance(metadata, dict):
            return False
        hits = 0
        if metadata.get("video_title") == "string":
            hits += 1
        rewrite_script = parsed.get("rewrite_script")
        if isinstance(rewrite_script, dict) and rewrite_script.get("full_text") == "string":
            hits += 1
        srt_list = parsed.get("srt")
        if isinstance(srt_list, list) and len(srt_list) > 0:
            first_srt = srt_list[0]
            if isinstance(first_srt, dict) and first_srt.get("text") == "Subtitle text":
                hits += 1
        if isinstance(metadata.get("hashtags"), list) and metadata["hashtags"] == ["hashtag1", "hashtag2"]:
            hits += 1
        sources = parsed.get("sources")
        if isinstance(sources, list) and len(sources) > 0:
            first_source = sources[0]
            if isinstance(first_source, dict) and first_source.get("youtube_url") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ":
                hits += 1
        return hits >= 3

    @staticmethod
    def _looks_like_gemini_edl_root(parsed: object) -> bool:
        if not (
            isinstance(parsed, dict)
            and isinstance(parsed.get("metadata"), dict)
            and isinstance(parsed.get("rewrite_script"), dict)
            and isinstance(parsed.get("srt"), list)
            and isinstance(parsed.get("video_segments"), list)
        ):
            return False
        if GeminiAutomationService._looks_like_schema_template(parsed):
            return False
        return True

    def _extract_json_by_predicate(self, response_text: str, predicate: Callable[[object], bool]) -> str:
        if not response_text or len(response_text.strip()) < 100:
            return ""

        code_block_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", response_text)
        if code_block_match:
            json_str = code_block_match.group(1).strip()
            try:
                parsed = loads_json_with_repair(json_str)
                if predicate(parsed):
                    return json.dumps(parsed, ensure_ascii=False)
            except (json.JSONDecodeError, ValueError):
                pass

        brace_start = response_text.find("{")
        brace_end = response_text.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            json_str = response_text[brace_start : brace_end + 1]
            try:
                parsed = loads_json_with_repair(json_str)
                if predicate(parsed):
                    return json.dumps(parsed, ensure_ascii=False)
            except (json.JSONDecodeError, ValueError):
                pass

        for idx in range(len(response_text) - 1, -1, -1):
            if response_text[idx] != "{":
                continue
            depth = 0
            for j in range(idx, len(response_text)):
                if response_text[j] == "{":
                    depth += 1
                elif response_text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = response_text[idx : j + 1]
                        try:
                            parsed = loads_json_with_repair(candidate)
                            if predicate(parsed):
                                return json.dumps(parsed, ensure_ascii=False)
                        except (json.JSONDecodeError, ValueError):
                            pass
                        break
            if depth != 0:
                break

        return ""

    def _extract_json(self, response_text: str) -> str:
        return self._extract_json_by_predicate(response_text, self._looks_like_gemini_edl_root)

    @staticmethod
    def _build_simple_edl_repair_prompt(errors: list[str]) -> str:
        issue_lines = "\n".join(f"- {error}" for error in errors[:10])
        return (
            "REPAIR JSON VỪA TRẢ VỀ. JSON hiện tại chưa hợp lệ:\n"
            f"{issue_lines}\n\n"
            "Trả lại TOÀN BỘ JSON object đã sửa, không dùng Markdown và không giải thích. "
            "Giữ nguyên dữ kiện đã xác minh, schema và URL nguồn. "
            "rewrite_script.full_text phải được tạo bằng cách ghép NGUYÊN VĂN srt[].text theo index; "
            "không viết hai phiên bản độc lập, không đổi từ hoặc dấu câu. "
            "metadata.target_duration phải bằng chính xác end của SRT cuối. "
            "Mọi video_segments item phải có đầy đủ field bắt buộc, gồm scene_description. "
            "Tự parse và kiểm tra lại JSON trước khi trả."
        )

    def _extract_analysis_json(self, response_text: str) -> str:
        return self._extract_json_by_predicate(response_text, looks_like_analysis_root)

    def _extract_story_plan_json(self, response_text: str) -> str:
        return self._extract_json_by_predicate(response_text, looks_like_story_plan_root)

    def _extract_timeline_json(self, response_text: str) -> str:
        return self._extract_json_by_predicate(response_text, looks_like_timeline_root)

    def _extract_source_access_json(self, response_text: str) -> str:
        return self._extract_json_by_predicate(response_text, looks_like_source_access_root)

    def _extract_chapter_analysis_json(self, response_text: str) -> str:
        return self._extract_json_by_predicate(response_text, looks_like_chapter_analysis_root)

    def _extract_coverage_review_json(self, response_text: str) -> str:
        return self._extract_json_by_predicate(response_text, looks_like_coverage_review_root)

    def _extract_edit_strategy_json(self, response_text: str) -> str:
        return self._extract_json_by_predicate(response_text, looks_like_edit_strategy_root)

    def _extract_story_assembly_json(self, response_text: str) -> str:
        return self._extract_json_by_predicate(response_text, looks_like_story_assembly_root)

    def _extract_director_plan_json(self, response_text: str) -> str:
        return self._extract_json_by_predicate(response_text, looks_like_director_plan_root)

    def _extract_final_chunk_json(self, response_text: str) -> str:
        return self._extract_json_by_predicate(response_text, looks_like_final_chunk_root)

    def _extract_alignment_audit_json(self, response_text: str) -> str:
        return self._extract_json_by_predicate(response_text, looks_like_alignment_audit_root)

    @staticmethod
    def _response_has_minimum_segments(json_str: str) -> tuple[bool, int]:
        """Check parsed JSON has at least MIN_GEMINI_RESPONSE_SEGMENTS.

        Returns (is_valid: bool, segment_count: int).
        """
        try:
            parsed = json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            return False, 0

        if not isinstance(parsed, dict):
            return False, 0

        segments = parsed.get("video_segments", [])
        if not isinstance(segments, list):
            return False, 0

        return len(segments) >= MIN_GEMINI_RESPONSE_SEGMENTS, len(segments)

    @staticmethod
    def _response_is_login_or_error(response_text: str) -> bool:
        if not response_text:
            return False
        stripped = response_text.strip()
        if len(stripped) < 200:
            return False
        text = stripped.lower()
        login_keywords = [
            "sign in", "sign-in", "đăng nhập",
            "log in", "log-in",
            "not signed in", "login required",
        ]
        error_keywords = [
            "something went wrong",
            "there was an error",
        ]
        for keyword in login_keywords:
            if keyword in text:
                return True
        for keyword in error_keywords:
            if keyword in text:
                return True
        return False

    @staticmethod
    def _response_indicates_source_access_failure(response_text: str) -> bool:
        if not response_text:
            return False
        text = response_text.lower()
        markers = [
            "i can't watch videos",
            "i cannot watch videos",
            "i can't view videos",
            "i cannot view videos",
            "i can't access youtube",
            "i cannot access youtube",
            "i can't open links",
            "i cannot open links",
            "i don't have access to youtube",
            "as an ai",
            "based on the title",
            "based on the url",
            "không thể xem video",
            "không thể truy cập youtube",
            "không thể mở liên kết",
            "dựa trên tiêu đề",
            "dựa trên url",
        ]
        return any(marker in text for marker in markers)

    async def _validate_json_for_render(self, task: GeminiAutomationTask, json_str: str, render_payload: dict) -> tuple[bool, list[str], object | None]:
        retries = settings.gemini_retry_count
        valid = False
        errors: list[str] = []
        parsed = None

        for attempt in range(retries):
            task.update("validating", f"Đang validate JSON (lần {attempt + 1}/{retries})...")
            await asyncio.sleep(0)

            try:
                parsed_dict = loads_json_with_repair(json_str)
            except (json.JSONDecodeError, ValueError) as exc:
                errors = [f"JSON parse error: {exc}"]
                break

            validator = JsonValidator()
            render_options = RenderOptions.model_validate(render_payload.get("render_options") or {}) if render_payload.get("render_options") else None
            valid, errors, parsed_model, fixed = validator.validate_with_auto_fix(parsed_dict, render_options=render_options)
            parsed = fixed or parsed_model

            if valid:
                break

            if attempt < retries - 1:
                task.update("auto_retry", f"JSON chưa hợp lệ. Đang thử áp dụng auto-fix (lần {attempt + 2}/{retries})...")
                await asyncio.sleep(2)

        if not valid:
            try:
                debug_path = settings.temp_dir / "gemini_failed_response"
                debug_path.mkdir(parents=True, exist_ok=True)
                (debug_path / f"{task.task_id}_extracted.json").write_text(json_str, encoding="utf-8")
                (debug_path / f"{task.task_id}_errors.json").write_text(json.dumps(errors[:10], ensure_ascii=False), encoding="utf-8")
                logger.warning("Gemini JSON validation failed for task %s. Debug files saved to %s/", task.task_id, debug_path)
            except Exception:
                pass
            if settings.gemini_audit_enabled:
                try:
                    self._write_audit_artifact(task, "validation_errors.json", json.dumps(errors[:10], ensure_ascii=False, indent=2))
                    self._write_audit_artifact(task, "validation_input.json", json_str)
                except Exception:
                    logger.exception("Failed to save validation audit for task %s", task.task_id)
            return False, errors, None

        task.update("validating", "JSON hợp lệ.")
        if parsed:
            srt_count = len(parsed.srt) if hasattr(parsed, "srt") else 0
            seg_count = len(parsed.video_segments) if hasattr(parsed, "video_segments") else 0
            logger.info("Validation OK: srt=%d items, video_segments=%d items, metadata=%s",
                          srt_count, seg_count, parsed.metadata.video_title if hasattr(parsed, "metadata") and hasattr(parsed.metadata, "video_title") else "?")
        await asyncio.sleep(0)  # yield → WS handler thấy "validating"
        return True, errors, parsed

    async def _validate_without_render(self, task: GeminiAutomationTask, json_str: str, render_payload: dict) -> None:
        valid, errors, parsed = await self._validate_json_for_render(task, json_str, render_payload)
        if not valid:
            task.mark_error(
                f"Nội dung JSON Gemini trả về không hợp lệ: {'; '.join(errors[:3])}. Hãy kiểm tra lại prompt hoặc thử lại sau.",
                public_error="Nội dung chưa thể xử lý tự động. Vui lòng thử lại.",
            )
            return
        dump = parsed.model_dump() if hasattr(parsed, "model_dump") else parsed
        await self._save_json_debug(task, "dry_run_final_validated", dump if isinstance(dump, dict) else {"payload": dump})
        if isinstance(dump, dict):
            srt_count = len(dump.get("srt") or [])
            seg_count = len(dump.get("video_segments") or [])
        else:
            srt_count = len(getattr(parsed, "srt", []) or []) if parsed is not None else 0
            seg_count = len(getattr(parsed, "video_segments", []) or []) if parsed is not None else 0
        task.update("dry_run_done", "Dry-run hoàn tất: JSON Gemini hợp lệ, đã dừng trước render.")
        task.mark_done({"json_valid": True, "dry_run": True, "render_submitted": False, "srt_count": srt_count, "video_segment_count": seg_count, "gemini_json": dump})

    async def _validate_and_render(self, task: GeminiAutomationTask, json_str: str, render_payload: dict) -> None:
        valid, errors, parsed = await self._validate_json_for_render(task, json_str, render_payload)
        if not valid:
            task.mark_error(
                f"Nội dung JSON Gemini trả về không hợp lệ: {'; '.join(errors[:3])}. Hãy kiểm tra lại prompt hoặc thử lại sau.",
                public_error="Nội dung chưa thể xử lý tự động. Vui lòng thử lại.",
            )
            return

        dump = parsed.model_dump() if hasattr(parsed, "model_dump") else parsed
        render_payload_merged = dict(render_payload)
        render_payload_merged["gemini_json"] = dump

        task.update("submitting_render", "Đang gửi render job...")
        await asyncio.sleep(0)

        if self._submit_render_fn:
            try:
                job_id = await self._submit_render_fn(render_payload_merged, task.task_id)
                task._render_job_id = job_id
                task.update("submitting_render", f"Đã gửi render job. Job ID: {job_id}")
                await asyncio.sleep(0)  # yield → WS handler thấy "submitting_render" trước mark_done
                task.mark_done({"job_id": job_id, "json_valid": True})
            except Exception as exc:
                task.mark_error(f"Gửi render job thất bại: {exc}", _cancel_render_fn=self._cancel_render_fn)
        else:
            task.mark_error("Chức năng submit render chưa được cấu hình.")


gemini_service = GeminiAutomationService()
