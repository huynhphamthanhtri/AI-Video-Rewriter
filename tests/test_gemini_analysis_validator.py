from app.services.gemini_analysis_validator import validate_analysis_payload


def _segment(index: int, start_minute: int, role: str = "progression") -> dict:
    return {
        "source_id": "source_1",
        "index": index,
        "start": f"00:{start_minute:02d}:00.000",
        "end": f"00:{start_minute:02d}:30.000",
        "label": f"Segment {index}",
        "description": "Detailed source moment",
        "story_role": role,
        "visual_value": 80,
        "story_importance": 80,
        "must_keep": index in {1, 10},
        "usable_for_hook": index == 1,
    }


def _valid_payload() -> dict:
    roles = ["setup", "progression", "progression", "context", "progression", "progression", "context", "progression", "climax", "ending"]
    return {
        "analysis_version": 1,
        "sources": [{"source_id": "source_1", "youtube_url": "https://www.youtube.com/watch?v=test", "estimated_duration": "00:09:30.000", "source_title": "Source"}],
        "overall_summary": "Full video analysis",
        "story_arc": {"setup": "setup", "progression": "progression", "climax": "climax", "ending": "ending"},
        "segments": [_segment(i + 1, i, role) for i, role in enumerate(roles)],
        "must_keep_moments": [{"source_id": "source_1", "timestamp": "00:00:00.000", "reason": "hook"}],
        "weak_or_repetitive_parts": [],
        "quality_notes": [],
    }


def test_valid_analysis_payload_passes():
    valid, errors, fixed = validate_analysis_payload(_valid_payload())
    assert valid
    assert errors == []
    assert fixed is not None


def test_too_few_segments_fails():
    payload = _valid_payload()
    payload["segments"] = payload["segments"][:4]
    valid, errors, _ = validate_analysis_payload(payload)
    assert not valid
    assert any("at least" in error for error in errors)


def test_medium_video_allows_seven_segments_with_full_story_roles():
    payload = _valid_payload()
    roles = ["setup", "progression", "context", "progression", "climax", "progression", "ending"]
    payload["segments"] = [_segment(i + 1, i, role) for i, role in enumerate(roles)]
    for index, segment in enumerate(payload["segments"]):
        start = index * 40
        end = start + 35
        segment["start"] = f"00:{start // 60:02d}:{start % 60:02d}.000"
        segment["end"] = f"00:{end // 60:02d}:{end % 60:02d}.000"

    valid, errors, fixed = validate_analysis_payload(payload)

    assert valid, errors
    assert fixed is not None


def test_under_six_minutes_allows_nine_segments():
    payload = _valid_payload()
    payload["segments"] = payload["segments"][:9]
    payload["segments"][0]["story_role"] = "setup"
    payload["segments"][-1]["story_role"] = "ending"
    for index, segment in enumerate(payload["segments"]):
        start = index * 38
        end = start + 35
        segment["start"] = f"00:{start // 60:02d}:{start % 60:02d}.000"
        segment["end"] = f"00:{end // 60:02d}:{end % 60:02d}.000"

    valid, errors, fixed = validate_analysis_payload(payload)

    assert valid, errors
    assert fixed is not None


def test_long_video_allows_ten_segments_with_full_story_roles():
    payload = _valid_payload()
    payload["segments"][-1]["end"] = "00:10:01.000"

    valid, errors, fixed = validate_analysis_payload(payload)

    assert valid, errors
    assert fixed is not None


def test_long_video_allows_eleven_segments_with_full_story_roles():
    payload = _valid_payload()
    payload["segments"].append(_segment(11, 15, "context"))
    payload["segments"][-1]["end"] = "00:16:35.000"

    valid, errors, fixed = validate_analysis_payload(payload)

    assert valid, errors
    assert fixed is not None


def test_long_video_rejects_nine_segments():
    payload = _valid_payload()
    payload["segments"] = payload["segments"][:9]
    payload["segments"][-1]["story_role"] = "ending"
    payload["segments"][-1]["end"] = "00:16:30.000"

    valid, errors, _ = validate_analysis_payload(payload)

    assert not valid
    assert any("at least 10" in error for error in errors)


def test_markdown_url_fails():
    payload = _valid_payload()
    payload["sources"][0]["youtube_url"] = "[https://www.youtube.com/watch?v=test](https://www.youtube.com/watch?v=test)"
    valid, errors, _ = validate_analysis_payload(payload)
    assert not valid
    assert any("Markdown" in error for error in errors)


def test_missing_climax_or_ending_fails():
    payload = _valid_payload()
    for segment in payload["segments"]:
        segment["story_role"] = "progression"
    payload["segments"][0]["story_role"] = "setup"
    valid, errors, _ = validate_analysis_payload(payload)
    assert not valid
    assert any("climax or ending" in error for error in errors)


def test_invalid_timestamp_fails():
    payload = _valid_payload()
    payload["segments"][0]["start"] = "00:00:00,000"
    valid, errors, _ = validate_analysis_payload(payload)
    assert not valid
    assert any("HH:MM:SS.mmm" in error for error in errors)


