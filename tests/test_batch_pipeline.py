import asyncio
import json

from app.api import routes
from app.schemas.prompt import GeminiAutoSubmitRequest
from app.services.batch_pipeline import BatchPipelineService


FORM_DATA = {
    "youtube_url": "https://www.youtube.com/watch?v=one",
    "youtube_urls": [
        "https://www.youtube.com/watch?v=one",
        "https://www.youtube.com/watch?v=two",
    ],
    "source_mode": "multi",
    "preset_name": "US COPS Documentary",
    "rewrite_style": "Điều tra",
    "target_audience": "Đại chúng",
    "tone": "Nghiêm túc",
    "target_duration": "5-10 phút",
    "retention_mode": "Cao",
    "hook_style": "Cảnh đắt giá",
    "clip_strategy": "Giữ đầy đủ ngữ cảnh",
    "reuse_level": "Cao",
    "content_density": "Trung bình",
    "target_language": "Tiếng Việt",
    "target_market": "Việt Nam",
    "localization_level": "medium",
    "rename_characters": False,
    "adapt_culture": True,
    "adapt_currency": True,
    "adapt_units": True,
    "adapt_company_names": False,
    "adaptation_mode": "faithful",
    "narrator_persona": "detective",
}


class FakeAutomationTask:
    def __init__(self, task_id: str, status: str = "done", result: dict | None = None, error: str | None = None):
        self.task_id = task_id
        self.status = status
        self.result = result
        self.error = error
        self.message = error or "ok"
        self.states = []

    async def wait_for_update(self, timeout: float = 1.0) -> bool:
        return False


class FakeAutomationService:
    def __init__(self, fail_urls: set[str] | None = None):
        self.fail_urls = fail_urls or set()
        self.started_urls: list[str] = []
        self.cancelled: list[str] = []
        self.last_render_payload: dict | None = None

    def start(self, task_id: str, prompt_text: str, render_payload: dict, user_data_dir: str | None = None,
              headless: bool | None = None, thinking_mode: str = "extended",
              model: str = "gemini-3.6-flash",
              form_data: dict | None = None):
        self.last_render_payload = render_payload
        url = render_payload["youtube_url"]
        self.started_urls.append(url)
        if url in self.fail_urls:
            return FakeAutomationTask(task_id, status="error", error="Gemini failed")
        return FakeAutomationTask(task_id, result={"job_id": f"job-{len(self.started_urls)}", "json_valid": True})

    def cancel(self, task_id: str) -> bool:
        self.cancelled.append(task_id)
        return True


async def no_sleep(seconds: float) -> None:
    return None


def test_batch_creation_has_two_pending_items(monkeypatch):
    monkeypatch.setattr("app.services.batch_pipeline.PromptGenerator.generate", lambda self, data: "prompt")
    service = BatchPipelineService(FakeAutomationService(), lambda job_id: {"status": "done", "result": {"final_video_path": job_id}}, no_sleep)

    async def run():
        batch = service.start(form_data=FORM_DATA, render_options={}, subtitle_mode="burn")
        initial_statuses = [item.status for item in batch.items]
        service.cancel(batch.batch_id)
        await service._tasks[batch.batch_id]
        return batch, initial_statuses

    batch, initial_statuses = asyncio.run(run())

    assert batch.total_items == 2
    assert initial_statuses == ["pending", "pending"]
    assert [item.source_url for item in batch.items] == FORM_DATA["youtube_urls"]


