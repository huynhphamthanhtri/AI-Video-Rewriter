from __future__ import annotations

import re
from typing import Any

from app.schemas.render import seconds_to_clip_timestamp, seconds_to_srt_timestamp, srt_timestamp_to_seconds, clip_timestamp_to_seconds


_TS_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}$")
_GENERIC_VISUAL = {"string", "scene", "clip", "video", "cảnh", "đoạn video", "hình ảnh"}


def ts_to_seconds(value: object) -> float | None:
    if not isinstance(value, str) or not _TS_RE.match(value):
        return None
    try:
        return clip_timestamp_to_seconds(value)
    except Exception:
        return None


def _is_non_empty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().lower() not in _GENERIC_VISUAL


def _list_of_dicts(value: object) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def validate_timeline_payload(payload: object) -> tuple[bool, list[str], dict | None]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["Timeline root must be an object."], None
    if payload.get("timeline_version") != 1:
        errors.append("timeline_version must be 1.")
    chapters = _list_of_dicts(payload.get("chapters"))
    if not chapters:
        errors.append("chapters must be a non-empty list.")
    previous_end = -1.0
    latest_end = 0.0
    roles: set[str] = set()
    for index, chapter in enumerate(chapters, start=1):
        if chapter.get("chapter_index") != index:
            errors.append(f"chapters[{index}].chapter_index must be {index}.")
        start = ts_to_seconds(chapter.get("start"))
        end = ts_to_seconds(chapter.get("end"))
        if start is None:
            errors.append(f"chapters[{index}].start must use HH:MM:SS.mmm.")
        if end is None:
            errors.append(f"chapters[{index}].end must use HH:MM:SS.mmm.")
        if start is not None and end is not None:
            if start >= end:
                errors.append(f"chapters[{index}].start must be before end.")
            if previous_end >= 0 and start < previous_end - 2:
                errors.append(f"chapters[{index}] overlaps previous chapter too much.")
            previous_end = max(previous_end, end)
            latest_end = max(latest_end, end)
        role = chapter.get("story_role")
        if isinstance(role, str):
            roles.add(role.lower())
        if not _is_non_empty_text(chapter.get("summary")):
            errors.append(f"chapters[{index}].summary is required.")
        if not _is_non_empty_text(chapter.get("analysis_instruction")):
            errors.append(f"chapters[{index}].analysis_instruction is required.")
    if chapters:
        first_start = ts_to_seconds(chapters[0].get("start"))
        if first_start is not None and first_start > 15:
            errors.append("first chapter should start near the beginning of the source.")
    if latest_end >= 1800 and len(chapters) < 6:
        errors.append("long sources should be split into at least 6 chapters.")
    if "setup" not in roles and chapters:
        errors.append("chapters should include setup.")
    if not roles.intersection({"climax", "ending", "payoff"}) and chapters:
        errors.append("chapters should include climax or ending/payoff.")
    return not errors, errors, payload if not errors else None


def looks_like_timeline_root(parsed: object) -> bool:
    return isinstance(parsed, dict) and parsed.get("timeline_version") == 1 and isinstance(parsed.get("chapters"), list)


def validate_source_access_payload(payload: object) -> tuple[bool, list[str], dict | None]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["Source access root must be an object."], None
    if payload.get("source_access_version") != 1:
        errors.append("source_access_version must be 1.")
    if not isinstance(payload.get("can_access_video"), bool):
        errors.append("can_access_video must be boolean.")
    if not _is_non_empty_text(payload.get("reason")):
        errors.append("reason is required.")
    return not errors, errors, payload if not errors else None


def looks_like_source_access_root(parsed: object) -> bool:
    return isinstance(parsed, dict) and parsed.get("source_access_version") == 1 and "can_access_video" in parsed


