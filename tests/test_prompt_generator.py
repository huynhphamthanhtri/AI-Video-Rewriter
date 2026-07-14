from pydantic import HttpUrl

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.composer import PromptComposer
from app.services.prompt_blocks.validation_block import ValidationBlock
from app.services.prompt_blocks.output_schema_block import OutputSchemaBlock
from app.services.prompt_generator import PromptGenerator


def _req(**overrides) -> PromptGenerateRequest:
    defaults = dict(
        youtube_url=HttpUrl("https://www.youtube.com/watch?v=test"),
        source_mode="single",
        target_language="Tiếng Việt",
        domain="general",
        user_instruction="",
    )
    defaults.update(overrides)
    return PromptGenerateRequest(**defaults)


def test_generate_prompt_contains_rules():
    prompt = PromptGenerator().generate(_req())
    assert "biên kịch remake video" in prompt
    assert "QUY TẮC JSON BẮT BUỘC" in prompt
    assert "STRICT OUTPUT CONTRACT" in prompt
    assert "Schema bắt buộc" in prompt
    assert "Nghiêm cấm bịa nội dung" in prompt
    assert "Tránh video quá dài hoặc quá nguyên bản" in prompt


def test_composer_language_metadata_rule_uses_selected_language():
    result = PromptComposer(_req(target_language="Korean", target_market="Korea")).compose()
    assert 'metadata.target_language MUST be exactly "Korean"' in result
    assert 'metadata.target_market MUST be exactly "Korea"' in result
    assert 'metadata.target_language MUST be exactly "Tiếng Việt"' not in result


def test_generate_analysis_prompt_contains_analysis_schema():
    prompt = PromptGenerator().generate_analysis_prompt(_req())
    assert "PHÂN TÍCH SÂU" in prompt
    assert "PHÂN TÍCH CẢNH VÀ THOẠI" in prompt
    assert '"scene_beats"' in prompt
    assert '"story_summary"' in prompt
    assert "Không viết kịch bản final" in prompt
    assert '"video_segments"' not in prompt


def test_generate_analysis_prompt_requires_detailed_scene_mapping_without_quota():
    prompt = PromptGenerator().generate_analysis_prompt(_req())
    assert "không theo quota" in prompt
    assert "setup" in prompt
    assert "climax" in prompt
    assert "payoff" in prompt
    assert "scene_beats" in prompt
    assert "hành động quan trọng" in prompt
    assert "pass 2" in prompt
    assert "visual_description" in prompt
    assert "must_keep_moments" in prompt
    assert "ít nhất 12 segments" not in prompt
    assert "18-28" not in prompt


def test_generate_story_plan_from_analysis_contains_compact_analysis_json():
    analysis = {
        "analysis_version": 1,
        "sources": [{"source_id": "source_1", "youtube_url": "https://www.youtube.com/watch?v=test"}],
        "overall_summary": "summary",
        "story_arc": {"setup": "setup", "progression": "progression", "climax": "climax", "ending": "ending"},
        "segments": [{"source_id": "source_1", "index": 1, "start": "00:00:00.000", "end": "00:00:10.000", "story_role": "setup"}],
    }
    prompt = PromptGenerator().generate_story_plan_from_analysis(_req(), analysis)
    assert "ANALYSIS_JSON" in prompt
    assert "STORY PLAN" in prompt
    assert "summary" in prompt


def test_generate_final_prompt_from_story_plan_contains_story_plan_and_final_schema():
    story_plan = {
        "plan_version": 1,
        "story_outline": ["summary"],
        "selected_moments": [{"source_id": "source_1", "analysis_index": 1, "timestamp_hint": "00:00:00.000", "purpose": "hook", "voiceover_point": "summary"}],
        "target_structure": {"opening": "open", "middle": "middle", "climax": "climax", "ending": "ending"},
    }
    analysis = {
        "analysis_version": 1,
        "sources": [{"source_id": "source_1", "youtube_url": "https://www.youtube.com/watch?v=test"}],
        "overall_summary": "summary",
        "story_arc": {},
        "segments": [],
    }
    prompt = PromptGenerator().generate_final_prompt_from_story_plan(_req(), analysis, story_plan)
    assert "STORY_PLAN_JSON" in prompt
    assert "summary" in prompt
    assert "STRICT OUTPUT CONTRACT" in prompt
    assert "video_segments" in prompt
    assert "quá 2 giây" in prompt
    assert "VALIDATION CRITICAL" in prompt
    assert "abs(duration_video - duration_srt) > 2 seconds" in prompt
    assert "Do not rely on renderer" in prompt


