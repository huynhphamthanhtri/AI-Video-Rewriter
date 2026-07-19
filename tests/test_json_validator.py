from app.services.json_validator import JsonValidator
from app.schemas.render import RenderOptions


def valid_payload():
    return {
        "metadata": {"video_title": "A", "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu"}],
    }


def test_validate_json_success():
    valid, errors, model = JsonValidator().validate(valid_payload())
    assert valid is True
    assert errors == []
    assert model is not None


def test_validate_json_strips_markdown_code_fence():
    import json

    payload = "```json\n" + json.dumps(valid_payload()) + "\n```"
    valid, errors, model, fixed_payload = JsonValidator().validate_with_auto_fix(payload)
    assert valid is True
    assert errors == []
    assert model is not None
    assert fixed_payload == valid_payload()


def test_validate_json_missing_subtitle_reference():
    payload = valid_payload()
    payload["video_segments"][0]["subtitle_end"] = 9
    valid, errors, _ = JsonValidator().validate(payload)
    assert valid is False
    assert "subtitle không tồn tại" in errors[0]


def test_validate_json_duration_mismatch():
    payload = valid_payload()
    payload["video_segments"][0]["source_end"] = "00:00:40.000"
    valid, errors, _ = JsonValidator().validate(payload)
    assert valid is False
    assert "lệch timing: video=40.0s" in errors[0]


def test_alignment_warnings_for_long_dense_segment():
    payload = valid_payload()
    payload["srt"][0]["end"] = "00:00:10,000"
    payload["srt"][0]["text"] = "Player runs then crosses and striker shoots finally."
    payload["rewrite_script"]["full_text"] = payload["srt"][0]["text"]
    payload["video_segments"][0]["source_end"] = "00:00:10.000"
    warnings = JsonValidator().alignment_warnings(payload)
    assert any("Segment #1 dài" in warning for warning in warnings)
    assert any("nhiều hành động" in warning for warning in warnings)


def test_validate_json_auto_fix_duration_mismatch():
    payload = valid_payload()
    payload["video_segments"][0]["source_end"] = "00:00:40.000"
    valid, errors, model, fixed_payload = JsonValidator().validate_with_auto_fix(payload)
    assert valid is True
    assert model is not None
    assert fixed_payload is not None
    assert fixed_payload["video_segments"][0]["source_end"] == "00:00:03.000"
    assert errors[0].startswith("AUTO FIX")


def test_validate_json_tts_hybrid_trims_long_source_duration():
    payload = valid_payload()
    payload["video_segments"][0]["source_end"] = "00:00:40.000"
    options = RenderOptions(tts_mode="voiceover", tts_fit_policy="hybrid")

    valid, errors, model, fixed_payload = JsonValidator().validate_with_auto_fix(payload, render_options=options)

    assert valid is True
    assert model is not None
    assert fixed_payload is not None
    assert fixed_payload["video_segments"][0]["source_end"] == "00:00:03.000"
    assert errors[0].startswith("AUTO FIX")


def test_validate_json_tts_hybrid_extends_small_shortage():
    payload = valid_payload()
    payload["srt"][0]["end"] = "00:00:06,000"
    payload["video_segments"][0]["source_end"] = "00:00:03.000"
    options = RenderOptions(tts_mode="voiceover", tts_fit_policy="hybrid")

    valid, errors, model, fixed_payload = JsonValidator().validate_with_auto_fix(payload, render_options=options)

    assert valid is True
    assert model is not None
    assert fixed_payload is not None
    assert fixed_payload["video_segments"][0]["source_end"] == "00:00:06.000"
    assert errors[0].startswith("AUTO FIX")


def test_validate_json_tts_hybrid_rejects_large_shortage():
    payload = valid_payload()
    payload["srt"][0]["end"] = "00:00:12,000"
    payload["video_segments"][0]["source_end"] = "00:00:03.000"
    options = RenderOptions(tts_mode="voiceover", tts_fit_policy="hybrid")

    valid, errors, model, fixed_payload = JsonValidator().validate_with_auto_fix(payload, render_options=options)

    assert valid is False
    assert model is None
    assert fixed_payload is None
    assert any("lệch timing: video=3.0s" in error for error in errors)


