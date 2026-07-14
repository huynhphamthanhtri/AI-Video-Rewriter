from __future__ import annotations

import re
from typing import Any


MIN_ANALYSIS_SEGMENTS = 10
MIN_ANALYSIS_SEGMENTS_LONG = 12
_SOURCE_TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}$")
_VALID_STORY_ROLES = {"opening", "setup", "progression", "climax", "ending", "context", "payoff", "hook"}
_STORY_ROLE_ALIASES = {
    "action": "progression",
    "emotion": "context",
    "intro": "opening",
    "introduction": "opening",
    "initial": "opening",
    "beginning": "opening",
    "lead_in": "opening",
    "lead-in": "opening",
    "exposition": "setup",
    "background": "context",
    "middle": "progression",
    "main_event": "progression",
    "main-event": "progression",
    "conflict": "progression",
    "challenge": "progression",
    "demo": "progression",
    "demonstration": "progression",
    "development": "progression",
    "build_up": "progression",
    "build-up": "progression",
    "rising_action": "progression",
    "rising-action": "progression",
    "turning_point": "climax",
    "turning-point": "climax",
    "test": "climax",
    "final_test": "climax",
    "final-test": "climax",
    "peak": "climax",
    "reveal": "payoff",
    "final_reveal": "payoff",
    "final-reveal": "payoff",
    "ending_payoff": "payoff",
    "ending-payoff": "payoff",
    "result": "payoff",
    "resolution": "ending",
    "conclusion": "ending",
    "closing": "ending",
    "outro": "ending",
}


def _source_timestamp_to_seconds(value: str) -> float | None:
    if not isinstance(value, str) or not _SOURCE_TIMESTAMP_RE.match(value):
        return None
    hms, ms = value.split(".")
    try:
        h, m, s = [int(part) for part in hms.split(":")]
    except ValueError:
        return None
    return float((((h * 60) + m) * 60) + s) + (int(ms) / 1000)


