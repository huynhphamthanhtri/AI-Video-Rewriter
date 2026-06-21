from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

from app.core.versions import (
    CURRENT_JSON_OUTPUT_SCHEMA_VERSION,
    CURRENT_PRESET_SCHEMA_VERSION,
    CURRENT_PROMPT_TEMPLATE_VERSION,
)

LocalizationLevel = Literal["none", "light", "medium", "heavy"]
AdaptationMode = Literal["faithful", "localized", "inspired"]
NarratorPersona = Literal[
    "neutral_narrator",
    "funny_friend",
    "drama_storyteller",
    "movie_reviewer",
    "news_anchor",
    "expert_analyst",
    "detective",
    "teacher",
    "podcast_host",
    "tech_reviewer",
    "investor",
]


class PresetBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=500)
    rewrite_style: str
    target_audience: str
    tone: str
    target_duration: str
    retention_mode: str
    hook_style: str
    clip_strategy: str
    reuse_level: str
    content_density: str
    target_language: str = Field(default="Tiếng Việt", min_length=1)
    target_market: str = Field(default="Việt Nam", min_length=1)
    localization_level: LocalizationLevel = "medium"
    rename_characters: bool = True
    adapt_culture: bool = True
    adapt_currency: bool = True
    adapt_units: bool = True
    adapt_company_names: bool = True
    adaptation_mode: AdaptationMode = "localized"
    narrator_persona: NarratorPersona = "neutral_narrator"
    preset_schema_version: int = Field(default=CURRENT_PRESET_SCHEMA_VERSION, ge=1)
    prompt_template_version: int = Field(default=CURRENT_PROMPT_TEMPLATE_VERSION, ge=1)
    json_output_schema_version: int = Field(default=CURRENT_JSON_OUTPUT_SCHEMA_VERSION, ge=1)


class PresetCreate(PresetBase):
    pass


class PresetUpdate(PresetBase):
    pass


class PresetCompareRequest(BaseModel):
    left_preset_id_or_name: str
    right_preset_id_or_name: str


class PresetCompareDiff(BaseModel):
    group: str
    field: str
    left: str | int | bool
    right: str | int | bool


class PresetCompareResponse(BaseModel):
    left_name: str
    right_name: str
    same: list[str]
    different: list[PresetCompareDiff]


class PresetRead(PresetBase):
    id: str
    is_builtin: bool

    @computed_field
    @property
    def intent(self) -> dict[str, str]:
        return {
            "rewrite_style": self.rewrite_style,
            "tone": self.tone,
            "target_audience": self.target_audience,
        }

    @computed_field
    @property
    def strategy(self) -> dict[str, str]:
        return {
            "retention_mode": self.retention_mode,
            "hook_style": self.hook_style,
            "clip_strategy": self.clip_strategy,
            "reuse_level": self.reuse_level,
            "content_density": self.content_density,
        }

    @computed_field
    @property
    def constraints(self) -> dict[str, str | bool]:
        return {
            "target_duration": self.target_duration,
            "target_language": self.target_language,
            "target_market": self.target_market,
            "localization_level": self.localization_level,
            "rename_characters": self.rename_characters,
            "adapt_culture": self.adapt_culture,
            "adapt_currency": self.adapt_currency,
            "adapt_units": self.adapt_units,
            "adapt_company_names": self.adapt_company_names,
            "adaptation_mode": self.adaptation_mode,
            "narrator_persona": self.narrator_persona,
        }
