from __future__ import annotations

from typing import Literal

from app.services.preset_service import validate_preset_conflicts


PromptHealthLevel = Literal["excellent", "good", "risky", "weak"]


def _level_for_score(score: int) -> PromptHealthLevel:
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 50:
        return "risky"
    return "weak"


SPECIFIC_REWRITE_STYLES = [
    "Chuyên gia phân tích", "Storytelling", "Viral", "Drama",
    "Hài hước", "Podcast", "Documentary", "Điều tra",
    "Tin tức", "Review chuyên sâu", "Tranh luận",
]


def score_preset_health(data: dict[str, object]) -> dict:
    score = 50
    strengths: list[str] = []
    warnings: list[str] = []
    details: list[dict] = []

    # --- Strengths ---

    hook = str(data.get("hook_style", ""))
    retention = str(data.get("retention_mode", ""))
    audience = str(data.get("target_audience", ""))
    loc_level = str(data.get("localization_level", "none"))
    loc_lang = str(data.get("target_language", ""))
    loc_market = str(data.get("target_market", ""))
    persona = str(data.get("narrator_persona", ""))
    rewrite = str(data.get("rewrite_style", ""))
    duration = str(data.get("target_duration", ""))
    tone = str(data.get("tone", ""))
    density = str(data.get("content_density", ""))
    clip = str(data.get("clip_strategy", ""))
    reuse = str(data.get("reuse_level", ""))
    adaptation = str(data.get("adaptation_mode", ""))

    if hook and hook not in ("Kể chuyện",):
        score += 10
        strengths.append("Hook được chọn cụ thể, có chủ đích.")
        details.append({
            "factor": "hook_style",
            "label": "Hook Style",
            "value": hook,
            "impact": 10,
            "reason": f"Hook cụ thể ({hook}): +10 điểm",
        })
    else:
        details.append({
            "factor": "hook_style",
            "label": "Hook Style",
            "value": hook or "(trống)",
            "impact": 0,
            "reason": "Hook mặc định hoặc không có: 0 điểm",
        })

    if retention in ("Cao", "Cực cao"):
        score += 10
        strengths.append("Chiến lược giữ chân người xem mạnh.")
        details.append({
            "factor": "retention_mode",
            "label": "Retention Mode",
            "value": retention,
            "impact": 10,
            "reason": f"Giữ chân {retention}: +10 điểm",
        })
    else:
        details.append({
            "factor": "retention_mode",
            "label": "Retention Mode",
            "value": retention,
            "impact": 0,
            "reason": "Giữ chân ở mức cơ bản: 0 điểm",
        })

    if audience not in ("Đại chúng", ""):
        score += 10
        strengths.append(f"Khán giả mục tiêu được định hướng rõ ({audience}).")
        details.append({
            "factor": "target_audience",
            "label": "Target Audience",
            "value": audience,
            "impact": 10,
            "reason": f"Audience cụ thể ({audience}): +10 điểm",
        })
    else:
        details.append({
            "factor": "target_audience",
            "label": "Target Audience",
            "value": audience or "(đại chúng)",
            "impact": 0,
            "reason": "Audience đại chúng: 0 điểm",
        })

    if loc_level != "none" and loc_lang and loc_market:
        score += 10
        strengths.append("Thông tin bản địa hóa đầy đủ (ngôn ngữ + thị trường).")
        details.append({
            "factor": "localization",
            "label": "Localization",
            "value": f"{loc_lang}/{loc_market}/{loc_level}",
            "impact": 10,
            "reason": "Bản địa hóa đầy đủ: +10 điểm",
        })
    else:
        details.append({
            "factor": "localization",
            "label": "Localization",
            "value": f"{loc_lang}/{loc_market}/{loc_level}",
            "impact": 0,
            "reason": "Thiếu thông tin bản địa hóa: 0 điểm",
        })

    if persona and persona != "neutral_narrator":
        score += 10
        strengths.append(f"Persona người kể chuyện được chọn cụ thể ({persona}).")
        details.append({
            "factor": "narrator_persona",
            "label": "Narrator Persona",
            "value": persona,
            "impact": 10,
            "reason": f"Persona cụ thể ({persona}): +10 điểm",
        })
    else:
        details.append({
            "factor": "narrator_persona",
            "label": "Narrator Persona",
            "value": persona or "neutral_narrator",
            "impact": 0,
            "reason": "Persona mặc định: 0 điểm",
        })

    if rewrite in SPECIFIC_REWRITE_STYLES:
        score += 10
        strengths.append(f"Phong cách viết lại có định hướng rõ ({rewrite}).")
        details.append({
            "factor": "rewrite_style",
            "label": "Rewrite Style",
            "value": rewrite,
            "impact": 10,
            "reason": f"Style cụ thể ({rewrite}): +10 điểm",
        })
    else:
        details.append({
            "factor": "rewrite_style",
            "label": "Rewrite Style",
            "value": rewrite or "(trống)",
            "impact": 0,
            "reason": "Style mặc định hoặc chung chung: 0 điểm",
        })

    # --- Warnings ---

    if duration in ("Tự đề xuất thời lượng phù hợp với kịch bản remake", ""):
        score -= 10
        warnings.append("Chưa chọn thời lượng mục tiêu. Đề xuất chọn cụ thể để tối ưu prompt.")
        details.append({
            "factor": "target_duration",
            "label": "Target Duration",
            "value": duration or "(trống)",
            "impact": -10,
            "reason": "Chưa chọn thời lượng: -10 điểm",
        })
    else:
        details.append({
            "factor": "target_duration",
            "label": "Target Duration",
            "value": duration,
            "impact": 0,
            "reason": f"Thời lượng cụ thể ({duration}): 0 điểm",
        })

    if tone in ("Thân thiện", ""):
        score -= 5
        warnings.append("Giọng điệu đang ở mức mặc định hoặc chung chung.")
        details.append({
            "factor": "tone",
            "label": "Tone",
            "value": tone or "(trống)",
            "impact": -5,
            "reason": "Giọng điệu mặc định/chung chung: -5 điểm",
        })
    else:
        details.append({
            "factor": "tone",
            "label": "Tone",
            "value": tone,
            "impact": 0,
            "reason": f"Giọng điệu cụ thể ({tone}): 0 điểm",
        })

    # Add conflict validator warnings
    conflict_warnings = validate_preset_conflicts(data)
    for cw in conflict_warnings:
        score -= 10
        warnings.append(cw["message"])
        details.append({
            "factor": "conflict",
            "label": "Conflict",
            "value": cw.get("field", ""),
            "impact": -10,
            "reason": cw["message"],
        })

    score = max(0, min(100, score))

    return {
        "score": score,
        "level": _level_for_score(score),
        "warnings": warnings,
        "strengths": strengths,
        "details": details,
    }
