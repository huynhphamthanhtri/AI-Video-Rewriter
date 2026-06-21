from __future__ import annotations

from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.preset import PresetORM
from app.schemas.preset import PresetCreate, PresetRead, PresetUpdate


DEFAULT_LOCALIZATION_CONFIG: dict[str, str | bool] = {
    "target_language": "Tiếng Việt", "target_market": "Việt Nam", "localization_level": "medium",
    "rename_characters": True, "adapt_culture": True, "adapt_currency": True, "adapt_units": True,
    "adapt_company_names": True, "adaptation_mode": "localized", "narrator_persona": "neutral_narrator",
}


def preset_payload(**overrides: str | bool) -> dict[str, str | bool]:
    payload = dict(DEFAULT_LOCALIZATION_CONFIG)
    payload.update(overrides)
    return payload


BUILTIN_PRESETS: list[dict[str, str | bool]] = [
    preset_payload(id="builtin-mac-dinh", name="Mặc Định", description="Preset đa năng, chất lượng cao, phù hợp mọi thể loại nội dung.", rewrite_style="Storytelling", target_audience="Đại chúng", tone="Thân thiện", target_duration="3-5 phút", retention_mode="Cao", hook_style="Cảnh đắt giá", clip_strategy="Giữ đầy đủ ngữ cảnh", reuse_level="Trung bình", content_density="Trung bình", is_builtin=True),
    preset_payload(id="builtin-tiktok-viral-60s", name="TikTok Viral 60s", description="Nội dung viral chất lượng, nhịp nhanh nhưng có chiều sâu.", rewrite_style="Viral", target_audience="Đại chúng", tone="Năng lượng cao", target_duration="1-3 phút", retention_mode="Cao", hook_style="Cảnh đắt giá", clip_strategy="Chỉ các đoạn hay nhất", reuse_level="Trung bình", content_density="Trung bình", is_builtin=True, narrator_persona="drama_storyteller"),
    preset_payload(id="builtin-youtube-shorts-review", name="YouTube Shorts Review", description="Review ngắn, tự nhiên, dễ tiếp cận.", rewrite_style="Review chuyên sâu", target_audience="Đại chúng", tone="Thân thiện", target_duration="1-3 phút", retention_mode="Cao", hook_style="Cảnh đắt giá", clip_strategy="Ưu tiên dữ kiện", reuse_level="Trung bình", content_density="Trung bình", is_builtin=True, narrator_persona="neutral_narrator"),
    preset_payload(id="builtin-review-cong-nghe", name="Review Công Nghệ", description="Phân tích công nghệ có chiều sâu, dễ hiểu.", rewrite_style="Chuyên gia phân tích", target_audience="Đại chúng", tone="Chuyên nghiệp", target_duration="5-10 phút", retention_mode="Cao", hook_style="Cảnh đắt giá", clip_strategy="Ưu tiên dữ kiện", reuse_level="Trung bình", content_density="Trung bình", is_builtin=True, narrator_persona="tech_reviewer"),
    preset_payload(id="builtin-podcast-tom-tat", name="Podcast Tóm Tắt", description="Tóm lược podcast mạch lạc.", rewrite_style="Podcast", target_audience="Người mới", tone="Thân thiện", target_duration="10-20 phút", retention_mode="Bình thường", hook_style="Cảnh đắt giá", clip_strategy="Giữ đầy đủ ngữ cảnh", reuse_level="Cao", content_density="Trung bình", is_builtin=True, narrator_persona="podcast_host"),
    preset_payload(id="builtin-documentary-mini", name="Documentary Mini", description="Tư liệu ngắn, mạch lạc và giàu bối cảnh.", rewrite_style="Documentary", target_audience="Đại chúng", tone="Nghiêm túc", target_duration="5-10 phút", retention_mode="Cao", hook_style="Cảnh đắt giá", clip_strategy="Giữ đầy đủ ngữ cảnh", reuse_level="Trung bình", content_density="Cao", is_builtin=True, narrator_persona="teacher"),
    preset_payload(id="builtin-tin-tuc-nhanh", name="Tin Tức Nhanh", description="Bản tin nhanh, chính xác, phù hợp thị trường Việt.", rewrite_style="Tin tức", target_audience="Đại chúng", tone="Chuyên nghiệp", target_duration="1-3 phút", retention_mode="Cao", hook_style="Cảnh đắt giá", clip_strategy="Ưu tiên dữ kiện", reuse_level="Cao", content_density="Trung bình", is_builtin=True, localization_level="medium", rename_characters=False, adapt_culture=False, adapt_company_names=False, adaptation_mode="localized", narrator_persona="news_anchor"),
    preset_payload(id="builtin-us-cops-documentary", name="US COPS Documentary", description="Kể lại documentary/cops reality theo hướng căng thẳng, rõ bối cảnh, tôn trọng dữ kiện.", rewrite_style="Điều tra", target_audience="Đại chúng", tone="Nghiêm túc", target_duration="5-10 phút", retention_mode="Cao", hook_style="Cảnh đắt giá", clip_strategy="Giữ đầy đủ ngữ cảnh", reuse_level="Cao", content_density="Trung bình", is_builtin=True, localization_level="medium", rename_characters=False, adapt_culture=True, adapt_currency=True, adapt_units=True, adapt_company_names=False, adaptation_mode="faithful", narrator_persona="detective"),
    preset_payload(id="builtin-reaction-hai-huoc", name="Reaction Hài Hước", description="Bình luận hài hước, sáng tạo, có chất.", rewrite_style="Hài hước", target_audience="Đại chúng", tone="Hài hước", target_duration="3-5 phút", retention_mode="Cao", hook_style="Cảnh đắt giá", clip_strategy="Ưu tiên cảm xúc", reuse_level="Trung bình", content_density="Trung bình", is_builtin=True, adaptation_mode="inspired", narrator_persona="funny_friend"),
    preset_payload(id="builtin-drama-ke-chuyen", name="Drama Kể Chuyện", description="Kể chuyện kịch tính, cảm xúc, lôi cuốn.", rewrite_style="Drama", target_audience="Đại chúng", tone="Cảm xúc", target_duration="5-10 phút", retention_mode="Cao", hook_style="Cảnh đắt giá", clip_strategy="Ưu tiên câu chuyện", reuse_level="Trung bình", content_density="Trung bình", is_builtin=True, narrator_persona="drama_storyteller"),
    preset_payload(id="builtin-phan-tich-chuyen-gia", name="Phân Tích Chuyên Gia", description="Phân tích sâu sắc, góc nhìn chuyên môn.", rewrite_style="Chuyên gia phân tích", target_audience="Chuyên gia", tone="Chuyên nghiệp", target_duration="5-10 phút", retention_mode="Bình thường", hook_style="Cảnh đắt giá", clip_strategy="Ưu tiên dữ kiện", reuse_level="Trung bình", content_density="Cao", is_builtin=True, narrator_persona="expert_analyst"),
    preset_payload(id="builtin-content-giao-duc", name="Content Giáo Dục", description="Giải thích dễ hiểu, giàu giá trị.", rewrite_style="Storytelling", target_audience="Sinh viên", tone="Thân thiện", target_duration="5-10 phút", retention_mode="Cao", hook_style="Cảnh đắt giá", clip_strategy="Giữ đầy đủ ngữ cảnh", reuse_level="Cao", content_density="Trung bình", is_builtin=True, narrator_persona="teacher"),
    preset_payload(id="builtin-nha-dau-tu", name="Nhà Đầu Tư", description="Phân tích thị trường, cơ hội đầu tư.", rewrite_style="Chuyên gia phân tích", target_audience="Nhà đầu tư", tone="Chuyên nghiệp", target_duration="5-10 phút", retention_mode="Cao", hook_style="Cảnh đắt giá", clip_strategy="Ưu tiên dữ kiện", reuse_level="Trung bình", content_density="Cao", is_builtin=True, narrator_persona="investor"),
    preset_payload(id="builtin-marketing-case-study", name="Marketing Case Study", description="Phân tích case study marketing thực tế.", rewrite_style="Storytelling", target_audience="Marketer", tone="Chuyên nghiệp", target_duration="3-5 phút", retention_mode="Cao", hook_style="Cảnh đắt giá", clip_strategy="Ưu tiên dữ kiện", reuse_level="Trung bình", content_density="Trung bình", is_builtin=True, narrator_persona="expert_analyst"),
    preset_payload(id="builtin-tranh-luan-goc-nhin-trai-chieu", name="Tranh Luận/Góc Nhìn Trái Chiều", description="Góc nhìn đa chiều, phân tích trái ngược.", rewrite_style="Tranh luận", target_audience="Đại chúng", tone="Năng lượng cao", target_duration="5-10 phút", retention_mode="Cao", hook_style="Cảnh đắt giá", clip_strategy="Giữ đầy đủ ngữ cảnh", reuse_level="Trung bình", content_density="Trung bình", is_builtin=True, narrator_persona="detective"),
]


