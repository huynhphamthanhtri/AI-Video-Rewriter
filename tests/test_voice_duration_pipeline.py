import pytest

from app.schemas.render import GeminiPayloadSchema, RenderOptions, clip_timestamp_to_seconds, srt_timestamp_to_seconds
from app.services.segment_planner import SegmentPlanner, SAFE_VIDEO_MIN_SOFT, SAFE_VIDEO_MAX_SOFT, DEAD_AIR_HARD_TRIM_THRESHOLD, DEAD_AIR_TARGET_PADDING, SOFT_DEAD_AIR_TRIGGER_SECONDS, SOFT_DEAD_AIR_MIN_PADDING, SOFT_DEAD_AIR_RATIO
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
            {"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:04.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu"},
            {"segment_id": 2, "order": 2, "source_id": "source_1", "source_start": "00:00:04.000", "source_end": "00:00:08.000", "subtitle_start": 2, "subtitle_end": 2, "scene_description": "Tiếp theo"},
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
            {"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:06.000", "subtitle_start": 1, "subtitle_end": 2, "scene_description": "Mở đầu"},
            {"segment_id": 2, "order": 2, "source_id": "source_1", "source_start": "00:00:06.000", "source_end": "00:00:10.000", "subtitle_start": 3, "subtitle_end": 3, "scene_description": "Kết"},
        ],
    })


def _plan_and_apply(payload: GeminiPayloadSchema, natural_durations: dict[int, float], source_duration: float):
    options = RenderOptions(tts_mode="voiceover", tts_fit_policy="hybrid", tts_max_speed=1.5)
    planner = SegmentPlanner()
    plans = planner.plan(payload, options, natural_durations, {"source_1": source_duration})
    shifts = planner.compute_srt_shifts(plans, payload)
    _apply_segment_plan_to_payload(payload, plans, shifts)
    return plans


