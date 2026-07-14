from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.base import PromptBlock
from app.services.prompt_labels import (
    LOCALIZATION_LEVEL_LABELS,
    bool_label,
)


class LocalizationBlock(PromptBlock):
    def render(self, data: PromptGenerateRequest) -> str:
        level_desc = {
            "minimal": "Chỉ dịch ngôn ngữ, giữ nguyên toàn bộ bối cảnh gốc.",
            "medium": "Chỉ địa phương hóa ngôn ngữ — ví dụ so sánh, đơn vị, cách xưng hô. Không thay đổi địa điểm, sự kiện, văn hóa gốc.",
            "heavy": "Địa phương hóa sâu: thay đổi ví dụ, so sánh, bối cảnh nhẹ cho phù hợp văn hóa đích, nhưng giữ nguyên sự kiện và cốt truyện gốc.",
        }.get(data.localization_level, "")
        return (
            f"Cấu hình ngôn ngữ và bản địa hóa:\n"
            f"- Ngôn ngữ đích: {data.target_language}\n"
            f"- Thị trường đích: {data.target_market}\n"
            f"- Mức độ địa phương hóa: {data.localization_level}\n"
            f"  {level_desc}\n"
            f"- Đổi tên nhân vật: {bool_label(data.rename_characters)}\n"
            f"- Quy đổi tiền tệ: {bool_label(data.adapt_currency)}\n"
            f"- Quy đổi đơn vị đo: {bool_label(data.adapt_units)}\n"
            f"- Đổi tên công ty/thương hiệu hư cấu: {bool_label(data.adapt_company_names)}"
        )