def _flexible_timestamp_to_seconds(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    exact = _source_timestamp_to_seconds(text)
    if exact is not None:
        return exact
    if re.match(r"^\d{2}:\d{2}:\d{2}$", text):
        try:
            h, m, s = [int(part) for part in text.split(":")]
        except ValueError:
            return None
        return float((((h * 60) + m) * 60) + s)
    if re.match(r"^\d{1,2}:\d{2}$", text):
        try:
            m, s = [int(part) for part in text.split(":")]
        except ValueError:
            return None
        return float((m * 60) + s)
    return None


def _is_markdown_url(value: object) -> bool:
    return isinstance(value, str) and ("[" in value or "](" in value or "]" in value)


def _normalize_story_role(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    role = value.strip().lower().replace(" ", "_")
    if role in _VALID_STORY_ROLES:
        return role
    return _STORY_ROLE_ALIASES.get(role)


def _normalize_analysis_v2(payload: dict) -> dict:
    if isinstance(payload.get("scene_beats"), list):
        payload["analysis_version"] = 2
    story = payload.get("story_summary")
    if isinstance(story, str):
        payload["story_summary"] = {"overview": story}
    elif not isinstance(story, dict):
        overall = payload.get("overall_summary")
        payload["story_summary"] = {"overview": overall if isinstance(overall, str) else ""}
    beats = payload.get("scene_beats")
    if isinstance(beats, list):
        for index, beat in enumerate(beats, start=1):
            if not isinstance(beat, dict):
                continue
            if not isinstance(beat.get("beat_id"), str) or not beat.get("beat_id", "").strip():
                beat["beat_id"] = f"b{index:03d}"
            if "dialogue_or_narration" not in beat:
                beat["dialogue_or_narration"] = ""
    return payload


def _analysis_segment_count(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    segments = payload.get("segments")
    return len(segments) if isinstance(segments, list) else 0


def minimum_analysis_segments(latest_end_seconds: float) -> int:
    if latest_end_seconds < 90:
        return 5
    if latest_end_seconds < 180:
        return 6
    if latest_end_seconds < 360:
        return 7
    if latest_end_seconds < 600:
        return 8
    return MIN_ANALYSIS_SEGMENTS


def validate_analysis_payload(payload: object) -> tuple[bool, list[str], dict | None]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["Analysis root must be an object."], None

    if payload.get("analysis_version") == 2 or isinstance(payload.get("scene_beats"), list):
        return _validate_analysis_v2(_normalize_analysis_v2(payload))

    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("sources must be a non-empty list.")
        sources = []
    source_ids: set[str] = set()
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            errors.append(f"sources[{index}] must be an object.")
            continue
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            errors.append(f"sources[{index}].source_id is required.")
        else:
            source_ids.add(source_id)
        youtube_url = source.get("youtube_url")
        if _is_markdown_url(youtube_url):
            errors.append(f"sources[{index}].youtube_url must not be a Markdown link.")
        elif not isinstance(youtube_url, str) or not youtube_url.startswith("http"):
            errors.append(f"sources[{index}].youtube_url must be a plain URL.")

    story_arc = payload.get("story_arc")
    if not isinstance(story_arc, dict):
        errors.append("story_arc must be an object.")

    segments = payload.get("segments")
    if not isinstance(segments, list):
        errors.append("segments must be a list.")
        segments = []

    roles: set[str] = set()
    latest_end = 0.0
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            errors.append(f"segments[{index}] must be an object.")
            continue
        source_id = segment.get("source_id")
        if source_ids and source_id not in source_ids:
            errors.append(f"segments[{index}].source_id does not reference sources[].")
        start = _source_timestamp_to_seconds(segment.get("start", ""))
        end = _source_timestamp_to_seconds(segment.get("end", ""))
        if start is None:
            errors.append(f"segments[{index}].start must use HH:MM:SS.mmm.")
        if end is None:
            errors.append(f"segments[{index}].end must use HH:MM:SS.mmm.")
        if start is not None and end is not None:
            if start >= end:
                errors.append(f"segments[{index}].start must be before end.")
            latest_end = max(latest_end, end)
        story_role = _normalize_story_role(segment.get("story_role"))
        if story_role is None:
            errors.append(f"segments[{index}].story_role must be one of {sorted(_VALID_STORY_ROLES)}.")
        else:
            segment["story_role"] = story_role
            roles.add(story_role)

    if "setup" not in roles:
        errors.append("segments must include at least one setup segment.")
    if not roles.intersection({"climax", "ending"}):
        errors.append("segments must include at least one climax or ending segment.")
    min_segments = minimum_analysis_segments(latest_end)
    if len(segments) < min_segments:
        errors.append(f"segments must contain at least {min_segments} items for deep analysis.")

    return not errors, errors, payload if not errors else None


def _validate_analysis_v2(payload: dict) -> tuple[bool, list[str], dict | None]:
    errors: list[str] = []
    if payload.get("analysis_version") != 2 and not isinstance(payload.get("scene_beats"), list):
        errors.append("analysis_version must be 2.")
    if any(key in payload for key in ("video_segments", "srt", "rewrite_script")):
        errors.append("analysis must not contain final EDL fields.")
    access = payload.get("source_access")
    if not isinstance(access, dict):
        errors.append("source_access must be an object.")
    elif access.get("can_access_video") is not True:
        errors.append(f"source_access.can_access_video must be true. reason={access.get('reason', '')}")
    source = payload.get("source")
    latest_end = 0.0
    source_duration = 0.0
    if not isinstance(source, dict):
        errors.append("source must be an object.")
    else:
        youtube_url = source.get("youtube_url")
        if _is_markdown_url(youtube_url):
            errors.append("source.youtube_url must not be a Markdown link.")
        elif not isinstance(youtube_url, str) or not youtube_url.startswith("http"):
            errors.append("source.youtube_url must be a plain URL.")
        duration = _flexible_timestamp_to_seconds(source.get("estimated_duration", ""))
        if duration is not None:
            source_duration = duration
    beats = payload.get("scene_beats")
    if not isinstance(beats, list):
        errors.append("scene_beats must be a list.")
        beats = []
    roles: set[str] = set()
    for index, beat in enumerate(beats, start=1):
        if not isinstance(beat, dict):
            errors.append(f"scene_beats[{index}] must be an object.")
            continue
        start = _source_timestamp_to_seconds(beat.get("start", ""))
        end = _source_timestamp_to_seconds(beat.get("end", ""))
        if start is None:
            errors.append(f"scene_beats[{index}].start must use HH:MM:SS.mmm.")
        if end is None:
            errors.append(f"scene_beats[{index}].end must use HH:MM:SS.mmm.")
        if start is not None and end is not None:
            if start >= end:
                errors.append(f"scene_beats[{index}].start must be before end.")
            latest_end = max(latest_end, end)
        role = _normalize_story_role(beat.get("story_role"))
        if role is None:
            errors.append(f"scene_beats[{index}].story_role must be one of {sorted(_VALID_STORY_ROLES)}.")
        else:
            beat["story_role"] = role
            roles.add(role)
        if not isinstance(beat.get("visual_description"), str) or not beat.get("visual_description", "").strip():
            errors.append(f"scene_beats[{index}].visual_description is required.")
    if not roles.intersection({"opening", "setup", "hook"}):
        errors.append("scene_beats must include at least one opening/setup/hook beat.")
    if not roles.intersection({"climax", "ending", "payoff"}):
        errors.append("scene_beats must include at least one climax/ending/payoff beat.")
    min_beats = minimum_analysis_segments(max(source_duration, latest_end))
    if source_duration <= 0:
        source_duration = latest_end
    if source_duration >= 1800:
        min_beats = 10
    elif source_duration >= 600:
        min_beats = 8
    if len(beats) < min_beats:
        errors.append(f"scene_beats must contain at least {min_beats} items for deep analysis.")
    if source_duration >= 600 and latest_end < source_duration * 0.50 and not roles.intersection({"climax", "ending", "payoff"}):
        errors.append("scene_beats must cover the late section of the source video.")
    return not errors, errors, payload if not errors else None


def looks_like_analysis_root(parsed: object) -> bool:
    if not isinstance(parsed, dict) or ("video_segments" in parsed or "srt" in parsed or "rewrite_script" in parsed):
        return False
    if parsed.get("analysis_version") == 2 and isinstance(parsed.get("scene_beats"), list):
        return True
    return isinstance(parsed.get("sources"), list) and isinstance(parsed.get("segments"), list) and ("overall_summary" in parsed or isinstance(parsed.get("story_arc"), dict))


def analysis_segment_count(payload: object) -> int:
    if isinstance(payload, dict) and isinstance(payload.get("scene_beats"), list):
        return len(payload["scene_beats"])
    return _analysis_segment_count(payload)


def analysis_latest_end_seconds(payload: object) -> float:
    if not isinstance(payload, dict):
        return 0.0
    latest = 0.0
    items = payload.get("scene_beats") if isinstance(payload.get("scene_beats"), list) else payload.get("segments")
    if not isinstance(items, list):
        return 0.0
    for segment in items:
        if isinstance(segment, dict):
            end = _source_timestamp_to_seconds(segment.get("end", ""))
            if end is not None:
                latest = max(latest, end)
    return latest
