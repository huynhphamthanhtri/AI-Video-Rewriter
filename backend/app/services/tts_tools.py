from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Coroutine

from app.core.config import settings
from app.schemas.render import GeminiPayloadSchema, RenderOptions, seconds_to_srt_timestamp, srt_timestamp_to_seconds

logger = logging.getLogger(__name__)

MAX_RAW_CUE_DURATION = 12.0
CHARS_PER_SEC_THRESHOLD = 8.0
MIN_CPS_CHECK_DURATION = 3.0

TTS_PREVIEWS_DIR = settings.temp_dir / "tts_voice_previews"
TTS_STUDIO_OUTPUTS_DIR = settings.temp_dir / "tts_studio_outputs"
TTS_STUDIO_MAX_CHARS = 10000
ALLOWED_STUDIO_FORMATS = frozenset({"wav", "mp3"})
TTS_OVERLAP_HARD_FAIL_SECONDS = 0.25

EDGE_TTS_VOICES = [
    {"id": "vi-VN-HoaiMyNeural", "label": "HoaiMy", "description": "Vietnamese female neural voice", "gender": "female", "languages": ["vi"], "locale": "vi-VN", "rank": 1, "best_for": "Vietnamese"},
    {"id": "vi-VN-NamMinhNeural", "label": "NamMinh", "description": "Vietnamese male neural voice", "gender": "male", "languages": ["vi"], "locale": "vi-VN", "rank": 2, "best_for": "Vietnamese"},
    {"id": "en-US-JennyNeural", "label": "Jenny", "description": "US English female neural voice", "gender": "female", "languages": ["en"], "locale": "en-US", "rank": 1, "best_for": "English US"},
    {"id": "en-US-GuyNeural", "label": "Guy", "description": "US English male neural voice", "gender": "male", "languages": ["en"], "locale": "en-US", "rank": 2, "best_for": "English US"},
    {"id": "de-DE-KatjaNeural", "label": "Katja", "description": "German female neural voice", "gender": "female", "languages": ["de"], "locale": "de-DE", "rank": 1, "best_for": "German"},
    {"id": "de-DE-ConradNeural", "label": "Conrad", "description": "German male neural voice", "gender": "male", "languages": ["de"], "locale": "de-DE", "rank": 2, "best_for": "German"},
    {"id": "ja-JP-NanamiNeural", "label": "Nanami", "description": "Japanese female neural voice", "gender": "female", "languages": ["ja"], "locale": "ja-JP", "rank": 1, "best_for": "Japanese"},
    {"id": "ja-JP-KeitaNeural", "label": "Keita", "description": "Japanese male neural voice", "gender": "male", "languages": ["ja"], "locale": "ja-JP", "rank": 2, "best_for": "Japanese"},
    {"id": "es-MX-DaliaNeural", "label": "Dalia", "description": "Mexican Spanish female neural voice", "gender": "female", "languages": ["es"], "locale": "es-MX", "rank": 1, "best_for": "Spanish Mexico"},
    {"id": "es-MX-JorgeNeural", "label": "Jorge", "description": "Mexican Spanish male neural voice", "gender": "male", "languages": ["es"], "locale": "es-MX", "rank": 2, "best_for": "Spanish Mexico"},
    {"id": "ko-KR-SunHiNeural", "label": "SunHi", "description": "Korean female neural voice", "gender": "female", "languages": ["ko"], "locale": "ko-KR", "rank": 1, "best_for": "Korean"},
    {"id": "ko-KR-InJoonNeural", "label": "InJoon", "description": "Korean male neural voice", "gender": "male", "languages": ["ko"], "locale": "ko-KR", "rank": 2, "best_for": "Korean"},
]


def list_edge_tts_voices() -> list[dict[str, Any]]:
    return sorted(EDGE_TTS_VOICES, key=lambda v: (v.get("rank", 99), v.get("locale", ""), v.get("id", "")))


