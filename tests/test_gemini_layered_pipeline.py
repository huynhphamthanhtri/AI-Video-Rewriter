import pytest

from app.services.gemini_layered_pipeline import (
    final_duration_seconds,
    duration_gate,
    merge_final_chunks,
    validate_source_access_payload,
    validate_alignment_audit_payload,
    validate_chapter_analysis_payload,
    validate_coverage_review_payload,
    validate_director_plan_payload,
    validate_edit_strategy_payload,
    validate_final_chunk_payload,
    validate_story_assembly_payload,
    validate_timeline_payload,
)


def test_validate_timeline_payload_accepts_long_source_chapters():
    payload = {
        "timeline_version": 1,
        "source_id": "source_1",
        "youtube_url": "https://www.youtube.com/watch?v=x",
        "estimated_duration": "00:40:00.000",
        "chapters": [
            {"chapter_index": 1, "start": "00:00:00.000", "end": "00:05:00.000", "story_role": "setup", "summary": "setup", "analysis_instruction": "analyze setup"},
            {"chapter_index": 2, "start": "00:05:00.000", "end": "00:10:00.000", "story_role": "progression", "summary": "progress", "analysis_instruction": "analyze progress"},
            {"chapter_index": 3, "start": "00:10:00.000", "end": "00:15:00.000", "story_role": "progression", "summary": "progress", "analysis_instruction": "analyze progress"},
            {"chapter_index": 4, "start": "00:15:00.000", "end": "00:25:00.000", "story_role": "context", "summary": "context", "analysis_instruction": "analyze context"},
            {"chapter_index": 5, "start": "00:25:00.000", "end": "00:35:00.000", "story_role": "climax", "summary": "climax", "analysis_instruction": "analyze climax"},
            {"chapter_index": 6, "start": "00:35:00.000", "end": "00:40:00.000", "story_role": "ending", "summary": "ending", "analysis_instruction": "analyze ending"},
        ],
        "quality_notes": [],
    }
    valid, errors, fixed = validate_timeline_payload(payload)
    assert valid, errors
    assert fixed is payload


def test_validate_chapter_analysis_rejects_outside_beat():
    payload = {
        "chapter_analysis_version": 1,
        "source_id": "source_1",
        "chapter_index": 1,
        "chapter_start": "00:00:00.000",
        "chapter_end": "00:01:00.000",
        "beats": [{"beat_index": 1, "start": "00:02:00.000", "end": "00:02:05.000", "visual_action": "man cuts wood", "what_changes_on_screen": "wood splits"}],
    }
    valid, errors, _ = validate_chapter_analysis_payload(payload, {"chapter_index": 1})
    assert not valid
    assert any("outside" in error for error in errors)


def test_validate_strategy_and_assembly():
    strategy = {
        "edit_strategy_version": 1,
        "recommended_duration_seconds": 120,
        "min_acceptable_duration_seconds": 90,
        "max_acceptable_duration_seconds": 180,
        "strategy_summary": "make a complete remake",
        "chapter_priorities": [{"chapter_index": 1, "priority": "high", "reason": "hook", "suggested_screen_time_seconds": 40}],
    }
    assert validate_edit_strategy_payload(strategy)[0]
    analyses = [{"chapter_index": 1, "beats": [{"beat_index": 1}]}, {"chapter_index": 2, "beats": [{"beat_index": 1}]}]
    assembly = {
        "assembly_version": 1,
        "target_duration_seconds": 120,
        "selected_beats": [
            {"chapter_index": 1, "beat_index": 1, "voiceover_intent": "open", "visual_requirement": "show the hook", "estimated_screen_time_seconds": 50},
            {"chapter_index": 2, "beat_index": 1, "voiceover_intent": "pay off", "visual_requirement": "show result", "estimated_screen_time_seconds": 50},
        ],
    }
    valid, errors, _ = validate_story_assembly_payload(assembly, analyses, strategy)
    assert valid, errors


def test_validate_director_plan_combines_strategy_and_selection():
    analyses = [{"chapter_index": 1, "beats": [{"beat_index": 1}]}, {"chapter_index": 2, "beats": [{"beat_index": 1}]}]
    payload = {
        "director_plan_version": 1,
        "coverage_assessment": {"passed": True, "overall_assessment": "enough", "missing_context": [], "important_story_threads": []},
        "edit_strategy": {"recommended_duration_seconds": 120, "min_acceptable_duration_seconds": 90, "max_acceptable_duration_seconds": 180, "strategy_summary": "complete", "pacing_style": "steady", "selection_principles": ["keep payoff"]},
        "selected_beats": [
            {"selection_index": 1, "chapter_index": 1, "beat_index": 1, "story_purpose": "opening", "voiceover_intent": "open", "visual_requirement": "show setup", "estimated_screen_time_seconds": 40},
            {"selection_index": 2, "chapter_index": 2, "beat_index": 1, "story_purpose": "ending", "voiceover_intent": "payoff", "visual_requirement": "show result", "estimated_screen_time_seconds": 50},
        ],
        "story_flow": ["opening", "ending"],
    }
    valid, errors, _ = validate_director_plan_payload(payload, analyses)
    assert valid, errors