def test_batch_runs_items_sequentially(monkeypatch):
    monkeypatch.setattr("app.services.batch_pipeline.PromptGenerator.generate", lambda self, data: "prompt")
    automation = FakeAutomationService()
    events: list[str] = []
    render_calls = {"job-1": 0, "job-2": 0}

    def render_status(job_id: str) -> dict:
        events.append(f"render:{job_id}:{render_calls[job_id]}")
        render_calls[job_id] += 1
        if job_id == "job-1" and render_calls[job_id] == 1:
            return {"status": "running"}
        return {"status": "done", "result": {"final_video_path": job_id}}

    async def tracked_sleep(seconds: float) -> None:
        events.append(f"sleep:start_count:{len(automation.started_urls)}")

    service = BatchPipelineService(automation, render_status, tracked_sleep)

    async def run():
        batch = service.start(form_data=FORM_DATA, render_options={}, subtitle_mode="burn")
        await service._tasks[batch.batch_id]
        return batch

    batch = asyncio.run(run())

    assert automation.started_urls == FORM_DATA["youtube_urls"]
    assert events[0:2] == ["render:job-1:0", "sleep:start_count:1"]
    assert batch.status == "done"
    assert [item.status for item in batch.items] == ["done", "done"]


def test_first_item_error_does_not_stop_second_item(monkeypatch):
    monkeypatch.setattr("app.services.batch_pipeline.PromptGenerator.generate", lambda self, data: "prompt")
    automation = FakeAutomationService(fail_urls={FORM_DATA["youtube_urls"][0]})
    service = BatchPipelineService(automation, lambda job_id: {"status": "done", "result": {"final_video_path": job_id}}, no_sleep)

    async def run():
        batch = service.start(form_data=FORM_DATA, render_options={}, subtitle_mode="burn")
        await service._tasks[batch.batch_id]
        return batch

    batch = asyncio.run(run())

    assert automation.started_urls == FORM_DATA["youtube_urls"]
    assert [item.status for item in batch.items] == ["error", "done"]
    assert batch.status == "done"


