from __future__ import annotations

import re
from typing import Any


_SOURCE_TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}$")


def _valid_timestamp(value: object) -> bool:
    return isinstance(value, str) and bool(_SOURCE_TIMESTAMP_RE.match(value))


def validate_story_plan_payload(payload: object) -> tuple[bool, list[str], dict | None]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["Story plan root must be an object."], None

    if payload.get("plan_version") != 1:
        errors.append("plan_version must be 1.")

    outline = payload.get("story_outline")
    if not isinstance(outline, list) or not outline or not all(isinstance(item, str) and item.strip() for item in outline):
        errors.append("story_outline must be a non-empty string list.")

    target_structure = payload.get("target_structure")
    if not isinstance(target_structure, dict):
        errors.append("target_structure must be an object.")
    else:
        for key in ("opening", "middle", "climax", "ending"):
            if not isinstance(target_structure.get(key), str) or not target_structure.get(key, "").strip():
                errors.append(f"target_structure.{key} is required.")

    selected = payload.get("selected_moments")
    if not isinstance(selected, list) or not selected:
        errors.append("selected_moments must be a non-empty list.")
        selected = []
    for index, item in enumerate(selected, start=1):
        if not isinstance(item, dict):
            errors.append(f"selected_moments[{index}] must be an object.")
            continue
        if not isinstance(item.get("source_id"), str) or not item.get("source_id"):
            errors.append(f"selected_moments[{index}].source_id is required.")
        if not isinstance(item.get("analysis_index"), int) or item.get("analysis_index") < 1:
            errors.append(f"selected_moments[{index}].analysis_index must be a positive integer.")
        if not _valid_timestamp(item.get("timestamp_hint")):
            errors.append(f"selected_moments[{index}].timestamp_hint must use HH:MM:SS.mmm.")
        if not isinstance(item.get("purpose"), str) or not item.get("purpose", "").strip():
            errors.append(f"selected_moments[{index}].purpose is required.")
        if not isinstance(item.get("voiceover_point"), str) or not item.get("voiceover_point", "").strip():
            errors.append(f"selected_moments[{index}].voiceover_point is required.")

    notes = payload.get("quality_notes", [])
    if notes is not None and not isinstance(notes, list):
        errors.append("quality_notes must be a list when provided.")

    return not errors, errors, payload if not errors else None


def looks_like_story_plan_root(parsed: object) -> bool:
    return (
        isinstance(parsed, dict)
        and parsed.get("plan_version") == 1
        and isinstance(parsed.get("story_outline"), list)
        and isinstance(parsed.get("selected_moments"), list)
        and isinstance(parsed.get("target_structure"), dict)
        and not ("video_segments" in parsed or "srt" in parsed or "rewrite_script" in parsed)
    )


def story_plan_summary(payload: object, errors: list[str] | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"selected_count": 0, "outline_count": 0, "errors": errors or []}
    return {
        "selected_count": len(payload.get("selected_moments") or []),
        "outline_count": len(payload.get("story_outline") or []),
        "errors": errors or [],
    }
