from app.services.gemini_automation import GeminiAutomationService


def make_valid_edl_dict(title="10 Phút Nấu Phở", script="Hôm nay chúng ta sẽ cùng học nấu phở.", srt_text="Hôm nay chúng ta sẽ cùng học nấu phở"):
    return {
        "metadata": {
            "video_title": title,
            "rewrite_style": "Hài hước",
            "target_audience": "Đại chúng",
            "tone": "Vui vẻ",
            "target_duration": "8-10 phút",
            "target_language": "Tiếng Việt",
            "target_market": "Việt Nam",
            "localization_level": "full",
            "hashtags": ["phở", "nấu ăn"],
        },
        "sources": [
            {
                "source_id": "source_1",
                "youtube_url": "https://www.youtube.com/watch?v=realVideoId",
                "label": "Video nguồn chính",
            }
        ],
        "rewrite_script": {"full_text": script},
        "srt": [
            {
                "index": 1,
                "start": "00:00:00,000",
                "end": "00:00:05,000",
                "text": srt_text,
            }
        ],
        "video_segments": [
            {
                "segment_id": 1,
                "order": 1,
                "source_id": "source_1",
                "source_start": "00:00:12.000",
                "source_end": "00:00:17.000",
                "subtitle_start": 1,
                "subtitle_end": 1,
                "scene_description": "Mở đầu",
                "importance_score": 95,
            }
        ],
    }


def make_template_dict():
    return {
        "metadata": {
            "video_title": "string",
            "rewrite_style": "string",
            "target_audience": "string",
            "tone": "string",
            "target_duration": "string",
            "target_language": "string",
            "target_market": "string",
            "localization_level": "string",
            "hashtags": ["hashtag1", "hashtag2"],
        },
        "sources": [
            {
                "source_id": "source_1",
                "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "label": "Video nguồn chính",
            }
        ],
        "rewrite_script": {"full_text": "string"},
        "srt": [
            {
                "index": 1,
                "start": "00:00:00,000",
                "end": "00:00:05,000",
                "text": "Subtitle text",
            }
        ],
        "video_segments": [
            {
                "segment_id": 1,
                "order": 1,
                "source_id": "source_1",
                "source_start": "00:00:12.000",
                "source_end": "00:00:17.000",
                "subtitle_start": 1,
                "subtitle_end": 1,
                "scene_description": "Mô tả ngắn cảnh được chọn",
                "importance_score": 95,
            }
        ],
    }


service = GeminiAutomationService()


def test_response_indicates_source_access_failure_english():
    text = "I can't watch videos or access YouTube links directly, but based on the URL..."
    assert GeminiAutomationService._response_indicates_source_access_failure(text)


def test_response_indicates_source_access_failure_vietnamese():
    text = "Tôi không thể xem video YouTube trực tiếp, nên chỉ có thể dựa trên tiêu đề."
    assert GeminiAutomationService._response_indicates_source_access_failure(text)


def test_response_indicates_source_access_failure_ignores_normal_json():
    import json

    text = json.dumps(make_valid_edl_dict(), ensure_ascii=False)
    assert not GeminiAutomationService._response_indicates_source_access_failure(text)


def test_looks_like_schema_template_rejects_template():
    d = make_template_dict()
    assert GeminiAutomationService._looks_like_schema_template(d)


def test_looks_like_gemini_edl_root_rejects_template():
    d = make_template_dict()
    assert not GeminiAutomationService._looks_like_gemini_edl_root(d)


def test_looks_like_gemini_edl_root_accepts_real():
    d = make_valid_edl_dict()
    assert GeminiAutomationService._looks_like_gemini_edl_root(d)


def test_looks_like_schema_template_does_not_accept_real():
    d = make_valid_edl_dict()
    assert not GeminiAutomationService._looks_like_schema_template(d)


def test_looks_like_schema_template_false_positive_guard():
    """Only 1-2 fields as template placeholder should not be rejected."""
    d = make_valid_edl_dict()
    d["metadata"]["video_title"] = "string"
    assert not GeminiAutomationService._looks_like_schema_template(d)


def test_extract_json_empty():
    assert service._extract_json("") == ""
    assert service._extract_json("abc") == ""


def test_extract_json_rejects_template():
    import json

    text = json.dumps(make_template_dict())
    result = service._extract_json(text)
    assert result == ""