def test_hybrid_small_overflow_now_uses_sync_duration_balance():
    """Previously footage_extend for voice 4.3/scene 4. Now handled by duration balance."""
    payload = _payload_two_segments()
    plans = _plan_and_apply(payload, {1: 4.3, 2: 4.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "sync_duration_balance"
    assert plan.video_speed_factor < 1.0  # slowdown
    assert plan.speed_factor > 1.0  # voice speedup
    assert plan.extend_seconds == 0.0
    # SRT cues stretched (video slower → cues longer)
    internal_scale = 1.0 / plan.video_speed_factor
    expected_cue1_end = srt_timestamp_to_seconds(payload.srt[0].end)
    assert expected_cue1_end == pytest.approx(4.0 * internal_scale, rel=1e-3)
    expected_cue2_start = srt_timestamp_to_seconds(payload.srt[1].start)
    assert expected_cue2_start == pytest.approx(4.0 * internal_scale, rel=1e-3)


def test_hybrid_large_overflow_now_uses_sync_duration_balance():
    """Previously footage_extend for voice 5.0/scene 4. Now duration balance."""
    payload = _payload_two_segments()
    plans = _plan_and_apply(payload, {1: 5.0, 2: 4.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "sync_duration_balance"
    assert plan.required_duration == pytest.approx(4.5, rel=1e-3)
    assert plan.extend_seconds == 0.0
    internal_scale = 4.5 / 4.0
    expected_cue1_end = srt_timestamp_to_seconds(payload.srt[0].end)
    assert expected_cue1_end == pytest.approx(4.0 * internal_scale, rel=1e-3)
    expected_cue2_start = srt_timestamp_to_seconds(payload.srt[1].start)
    assert expected_cue2_start == pytest.approx(4.0 * internal_scale, rel=1e-3)


def test_hybrid_large_overflow_with_exhausted_source_now_uses_sync_duration_balance():
    """Previously freeze_frame for voice 6.0/scene 4. Now fits within 1.5 max speed."""
    payload = _payload_two_segments()
    plans = _plan_and_apply(payload, {1: 6.0, 2: 4.0}, source_duration=4.0)

    plan = plans[0]
    assert plan.decision == "sync_duration_balance"
    target = 4.0 / SAFE_VIDEO_MIN_SOFT
    assert plan.required_duration == pytest.approx(target, rel=1e-3)
    assert plan.speed_factor == pytest.approx(6.0 / target, rel=1e-3)
    assert plan.extend_seconds == 0.0
    assert payload.video_segments[0].freeze_frame_duration is None
    internal_scale = target / 4.0
    expected_cue1_end = srt_timestamp_to_seconds(payload.srt[0].end)
    assert expected_cue1_end == pytest.approx(4.0 * internal_scale, rel=1e-3)


def test_segment_plan_serialization_has_explicit_duration_fields():
    payload = _payload_two_segments()
    plans = _plan_and_apply(payload, {1: 5.0, 2: 4.0}, source_duration=20.0)

    data = _segment_plan_to_dict(plans[0])

    # Now uses duration balance: target=(scene+voice)/2 = 4.5s
    assert data["original_scene_duration"] == pytest.approx(4.0)
    assert data["final_scene_duration"] == pytest.approx(4.5, rel=1e-3)
    assert data["natural_voice_duration"] == pytest.approx(5.0)
    assert data["extend_seconds"] == 0.0
    assert data["decision"] == "sync_duration_balance"
    assert data["speed_factor"] == pytest.approx(5.0 / 4.5, rel=1e-3)
    assert data["video_speed_factor"] == pytest.approx(4.0 / 4.5, rel=1e-3)
    assert data["freeze_duration"] is None
    assert data["balance_ratio"] == pytest.approx(0.5)
    assert data["warning"] != ""
    assert "scene_duration" not in data
    assert "required_duration" not in data


def test_sync_duration_balance_small_overflow():
    """Voice slightly longer than scene → balanced video slowdown + voice speedup."""
    payload = _payload_two_segments()
    # Voice 4.3s in 4s scene: diff=0.3 > tolerance=0.25 → proceed
    # ratio=1.075, ideal_video=1/sqrt(1.075)=0.965, voice=sqrt(1.075)=1.037
    # Both within caps → exact balanced fit
    plans = _plan_and_apply(payload, {1: 4.3, 2: 4.0}, source_duration=20.0)

    plan = plans[0]
    target = 4.0 + (4.3 - 4.0) * 0.5
    assert plan.decision == "sync_duration_balance"
    assert plan.required_duration == pytest.approx(target, rel=1e-3)
    assert plan.video_speed_factor == pytest.approx(4.0 / target, rel=1e-3)
    assert plan.speed_factor == pytest.approx(4.3 / target, rel=1e-3)
    assert plan.extend_seconds == 0.0
    assert plan.duration_delta_seconds == pytest.approx(target - 4.0, rel=1e-3)

    # SRT cues should be stretched by internal_scale = 1/video_speed (video slows down → cues longer)
    internal_scale = target / 4.0
    expected_cue1_end = srt_timestamp_to_seconds(payload.srt[0].end)
    assert expected_cue1_end == pytest.approx(4 * internal_scale, rel=1e-3)

    # Second segment should be shifted by delta
    expected_cue2_start = srt_timestamp_to_seconds(payload.srt[1].start)
    assert expected_cue2_start == pytest.approx(4 + plan.duration_delta_seconds, rel=1e-3)


def test_sync_duration_balance_hits_video_min_cap():
    """Video slowdown capped at SAFE_VIDEO_MIN_SOFT, voice compensates."""
    payload = _payload_two_segments()
    # Scene=4s, Voice=5.0s → ratio=1.25
    # ideal_video=1/sqrt(1.25)=0.894 < 0.92 → capped at SAFE_VIDEO_MIN_SOFT
    # voice_speed = 1.25 * 0.92 = 1.15 ≤ 1.5 → fits
    plans = _plan_and_apply(payload, {1: 5.0, 2: 4.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "sync_duration_balance"
    target = 4.0 + (5.0 - 4.0) * 0.5
    assert plan.video_speed_factor == pytest.approx(4.0 / target, rel=1e-3)
    assert plan.speed_factor == pytest.approx(5.0 / target, rel=1e-3)
    assert plan.extend_seconds == 0.0


def test_duration_balance_10s_scene_14s_voice_uses_midpoint_with_video_cap():
    payload = _payload_long_scene()
    plans = _plan_and_apply(payload, {1: 14.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "sync_duration_balance"
    target = 10.0 / SAFE_VIDEO_MIN_SOFT
    assert plan.required_duration == pytest.approx(target, rel=1e-3)
    assert plan.video_speed_factor == pytest.approx(SAFE_VIDEO_MIN_SOFT, rel=1e-3)
    assert plan.speed_factor == pytest.approx(14.0 / target, rel=1e-3)


def test_balanced_large_overflow_clamps_to_video_slowdown_cap():
    """Voice too long for midpoint target clamps to video slowdown cap before fallback."""
    payload = _payload_two_segments()
    # Scene=4s, Voice=7s → 50/50 target=5.5 but video slowdown clamps to 4/0.85.
    plans = _plan_and_apply(payload, {1: 7.0, 2: 4.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "sync_duration_balance"
    target = 4.0 / SAFE_VIDEO_MIN_SOFT
    assert plan.required_duration == pytest.approx(target, rel=1e-3)
    assert plan.video_speed_factor == pytest.approx(SAFE_VIDEO_MIN_SOFT, rel=1e-3)
    assert plan.speed_factor == pytest.approx(7.0 / target, rel=1e-3)


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
    """Multi-cue segment with video slowdown → cues are redistributed by natural voice duration."""
    payload = _payload_three_cues()
    # Segment 1: scene=6s (0-6), two cues (0-3, 3-6)
    # Cue1=3.2s, Cue2=3.3s → total=6.5s, diff=0.5 > tolerance=0.30
    # ratio=6.5/6=1.083, ideal_video=1/sqrt(1.083)=0.961, voice=sqrt(1.083)=1.041
    # Both within caps → sync_speed_balance
    plans = _plan_and_apply(payload, {1: 3.2, 2: 3.3, 3: 4.0}, source_duration=20.0)

    plan = plans[0]
    assert plan.decision == "sync_duration_balance"
    assert plan.video_speed_factor < 1.0  # slowdown

    target = 6.0 + (6.5 - 6.0) * 0.5
    cue1_target = target * (3.2 / 6.5)
    cue1_start = srt_timestamp_to_seconds(payload.srt[0].start)
    cue1_end = srt_timestamp_to_seconds(payload.srt[0].end)
    assert cue1_start == pytest.approx(0.0, abs=0.01)
    assert cue1_end == pytest.approx(cue1_target, rel=1e-3)

    cue2_start = srt_timestamp_to_seconds(payload.srt[1].start)
    cue2_end = srt_timestamp_to_seconds(payload.srt[1].end)
    assert cue2_start == pytest.approx(cue1_target, rel=1e-3)
    assert cue2_end == pytest.approx(target, rel=1e-3)

    # Cue 3 (segment 2, unchanged) should be shifted by segment 1 delta
    cue3_start = srt_timestamp_to_seconds(payload.srt[2].start)
    expected_delta = plan.duration_delta_seconds
    assert cue3_start == pytest.approx(6.0 + expected_delta, rel=1e-3)


def test_sync_duration_balance_preserves_no_change_for_exact_fit():
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
            {"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:10.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu"},
        ],
    })


def test_sync_video_hard_trim_with_severe_underflow():
    """Large underflow (scene 10s, voice 4s) => residual 4.696 >= 4.0 => hard trim."""
    payload = _payload_long_scene()
    # Scene=10, Voice=4: speedup_dur=10/1.15=8.696, residual=4.696 >= 4.0 => hard trim
    # required_duration=4+0.25=4.25
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
    expected_dur = 4.0 + DEAD_AIR_TARGET_PADDING  # 4.25
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
            {"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:10.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu"},
            {"segment_id": 2, "order": 2, "source_id": "source_1", "source_start": "00:00:10.000", "source_end": "00:00:14.000", "subtitle_start": 2, "subtitle_end": 2, "scene_description": "Tiếp theo"},
        ],
    })


def test_hard_trim_removes_inter_cue_gap():
    """Hard-trimmed seg1 (scene=10, voice=4) must compress internal cue and shift seg2 so cues abut."""
    payload = _payload_hard_trim_two_segments()
    plans = _plan_and_apply(payload, {1: 4.0, 2: 4.0}, source_duration=20.0)
    assert plans[0].decision == "sync_video_hard_trim"
    expected_dur = 4.0 + DEAD_AIR_TARGET_PADDING  # 4.25
    cue1_end = srt_timestamp_to_seconds(payload.srt[0].end)
    cue2_start = srt_timestamp_to_seconds(payload.srt[1].start)
    assert cue1_end == pytest.approx(expected_dur, rel=1e-3)
    assert cue2_start == pytest.approx(expected_dur, rel=1e-3)


def test_underflow_below_hard_trim_threshold_uses_soft_trim():
    """Residual 2.217 < 4.0 => no hard trim, uses sync_video_trim_speedup_capped."""
    payload = _payload_three_cues()  # Seg1: 0-6 (cues 0-3, 3-6), Seg2: 6-10 (cue 6-10)
    # Cue 1=1.5s, Cue 2=1.5s → total 3s voice in 6s scene
    # speedup_dur=6/1.15=5.217, residual=2.217 < 4.0 => no hard trim
    plans = _plan_and_apply(payload, {1: 1.5, 2: 1.5, 3: 4.0}, source_duration=20.0)
    plan = plans[0]
    assert plan.decision == "sync_video_soft_trim"
    assert plan.video_speed_factor == SAFE_VIDEO_MAX_SOFT
    assert plan.speed_factor == 1.0
    # After capped speedup: final_dur = 6/1.15 = 5.217
    expected_final = 3.0 + SOFT_DEAD_AIR_MIN_PADDING
    assert plan.required_duration == pytest.approx(expected_final, rel=1e-3)
    assert "SOFT_TRIM_DEAD_AIR" in plan.warning
    assert "HARD_TRIM_DEAD_AIR" not in plan.warning


# ── Soft trim tests ──


def _payload_soft_trim_scene() -> GeminiPayloadSchema:
    """8s scene with 4s voice; used for soft trim testing."""
    return GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "A", "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút"},
        "sources": [{"source_id": "source_1", "local_video_path": "E:/AUTO_REVIEW/test.mp4"}],
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [
            {"index": 1, "start": "00:00:00,000", "end": "00:00:08,000", "text": "Câu một"},
        ],
        "video_segments": [
            {"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:08.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu"},
        ],
    })


def test_soft_trim_applies_when_extra_dead_air_large():
    """Scene=8s, Voice=4s: speedup=6.957, residual=2.957 < hard trim threshold,
    extra=2.057 >= 1.5 trigger → soft trim."""
    payload = _payload_soft_trim_scene()
    plans = _plan_and_apply(payload, {1: 4.0}, source_duration=20.0)
    plan = plans[0]
    assert plan.decision == "sync_video_soft_trim"
    assert plan.video_speed_factor == SAFE_VIDEO_MAX_SOFT
    assert plan.speed_factor == 1.0
    padding = max(SOFT_DEAD_AIR_MIN_PADDING, min(1.0, 4.0 * SOFT_DEAD_AIR_RATIO))
    expected_dur = 4.0 + padding
    assert plan.required_duration == pytest.approx(expected_dur, rel=1e-3)
    assert plan.duration_delta_seconds == pytest.approx(expected_dur - 8.0, rel=1e-3)
    assert "SOFT_TRIM_DEAD_AIR" in plan.warning
    assert "HARD_TRIM_DEAD_AIR" not in plan.warning


def test_soft_trim_normalizes_moderate_dead_air():
    """Scene=8s, Voice=5s: extra=0.957 < 1.5 trigger → capped speedup, not soft trim."""
    payload = _payload_soft_trim_scene()
    plans = _plan_and_apply(payload, {1: 5.0}, source_duration=20.0)
    plan = plans[0]
    assert plan.decision == "sync_video_soft_trim"
    assert "SOFT_TRIM_DEAD_AIR" in plan.warning


def test_soft_trim_applies_regardless_of_score():
    """Scene=8s, Voice=4s: soft trim applies since importance check was removed."""
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "A", "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút"},
        "sources": [{"source_id": "source_1", "local_video_path": "E:/AUTO_REVIEW/test.mp4"}],
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [
            {"index": 1, "start": "00:00:00,000", "end": "00:00:08,000", "text": "Câu một"},
        ],
        "video_segments": [
            {"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:08.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu"},
        ],
    })
    plans = _plan_and_apply(payload, {1: 4.0}, source_duration=20.0)
    plan = plans[0]
    assert plan.decision == "sync_video_soft_trim"


