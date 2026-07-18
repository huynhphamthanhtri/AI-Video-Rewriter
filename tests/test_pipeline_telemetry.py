import asyncio
from unittest.mock import AsyncMock

from app.services.gemini_automation import GeminiAutomationService, GeminiAutomationTask
from app.services.pipeline_telemetry import PipelineTelemetry


def test_pipeline_telemetry_summarizes_passes(monkeypatch):
    perf_values = iter([12.5, 15.0])
    monkeypatch.setattr("app.services.pipeline_telemetry.time.perf_counter", lambda: next(perf_values))
    telemetry = PipelineTelemetry(started_at=100.0)
    telemetry.record_gemini_pass(name="timeline", attempt=1, prompt_text="abcd",
                                 response_text="{}", started_at=10.0, valid=False,
                                 errors=["missing chapters"])
    telemetry.record_gemini_pass(name="timeline", attempt=2, prompt_text="abcdef",
                                 response_text='{"ok":true}', started_at=12.0, valid=True)
    snapshot = telemetry.snapshot()
    assert snapshot["gemini_pass_count"] == 2
    assert snapshot["gemini_retry_count"] == 1
    assert snapshot["prompt_chars_total"] == 10
    assert snapshot["response_chars_total"] == 13
    assert snapshot["gemini_seconds_total"] == 5.5
    assert snapshot["gemini_passes"][0]["error_count"] == 1


def test_pipeline_telemetry_does_not_store_content():
    telemetry = PipelineTelemetry()
    telemetry.record_gemini_pass(name="chapter_1", attempt=1, prompt_text="secret prompt",
                                 response_text="secret response", started_at=0.0, valid=True)
    serialized = str(telemetry.snapshot())
    assert "secret prompt" not in serialized
    assert "secret response" not in serialized


def test_dry_run_counts_dict_payload_items(monkeypatch):
    service = GeminiAutomationService()
    task = GeminiAutomationTask("dry-run-counts")
    payload = {
        "srt": [{"index": 1}, {"index": 2}],
        "video_segments": [{"start": 0}, {"start": 1}, {"start": 2}],
    }
    monkeypatch.setattr(
        service,
        "_validate_json_for_render",
        AsyncMock(return_value=(True, [], payload)),
    )
    monkeypatch.setattr(service, "_save_json_debug", AsyncMock())

    asyncio.run(service._validate_without_render(task, "{}", {}))

    assert task.status == "done"
    assert task.result["srt_count"] == 2
    assert task.result["video_segment_count"] == 3
