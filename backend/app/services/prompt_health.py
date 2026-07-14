from __future__ import annotations

from typing import Literal


PromptHealthLevel = Literal["excellent", "good", "risky", "weak"]


def _level_for_score(score: int) -> PromptHealthLevel:
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 50:
        return "risky"
    return "weak"


def score_preset_health(data: dict[str, object]) -> dict:
    details: list[dict] = []
    warnings: list[str] = []
    strengths: list[str] = []

    def add(factor: str, label: str, value: object, impact: int, reason: str) -> None:
        details.append({
            "factor": factor,
            "label": label,
            "value": str(value or ""),
            "impact": impact,
            "reason": reason,
        })
        if impact > 0:
            strengths.append(reason)
        elif impact < 0:
            warnings.append(reason)

    rewrite_style = str(data.get("rewrite_style") or "").lower()
    target_audience = str(data.get("target_audience") or "").lower()
    tone = str(data.get("tone") or "").lower()
    duration = str(data.get("target_duration") or "").lower()
    retention = str(data.get("retention_mode") or "").lower()
    hook = str(data.get("hook_style") or "").lower()
    clip = str(data.get("clip_strategy") or "").lower()
    reuse = str(data.get("reuse_level") or "").lower()
    density = str(data.get("content_density") or "").lower()
    language = str(data.get("target_language") or "").strip()
    market = str(data.get("target_market") or "").strip()
    localization = str(data.get("localization_level") or "").lower()
    adaptation = str(data.get("adaptation_mode") or "").lower()
    narrator = str(data.get("narrator_persona") or "").lower()

    if any(token in rewrite_style for token in ("điều tra", "story", "drama", "case")):
        add("rewrite_style", "Rewrite style", data.get("rewrite_style"), 10, "Phong cách remake có định hướng kể chuyện rõ.")
    elif "giữ nguyên" in rewrite_style:
        add("rewrite_style", "Rewrite style", data.get("rewrite_style"), -12, "Phong cách quá gần bản gốc, giảm tính remake.")

    if "chuyên gia" in target_audience or "đại chúng" in target_audience:
        add("target_audience", "Audience", data.get("target_audience"), 6, "Đối tượng xem rõ ràng.")
    if any(token in tone for token in ("nghiêm", "thân thiện", "hài", "kịch")):
        add("tone", "Tone", data.get("tone"), 5, "Tone phù hợp để dẫn chuyện nhất quán.")

    if "tự đề xuất" in duration or not duration:
        add("target_duration", "Duration", data.get("target_duration"), -12, "Thời lượng chưa cụ thể, dễ sinh kịch bản lan man.")
    elif any(token in duration for token in ("1-3", "3-5", "5-10")):
        add("target_duration", "Duration", data.get("target_duration"), 7, "Thời lượng mục tiêu rõ.")

    if "cực cao" in retention:
        add("retention_mode", "Retention", data.get("retention_mode"), 10, "Retention cao giúp ưu tiên hook và nhịp dựng.")
    elif "cao" in retention:
        add("retention_mode", "Retention", data.get("retention_mode"), 7, "Retention đủ tốt cho remake.")
    elif "bình" in retention:
        add("retention_mode", "Retention", data.get("retention_mode"), -6, "Retention bình thường có thể thiếu lực giữ người xem.")

    if "cảnh đắt" in hook or "tò mò" in hook:
        add("hook_style", "Hook", data.get("hook_style"), 8, "Hook có điểm neo hấp dẫn.")
    elif "kể chuyện" in hook:
        add("hook_style", "Hook", data.get("hook_style"), -3, "Hook kể chuyện chung chung, ít tạo cú kéo đầu video.")

    if "giữ đầy đủ" in clip or "dữ kiện" in clip:
        add("clip_strategy", "Clip strategy", data.get("clip_strategy"), 6, "Chiến lược clip có tiêu chí giữ ngữ cảnh.")
    if "cao" in reuse:
        add("reuse_level", "Reuse", data.get("reuse_level"), -10, "Reuse cao dễ làm video quá nguyên bản.")
    elif "trung" in reuse or "thấp" in reuse:
        add("reuse_level", "Reuse", data.get("reuse_level"), 5, "Mức reuse an toàn cho remake.")
    if "cao" in density:
        add("content_density", "Content density", data.get("content_density"), 4, "Mật độ nội dung cao giúp video có nhiều điểm kể.")
    elif "thấp" in density:
        add("content_density", "Content density", data.get("content_density"), -6, "Mật độ thấp dễ thiếu chất liệu dựng.")

    if language:
        add("target_language", "Language", language, 5, "Ngôn ngữ đầu ra rõ.")
    else:
        add("target_language", "Language", language, -12, "Thiếu ngôn ngữ đầu ra.")
    if market:
        add("target_market", "Market", market, 4, "Thị trường mục tiêu rõ.")
    else:
        add("target_market", "Market", market, -8, "Thiếu thị trường mục tiêu.")
    if localization in {"medium", "heavy"} or adaptation == "localized":
        add("localization", "Localization", localization or adaptation, 7, "Có bản địa hóa để kịch bản tự nhiên hơn.")
    elif localization == "none" and adaptation == "faithful":
        add("localization", "Localization", localization, -8, "Thiếu bản địa hóa, dễ khô và xa người xem.")
    if narrator in {"detective", "expert_analyst", "drama_storyteller"}:
        add("narrator_persona", "Narrator", data.get("narrator_persona"), 8, "Persona dẫn chuyện có màu sắc rõ.")

    score = max(0, min(100, 50 + sum(item["impact"] for item in details)))
    return {
        "score": score,
        "level": _level_for_score(score),
        "warnings": warnings,
        "strengths": strengths,
        "details": details,
    }