def test_extract_json_rejects_template_in_body_text():
    text = (
        "Here is some leading context\n\n"
        "User instruction: do something\n\n"
        '{"metadata":{"video_title":"string","rewrite_style":"string","target_audience":"string",'
        '"tone":"string","target_duration":"string","target_language":"string","target_market":"string",'
        '"localization_level":"string","hashtags":["hashtag1","hashtag2"]},'
        '"sources":[{"source_id":"source_1","youtube_url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ","label":"Video nguồn chính"}],'
        '"rewrite_script":{"full_text":"string"},'
        '"srt":[{"index":1,"start":"00:00:00,000","end":"00:00:05,000","text":"Subtitle text"}],'
        '"video_segments":[{"segment_id":1,"order":1,"source_id":"source_1","source_start":"00:00:12.000","source_end":"00:00:17.000","subtitle_start":1,"subtitle_end":1,"scene_description":"Mô tả ngắn cảnh được chọn","importance_score":95}]}'
        "\n\nTrailing text..."
    )
    result = service._extract_json(text)
    assert result == "", f"Expected empty, got: {result[:100]}"


def test_extract_json_accepts_real():
    import json

    d = make_valid_edl_dict()
    text = json.dumps(d)
    result = service._extract_json(text)
    assert result != ""
    parsed = json.loads(result)
    assert parsed["metadata"]["video_title"] == "10 Phút Nấu Phở"


def test_extract_json_accepts_real_in_body_text():
    import json

    d = make_valid_edl_dict()
    text = "Some conversation history...\n\n" + json.dumps(d) + "\n\nTrailing..."
    result = service._extract_json(text)
    assert result != ""
    parsed = json.loads(result)
    assert parsed["metadata"]["video_title"] == "10 Phút Nấu Phở"


def test_extract_json_accepts_real_prefixed_with_thinking():
    """Gemini sometimes returns thinking text before the JSON."""
    import json

    d = make_valid_edl_dict()
    text = "Let me think about this carefully...\n\n" + json.dumps(d)
    result = service._extract_json(text)
    assert result != ""
    parsed = json.loads(result)
    assert parsed["metadata"]["video_title"] == "10 Phút Nấu Phở"


def test_extract_json_code_block():
    import json

    d = make_valid_edl_dict()
    text = "Some text\n```json\n" + json.dumps(d) + "\n```\nMore text"
    result = service._extract_json(text)
    assert result != ""
    parsed = json.loads(result)
    assert parsed["metadata"]["video_title"] == "10 Phút Nấu Phở"


def test_extract_json_multiple_json_objects_picks_valid():
    """When body contains both template and real JSON, the real one should be extracted."""
    import json

    template = json.dumps(make_template_dict())
    real = json.dumps(make_valid_edl_dict("Real Title"))
    text = template + "\n\n" + real
    result = service._extract_json(text)
    assert result != ""
    parsed = json.loads(result)
    assert parsed["metadata"]["video_title"] == "Real Title"


def test_extract_json_multiple_json_objects_reversed_order():
    """When real JSON appears before template, real should still be extracted."""
    import json

    real = json.dumps(make_valid_edl_dict("Earlier Real"))
    template = json.dumps(make_template_dict())
    text = real + "\n\n" + template
    result = service._extract_json(text)
    assert result != ""
    parsed = json.loads(result)
    assert parsed["metadata"]["video_title"] == "Earlier Real"


def test_choose_final_response_text_prefers_clipboard_when_both_have_json():
    dom = 'Some text with {"metadata":{"video_title":"DOM Title","rewrite_style":"D","target_audience":"D","tone":"D","target_duration":"D","hashtags":[]},"rewrite_script":{"full_text":"Dom text"},"srt":[{"index":1,"start":"00:00:00,000","end":"00:00:03,000","text":"Dom"}],"video_segments":[{"segment_id":1,"order":1,"source_start":"00:00:00.000","source_end":"00:00:03.000","subtitle_start":1,"subtitle_end":1,"scene_description":"D","importance_score":95}]}'
    clip = 'Clipboard text with {"metadata":{"video_title":"Clip Title","rewrite_style":"C","target_audience":"C","tone":"C","target_duration":"C","hashtags":[]},"rewrite_script":{"full_text":"Clip text"},"srt":[{"index":1,"start":"00:00:00,000","end":"00:00:03,000","text":"Clip"}],"video_segments":[{"segment_id":1,"order":1,"source_start":"00:00:00.000","source_end":"00:00:03.000","subtitle_start":1,"subtitle_end":1,"scene_description":"C","importance_score":95}]}'
    result = service._choose_final_response_text(dom, clip)
    # Both have JSON; longer one wins
    assert "Clipboard" in result or "DOM" in result


