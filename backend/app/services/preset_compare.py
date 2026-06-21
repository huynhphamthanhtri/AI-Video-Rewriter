from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.preset import PresetORM
from app.schemas.preset import PresetCompareDiff, PresetCompareResponse


INTENT_FIELDS = ["rewrite_style", "target_audience", "tone"]
STRATEGY_FIELDS = ["retention_mode", "hook_style", "clip_strategy", "reuse_level", "content_density"]
CONSTRAINTS_FIELDS = ["target_duration", "target_language", "target_market"]
LOCALIZATION_FIELDS = [
    "localization_level", "rename_characters", "adapt_culture",
    "adapt_currency", "adapt_units", "adapt_company_names",
    "adaptation_mode", "narrator_persona",
]
VERSIONING_FIELDS = ["preset_schema_version", "prompt_template_version", "json_output_schema_version"]

COMPARE_FIELDS = INTENT_FIELDS + STRATEGY_FIELDS + CONSTRAINTS_FIELDS + LOCALIZATION_FIELDS + VERSIONING_FIELDS

FIELD_TO_GROUP: dict[str, str] = {}
for f in INTENT_FIELDS:
    FIELD_TO_GROUP[f] = "intent"
for f in STRATEGY_FIELDS:
    FIELD_TO_GROUP[f] = "strategy"
for f in CONSTRAINTS_FIELDS:
    FIELD_TO_GROUP[f] = "constraints"
for f in LOCALIZATION_FIELDS:
    FIELD_TO_GROUP[f] = "localization"
for f in VERSIONING_FIELDS:
    FIELD_TO_GROUP[f] = "versioning"

FIELD_LABELS: dict[str, str] = {
    "rewrite_style": "Rewrite Style",
    "target_audience": "Target Audience",
    "tone": "Tone",
    "retention_mode": "Retention Mode",
    "hook_style": "Hook Style",
    "clip_strategy": "Clip Strategy",
    "reuse_level": "Reuse Level",
    "content_density": "Content Density",
    "target_duration": "Target Duration",
    "target_language": "Target Language",
    "target_market": "Target Market",
    "localization_level": "Localization Level",
    "rename_characters": "Rename Characters",
    "adapt_culture": "Adapt Culture",
    "adapt_currency": "Adapt Currency",
    "adapt_units": "Adapt Units",
    "adapt_company_names": "Adapt Company Names",
    "adaptation_mode": "Adaptation Mode",
    "narrator_persona": "Narrator Persona",
    "preset_schema_version": "Preset Schema Version",
    "prompt_template_version": "Prompt Template Version",
    "json_output_schema_version": "JSON Output Schema Version",
}


def _lookup_preset(db: Session, preset_id_or_name: str) -> PresetORM | None:
    orm = db.query(PresetORM).filter(PresetORM.id == preset_id_or_name).first()
    if orm:
        return orm
    orm = (
        db.query(PresetORM)
        .filter(PresetORM.name.ilike(preset_id_or_name))
        .first()
    )
    if orm:
        return orm
    # Fallback: full Unicode casefold for accented characters (SQLite ILIKE
    # only folds ASCII A-Z → a-z, not accented letters like Ô→ô or Ệ→ệ).
    target = preset_id_or_name.casefold()
    for row in db.query(PresetORM).all():
        if row.name.casefold() == target:
            return row
    return orm


def compare_presets(
    db: Session, left_id_or_name: str, right_id_or_name: str
) -> PresetCompareResponse:
    left = _lookup_preset(db, left_id_or_name)
    right = _lookup_preset(db, right_id_or_name)

    if left is None:
        raise ValueError(f"Preset bên trái không tìm thấy: {left_id_or_name}")
    if right is None:
        raise ValueError(f"Preset bên phải không tìm thấy: {right_id_or_name}")

    same: list[str] = []
    different: list[PresetCompareDiff] = []

    for field in COMPARE_FIELDS:
        left_val = getattr(left, field, None)
        right_val = getattr(right, field, None)
        label = FIELD_LABELS.get(field, field)
        group = FIELD_TO_GROUP.get(field, "other")

        if left_val == right_val:
            same.append(field)
        else:
            different.append(
                PresetCompareDiff(
                    group=group,
                    field=label,
                    left=_fmt_val(left_val),
                    right=_fmt_val(right_val),
                )
            )

    return PresetCompareResponse(
        left_name=left.name,
        right_name=right.name,
        same=same,
        different=different,
    )


def _fmt_val(val: object) -> str | int | bool:
    if isinstance(val, (int, bool)):
        return val
    return str(val or "")
