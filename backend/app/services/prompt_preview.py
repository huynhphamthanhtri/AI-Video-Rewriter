from __future__ import annotations

from pydantic import HttpUrl

from app.schemas.prompt import (
    PromptGenerateRequest,
    PromptPreviewRequest,
    PromptPreviewResponse,
    PromptPreviewSection,
)
from app.services.prompt_generator import PromptGenerator


DUMMY_URL = HttpUrl("https://www.youtube.com/watch?v=preview_dummy")

SECTION_MARKERS: list[tuple[str, str]] = [
    ("Role", "LỚP 1"),
    ("Source Rules", "CHỐNG BỊA NỘI DUNG"),
    ("Intent", "CẤU HÌNH VIẾT LẠI"),
    ("Strategy", "LỚP 2"),
    ("Localization", "NGÔN NGỮ VÀ BẢN ĐỊA HÓA"),
    ("Story", "LỚP 3"),
    ("Subtitle Rules", "RÀNG BUỘC SUBTITLE"),
    ("Content Quality", "CHẤT LƯỢNG NỘI DUNG"),
    ("Hook Requirements", "HOOK BẮT BUỘC"),
    ("Task Assignment", "NHIỆM VỤ"),
    ("Alignment Rules", "SRT-SCENE ALIGNMENT RULES"),
    ("Domain Rules", "DOMAIN RULES"),
    ("Validation", "QUY TẮC JSON BẮT BUỘC:"),
    ("Output Contract", "STRICT OUTPUT CONTRACT"),
    ("Schema", "Schema bắt buộc"),
]


def _to_generate_request(preview: PromptPreviewRequest) -> PromptGenerateRequest:
    return PromptGenerateRequest(
        youtube_url=DUMMY_URL,
        youtube_urls=[],
        source_mode="single",
        preset_name=None,
        rewrite_style=preview.rewrite_style,
        target_audience=preview.target_audience,
        tone=preview.tone,
        target_duration=preview.target_duration,
        retention_mode=preview.retention_mode,
        hook_style=preview.hook_style,
        clip_strategy=preview.clip_strategy,
        reuse_level=preview.reuse_level,
        content_density=preview.content_density,
        target_language=preview.target_language,
        target_market=preview.target_market,
        localization_level=preview.localization_level,
        rename_characters=preview.rename_characters,
        adapt_culture=preview.adapt_culture,
        adapt_currency=preview.adapt_currency,
        adapt_units=preview.adapt_units,
        adapt_company_names=preview.adapt_company_names,
        adaptation_mode=preview.adaptation_mode,
        narrator_persona="neutral_narrator",
    )


class PromptPreviewService:
    def __init__(self) -> None:
        self._generator = PromptGenerator()

    def preview(self, data: PromptPreviewRequest) -> PromptPreviewResponse:
        gen_request = _to_generate_request(data)
        preview_text = self._generator.generate(gen_request)
        full_length = len(preview_text)
        estimated_tokens = round(full_length * 0.38)

        sections = self._detect_sections(preview_text)

        return PromptPreviewResponse(
            preview_text=preview_text,
            full_length=full_length,
            estimated_tokens=estimated_tokens,
            sections=sections,
        )

    def _detect_sections(self, text: str) -> list[PromptPreviewSection]:
        sections: list[PromptPreviewSection] = []

        for title, marker in SECTION_MARKERS:
            pos = text.find(marker)
            if pos == -1:
                continue
            start_excerpt = max(0, pos)
            end_excerpt = min(len(text), pos + 120)
            excerpt = text[start_excerpt:end_excerpt].strip()

            sections.append(
                PromptPreviewSection(
                    title=title,
                    start=pos,
                    end=end_excerpt,
                    excerpt=excerpt,
                )
            )

        sections.sort(key=lambda s: s.start)
        return sections