class PresetNotFoundError(ValueError):
    pass


class PresetProtectedError(ValueError):
    pass


class PresetConflictError(ValueError):
    pass


PRESET_CONFLICT_RULES: list[tuple[str, str, str]] = [
    ("reuse_level == 'Cao' and adaptation_mode == 'inspired'",
     "reuse_level", "Bạn đang yêu cầu giữ lại nhiều nội dung gốc (reuse=Cao) nhưng adaptation_mode là inspired (lấy cảm hứng). Hai lựa chọn này có thể mâu thuẫn."),
    ("adaptation_mode == 'faithful' and rename_characters == True",
     "adaptation_mode", "Faithful mode thường không nên đổi tên nhân vật."),
    ("localization_level != 'none' and target_language == ''",
     "localization_level", "Localize cần target_language."),
    ("localization_level != 'none' and target_market == ''",
     "localization_level", "Localize cần target_market."),
]


def validate_preset_conflicts(data: dict[str, object]) -> list[dict[str, str]]:
    """Check for logical conflicts in preset field values.
    Returns list of {field, message} warnings.
    """
    warnings: list[dict[str, str]] = []
    for condition, field, message in PRESET_CONFLICT_RULES:
        try:
            if eval(condition, {"__builtins__": {}}, dict(data)):
                warnings.append({"field": field, "message": message})
        except Exception:
            pass

    # Duration-based checks
    dur = str(data.get("target_duration", ""))
    short_dur = any(kw in dur.lower() for kw in ["1-3", "30", "60", "< 2"])
    density = str(data.get("content_density", ""))
    if short_dur and density == "Cao":
        warnings.append({"field": "content_density", "message": "Video ngắn khó chứa nội dung mật độ cao, cân nhắc giảm density."})

    clip = str(data.get("clip_strategy", ""))
    if short_dur and "ngữ cảnh" in clip:
        warnings.append({"field": "clip_strategy", "message": "Clip strategy 'Giữ đầy đủ ngữ cảnh' không phù hợp với video ngắn."})

    reuse = str(data.get("reuse_level", ""))
    if reuse in ("Thấp", "Rất thấp") and "ngữ cảnh" in clip:
        warnings.append({"field": "reuse_level", "message": "Reuse thấp nhưng clip strategy giữ nguyên cảnh gốc — có thể không đủ素材."})

    return warnings