def test_v2_normalizes_common_story_role_aliases():
    payload = {
        "analysis_version": 2,
        "source_access": {"can_access_video": True, "reason": "ok"},
        "source": {"youtube_url": "https://www.youtube.com/watch?v=test", "estimated_duration": "00:04:30.000"},
        "story_summary": {"overview": "summary"},
        "scene_beats": [
            {"beat_id": "b1", "start": "00:00:00.000", "end": "00:00:20.000", "story_role": "introduction", "visual_description": "open", "dialogue_or_narration": "intro"},
            {"beat_id": "b2", "start": "00:00:20.000", "end": "00:01:00.000", "story_role": "rising action", "visual_description": "build", "dialogue_or_narration": "build"},
            {"beat_id": "b3", "start": "00:01:00.000", "end": "00:02:00.000", "story_role": "final reveal", "visual_description": "result", "dialogue_or_narration": "result"},
            {"beat_id": "b4", "start": "00:02:00.000", "end": "00:03:00.000", "story_role": "conclusion", "visual_description": "end", "dialogue_or_narration": "end"},
            {"beat_id": "b5", "start": "00:03:00.000", "end": "00:04:00.000", "story_role": "background", "visual_description": "context", "dialogue_or_narration": "context"},
            {"beat_id": "b6", "start": "00:04:00.000", "end": "00:05:00.000", "story_role": "peak", "visual_description": "peak", "dialogue_or_narration": "peak"},
            {"beat_id": "b7", "start": "00:05:00.000", "end": "00:05:20.000", "story_role": "outro", "visual_description": "outro", "dialogue_or_narration": "outro"},
            {"beat_id": "b8", "start": "00:05:20.000", "end": "00:05:40.000", "story_role": "action", "visual_description": "action beat", "dialogue_or_narration": "action"},
            {"beat_id": "b9", "start": "00:05:40.000", "end": "00:06:00.000", "story_role": "emotion", "visual_description": "emotion beat", "dialogue_or_narration": "emotion"},
        ],
    }

    valid, errors, fixed = validate_analysis_payload(payload)

    assert valid, errors
    assert fixed["scene_beats"][0]["story_role"] == "opening"
    assert fixed["scene_beats"][1]["story_role"] == "progression"
    assert fixed["scene_beats"][2]["story_role"] == "payoff"
    assert fixed["scene_beats"][7]["story_role"] == "progression"
    assert fixed["scene_beats"][8]["story_role"] == "context"


def _v2_payload(count: int = 8, duration: str = "00:12:00.000") -> dict:
    roles = ["opening", "setup", "progression", "context", "progression", "climax", "payoff", "ending"]
    beats = []
    for index in range(count):
        start = index * 60
        end = start + 30
        beats.append({
            "beat_id": f"b{index + 1:03d}",
            "start": f"00:{start // 60:02d}:{start % 60:02d}.000",
            "end": f"00:{end // 60:02d}:{end % 60:02d}.000",
            "story_role": roles[index % len(roles)],
            "visual_description": "A clear visual moment",
            "dialogue_or_narration": "Narration",
        })
    return {
        "analysis_version": 2,
        "source_access": {"can_access_video": True, "reason": "ok"},
        "source": {"youtube_url": "https://www.youtube.com/watch?v=test", "estimated_duration": duration},
        "story_summary": {"overview": "summary"},
        "scene_beats": beats,
    }


def test_v2_allows_missing_analysis_version_when_scene_beats_exist():
    payload = _v2_payload()
    del payload["analysis_version"]
    valid, errors, fixed = validate_analysis_payload(payload)
    assert valid, errors
    assert fixed["analysis_version"] == 2


def test_v2_converts_story_summary_string_to_object():
    payload = _v2_payload()
    payload["story_summary"] = "A compact summary"
    valid, errors, fixed = validate_analysis_payload(payload)
    assert valid, errors
    assert fixed["story_summary"] == {"overview": "A compact summary"}


def test_v2_fills_missing_dialogue_and_beat_id():
    payload = _v2_payload()
    del payload["scene_beats"][0]["beat_id"]
    del payload["scene_beats"][0]["dialogue_or_narration"]
    valid, errors, fixed = validate_analysis_payload(payload)
    assert valid, errors
    assert fixed["scene_beats"][0]["beat_id"] == "b001"
    assert fixed["scene_beats"][0]["dialogue_or_narration"] == ""


def test_v2_accepts_flexible_estimated_duration():
    for duration in ("00:12:00", "12:00"):
        payload = _v2_payload(duration=duration)
        valid, errors, fixed = validate_analysis_payload(payload)
        assert valid, errors
        assert fixed is not None


def test_v2_long_video_allows_ten_scene_beats():
    payload = _v2_payload(count=10, duration="00:30:00.000")
    payload["scene_beats"][-1]["end"] = "00:25:00.000"
    valid, errors, fixed = validate_analysis_payload(payload)
    assert valid, errors
    assert fixed is not None


def test_v2_late_coverage_allows_if_payoff_present():
    payload = _v2_payload(count=8, duration="00:20:00.000")
    payload["scene_beats"][-1]["end"] = "00:08:00.000"
    payload["scene_beats"][-1]["story_role"] = "payoff"
    valid, errors, fixed = validate_analysis_payload(payload)
    assert valid, errors
    assert fixed is not None


def test_v2_still_rejects_no_source_access():
    payload = _v2_payload()
    payload["source_access"]["can_access_video"] = False
    valid, errors, _ = validate_analysis_payload(payload)
    assert not valid
    assert any("can_access_video" in error for error in errors)


def test_v2_still_rejects_final_edl_fields():
    payload = _v2_payload()
    payload["video_segments"] = []
    valid, errors, _ = validate_analysis_payload(payload)
    assert not valid
    assert any("final EDL" in error for error in errors)


def test_v2_still_rejects_missing_visual_description():
    payload = _v2_payload()
    payload["scene_beats"][0]["visual_description"] = ""
    valid, errors, _ = validate_analysis_payload(payload)
    assert not valid
    assert any("visual_description" in error for error in errors)
