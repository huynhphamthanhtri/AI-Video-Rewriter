from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from app.schemas.batch import BatchItemProgress, BatchProgress
from app.schemas.prompt import PromptGenerateRequest
from app.services.gemini_automation import GeminiAutomationService, gemini_service
from app.services.prompt_generator import PromptGenerator
from app.services.video_tools import ui_safe_error


RenderStatusGetter = Callable[[str], dict | None]
SleepFn = Callable[[float], Awaitable[None]]


class BatchPipelineService:
    def __init__(
        self,
        automation_service: GeminiAutomationService | None = None,
        render_status_getter: RenderStatusGetter | None = None,
        sleep_fn: SleepFn | None = None,
    ) -> None:
        self.automation_service = automation_service or gemini_service
        self.render_status_getter = render_status_getter
        self.sleep_fn = sleep_fn or asyncio.sleep
        self._batches: dict[str, BatchProgress] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._cancel_requested: set[str] = set()
        self._cancel_render_fn: Callable[[str], None] | None = None

    def set_render_status_getter(self, getter: RenderStatusGetter) -> None:
        self.render_status_getter = getter

    def set_cancel_render_fn(self, fn: Callable[[str], None]) -> None:
        self._cancel_render_fn = fn

    def start(
        self,
        *,
        form_data: dict,
        render_options: dict,
        subtitle_mode: str,
        ytdlp_cookies_file: str | None = None,
        ytdlp_cookies_from_browser: str | None = None,
        local_video_path: str | None = None,
        user_data_dir: str | None = None,
        headless: bool | None = None,
        gemini_thinking_mode: str = "extended",
        gemini_analysis_mode: str = "deep_analysis",
    ) -> BatchProgress:
        urls = self._extract_urls(form_data)
        batch_id = str(uuid.uuid4())
        batch = BatchProgress(
            batch_id=batch_id,
            status="pending",
            total_items=len(urls),
            items=[BatchItemProgress(index=index, source_url=url) for index, url in enumerate(urls)],
        )
        self._batches[batch_id] = batch
        self._tasks[batch_id] = asyncio.create_task(
            self._run_batch(
                batch_id=batch_id,
                form_data=form_data,
                render_options=render_options,
                subtitle_mode=subtitle_mode,
                ytdlp_cookies_file=ytdlp_cookies_file,
                ytdlp_cookies_from_browser=ytdlp_cookies_from_browser,
                local_video_path=local_video_path,
                user_data_dir=user_data_dir,
                headless=headless,
                gemini_thinking_mode=gemini_thinking_mode,
                gemini_analysis_mode=gemini_analysis_mode,
            )
        )
        return batch

    def get(self, batch_id: str) -> BatchProgress | None:
        return self._batches.get(batch_id)

    def cancel(self, batch_id: str) -> bool:
        batch = self._batches.get(batch_id)
        if not batch or batch.status in {"done", "error", "cancelled"}:
            return False
        self._cancel_requested.add(batch_id)
        batch.status = "cancelled"
        batch.ended_at = time.time()
        for item in batch.items:
            if item.status == "pending":
                item.status = "cancelled"
                item.ended_at = batch.ended_at
            elif item.status == "running":
                item.status = "cancelled"
                item.ended_at = batch.ended_at
                if item.task_id:
                    self.automation_service.cancel(item.task_id)
                if item.job_id and self._cancel_render_fn:
                    try:
                        self._cancel_render_fn(item.job_id)
                    except Exception:
                        pass
        return True

    def _extract_urls(self, form_data: dict) -> list[str]:
        raw_urls = form_data.get("youtube_urls") or []
        urls = [str(url).strip() for url in raw_urls if str(url).strip()]
        if not urls and form_data.get("youtube_url"):
            urls = [str(form_data["youtube_url"]).strip()]
        seen: set[str] = set()
        unique_urls: list[str] = []
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            unique_urls.append(url)
        if len(unique_urls) < 2:
            raise ValueError("Batch cần ít nhất 2 YouTube URL.")
        return unique_urls

    async def _run_batch(
        self,
        *,
        batch_id: str,
        form_data: dict,
        render_options: dict,
        subtitle_mode: str,
        ytdlp_cookies_file: str | None,
        ytdlp_cookies_from_browser: str | None = None,
        local_video_path: str | None,
        user_data_dir: str | None,
        headless: bool | None = None,
        gemini_thinking_mode: str = "extended",
        gemini_analysis_mode: str = "deep_analysis",
    ) -> None:
        batch = self._batches[batch_id]
        batch.status = "running"
        batch.started_at = time.time()
        try:
            for item in batch.items:
                if batch_id in self._cancel_requested:
                    self._mark_remaining_cancelled(batch, item.index)
                    return
                batch.current_index = item.index
                await self._run_item(
                    batch=batch,
                    item=item,
                    form_data=form_data,
                    render_options=render_options,
                    subtitle_mode=subtitle_mode,
                    ytdlp_cookies_file=ytdlp_cookies_file,
                    ytdlp_cookies_from_browser=ytdlp_cookies_from_browser,
                    local_video_path=local_video_path,
                    user_data_dir=user_data_dir,
                    headless=headless,
                    gemini_thinking_mode=gemini_thinking_mode,
                    gemini_analysis_mode=gemini_analysis_mode,
                )
            self._finish_batch(batch)
        except Exception as exc:  # noqa: BLE001
            batch.status = "error"
            msg = ui_safe_error(str(exc))
            if not msg:
                msg = f"{type(exc).__name__}: lỗi nội bộ khi xử lý batch pipeline."
            batch.error = msg
            batch.ended_at = time.time()

    async def _run_item(
        self,
        *,
        batch: BatchProgress,
        item: BatchItemProgress,
        form_data: dict,
        render_options: dict,
        subtitle_mode: str,
        ytdlp_cookies_file: str | None,
        ytdlp_cookies_from_browser: str | None = None,
        local_video_path: str | None,
        user_data_dir: str | None,
        headless: bool | None = None,
        gemini_thinking_mode: str = "extended",
        gemini_analysis_mode: str = "deep_analysis",
    ) -> None:
        item.status = "running"
        item.started_at = time.time()
        try:
            item_form = dict(form_data)
            item_form["youtube_url"] = item.source_url
            item_form["youtube_urls"] = [item.source_url]
            item_form["source_mode"] = "single"
            prompt_req = PromptGenerateRequest.model_validate(item_form)
            prompt = PromptGenerator().generate(prompt_req)
            render_payload = {
                "youtube_url": item.source_url,
                "local_video_path": local_video_path,
                "ytdlp_cookies_file": ytdlp_cookies_file,
                "ytdlp_cookies_from_browser": ytdlp_cookies_from_browser,
                "user_data_dir": user_data_dir,
                "burn_subtitle": subtitle_mode == "burn",
                "subtitle_mode": subtitle_mode,
                "render_options": render_options,
                "gemini_json": {},
                "output_dir_name": form_data.get("output_dir_name"),
                "output_dir_path": form_data.get("output_dir_path"),
            }
            task_id = str(uuid.uuid4())
            task = self.automation_service.start(task_id, prompt, render_payload, user_data_dir, headless=headless,
                                                     thinking_mode=gemini_thinking_mode,
                                                     analysis_mode=gemini_analysis_mode,
                                                     form_data=item_form)
            item.task_id = task_id

            while task.status == "running":
                if batch.batch_id in self._cancel_requested:
                    self.automation_service.cancel(task_id)
                    item.status = "cancelled"
                    item.ended_at = time.time()
                    return
                item.states = list(task.states)
                await task.wait_for_update(timeout=1.0)

            item.states = list(task.states)
            if task.status == "error":
                item.status = "error"
                item.error = task.error or task.message or "Auto pipeline item failed without error detail. Xem logs/error.log."
                item.ended_at = time.time()
                return
            if task.result and task.result.get("cancelled"):
                item.status = "cancelled"
                item.result = task.result
                item.ended_at = time.time()
                return

            item.result = task.result
            item.job_id = str((task.result or {}).get("job_id") or "") or None
            if not item.job_id:
                item.status = "error"
                item.error = "Auto pipeline did not return render job_id."
                item.ended_at = time.time()
                return

            render_status = await self._wait_for_render_job(batch.batch_id, item, item.job_id)
            if batch.batch_id in self._cancel_requested:
                item.status = "cancelled"
                item.ended_at = time.time()
                return
            item.result = render_status.get("result") or item.result
            if render_status.get("status") == "done":
                item.status = "done"
            elif render_status.get("status") == "cancelled":
                item.status = "cancelled"
            else:
                item.status = "error"
                item.error = render_status.get("message") or "; ".join(render_status.get("errors") or []) or "Render job failed."
            item.ended_at = time.time()
        except Exception as exc:  # noqa: BLE001
            item.status = "error"
            msg = ui_safe_error(str(exc))
            if not msg:
                msg = f"{type(exc).__name__}: lỗi nội bộ khi chạy batch item."
            item.error = msg
            item.ended_at = time.time()

    async def _wait_for_render_job(self, batch_id: str, item: BatchItemProgress, job_id: str) -> dict[str, Any]:
        if self.render_status_getter is None:
            raise RuntimeError("Batch render status getter is not configured.")
        while True:
            if batch_id in self._cancel_requested:
                if job_id and self._cancel_render_fn:
                    try:
                        self._cancel_render_fn(job_id)
                    except Exception:
                        pass
                return {"status": "cancelled", "message": "Batch cancelled."}
            status = self.render_status_getter(job_id)
            if status is None:
                raise RuntimeError("Render job không tồn tại.")
            item.render_status = status
            if status.get("status") in {"done", "error", "cancelled"}:
                return status
            await self.sleep_fn(2.0)

    def _mark_remaining_cancelled(self, batch: BatchProgress, start_index: int) -> None:
        now = time.time()
        for item in batch.items[start_index:]:
            if item.status in {"pending", "running"}:
                item.status = "cancelled"
                item.ended_at = now
        batch.status = "cancelled"
        batch.ended_at = now

    def _finish_batch(self, batch: BatchProgress) -> None:
        batch.ended_at = time.time()
        if any(item.status == "done" for item in batch.items):
            batch.status = "done"
            return
        if all(item.status == "cancelled" for item in batch.items):
            batch.status = "cancelled"
            return
        batch.status = "error"
        first_error = next((item.error for item in batch.items if item.error), "")
        batch.error = first_error and f"All batch items failed. Error đầu tiên: {first_error}" or "All batch items failed."


batch_service = BatchPipelineService()