def validate_chapter_analysis_payload(payload: object, chapter: dict | None = None) -> tuple[bool, list[str], dict | None]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["Chapter analysis root must be an object."], None
    if payload.get("chapter_analysis_version") != 1:
        errors.append("chapter_analysis_version must be 1.")
    expected_index = chapter.get("chapter_index") if isinstance(chapter, dict) else None
    if expected_index is not None and payload.get("chapter_index") != expected_index:
        errors.append("chapter_index does not match requested chapter.")
    chapter_start = ts_to_seconds(payload.get("chapter_start"))
    chapter_end = ts_to_seconds(payload.get("chapter_end"))
    if chapter_start is None or chapter_end is None or chapter_start >= chapter_end:
        errors.append("chapter_start/chapter_end must be valid timestamps.")
    beats = _list_of_dicts(payload.get("beats"))
    if not beats:
        errors.append("beats must be a non-empty list.")
    for index, beat in enumerate(beats, start=1):
        if not isinstance(beat.get("beat_index"), int) or beat.get("beat_index") < 1:
            errors.append(f"beats[{index}].beat_index must be a positive integer.")
        start = ts_to_seconds(beat.get("start"))
        end = ts_to_seconds(beat.get("end"))
        if start is None or end is None:
            errors.append(f"beats[{index}].start/end must use HH:MM:SS.mmm.")
            continue
        if start >= end:
            errors.append(f"beats[{index}].start must be before end.")
        if chapter_start is not None and start < chapter_start - 2:
            errors.append(f"beats[{index}] starts outside requested chapter.")
        if chapter_end is not None and end > chapter_end + 2:
            errors.append(f"beats[{index}] ends outside requested chapter.")
        if not _is_non_empty_text(beat.get("visual_action")):
            errors.append(f"beats[{index}].visual_action is required.")
        if not _is_non_empty_text(beat.get("what_changes_on_screen")):
            errors.append(f"beats[{index}].what_changes_on_screen is required.")
    chapter_duration = (chapter_end - chapter_start) if chapter_start is not None and chapter_end is not None else 0
    if chapter_duration >= 240 and len(beats) < 3:
        errors.append("long chapters need at least 3 visual beats.")
    return not errors, errors, payload if not errors else None


def looks_like_chapter_analysis_root(parsed: object) -> bool:
    return isinstance(parsed, dict) and parsed.get("chapter_analysis_version") == 1 and isinstance(parsed.get("beats"), list)


def validate_coverage_review_payload(payload: object) -> tuple[bool, list[str], dict | None]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["Coverage review root must be an object."], None
    if payload.get("coverage_review_version") != 1:
        errors.append("coverage_review_version must be 1.")
    if not isinstance(payload.get("passed"), bool):
        errors.append("passed must be boolean.")
    if payload.get("coverage_quality") not in {"strong", "acceptable", "weak"}:
        errors.append("coverage_quality must be strong, acceptable, or weak.")
    if not _is_non_empty_text(payload.get("overall_assessment")):
        errors.append("overall_assessment is required.")
    weak = payload.get("missing_or_weak_chapters", [])
    if weak is not None and not isinstance(weak, list):
        errors.append("missing_or_weak_chapters must be a list.")
    return not errors, errors, payload if not errors else None


def looks_like_coverage_review_root(parsed: object) -> bool:
    return isinstance(parsed, dict) and parsed.get("coverage_review_version") == 1 and "passed" in parsed


def validate_edit_strategy_payload(payload: object) -> tuple[bool, list[str], dict | None]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["Edit strategy root must be an object."], None
    if payload.get("edit_strategy_version") != 1:
        errors.append("edit_strategy_version must be 1.")
    min_d = payload.get("min_acceptable_duration_seconds")
    rec_d = payload.get("recommended_duration_seconds")
    max_d = payload.get("max_acceptable_duration_seconds")
    if not all(isinstance(v, (int, float)) and v > 0 for v in (min_d, rec_d, max_d)):
        errors.append("duration fields must be positive numbers.")
    elif not (min_d <= rec_d <= max_d):
        errors.append("duration fields must satisfy min <= recommended <= max.")
    if not _is_non_empty_text(payload.get("strategy_summary")):
        errors.append("strategy_summary is required.")
    priorities = _list_of_dicts(payload.get("chapter_priorities"))
    if not priorities:
        errors.append("chapter_priorities must be a non-empty list.")
    return not errors, errors, payload if not errors else None


