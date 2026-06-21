from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.versions import (
    CURRENT_JSON_OUTPUT_SCHEMA_VERSION,
    CURRENT_PRESET_SCHEMA_VERSION,
    CURRENT_PROMPT_TEMPLATE_VERSION,
)


class PromptRunORM(Base):
    __tablename__ = "prompt_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    prompt_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    health_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    preset_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    rewrite_style: Mapped[str | None] = mapped_column(String(100), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    form_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    preset_schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    json_output_schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