class PresetService:
    def __init__(self, db: Session):
        self.db = db

    def seed_builtin_presets(self) -> None:
        self.sync_builtin_presets()

    def builtin_sync_status(self) -> dict:
        existing = {preset.id: preset for preset in self.db.scalars(select(PresetORM).where(PresetORM.is_builtin.is_(True))).all()}
        expected_ids = {str(preset["id"]) for preset in BUILTIN_PRESETS}
        missing: list[dict[str, str]] = []
        outdated: list[dict[str, object]] = []
        extra = sorted(set(existing) - expected_ids)

        for preset in BUILTIN_PRESETS:
            preset_id = str(preset["id"])
            current = existing.get(preset_id)
            if current is None:
                missing.append({"id": preset_id, "name": str(preset.get("name", preset_id))})
                continue
            differences = []
            for key, expected_value in preset.items():
                if getattr(current, key) != expected_value:
                    differences.append(key)
            if differences:
                outdated.append({"id": preset_id, "name": str(preset.get("name", preset_id)), "fields": differences})

        return {
            "expected_count": len(BUILTIN_PRESETS),
            "db_builtin_count": len(existing),
            "missing": missing,
            "outdated": outdated,
            "extra_builtin_ids": extra,
            "in_sync": not missing and not outdated and not extra,
        }

    def sync_builtin_presets(self) -> dict:
        existing = {preset.id: preset for preset in self.db.scalars(select(PresetORM).where(PresetORM.is_builtin.is_(True))).all()}
        inserted = 0
        updated = 0
        for preset in BUILTIN_PRESETS:
            preset_id = str(preset["id"])
            if preset_id in existing:
                changed = False
                for key, value in preset.items():
                    if getattr(existing[preset_id], key) != value:
                        setattr(existing[preset_id], key, value)
                        changed = True
                if changed:
                    updated += 1
            else:
                self.db.add(PresetORM(**preset))
                inserted += 1
        self.db.commit()
        status = self.builtin_sync_status()
        return {"inserted": inserted, "updated": updated, "status": status}

    def list_presets(self) -> list[PresetRead]:
        presets = self.db.scalars(select(PresetORM).order_by(PresetORM.is_builtin.desc(), PresetORM.name.asc())).all()
        return [PresetRead.model_validate(preset, from_attributes=True) for preset in presets]

    def create_preset(self, payload: PresetCreate) -> PresetRead:
        preset = PresetORM(id=str(uuid4()), is_builtin=False, **payload.model_dump())
        self.db.add(preset)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise PresetConflictError("Tên preset đã tồn tại.") from exc
        self.db.refresh(preset)
        return PresetRead.model_validate(preset, from_attributes=True)

    def update_preset(self, preset_id: str, payload: PresetUpdate) -> PresetRead:
        preset = self.db.get(PresetORM, preset_id)
        if preset is None:
            raise PresetNotFoundError("Không tìm thấy preset cần cập nhật.")
        if preset.is_builtin:
            raise PresetProtectedError("Không được sửa preset mặc định.")
        for key, value in payload.model_dump().items():
            setattr(preset, key, value)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise PresetConflictError("Tên preset đã tồn tại.") from exc
        self.db.refresh(preset)
        return PresetRead.model_validate(preset, from_attributes=True)

    def delete_preset(self, preset_id: str) -> None:
        preset = self.db.get(PresetORM, preset_id)
        if preset is None:
            raise PresetNotFoundError("Không tìm thấy preset cần xóa.")
        if preset.is_builtin:
            raise PresetProtectedError("Không được xóa preset mặc định.")
        self.db.delete(preset)
        self.db.commit()