def looks_like_edit_strategy_root(parsed: object) -> bool:
    return isinstance(parsed, dict) and parsed.get("edit_strategy_version") == 1 and "recommended_duration_seconds" in parsed


def validate_story_assembly_payload(payload: object, analyses: list[dict] | None = None, strategy: dict | None = None) -> tuple[bool, list[str], dict | None]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["Story assembly root must be an object."], None
    if payload.get("assembly_version") != 1:
        errors.append("assembly_version must be 1.")
    selected = _list_of_dicts(payload.get("selected_beats"))
    if not selected:
        errors.append("selected_beats must be a non-empty list.")
    known: set[tuple[int, int]] = set()
    if analyses:
        for analysis in analyses:
            chapter_index = analysis.get("chapter_index")
            for beat in _list_of_dicts(analysis.get("beats")):
                if isinstance(chapter_index, int) and isinstance(beat.get("beat_index"), int):
                    known.add((chapter_index, beat["beat_index"]))
    total = 0.0
    chapters: set[int] = set()
    for index, item in enumerate(selected, start=1):
        ci = item.get("chapter_index")
        bi = item.get("beat_index")
        if known and (ci, bi) not in known:
            errors.append(f"selected_beats[{index}] references an unknown beat.")
        if isinstance(ci, int):
            chapters.add(ci)
        seconds = item.get("estimated_screen_time_seconds")
        if isinstance(seconds, (int, float)) and seconds > 0:
            total += float(seconds)
        else:
            errors.append(f"selected_beats[{index}].estimated_screen_time_seconds must be positive.")
        if not _is_non_empty_text(item.get("voiceover_intent")):
            errors.append(f"selected_beats[{index}].voiceover_intent is required.")
        if not _is_non_empty_text(item.get("visual_requirement")):
            errors.append(f"selected_beats[{index}].visual_requirement is required.")
    if strategy and isinstance(strategy.get("min_acceptable_duration_seconds"), (int, float)):
        if total < float(strategy["min_acceptable_duration_seconds"]) * 0.65:
            errors.append("selected beat screen time is far below edit strategy minimum.")
    if len(chapters) < 2 and len(selected) >= 3:
        errors.append("selected beats should not all come from one chapter unless the source is very short.")
    return not errors, errors, payload if not errors else None


def looks_like_story_assembly_root(parsed: object) -> bool:
    return isinstance(parsed, dict) and parsed.get("assembly_version") == 1 and isinstance(parsed.get("selected_beats"), list)


def validate_director_plan_payload(payload: object, analyses: list[dict] | None = None) -> tuple[bool, list[str], dict | None]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["Director plan root must be an object."], None
    if payload.get("director_plan_version") != 1:
        errors.append("director_plan_version must be 1.")
    coverage = payload.get("coverage_assessment")
    if not isinstance(coverage, dict):
        errors.append("coverage_assessment must be an object.")
    elif not isinstance(coverage.get("passed"), bool):
        errors.append("coverage_assessment.passed must be boolean.")
    strategy = payload.get("edit_strategy")
    if not isinstance(strategy, dict):
        errors.append("edit_strategy must be an object.")
    else:
        min_d = strategy.get("min_acceptable_duration_seconds")
        rec_d = strategy.get("recommended_duration_seconds")
        max_d = strategy.get("max_acceptable_duration_seconds")
        if not all(isinstance(v, (int, float)) and v > 0 for v in (min_d, rec_d, max_d)):
            errors.append("edit_strategy duration fields must be positive numbers.")
        elif not (min_d <= rec_d <= max_d):
            errors.append("edit_strategy duration fields must satisfy min <= recommended <= max.")
    selected = _list_of_dicts(payload.get("selected_beats"))
    if not selected:
        errors.append("selected_beats must be a non-empty list.")
    known: set[tuple[int, int]] = set()
    if analyses:
        for analysis in analyses:
            chapter_index = analysis.get("chapter_index")
            for beat in _list_of_dicts(analysis.get("beats")):
                if isinstance(chapter_index, int) and isinstance(beat.get("beat_index"), int):
                    known.add((chapter_index, beat["beat_index"]))
    for index, item in enumerate(selected, start=1):
        ci = item.get("chapter_index")
        bi = item.get("beat_index")
        if known and (ci, bi) not in known:
            errors.append(f"selected_beats[{index}] references an unknown beat.")
        if not _is_non_empty_text(item.get("voiceover_intent")):
            errors.append(f"selected_beats[{index}].voiceover_intent is required.")
        if not _is_non_empty_text(item.get("visual_requirement")):
            errors.append(f"selected_beats[{index}].visual_requirement is required.")
        if not isinstance(item.get("estimated_screen_time_seconds"), (int, float)) or item.get("estimated_screen_time_seconds") <= 0:
            errors.append(f"selected_beats[{index}].estimated_screen_time_seconds must be positive.")
    flow = payload.get("story_flow")
    if not isinstance(flow, list) or not flow:
        errors.append("story_flow must be a non-empty list.")
    return not errors, errors, payload if not errors else None


