from __future__ import annotations

import json
import re
import urllib.parse

from pydantic import ValidationError

from app.schemas.render import GeminiPayloadSchema, RenderOptions, clip_timestamp_to_seconds, seconds_to_clip_timestamp, srt_timestamp_to_seconds


ACTION_CONNECTORS = {"then", "and", "after", "before", "finally", "next", "but", "while", "rồi", "sau đó", "tiếp theo"}
MAX_SAFE_VOICEOVER_EXTEND_SECONDS = 5.0
MAX_AUTO_FIX_SRT_OVERLAP_SECONDS = 0.5
MAX_AUTO_FIX_SRT_OVERLAP_RATIO = 0.1
STOPWORDS = {"the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "at", "for", "with", "is", "are", "it", "this", "that", "he", "she", "they", "his", "her", "their", "và", "là", "của", "cho", "trong", "với", "một", "các", "đang"}

TEXT_KEYS_FOR_REPAIR = frozenset({"full_text", "text", "scene_description"})

_SRT_TIMESTAMP_MISSING_HOUR_RE = re.compile(r"^(\d{2}:\d{2},\d{3})$")


def loads_json_with_repair(value: str) -> dict:
    """
    Parse JSON string with repair pass for Gemini-style unescaped quotes.
    Attempts strict parse first; if that fails, repairs known text fields
    and retries.
    """
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass

    repaired = _repair_unescaped_quotes(value)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        raise ValueError(f"JSON không hợp lệ sau khi repair: không thể parse")


def _repair_unescaped_quotes(raw: str) -> str:
    """
    Target repair of unescaped double quotes inside known text fields
    (full_text, text, scene_description) that Gemini often fills with
    dialogue containing quotation marks.
    """
    out: list[str] = []
    i = 0
    n = len(raw)

    while i < n:
        if raw[i] != '"':
            out.append(raw[i])
            i += 1
            continue

        key_end = raw.find('"', i + 1)
        if key_end == -1 or key_end - i <= 1:
            out.append(raw[i])
            i += 1
            continue

        key = raw[i + 1:key_end]

        if key not in TEXT_KEYS_FOR_REPAIR:
            out.append(raw[i:key_end + 1])
            i = key_end + 1
            continue

        scan = key_end + 1
        while scan < n and raw[scan] in ' \t\n\r':
            scan += 1
        if scan >= n or raw[scan] != ':':
            out.append(raw[i:key_end + 1])
            i = key_end + 1
            continue

        scan += 1
        while scan < n and raw[scan] in ' \t\n\r':
            scan += 1
        if scan >= n or raw[scan] != '"':
            out.append(raw[i:key_end + 1])
            i = key_end + 1
            continue

        out.append(raw[i:scan + 1])
        i = scan + 1

        while i < n:
            if raw[i] == '\\':
                out.append(raw[i:i + 2])
                i += 2
            elif raw[i] == '"':
                if _is_closing_quote(raw, i + 1, n):
                    out.append('"')
                    i += 1
                    break
                out.append('\\"')
                i += 1
            else:
                out.append(raw[i])
                i += 1

    return ''.join(out)


def _is_closing_quote(raw: str, start: int, n: int) -> bool:
    """
    Determine if the quote at position `start - 1` is a JSON structural closing quote.
    A quote is structural only if followed by `, "` (new key/string), `, }` (trailing comma),
    `}` or `]` (end of container).
    A quote immediately followed by `"` (with only whitespace) is always an inner quote
    because valid JSON requires a comma between sibling key/value pairs.
    """
    pos = start
    while pos < n and raw[pos] in ' \t\n\r':
        pos += 1
    if pos >= n:
        return True
    ch = raw[pos]
    if ch in ('}', ']'):
        return True
    if ch == '"':
        # `" "` with only whitespace between cannot be a closing + opening in valid JSON
        return False
    if ch == ',':
        pos += 1
        while pos < n and raw[pos] in ' \t\n\r':
            pos += 1
        if pos >= n:
            return False
        if raw[pos] == '"' or raw[pos] in ('}', ']'):
            return True
    return False


class JsonValidator:
    def validate(self, payload: object) -> tuple[bool, list[str], GeminiPayloadSchema | None]:
        try:
            normalized_payload = self.normalize_payload(payload)
            model = GeminiPayloadSchema.model_validate(normalized_payload)
            timeline_errors = self._validate_srt_timeline(model)
            if timeline_errors:
                return False, timeline_errors, None
            return True, [], model
        except ValidationError as exc:
            return False, [self._translate_error(error) for error in exc.errors()], None
        except ValueError as exc:
            return False, [str(exc)], None

    def validate_with_auto_fix(self, payload: object, render_options: RenderOptions | dict | None = None) -> tuple[bool, list[str], GeminiPayloadSchema | None, dict | None]:
        try:
            normalized_payload = self.normalize_payload(payload)
        except ValueError as exc:
            return False, [str(exc)], None, None

        valid, errors, model = self.validate(normalized_payload)
        if valid:
            return True, [], model, normalized_payload

        fixed_payload = self.auto_fix_payload(normalized_payload, render_options=render_options)
        fixed_valid, fixed_errors, fixed_model = self.validate(fixed_payload)
        if fixed_valid:
            return True, ["AUTO FIX: Đã chuẩn hóa timeline/source duration trong payload."], fixed_model, fixed_payload
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

    @staticmethod
    def _normalize_clip_timestamps(payload: dict) -> None:
        segments = payload.get("video_segments")
        if not isinstance(segments, list):
            return
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            for key in ("source_start", "source_end"):
                val = seg.get(key)
                if isinstance(val, str):
                    val = val.strip().replace(",", ".")
                    seg[key] = val

    @staticmethod
    def _normalize_srt_timestamps(payload: dict) -> None:
        srt_items = payload.get("srt")
        if not isinstance(srt_items, list):
            return
        for item in srt_items:
            if not isinstance(item, dict):
                continue
            for key in ("start", "end"):
                val = item.get(key)
                if isinstance(val, str) and _SRT_TIMESTAMP_MISSING_HOUR_RE.match(val):
                    item[key] = f"00:{val}"

    @staticmethod
    def _normalize_metadata_language(payload: dict) -> None:
        meta = payload.get("metadata")
        if not isinstance(meta, dict):
            return
        lang = meta.get("target_language")
        if isinstance(lang, str):
            lang_norm = lang.strip().lower().replace("  ", " ")
            if lang_norm in ("vi", "vietnamese", "tieng viet"):
                meta["target_language"] = "Tiếng Việt"
        market = meta.get("target_market")
        if isinstance(market, str):
            market_norm = market.strip().lower().replace("  ", " ")
            if market_norm in ("vietnam", "viet nam", "vn"):
                meta["target_market"] = "Việt Nam"

    def normalize_payload(self, payload: object) -> dict:
        if isinstance(payload, dict):
            parsed = payload
        elif isinstance(payload, str):
            cleaned = self.strip_markdown_code_fence(payload)
            try:
                parsed = loads_json_with_repair(cleaned)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"JSON không hợp lệ: {exc}") from exc
        else:
            raise ValueError("JSON EDL phải là object hoặc chuỗi JSON hợp lệ.")
        if not isinstance(parsed, dict):
            raise ValueError("JSON EDL root phải là object.")
        sources = parsed.get("sources", [])
        if isinstance(sources, list):
            for source in sources:
                if isinstance(source, dict) and isinstance(source.get("youtube_url"), str):
                    source["youtube_url"] = self._sanitize_url(source["youtube_url"])
        self._normalize_clip_timestamps(parsed)
        self._normalize_srt_timestamps(parsed)
        self._normalize_metadata_language(parsed)
        return parsed

    @staticmethod
    def _find_srt_timeline_overlaps(model: GeminiPayloadSchema) -> list[dict[str, object]]:
        sorted_srt = sorted(model.srt, key=lambda c: c.index)
        overlaps: list[dict[str, object]] = []
        for i in range(len(sorted_srt) - 1):
            current = sorted_srt[i]
            nxt = sorted_srt[i + 1]
            current_end = srt_timestamp_to_seconds(current.end)
            next_start = srt_timestamp_to_seconds(nxt.start)
            if current_end > next_start:
                overlaps.append({
                    "current_index": current.index,
                    "next_index": nxt.index,
                    "current_end": current.end,
                    "next_start": nxt.start,
                    "overlap_seconds": round(current_end - next_start, 3),
                })
        return overlaps

    def _validate_srt_timeline(self, model: GeminiPayloadSchema) -> list[str]:
        overlaps = self._find_srt_timeline_overlaps(model)
        return [
            f"SRT_OVERLAP: srt[{o['current_index']}] ends at {o['current_end']} "
            f"after srt[{o['next_index']}] starts at {o['next_start']} "
            f"({o['overlap_seconds']:.2f}s overlap)."
            for o in overlaps
        ]

    def strip_markdown_code_fence(self, value: str) -> str:
        cleaned = value.strip()
        match = re.fullmatch(r"```(?:json|JSON)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
        if match:
            return match.group(1).strip()
        return cleaned

    def auto_fix_payload(self, payload: dict, render_options: RenderOptions | dict | None = None) -> dict:
        fixed_payload = self._deepcopy_payload(payload)
        self._auto_fix_sources(fixed_payload)
        self._auto_fix_duplicates_and_sort(fixed_payload)
        self._auto_fix_srt_tiny_overlaps(fixed_payload)
        if self._skip_duration_auto_fix(render_options):
            return fixed_payload
        voiceover_safe_trim_only = self._voiceover_safe_trim_only(render_options)
        return self.auto_fix_duration_mismatch(fixed_payload, trim_only=voiceover_safe_trim_only)

    def _skip_duration_auto_fix(self, render_options: RenderOptions | dict | None) -> bool:
        if render_options is None:
            return False
        if isinstance(render_options, dict):
            tts_mode = render_options.get("tts_mode")
            tts_fit_policy = render_options.get("tts_fit_policy", "hybrid")
        else:
            tts_mode = render_options.tts_mode
            tts_fit_policy = render_options.tts_fit_policy
        return False

    def _voiceover_safe_trim_only(self, render_options: RenderOptions | dict | None) -> bool:
        if render_options is None:
            return False
        if isinstance(render_options, dict):
            tts_mode = render_options.get("tts_mode")
            tts_fit_policy = render_options.get("tts_fit_policy", "hybrid")
        else:
            tts_mode = render_options.tts_mode
            tts_fit_policy = render_options.tts_fit_policy
        return tts_mode == "voiceover" and tts_fit_policy != "segment_uniform"

    def auto_fix_duration_mismatch(self, payload: dict, trim_only: bool = False) -> dict:
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
                source_end_seconds = clip_timestamp_to_seconds(segment["source_end"])
            except (KeyError, TypeError, ValueError):
                continue
            if subtitle_duration <= 0:
                continue
            source_duration = source_end_seconds - source_start_seconds
            shortage = subtitle_duration - source_duration
            if trim_only and source_duration <= subtitle_duration and not (0 < shortage <= MAX_SAFE_VOICEOVER_EXTEND_SECONDS):
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
            indices = [item.get("index") for item in srt_items if isinstance(item, dict)]
            if len(indices) != len(set(indices)):
                pass
        segments = payload.get("video_segments")
        if isinstance(segments, list):
            segments.sort(key=lambda item: item.get("order", 0) if isinstance(item, dict) else 0)
            for index, segment in enumerate([item for item in segments if isinstance(item, dict)], start=1):
                segment["order"] = index
                segment["segment_id"] = index

    @staticmethod
    def _auto_fix_srt_tiny_overlaps(payload: dict) -> None:
        srt_items = payload.get("srt")
        if not isinstance(srt_items, list) or len(srt_items) < 2:
            return
        srt_items.sort(key=lambda item: item.get("index", 0) if isinstance(item, dict) else 0)
        for i in range(len(srt_items) - 1):
            current = srt_items[i]
            nxt = srt_items[i + 1]
            if not isinstance(current, dict) or not isinstance(nxt, dict):
                continue
            try:
                current_end = srt_timestamp_to_seconds(current["end"])
                current_start = srt_timestamp_to_seconds(current["start"])
                next_start = srt_timestamp_to_seconds(nxt["start"])
            except (KeyError, TypeError, ValueError):
                continue
            if current_end <= next_start:
                continue
            overlap = current_end - next_start
            dur = current_end - current_start
            ratio = overlap / max(dur, 0.001)
            if overlap <= MAX_AUTO_FIX_SRT_OVERLAP_SECONDS and ratio <= MAX_AUTO_FIX_SRT_OVERLAP_RATIO:
                from app.schemas.render import seconds_to_srt_timestamp
                current["end"] = seconds_to_srt_timestamp(next_start)

    def _sanitize_url(self, value: str) -> str:
        cleaned = value.strip().strip("<>")
        markdown_match = re.fullmatch(r"\[[^\]]+]\(([^)]+)\)", cleaned)
        if markdown_match:
            cleaned = markdown_match.group(1).strip().strip("<>")
        try:
            parsed = urllib.parse.urlparse(cleaned)
            if parsed.netloc in {"google.com", "www.google.com"}:
                qs = urllib.parse.parse_qs(parsed.query)
                q = qs.get("q")
                if q:
                    inner = urllib.parse.unquote(q[0])
                    inner_parsed = urllib.parse.urlparse(inner)
                    if inner_parsed.netloc in {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}:
                        return self._sanitize_url(inner)
        except Exception:
            pass
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



