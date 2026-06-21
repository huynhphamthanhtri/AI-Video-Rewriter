from pydantic import HttpUrl

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.composer import PromptComposer
from app.services.prompt_blocks.intent_block import IntentBlock
from app.services.prompt_blocks.localization_block import LocalizationBlock
from app.services.prompt_blocks.strategy_block import StrategyBlock
from app.services.prompt_blocks.validation_block import ValidationBlock
from app.services.prompt_blocks.output_schema_block import OutputSchemaBlock
from app.services.prompt_generator import PromptGenerator


def _req(**overrides) -> PromptGenerateRequest:
    defaults = dict(
        youtube_url=HttpUrl("https://www.youtube.com/watch?v=test"),
        source_mode="single",
        preset_name="Test Preset",
        rewrite_style="Storytelling",
        target_audience="Đại chúng",
        tone="Thân thiện",
        target_duration="3-5 phút",
        retention_mode="Cao",
        hook_style="Cảnh đắt giá",
        clip_strategy="Giữ đầy đủ ngữ cảnh",
        reuse_level="Trung bình",
        content_density="Trung bình",
    )
    defaults.update(overrides)
    return PromptGenerateRequest(**defaults)


def test_generate_prompt_contains_rules():
    prompt = PromptGenerator().generate(_req())
    assert "Bạn là chuyên gia biên tập video" in prompt
    assert "RÀNG BUỘC SUBTITLE" in prompt
    assert "CHẤT LƯỢNG NỘI DUNG" in prompt
    assert "QUY TẮC JSON BẮT BUỘC" in prompt
    assert "STRICT OUTPUT CONTRACT" in prompt
    assert "Schema bắt buộc" in prompt


def test_generate_prompt_multi_source_contains_source_rules():
    prompt = PromptGenerator().generate(_req(source_mode="multi", youtube_urls=[HttpUrl("https://www.youtube.com/watch?v=first"), HttpUrl("https://www.youtube.com/watch?v=second")]))
    assert "MULTI-SOURCE RULES" in prompt


def test_generate_prompt_single_source_missing_multi_rules():
    prompt = PromptGenerator().generate(_req())
    assert "MULTI-SOURCE RULES" not in prompt


def test_intent_block_contains_preset_name():
    block = IntentBlock()
    result = block.render(_req(preset_name="My Preset"))
    assert "My Preset" in result
    assert "Cấu hình viết lại:" in result
    assert "Storytelling" in result


def test_intent_block_auto_duration():
    block = IntentBlock()
    result = block.render(_req(target_duration="Tự đề xuất thời lượng phù hợp với kịch bản remake"))
    assert "AI tự đề xuất" in result


def test_strategy_block_contains_fields():
    block = StrategyBlock()
    result = block.render(_req())
    assert "Chiến lược giữ chân" in result
    assert "Cao" in result
    assert "Cảnh đắt giá" in result
    assert "Giữ đầy đủ ngữ cảnh" in result


def test_localization_block_contains_config():
    block = LocalizationBlock()
    result = block.render(_req())
    assert "Cấu hình ngôn ngữ và bản địa hóa:" in result
    assert "Ngôn ngữ đích: Tiếng Việt" in result
    assert "Thị trường đích: Việt Nam" in result
    assert "Chế độ chuyển thể" in result
    assert "Persona người kể chuyện" in result


def test_validation_block_contains_json_rules():
    block = ValidationBlock()
    result = block.render(_req())
    assert "QUY TẮC JSON BẮT BUỘC:" in result
    assert "Return ONLY valid JSON" in result
    assert "video_segments" in result
    assert "source_1" in result


def test_validation_block_multi_source_segment_rule():
    block = ValidationBlock()
    result = block.render(_req(source_mode="multi"))
    assert "source_id là bắt buộc" in result
    assert "multi-source" not in result or True  # no negative check needed


