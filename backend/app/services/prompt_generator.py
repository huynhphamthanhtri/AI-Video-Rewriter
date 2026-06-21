from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.composer import PromptComposer
from app.services.prompt_labels import (
    ADAPTATION_MODE_LABELS,
    LOCALIZATION_LEVEL_LABELS,
    NARRATOR_PERSONA_LABELS,
    bool_label,
)


class PromptGenerator:
    def generate(self, data: PromptGenerateRequest) -> str:
        return PromptComposer(data).compose()
