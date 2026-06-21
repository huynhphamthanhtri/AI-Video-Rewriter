from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.preset import PresetORM
from app.services.preset_compare import compare_presets


def _engine():
    return create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})


def _presets() -> list[PresetORM]:
    return [
        PresetORM(
            id="p1", name="Preset A",
            rewrite_style="Storytelling", target_audience="Đại chúng", tone="Thân thiện",
            target_duration="3-5 phút", retention_mode="Cao", hook_style="Cảnh đắt giá",
            clip_strategy="Giữ đầy đủ ngữ cảnh", reuse_level="Trung bình", content_density="Trung bình",
            target_language="Tiếng Việt", target_market="Việt Nam", localization_level="medium",
            rename_characters=True, adapt_culture=True, adapt_currency=True,
            adapt_units=True, adapt_company_names=True, adaptation_mode="localized",
            narrator_persona="neutral_narrator",
            preset_schema_version=1, prompt_template_version=1, json_output_schema_version=1,
        ),
        PresetORM(
            id="p2", name="Preset B",
            rewrite_style="Điều tra", target_audience="Chuyên gia", tone="Nghiêm túc",
            target_duration="10-15 phút", retention_mode="Cực cao", hook_style="Cảnh đắt giá",
            clip_strategy="Giữ đầy đủ ngữ cảnh", reuse_level="Cao", content_density="Cao",
            target_language="Tiếng Việt", target_market="Việt Nam", localization_level="high",
            rename_characters=True, adapt_culture=True, adapt_currency=True,
            adapt_units=True, adapt_company_names=False, adaptation_mode="localized",
            narrator_persona="detective",
            preset_schema_version=1, prompt_template_version=1, json_output_schema_version=1,
        ),
    ]


def _session() -> tuple[Session, list[PresetORM]]:
    engine = _engine()
    Base.metadata.create_all(bind=engine)
    session: Session = sessionmaker(bind=engine)()
    objs = _presets()
    session.add_all(objs)
    session.commit()
    return session, objs


def test_compare_same_preset_returns_all_same():
    session, _ = _session()
    try:
        result = compare_presets(db=session, left_id_or_name="p1", right_id_or_name="p1")
        assert len(result.different) == 0
        assert len(result.same) > 0
    finally:
        session.close()


def test_compare_different_presets_returns_diffs():
    session, _ = _session()
    try:
        result = compare_presets(db=session, left_id_or_name="p1", right_id_or_name="p2")
        assert len(result.different) > 0
        for d in result.different:
            assert d.group
            assert d.field
            assert d.left != d.right
    finally:
        session.close()


def test_compare_by_name():
    session, _ = _session()
    try:
        result = compare_presets(db=session, left_id_or_name="Preset A", right_id_or_name="Preset B")
        assert len(result.different) > 0
    finally:
        session.close()


def test_compare_case_insensitive():
    session, _ = _session()
    try:
        result = compare_presets(db=session, left_id_or_name="PRESET A", right_id_or_name="preset a")
        assert len(result.different) == 0
    finally:
        session.close()


def test_compare_returns_grouped_diffs():
    session, _ = _session()
    try:
        result = compare_presets(db=session, left_id_or_name="p1", right_id_or_name="p2")
        groups = {d.group for d in result.different}
        for g in groups:
            assert g in ("intent", "strategy", "constraints", "localization", "versioning")
    finally:
        session.close()


def test_compare_not_found():
    session, _ = _session()
    try:
        with pytest.raises(ValueError):
            compare_presets(db=session, left_id_or_name="nonexistent", right_id_or_name="p1")
    finally:
        session.close()


def test_compare_returns_names():
    session, _ = _session()
    try:
        result = compare_presets(db=session, left_id_or_name="p1", right_id_or_name="p2")
        assert result.left_name == "Preset A"
        assert result.right_name == "Preset B"
    finally:
        session.close()


# ── Robustness: Unicode / case-insensitive Vietnamese ──

def _session_with_vietnamese() -> tuple[Session, PresetORM]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session: Session = sessionmaker(bind=engine)()
    preset = PresetORM(
        id="vn1", name="review công nghệ",
        rewrite_style="Storytelling", target_audience="Đại chúng", tone="Thân thiện",
        target_duration="3-5 phút", retention_mode="Cao", hook_style="Cảnh đắt giá",
        clip_strategy="Giữ đầy đủ ngữ cảnh", reuse_level="Trung bình", content_density="Trung bình",
    )
    session.add(preset)
    session.commit()
    return session, preset


def test_compare_vietnamese_case_ascii_only():
    """ASCII case change (r→R, c→C) — ILIKE handles this natively."""
    session, preset = _session_with_vietnamese()
    try:
        result = compare_presets(db=session, left_id_or_name="Review Công Nghệ", right_id_or_name=preset.id)
        assert result.left_name == preset.name
    finally:
        session.close()


def test_compare_vietnamese_uppercase_accented():
    """Full uppercase with accented chars (Ô, Ệ) — must still match via casefold fallback."""
    session, preset = _session_with_vietnamese()
    try:
        result = compare_presets(db=session, left_id_or_name="REVIEW CÔNG NGHỆ", right_id_or_name=preset.id)
        assert result.left_name == preset.name
    finally:
        session.close()


def test_compare_vietnamese_mixed_case_accented():
    """Mixed-case accented: 'REVIEW công nghệ' — ASCII 'REVIEW' folded by ILIKE or casefold."""
    session, preset = _session_with_vietnamese()
    try:
        result = compare_presets(db=session, left_id_or_name="REVIEW công nghệ", right_id_or_name=preset.id)
        assert result.left_name == preset.name
    finally:
        session.close()
