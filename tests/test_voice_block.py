import pytest
from pydantic import HttpUrl

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.voice_block import VoiceBlock


def _req(tone: str = "Thân thiện") -> PromptGenerateRequest:
    return PromptGenerateRequest(
        youtube_url=HttpUrl("https://www.youtube.com/watch?v=test"),
        source_mode="single",
        rewrite_style="Storytelling",
        target_audience="Đại chúng",
        tone=tone,
        target_duration="3-5 phút",
        retention_mode="Cao",
        hook_style="Cảnh đắt giá",
        clip_strategy="Giữ đầy đủ ngữ cảnh",
        reuse_level="Trung bình",
        content_density="Trung bình",
        narrator_persona="neutral_narrator",
    )


class TestVoiceBlock:
    def test_contains_voice_header(self) -> None:
        result = VoiceBlock().render(_req())
        assert "GIỌNG KỂ" in result

    def test_contains_no_behavior_section(self) -> None:
        result = VoiceBlock().render(_req())
        assert "HƯỚNG DẪN HÀNH VI KỂ CHUYỆN" not in result

    def test_contains_no_persona_key(self) -> None:
        result = VoiceBlock().render(_req())
        assert "neutral_narrator" not in result

    def test_tone_appears(self) -> None:
        result = VoiceBlock().render(_req("Nghiêm túc"))
        assert "Nghiêm túc" in result

    def test_tone_not_in_english_label(self) -> None:
        result = VoiceBlock().render(_req("detective"))
        assert "Tone:" not in result
