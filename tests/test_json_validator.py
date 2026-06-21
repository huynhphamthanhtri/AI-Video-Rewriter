from app.services.json_validator import JsonValidator


def valid_payload():
    return {
        "metadata": {"video_title": "A", "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
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
    assert "thời lượng 40.0 giây" in errors[0]


def test_alignment_warnings_for_long_dense_segment():
    payload = valid_payload()
    payload["srt"][0]["end"] = "00:00:10,000"
    payload["srt"][0]["text"] = "Player runs then crosses and striker shoots finally."
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


def test_validate_json_duplicate_srt_index():
    payload = valid_payload()
    payload["srt"].append({"index": 1, "start": "00:00:03,000", "end": "00:00:06,000", "text": "Trùng"})
    valid, errors, _ = JsonValidator().validate(payload)
    assert valid is False
    assert "srt có index bị trùng" in errors[0]


def test_validate_json_duplicate_segment_order():
    payload = valid_payload()
    payload["srt"].append({"index": 2, "start": "00:00:03,000", "end": "00:00:06,000", "text": "Xin chào"})
    payload["video_segments"].append({"segment_id": 2, "order": 1, "source_start": "00:00:03.000", "source_end": "00:00:06.000", "subtitle_start": 2, "subtitle_end": 2, "scene_description": "Mở đầu", "importance_score": 95})
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
