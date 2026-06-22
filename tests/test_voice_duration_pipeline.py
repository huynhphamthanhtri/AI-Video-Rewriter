import pytest

from app.schemas.render import GeminiPayloadSchema, RenderOptions, clip_timestamp_to_seconds
from app.services.segment_planner import SegmentPlanner
from app.services.video_tools import _apply_segment_plan_to_payload, _segment_plan_to_dict


def _payload_two_segments() -> GeminiPayloadSchema:
    return GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "A", "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút"},
        "sources": [{"source_id": "source_1", "local_video_path": "E:/AUTO_REVIEW/test.mp4"}],
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [
            {"index": 1, "start": "00:00:00,000", "end": "00:00:04,000", "text": "Câu một"},
            {"index": 2, "start": "00:00:04,000", "end": "00:00:08,000", "text": "Câu hai"},
        ],
        "video_segments": [
            {"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:04.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95},
            {"segment_id": 2, "order": 2, "source_id": "source_1", "source_start": "00:00:04.000", "source_end": "00:00:08.000", "subtitle_start": 2, "subtitle_end": 2, "scene_description": "Tiếp theo", "importance_score": 80},
        ],
    })


def _plan_and_apply(payload: GeminiPayloadSchema, natural_durations: dict[int, float], source_duration: float):
    options = RenderOptions(tts_mode="voiceover", tts_fit_policy="hybrid", tts_max_speed=1.5)
    planner = SegmentPlanner()
    plans = planner.plan(payload, options, natural_durations, {"source_1": source_duration})
    shifts = planner.compute_srt_shifts(plans, payload)
    _apply_segment_plan_to_payload(payload, plans, shifts)
    return plans


def test_hybrid_small_overflow_uses_light_speedup_without_payload_extension():
    payload = _payload_two_segments()
    plans = _plan_and_apply(payload, {1: 4.3, 2: 4.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "light_speedup"
    assert plan.speed_factor == pytest.approx(1.075)
    assert plan.extend_seconds == 0
    assert payload.video_segments[0].source_end == "00:00:04.000"
    assert payload.video_segments[0].freeze_frame_duration is None
    assert payload.srt[0].end == "00:00:04,000"
    assert payload.srt[1].start == "00:00:04,000"


def test_hybrid_large_overflow_uses_footage_extend_and_shifts_subsequent_cues():
    payload = _payload_two_segments()
    plans = _plan_and_apply(payload, {1: 5.0, 2: 4.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "footage_extend"
    assert plan.speed_factor == 1.0
    assert plan.extend_seconds == pytest.approx(1.0)
    assert payload.video_segments[0].source_end == "00:00:05.000"
    assert payload.video_segments[0].freeze_frame_duration is None
    assert payload.srt[0].end == "00:00:05,000"
    assert payload.srt[1].start == "00:00:05,000"
    assert payload.srt[1].end == "00:00:09,000"


def test_hybrid_large_overflow_with_exhausted_source_uses_freeze_without_source_end_extension():
    payload = _payload_two_segments()
    plans = _plan_and_apply(payload, {1: 6.0, 2: 4.0}, source_duration=4.0)

    plan = plans[0]
    segment = payload.video_segments[0]
    final_duration = clip_timestamp_to_seconds(segment.source_end) - clip_timestamp_to_seconds(segment.source_start) + (segment.freeze_frame_duration or 0.0)

    assert plan.decision == "freeze_frame"
    assert plan.speed_factor == 1.0
    assert plan.extend_seconds == pytest.approx(2.0)
    assert payload.video_segments[0].source_end == "00:00:04.000"
    assert payload.video_segments[0].freeze_frame_duration == pytest.approx(2.0)
    assert final_duration == pytest.approx(6.0)
    assert final_duration != pytest.approx(8.0)
    assert payload.srt[0].end == "00:00:06,000"
    assert payload.srt[1].start == "00:00:06,000"
    assert payload.srt[1].end == "00:00:10,000"


def test_segment_plan_serialization_has_explicit_duration_fields():
    payload = _payload_two_segments()
    plans = _plan_and_apply(payload, {1: 5.0, 2: 4.0}, source_duration=20.0)

    data = _segment_plan_to_dict(plans[0])

    assert data["original_scene_duration"] == pytest.approx(4.0)
    assert data["final_scene_duration"] == pytest.approx(5.0)
    assert data["natural_voice_duration"] == pytest.approx(5.0)
    assert data["extend_seconds"] == pytest.approx(1.0)
    assert data["decision"] == "footage_extend"
    assert data["speed_factor"] == 1.0
    assert data["freeze_duration"] is None
    assert data["warning"] == ""
    assert "scene_duration" not in data
    assert "required_duration" not in data
