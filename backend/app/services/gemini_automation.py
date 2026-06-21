from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from app.core.config import settings
from app.services.fingerprint import build_init_script, generate_fingerprint
from app.services.json_validator import JsonValidator

logger = logging.getLogger(__name__)

STEP_LABELS: dict[str, str] = {
    "init": "Khởi tạo",
    "init_browser": "Khởi tạo Chromium",
    "navigate_gemini": "Truy cập Gemini",
    "wait_login": "Đăng nhập Gemini",
    "submitting_prompt": "Gửi prompt",
    "waiting_response": "Gemini trả lời",
    "extracting_json": "Trích xuất dữ liệu",
    "validating": "Kiểm tra dữ liệu",
    "auto_retry": "Thử lại",
    "submitting_render": "Tạo video",
    "cancelling": "Đang hủy",
}

GEMINI_SELECTORS = {
    "prompt_input": [
        "div[contenteditable='true']",
        "[role='textbox']",
        "textarea",
    ],
    "send_button": [
        "button[aria-label*='Send']",
        "button[data-test-id='send-button']",
        "button.send-button",
        "button[class*='send']",
    ],
    "stop_button": [
        "button:has-text('Stop')",
        "button[aria-label*='Stop']",
        "button[aria-label*='stop']",
        "button[class*='stop']",
        "[data-test-id='stop-generation']",
        "button:has-text('Dừng')",
    ],
    "sign_in_indicators": [
        "a[href*='SignOut']",
        "a[href*='signin']",
        "a[href*='accounts.google.com']",
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
    ],
    "chat_area": [
        "[role='textbox']",
        "div[contenteditable='true']",
        "textarea",
    ],
}


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
        self.states: list[dict] = []
        self._event = asyncio.Event()

    def _push_state(self, step: str) -> None:
        now = time.time()
        if self.states:
            prev = self.states[-1]
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

    def mark_error(self, error: str) -> None:
        self.status = "error"
        self.step = "error"
        self.message = error
        self.error = error
        if self.states:
            cur = self.states[-1]
            if cur["end_ts"] is None:
                cur["end_ts"] = time.time()
            cur["status"] = "error"
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
    _submit_render_fn: Callable[[dict], str] | None = None
    _browsers: dict[str, dict] = {}
    _browser_tasks: dict[str, asyncio.Task] = {}

    def set_submit_render_fn(self, fn: Callable[[dict], str]) -> None:
        self._submit_render_fn = fn

    def _get_user_data_dir(self) -> str | None:
        return settings.gemini_user_data_dir

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
        parts = [user_data_dir or 'default']
        for c in auth_cookies:
            if c['name'] in ('SAPISID', '__Secure-3PSAPISID'):
                parts.append(c['value'][:16])
                break
        import time as _t
        parts.append(str(_t.time_ns()))
        return '|'.join(parts)

    async def _launch_stealth_context(
        self,
        pw: Any,
        user_data_dir: str | None = None,
        auth_cookies: list[dict] | None = None,
        headless: bool = True,
        storage_state_path: str | Path | None = None,
    ) -> tuple[Any, Any, Any]:

        ac = auth_cookies or []
        seed = self._stealth_seed(user_data_dir, ac)
        fp = generate_fingerprint(seed)
        stealth_js = build_init_script(fp)
        args = [
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-web-security',
        ]
        if headless:
            args.append('--headless')
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
        page.set_default_timeout(30000)
        return browser, context, page

    def get_session_status(self) -> dict:
        session_path = Path(settings.gemini_session_path)
        if not session_path.exists():
            return {"exists": False, "path": str(session_path)}
        try:
            data = json.loads(session_path.read_text(encoding="utf-8"))
            cookies = data.get("cookies", [])
            has_auth = any(c["name"] in {"SAPISID", "__Secure-3PSAPISID", "OSID"} for c in cookies)
            return {"exists": has_auth, "path": str(session_path)}
        except Exception:
            return {"exists": False, "path": str(session_path)}

    async def open_standalone_browser(self, user_data_dir: str | None = None) -> str:
        browser_id = str(uuid.uuid4())
        task = asyncio.create_task(self._run_standalone_browser(browser_id, user_data_dir))
        self._browser_tasks[browser_id] = task
        return browser_id

    async def _run_standalone_browser(self, browser_id: str, user_data_dir: str | None = None) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.exception("playwright not installed")
            return

        try:
            async with async_playwright() as pw:
                browsers_path = settings.playwright_browsers_path
                if browsers_path:
                    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path

                self._browsers[browser_id] = {"status": "launching"}
                session_path = Path(settings.gemini_session_path)

                auth_cookies: list[dict] = []
                if user_data_dir:
                    pd = self._profile_dir(user_data_dir)
                    if pd:
                        auth_cookies = self._extract_auth_cookies(pd)
                        logger.info("Extracted %d auth cookies from %s", len(auth_cookies), pd)

                browser, context, page = await self._launch_stealth_context(
                    pw, user_data_dir, auth_cookies, headless=False,
                )

                await page.goto(settings.gemini_url, wait_until="domcontentloaded")

                self._browsers[browser_id] = {
                    "status": "open",
                    "browser": browser,
                    "context": context,
                    "page": page,
                }

                await page.wait_for_load_state("networkidle")

                async def _save_loop():
                    while True:
                        await asyncio.sleep(10)
                        try:
                            await context.storage_state(path=str(session_path))
                        except Exception:
                            return

                save_task = asyncio.create_task(_save_loop())

                closed = asyncio.Event()
                browser.on("disconnected", lambda: closed.set())
                await closed.wait()

                save_task.cancel()
                try:
                    await save_task
                except Exception:
                    pass

        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Standalone browser failed")
        finally:
            self._browsers.pop(browser_id, None)
            self._browser_tasks.pop(browser_id, None)

    async def close_standalone_browser(self, browser_id: str) -> bool:
        entry = self._browsers.pop(browser_id, None)
        if entry and entry.get("browser"):
            try:
                await entry["browser"].close()
                return True
            except Exception:
                return False
        return False

    def start(self, task_id: str, prompt_text: str, render_payload: dict, user_data_dir: str | None = None) -> GeminiAutomationTask:
        task = GeminiAutomationTask(task_id)
        self._tasks[task_id] = task
        ud = user_data_dir or self._get_user_data_dir()
        asyncio.create_task(self._run_pipeline(task, prompt_text, render_payload, ud))
        return task

    def get_task(self, task_id: str) -> GeminiAutomationTask | None:
        return self._tasks.get(task_id)

    def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.status == "running":
            task.cancel_requested = True
            task.update("cancelling", "Đang hủy...")
            return True
        return False

    async def _run_pipeline(self, task: GeminiAutomationTask, prompt_text: str, render_payload: dict, user_data_dir: str | None = None) -> None:
        browser = None
        context = None
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

                if user_data_dir:
                    pd = self._profile_dir(user_data_dir)
                    auth_cookies = self._extract_auth_cookies(pd) if pd else []
                    logger.info("Pipeline extracted %d auth cookies from %s", len(auth_cookies), pd)
                    if auth_cookies:
                        task.update("navigate_gemini", "Đã nạp cookies từ Chrome profile.")
                        browser, context, page = await self._launch_stealth_context(
                            pw, user_data_dir, auth_cookies, headless=settings.playwright_headless,
                        )
                    elif session_path.exists():
                        task.update("navigate_gemini", "Đang khởi tạo phiên làm việc đã lưu...")
                        browser, context, page = await self._launch_stealth_context(
                            pw, user_data_dir, headless=settings.playwright_headless,
                            storage_state_path=session_path,
                        )
                    else:
                        task.update("navigate_gemini", "Đang khởi tạo phiên mới...")
                        browser, context, page = await self._launch_stealth_context(
                            pw, headless=settings.playwright_headless,
                        )
                elif session_path.exists():
                    task.update("navigate_gemini", "Đang khởi tạo phiên làm việc đã lưu...")
                    browser, context, page = await self._launch_stealth_context(
                        pw, user_data_dir, headless=settings.playwright_headless,
                        storage_state_path=session_path,
                    )
                else:
                    task.update("navigate_gemini", "Đang khởi tạo phiên mới...")
                    browser, context, page = await self._launch_stealth_context(
                        pw, headless=settings.playwright_headless,
                    )

                task.update("navigate_gemini", "Đang truy cập Gemini...")
                await page.goto(settings.gemini_url, wait_until="domcontentloaded")

                await self._handle_login_if_needed(task, page, context, session_path)
                if task.status != "running":
                    return

                await self._submit_prompt(task, page, prompt_text)
                if task.status != "running":
                    return

                response_text = await self._wait_for_response(task, page, context)
                await asyncio.sleep(0)  # yield → WS handler thấy "waiting_response"

                json_str = ""
                for retry in range(3):
                    if task.status != "running":
                        return
                    task.update("extracting_json", f"Đang trích xuất JSON (lần {retry + 1}/3)...")
                    await asyncio.sleep(0)
                    json_str = self._extract_json(response_text)
                    if json_str:
                        break
                    if retry < 2:
                        await asyncio.sleep(3)
                        response_text = await self._wait_for_response(task, page, context)

                if not json_str:
                    task.mark_error("Không thể trích xuất JSON từ phản hồi Gemini sau 3 lần thử.")
                    return

                await self._validate_and_render(task, json_str, render_payload)

        except asyncio.CancelledError:
            task.mark_error("Pipeline bị hủy.")
        except Exception as exc:
            logger.exception("Gemini automation pipeline failed")
            task.mark_error(str(exc))
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

    @staticmethod
    async def _check_cookies_logged_in(context: Any) -> bool:
        cookies = await context.cookies()
        return any(c["name"] in {"SAPISID", "__Secure-3PSAPISID", "OSID"} for c in cookies)

    async def _handle_login_if_needed(
        self,
        task: GeminiAutomationTask,
        page: Any,
        context: Any,
        session_path: Path,
    ) -> None:
        await page.wait_for_load_state("networkidle")

        is_logged_in = await self._check_cookies_logged_in(context)

        if not is_logged_in:
            chat_count = 0
            for sel in GEMINI_SELECTORS["chat_area"]:
                chat_count = await page.locator(sel).count()
                if chat_count > 0:
                    break

            sign_in_count = 0
            for sel in GEMINI_SELECTORS["sign_in_indicators"]:
                sign_in_count = await page.locator(sel).count()
                if sign_in_count > 0:
                    break

            avatar_count = 0
            for sel in GEMINI_SELECTORS["user_avatar"]:
                avatar_count = await page.locator(sel).count()
                if avatar_count > 0:
                    break

            if chat_count > 0 and sign_in_count == 0:
                is_logged_in = True
            elif avatar_count > 0:
                is_logged_in = True

        if not is_logged_in:
            task.update("wait_login", "Vui lòng đăng nhập Gemini trên trình duyệt vừa mở. Bạn có 5 phút.", detail={"login_required": True})
            try:
                await page.wait_for_url("**/app", timeout=300000)
                await asyncio.sleep(3)
                task.update("wait_login", "Đã phát hiện đăng nhập thành công. Đang lưu phiên làm việc...")
                await context.storage_state(path=str(session_path))
                task.update("wait_login", "Phiên làm việc đã được lưu.")
            except Exception:
                task.mark_error("Quá thời gian chờ đăng nhập Gemini. Vui lòng thử lại.")
        else:
            if not session_path.exists():
                try:
                    await context.storage_state(path=str(session_path))
                except Exception:
                    pass

    async def _submit_prompt(self, task: GeminiAutomationTask, page: Any, prompt_text: str) -> None:
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
                task.mark_error("Không tìm thấy ô nhập prompt trên Gemini.")
                return

        task.update("submitting_prompt", "Đang nhập prompt...")
        await input_element.click()
        await asyncio.sleep(0.5)

        await page.keyboard.insert_text(prompt_text)
        await asyncio.sleep(1)

        entered = await input_element.inner_text()
        if len(entered.strip()) < 50:
            await input_element.click()
            await page.keyboard.type(prompt_text[:10])
            await page.keyboard.insertText(prompt_text[10:])
            await asyncio.sleep(1)

        task.update("submitting_prompt", "Đang gửi prompt đến Gemini...")
        await page.keyboard.press("Enter")
        task.update("waiting_response", "Đã gửi prompt. Đang chờ Gemini xử lý...")

    async def _wait_for_response(self, task: GeminiAutomationTask, page: Any, context: Any) -> str:
        stop_sel = None
        for sel in GEMINI_SELECTORS["stop_button"]:
            count = await page.locator(sel).count()
            if count > 0:
                stop_sel = sel
                break

        if stop_sel:
            try:
                await page.locator(stop_sel).first.wait_for(state="visible", timeout=15000)
            except Exception:
                pass
            try:
                await page.locator(stop_sel).first.wait_for(state="hidden", timeout=settings.gemini_timeout_seconds * 1000)
            except Exception:
                pass

        task.update("waiting_response", "Đang chờ Gemini trả kết quả...")

        prev_len = 0
        stable = 0
        for _ in range(60):
            cur = len(await page.evaluate("document.body.innerText || ''"))
            if cur == prev_len and cur > 5000:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
            prev_len = cur
            await asyncio.sleep(2)

        task.update("waiting_response", "Đang sao chép kết quả từ Gemini...")

        try:
            await context.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass

        copy_btn = page.locator('[data-test-id="copy-button"]').last
        if await copy_btn.count() > 0:
            for _ in range(2):
                try:
                    await copy_btn.click(timeout=5000)
                    await asyncio.sleep(2)
                    response_text = await page.evaluate("navigator.clipboard.readText()")
                    if response_text and len(response_text.strip()) > 100:
                        task.update("waiting_response", "Đã nhận kết quả từ Gemini.")
                        return response_text
                except Exception:
                    pass
                await asyncio.sleep(1)

        task.update("waiting_response", "Đang đọc nội dung từ trang Gemini...")
        response_text = await page.evaluate("document.body.innerText || ''")
        task.update("waiting_response", "Đã nhận kết quả từ Gemini.")
        return response_text or ""

    def _extract_json(self, response_text: str) -> str:
        if not response_text or len(response_text.strip()) < 100:
            return ""

        code_block_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", response_text)
        if code_block_match:
            json_str = code_block_match.group(1).strip()
            try:
                parsed = json.loads(json_str)
                return json.dumps(parsed, ensure_ascii=False)
            except json.JSONDecodeError:
                pass

        brace_start = response_text.find("{")
        brace_end = response_text.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            json_str = response_text[brace_start : brace_end + 1]
            try:
                parsed = json.loads(json_str)
                return json.dumps(parsed, ensure_ascii=False)
            except json.JSONDecodeError:
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
                            parsed = json.loads(candidate)
                            return json.dumps(parsed, ensure_ascii=False)
                        except json.JSONDecodeError:
                            break
            if depth == 0:
                break

        return ""

    async def _validate_and_render(self, task: GeminiAutomationTask, json_str: str, render_payload: dict) -> None:
        retries = settings.gemini_retry_count
        valid = False
        errors: list[str] = []
        parsed = None

        for attempt in range(retries):
            task.update("validating", f"Đang validate JSON (lần {attempt + 1}/{retries})...")
            await asyncio.sleep(0)

            validator = JsonValidator()
            valid, errors, parsed_model, fixed = validator.validate_with_auto_fix(json.loads(json_str))
            parsed = fixed or parsed_model

            if valid:
                break

            if attempt < retries - 1:
                task.update("auto_retry", f"JSON chưa hợp lệ. Đang thử lại lần {attempt + 2}...")
                await asyncio.sleep(2)

        if not valid:
            task.mark_error(f"JSON không hợp lệ sau {retries} lần thử: {'; '.join(errors[:3])}")
            return

        task.update("validating", "JSON hợp lệ.")
        await asyncio.sleep(0)  # yield → WS handler thấy "validating"

        dump = parsed.model_dump() if hasattr(parsed, "model_dump") else parsed
        render_payload_merged = dict(render_payload)
        render_payload_merged["gemini_json"] = dump

        task.update("submitting_render", "Đang gửi render job...")
        await asyncio.sleep(0)

        if self._submit_render_fn:
            try:
                job_id = self._submit_render_fn(render_payload_merged)
                task.update("submitting_render", f"Đã gửi render job. Job ID: {job_id}")
                await asyncio.sleep(0)  # yield → WS handler thấy "submitting_render" trước mark_done
                task.mark_done({"job_id": job_id, "json_valid": True})
            except Exception as exc:
                task.mark_error(f"Gửi render job thất bại: {exc}")
        else:
            task.mark_error("Chức năng submit render chưa được cấu hình.")


gemini_service = GeminiAutomationService()