def looks_like_director_plan_root(parsed: object) -> bool:
    return isinstance(parsed, dict) and parsed.get("director_plan_version") == 1 and isinstance(parsed.get("selected_beats"), list) and isinstance(parsed.get("edit_strategy"), dict)


def director_strategy(payload: dict) -> dict:
    return payload.get("edit_strategy", {}) if isinstance(payload, dict) and isinstance(payload.get("edit_strategy"), dict) else {}


def validate_final_chunk_payload(payload: object) -> tuple[bool, list[str], dict | None]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["Final chunk root must be an object."], None
    if payload.get("chunk_version") != 1:
        errors.append("chunk_version must be 1.")
    if not _is_non_empty_text(payload.get("chunk_name")):
        errors.append("chunk_name is required.")
    if not _is_non_empty_text(payload.get("rewrite_text")):
        errors.append("rewrite_text is required.")
    srt = _list_of_dicts(payload.get("srt"))
    segments = _list_of_dicts(payload.get("video_segments"))
    if not srt:
        errors.append("srt must be a non-empty list.")
    if not segments:
        errors.append("video_segments must be a non-empty list.")
    srt_indexes = {item.get("index") for item in srt if isinstance(item.get("index"), int)}
    for index, item in enumerate(srt, start=1):
        if item.get("index") != index:
            errors.append(f"srt[{index}].index must be {index}.")
        try:
            start = srt_timestamp_to_seconds(item.get("start", ""))
            end = srt_timestamp_to_seconds(item.get("end", ""))
            if start >= end:
                errors.append(f"srt[{index}].start must be before end.")
        except Exception:
            errors.append(f"srt[{index}] timestamps must use HH:MM:SS,mmm.")
        if not _is_non_empty_text(item.get("text")):
            errors.append(f"srt[{index}].text is required.")
    for index, segment in enumerate(segments, start=1):
        start = ts_to_seconds(segment.get("source_start"))
        end = ts_to_seconds(segment.get("source_end"))
        if start is None or end is None or start >= end:
            errors.append(f"video_segments[{index}] source_start/source_end invalid.")
        ss = segment.get("subtitle_start")
        se = segment.get("subtitle_end")
        if not isinstance(ss, int) or not isinstance(se, int) or ss > se or ss not in srt_indexes or se not in srt_indexes:
            errors.append(f"video_segments[{index}] subtitle range invalid.")
        if not _is_non_empty_text(segment.get("scene_description")):
            errors.append(f"video_segments[{index}].scene_description is required.")
    return not errors, errors, payload if not errors else None


def looks_like_final_chunk_root(parsed: object) -> bool:
    return isinstance(parsed, dict) and parsed.get("chunk_version") == 1 and isinstance(parsed.get("srt"), list) and isinstance(parsed.get("video_segments"), list)