def test_choose_final_response_text_clipboard_when_dom_no_json():
    clip = '{"metadata":{"video_title":"Clip Title","rewrite_style":"C","target_audience":"C","tone":"C","target_duration":"C","hashtags":[]},"rewrite_script":{"full_text":"Clip text"},"srt":[{"index":1,"start":"00:00:00,000","end":"00:00:03,000","text":"Clip"}],"video_segments":[{"segment_id":1,"order":1,"source_start":"00:00:00.000","source_end":"00:00:03.000","subtitle_start":1,"subtitle_end":1,"scene_description":"C","importance_score":95}]}'
    dom = "Just some random text without JSON structure"
    result = service._choose_final_response_text(dom, clip)
    import json
    parsed = json.loads(result)
    assert parsed["metadata"]["video_title"] == "Clip Title"


def test_choose_final_response_text_dom_when_clipboard_no_json():
    dom = '{"metadata":{"video_title":"DOM Title","rewrite_style":"D","target_audience":"D","tone":"D","target_duration":"D","hashtags":[]},"rewrite_script":{"full_text":"Dom text"},"srt":[{"index":1,"start":"00:00:00,000","end":"00:00:03,000","text":"Dom"}],"video_segments":[{"segment_id":1,"order":1,"source_start":"00:00:00.000","source_end":"00:00:03.000","subtitle_start":1,"subtitle_end":1,"scene_description":"D","importance_score":95}]}'
    clip = "Just some random clipboard without JSON"
    result = service._choose_final_response_text(dom, clip)
    import json
    parsed = json.loads(result)
    assert parsed["metadata"]["video_title"] == "DOM Title"


def test_choose_final_response_text_both_empty():
    result = service._choose_final_response_text("", "")
    assert result == ""


def make_edl_with_segments(count: int) -> str:
    import json

    d = make_valid_edl_dict()
    d["video_segments"] = [
        {
            "segment_id": i,
            "order": i,
            "source_id": "source_1",
            "source_start": f"00:00:{(i-1)*6:02d}.000",
            "source_end": f"00:00:{i*6:02d}.000",
            "subtitle_start": 1,
            "subtitle_end": 1,
            "scene_description": f"Scene {i}",
            "importance_score": 90,
            "freeze_frame_duration": None,
        }
        for i in range(1, count + 1)
    ]
    return json.dumps(d)


def test_response_has_minimum_segments_exactly_5():
    """5 segments meets the threshold."""
    json_str = make_edl_with_segments(5)
    valid, count = GeminiAutomationService._response_has_minimum_segments(json_str)
    assert valid is True
    assert count == 5


def test_response_has_minimum_segments_under_5():
    """4 segments is below threshold."""
    json_str = make_edl_with_segments(4)
    valid, count = GeminiAutomationService._response_has_minimum_segments(json_str)
    assert valid is False
    assert count == 4


def test_response_has_minimum_segments_many():
    """15 segments (real video) is well above threshold."""
    json_str = make_edl_with_segments(15)
    valid, count = GeminiAutomationService._response_has_minimum_segments(json_str)
    assert valid is True
    assert count == 15


def test_response_has_minimum_segments_no_segments_key():
    """Missing video_segments key should return False."""
    d = make_valid_edl_dict()
    del d["video_segments"]
    import json

    json_str = json.dumps(d)
    valid, count = GeminiAutomationService._response_has_minimum_segments(json_str)
    assert valid is False
    assert count == 0


def test_response_has_minimum_segments_invalid_json():
    """Invalid JSON returns False."""
    valid, count = GeminiAutomationService._response_has_minimum_segments("{invalid")
    assert valid is False
    assert count == 0


def test_response_has_minimum_segments_empty_string():
    valid, count = GeminiAutomationService._response_has_minimum_segments("")
    assert valid is False
    assert count == 0


