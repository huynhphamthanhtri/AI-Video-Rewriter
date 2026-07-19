from __future__ import annotations

import pytest

from app.schemas.render import clip_timestamp_to_seconds
from app.services.json_validator import AUTO_FIX_DURATION_TOLERANCE_SECONDS, JsonValidator


@pytest.fixture
def validator() -> JsonValidator:
    return JsonValidator()


@pytest.fixture
def payload_temp():
    import copy
    return copy.deepcopy({
        "metadata": {"video_title": "Test", "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút"},
        "sources": [{"source_id": "source_1"}],
        "rewrite_script": {"full_text": "Test"},
        "srt": [
            {"index": 1, "start": "00:00:00,000", "end": "00:00:04,000", "text": "Câu một"},
        ],
        "video_segments": [
            {"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:04.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Test"},
        ],
    })


def test_auto_fix_leaves_matching_duration_unchanged(validator, payload_temp):
    """SRT 4.0s, source 4.0s → source_end unchanged."""
    result = validator.auto_fix_duration_mismatch(payload_temp)
    assert result["video_segments"][0]["source_end"] == "00:00:04.000"


def test_auto_fix_leaves_tiny_delta_unchanged(validator, payload_temp):
    """SRT 4.0s, source 4.1s → unchanged because delta <= tolerance."""
    payload_temp["video_segments"][0]["source_end"] = "00:00:04.100"
    result = validator.auto_fix_duration_mismatch(payload_temp)
    assert result["video_segments"][0]["source_end"] == "00:00:04.100"


def test_auto_fix_extends_when_video_too_short(validator, payload_temp):
    """SRT 4.0s, source 2.0s → extend to 4.0s."""
    payload_temp["video_segments"][0]["source_end"] = "00:00:02.000"
    result = validator.auto_fix_duration_mismatch(payload_temp)
    new_end = clip_timestamp_to_seconds(result["video_segments"][0]["source_end"])
    assert abs(new_end - 4.0) < 0.01


def test_auto_fix_trims_when_video_too_long(validator, payload_temp):
    """SRT 4.0s, source 10.0s → trim to 4.0s."""
    payload_temp["video_segments"][0]["source_end"] = "00:00:10.000"
    result = validator.auto_fix_duration_mismatch(payload_temp)
    new_end = clip_timestamp_to_seconds(result["video_segments"][0]["source_end"])
    assert abs(new_end - 4.0) < 0.01


def test_auto_fix_keeps_source_start_anchor(validator, payload_temp):
    """source_start stays fixed after auto-fix."""
    payload_temp["video_segments"][0]["source_start"] = "00:01:00.000"
    payload_temp["video_segments"][0]["source_end"] = "00:01:10.000"
    result = validator.auto_fix_duration_mismatch(payload_temp)
    seg = result["video_segments"][0]
    assert seg["source_start"] == "00:01:00.000"
    new_end = clip_timestamp_to_seconds(seg["source_end"])
    assert abs(new_end - 64.0) < 0.01


def test_validate_with_auto_fix_passes_after_duration_sync(validator, payload_temp):
    """Payload with 2s→4s mismatch passes after auto-fix."""
    payload_temp["video_segments"][0]["source_end"] = "00:00:02.000"
    valid, errors, model, fixed = validator.validate_with_auto_fix(payload_temp)
    assert valid is True
    assert model is not None


def test_trim_only_skips_large_voiceover_extension(validator, payload_temp):
    """trim_only=True, source 1s, SRT 10s → unchanged."""
    payload_temp["srt"][0]["end"] = "00:00:10,000"
    payload_temp["video_segments"][0]["source_start"] = "00:00:00.000"
    payload_temp["video_segments"][0]["source_end"] = "00:00:01.000"
    result = validator.auto_fix_duration_mismatch(payload_temp, trim_only=True)
    assert result["video_segments"][0]["source_end"] == "00:00:01.000"


def test_trim_only_still_trims_dead_air(validator, payload_temp):
    """trim_only=True, source 10s, SRT 4s → still trims."""
    payload_temp["video_segments"][0]["source_end"] = "00:00:10.000"
    result = validator.auto_fix_duration_mismatch(payload_temp, trim_only=True)
    new_end = clip_timestamp_to_seconds(result["video_segments"][0]["source_end"])
    assert abs(new_end - 4.0) < 0.01
