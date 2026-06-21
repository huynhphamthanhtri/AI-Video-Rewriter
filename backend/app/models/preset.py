from __future__ import annotations

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.versions import (
    CURRENT_JSON_OUTPUT_SCHEMA_VERSION,
    CURRENT_PRESET_SCHEMA_VERSION,
    CURRENT_PROMPT_TEMPLATE_VERSION,
)


class PresetORM(Base):
    __tablename__ = "presets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    rewrite_style: Mapped[str] = mapped_column(String(100), nullable=False)
    target_audience: Mapped[str] = mapped_column(String(100), nullable=False)
    tone: Mapped[str] = mapped_column(String(100), nullable=False)
    target_duration: Mapped[str] = mapped_column(String(100), nullable=False)
    retention_mode: Mapped[str] = mapped_column(String(100), nullable=False)
    hook_style: Mapped[str] = mapped_column(String(100), nullable=False)
    clip_strategy: Mapped[str] = mapped_column(String(100), nullable=False)
    reuse_level: Mapped[str] = mapped_column(String(100), nullable=False)
    content_density: Mapped[str] = mapped_column(String(100), nullable=False)
    target_language: Mapped[str] = mapped_column(String(100), default="Tiếng Việt", nullable=False)
    target_market: Mapped[str] = mapped_column(String(100), default="Việt Nam", nullable=False)
    localization_level: Mapped[str] = mapped_column(String(50), default="medium", nullable=False)
    rename_characters: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    adapt_culture: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    adapt_currency: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    adapt_units: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    adapt_company_names: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    adaptation_mode: Mapped[str] = mapped_column(String(50), default="localized", nullable=False)
    narrator_persona: Mapped[str] = mapped_column(String(100), default="drama_storyteller", nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preset_schema_version: Mapped[int] = mapped_column(Integer, default=CURRENT_PRESET_SCHEMA_VERSION, nullable=False)
    prompt_template_version: Mapped[int] = mapped_column(Integer, default=CURRENT_PROMPT_TEMPLATE_VERSION, nullable=False)
    json_output_schema_version: Mapped[int] = mapped_column(Integer, default=CURRENT_JSON_OUTPUT_SCHEMA_VERSION, nullable=False)


class AppSettingORM(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