def test_generate_prompt_multi_source_contains_mapping():
    prompt = PromptGenerator().generate(_req(
        source_mode="multi",
        youtube_urls=[
            HttpUrl("https://www.youtube.com/watch?v=first"),
            HttpUrl("https://www.youtube.com/watch?v=second"),
        ],
    ))
    assert "QUY TẮC NHIỀU NGUỒN" in prompt
    assert "source_1" in prompt
    assert "source_2" in prompt


def test_generate_prompt_single_source_missing_multi_rules():
    prompt = PromptGenerator().generate(_req())
    assert "QUY TẮC NHIỀU NGUỒN" not in prompt


def test_validation_block_contains_json_rules():
    block = ValidationBlock()
    result = block.render(_req())
    assert "QUY TẮC JSON BẮT BUỘC:" in result
    assert "video_segments" in result
    assert "INVALID" in result
    assert "bắt buộc phải có sources[]" in result


def test_validation_block_multi_source_segment_rule():
    block = ValidationBlock()
    result = block.render(_req(source_mode="multi"))
    assert "source_id là bắt buộc" in result
    assert "subtitle_start→subtitle_end" in result


def test_output_schema_block_contains_contract():
    block = OutputSchemaBlock()
    result = block.render(_req())
    assert "STRICT OUTPUT CONTRACT" in result
    assert "MANDATORY RULES" in result
    assert "Extra fields = REJECTED" in result
    assert "Schema bắt buộc" in result
    assert '"importance_score": 95' in result
    assert "Không thêm tts_text" in result
    assert "KHÔNG ĐƯỢC VƯỢT QUÁ 90" in result


def test_output_schema_block_contains_literal_values_block():
    result = OutputSchemaBlock().render(_req())
    assert "FINAL LITERAL VALUES" in result
    assert 'target_language = "Tiếng Việt"' in result
    assert 'target_market = "Việt Nam"' in result
    assert 'INVALID: "00:15,000"' in result
    assert 'Do NOT use: "action", "emotion".' in result


def test_output_schema_block_korean_literal_values():
    result = OutputSchemaBlock().render(_req(target_language="Korean", target_market="Korea"))
    assert 'target_language = "Korean"' in result
    assert 'target_market = "Korea"' in result


def test_output_schema_block_uses_single_braces():
    result = OutputSchemaBlock().render(_req())
    assert "{" in result
    assert "}" in result
    assert "{{" not in result
    assert "}}" not in result


def test_output_schema_block_multi_source_shows_two_items():
    block = OutputSchemaBlock()
    result = block.render(_req(
        source_mode="multi",
        youtube_urls=[
            HttpUrl("https://www.youtube.com/watch?v=a"),
            HttpUrl("https://www.youtube.com/watch?v=b"),
        ],
    ))
    assert '"source_id": "source_1"' in result
    assert '"source_id": "source_2"' in result
    assert "nguồn video 1" in result
    assert "nguồn video 2" in result


def test_output_schema_block_single_source():
    block = OutputSchemaBlock()
    result = block.render(_req())
    assert "Video nguồn chính" in result


def test_output_schema_block_does_not_contain_placeholder_url():
    result = OutputSchemaBlock().render(_req(source_mode="single"))
    assert "watch?v=..." not in result
    assert "dQw4w9WgXcQ" not in result
    assert "watch?v=test" in result


def test_output_schema_block_multi_does_not_contain_placeholder_url():
    result = OutputSchemaBlock().render(_req(source_mode="multi"))
    assert "watch?v=..." not in result
    assert "dQw4w9WgXcQ" not in result
    assert "watch?v=test" in result


def test_output_schema_block_single_uses_input_url():
    result = OutputSchemaBlock().render(_req(
        youtube_url=HttpUrl("https://www.youtube.com/watch?v=Iy3F569-bTY"),
        source_mode="single",
    ))
    assert "dQw4w9WgXcQ" not in result
    assert '"youtube_url": "https://www.youtube.com/watch?v=Iy3F569-bTY"' in result