def test_validate_json_tts_hybrid_repairs_mixed_duration_mismatch():
    payload = valid_payload()
    payload["rewrite_script"]["full_text"] = "Một Hai"
    payload["srt"] = [
        {"index": 1, "start": "00:00:00,000", "end": "00:00:15,000", "text": "Một"},
        {"index": 2, "start": "00:00:15,000", "end": "00:00:30,000", "text": "Hai"},
    ]
    payload["video_segments"] = [
        {"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:23.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Một"},
        {"segment_id": 2, "order": 2, "source_start": "00:00:30.000", "source_end": "00:00:42.000", "subtitle_start": 2, "subtitle_end": 2, "scene_description": "Hai"},
    ]
    options = RenderOptions(tts_mode="voiceover", tts_fit_policy="hybrid")

    valid, errors, model, fixed_payload = JsonValidator().validate_with_auto_fix(payload, render_options=options)

    assert valid is True
    assert model is not None
    assert fixed_payload is not None
    assert fixed_payload["video_segments"][0]["source_end"] == "00:00:15.000"
    assert fixed_payload["video_segments"][1]["source_end"] == "00:00:45.000"
    assert errors[0].startswith("AUTO FIX")


def test_validate_json_tts_segment_uniform_keeps_duration_auto_fix():
    payload = valid_payload()
    payload["video_segments"][0]["source_end"] = "00:00:40.000"
    options = RenderOptions(tts_mode="voiceover", tts_fit_policy="segment_uniform")

    valid, errors, model, fixed_payload = JsonValidator().validate_with_auto_fix(payload, render_options=options)

    assert valid is True
    assert model is not None
    assert fixed_payload is not None
    assert fixed_payload["video_segments"][0]["source_end"] == "00:00:03.000"
    assert errors[0].startswith("AUTO FIX")


def test_validate_json_duplicate_srt_index():
    payload = valid_payload()
    payload["srt"].append({"index": 1, "start": "00:00:03,000", "end": "00:00:06,000", "text": "Trùng"})
    valid, errors, _ = JsonValidator().validate(payload)
    assert valid is False
    assert "srt có index bị trùng" in errors[0]


def test_validate_json_duplicate_srt_with_segment_ref_does_not_auto_fix():
    payload = valid_payload()
    payload["srt"] = [
        {"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Một"},
        {"index": 1, "start": "00:00:04,000", "end": "00:00:06,000", "text": "Hai (trùng index)"},
    ]
    payload["video_segments"] = [
        {"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:06.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Cảnh"},
    ]
    valid, errors, model, fixed_payload = JsonValidator().validate_with_auto_fix(payload)
    assert valid is False, "auto-fix should not silently produce valid payload when duplicates exist"
    assert model is None


def test_validate_json_duplicate_segment_order():
    payload = valid_payload()
    payload["srt"].append({"index": 2, "start": "00:00:03,000", "end": "00:00:06,000", "text": "Xin chào"})
    payload["video_segments"].append({"segment_id": 2, "order": 1, "source_start": "00:00:03.000", "source_end": "00:00:06.000", "subtitle_start": 2, "subtitle_end": 2, "scene_description": "Mở đầu"})
    valid, errors, _ = JsonValidator().validate(payload)
    assert valid is False
    assert "video_segments có order bị trùng" in errors[0]


def test_validate_json_multi_source_success():
    payload = valid_payload()
    payload["sources"] = [{"source_id": "source_1", "youtube_url": "https://youtube.com/watch?v=a", "label": "A"}]
    payload["video_segments"][0]["source_id"] = "source_1"
    valid, errors, _ = JsonValidator().validate(payload)
    assert valid is True
    assert errors == []


def test_validate_json_multi_source_missing_segment_source_id():
    payload = valid_payload()
    payload["sources"] = [{"source_id": "source_1", "youtube_url": "https://youtube.com/watch?v=a", "label": "A"}]
    valid, errors, _ = JsonValidator().validate(payload)
    assert valid is False
    assert "thiếu source_id" in errors[0]


def test_validate_json_multi_source_unknown_source_id():
    payload = valid_payload()
    payload["sources"] = [{"source_id": "source_1", "youtube_url": "https://youtube.com/watch?v=a", "label": "A"}]
    payload["video_segments"][0]["source_id"] = "source_2"
    valid, errors, _ = JsonValidator().validate(payload)
    assert valid is False
    assert "source_id không tồn tại" in errors[0]


def test_validate_json_sanitizes_google_search_url():
    wrapped = "https://www.google.com/search?q=https://youtube.com/watch%3Fv%3Dabc123"
    result = JsonValidator()._sanitize_url(wrapped)
    assert result == "https://youtube.com/watch?v=abc123"


def test_validate_json_sanitizes_google_redirect_url():
    wrapped = "https://www.google.com/url?q=https%3A%2F%2Fyoutu.be%2Fxyz789"
    result = JsonValidator()._sanitize_url(wrapped)
    assert result == "https://youtu.be/xyz789"


def test_validate_json_sanitize_google_passthrough():
    result = JsonValidator()._sanitize_url("https://www.google.com/search?q=cats")
    assert "google.com/search" in result


def test_normalize_srt_timestamp_missing_hour():
    payload = {
        "srt": [
            {"index": 1, "start": "00:15,000", "end": "00:00:30,000", "text": "test"},
        ],
    }
    JsonValidator()._normalize_srt_timestamps(payload)
    assert payload["srt"][0]["start"] == "00:00:15,000"
    assert payload["srt"][0]["end"] == "00:00:30,000"