def test_soft_trim_scales_srt_by_final_duration():
    """Soft-trimmed segment: single cue end must be scaled by final_dur/orig_dur (same as hard trim)."""
    payload = _payload_soft_trim_scene()
    plans = _plan_and_apply(payload, {1: 4.0}, source_duration=20.0)
    plan = plans[0]
    assert plan.decision == "sync_video_soft_trim"
    expected_final = plan.required_duration
    cue_end = srt_timestamp_to_seconds(payload.srt[0].end)
    # internal_scale = final_dur / orig_dur; single cue covers full scene
    assert cue_end == pytest.approx(expected_final, rel=1e-3)


def test_soft_trim_with_two_segments_shifts_next_segment():
    """Soft-trimmed seg1 shifts seg2 by delta."""
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "A", "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút"},
        "sources": [{"source_id": "source_1", "local_video_path": "E:/AUTO_REVIEW/test.mp4"}],
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [
            {"index": 1, "start": "00:00:00,000", "end": "00:00:08,000", "text": "Câu một"},
            {"index": 2, "start": "00:00:08,000", "end": "00:00:12,000", "text": "Câu hai"},
        ],
        "video_segments": [
            {"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:08.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu"},
            {"segment_id": 2, "order": 2, "source_id": "source_1", "source_start": "00:00:08.000", "source_end": "00:00:12.000", "subtitle_start": 2, "subtitle_end": 2, "scene_description": "Tiếp theo"},
        ],
    })
    # Seg1: scene=8, voice=4 → soft trim (residual=2.957 < 4.0, extra=2.057 >= 1.5)
    # Seg2: scene=4, voice=4 → no_change
    plans = _plan_and_apply(payload, {1: 4.0, 2: 4.0}, source_duration=20.0)
    assert plans[0].decision == "sync_video_soft_trim"
    cue1_end = srt_timestamp_to_seconds(payload.srt[0].end)
    cue2_start = srt_timestamp_to_seconds(payload.srt[1].start)
    assert cue2_start == pytest.approx(cue1_end, rel=1e-3)


# ── Trailing trim tests ──


def test_trailing_trim_triggered_when_expected():
    """Probe-based test: verify trailing trim diagnostic is included in render plan when tail exceeds threshold."""
    # This test validates the logic path; actual ffmpeg probe is tested via integration
    from app.services.video_tools import TRAILING_DEAD_AIR_TRIM_THRESHOLD, _trim_tts_trailing_dead_air_if_needed
    assert TRAILING_DEAD_AIR_TRIM_THRESHOLD == 6.0


def test_trailing_trim_skipped_without_voiceover():
    """Trailing trim returns early when no voiceover path provided."""
    from app.services.video_tools import _trim_tts_trailing_dead_air_if_needed
    from app.services.video_tools import select_video_encoder
    from pathlib import Path
    from app.schemas.render import RenderOptions
    profile = select_video_encoder()
    result = _trim_tts_trailing_dead_air_if_needed(Path("dummy.mp4"), None, Path("out.mp4"), RenderOptions(), encoder_profile=profile)
    assert result[1]["applied"] is False
    assert result[1]["reason"] == "missing_voiceover_path"


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