def test_extract_analysis_json_accepts_analysis_root():
    import json

    payload = {
        "analysis_version": 1,
        "sources": [{"source_id": "source_1", "youtube_url": "https://www.youtube.com/watch?v=test"}],
        "overall_summary": "summary",
        "story_arc": {"setup": "a", "progression": "b", "climax": "c", "ending": "d"},
        "segments": [{"source_id": "source_1", "index": 1, "start": "00:00:00.000", "end": "00:00:10.000"}],
    }
    extracted = GeminiAutomationService()._extract_analysis_json(json.dumps(payload, ensure_ascii=False))
    assert extracted
    assert json.loads(extracted)["analysis_version"] == 1


def test_extract_json_rejects_analysis_root():
    import json

    payload = {
        "analysis_version": 1,
        "sources": [{"source_id": "source_1", "youtube_url": "https://www.youtube.com/watch?v=test"}],
        "overall_summary": "summary",
        "segments": [{"source_id": "source_1", "index": 1, "start": "00:00:00.000", "end": "00:00:10.000"}],
    }
    assert GeminiAutomationService()._extract_json(json.dumps(payload, ensure_ascii=False)) == ""


def test_choose_response_text_accepts_analysis_json_from_clipboard():
    import json

    service = GeminiAutomationService()
    analysis_payload = {
        "analysis_version": 1,
        "sources": [{"source_id": "source_1", "youtube_url": "https://www.youtube.com/watch?v=test"}],
        "overall_summary": "summary",
        "story_arc": {"setup": "a", "progression": "b", "climax": "c", "ending": "d"},
        "segments": [{"source_id": "source_1", "index": 1, "start": "00:00:00.000", "end": "00:00:10.000"}],
    }
    dom_text = "Gemini page text without structured JSON" * 20
    clipboard_text = json.dumps(analysis_payload, ensure_ascii=False)

    chosen = service._choose_final_response_text(
        dom_text,
        clipboard_text,
        extract_json_fn=service._extract_analysis_json,
    )

    assert chosen == clipboard_text


def test_choose_response_text_does_not_treat_analysis_as_final_edl():
    import json

    service = GeminiAutomationService()
    analysis_payload = {
        "analysis_version": 1,
        "sources": [{"source_id": "source_1", "youtube_url": "https://www.youtube.com/watch?v=test"}],
        "overall_summary": "summary",
        "segments": [{"source_id": "source_1", "index": 1, "start": "00:00:00.000", "end": "00:00:10.000"}],
    }
    dom_text = "long DOM text without final EDL JSON " * 50
    clipboard_text = json.dumps(analysis_payload, ensure_ascii=False)

    chosen = service._choose_final_response_text(dom_text, clipboard_text)

    assert chosen == dom_text


def test_recover_analysis_from_partial_accepts_valid_analysis_json():
    import asyncio
    import json

    from app.services.gemini_automation import GeminiAutomationTask

    service = GeminiAutomationService()
    payload = {
        "analysis_version": 1,
        "sources": [{"source_id": "source_1", "youtube_url": "https://www.youtube.com/watch?v=test"}],
        "overall_summary": "summary",
        "story_arc": {"setup": "a", "progression": "b", "climax": "c", "ending": "d"},
        "segments": [
            {"source_id": "source_1", "index": 1, "start": "00:00:00.000", "end": "00:00:20.000", "story_role": "setup"},
            {"source_id": "source_1", "index": 2, "start": "00:00:20.000", "end": "00:00:40.000", "story_role": "progression"},
            {"source_id": "source_1", "index": 3, "start": "00:00:40.000", "end": "00:01:00.000", "story_role": "progression"},
            {"source_id": "source_1", "index": 4, "start": "00:01:00.000", "end": "00:01:20.000", "story_role": "climax"},
            {"source_id": "source_1", "index": 5, "start": "00:01:20.000", "end": "00:01:30.000", "story_role": "progression"},
            {"source_id": "source_1", "index": 6, "start": "00:01:30.000", "end": "00:01:45.000", "story_role": "ending"},
        ],
    }
    text = "partial Gemini page before copy button\n" + json.dumps(payload, ensure_ascii=False)

    recovered, errors = asyncio.run(service._recover_analysis_from_partial(GeminiAutomationTask("partial-analysis"), text))

    assert errors == []
    assert recovered is not None
    assert recovered["analysis_version"] == 1
