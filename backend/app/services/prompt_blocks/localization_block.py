from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.base import PromptBlock
from app.services.prompt_labels import (
    ADAPTATION_MODE_LABELS,
    LOCALIZATION_LEVEL_LABELS,
    NARRATOR_PERSONA_LABELS,
    bool_label,
)


class LocalizationBlock(PromptBlock):
    def render(self, data: PromptGenerateRequest) -> str:
        return (
            f"Cấu hình ngôn ngữ và bản địa hóa:\n"
            f"- Ngôn ngữ đích: {data.target_language}\n"
            f"- Thị trường đích: {data.target_market}\n"
            f"- Mức độ địa phương hóa: {LOCALIZATION_LEVEL_LABELS[data.localization_level]} ({data.localization_level})\n"
            f"- Đổi tên nhân vật: {bool_label(data.rename_characters)}\n"
            f"- Điều chỉnh bối cảnh văn hóa: {bool_label(data.adapt_culture)}\n"
            f"- Quy đổi tiền tệ: {bool_label(data.adapt_currency)}\n"
            f"- Quy đổi đơn vị đo: {bool_label(data.adapt_units)}\n"
            f"- Đổi tên công ty/thương hiệu hư cấu: {bool_label(data.adapt_company_names)}\n"
            f"- Chế độ chuyển thể: {ADAPTATION_MODE_LABELS[data.adaptation_mode]} ({data.adaptation_mode})\n"
            f"- Persona người kể chuyện: {NARRATOR_PERSONA_LABELS[data.narrator_persona]} ({data.narrator_persona})"
        )
