import asyncio

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

    def start(self, task_id: str, prompt_text: str, render_payload: dict, user_data_dir: str | None = None):
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


def test_single_auto_submit_function_uses_existing_service(monkeypatch):
    calls: list[dict] = []

    monkeypatch.setattr(routes.PromptGenerator, "generate", lambda self, data: "prompt")
    monkeypatch.setattr(routes.batch_service, "start", lambda **kwargs: calls.append({"batch": kwargs}))

    def fake_start(task_id: str, prompt_text: str, render_payload: dict, user_data_dir: str | None = None):
        calls.append({"single": {"task_id": task_id, "prompt_text": prompt_text, "render_payload": render_payload}})
        return None

    monkeypatch.setattr(routes.gemini_service, "start", fake_start)
    payload = GeminiAutoSubmitRequest(form_data={**FORM_DATA, "youtube_urls": [FORM_DATA["youtube_url"]], "source_mode": "single"}, render_options={}, subtitle_mode="burn")

    asyncio.run(routes.gemini_auto_submit(payload))

    assert len(calls) == 1
    assert "single" in calls[0]
