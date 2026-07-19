from pydantic import HttpUrl

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.output_schema_block import OutputSchemaBlock
from app.services.prompt_blocks.validation_block import ValidationBlock
from app.services.prompt_generator import PromptGenerator


def _req(**overrides) -> PromptGenerateRequest:
    defaults = dict(
        youtube_url=HttpUrl("https://www.youtube.com/watch?v=test"),
        source_mode="single",
        target_language="Tiếng Việt",
        target_market="Việt Nam",
        domain="general",
        user_instruction="",
    )
    defaults.update(overrides)
    return PromptGenerateRequest(**defaults)


def test_generate_prompt_uses_verified_remake_one_shot():
    prompt = PromptGenerator().generate(_req())
    assert "SIMPLE EDITOR — VERIFIED REMAKE VIDEO ONE-SHOT" in prompt
    assert "NGUYÊN TẮC XÁC MINH NGUỒN" in prompt
    assert "MỤC TIÊU SÁNG TẠO" in prompt
    assert "QUY TẮC TIMING VÀ VOICEOVER" in prompt
    assert "TÍNH NHẤT QUÁN GIỮA CÁC PHẦN" in prompt
    assert "ĐỊNH DẠNG TIMESTAMP" in prompt
    assert "OUTPUT CONTRACT" in prompt
    assert "SCHEMA BẮT BUỘC" in prompt
    assert "FINAL SELF-CHECK" in prompt


def test_generate_prompt_section_two_is_short():
    prompt = PromptGenerator().generate(_req())
    assert "Video remake phải có một câu chuyện hoàn chỉnh. Bám sát nội dung video gốc." in prompt
    assert "Hình ảnh khiến người xem" not in prompt
    assert "Ưu tiên các cảnh có" not in prompt


def test_generate_prompt_keeps_render_schema_contract():
    prompt = PromptGenerator().generate(_req())
    for key in ["metadata", "sources", "rewrite_script", "srt", "video_segments"]:
        assert key in prompt
    assert '"video_title"' in prompt
    assert '"rewrite_style"' in prompt
    assert '"segment_id"' in prompt
    assert '"order"' in prompt
    assert '"source_start"' in prompt
    assert '"source_end"' in prompt
    assert '"subtitle_start"' in prompt
    assert '"subtitle_end"' in prompt
    assert '"scene_description"' in prompt


def test_generate_prompt_no_unused_fields_in_schema():
    prompt = PromptGenerator().generate(_req())
    forbidden = [
        "scene_beats",
        "story_role",
        "output_start",
        "output_end",
        "selection_reason",
        "editing_instruction",
        "audio_instruction",
        "text_overlay",
        "transition",
        "playback_speed",
        "analysis_status",
        "analysis_note",
        "opening_strategy",
    ]
    for field in forbidden:
        assert field not in prompt or f"# {field}" in prompt or "Không được" in prompt


def test_generate_prompt_has_verification_rules():
    prompt = PromptGenerator().generate(_req())
    assert "XÁC MINH NGUỒN" in prompt
    assert "không thể truy cập hoặc xác minh" in prompt
    assert "rewrite_script.full_text phải là chuỗi rỗng" in prompt
    assert "srt và video_segments phải là mảng rỗng" in prompt


def test_generate_prompt_uses_user_instruction():
    prompt = PromptGenerator().generate(_req(user_instruction="Make it tense"))
    assert "Hướng dẫn bổ sung từ người dùng" in prompt
    assert "Make it tense" in prompt


def test_generate_prompt_multi_source_no_special_section():
    prompt = PromptGenerator().generate(_req(
        source_mode="multi",
        youtube_urls=[
            HttpUrl("https://www.youtube.com/watch?v=first"),
            HttpUrl("https://www.youtube.com/watch?v=second"),
        ],
    ))
    assert "MULTI-SOURCE RULES" not in prompt
    assert "source_1" in prompt
    assert "source_2" in prompt


def test_validation_block_contains_contract_rules():
    result = ValidationBlock().render(_req())
    assert "Chỉ trả về một JSON object hợp lệ" in result
    assert "Không dùng Markdown" in result
    assert "Root object chỉ được có các key" in result
    assert "srt" in result
    assert "video_segments" in result
    assert "scene_beats" in result and "Dùng" in result
    assert "output_start" in result and "Dùng" in result