def test_output_schema_block_rule_16_uses_input_url():
    result = OutputSchemaBlock().render(_req(
        youtube_url=HttpUrl("https://www.youtube.com/watch?v=Iy3F569-bTY"),
        source_mode="single",
    ))
    assert "vd: https://www.youtube.com/watch?v=Iy3F569-bTY" in result


def test_composer_contains_new_prompt_blocks():
    composer = PromptComposer(_req())
    result = composer.compose()
    assert "biên kịch remake video" in result
    assert "Lưu ý: Tuyệt đối không được bịa nội dung nếu không xem được link." in result
    assert "Cắt bỏ các cảnh thừa, cảnh dở." in result
    assert "Cân nhắc để không cắt mạch truyện." in result
    assert "Cảnh không mô tả hết ý của voiceover." in result
    assert "* Lưu ý về khớp cảnh và voiceover" in result
    assert "QUY TẮC JSON BẮT BUỘC:" in result
    assert "STRICT OUTPUT CONTRACT" in result
    assert "Schema bắt buộc" in result
    assert "DOMAIN RULES FOR SPORTS" not in result


def test_composer_omits_old_scene_guidance_blocks():
    result = PromptComposer(_req()).compose()
    assert "Không viết như bản tóm tắt khô" not in result
    assert "Không được kết thúc remake" not in result
    assert "Chỉ được lược bỏ các cảnh chuyển tiếp ít giá trị" not in result
    assert "không có thoại và tình tiết hay" not in result
    assert "Tuy nhiên không được cắt bỏ cảnh tạo bước ngoặt" not in result
    assert "Mỗi segment nên tương ứng" not in result
    assert "Cấu trúc kể chuyện" not in result


def test_composer_contains_user_instruction_fallback_decisions():
    result = PromptComposer(_req()).compose()
    assert '- Độ dài video remake phù hợp nhất nếu trong phần "Hướng dẫn thêm" không yêu cầu độ dài.' in result
    assert '- Giọng kể và sắc thái cảm xúc nếu trong phần "Hướng dẫn thêm" không yêu cầu Giọng kể và sắc thái cảm xúc cụ thể.' in result
    assert '- Nhịp cắt cảnh, tốc độ dẫn chuyện nếu trong phần "Hướng dẫn thêm" không yêu cầu Nhịp cắt cảnh, tốc độ dẫn chuyện cụ thể.' in result


def test_composer_injects_sports_block_when_domain_is_sports():
    composer = PromptComposer(_req(domain="sports"))
    result = composer.compose()
    assert "DOMAIN RULES FOR SPORTS" in result


def test_prompt_contains_strict_output_contract():
    prompt = PromptGenerator().generate(_req())
    assert "STRICT OUTPUT CONTRACT" in prompt
    assert "VIOLATION → TOÀN BỘ RESPONSE BỊ REJECT" in prompt


def test_generate_prompt_contains_priority_order_when_user_instruction():
    prompt = PromptGenerator().generate(_req(user_instruction="Nhấn mạnh góc hài hước"))
    assert "Thứ tự ưu tiên" in prompt
    assert "1. Giữ đúng mạch logic" in prompt


def test_composer_contains_timing_guardrails():
    result = PromptComposer(_req()).compose()
    assert "QUY TẮC BẮT BUỘC" in result
    assert "không được rút ngắn lời dẫn chỉ để vừa khít thời lượng cảnh" in result
    assert "Không viết voiceover kiểu liệt kê mốc cảnh" in result
    assert "tự cân bằng độ dài lời dẫn" in result
    assert "ưu tiên kịch bản tự nhiên" in result
    assert "tràn cảnh" in result
    assert "liên tục theo mạch cảm xúc" in result


def test_composer_contains_self_check_timing():
    result = PromptComposer(_req()).compose()
    assert "TỰ KIỂM TRA THỜI LƯỢNG TỪNG SEGMENT TRƯỚC KHI XUẤT JSON" in result
    assert "không tạo pattern máy móc" in result.lower()
    assert "không theo công thức số từ cứng" in result
    assert "ưu tiên mở rộng source range" in result
    assert "voiceover bị ép nhanh" in result