def test_normalize_srt_timestamp_valid_unchanged():
    payload = {
        "srt": [
            {"index": 1, "start": "00:00:15,000", "end": "00:00:30,000", "text": "test"},
        ],
    }
    JsonValidator()._normalize_srt_timestamps(payload)
    assert payload["srt"][0]["start"] == "00:00:15,000"
    assert payload["srt"][0]["end"] == "00:00:30,000"


def test_normalize_metadata_language_vi():
    payload = {
        "metadata": {
            "target_language": "vi",
            "target_market": "Vietnam",
        },
    }
    JsonValidator()._normalize_metadata_language(payload)
    assert payload["metadata"]["target_language"] == "Tiếng Việt"
    assert payload["metadata"]["target_market"] == "Việt Nam"


def test_normalize_metadata_language_unchanged():
    payload = {
        "metadata": {
            "target_language": "Tiếng Việt",
            "target_market": "Việt Nam",
        },
    }
    JsonValidator()._normalize_metadata_language(payload)
    assert payload["metadata"]["target_language"] == "Tiếng Việt"
    assert payload["metadata"]["target_market"] == "Việt Nam"


def test_validate_json_unwraps_google_url_in_sources():
    import json
    payload = valid_payload()
    payload["sources"] = [{"source_id": "source_1", "youtube_url": "https://www.google.com/search?q=https://youtube.com/watch%3Fv%3Dabc123", "label": "A"}]
    payload["video_segments"][0]["source_id"] = "source_1"
    json_str = json.dumps(payload)
    valid, errors, model, fixed_payload = JsonValidator().validate_with_auto_fix(json_str)
    assert valid is True
    assert errors == []
    assert fixed_payload["sources"][0]["youtube_url"] == "https://youtube.com/watch?v=abc123"


def test_validate_srt_overlap_fails():
    payload = valid_payload()
    payload["srt"] = [
        {"index": 1, "start": "00:00:00,000", "end": "00:00:06,000", "text": "Mở đầu"},
        {"index": 2, "start": "00:00:06,000", "end": "00:01:22,000", "text": "Quá dài, chồng lên cue 3"},
        {"index": 3, "start": "00:00:12,000", "end": "00:00:19,000", "text": "Nằm trong khoảng cue 2"},
    ]
    payload["video_segments"] = [
        {"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:06.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu"},
        {"segment_id": 2, "order": 2, "source_start": "00:00:06.000", "source_end": "00:01:22.000", "subtitle_start": 2, "subtitle_end": 2, "scene_description": "Tiếp"},
        {"segment_id": 3, "order": 3, "source_start": "00:00:12.000", "source_end": "00:00:19.000", "subtitle_start": 3, "subtitle_end": 3, "scene_description": "Xung đột"},
    ]
    valid, errors, _ = JsonValidator().validate(payload)
    assert valid is False
    srt_overlap_errors = [e for e in errors if "SRT_OVERLAP" in e]
    assert len(srt_overlap_errors) == 1
    assert "srt[2]" in srt_overlap_errors[0]
    assert "srt[3]" in srt_overlap_errors[0]


def test_validate_srt_tiny_overlap_auto_fix():
    payload = valid_payload()
    payload["rewrite_script"]["full_text"] = "Hơi dài OK"
    payload["srt"] = [
        {"index": 1, "start": "00:00:00,000", "end": "00:00:06,200", "text": "Hơi dài"},
        {"index": 2, "start": "00:00:06,000", "end": "00:00:10,000", "text": "OK"},
    ]
    payload["video_segments"] = [
        {"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:10.000", "subtitle_start": 1, "subtitle_end": 2, "scene_description": "Cảnh"},
    ]
    valid, errors, model, fixed_payload = JsonValidator().validate_with_auto_fix(payload)
    assert valid is True, f"Tiny overlap should be auto-fixed but got: {errors}"
    assert model is not None
    cue1_end = fixed_payload["srt"][0]["end"]
    assert cue1_end == "00:00:06,000", f"Expected trimmed to 00:00:06,000 but got {cue1_end}"


def test_validate_terminal_segment_must_cover_last_srt():
    payload = valid_payload()
    payload["srt"] = [
        {"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Mở đầu"},
        {"index": 2, "start": "00:00:03,000", "end": "00:00:06,000", "text": "Kết thúc"},
    ]
    payload["rewrite_script"]["full_text"] = "Mở đầu Kết thúc"
    payload["video_segments"][0]["source_end"] = "00:00:03.000"
    payload["video_segments"][0]["subtitle_end"] = 1

    valid, errors, _ = JsonValidator().validate(payload)

    assert valid is False
    assert any(error.startswith("TIMELINE_TERMINAL_SYNC_MISMATCH") for error in errors)