def tts_studio_outputs_dir() -> Path:
    TTS_STUDIO_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    return TTS_STUDIO_OUTPUTS_DIR


def _filename_slug(voice_label: str, text: str) -> str:
    def slugify(s: str) -> str:
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
        return s[:40]

    voice_slug = slugify(voice_label) or "voice"
    text_slug = slugify(text[:60]) or "text"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:8]
    return f"tts_{voice_slug}_{text_slug}_{timestamp}_{short_id}"


def generate_standalone_tts(
    voice_id: str,
    text: str,
    output_format: str = "wav",
) -> Path:
    voice_data = next((v for v in EDGE_TTS_VOICES if v["id"] == voice_id), None)
    if not voice_data:
        valid_ids = ", ".join(v["id"] for v in EDGE_TTS_VOICES)
        raise ValueError(f"Voice '{voice_id}' không tồn tại. Các voice có sẵn: {valid_ids}")

    if output_format not in ALLOWED_STUDIO_FORMATS:
        raise ValueError(f"Format không hợp lệ: '{output_format}'. Chỉ hỗ trợ: {', '.join(sorted(ALLOWED_STUDIO_FORMATS))}.")

    cleaned = _normalize_tts_text(text)
    if not cleaned:
        raise ValueError("Text rỗng sau khi normalize. Vui lòng nhập nội dung cần chuyển giọng.")

    if len(cleaned) > TTS_STUDIO_MAX_CHARS:
        raise ValueError(f"Text quá dài ({len(cleaned)} ký tự). Tối đa {TTS_STUDIO_MAX_CHARS} ký tự.")

    output_dir = tts_studio_outputs_dir()
    stem = _filename_slug(voice_data.get("label", voice_id), cleaned)
    wav_path = output_dir / f"{stem}.wav"

    EdgeTtsSynthesizer().synthesize_to_file(
        cleaned,
        wav_path,
        RenderOptions(tts_voice_id=voice_id),
        voice_data,
    )

    if output_format == "mp3":
        mp3_path = output_dir / f"{stem}.mp3"
        _run([
            settings.ffmpeg_binary, "-y", "-i", str(wav_path),
            "-codec:a", "libmp3lame", "-b:a", "192k",
            str(mp3_path),
        ])
        wav_path.unlink(missing_ok=True)
        return mp3_path

    return wav_path


def _metadata_language(payload: GeminiPayloadSchema | None) -> str:
    if not payload:
        return ""
    return " ".join([payload.metadata.target_language or "", payload.metadata.target_market or ""]).lower()


def _language_voice_prefix(language: str) -> str:
    if "japanese" in language or "tiếng nhật" in language or "nhật" in language:
        return "ja-JP"
    if "korean" in language or "tiếng hàn" in language or "hàn" in language:
        return "ko-KR"
    if "german" in language or "tiếng đức" in language or "đức" in language:
        return "de-DE"
    if "spanish" in language or "mexico" in language or "mexican" in language or "tiếng tây ban nha" in language:
        return "es-MX"
    if "english" in language or "tiếng anh" in language or "mỹ" in language or "us" in language:
        return "en-US"
    return "vi-VN"


def alternate_edge_tts_voice(voice_data: dict[str, Any]) -> dict[str, Any] | None:
    voice_id = voice_data.get("id")
    locale = voice_data.get("locale")
    if not voice_id or not locale:
        return None
    candidates = [voice for voice in EDGE_TTS_VOICES if voice.get("locale") == locale and voice.get("id") != voice_id]
    return sorted(candidates, key=lambda v: (v.get("rank", 99), v.get("id", "")))[0] if candidates else None


