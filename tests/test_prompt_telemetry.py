from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.schemas.prompt import PromptRunCreate
from app.services.prompt_telemetry import PromptRunService, _sanitize_form_data


@pytest.fixture()
def service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        yield PromptRunService(db)


def test_sanitize_form_data_excludes_sensitive_fields():
    raw = {"youtube_url": "https://youtube.com/watch?v=abc", "rewrite_style": "Điều tra", "youtube_urls": ["a"], "ytdlp_cookies_file": "/path/to/cookies", "tone": "Nghiêm túc"}
    result = _sanitize_form_data(raw)
    assert "youtube_url" not in result
    assert "youtube_urls" not in result
    assert "ytdlp_cookies_file" not in result
    assert result["rewrite_style"] == "Điều tra"
    assert result["tone"] == "Nghiêm túc"


def test_record_success_run(service):
    result = service.record_run(PromptRunCreate(
        prompt_text="This is a test prompt for verification",
        form_data={"rewrite_style": "Điều tra", "preset_name": "US COPS Documentary"},
        health_score=85,
        health_level="excellent",
        status="success",
        duration_ms=1234.5,
    ))
    assert result is not None
    assert result.status == "success"
    assert result.health_score == 85
    assert result.prompt_chars == 38
    assert result.prompt_hash is not None
    assert len(result.prompt_hash) == 64  # SHA256 hex
    assert result.preset_schema_version == 1
    assert result.error_message is None


def test_record_error_run(service):
    result = service.record_run(PromptRunCreate(
        prompt_text="",
        form_data={"rewrite_style": "Điều tra"},
        status="error",
        error_message="Generation failed",
        duration_ms=500.0,
    ))
    assert result is not None
    assert result.status == "error"
    assert result.error_message == "Generation failed"
    assert result.health_score is None
    assert result.prompt_chars is None  # empty string -> None


def test_telemetry_failure_does_not_crash(service):
    result = service.record_run(PromptRunCreate(
        prompt_text="x" * 100000,
        form_data={"key": "v" * 100000},
        status="success",
    ))
    assert result is not None


def test_prompt_text_not_stored_raw(service):
    result = service.record_run(PromptRunCreate(
        prompt_text="secret-prompt-content",
        form_data={},
        status="success",
    ))
    assert result is not None
    assert hasattr(result, "prompt_hash")
    assert hasattr(result, "prompt_chars")
    assert not hasattr(result, "prompt_text")


def test_stats_empty(service):
    stats = service.get_stats()
    assert stats.total_runs == 0
    assert stats.success_count == 0
    assert stats.error_count == 0
    assert stats.avg_health_score is None
    assert stats.top_presets == []
    assert stats.last_7d_count == 0


def test_stats_after_records(service):
    service.record_run(PromptRunCreate(prompt_text="a", form_data={"preset_name": "P1", "rewrite_style": "RS1"}, health_score=80, health_level="good", status="success"))
    service.record_run(PromptRunCreate(prompt_text="b", form_data={"preset_name": "P2", "rewrite_style": "RS1"}, health_score=90, health_level="excellent", status="success"))
    service.record_run(PromptRunCreate(prompt_text="c", form_data={"preset_name": "P1", "rewrite_style": "RS2"}, status="error", error_message="fail"))

    stats = service.get_stats()
    assert stats.total_runs == 3
    assert stats.success_count == 2
    assert stats.error_count == 1
    assert stats.avg_health_score is not None
    assert 85.0 <= stats.avg_health_score <= 85.1


def test_stats_top_presets(service):
    for i, name in enumerate(["P1", "P1", "P2", "P3", "P3", "P3"]):
        service.record_run(PromptRunCreate(prompt_text=f"p{i}", form_data={"preset_name": name, "rewrite_style": "RS"}, health_score=70, health_level="good", status="success"))

    stats = service.get_stats()
    assert len(stats.top_presets) == 3
    assert stats.top_presets[0]["name"] == "P3"
    assert stats.top_presets[0]["count"] == 3


def test_stats_avg_health(service):
    for score in [50, 60, 70]:
        service.record_run(PromptRunCreate(prompt_text="t", form_data={"preset_name": "P"}, health_score=score, health_level="good", status="success"))
    service.record_run(PromptRunCreate(prompt_text="t", form_data={"preset_name": "P"}, status="error"))

    stats = service.get_stats()
    assert stats.avg_health_score == 60.0


def test_stats_since_filter(service):
    service.record_run(PromptRunCreate(prompt_text="old", form_data={}, health_score=50, health_level="risky", status="success"))
    stats = service.get_stats(since=0)
    assert stats.total_runs >= 1


def test_stats_trend_last_7d_vs_prev_7d(service):
    stats = service.get_stats()
    assert isinstance(stats.last_7d_count, int)
    assert isinstance(stats.prev_7d_count, int)
