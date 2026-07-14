"""Tests for WebSocket + HTTP fallback for single-link auto pipeline.

Demonstrates why single-link (WebSocket) can show UI error while multi-link
(batch, HTTP polling) never has the issue.
"""

from __future__ import annotations

import pathlib

import pytest
from starlette.testclient import TestClient

from app.main import create_app
from app.services.batch_pipeline import BatchPipelineService
from app.services.gemini_automation import GeminiAutomationTask, gemini_service


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_tasks():
    yield
    gemini_service._tasks.clear()


class TestHttpStatusEndpoint:
    """HTTP GET /api/gemini/status/{task_id} — the fallback mechanism."""

    def test_returns_404_for_unknown_task(self, client):
        resp = client.get("/api/gemini/status/nonexistent")
        assert resp.status_code == 404

    def test_returns_latest_task_state(self, client):
        task = GeminiAutomationTask("test-http")
        gemini_service._tasks["test-http"] = task

        resp = client.get("/api/gemini/status/test-http")
        assert resp.status_code == 200
        data = resp.json()
        assert data["step"] == "init"
        assert data["status"] == "running"
        assert data["task_id"] == "test-http"

        task.update("init_browser", "Browser starting...")

        resp = client.get("/api/gemini/status/test-http")
        data = resp.json()
        assert data["step"] == "init_browser"
        assert data["status"] == "running"

        task.mark_done({"job_id": "job-1"})

        resp = client.get("/api/gemini/status/test-http")
        data = resp.json()
        assert data["status"] == "done"
        assert data["step"] == "complete"
        assert data["result"]["job_id"] == "job-1"


class TestWebSocketAndHttpFallback:
    """WebSocket delivers states; HTTP fallback works when WS is gone."""

    def test_ws_delivers_init_state_and_http_matches(self, client):
        """Single-link: WS delivers init state, HTTP GET returns same data."""
        task = GeminiAutomationTask("test-ws")
        gemini_service._tasks["test-ws"] = task

        resp = client.get("/api/gemini/status/test-ws")
        http_state = resp.json()

        with client.websocket_connect("/api/gemini/status/test-ws") as ws:
            ws_state = ws.receive_json()

        assert ws_state["step"] == http_state["step"] == "init"
        assert ws_state["status"] == http_state["status"] == "running"
        assert ws_state["task_id"] == http_state["task_id"] == "test-ws"

    def test_ws_drop_then_http_polling_still_works(self, client):
        """Core fix: after WS closes, HTTP GET returns latest state for polling.

        This simulates the frontend 'WebSocket connection closed unexpectedly'
        scenario — the WS connection drops, but the backend task continues
        running and HTTP fallback polling (fetchAutoPipelineStatus) catches up.
        """
        task = GeminiAutomationTask("test-drop")
        gemini_service._tasks["test-drop"] = task

        # 1) WS connects, receives init state
        with client.websocket_connect("/api/gemini/status/test-drop") as ws:
            ws.receive_json()  # init state received

        # 2) WS is now dropped (closed by test client)

        # 3) Pipeline continues running (no WS to send updates)
        task.update("init_browser", "Browser starting...")
        task.update("navigate_gemini", "Navigating Gemini...")

        # 4) HTTP GET returns latest state — what the frontend fallback polls
        resp = client.get("/api/gemini/status/test-drop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["step"] == "navigate_gemini"
        assert data["status"] == "running"

        # 5) Pipeline finishes
        task.mark_done({"job_id": "job-drop"})

        resp = client.get("/api/gemini/status/test-drop")
        data = resp.json()
        assert data["status"] == "done"
        assert data["result"]["job_id"] == "job-drop"

    def test_ws_error_then_http_polling_still_works(self, client):
        """Similar to drop but pipeline ends with error — HTTP polls final
        error state correctly."""
        task = GeminiAutomationTask("test-err")
        gemini_service._tasks["test-err"] = task

        with client.websocket_connect("/api/gemini/status/test-err") as ws:
            ws.receive_json()  # init

        # WS dropped, pipeline errors
        task.update("submitting_prompt", "Sending...")
        task.mark_error("Gemini timeout", _cancel_render_fn=None)

        resp = client.get("/api/gemini/status/test-err")
        data = resp.json()
        assert data["status"] == "error"
        assert "Gemini timeout" in (data.get("error") or data.get("message", ""))


class TestBatchVsSingleComparison:
    """Why batch (multi-link) never has the WebSocket issue."""

    def test_batch_polls_in_process_no_websocket(self):
        """Batch _run_item reads task.states directly via wait_for_update
        — no external connection that can drop."""
        task = GeminiAutomationTask("batch-item")
        task.update("init_browser", "Browser...")
        task.update("navigate_gemini", "Navigating...")
        task.update("submitting_prompt", "Submitting...")
        task.mark_done({"job_id": "batch-job"})

        # _run_item does: item.states = list(task.states); task.wait_for_update()
        states = list(task.states)
        assert len(states) >= 4
        assert states[-1]["step"] == "submitting_prompt"
        assert states[-1]["status"] == "done"

    def test_single_link_uses_http_polling_like_multi_link(self):
        """Source assertion: 1-link uses pollAutoPipelineStatus (HTTP polling)
        matching multi-link's pollBatchProgress pattern. No WebSocket dependency."""
        app_tsx = pathlib.Path("frontend/src/App.tsx").read_text(encoding="utf-8")

        assert "pollAutoPipelineStatus" in app_tsx, "Single-link must use HTTP polling"
        assert "pollBatchProgress" in app_tsx, "Multi-link must use HTTP poll"
        assert "startBatchAutoPipeline" in app_tsx, "Multi-link uses batch API"

    def test_single_link_path_uses_polling_not_websocket(self):
        """Single-link path calls pollAutoPipelineStatus (HTTP polling),
        not connectAutoPipelineWS (WebSocket)."""
        app_tsx = pathlib.Path("frontend/src/App.tsx").read_text(encoding="utf-8")

        assert "pollAutoPipelineStatus(res.task_id)" in app_tsx
        assert "connectAutoPipelineWS(" not in app_tsx

    def test_fetch_auto_pipeline_status_exists(self):
        """fetchAutoPipelineStatus must be defined in api.ts."""
        api_ts = pathlib.Path("frontend/src/api.ts").read_text(encoding="utf-8")

        assert "fetchAutoPipelineStatus" in api_ts
        assert "gemini/status" in api_ts
        assert "API_BASE" in api_ts

    def test_connect_auto_pipeline_ws_has_http_fallback(self):
        """connectAutoPipelineWS (infrastructure) must contain HTTP polling fallback."""
        api_ts = pathlib.Path("frontend/src/api.ts").read_text(encoding="utf-8")

        assert "fetchAutoPipelineStatus" in api_ts
        assert "pollInterval" in api_ts
        assert "onclose" in api_ts

        # Must NOT immediately call onError on close
        assert "startHttpPolling" in api_ts or "onError" not in api_ts.split("ws.onclose")[0].split("onclose")[-1] if "onclose" in api_ts else True

    def test_poll_auto_pipeline_status_function_exists(self):
        """pollAutoPipelineStatus must be defined in App.tsx."""
        app_tsx = pathlib.Path("frontend/src/App.tsx").read_text(encoding="utf-8")

        assert "async function pollAutoPipelineStatus" in app_tsx
        assert "fetchAutoPipelineStatus(taskId)" in app_tsx
        assert "autoRenderPollCancelledRef.current = false" in app_tsx
