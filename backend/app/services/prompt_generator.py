from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.composer import PromptComposer


class PromptGenerator:
    def generate(self, data: PromptGenerateRequest) -> str:
        return PromptComposer(data).compose_simple_editor()