def test_validate_unmapped_srt_index_fails():
    payload = valid_payload()
    payload["srt"] = [
        {"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Một"},
        {"index": 2, "start": "00:00:03,000", "end": "00:00:06,000", "text": "Hai"},
    ]
    payload["rewrite_script"]["full_text"] = "Một Hai"
    payload["video_segments"][0]["source_end"] = "00:00:03.000"
    payload["video_segments"][0]["subtitle_end"] = 1

    valid, errors, _ = JsonValidator().validate(payload)

    assert valid is False
    assert any(error.startswith("TIMELINE_UNMAPPED_SRT") for error in errors)


def test_validate_wide_range_mapping_covers_sequential_srt():
    payload = valid_payload()
    payload["srt"] = [
        {"index": 1, "start": "00:00:00,000", "end": "00:00:02,000", "text": "Một"},
        {"index": 2, "start": "00:00:02,000", "end": "00:00:04,000", "text": "Hai"},
    ]
    payload["rewrite_script"]["full_text"] = "Một Hai"
    payload["video_segments"][0].update({
        "source_end": "00:00:04.000",
        "subtitle_end": 2,
    })

    valid, errors, _ = JsonValidator().validate(payload)

    assert valid is True
    assert errors == []


def test_validate_full_text_mismatch_fails_without_auto_fix():
    payload = valid_payload()
    payload["rewrite_script"]["full_text"] = "Nội dung khác"

    valid, errors, model, fixed_payload = JsonValidator().validate_with_auto_fix(payload)

    assert valid is False
    assert model is None
    assert fixed_payload is None
    assert any(error.startswith("TIMELINE_FULL_TEXT_MISMATCH") for error in errors)


def test_validate_does_not_auto_fix_semantic_full_text_mismatch():
    payload = valid_payload()
    payload["rewrite_script"]["full_text"] = "Xin chào bạn, hôm nay chúng ta cùng bắt đầu câu chuyện."
    payload["srt"][0]["text"] = "Xin chào bạn hôm nay chúng ta cùng bắt đầu câu chuyện."
    payload["video_segments"][0]["source_end"] = "00:00:08.000"

    valid, errors, model, fixed_payload = JsonValidator().validate_with_auto_fix(
        payload,
        render_options=RenderOptions(tts_mode="voiceover", tts_fit_policy="hybrid"),
    )

    assert valid is False
    assert model is None
    assert fixed_payload is None
    assert any(error.startswith("TIMELINE_FULL_TEXT_MISMATCH") for error in errors)


def test_validate_fails_when_exact_target_duration_is_incomplete():
    payload = valid_payload()
    payload["metadata"]["target_duration"] = "4 phút"
    payload["srt"][0]["end"] = "00:01:15,000"
    payload["video_segments"][0]["source_end"] = "00:01:15.000"

    valid, errors, _ = JsonValidator().validate(payload)

    assert valid is False
    assert any(error.startswith("TIMELINE_DURATION_INCOMPLETE") for error in errors)


def test_validate_exact_target_duration_passes():
    payload = valid_payload()
    payload["metadata"]["target_duration"] = "4 phút"
    payload["srt"][0]["end"] = "00:04:00,000"
    payload["video_segments"][0]["source_end"] = "00:04:00.000"

    valid, errors, _ = JsonValidator().validate(payload)

    assert valid is True
    assert errors == []


def test_validate_srt_large_overlap_no_auto_fix():
    payload = valid_payload()
    payload["srt"] = [
        {"index": 1, "start": "00:00:00,000", "end": "00:00:06,000", "text": "Mở đầu"},
        {"index": 2, "start": "00:00:06,000", "end": "00:01:22,000", "text": "Quá dài"},
        {"index": 3, "start": "00:00:12,000", "end": "00:00:19,000", "text": "Nằm trong cue 2"},
    ]
    payload["video_segments"] = [
        {"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:06.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu"},
        {"segment_id": 2, "order": 2, "source_start": "00:00:06.000", "source_end": "00:01:22.000", "subtitle_start": 2, "subtitle_end": 2, "scene_description": "Tiếp"},
        {"segment_id": 3, "order": 3, "source_start": "00:00:12.000", "source_end": "00:00:19.000", "subtitle_start": 3, "subtitle_end": 3, "scene_description": "Xung đột"},
    ]
    valid, errors, model, fixed_payload = JsonValidator().validate_with_auto_fix(payload)
    assert valid is False, "Large overlap should not be auto-fixed"
    assert model is None
    srt_overlap_errors = [e for e in errors if "SRT_OVERLAP" in e]
    assert len(srt_overlap_errors) >= 1, "Should report SRT overlap in errors"
