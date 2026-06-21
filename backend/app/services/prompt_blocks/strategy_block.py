from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.base import PromptBlock


class StrategyBlock(PromptBlock):
    def render(self, data: PromptGenerateRequest) -> str:
        return (
            f"- Chiến lược giữ chân người xem: {data.retention_mode}\n"
            f"- Kiểu hook mở đầu: {data.hook_style}\n"
            f"- Chiến lược chọn cảnh: {data.clip_strategy}\n"
            f"- Mức độ tái sử dụng video gốc: {data.reuse_level}\n"
            f" - Mật độ nội dung: {data.content_density}"
        )
