import math

import pytest

from app.schemas.render import GeminiPayloadSchema, RenderOptions, clip_timestamp_to_seconds, srt_timestamp_to_seconds
from app.services.segment_planner import SegmentPlanner, SAFE_VIDEO_MIN_SOFT, SAFE_VIDEO_MAX_SOFT, DEAD_AIR_HARD_TRIM_THRESHOLD, DEAD_AIR_TARGET_PADDING
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


def _payload_three_cues() -> GeminiPayloadSchema:
    """Three cues across two segments (2 cues in seg1, 1 in seg2)."""
    return GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "A", "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút"},
        "sources": [{"source_id": "source_1", "local_video_path": "E:/AUTO_REVIEW/test.mp4"}],
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [
            {"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Câu một"},
            {"index": 2, "start": "00:00:03,000", "end": "00:00:06,000", "text": "Câu hai"},
            {"index": 3, "start": "00:00:06,000", "end": "00:00:10,000", "text": "Câu ba"},
        ],
        "video_segments": [
            {"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:06.000", "subtitle_start": 1, "subtitle_end": 2, "scene_description": "Mở đầu", "importance_score": 95},
            {"segment_id": 2, "order": 2, "source_id": "source_1", "source_start": "00:00:06.000", "source_end": "00:00:10.000", "subtitle_start": 3, "subtitle_end": 3, "scene_description": "Kết", "importance_score": 80},
        ],
    })


def _plan_and_apply(payload: GeminiPayloadSchema, natural_durations: dict[int, float], source_duration: float):
    options = RenderOptions(tts_mode="voiceover", tts_fit_policy="hybrid", tts_max_speed=1.5)
    planner = SegmentPlanner()
    plans = planner.plan(payload, options, natural_durations, {"source_1": source_duration})
    shifts = planner.compute_srt_shifts(plans, payload)
    _apply_segment_plan_to_payload(payload, plans, shifts)
    return plans


