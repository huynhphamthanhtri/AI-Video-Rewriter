from app.schemas.prompt import PromptPreviewRequest
from app.services.prompt_preview import PromptPreviewService


def _preview(**overrides) -> PromptPreviewRequest:
    data = dict(
        rewrite_style="Storytelling",
        target_audience="Đại chúng",
        tone="Thân thiện",
        target_duration="3-5 phút",
        retention_mode="Cao",
        hook_style="Cảnh đắt giá",
        clip_strategy="Giữ đầy đủ ngữ cảnh",
        reuse_level="Trung bình",
        content_density="Trung bình",
        target_language="Tiếng Việt",
        target_market="Việt Nam",
        localization_level="medium",
        rename_characters=True,
        adapt_culture=True,
        adapt_currency=True,
        adapt_units=True,
        adapt_company_names=True,
        adaptation_mode="localized",
        narrator_persona="neutral_narrator",
    )
    data.update(overrides)
    return PromptPreviewRequest(**data)


def test_preview_contains_text():
    result = PromptPreviewService().preview(_preview())
    assert len(result.preview_text) > 50
    assert "Bạn là một chuyên gia biên kịch" in result.preview_text


def test_preview_returns_full_length():
    result = PromptPreviewService().preview(_preview())
    assert result.full_length == len(result.preview_text)


def test_preview_estimates_tokens():
    result = PromptPreviewService().preview(_preview())
    assert result.estimated_tokens > 0
    expected = round(len(result.preview_text) * 0.38)
    assert result.estimated_tokens == expected


def test_preview_returns_sections():
    result = PromptPreviewService().preview(_preview())
    assert len(result.sections) >= 5


def test_preview_sections_have_valid_ranges():
    result = PromptPreviewService().preview(_preview())
    for section in result.sections:
        assert 0 <= section.start < section.end
        assert section.end <= result.full_length
        assert len(section.excerpt) > 0