def test_output_schema_block_contains_schema():
    result = OutputSchemaBlock().render(_req())
    assert "Schema bắt buộc" in result
    assert "video_title" in result
    assert "target_language" in result
    assert "Tiếng Việt" in result
    assert "scene_beats" not in result
    assert "output_start" not in result
    assert "output_end" not in result
    assert "story_role" not in result


def test_output_schema_block_uses_input_url():
    result = OutputSchemaBlock().render(_req(youtube_url=HttpUrl("https://www.youtube.com/watch?v=Iy3F569-bTY")))
    assert "watch?v=..." not in result
    assert '"youtube_url": "https://www.youtube.com/watch?v=Iy3F569-bTY"' in result


def test_generate_prompt_has_timing_and_voiceover_rules():
    prompt = PromptGenerator().generate(_req())
    assert "Tốc độ đọc mục tiêu" in prompt
    assert "2.5–3 từ" in prompt
    assert "Không nhồi quá nhiều từ" in prompt
    assert "Không chia subtitle" in prompt
    assert "khoảng lặng có chủ ý" in prompt
    assert "source_start phải nhỏ hơn source_end" in prompt


def test_generate_prompt_has_dynamic_pacing_and_target_duration():
    prompt = PromptGenerator().generate(_req(target_duration="10-20 phút"))
    assert "Thời lượng remake mục tiêu: 10-20 phút" in prompt
    assert "DYNAMIC PACING VÀ LONG-HORIZON PLANNING" in prompt
    assert "FAST" in prompt and "3-5 giây/SRT" in prompt
    assert "MEDIUM" in prompt and "6-10 giây/SRT" in prompt
    assert "COMPACT" in prompt and "10-15 giây/SRT" in prompt
    assert "25%, 50%, 75% và 100%" in prompt
    assert "+/-15 percentage points" in prompt
    assert "T_target_seconds" in prompt
    assert "N_min = ceil" in prompt
    assert "average_profile_duration_seconds" in prompt
    assert "255" in prompt and "32 SRT" in prompt
    assert "NARRATIVE EXPANSION STRATEGY" in prompt
    assert "FINAL ARITHMETIC GATE" in prompt
    assert "FINAL TEXT GATE" in prompt


def test_generate_prompt_has_long_form_safety_and_terminal_sync_rules():
    prompt = PromptGenerator().generate(_req(target_duration="5-10 phút"))
    assert "Không áp bất kỳ giới hạn phần tử" in prompt
    assert "không được vượt quá 3 dòng" in prompt
    assert "boundary 80 ký tự" in prompt
    assert "Wide-range mapping" in prompt
    assert "Video segment cuối theo order" in prompt
    assert "Mọi SRT index phải được ít nhất một video segment" in prompt
    assert "Không đóng JSON sớm" in prompt or "đóng JSON sớm" in prompt


def test_generate_prompt_removes_legacy_array_limit_and_clip_preservation_rule():
    prompt = PromptGenerator().generate(_req())
    assert "không được vượt quá 90 phần tử" not in prompt
    assert "max 90" not in prompt.lower()
    assert "Giữ lại từ 100% các cảnh" not in prompt
    assert "Giữ 100% mạch truyện cốt lõi" in prompt


def test_generate_prompt_has_consistency_rules():
    prompt = PromptGenerator().generate(_req())
    assert "full_text phải bằng nội dung" in prompt
    assert "srt[].text ghép lại" in prompt
    assert "subtitle_start phải bằng subtitle_end" in prompt
    assert "order phải tăng liên tục từ 1" in prompt
    assert "segment_id phải là số nguyên dương" in prompt


def test_generate_prompt_has_timestamp_format():
    prompt = PromptGenerator().generate(_req())
    assert "HH:MM:SS,mmm" in prompt
    assert "HH:MM:SS.mmm" in prompt
    assert "\"00:00:15,000\"" in prompt or "'00:00:15,000'" in prompt


def test_generate_prompt_has_self_check():
    prompt = PromptGenerator().generate(_req())
    assert "FINAL SELF-CHECK" in prompt
    assert "JSON parse được" in prompt
    assert "Không có field thừa" in prompt
    assert "Không có trailing comma" in prompt


def test_generate_prompt_validation_block_no_multi_source_conditional():
    prompt = PromptGenerator().generate(_req(source_mode="multi", youtube_urls=[
        HttpUrl("https://www.youtube.com/watch?v=first"),
        HttpUrl("https://www.youtube.com/watch?v=second"),
    ]))
    assert "Với một nguồn video" in prompt
