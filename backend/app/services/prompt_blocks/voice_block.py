from __future__ import annotations
from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.base import PromptBlock


class VoiceBlock(PromptBlock):
    def render(self, data: PromptGenerateRequest) -> str:
        return (
            "GIỌNG KỂ / VOICE & PERSONALITY:\n"
            f"- Giọng điệu tổng thể: {data.tone}"
        )