def test_final_prompts_contain_subtitle_range_hard_check():
    analysis = {"analysis_version": 2, "scene_beats": []}
    story_plan = {"plan_version": 1, "story_outline": [], "selected_moments": []}
    prompts = [
        PromptComposer(_req()).compose(),
        PromptComposer(_req()).compose_from_analysis(analysis),
        PromptComposer(_req()).compose_from_story_plan(analysis, story_plan),
    ]
    for prompt in prompts:
        assert "SUBTITLE RANGE HARD CHECK" in prompt
        assert "subtitle_start MUST be <= subtitle_end" in prompt
        assert 'INVALID: {"subtitle_start": 25, "subtitle_end": 24}' in prompt
        assert "Do NOT return JSON if any video_segments item has subtitle_start > subtitle_end" in prompt


def test_composer_omits_rigid_timing_formulas():
    result = PromptComposer(_req()).compose()
    assert "2.4 đến 3.0 từ/giây" not in result
    assert "3-4 giây" not in result
    assert "7-8 giây" not in result
    assert "quá 1.0 giây" not in result
    assert "3-6 giây" not in result


def test_deep_analysis_final_prompt_discourages_dry_summary():
    result = PromptComposer(_req()).compose_from_analysis({"analysis_version": 1, "segments": []})
    assert "không biến scene_beats thành danh sách tóm tắt khô" in result
    assert "TTS-SAFE SUBTITLE RULE" in result
    assert "Target CPS: 5-8" in result
    assert "Không nén nhiều dữ kiện" in result


def test_deep_analysis_final_prompt_requires_direct_scene_alignment():
    result = PromptComposer(_req()).compose_from_analysis({"analysis_version": 1, "segments": []})
    assert "CÁCH DÙNG ANALYSIS_JSON" in result
    assert "Dùng must_keep_moments[] làm điểm neo timestamp" in result
    assert "Dùng weak_or_repetitive_parts[] để tránh" in result
    assert "QUY TẮC KHỚP CẢNH VỚI LỜI DẪN" in result
    assert "đối chiếu video gốc khi chọn timestamp final" in result
    assert "Không copy nguyên range của analysis segment" in result
    assert "source_start/source_end phải là đoạn hình cụ thể khớp trực tiếp với srt.text" in result
    assert "source_start/source_end nên có thời lượng gần" in result
    assert "Không chọn clip dài chỉ vì analysis segment dài" in result
    assert "Không tự thêm field phụ như source_start_ms" in result
    assert "scene_description phải mô tả đúng visual trong đoạn cắt cuối cùng" in result
    assert "10-18 video_segments" not in result


def test_generate_prompt_includes_priority_when_no_user_instruction():
    prompt = PromptGenerator().generate(_req(user_instruction=""))
    assert "Thứ tự ưu tiên" in prompt
    assert "1. Giữ đúng mạch logic" in prompt


def test_full_layered_prompts_contain_contracts():
    req = _req()
    generator = PromptGenerator()
    timeline = generator.generate_timeline_scout_prompt(req)
    assert "TIMELINE SCOUT" in timeline
    assert "timeline_version" in timeline

    timeline_json = {
        "timeline_version": 1,
        "source_id": "source_1",
        "youtube_url": "https://www.youtube.com/watch?v=x",
        "chapters": [{"chapter_index": 1, "start": "00:00:00.000", "end": "00:01:00.000", "story_role": "setup", "summary": "setup", "analysis_instruction": "analyze"}],
    }
    chapter = generator.generate_chapter_analysis_prompt(req, timeline_json, timeline_json["chapters"][0])
    assert "CHAPTER ANALYSIS" in chapter
    assert "chapter_analysis_version" in chapter

    analysis = {"chapter_index": 1, "beats": [{"beat_index": 1, "visual_action": "action"}]}
    strategy = {"edit_strategy_version": 1, "recommended_duration_seconds": 60, "min_acceptable_duration_seconds": 45, "max_acceptable_duration_seconds": 90, "strategy_summary": "summary", "chapter_priorities": []}
    chunk = generator.generate_final_chunk_prompt(req, "opening", [{"chapter_index": 1, "beat_index": 1}], [analysis], strategy)
    assert "FINAL EDL CHUNK" in chunk
    assert "chunk_version" in chunk

    director = generator.generate_director_plan_prompt(req, timeline_json, [analysis])
    assert "DIRECTOR PLAN" in director
    assert "director_plan_version" in director
    assert "BEAT_CATALOG_COMPACT" in director

    audit = generator.generate_compact_alignment_audit_prompt(req, {"srt": [], "video_segments": []}, {"director_plan_version": 1})
    assert "COMPACT ALIGNMENT AUDIT" in audit
    assert "DIRECTOR_PLAN_JSON" in audit
