from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.base import PromptBlock


class IntentBlock(PromptBlock):
    def render(self, data: PromptGenerateRequest) -> str:
        duration_instruction = (
            "AI tự đề xuất thời lượng phù hợp nhất với kịch bản remake, nhịp kể, "
            "mật độ nội dung và khả năng giữ chân người xem. "
            "Ghi thời lượng đề xuất vào metadata.target_duration."
            if data.target_duration == "Tự đề xuất thời lượng phù hợp với kịch bản remake"
            else data.target_duration
        )
        return (
            f"Cấu hình viết lại:\n"
            f"- Preset: {data.preset_name or 'Tùy chỉnh thủ công'}\n"
            f"- Phong cách viết lại: {data.rewrite_style}\n"
            f"- Đối tượng khán giả: {data.target_audience}\n"
            f"- Giọng điệu: {data.tone}\n"
            f"- Độ dài video mục tiêu: {duration_instruction}"
        )
