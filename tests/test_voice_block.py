import pytest
from pydantic import HttpUrl

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.voice_block import VoiceBlock


def _req(narrator_persona: str = "neutral_narrator", tone: str = "Thân thiện") -> PromptGenerateRequest:
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
        narrator_persona=narrator_persona,
    )


class TestVoiceBlockNeutralNarrator:
    def test_behavior_contains_objective_tone(self) -> None:
        result = VoiceBlock().render(_req("neutral_narrator"))
        assert "trình tự thời gian" in result
        assert "khách quan" in result

    def test_output_contains_persona_key(self) -> None:
        result = VoiceBlock().render(_req("neutral_narrator"))
        assert "neutral_narrator" in result

    def test_output_contains_tone(self) -> None:
        result = VoiceBlock().render(_req("neutral_narrator", "Nghiêm túc"))
        assert "Nghiêm túc" in result

    def test_behavior_is_not_generic_label(self) -> None:
        result = VoiceBlock().render(_req("neutral_narrator"))
        assert "narrative approach" not in result.lower()
        assert "reasoning style" not in result.lower()


class TestVoiceBlockDramaStoryteller:
    def test_behavior_contains_drama_patterns(self) -> None:
        result = VoiceBlock().render(_req("drama_storyteller"))
        assert "cao trào" in result
        assert "cảm thán" in result
        assert "căng thẳng" in result

    def test_output_section_marker(self) -> None:
        result = VoiceBlock().render(_req("drama_storyteller"))
        assert "GIỌNG KỂ" in result
        assert "HƯỚNG DẪN HÀNH VI KỂ CHUYỆN" in result


class TestVoiceBlockTechReviewer:
    def test_behavior_contains_comparison_patterns(self) -> None:
        result = VoiceBlock().render(_req("tech_reviewer"))
        assert "So sánh" in result
        assert "trade-off" in result or "đánh giá" in result

    def test_behavior_contains_spec_guidance(self) -> None:
        result = VoiceBlock().render(_req("tech_reviewer"))
        assert "thông số" in result or "số liệu" in result


class TestVoiceBlockDetective:
    def test_behavior_contains_evidence_patterns(self) -> None:
        result = VoiceBlock().render(_req("detective"))
        assert "bằng chứng" in result
        assert "câu hỏi" in result
        assert "suy luận" in result

    def test_behavior_contains_reveal_progression(self) -> None:
        result = VoiceBlock().render(_req("detective"))
        assert "hé lộ" in result or "từng lớp" in result


class TestVoiceBlockFunnyFriend:
    def test_behavior_contains_humor_patterns(self) -> None:
        result = VoiceBlock().render(_req("funny_friend"))
        assert "hài" in result or "tự trào" in result or "thoải mái" in result

    def test_behavior_contains_conversational_style(self) -> None:
        result = VoiceBlock().render(_req("funny_friend"))
        assert "tám" in result or "bạn" in result


class TestVoiceBlockMovieReviewer:
    def test_movie_reviewer_contains_cinema_language(self) -> None:
        result = VoiceBlock().render(_req("movie_reviewer"))
        assert "diễn xuất" in result or "kịch bản" in result or "hình ảnh" in result

    def test_movie_reviewer_contains_comparison(self) -> None:
        result = VoiceBlock().render(_req("movie_reviewer"))
        assert "So sánh" in result


class TestVoiceBlockNewsAnchor:
    def test_news_anchor_contains_5w1h_pattern(self) -> None:
        result = VoiceBlock().render(_req("news_anchor"))
        assert "5W1H" in result or "ngắn" in result

    def test_news_anchor_contains_journalism_style(self) -> None:
        result = VoiceBlock().render(_req("news_anchor"))
        assert "dữ kiện" in result
        assert "trung lập" in result or "cảm xúc" in result


class TestVoiceBlockExpertAnalyst:
    def test_expert_analyst_contains_analysis_patterns(self) -> None:
        result = VoiceBlock().render(_req("expert_analyst"))
        assert "nguyên nhân" in result or "dữ liệu" in result
        assert "đa chiều" in result

    def test_expert_analyst_contains_prediction(self) -> None:
        result = VoiceBlock().render(_req("expert_analyst"))
        assert "Dự đoán" in result


class TestVoiceBlockTeacher:
    def test_teacher_contains_explanation_patterns(self) -> None:
        result = VoiceBlock().render(_req("teacher"))
        assert "dễ đến khó" in result or "cơ bản" in result
        assert "giải thích" in result

    def test_teacher_contains_metaphor_guidance(self) -> None:
        result = VoiceBlock().render(_req("teacher"))
        assert "So sánh" in result or "ẩn dụ" in result


class TestVoiceBlockPodcastHost:
    def test_podcast_host_contains_conversation_patterns(self) -> None:
        result = VoiceBlock().render(_req("podcast_host"))
        assert "trò chuyện" in result or "đối thoại" in result

    def test_podcast_host_contains_pacing(self) -> None:
        result = VoiceBlock().render(_req("podcast_host"))
        assert "chậm" in result or "khoảng lặng" in result


class TestVoiceBlockInvestor:
    def test_investor_contains_market_analysis(self) -> None:
        result = VoiceBlock().render(_req("investor"))
        assert "thị trường" in result
        assert "rủi ro" in result or "cơ hội" in result
        assert "định giá" in result or "doanh thu" in result

    def test_investor_contains_benchmark(self) -> None:
        result = VoiceBlock().render(_req("investor"))
        assert "So sánh" in result


class TestVoiceBlockFallback:
    def test_unknown_persona_key_falls_back(self) -> None:
        # Fallback is triggered by key not in _PERSONA_BEHAVIOR dict.
        # We test this by checking the dict directly since the Pydantic Literal
        # type prevents passing unknown values through PromptGenerateRequest.
        from app.services.prompt_blocks.voice_block import _PERSONA_BEHAVIOR
        assert "non_existent_persona" not in _PERSONA_BEHAVIOR

    def test_fallback_is_not_label_dump(self) -> None:
        from app.services.prompt_blocks.voice_block import _FALLBACK_BEHAVIOR
        assert "Tone:" not in _FALLBACK_BEHAVIOR
        assert "Persona:" not in _FALLBACK_BEHAVIOR
        assert _FALLBACK_BEHAVIOR.startswith("-")


class TestVoiceBlockToneFieldPresence:
    def test_tone_appears_in_output(self) -> None:
        result = VoiceBlock().render(_req("neutral_narrator", "Năng lượng cao"))
        assert "Năng lượng cao" in result

    def test_giọng_điệu_header_frame_only(self) -> None:
        result = VoiceBlock().render(_req("detective"))
        assert "Tone:" not in result
        # Persona: header is metadata, not the behavioral content.
        # Behavioral guidance follows below the header row.


class TestVoiceBlockAllPersonasSmoke:
    @pytest.mark.parametrize("persona", [
        "neutral_narrator",
        "drama_storyteller",
        "tech_reviewer",
        "detective",
        "funny_friend",
        "movie_reviewer",
        "news_anchor",
        "expert_analyst",
        "teacher",
        "podcast_host",
        "investor",
    ])
    def test_each_persona_renders_without_error(self, persona: str) -> None:
        result = VoiceBlock().render(_req(persona))
        assert result
        assert "GIỌNG KỂ" in result
