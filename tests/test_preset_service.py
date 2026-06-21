import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.versions import (
    CURRENT_JSON_OUTPUT_SCHEMA_VERSION,
    CURRENT_PRESET_SCHEMA_VERSION,
    CURRENT_PROMPT_TEMPLATE_VERSION,
)
from app.models.preset import PresetORM
from app.schemas.preset import PresetCreate
from app.services.preset_service import PresetConflictError, PresetProtectedError, PresetService
from app.services.preset_service import BUILTIN_PRESETS, validate_preset_conflicts


def preset_payload(name: str = "Preset A") -> PresetCreate:
    return PresetCreate(
        name=name,
        description="",
        rewrite_style="Drama",
        target_audience="Đại chúng",
        tone="Hài hước",
        target_duration="1-3 phút",
        retention_mode="Cao",
        hook_style="Gây sốc",
        clip_strategy="Giữ đầy đủ ngữ cảnh",
        reuse_level="Trung bình",
        content_density="Trung bình",
    )


@pytest.fixture()
def service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        yield PresetService(db)


def test_create_preset_rejects_duplicate_name(service: PresetService):
    service.create_preset(preset_payload("Duplicate"))

    with pytest.raises(PresetConflictError, match="Tên preset"):
        service.create_preset(preset_payload("Duplicate"))


def test_update_builtin_preset_is_rejected(service: PresetService):
    service.db.add(PresetORM(id="builtin", is_builtin=True, **preset_payload("Builtin").model_dump()))
    service.db.commit()

    with pytest.raises(PresetProtectedError, match="preset mặc định"):
        service.update_preset("builtin", preset_payload("Updated"))


def test_builtin_presets_required_fields():
    for preset in BUILTIN_PRESETS:
        assert preset.get("name"), f"Builtin preset {preset.get('id')} missing name"
        assert preset.get("rewrite_style"), f"Builtin preset {preset.get('id')} missing rewrite_style"
        assert preset.get("target_audience"), f"Builtin preset {preset.get('id')} missing target_audience"
        assert preset.get("tone"), f"Builtin preset {preset.get('id')} missing tone"
        assert preset.get("target_duration"), f"Builtin preset {preset.get('id')} missing target_duration"


def test_builtin_presets_have_unique_ids():
    ids = [p["id"] for p in BUILTIN_PRESETS]
    assert len(ids) == len(set(ids)), "Builtin preset IDs must be unique"


def test_preset_create_defaults_to_current_versions(service: PresetService):
    created = service.create_preset(preset_payload("VersionTest"))
    assert created.preset_schema_version == CURRENT_PRESET_SCHEMA_VERSION
    assert created.prompt_template_version == CURRENT_PROMPT_TEMPLATE_VERSION
    assert created.json_output_schema_version == CURRENT_JSON_OUTPUT_SCHEMA_VERSION


def test_conflict_validator_reuse_adaptation_conflict():
    warnings = validate_preset_conflicts({
        "reuse_level": "Cao", "adaptation_mode": "inspired",
        "localization_level": "none", "target_language": "Tiếng Việt", "target_market": "Việt Nam",
        "target_duration": "5-10 phút", "content_density": "Trung bình", "clip_strategy": "Giữ đầy đủ ngữ cảnh",
        "reuse_level": "Cao",
    })
    messages = [w["message"] for w in warnings]
    assert any("reuse" in m.lower() and "inspired" in m.lower() for m in messages)


def test_conflict_validator_faithful_rename_conflict():
    warnings = validate_preset_conflicts({
        "adaptation_mode": "faithful", "rename_characters": True,
        "localization_level": "none", "target_language": "Tiếng Việt", "target_market": "Việt Nam",
        "target_duration": "5-10 phút", "content_density": "Trung bình", "clip_strategy": "Giữ đầy đủ ngữ cảnh",
        "reuse_level": "Trung bình",
    })
    messages = [w["message"] for w in warnings]
    assert any("faithful" in m.lower() and "đổi tên" in m.lower() for m in messages)


def test_conflict_validator_short_duration_high_density():
    warnings = validate_preset_conflicts({
        "target_duration": "1-3 phút", "content_density": "Cao",
        "localization_level": "none", "target_language": "Tiếng Việt", "target_market": "Việt Nam",
        "clip_strategy": "Chỉ các đoạn hay nhất", "reuse_level": "Trung bình",
    })
    messages = [w["message"] for w in warnings]
    assert any("density" in m.lower() for m in messages)


def test_conflict_validator_no_false_positives():
    warnings = validate_preset_conflicts({
        "reuse_level": "Trung bình", "adaptation_mode": "localized",
        "localization_level": "medium", "target_language": "Tiếng Việt", "target_market": "Việt Nam",
        "target_duration": "5-10 phút", "content_density": "Trung bình",
        "clip_strategy": "Chỉ các đoạn hay nhất", "rename_characters": False,
    })
    assert len(warnings) == 0


def test_conflict_validator_does_not_use_unknown_values():
    data = {
        "reuse_level": "Cao", "adaptation_mode": "localized",
        "localization_level": "none", "target_language": "", "target_market": "",
        "rewrite_style": "Sáng tạo hoàn toàn",
        "target_duration": "5-10 phút", "content_density": "Trung bình", "clip_strategy": "Giữ đầy đủ ngữ cảnh",
    }
    warnings = validate_preset_conflicts(data)
    for w in warnings:
        assert "Sáng tạo" not in w["message"] and "Highly Original" not in w["message"]