def validate_alignment_audit_payload(payload: object) -> tuple[bool, list[str], dict | None]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["Alignment audit root must be an object."], None
    if payload.get("alignment_audit_version") != 1:
        errors.append("alignment_audit_version must be 1.")
    if not isinstance(payload.get("passed"), bool):
        errors.append("passed must be boolean.")
    if payload.get("final_recommendation") not in {"render", "repair", "stop"}:
        errors.append("final_recommendation must be render, repair, or stop.")
    issues = payload.get("issues", [])
    if issues is not None and not isinstance(issues, list):
        errors.append("issues must be a list.")
    return not errors, errors, payload if not errors else None


def looks_like_alignment_audit_root(parsed: object) -> bool:
    return isinstance(parsed, dict) and parsed.get("alignment_audit_version") == 1 and "final_recommendation" in parsed


def merge_final_chunks(chunks: list[dict], sources: list[dict], target_language: str, title: str | None = None, strategy: dict | None = None) -> dict:
    srt_items: list[dict] = []
    video_segments: list[dict] = []
    rewrite_parts: list[str] = []
    current_time = 0.0
    next_srt_index = 1
    next_segment_id = 1
    for chunk in chunks:
        local_index_map: dict[int, int] = {}
        local_srt = _list_of_dicts(chunk.get("srt"))
        if chunk.get("rewrite_text"):
            rewrite_parts.append(str(chunk["rewrite_text"]).strip())
        chunk_start_time = current_time
        chunk_max_end = current_time
        for item in local_srt:
            old_index = item.get("index")
            start = current_time + srt_timestamp_to_seconds(item["start"])
            end = current_time + srt_timestamp_to_seconds(item["end"])
            local_index_map[old_index] = next_srt_index
            srt_items.append({
                "index": next_srt_index,
                "start": seconds_to_srt_timestamp(start),
                "end": seconds_to_srt_timestamp(end),
                "text": item.get("text", ""),
            })
            if item.get("tts_text"):
                srt_items[-1]["tts_text"] = item["tts_text"]
            chunk_max_end = max(chunk_max_end, end)
            next_srt_index += 1
        for segment in _list_of_dicts(chunk.get("video_segments")):
            raw_ss = segment.get("subtitle_start")
            raw_se = segment.get("subtitle_end")
            if raw_ss is None or raw_se is None or raw_ss not in local_index_map or raw_se not in local_index_map:
                chunk_name = chunk.get("chunk_name", "?")
                raise ValueError(
                    f"Segment references subtitle range [{raw_ss}, {raw_se}] "
                    f"but chunk '{chunk_name}' local SRT indices are {sorted(local_index_map)}."
                )
            ss = local_index_map[raw_ss]
            se = local_index_map[raw_se]
            video_segments.append({
                "segment_id": next_segment_id,
                "order": next_segment_id,
                "source_id": segment.get("source_id") or "source_1",
                "source_start": segment.get("source_start", "00:00:00.000"),
                "source_end": segment.get("source_end", "00:00:01.000"),
                "subtitle_start": ss,
                "subtitle_end": se,
                "scene_description": segment.get("scene_description", "Cảnh được chọn từ bản dựng theo chapter."),
                "importance_score": int(segment.get("importance_score", 85) or 85),
            })
            next_segment_id += 1
        current_time = max(chunk_max_end, chunk_start_time)
    duration_text = ""
    if strategy and isinstance(strategy.get("recommended_duration_seconds"), (int, float)):
        duration_text = f"Khoảng {int(strategy['recommended_duration_seconds'])} giây"
    canonical_language = canonical_target_language(target_language)
    return {
        "metadata": {
            "video_title": title or "Video remake phân tích sâu",
            "rewrite_style": "Phân tích sâu nhiều tầng",
            "target_audience": "Đại chúng",
            "tone": "Tự nhiên, hấp dẫn",
            "target_duration": duration_text or "Theo edit strategy của Gemini",
            "target_language": canonical_language,
            "target_market": "Việt Nam" if canonical_language == "Tiếng Việt" else "Global",
            "localization_level": "full",
            "hashtags": ["remake", "story", "video"],
        },
        "sources": sources or [{"source_id": "source_1", "label": "Video nguồn chính"}],
        "rewrite_script": {"full_text": "\n\n".join(part for part in rewrite_parts if part)},
        "srt": srt_items,
        "video_segments": video_segments,
    }


