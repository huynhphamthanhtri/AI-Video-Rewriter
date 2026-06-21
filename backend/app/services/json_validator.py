from __future__ import annotations

import json
import re

from pydantic import ValidationError

from app.schemas.render import GeminiPayloadSchema, clip_timestamp_to_seconds, seconds_to_clip_timestamp, srt_timestamp_to_seconds


ACTION_CONNECTORS = {"then", "and", "after", "before", "finally", "next", "but", "while", "rồi", "sau đó", "tiếp theo"}
STOPWORDS = {"the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "at", "for", "with", "is", "are", "it", "this", "that", "he", "she", "they", "his", "her", "their", "và", "là", "của", "cho", "trong", "với", "một", "các", "đang"}


class JsonValidator:
    def validate(self, payload: object) -> tuple[bool, list[str], GeminiPayloadSchema | None]:
        try:
            normalized_payload = self.normalize_payload(payload)
            model = GeminiPayloadSchema.model_validate(normalized_payload)
            return True, [], model
        except ValidationError as exc:
            return False, [self._translate_error(error) for error in exc.errors()], None
        except ValueError as exc:
            return False, [str(exc)], None

    def validate_with_auto_fix(self, payload: object) -> tuple[bool, list[str], GeminiPayloadSchema | None, dict | None]:
        try:
            normalized_payload = self.normalize_payload(payload)
        except ValueError as exc:
            return False, [str(exc)], None, None

        valid, errors, model = self.validate(normalized_payload)
        if valid:
            return True, [], model, normalized_payload

        fixed_payload = self.auto_fix_payload(normalized_payload)
        fixed_valid, fixed_errors, fixed_model = self.validate(fixed_payload)
        if fixed_valid:
            return True, ["AUTO FIX: Đã trim/kéo dài source_end của video_segments để khớp thời lượng subtitle."], fixed_model, fixed_payload
        return False, errors + fixed_errors, None, None

    def alignment_warnings(self, payload: object) -> list[str]:
        valid, _, model = self.validate(payload)
        if not valid or model is None:
            return []
        warnings: list[str] = []
        srt_by_index = {item.index: item for item in model.srt}
        for segment in model.video_segments:
            subtitle_items = [srt_by_index[index] for index in range(segment.subtitle_start, segment.subtitle_end + 1) if index in srt_by_index]
            text = " ".join(item.text for item in subtitle_items)
            duration = segment.duration_seconds
            word_count = len(re.findall(r"\w+", text))
            if duration > 8:
                warnings.append(f"ALIGNMENT WARNING: Segment #{segment.segment_id} dài {duration:.1f}s; action/highlights nên ưu tiên 3-6s để SRT bám cảnh hơn.")
            if duration > 0 and word_count / duration > 3.0:
                warnings.append(f"ALIGNMENT WARNING: Segment #{segment.segment_id} subtitle hơi dày ({word_count} words/{duration:.1f}s = {word_count/duration:.1f} words/s), dễ không khớp nhịp cảnh.")
            lower_text = text.lower()
            if sum(1 for token in ACTION_CONNECTORS if token in lower_text) >= 2:
                warnings.append(f"ALIGNMENT WARNING: Segment #{segment.segment_id} subtitle có nhiều hành động nối tiếp; nên tách thành nhiều segment/SRT nhỏ hơn.")
            overlap = self._keyword_overlap(text, segment.scene_description)
            if text and segment.scene_description and overlap < 0.12:
                warnings.append(f"ALIGNMENT WARNING: Segment #{segment.segment_id} subtitle và scene_description ít keyword chung; kiểm tra lại có đúng cảnh không.")
        return warnings

    def normalize_payload(self, payload: object) -> dict:
        if isinstance(payload, dict):
            parsed = payload
        elif isinstance(payload, str):
            cleaned = self.strip_markdown_code_fence(payload)
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON không hợp lệ: {exc.msg}") from exc
        else:
            raise ValueError("JSON EDL phải là object hoặc chuỗi JSON hợp lệ.")
        if not isinstance(parsed, dict):
            raise ValueError("JSON EDL root phải là object.")
        sources = parsed.get("sources", [])
        if isinstance(sources, list):
            for source in sources:
                if isinstance(source, dict) and isinstance(source.get("youtube_url"), str):
                    source["youtube_url"] = self._sanitize_url(source["youtube_url"])
        return parsed

    def strip_markdown_code_fence(self, value: str) -> str:
        cleaned = value.strip()
        match = re.fullmatch(r"```(?:json|JSON)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
        if match:
            return match.group(1).strip()
        return cleaned

    def auto_fix_payload(self, payload: dict) -> dict:
        fixed_payload = self._deepcopy_payload(payload)
        self._auto_fix_sources(fixed_payload)
        self._auto_fix_duplicates_and_sort(fixed_payload)
        return self.auto_fix_duration_mismatch(fixed_payload)

    def auto_fix_duration_mismatch(self, payload: dict) -> dict:
        fixed_payload = self._deepcopy_payload(payload)
        srt_items = fixed_payload.get("srt", [])
        segments = fixed_payload.get("video_segments", [])
        if not isinstance(srt_items, list) or not isinstance(segments, list):
            return fixed_payload

        srt_by_index = {item.get("index"): item for item in srt_items if isinstance(item, dict)}
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            subtitle_start = segment.get("subtitle_start")
            subtitle_end = segment.get("subtitle_end")
            start_item = srt_by_index.get(subtitle_start)
            end_item = srt_by_index.get(subtitle_end)
            if not isinstance(start_item, dict) or not isinstance(end_item, dict):
                continue
            try:
                subtitle_duration = srt_timestamp_to_seconds(end_item["end"]) - srt_timestamp_to_seconds(start_item["start"])
                source_start_seconds = clip_timestamp_to_seconds(segment["source_start"])
            except (KeyError, TypeError, ValueError):
                continue
            if subtitle_duration <= 0:
                continue
            segment["source_end"] = seconds_to_clip_timestamp(source_start_seconds + subtitle_duration)
        return fixed_payload

    def _auto_fix_sources(self, payload: dict) -> None:
        sources = payload.get("sources")
        segments = payload.get("video_segments", [])
        if isinstance(sources, list) and len(sources) == 1 and isinstance(sources[0], dict):
            source_id = sources[0].get("source_id") or "source_1"
            sources[0]["source_id"] = source_id
            if isinstance(sources[0].get("youtube_url"), str):
                sources[0]["youtube_url"] = self._sanitize_url(sources[0]["youtube_url"])
            for segment in segments if isinstance(segments, list) else []:
                if isinstance(segment, dict) and not segment.get("source_id"):
                    segment["source_id"] = source_id

    def _auto_fix_duplicates_and_sort(self, payload: dict) -> None:
        srt_items = payload.get("srt")
        if isinstance(srt_items, list):
            srt_items.sort(key=lambda item: item.get("index", 0) if isinstance(item, dict) else 0)
            seen: set[int] = set()
            next_index = 1
            for item in srt_items:
                if not isinstance(item, dict):
                    continue
                current = item.get("index")
                if not isinstance(current, int) or current in seen:
                    while next_index in seen:
                        next_index += 1
                    item["index"] = next_index
                    current = next_index
                seen.add(current)
        segments = payload.get("video_segments")
        if isinstance(segments, list):
            segments.sort(key=lambda item: item.get("order", 0) if isinstance(item, dict) else 0)
            for index, segment in enumerate([item for item in segments if isinstance(item, dict)], start=1):
                segment["order"] = index
                segment["segment_id"] = index

    def _sanitize_url(self, value: str) -> str:
        cleaned = value.strip().strip("<>")
        markdown_match = re.fullmatch(r"\[[^\]]+]\(([^)]+)\)", cleaned)
        if markdown_match:
            cleaned = markdown_match.group(1).strip().strip("<>")
        return cleaned

    def _keyword_overlap(self, left: str, right: str) -> float:
        left_words = {word.lower() for word in re.findall(r"[A-Za-zÀ-ỹ0-9]+", left) if len(word) > 2 and word.lower() not in STOPWORDS}
        right_words = {word.lower() for word in re.findall(r"[A-Za-zÀ-ỹ0-9]+", right) if len(word) > 2 and word.lower() not in STOPWORDS}
        if not left_words or not right_words:
            return 1.0
        return len(left_words & right_words) / max(1, min(len(left_words), len(right_words)))

    def _deepcopy_payload(self, payload: dict) -> dict:
        import copy

        return copy.deepcopy(payload)

    def _translate_error(self, error: dict) -> str:
        loc = " -> ".join(str(part) for part in error.get("loc", []))
        msg = error.get("msg", "Dữ liệu không hợp lệ")
        translations = {
            "Field required": "Thiếu trường bắt buộc.",
            "Input should be a valid string": "Giá trị phải là chuỗi hợp lệ.",
            "Input should be a valid integer": "Giá trị phải là số nguyên hợp lệ.",
            "Input should be a valid dictionary": "Giá trị phải là đối tượng JSON hợp lệ.",
        }
        translated = translations.get(msg, msg)
        return f"Lỗi tại '{loc}': {translated}"