def resolve_edge_tts_voice(options: RenderOptions, payload: GeminiPayloadSchema | None = None) -> dict[str, Any]:
    by_id = {voice["id"]: voice for voice in EDGE_TTS_VOICES}
    prefix = _language_voice_prefix(_metadata_language(payload))
    if options.tts_voice_id != "auto" and options.tts_voice_id in by_id:
        selected = by_id[options.tts_voice_id]
        if selected["id"].startswith(prefix):
            return selected
        logger.warning("Ignoring TTS voice %s because target language expects %s", options.tts_voice_id, prefix)
    gender = options.tts_voice_gender if options.tts_voice_gender != "auto" else "female"
    matches = [voice for voice in EDGE_TTS_VOICES if voice["id"].startswith(prefix) and voice["gender"] == gender]
    if matches:
        return sorted(matches, key=lambda v: (v.get("rank", 99), v["id"]))[0]
    prefix_matches = [voice for voice in EDGE_TTS_VOICES if voice["id"].startswith(prefix)]
    if prefix_matches:
        return sorted(prefix_matches, key=lambda v: (v.get("rank", 99), v["id"]))[0]
    return by_id["vi-VN-HoaiMyNeural"]


@dataclass
class TtsCuePlan:
    index: int
    segment_id: int | None
    text: str
    start_seconds: float
    end_seconds: float
    slot_duration: float
    generated_duration: float
    applied_speed: float
    final_duration: float
    status: str
    warning: str = ""


def _run(cmd: list[str]) -> None:
    exe = cmd[0] if cmd else ""
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise RuntimeError(f"Không tìm thấy executable: {exe}. Hãy chạy launcher dev mode với FFmpeg trên PATH hoặc build runtime package.") from None
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(detail or f"Lệnh thất bại: {' '.join(cmd)}") from exc