def final_duration_seconds(payload: dict) -> float:
    srt = _list_of_dicts(payload.get("srt"))
    latest = 0.0
    for item in srt:
        try:
            latest = max(latest, srt_timestamp_to_seconds(item.get("end", "")))
        except Exception:
            pass
    return latest


def canonical_target_language(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip()
    known = {
        "ti?ng vi?t": "Tiếng Việt",
        "tiếng việt": "Tiếng Việt",
        "tieng viet": "Tiếng Việt",
        "english": "English",
        "german": "German",
        "japanese": "Japanese",
        "spanish": "Spanish",
        "korean": "Korean",
    }
    return known.get(normalized.lower(), normalized)


def duration_gate(final_payload: dict, strategy: dict) -> tuple[bool, dict]:
    final_duration = final_duration_seconds(final_payload)
    min_duration = strategy.get("min_acceptable_duration_seconds") if isinstance(strategy, dict) else None
    recommended = strategy.get("recommended_duration_seconds") if isinstance(strategy, dict) else None
    if not isinstance(min_duration, (int, float)) or min_duration <= 0:
        return True, {"final_duration_seconds": final_duration, "reason": "no_min_duration"}
    threshold = float(min_duration) * 0.9
    passed = final_duration >= threshold
    return passed, {
        "final_duration_seconds": final_duration,
        "min_acceptable_duration_seconds": float(min_duration),
        "recommended_duration_seconds": recommended,
        "threshold_seconds": threshold,
        "short_by_seconds": max(0.0, threshold - final_duration),
    }


def user_requests_short_form(user_instruction: str | None) -> bool:
    text = (user_instruction or "").lower()
    markers = ["short", "shorts", "reels", "tiktok", "tik tok", "dưới 90", "duoi 90", "1 phút", "1 phut", "60s", "60 giây", "ngắn"]
    return any(marker in text for marker in markers)


def two_prompt_duration_gate(source_duration_seconds: float, final_payload: dict, user_instruction: str | None = None) -> tuple[bool, dict]:
    final_duration = final_duration_seconds(final_payload)
    if user_requests_short_form(user_instruction):
        return True, {"source_duration_seconds": source_duration_seconds, "final_duration_seconds": final_duration, "reason": "short_form_requested"}
    min_required = 0.0
    if source_duration_seconds >= 45 * 60:
        min_required = 300.0
    elif source_duration_seconds >= 30 * 60:
        min_required = 240.0
    if min_required <= 0:
        return True, {"source_duration_seconds": source_duration_seconds, "final_duration_seconds": final_duration, "reason": "no_hard_minimum"}
    passed = final_duration >= min_required
    return passed, {
        "source_duration_seconds": source_duration_seconds,
        "final_duration_seconds": final_duration,
        "min_required_seconds": min_required,
        "short_by_seconds": max(0.0, min_required - final_duration),
    }


def pipeline_quality_summary(timeline: dict, chapter_analyses: list[dict], strategy: dict, assembly: dict, final_payload: dict, audit: dict) -> dict:
    beat_count = sum(len(_list_of_dicts(item.get("beats"))) for item in chapter_analyses)
    return {
        "chapter_count": len(_list_of_dicts(timeline.get("chapters"))),
        "beat_count": beat_count,
        "recommended_duration_seconds": strategy.get("recommended_duration_seconds"),
        "final_duration_seconds": final_duration_seconds(final_payload),
        "selected_beat_count": len(_list_of_dicts(assembly.get("selected_beats"))),
        "alignment_passed": audit.get("passed"),
        "alignment_recommendation": audit.get("final_recommendation"),
        "alignment_quality": audit.get("overall_quality"),
    }