def test_validate_review_chunk_and_audit():
    assert validate_coverage_review_payload({"coverage_review_version": 1, "passed": True, "overall_assessment": "enough", "coverage_quality": "acceptable", "missing_or_weak_chapters": []})[0]
    chunk = {
        "chunk_version": 1,
        "chunk_name": "opening",
        "rewrite_text": "Mở đầu câu chuyện.",
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:04,000", "text": "Mở đầu câu chuyện."}],
        "video_segments": [{"source_id": "source_1", "source_start": "00:00:10.000", "source_end": "00:00:14.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Người dẫn đang dựng trại", "importance_score": 90}],
    }
    assert validate_final_chunk_payload(chunk)[0]
    assert validate_alignment_audit_payload({"alignment_audit_version": 1, "passed": True, "final_recommendation": "render", "issues": []})[0]


def test_merge_final_chunks_renumbers_and_offsets():
    chunks = [
        {
            "chunk_version": 1,
            "chunk_name": "opening",
            "rewrite_text": "Một.",
            "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:04,000", "text": "Một."}],
            "video_segments": [{"source_id": "source_1", "source_start": "00:00:10.000", "source_end": "00:00:14.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Cảnh một", "importance_score": 90}],
        },
        {
            "chunk_version": 1,
            "chunk_name": "ending",
            "rewrite_text": "Hai.",
            "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Hai."}],
            "video_segments": [{"source_id": "source_1", "source_start": "00:01:10.000", "source_end": "00:01:13.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Cảnh hai", "importance_score": 88}],
        },
    ]
    merged = merge_final_chunks(chunks, [{"source_id": "source_1", "youtube_url": "https://example.test"}], "Tiếng Việt")
    assert [item["index"] for item in merged["srt"]] == [1, 2]
    assert merged["srt"][1]["start"] == "00:00:04,000"
    assert merged["video_segments"][1]["subtitle_start"] == 2
    assert final_duration_seconds(merged) == 7


def test_duration_gate_rejects_too_short_final():
    payload = {"srt": [{"end": "00:02:00,000"}]}
    ok, info = duration_gate(payload, {"min_acceptable_duration_seconds": 300, "recommended_duration_seconds": 480})
    assert not ok
    assert info["short_by_seconds"] > 0


def test_validate_source_access_payload():
    valid, errors, _ = validate_source_access_payload({"source_access_version": 1, "can_access_video": True, "reason": "visible"})
    assert valid, errors


def test_merge_final_chunks_rejects_missing_subtitle_reference():
    chunk = {
        "chunk_version": 1,
        "chunk_name": "bad_chunk",
        "rewrite_text": "Một.",
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:04,000", "text": "Một."}],
        "video_segments": [{"source_id": "source_1", "source_start": "00:00:10.000", "source_end": "00:00:14.000", "subtitle_start": 9, "subtitle_end": 9, "scene_description": "Cảnh lỗi", "importance_score": 90}],
    }
    with pytest.raises(ValueError, match="subtitle range"):
        merge_final_chunks([chunk], [{"source_id": "source_1"}], "Tiếng Việt")


def test_merge_final_chunks_rejects_missing_subtitle_end():
    chunk = {
        "chunk_version": 1,
        "chunk_name": "bad_chunk",
        "rewrite_text": "Một.",
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:04,000", "text": "Một."}],
        "video_segments": [{"source_id": "source_1", "source_start": "00:00:10.000", "source_end": "00:00:14.000", "subtitle_start": 1, "subtitle_end": 9, "scene_description": "Cảnh lỗi", "importance_score": 90}],
    }
    with pytest.raises(ValueError, match="subtitle range"):
        merge_final_chunks([chunk], [{"source_id": "source_1"}], "Tiếng Việt")


def test_merge_final_chunks_accepts_valid_references():
    chunk = {
        "chunk_version": 1,
        "chunk_name": "good",
        "rewrite_text": "Một.",
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:04,000", "text": "Một."}],
        "video_segments": [{"source_id": "source_1", "source_start": "00:00:10.000", "source_end": "00:00:14.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Cảnh một", "importance_score": 90}],
    }
    merged = merge_final_chunks([chunk], [{"source_id": "source_1"}], "Tiếng Việt")
    assert merged["video_segments"][0]["subtitle_start"] == 1
    assert merged["video_segments"][0]["subtitle_end"] == 1


def test_merge_final_chunks_canonicalizes_vietnamese_label():
    chunk = {
        "chunk_version": 1,
        "chunk_name": "chunk_1",
        "rewrite_text": "Một.",
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:04,000", "text": "Một."}],
        "video_segments": [{"source_id": "source_1", "source_start": "00:00:10.000", "source_end": "00:00:14.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Cảnh một", "importance_score": 90}],
    }
    merged = merge_final_chunks([chunk], [{"source_id": "source_1"}], "Ti?ng Vi?t")
    assert merged["metadata"]["target_language"] == "Tiếng Việt"
    assert merged["metadata"]["target_market"] == "Việt Nam"