def _run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def probe_audio_duration(path: Path) -> float:
    cmd = [settings.ffprobe_binary, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return float(result.stdout.strip() or 0)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 0.0


def probe_media_duration(path: Path) -> float:
    cmd = [settings.ffprobe_binary, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return float(result.stdout.strip() or 0)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 0.0


def video_has_audio(path: Path) -> bool:
    cmd = [settings.ffprobe_binary, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return bool(result.stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return False


def _atempo_filter(speed: float) -> str:
    remaining = max(0.5, min(4.0, speed))
    parts: list[str] = []
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2.0
    parts.append(f"atempo={remaining:.4f}")
    return ",".join(parts)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 1.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil((percentile / 100) * len(ordered)) - 1))
    return ordered[index]


def _normalize_tts_text(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    text = text.replace("…", "...").replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


class EdgeTtsSynthesizer:
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 2

    @staticmethod
    def _is_transient_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        markers = [
            "no audio was received",
            "connection",
            "timeout",
            "websocket",
            "server disconnected",
            "cannot connect",
            "eof",
            "reset",
            "broken",
            "unreachable",
        ]
        return any(m in msg for m in markers)

    def synthesize_to_file(self, text: str, output_path: Path, options: RenderOptions, voice_data: dict[str, Any] | None = None) -> None:
        try:
            import edge_tts
        except ImportError as exc:
            raise RuntimeError("Edge TTS chưa được cài. Vui lòng chạy pip install -r backend/requirements.txt.") from exc
        voice_id = (voice_data or {}).get("id") or "ja-JP-NanamiNeural"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        last_error: Exception | None = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            temp_media = output_path.with_suffix(".mp3")

            async def save_media() -> None:
                communicate = edge_tts.Communicate(_normalize_tts_text(text) or " ", voice_id)
                await communicate.save(str(temp_media))

            try:
                _run_async(save_media())
                if not temp_media.exists() or temp_media.stat().st_size == 0:
                    raise RuntimeError("Edge TTS tạo file âm thanh rỗng.")
                _run([settings.ffmpeg_binary, "-y", "-i", str(temp_media), "-ar", "48000", "-ac", "2", str(output_path)])
                if not output_path.exists() or output_path.stat().st_size == 0:
                    raise RuntimeError("FFmpeg tạo file WAV rỗng từ âm thanh Edge TTS.")
                if probe_audio_duration(output_path) <= 0:
                    raise RuntimeError("File WAV sau Edge TTS có duration <= 0.")
                return
            except Exception as exc:
                last_error = exc
                transient = self._is_transient_error(exc)
                logger.warning(
                    "Edge TTS attempt %d/%d failed for voice=%s text_len=%d transient=%s: %s",
                    attempt, self.MAX_RETRIES, voice_id, len(text), transient, exc,
                )
                if transient and attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY_SECONDS * attempt)
                    continue
                if attempt >= self.MAX_RETRIES or not transient:
                    raise RuntimeError(
                        f"Edge TTS không tạo được audio sau {attempt} lần thử. "
                        f"Voice={voice_id}, text preview={text[:80]!r}. Lỗi: {last_error}"
                    ) from last_error
            finally:
                temp_media.unlink(missing_ok=True)


class TtsVoiceoverService:
    def _split_long_cue(self, text: str, max_chars: int = 200) -> list[str]:
        if len(text) <= max_chars:
            return [text]
        parts: list[str] = []
        sentences = re.split(r'(?<=[.!?。！？])\s+', text)
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= max_chars:
                current = (current + " " + sentence).strip()
            else:
                if current:
                    parts.append(current)
                if len(sentence) > max_chars:
                    words = sentence.split() if " " in sentence else list(sentence)
                    separator = " " if " " in sentence else ""
                    chunk = ""
                    for word in words:
                        candidate = (chunk + separator + word).strip()
                        if len(candidate) <= max_chars:
                            chunk = candidate
                        else:
                            if chunk:
                                parts.append(chunk)
                            chunk = word
                    current = chunk
                else:
                    current = sentence
        if current:
            parts.append(current)
        return parts or [text]

    def generate_natural_tts(self, payload: GeminiPayloadSchema, output_dir: Path, workspace_dir: Path, options: RenderOptions, progress_callback=None, cancel_callback=None) -> tuple[dict[int, float], list[tuple[Path, float, int | None]]]:
        if options.tts_engine != "edge_tts":
            raise RuntimeError("Edge TTS là engine TTS duy nhất được hỗ trợ.")
        if options.tts_voice_mode != "preset":
            raise RuntimeError("Edge TTS không hỗ trợ clone voice.")
        tts_dir = workspace_dir / "tts"
        raw_dir = tts_dir / "raw"
        fitted_dir = tts_dir / "fitted"
        raw_dir.mkdir(parents=True, exist_ok=True)
        fitted_dir.mkdir(parents=True, exist_ok=True)
        if progress_callback:
            progress_callback({"step": "Generate TTS", "message": "Đang tạo voiceover bằng Edge TTS...", "progress": 90, "phase": "tts_generate", "phase_progress": 0.0})
        synth = EdgeTtsSynthesizer()
        voice_data = resolve_edge_tts_voice(options, payload)
        fallback_voice_data = alternate_edge_tts_voice(voice_data)
        cue_to_segment = self._cue_segment_map(payload)
        natural_durations: dict[int, float] = {}
        natural_paths: list[tuple[Path, float, int | None]] = []
        total = len(payload.srt)

        def _process_cue(cue: object) -> tuple[int, float, tuple[Path, float, int | None]]:
            start = srt_timestamp_to_seconds(cue.start)
            end = srt_timestamp_to_seconds(cue.end)
            segment_id = cue_to_segment.get(cue.index)
            raw_text = _normalize_tts_text(cue.tts_text or cue.text)
            sub_texts = self._split_long_cue(raw_text, options.tts_max_chars)
            raw_paths: list[Path] = []
            for sub_idx, sub_text in enumerate(sub_texts):
                sub_raw_path = raw_dir / f"cue_{cue.index:04d}_sub_{sub_idx:02d}.wav"
                try:
                    synth.synthesize_to_file(sub_text, sub_raw_path, options, voice_data)
                except RuntimeError as exc:
                    logger.warning("Primary TTS voice failed for cue=%s sub=%s voice=%s: %s", cue.index, sub_idx, voice_data.get("id"), exc)
                    split_retry = self._split_long_cue(sub_text, max(80, min(140, options.tts_max_chars // 2)))
                    if len(split_retry) > 1:
                        retry_paths: list[Path] = []
                        for retry_idx, retry_text in enumerate(split_retry):
                            retry_path = raw_dir / f"cue_{cue.index:04d}_sub_{sub_idx:02d}_retry_{retry_idx:02d}.wav"
                            try:
                                synth.synthesize_to_file(retry_text, retry_path, options, voice_data)
                            except RuntimeError:
                                if fallback_voice_data is None:
                                    raise
                                synth.synthesize_to_file(retry_text, retry_path, options, fallback_voice_data)
                            retry_paths.append(retry_path)
                        concat_retry = fitted_dir / f"concat_retry_{cue.index:04d}_{sub_idx:02d}.txt"
                        with open(concat_retry, "w", encoding="utf-8") as f:
                            for p in retry_paths:
                                f.write(f"file '{p}'\n")
                        _run([settings.ffmpeg_binary, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_retry), "-c", "copy", str(sub_raw_path)])
                    elif fallback_voice_data is not None:
                        synth.synthesize_to_file(sub_text, sub_raw_path, options, fallback_voice_data)
                    else:
                        raise
                sub_duration = probe_audio_duration(sub_raw_path)
                if sub_duration > MAX_RAW_CUE_DURATION:
                    truncated_path = raw_dir / f"cue_{cue.index:04d}_sub_{sub_idx:02d}_truncated.wav"
                    _run([settings.ffmpeg_binary, "-y", "-i", str(sub_raw_path), "-t", f"{MAX_RAW_CUE_DURATION:.3f}", "-ar", "48000", "-ac", "2", str(truncated_path)])
                    sub_raw_path = truncated_path
                raw_paths.append(sub_raw_path)
            raw_path = raw_dir / f"cue_{cue.index:04d}.wav"
            if len(raw_paths) == 1:
                if raw_paths[0] != raw_path:
                    raw_paths[0].replace(raw_path)
            else:
                concat_list = fitted_dir / f"concat_{cue.index:04d}.txt"
                with open(concat_list, "w", encoding="utf-8") as f:
                    for p in raw_paths:
                        f.write(f"file '{p}'\n")
                _run([settings.ffmpeg_binary, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(raw_path)])
            natural_path = fitted_dir / f"cue_{cue.index:04d}.wav"
            silence_filter = "areverse,silenceremove=start_periods=1:start_duration=0.05:start_threshold=-50dB,areverse,asetpts=PTS-STARTPTS"
            _run([settings.ffmpeg_binary, "-y", "-i", str(raw_path), "-af", silence_filter, "-ar", "48000", "-ac", "2", str(natural_path)])
            natural_duration = probe_audio_duration(natural_path)
            return cue.index, natural_duration, (natural_path, start, segment_id)

        cues = list(payload.srt)
        max_workers = min(4, len(cues))

        if max_workers <= 1:
            for pos, cue in enumerate(cues, start=1):
                if cancel_callback:
                    cancel_callback()
                idx, dur, info = _process_cue(cue)
                natural_durations[idx] = dur
                natural_paths.append(info)
                if progress_callback:
                    progress_callback({"step": "Generate TTS", "message": f"Đang tạo Edge TTS {pos}/{total}...", "progress": 90 + int((pos / total) * 3), "phase": "tts_generate", "phase_progress": pos / total})
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_process_cue, cue): cue for cue in cues}
                for pos, future in enumerate(as_completed(futures), start=1):
                    if cancel_callback:
                        cancel_callback()
                    idx, dur, info = future.result()
                    natural_durations[idx] = dur
                    natural_paths.append(info)
                    if progress_callback:
                        progress_callback({"step": "Generate TTS", "message": f"Đang tạo Edge TTS {pos}/{total}...", "progress": 90 + int((pos / total) * 3), "phase": "tts_generate", "phase_progress": pos / total})

        natural_paths.sort(key=lambda x: x[1])
        return natural_durations, natural_paths

    def generate_voiceover(self, payload: GeminiPayloadSchema, output_dir: Path, workspace_dir: Path, options: RenderOptions, video_duration: float, progress_callback=None, cancel_callback=None, segment_speeds: dict[int | None, float] | None = None) -> dict[str, Any]:
        if options.tts_engine != "edge_tts":
            raise RuntimeError("Edge TTS là engine TTS duy nhất được hỗ trợ.")
        tts_dir = workspace_dir / "tts"
        fitted_dir = tts_dir / "fitted"
        natural_path = fitted_dir / "cue_0001.wav"
        if not natural_path.exists():
            self.generate_natural_tts(payload, output_dir, workspace_dir, options, progress_callback=progress_callback, cancel_callback=cancel_callback)
        cue_to_segment = self._cue_segment_map(payload)
        items: list[dict[str, Any]] = []
        for cue in payload.srt:
            start = srt_timestamp_to_seconds(cue.start)
            segment_id = cue_to_segment.get(cue.index)
            path = fitted_dir / f"cue_{cue.index:04d}.wav"
            dur = probe_audio_duration(path)
            items.append({"cue": cue, "path": path, "start": start, "segment_id": segment_id, "natural_duration": dur})
        items.sort(key=lambda x: x["start"])
        if segment_speeds is None:
            required_by_segment: dict[int | None, list[float]] = {}
            for item in items:
                slot = max(0.05, srt_timestamp_to_seconds(item["cue"].end) - srt_timestamp_to_seconds(item["cue"].start))
                req = max(1.0, item["natural_duration"] / slot) if item["natural_duration"] > 0 else 1.0
                required_by_segment.setdefault(item["segment_id"], []).append(req)
            segment_speeds = {seg_id: min(max(_percentile(values, 90), 1.0), options.tts_max_speed) for seg_id, values in required_by_segment.items()}
        for item in items:
            item_start = item["start"]
            speed = segment_speeds.get(item["segment_id"], 1.0)
            final_dur = item["natural_duration"] / speed if speed > 0 else item["natural_duration"]
            item["adjusted_start"] = item_start
            item["adjusted_end"] = item_start + final_dur
        plans: list[TtsCuePlan] = []
        fitted_paths: list[tuple[Path, float]] = []
        for item in items:
            if cancel_callback:
                cancel_callback()
            speed = segment_speeds.get(item["segment_id"], 1.0)
            final_path = fitted_dir / f"cue_{item['cue'].index:04d}_final.wav"
            if speed > 1.0:
                speed_filter = _atempo_filter(speed)
                _run([settings.ffmpeg_binary, "-y", "-i", str(item["path"]), "-af", f"{speed_filter},asetpts=PTS-STARTPTS", "-ar", "48000", "-ac", "2", str(final_path)])
            elif item["path"] != final_path:
                shutil.copy2(str(item["path"]), str(final_path))
            final_duration = probe_audio_duration(final_path)
            slot = max(0.05, srt_timestamp_to_seconds(item["cue"].end) - srt_timestamp_to_seconds(item["cue"].start))
            overflow = final_duration > slot + max(0.15, slot * 0.03)
            warning = ""
            if overflow:
                warning = f"TTS_OVERFLOW: cue {item['cue'].index} natural={item['natural_duration']:.2f}s slot={slot:.2f}s final={final_duration:.2f}s speed={speed:.3f}. Video will be extended by SegmentPlanner."
            plan_text = _normalize_tts_text(item["cue"].tts_text or item["cue"].text)
            plans.append(TtsCuePlan(index=item["cue"].index, segment_id=item["segment_id"], text=plan_text, start_seconds=item["adjusted_start"], end_seconds=item["adjusted_end"], slot_duration=slot, generated_duration=item["natural_duration"], applied_speed=speed, final_duration=final_duration, status="warning" if warning else "ok", warning=warning))
            fitted_paths.append((final_path, item["adjusted_start"]))
        voiceover_path = output_dir / "voiceover.wav"
        self._validate_no_voiceover_overlap(plans)
        self._build_voiceover_track(fitted_paths, voiceover_path, video_duration)
        voice_data = resolve_edge_tts_voice(options, payload)
        plan_path = output_dir / "tts_plan.json"
        warnings_list = [plan.warning for plan in plans if plan.warning]

        # ── Timing quality diagnostics ──
        sorted_plans = sorted(plans, key=lambda p: p.start_seconds)
        big_gap_count = 0
        total_big_gap_seconds = 0.0
        max_gap_seconds = 0.0
        overlap_count = 0
        max_overlap_seconds = 0.0
        last_end = 0.0
        prev_end = sorted_plans[0].end_seconds if sorted_plans else 0.0
        for plan in sorted_plans:
            overlap_diag = prev_end - plan.start_seconds
            if overlap_diag > 0:
                overlap_count += 1
                max_overlap_seconds = max(max_overlap_seconds, overlap_diag)
            gap = plan.start_seconds - prev_end
            if gap > 3.0:
                big_gap_count += 1
                total_big_gap_seconds += gap
                max_gap_seconds = max(max_gap_seconds, gap)
            prev_end = max(prev_end, plan.end_seconds)
            last_end = max(last_end, plan.end_seconds)

        plan_payload = {
            "engine": options.tts_engine,
            "voice_mode": "preset",
            "voice": {key: value for key, value in voice_data.items() if key != "rank"},
            "requested_gender": options.tts_voice_gender,
            "fit_policy": options.tts_fit_policy,
            "max_speed": options.tts_max_speed,
            "max_chars": options.tts_max_chars,
            "segment_speeds": {str(key): value for key, value in segment_speeds.items()},
            "warnings": warnings_list,
            "cues": [plan.__dict__ for plan in plans],
            "voiceover_path": str(voiceover_path),
            "timing_quality": {
                "big_gap_count": big_gap_count,
                "total_big_gap_seconds": round(total_big_gap_seconds, 2),
                "max_gap_seconds": round(max_gap_seconds, 2),
                "overlap_count": overlap_count,
                "max_overlap_seconds": round(max_overlap_seconds, 2),
                "last_cue_end_seconds": round(last_end, 2),
            },
        }
        plan_path.write_text(json.dumps(plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"voiceover_path": str(voiceover_path), "tts_plan_path": str(plan_path), "tts_warning_count": str(len(warnings_list))}

    def mix_voiceover(self, video_path: Path, voiceover_path: Path, output_path: Path, options: RenderOptions, encoder_profile: Any = None) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        video_duration = probe_media_duration(video_path)
        voiceover_duration = probe_audio_duration(voiceover_path)
        pad_seconds = max(0.0, voiceover_duration - video_duration)
        if options.original_audio_mode == "mute" or not video_has_audio(video_path):
            filter_complex = f"[1:a]volume={options.voiceover_volume:.3f}[a]"
        else:
            filter_complex = f"[0:a]volume={options.original_audio_volume:.3f}[orig];[1:a]volume={options.voiceover_volume:.3f}[vo];[orig][vo]amix=inputs=2:duration=first:normalize=0[a]"
        cmd = [settings.ffmpeg_binary, "-y", "-i", str(video_path), "-i", str(voiceover_path), "-filter_complex", filter_complex, "-map", "0:v:0", "-map", "[a]"]
        if pad_seconds > 0.05:
            from app.services.video_tools import select_video_encoder, video_encoder_args, quality_for_stability
            profile = encoder_profile or select_video_encoder(options.video_encoder)
            quality = quality_for_stability(options)
            cmd.extend(["-vf", f"tpad=stop_mode=clone:stop_duration={pad_seconds:.3f}", *video_encoder_args(profile, quality)])
        else:
            cmd.extend(["-c:v", "copy"])
        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(output_path)])
        _run(cmd)
        return output_path

    @staticmethod
    def _validate_no_voiceover_overlap(plans: list[TtsCuePlan]) -> None:
        sorted_plans = sorted(plans, key=lambda p: p.start_seconds)
        prev_end = 0.0
        prev_index: int | None = None
        for plan in sorted_plans:
            if plan.start_seconds < prev_end - 0.001:
                overlap = prev_end - plan.start_seconds
                if overlap > TTS_OVERLAP_HARD_FAIL_SECONDS:
                    raise RuntimeError(
                        f"TTS_TIMING_OVERLAP: cue {prev_index} overlaps cue {plan.index} "
                        f"by {overlap:.2f}s. Refusing to mix overlapping voiceover."
                    )
            prev_end = max(prev_end, plan.end_seconds)
            prev_index = plan.index

    def _build_voiceover_track(self, fitted_paths: list[tuple[Path, float]], output_path: Path, video_duration: float) -> None:
        duration = max(0.1, video_duration)
        if not fitted_paths:
            _run([settings.ffmpeg_binary, "-y", "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=48000:d={duration:.3f}", str(output_path)])
            return
        cmd = [settings.ffmpeg_binary, "-y", "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=48000:d={duration:.3f}"]
        for path, _ in fitted_paths:
            cmd.extend(["-i", str(path)])
        filters: list[str] = ["[0:a]volume=0[base]"]
        inputs = ["[base]"]
        for index, (_, start) in enumerate(fitted_paths, start=1):
            delay_ms = max(0, int(round(start * 1000)))
            filters.append(f"[{index}:a]adelay={delay_ms}:all=1[a{index}]")
            inputs.append(f"[a{index}]")
        filters.append(f"{''.join(inputs)}amix=inputs={len(inputs)}:duration=first:normalize=0[aout]")
        cmd.extend(["-filter_complex", ";".join(filters), "-map", "[aout]", "-ar", "48000", "-ac", "2", str(output_path)])
        _run(cmd)

    def _cue_segment_map(self, payload: GeminiPayloadSchema) -> dict[int, int]:
        mapping: dict[int, int] = {}
        for segment in payload.video_segments:
            for index in range(segment.subtitle_start, segment.subtitle_end + 1):
                mapping[index] = segment.segment_id
        return mapping


def edge_tts_status() -> dict[str, str]:
    try:
        import edge_tts  # type: ignore  # noqa: F401
        return {"status": "ready", "engine": "edge_tts", "message": "Edge TTS đã sẵn sàng."}
    except ImportError:
        return {"status": "not_installed", "engine": "edge_tts", "message": "Edge TTS chưa được cài. Chạy pip install -r backend/requirements.txt để bật TTS."}


def tts_clones_dir() -> Path:
    return settings.temp_dir / "tts_voices"


def list_cloned_voices() -> list[dict[str, Any]]:
    return []


def create_clone_voice(name: str, source_audio_path: Path, options: RenderOptions | None = None) -> dict[str, Any]:
    raise RuntimeError("Edge TTS không hỗ trợ clone voice.")


def preview_builtin_voice(voice_id: str, text: str, options: RenderOptions) -> Path:
    voice_data = next((v for v in EDGE_TTS_VOICES if v["id"] == voice_id), None)
    if not voice_data:
        raise ValueError(f"Edge TTS voice '{voice_id}' không tồn tại.")
    TTS_PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = TTS_PREVIEWS_DIR / f"preview_{voice_id}.wav"
    EdgeTtsSynthesizer().synthesize_to_file(_normalize_tts_text(text) or "Xin chào, đây là giọng đọc thử từ Edge TTS.", output_path, options, voice_data)
    return output_path


def preview_clone_voice(clone_id: str, text: str, options: RenderOptions) -> Path:
    raise RuntimeError("Edge TTS không hỗ trợ clone voice.")
