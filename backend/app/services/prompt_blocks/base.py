from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.prompt import PromptGenerateRequest


class PromptBlock(ABC):
    @abstractmethod
    def render(self, data: PromptGenerateRequest) -> str:
        ...