def test_hybrid_small_overflow_now_uses_sync_speed_balance():
    """Previously footage_extend for voice 4.3/scene 4. Now handled by sync_speed_balance."""
    payload = _payload_two_segments()
    plans = _plan_and_apply(payload, {1: 4.3, 2: 4.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "sync_speed_balance"
    assert plan.video_speed_factor < 1.0  # slowdown
    assert plan.speed_factor > 1.0  # voice speedup
    assert plan.extend_seconds == 0.0
    # SRT cues stretched (video slower → cues longer)
    internal_scale = 1.0 / plan.video_speed_factor
    expected_cue1_end = srt_timestamp_to_seconds(payload.srt[0].end)
    assert expected_cue1_end == pytest.approx(4.0 * internal_scale, rel=1e-3)
    expected_cue2_start = srt_timestamp_to_seconds(payload.srt[1].start)
    assert expected_cue2_start == pytest.approx(4.0 * internal_scale, rel=1e-3)


def test_hybrid_large_overflow_now_uses_sync_speed_balance():
    """Previously footage_extend for voice 5.0/scene 4. Now sync_speed_balance (video cap)."""
    payload = _payload_two_segments()
    plans = _plan_and_apply(payload, {1: 5.0, 2: 4.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "sync_speed_balance"
    assert plan.video_speed_factor == SAFE_VIDEO_MIN_SOFT  # capped
    assert plan.extend_seconds == 0.0
    # Eff scene = 4 / 0.92 = 4.348
    internal_scale = 1.0 / SAFE_VIDEO_MIN_SOFT
    expected_cue1_end = srt_timestamp_to_seconds(payload.srt[0].end)
    assert expected_cue1_end == pytest.approx(4.0 * internal_scale, rel=1e-3)
    expected_cue2_start = srt_timestamp_to_seconds(payload.srt[1].start)
    assert expected_cue2_start == pytest.approx(4.0 * internal_scale, rel=1e-3)


def test_hybrid_large_overflow_with_exhausted_source_now_uses_sync_speed_balance():
    """Previously freeze_frame for voice 6.0/scene 4. Now fits within 1.5 max speed."""
    payload = _payload_two_segments()
    plans = _plan_and_apply(payload, {1: 6.0, 2: 4.0}, source_duration=4.0)

    plan = plans[0]
    assert plan.decision == "sync_speed_balance"
    assert plan.video_speed_factor == SAFE_VIDEO_MIN_SOFT
    expected_voice = (6.0 / 4.0) * SAFE_VIDEO_MIN_SOFT  # 1.38
    assert plan.speed_factor == pytest.approx(expected_voice, rel=1e-3)
    assert plan.extend_seconds == 0.0
    assert payload.video_segments[0].freeze_frame_duration is None
    # Eff scene = 4 / 0.92 = 4.348
    internal_scale = 1.0 / SAFE_VIDEO_MIN_SOFT
    expected_cue1_end = srt_timestamp_to_seconds(payload.srt[0].end)
    assert expected_cue1_end == pytest.approx(4.0 * internal_scale, rel=1e-3)


def test_segment_plan_serialization_has_explicit_duration_fields():
    payload = _payload_two_segments()
    plans = _plan_and_apply(payload, {1: 5.0, 2: 4.0}, source_duration=20.0)

    data = _segment_plan_to_dict(plans[0])

    # Now uses sync_speed_balance: video_speed=0.92, eff_scene=4/0.92=4.348
    assert data["original_scene_duration"] == pytest.approx(4.0)
    assert data["final_scene_duration"] == pytest.approx(4.0 / SAFE_VIDEO_MIN_SOFT, rel=1e-3)
    assert data["natural_voice_duration"] == pytest.approx(5.0)
    assert data["extend_seconds"] == 0.0
    assert data["decision"] == "sync_speed_balance"
    assert data["speed_factor"] == pytest.approx(1.25 * SAFE_VIDEO_MIN_SOFT, rel=1e-3)
    assert data["video_speed_factor"] == SAFE_VIDEO_MIN_SOFT
    assert data["freeze_duration"] is None
    assert "VOICE_SPEED_LIMIT" in data["warning"]
    assert data["warning"] != ""
    assert "scene_duration" not in data
    assert "required_duration" not in data


def test_sync_speed_balance_small_overflow():
    """Voice slightly longer than scene → balanced video slowdown + voice speedup."""
    payload = _payload_two_segments()
    # Voice 4.3s in 4s scene: diff=0.3 > tolerance=0.25 → proceed
    # ratio=1.075, ideal_video=1/sqrt(1.075)=0.965, voice=sqrt(1.075)=1.037
    # Both within caps → exact balanced fit
    plans = _plan_and_apply(payload, {1: 4.3, 2: 4.0}, source_duration=20.0)

    plan = plans[0]
    ratio = 4.3 / 4.0  # 1.075
    ideal_video = 1.0 / math.sqrt(ratio)  # ~0.965
    ideal_voice = math.sqrt(ratio)  # ~1.037
    assert plan.decision == "sync_speed_balance"
    assert plan.video_speed_factor == pytest.approx(ideal_video, rel=1e-3)
    assert plan.speed_factor == pytest.approx(ideal_voice, rel=1e-3)
    assert plan.extend_seconds == 0.0
    assert plan.duration_delta_seconds == pytest.approx(4 / ideal_video - 4, rel=1e-3)

    # SRT cues should be stretched by internal_scale = 1/video_speed (video slows down → cues longer)
    internal_scale = 1.0 / ideal_video
    expected_cue1_end = srt_timestamp_to_seconds(payload.srt[0].end)
    assert expected_cue1_end == pytest.approx(4 * internal_scale, rel=1e-3)

    # Second segment should be shifted by delta
    expected_cue2_start = srt_timestamp_to_seconds(payload.srt[1].start)
    assert expected_cue2_start == pytest.approx(4 + plan.duration_delta_seconds, rel=1e-3)


def test_sync_speed_balance_hits_video_min_cap():
    """Video slowdown capped at SAFE_VIDEO_MIN_SOFT, voice compensates."""
    payload = _payload_two_segments()
    # Scene=4s, Voice=5.0s → ratio=1.25
    # ideal_video=1/sqrt(1.25)=0.894 < 0.92 → capped at SAFE_VIDEO_MIN_SOFT
    # voice_speed = 1.25 * 0.92 = 1.15 ≤ 1.5 → fits
    plans = _plan_and_apply(payload, {1: 5.0, 2: 4.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "sync_speed_balance"
    assert plan.video_speed_factor == pytest.approx(SAFE_VIDEO_MIN_SOFT, rel=1e-3)
    expected_voice = 1.25 * SAFE_VIDEO_MIN_SOFT  # 1.15
    assert plan.speed_factor == pytest.approx(expected_voice, rel=1e-3)
    assert plan.extend_seconds == 0.0


def test_balanced_too_large_overflow_falls_back_to_footage_extend():
    """Voice too long for balanced approach → fallback footage_extend, no video speed."""
    payload = _payload_two_segments()
    # Scene=4s, Voice=7s → ratio=1.75
    # ideal_video=0.756 < 0.92 → video_speed=0.92
    # voice_speed=1.75*0.92=1.61 > max_speed(1.5) → fallback
    plans = _plan_and_apply(payload, {1: 7.0, 2: 4.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "footage_extend"
    assert plan.video_speed_factor == 1.0  # no video speed in fallback
    assert plan.extend_seconds == pytest.approx(3.0)  # original overflow (7-4)


def test_sync_video_trim_speedup_small_underflow():
    """Voice slightly shorter than scene → video speed-up to match."""
    payload = _payload_two_segments()
    # Scene=4s, Voice=3.7s → diff=-0.3 < -tolerance(0.25) → proceed
    # underflow ratio=4/3.7=1.081 ≤ 1.10 → triggers trim
    plans = _plan_and_apply(payload, {1: 3.7, 2: 4.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "sync_video_trim_speedup"
    expected_speed = 4 / 3.7  # ~1.081
    assert plan.video_speed_factor == pytest.approx(expected_speed, rel=1e-3)
    assert plan.speed_factor == 1.0
    assert plan.extend_seconds == 0.0
    # Duration delta should be negative (shorter final duration)
    expected_delta = 4 / expected_speed - 4  # negative
    assert plan.duration_delta_seconds == pytest.approx(expected_delta, rel=1e-3)

    # SRT cue1 should be compressed: 4s / expected_speed → 3.7s (matches voice)
    expected_cue1_end = srt_timestamp_to_seconds(payload.srt[0].end)
    assert expected_cue1_end == pytest.approx(3.7, rel=1e-3)


def test_sync_video_trim_speedup_capped_large_underflow():
    """Voice much shorter than scene → capped speedup to reduce dead air."""
    payload = _payload_two_segments()
    # Scene=4s, Voice=3.0s → underflow ratio=1.333 > SAFE_VIDEO_MAX_SOFT → capped speed
    plans = _plan_and_apply(payload, {1: 3.0, 2: 4.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "sync_video_trim_speedup_capped"
    assert plan.video_speed_factor == SAFE_VIDEO_MAX_SOFT
    assert plan.speed_factor == 1.0
    expected_delta = 4 / SAFE_VIDEO_MAX_SOFT - 4
    assert plan.duration_delta_seconds == pytest.approx(expected_delta, rel=1e-3)
    assert "dead air reduced" in plan.warning
    residual = (4 / SAFE_VIDEO_MAX_SOFT) - 3.0
    if residual >= 0.5:
        assert "CAP_REACHED_STILL_MISMATCH" in plan.warning

    # SRT cue1 should be compressed: 4s / SAFE_VIDEO_MAX_SOFT
    expected_cue1_end = srt_timestamp_to_seconds(payload.srt[0].end)
    assert expected_cue1_end == pytest.approx(4 / SAFE_VIDEO_MAX_SOFT, rel=1e-3)


def test_srt_local_scaling_with_multiple_cues_in_segment():
    """Multi-cue segment with video slowdown → all internal cues stretched proportionally."""
    payload = _payload_three_cues()
    # Segment 1: scene=6s (0-6), two cues (0-3, 3-6)
    # Cue1=3.2s, Cue2=3.3s → total=6.5s, diff=0.5 > tolerance=0.30
    # ratio=6.5/6=1.083, ideal_video=1/sqrt(1.083)=0.961, voice=sqrt(1.083)=1.041
    # Both within caps → sync_speed_balance
    plans = _plan_and_apply(payload, {1: 3.2, 2: 3.3, 3: 4.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "sync_speed_balance"
    v_speed = plan.video_speed_factor
    assert v_speed < 1.0  # slowdown

    # Internal scale = 1/video_speed > 1 (cues are stretched)
    internal_scale = 1.0 / v_speed
    # Cue 1: original 0-3 → stretched to 0 to 3*internal_scale
    cue1_start = srt_timestamp_to_seconds(payload.srt[0].start)
    cue1_end = srt_timestamp_to_seconds(payload.srt[0].end)
    assert cue1_start == pytest.approx(0.0, abs=0.01)
    assert cue1_end == pytest.approx(3.0 * internal_scale, rel=1e-3)

    # Cue 2: original 3-6 → stretched to (3*internal_scale) to (6*internal_scale)
    cue2_start = srt_timestamp_to_seconds(payload.srt[1].start)
    cue2_end = srt_timestamp_to_seconds(payload.srt[1].end)
    assert cue2_start == pytest.approx(3.0 * internal_scale, rel=1e-3)
    assert cue2_end == pytest.approx(6.0 * internal_scale, rel=1e-3)

    # Cue 3 (segment 2, unchanged) should be shifted by segment 1 delta
    cue3_start = srt_timestamp_to_seconds(payload.srt[2].start)
    expected_delta = plan.duration_delta_seconds
    assert cue3_start == pytest.approx(6.0 + expected_delta, rel=1e-3)


def test_sync_speed_balance_preserves_no_change_for_exact_fit():
    """Voice exactly matching scene duration → no_change within tolerance."""
    payload = _payload_two_segments()
    # 4.0 voice in 4.0 scene → diff=0 ≤ tolerance (0.25)
    plans = _plan_and_apply(payload, {1: 4.0, 2: 4.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "no_change"
    assert plan.video_speed_factor == 1.0
    assert plan.speed_factor == 1.0
    # No diagnostic warning for exact match
    assert plan.warning == ""

    # SRT should be untouched
    assert srt_timestamp_to_seconds(payload.srt[0].start) == 0.0
    assert srt_timestamp_to_seconds(payload.srt[0].end) == 4.0
    assert srt_timestamp_to_seconds(payload.srt[1].start) == 4.0
    assert srt_timestamp_to_seconds(payload.srt[1].end) == 8.0


def _payload_long_scene() -> GeminiPayloadSchema:
    """Single segment with 10s scene and 10s SRT slot. Used for severe dead air testing."""
    return GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "A", "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút"},
        "sources": [{"source_id": "source_1", "local_video_path": "E:/AUTO_REVIEW/test.mp4"}],
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [
            {"index": 1, "start": "00:00:00,000", "end": "00:00:10,000", "text": "Câu một dài hơn"},
        ],
        "video_segments": [
            {"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:10.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95},
        ],
    })


def test_sync_video_hard_trim_with_severe_underflow():
    """Large underflow (scene 10s, voice 4s) => hard trim to voice+DEAD_AIR_TARGET_PADDING."""
    payload = _payload_long_scene()
    # Scene=10, Voice=4: speedup_dur=10/1.15=8.696, residual=4.696 >= 1.5 => hard trim
    # required_duration=4+0.75=4.75
    plans = _plan_and_apply(payload, {1: 4.0}, source_duration=20.0)
    plan = plans[0]
    assert plan.decision == "sync_video_hard_trim"
    assert plan.video_speed_factor == SAFE_VIDEO_MAX_SOFT
    assert plan.speed_factor == 1.0
    expected_duration = 4.0 + DEAD_AIR_TARGET_PADDING
    assert plan.required_duration == pytest.approx(expected_duration, rel=1e-3)
    assert plan.duration_delta_seconds == pytest.approx(expected_duration - 10.0, rel=1e-3)
    assert "HARD_TRIM_DEAD_AIR" in plan.warning
    assert "SEVERE_DEAD_AIR" not in plan.warning
    assert "CAP_REACHED_STILL_MISMATCH" not in plan.warning


def test_hard_trim_compresses_single_cue_to_required_duration():
    """Hard-trimmed segment: single cue end must equal required_duration, not orig_dur."""
    payload = _payload_long_scene()  # scene=10, one cue: 0-10
    plans = _plan_and_apply(payload, {1: 4.0}, source_duration=20.0)
    plan = plans[0]
    assert plan.decision == "sync_video_hard_trim"
    expected_dur = 4.0 + DEAD_AIR_TARGET_PADDING  # 4.75
    assert plan.required_duration == pytest.approx(expected_dur, rel=1e-3)
    cue_end = srt_timestamp_to_seconds(payload.srt[0].end)
    assert cue_end == pytest.approx(expected_dur, rel=1e-3)


def _payload_hard_trim_two_segments() -> GeminiPayloadSchema:
    return GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "A", "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút"},
        "sources": [{"source_id": "source_1", "local_video_path": "E:/AUTO_REVIEW/test.mp4"}],
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [
            {"index": 1, "start": "00:00:00,000", "end": "00:00:10,000", "text": "Câu một"},
            {"index": 2, "start": "00:00:10,000", "end": "00:00:14,000", "text": "Câu hai"},
        ],
        "video_segments": [
            {"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:10.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95},
            {"segment_id": 2, "order": 2, "source_id": "source_1", "source_start": "00:00:10.000", "source_end": "00:00:14.000", "subtitle_start": 2, "subtitle_end": 2, "scene_description": "Tiếp theo", "importance_score": 80},
        ],
    })


def test_hard_trim_removes_inter_cue_gap():
    """Hard-trimmed seg1 (scene=10, voice=4) must compress internal cue and shift seg2 so cues abut."""
    payload = _payload_hard_trim_two_segments()
    plans = _plan_and_apply(payload, {1: 4.0, 2: 4.0}, source_duration=20.0)
    assert plans[0].decision == "sync_video_hard_trim"
    expected_dur = 4.0 + DEAD_AIR_TARGET_PADDING  # 4.75
    cue1_end = srt_timestamp_to_seconds(payload.srt[0].end)
    cue2_start = srt_timestamp_to_seconds(payload.srt[1].start)
    assert cue1_end == pytest.approx(expected_dur, rel=1e-3)
    assert cue2_start == pytest.approx(expected_dur, rel=1e-3)


def test_hard_trim_compresses_multiple_cues_in_segment():
    """Multiple internal cues in a hard-trimmed segment compress proportionally."""
    payload = _payload_three_cues()  # Seg1: 0-6 (cues 0-3, 3-6), Seg2: 6-10 (cue 6-10)
    # Cue 1=1.5s, Cue 2=1.5s → total 3s voice in 6s scene → hard trim required_dur=3.75
    # internal_scale = 3.75/6 = 0.625
    plans = _plan_and_apply(payload, {1: 1.5, 2: 1.5, 3: 4.0}, source_duration=20.0)
    assert plans[0].decision == "sync_video_hard_trim"
    expected_dur = 3.0 + DEAD_AIR_TARGET_PADDING  # 3.75
    # Cue 1: orig 0-3 → compressed to 0 - (3*0.625=1.875)
    assert srt_timestamp_to_seconds(payload.srt[0].start) == pytest.approx(0.0, abs=0.01)
    assert srt_timestamp_to_seconds(payload.srt[0].end) == pytest.approx(3.0 * expected_dur / 6.0, rel=1e-3)
    # Cue 2: orig 3-6 → compressed to 1.875 - 3.75
    assert srt_timestamp_to_seconds(payload.srt[1].start) == pytest.approx(3.0 * expected_dur / 6.0, rel=1e-3)
    assert srt_timestamp_to_seconds(payload.srt[1].end) == pytest.approx(expected_dur, rel=1e-3)
    # Cue 3 (seg2): shifted by delta (3.75 - 6 = -2.25), starts at 6 + (-2.25) = 3.75
    assert srt_timestamp_to_seconds(payload.srt[2].start) == pytest.approx(expected_dur, rel=1e-3)


def test_timing_diagnostics_voice_overflow_after_freeze_cap():
    """Overflow exceeds MAX_FREEZE_FRAME => VOICE_OVERFLOW + VOICE_SPEED_LIMIT."""
    payload = _payload_two_segments()
    # Scene=4, Voice=9: ratio=2.25 => ideal_video=0.667 < 0.92, voice=2.07 > 1.5 => fallback
    # overflow=5, source_remaining=0 => freeze capped at 3s
    # required=7, residual=7-9=-2.0 => VOICE_OVERFLOW
    # speed_factor=min(1.5, 9/7)=1.286 >= 1.10 => VOICE_SPEED_LIMIT
    plans = _plan_and_apply(payload, {1: 9.0, 2: 4.0}, source_duration=0.0)
    plan = plans[0]
    assert plan.decision == "hybrid_extend_speedup"
    assert "VOICE_OVERFLOW" in plan.warning
    assert "VOICE_SPEED_LIMIT" in plan.warning
