from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings
from app.core.versions import (
    CURRENT_JSON_OUTPUT_SCHEMA_VERSION,
    CURRENT_PRESET_SCHEMA_VERSION,
    CURRENT_PROMPT_TEMPLATE_VERSION,
)


def _ensure_sqlite_parent() -> None:
    if not settings.sqlite_url.startswith("sqlite:///"):
        return
    db_path = settings.sqlite_url.removeprefix("sqlite:///")
    if db_path and db_path != ":memory:":
        from pathlib import Path

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    pass


_ensure_sqlite_parent()
engine = create_engine(settings.sqlite_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


PRESET_LOCALIZATION_COLUMNS: dict[str, str] = {
    "target_language": "VARCHAR(100) NOT NULL DEFAULT 'Tiếng Việt'",
    "target_market": "VARCHAR(100) NOT NULL DEFAULT 'Việt Nam'",
    "localization_level": "VARCHAR(50) NOT NULL DEFAULT 'medium'",
    "rename_characters": "BOOLEAN NOT NULL DEFAULT 1",
    "adapt_culture": "BOOLEAN NOT NULL DEFAULT 1",
    "adapt_currency": "BOOLEAN NOT NULL DEFAULT 1",
    "adapt_units": "BOOLEAN NOT NULL DEFAULT 1",
    "adapt_company_names": "BOOLEAN NOT NULL DEFAULT 1",
    "adaptation_mode": "VARCHAR(50) NOT NULL DEFAULT 'localized'",
    "narrator_persona": "VARCHAR(100) NOT NULL DEFAULT 'neutral_narrator'",
}


PRESET_VERSION_COLUMNS: dict[str, str] = {
    "preset_schema_version": f"INTEGER NOT NULL DEFAULT {CURRENT_PRESET_SCHEMA_VERSION}",
    "prompt_template_version": f"INTEGER NOT NULL DEFAULT {CURRENT_PROMPT_TEMPLATE_VERSION}",
    "json_output_schema_version": f"INTEGER NOT NULL DEFAULT {CURRENT_JSON_OUTPUT_SCHEMA_VERSION}",
}


def migrate_sqlite_presets() -> None:
    """Add localization + version columns to existing SQLite databases without losing presets."""
    inspector = inspect(engine)
    if "presets" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("presets")}
    with engine.begin() as connection:
        for column_name, column_definition in PRESET_LOCALIZATION_COLUMNS.items():
            if column_name not in existing_columns:
                connection.execute(text(f"ALTER TABLE presets ADD COLUMN {column_name} {column_definition}"))
        for column_name, column_definition in PRESET_VERSION_COLUMNS.items():
            if column_name not in existing_columns:
                connection.execute(text(f"ALTER TABLE presets ADD COLUMN {column_name} {column_definition}"))


def migrate_sqlite_app_settings() -> None:
    inspector = inspect(engine)
    if "app_settings" in inspector.get_table_names():
        return
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE app_settings (key VARCHAR(100) PRIMARY KEY, value_json TEXT NOT NULL, updated_at FLOAT NOT NULL)"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