def test_completed_batch_persists_across_service_restart(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.batch_pipeline.PromptGenerator.generate", lambda self, data: "prompt")
    storage = tmp_path / "batch_queue.json"
    automation = FakeAutomationService()
    service = BatchPipelineService(
        automation,
        lambda job_id: {"status": "done", "result": {"final_video_path": job_id}},
        no_sleep,
        storage_path=storage,
    )

    async def run():
        batch = service.start(form_data=FORM_DATA, render_options={}, subtitle_mode="burn")
        await service._tasks[batch.batch_id]
        return batch.batch_id

    batch_id = asyncio.run(run())
    restored = BatchPipelineService(FakeAutomationService(), storage_path=storage)
    batch = restored.get(batch_id)
    assert batch is not None
    assert batch.status == "done"
    assert [item.status for item in batch.items] == ["done", "done"]


def test_restart_marks_interrupted_item_failed_and_continues_next(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.batch_pipeline.PromptGenerator.generate", lambda self, data: "prompt")
    storage = tmp_path / "batch_queue.json"
    storage.write_text(json.dumps({
        "version": 1,
        "batches": [{
            "progress": {
                "batch_id": "persisted",
                "status": "running",
                "total_items": 2,
                "current_index": 0,
                "items": [
                    {"index": 0, "source_url": FORM_DATA["youtube_urls"][0], "status": "running"},
                    {"index": 1, "source_url": FORM_DATA["youtube_urls"][1], "status": "pending"},
                ],
            },
            "config": {
                "form_data": FORM_DATA,
                "render_options": {},
                "subtitle_mode": "burn",
                "local_video_path": None,
                "ytdlp_cookies_file": None,
                "ytdlp_cookies_from_browser": None,
                "user_data_dir": None,
                "headless": True,
                "gemini_thinking_mode": "standard",
            },
        }],
    }), encoding="utf-8")
    automation = FakeAutomationService()
    service = BatchPipelineService(
        automation,
        lambda job_id: {"status": "done", "result": {"final_video_path": job_id}},
        no_sleep,
        storage_path=storage,
    )
    batch = service.get("persisted")
    assert batch is not None
    assert batch.status == "pending"
    assert [item.status for item in batch.items] == ["error", "pending"]
    assert "restarted" in (batch.items[0].error or "")

    async def resume():
        service.resume_pending()
        await service._tasks["persisted"]

    asyncio.run(resume())
    assert automation.started_urls == [FORM_DATA["youtube_urls"][1]]
    assert [item.status for item in batch.items] == ["error", "done"]
    assert batch.status == "done"


def test_queue_endurance_runs_twenty_items_sequentially_and_continues_failures(monkeypatch):
    monkeypatch.setattr("app.services.batch_pipeline.PromptGenerator.generate", lambda self, data: "prompt")
    urls = [f"https://www.youtube.com/watch?v=endurance{i:02d}" for i in range(20)]
    fail_urls = set(urls[::5])
    automation = FakeAutomationService(fail_urls=fail_urls)
    service = BatchPipelineService(
        automation,
        lambda job_id: {"status": "done", "result": {"final_video_path": job_id}},
        no_sleep,
    )
    form_data = {**FORM_DATA, "youtube_url": urls[0], "youtube_urls": urls}

    async def run():
        batch = service.start(form_data=form_data, render_options={}, subtitle_mode="srt")
        await service._tasks[batch.batch_id]
        return batch

    batch = asyncio.run(run())
    assert automation.started_urls == urls
    assert sum(item.status == "error" for item in batch.items) == len(fail_urls)
    assert sum(item.status == "done" for item in batch.items) == 20 - len(fail_urls)
    assert batch.status == "done"


def test_cancel_batch_marks_running_and_pending_items(monkeypatch):
    monkeypatch.setattr("app.services.batch_pipeline.PromptGenerator.generate", lambda self, data: "prompt")
    automation = FakeAutomationService()
    service = BatchPipelineService(automation, lambda job_id: {"status": "running"}, no_sleep)

    original_sleep = service.sleep_fn

    async def cancel_on_sleep(seconds: float) -> None:
        service.cancel(next(iter(service._batches)))
        await original_sleep(seconds)

    service.sleep_fn = cancel_on_sleep
    async def run():
        batch = service.start(form_data=FORM_DATA, render_options={}, subtitle_mode="burn")
        await service._tasks[batch.batch_id]
        return batch

    batch = asyncio.run(run())

    assert batch.status == "cancelled"
    assert automation.started_urls == [FORM_DATA["youtube_urls"][0]]
    assert [item.status for item in batch.items] == ["cancelled", "cancelled"]
    assert automation.cancelled


def test_single_auto_submit_route_remains_registered():
    paths = {route.path for route in routes.router.routes}

    assert "/gemini/auto-submit" in paths
    assert "/gemini/batch-auto-submit" in paths


def test_auto_submit_defaults_to_video_without_burned_subtitles():
    assert GeminiAutoSubmitRequest().subtitle_mode == "none"


class FakeSession:
    class FakeDB:
        def close(self):
            pass
    def __enter__(self):
        return self.FakeDB()
    def __exit__(self, *args):
        pass


def test_single_auto_submit_function_uses_existing_service(monkeypatch):
    calls: list[dict] = []

    monkeypatch.setattr("app.core.database.SessionLocal", FakeSession)
    monkeypatch.setattr(routes, "_get_youtube_duration_seconds", lambda url, **kwargs: 600)
    monkeypatch.setattr(routes, "_effective_cookies_file", lambda value, db: "resolved_cookies.txt")
    monkeypatch.setattr(routes.PromptGenerator, "generate", lambda self, data: "prompt")
    monkeypatch.setattr(routes.batch_service, "start", lambda **kwargs: calls.append({"batch": kwargs}))

    def fake_start(task_id: str, prompt_text: str, render_payload: dict, user_data_dir: str | None = None,
                    headless: bool | None = None, thinking_mode: str = "extended",
                    model: str = "gemini-3.6-flash",
                    form_data: dict | None = None,
                    dry_run: bool = False):
        calls.append({"single": {"task_id": task_id, "prompt_text": prompt_text, "render_payload": render_payload, "dry_run": dry_run}})
        return None

    monkeypatch.setattr(routes.gemini_service, "start", fake_start)
    payload = GeminiAutoSubmitRequest(form_data={**FORM_DATA, "youtube_urls": [FORM_DATA["youtube_url"]], "source_mode": "single"}, render_options={}, subtitle_mode="burn")

    asyncio.run(routes.gemini_auto_submit(payload))

    assert len(calls) == 1
    assert "single" in calls[0]
    assert calls[0]["single"]["dry_run"] is False
    assert calls[0]["single"]["render_payload"]["ytdlp_cookies_file"] == "resolved_cookies.txt"


def test_batch_item_render_status_populated(monkeypatch):
    monkeypatch.setattr("app.services.batch_pipeline.PromptGenerator.generate", lambda self, data: "prompt")
    automation = FakeAutomationService()
    service = BatchPipelineService(
        automation,
        lambda job_id: {"status": "done", "progress": 100, "message": "Done", "result": {"final_video_path": "job-1"}},
        no_sleep,
    )

    async def run():
        batch = service.start(form_data=FORM_DATA, render_options={}, subtitle_mode="burn")
        await service._tasks[batch.batch_id]
        return batch

    batch = asyncio.run(run())

    assert batch.items[0].render_status is not None
    assert batch.items[0].render_status.get("status") == "done"
    assert batch.items[0].render_status.get("progress") == 100


def test_batch_item_render_status_progressive_updates(monkeypatch):
    monkeypatch.setattr("app.services.batch_pipeline.PromptGenerator.generate", lambda self, data: "prompt")
    automation = FakeAutomationService()
    calls: list[int] = []

    def render_status(job_id: str) -> dict:
        n = len(calls)
        calls.append(n)
        if n < 3:
            return {"status": "running", "progress": n * 30, "step": "step", "message": f"Step {n}"}
        return {"status": "done", "progress": 100, "message": "Done", "result": {"final_video_path": "job-1"}}

    async def fake_sleep(seconds: float) -> None:
        pass

    service = BatchPipelineService(automation, render_status, fake_sleep)

    async def run():
        batch = service.start(form_data=FORM_DATA, render_options={}, subtitle_mode="burn")
        await service._tasks[batch.batch_id]
        return batch

    batch = asyncio.run(run())

    assert len(calls) >= 4
    assert batch.items[0].render_status is not None
    assert batch.items[0].render_status.get("status") == "done"


def test_batch_propagates_ytdlp_cookies_from_browser(monkeypatch):
    monkeypatch.setattr("app.services.batch_pipeline.PromptGenerator.generate", lambda self, data: "prompt")
    automation = FakeAutomationService()
    service = BatchPipelineService(automation, lambda job_id: {"status": "done", "result": {"final_video_path": job_id}}, no_sleep)

    async def run():
        batch = service.start(
            form_data=FORM_DATA,
            render_options={},
            subtitle_mode="burn",
            ytdlp_cookies_from_browser="chrome",
        )
        await service._tasks[batch.batch_id]
        return batch

    batch = asyncio.run(run())
    assert automation.last_render_payload is not None
    assert automation.last_render_payload.get("ytdlp_cookies_from_browser") == "chrome"


def test_single_auto_submit_passes_auth_to_duration(monkeypatch):
    captured: dict = {}

    def capture_duration(url, **kwargs):
        captured.update(kwargs)
        return 600
    monkeypatch.setattr("app.core.database.SessionLocal", FakeSession)
    monkeypatch.setattr(routes, "_effective_cookies_file", lambda value, db: "resolved.txt")
    monkeypatch.setattr(routes, "_get_youtube_duration_seconds", capture_duration)
    monkeypatch.setattr(routes.PromptGenerator, "generate", lambda self, data: "prompt")
    monkeypatch.setattr(routes.gemini_service, "start", lambda *a, **kw: None)

    payload = GeminiAutoSubmitRequest(
        form_data={**FORM_DATA, "youtube_urls": [FORM_DATA["youtube_url"]], "source_mode": "single"},
        render_options={},
        subtitle_mode="burn",
        user_data_dir="E:/profile",
        ytdlp_cookies_from_browser="chrome",
    )
    asyncio.run(routes.gemini_auto_submit(payload))

    assert captured.get("cookies_file") == "resolved.txt"
    assert captured.get("cookies_from_browser") == "chrome"
    assert captured.get("user_data_dir") == "E:/profile"


def test_batch_auto_submit_passes_auth_to_duration(monkeypatch):
    captured: list[dict] = []

    def capture_duration(url, **kwargs):
        captured.append(kwargs)
        return 600

    monkeypatch.setattr("app.core.database.SessionLocal", FakeSession)
    monkeypatch.setattr(routes, "_effective_cookies_file", lambda value, db: "batch_resolved.txt")
    monkeypatch.setattr(routes, "_get_youtube_duration_seconds", capture_duration)
    monkeypatch.setattr(routes.PromptGenerator, "generate", lambda self, data: "prompt")
    monkeypatch.setattr(routes.batch_service, "start", lambda **kwargs: type("Batch", (), {"model_dump": lambda self: {"batch_id": "b1", "total_items": 2, "status": "pending", "items": []}})())

    payload = GeminiAutoSubmitRequest(
        form_data=FORM_DATA,
        render_options={},
        subtitle_mode="burn",
        user_data_dir="E:/batch_profile",
        ytdlp_cookies_from_browser="edge",
    )
    asyncio.run(routes.gemini_batch_auto_submit(payload))

    assert len(captured) == 2
    for kwargs in captured:
        assert kwargs.get("cookies_file") == "batch_resolved.txt"
        assert kwargs.get("cookies_from_browser") == "edge"
        assert kwargs.get("user_data_dir") == "E:/batch_profile"


def test_parse_cookies_from_browser_helper():
    assert routes._parse_cookies_from_browser("chrome:C:\\Profile") == ("chrome", "C:\\Profile", None, None)
    assert routes._parse_cookies_from_browser("chrome") == ("chrome", None, None, None)
    assert routes._parse_cookies_from_browser(None) is None
    assert routes._parse_cookies_from_browser("") is None
    assert routes._parse_cookies_from_browser("  ") is None
    assert routes._parse_cookies_from_browser("edge:C:\\Edge\\Profile") == ("edge", "C:\\Edge\\Profile", None, None)
    assert routes._parse_cookies_from_browser("firefox:/home/user/firefox") == ("firefox", "/home/user/firefox", None, None)


def test_ffprobe_direct_media_duration_supports_webm(monkeypatch):
    monkeypatch.setattr(
        routes.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"returncode": 0, "stdout": "1680.4\n"})(),
    )
    assert routes._ffprobe_direct_media_duration("https://example.test/Apollo11.webm") == 1680


def test_ffprobe_direct_media_duration_skips_web_pages(monkeypatch):
    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(routes.subprocess, "run", fake_run)
    assert routes._ffprobe_direct_media_duration("https://www.youtube.com/watch?v=abc") is None
    assert called is False


def test_resolve_duration_auth_falls_back_to_repo_profile(monkeypatch, tmp_path):
    """When user_data_dir=None and gemini_profile_path missing,
    _resolve_duration_auth falls back to ROOT_DIR/data/gemini_profile."""
    repo_root = tmp_path / "repo"
    repo_profile = repo_root / "data" / "gemini_profile"
    cookie = repo_profile / "Default" / "Network" / "Cookies"
    cookie.parent.mkdir(parents=True, exist_ok=True)
    cookie.write_bytes(b"")

    monkeypatch.setattr(routes, "ROOT_DIR", repo_root)
    monkeypatch.setattr(routes.settings, "gemini_profile_path", tmp_path / "nonexistent")
    monkeypatch.setattr(routes.settings, "ytdlp_cookies_from_browser", None)

    _, cookies_from_browser = routes._resolve_duration_auth(None, None, None)
    assert cookies_from_browser == f"chrome:{repo_profile}"