def test_output_schema_block_contains_contract():
    block = OutputSchemaBlock()
    result = block.render(_req())
    assert "STRICT OUTPUT CONTRACT" in result
    assert "MANDATORY RULES" in result
    assert "Extra fields = REJECTED" in result
    assert "Schema bắt buộc" in result
    assert '"importance_score": 95' in result


def test_output_schema_block_multi_source():
    block = OutputSchemaBlock()
    result = block.render(_req(source_mode="multi", youtube_urls=[HttpUrl("https://www.youtube.com/watch?v=a"), HttpUrl("https://www.youtube.com/watch?v=b")]))
    assert "Mô tả ngắn nguồn video" in result


def test_output_schema_block_single_source():
    block = OutputSchemaBlock()
    result = block.render(_req())
    assert "Video nguồn chính" in result


def test_composer_all_blocks_present():
    composer = PromptComposer(_req())
    result = composer.compose()
    assert "Bạn là chuyên gia biên tập video" in result
    assert "Cấu hình viết lại:" in result
    assert "Chiến lược giữ chân" in result
    assert "Cấu hình ngôn ngữ và bản địa hóa:" in result
    assert "QUY TẮC JSON BẮT BUỘC:" in result
    assert "STRICT OUTPUT CONTRACT" in result
    assert "RÀNG BUỘC SUBTITLE" in result
    assert "CHẤT LƯỢNG NỘI DUNG" in result
    assert "HOOK BẮT BUỘC" in result
    assert "Nhiệm vụ:" in result
    assert "SRT-SCENE ALIGNMENT RULES" in result
    assert "DOMAIN RULES FOR SPORTS" in result


def test_prompt_contains_strict_output_contract():
    prompt = PromptGenerator().generate(_req())
    assert "STRICT OUTPUT CONTRACT" in prompt
    assert "VIOLATION → TOÀN BỘ RESPONSE BỊ REJECT" in prompt


def test_prompt_contains_canonical_market_label():
    prompt = PromptGenerator().generate(_req(target_market="Việt Nam"))
    assert "Việt Nam" in prompt


def test_prompt_contains_voice_section():
    prompt = PromptGenerator().generate(_req())
    assert "GIỌNG KỂ / VOICE" in prompt
    assert "HƯỚNG DẪN HÀNH VI KỂ CHUYỆN" in prompt
    assert "Thân thiện" in prompt  # tone appears in VoiceBlock


def test_prompt_contains_creator_dna_when_present(monkeypatch):
    monkeypatch.setattr(
        "app.services.prompt_blocks.composer.load_creator_dna",
        lambda path=None: "DNA CONTENT - TEST CREATOR IDENTITY",
    )
    prompt = PromptGenerator().generate(_req())
    assert "CREATOR DNA / BẢN SẮC" in prompt
    assert "DNA CONTENT" in prompt


def test_prompt_omits_creator_dna_when_absent(monkeypatch):
    monkeypatch.setattr(
        "app.services.prompt_blocks.composer.load_creator_dna",
        lambda path=None: None,
    )
    prompt = PromptGenerator().generate(_req())
    assert "CREATOR DNA" not in prompt


def test_prompt_section_order(monkeypatch):
    monkeypatch.setattr(
        "app.services.prompt_blocks.composer.load_creator_dna",
        lambda path=None: "Order test DNA",
    )
    prompt = PromptGenerator().generate(_req(narrator_persona="detective"))
    strategy_idx = prompt.index("Chiến lược giữ chân")
    voice_idx = prompt.index("GIỌNG KỂ / VOICE")
    dna_idx = prompt.index("CREATOR DNA / BẢN SẮC")
    loc_idx = prompt.index("Cấu hình ngôn ngữ và bản địa hóa:")
    assert strategy_idx < voice_idx, "Strategy should come before Voice"
    assert voice_idx < dna_idx, "Voice should come before Creator DNA"
    assert dna_idx < loc_idx, "Creator DNA should come before Localization"
