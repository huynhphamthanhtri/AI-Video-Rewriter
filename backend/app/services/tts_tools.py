from __future__ import annotations

import json
import math
import os
import re
import time
import uuid
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas.render import GeminiPayloadSchema, RenderOptions, srt_timestamp_to_seconds


VIENEU_TURBO_VOICES = [
    {"id": "ly", "vieneu_id": "Bích Ngọc (Nữ - Miền Bắc)", "label": "Ly", "description": "Nữ miền Bắc, trung tính, dễ nghe", "gender": "female", "region": "vi_north", "languages": ["vi", "en", "vi_en"], "recommended_for": ["neutral", "drama_storyteller", "podcast_host"]},
    {"id": "ngoc", "vieneu_id": "Bích Ngọc (Nữ - Miền Bắc)", "label": "Ngọc", "description": "Nữ miền Bắc, rõ và sáng", "gender": "female", "region": "vi_north", "languages": ["vi", "en", "vi_en"], "recommended_for": ["neutral", "news_anchor"]},
    {"id": "tuyen", "vieneu_id": "Phạm Tuyên (Nam - Miền Bắc)", "label": "Tuyên", "description": "Nam miền Bắc, thuyết minh rõ", "gender": "male", "region": "vi_north", "languages": ["vi", "en", "vi_en"], "recommended_for": ["neutral", "news_anchor", "sports_commentator"]},
    {"id": "binh", "vieneu_id": "Phạm Tuyên (Nam - Miền Bắc)", "label": "Bình", "description": "Nam miền Bắc, trầm ổn", "gender": "male", "region": "vi_north", "languages": ["vi", "en", "vi_en"], "recommended_for": ["neutral", "podcast_host"]},
    {"id": "doan", "vieneu_id": "Thục Đoan (Nữ - Miền Nam)", "label": "Đoan", "description": "Nữ miền Nam, tự nhiên", "gender": "female", "region": "vi_south", "languages": ["vi", "en", "vi_en"], "recommended_for": ["neutral", "funny_reviewer", "drama_storyteller"]},
    {"id": "vinh", "vieneu_id": "Xuân Vĩnh (Nam - Miền Nam)", "label": "Vĩnh", "description": "Nam miền Nam, thân thiện", "gender": "male", "region": "vi_south", "languages": ["vi", "en", "vi_en"], "recommended_for": ["neutral", "sports_commentator", "podcast_host"]},
]


def list_vieneu_turbo_voices() -> list[dict[str, Any]]:
    return [{key: value for key, value in voice.items() if key != "vieneu_id"} for voice in VIENEU_TURBO_VOICES]


def tts_clones_dir() -> Path:
    return settings.temp_dir / "tts_voices"


def list_cloned_voices() -> list[dict[str, Any]]:
    root = tts_clones_dir()
    if not root.exists():
        return []
    items: list[dict[str, Any]] = []
    for meta_path in root.glob("*/metadata.json"):
        try:
            items.append(json.loads(meta_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(items, key=lambda item: item.get("created_at", 0), reverse=True)


def get_cloned_voice(clone_id: str) -> dict[str, Any]:
    meta_path = tts_clones_dir() / clone_id / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError("Clone voice không tồn tại.")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def clone_voice_embedding_path(clone_id: str) -> Path:
    return tts_clones_dir() / clone_id / "voice.npy"


def resolve_vieneu_voice(options: RenderOptions) -> dict[str, Any]:
    by_id = {voice["id"]: voice for voice in VIENEU_TURBO_VOICES}
    if options.tts_voice_id != "auto":
        if options.tts_voice_id in by_id:
            return by_id[options.tts_voice_id]
    candidates = [v for v in VIENEU_TURBO_VOICES if v["gender"] == (options.tts_voice_gender if options.tts_voice_gender != "auto" else "female")]
    if options.tts_voice_region != "auto":
        region_candidates = [v for v in candidates if v["region"] == options.tts_voice_region]
        if region_candidates:
            candidates = region_candidates
    if options.tts_persona != "neutral":
        persona_matches = [v for v in candidates if options.tts_persona in v.get("recommended_for", [])]
        if persona_matches:
            candidates = persona_matches
    return candidates[0]


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
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def probe_audio_duration(path: Path) -> float:
    cmd = [settings.ffprobe_binary, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return float(result.stdout.strip() or 0)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 0.0


def video_has_audio(path: Path) -> bool:
    cmd = [settings.ffprobe_binary, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
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


def normalize_text_for_vietnamese_tts(text: str) -> str:
    result = text
    number_pattern = re.compile(r'\b(\d{1,3}(?:,\d{3})*)(?:\.(\d+))?\b')
    def _convert_number(m: re.Match) -> str:
        int_part = m.group(1)
        dec_part = m.group(2)
        has_thousands = "," in int_part
        if has_thousands:
            int_part = int_part.replace(",", ".")
        if dec_part is not None:
            return f"{int_part},{dec_part}"
        return int_part

    result = number_pattern.sub(_convert_number, result)
    replacements = [
        (r'\$(\d[\d,.]*)', r'\1 đô la'),
        (r'(\d[\d,.]*)\s*\$', r'\1 đô la'),
        (r'(\d[\d,.]*)\s*km', r'\1 ki-lô-mét'),
        (r'(\d[\d,.]*)\s*kg', r'\1 ki-lô-gam'),
        (r'(\d[\d,.]*)\s*%', r'\1 phần trăm'),
        (r'(\d[\d,.]*)\s*°C', r'\1 độ C'),
        (r'(\d[\d,.]*)\s*cm', r'\1 xăng-ti-mét'),
        (r'(\d[\d,.]*)\s*mm', r'\1 mi-li-mét'),
    ]
    for pattern, repl in replacements:
        result = re.sub(pattern, repl, result, flags=re.IGNORECASE)
    result = re.sub(r'\bCEO\b', 'si-ai-âu', result, flags=re.IGNORECASE)
    result = re.sub(r'\bOK\b', 'âu-kây', result, flags=re.IGNORECASE)
    result = re.sub(r'\bSP\s*500\b', 'ét-pi năm trăm', result, flags=re.IGNORECASE)
    result = re.sub(r'\bUSA\b', 'u ét a', result, flags=re.IGNORECASE)
    result = re.sub(r'\bFBI\b', 'ép bi ai', result, flags=re.IGNORECASE)
    result = re.sub(r'\bCIA\b', 'xi ai ê', result, flags=re.IGNORECASE)
    result = re.sub(r'\bGPS\b', 'gì pi ét', result, flags=re.IGNORECASE)
    result = re.sub(r'\bWiFi\b', 'uai-fai', result, flags=re.IGNORECASE)
    result = re.sub(r'\b4K\b', 'bốn kay', result, flags=re.IGNORECASE)
    result = re.sub(r'\b8K\b', 'tám kay', result, flags=re.IGNORECASE)
    result = re.sub(r'\bHD\b', 'hát-đê', result, flags=re.IGNORECASE)
    return result


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 1.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil((percentile / 100) * len(ordered)) - 1))
    return ordered[index]


class VieneuTurboSynthesizer:
    def __init__(self, emotion: str = "natural"):
        try:
            from vieneu import Vieneu  # type: ignore
        except ImportError as exc:
            raise RuntimeError("VieNeu Turbo chưa được cài. Vui lòng chạy scripts/install_tts.ps1 hoặc tắt TTS voiceover.") from exc
        try:
            self.tts = Vieneu(mode="turbo", emotion=emotion)
        except TypeError:
            self.tts = Vieneu(mode="turbo")

    def encode_reference_to_file(self, reference_audio_path: Path, output_path: Path) -> None:
        import numpy as np

        embedding = self.tts.encode_reference(str(reference_audio_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(output_path, embedding)

    def synthesize_to_file(self, text: str, output_path: Path, options: RenderOptions, voice_data: dict[str, Any] | None = None, clone_embedding_path: Path | None = None) -> None:
        if clone_embedding_path is not None:
            import numpy as np

            voice = np.load(clone_embedding_path, allow_pickle=False)
        else:
            voice_name = (voice_data or {}).get("vieneu_id")
            if not voice_name:
                raise RuntimeError("Không tìm thấy vieneu_id trong voice_data.")
            try:
                voice = self.tts.get_preset_voice(voice_name)
            except Exception as exc:
                available = ", ".join(v[1] for v in self.tts.list_preset_voices())
                raise RuntimeError(
                    f"VieNeu không tìm thấy preset voice '{voice_name}'. "
                    f"Các voice có sẵn: {available}"
                ) from exc
        audio = self.tts.infer(text=text, voice=voice, temperature=options.tts_temperature, top_k=options.tts_top_k, max_chars=options.tts_max_chars, show_progress=False, apply_watermark=options.tts_apply_watermark)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.tts.save(audio, str(output_path))


class TtsVoiceoverService:
    def _split_long_cue(self, text: str, max_chars: int = 200) -> list[str]:
        if len(text) <= max_chars:
            return [text]
        parts: list[str] = []
        sentences = re.split(r'(?<=[.!?])\s+', text)
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= max_chars:
                current = (current + " " + sentence).strip()
            else:
                if current:
                    parts.append(current)
                if len(sentence) > max_chars:
                    words = sentence.split()
                    chunk = ""
                    for word in words:
                        if len(chunk) + len(word) + 1 <= max_chars:
                            chunk = (chunk + " " + word).strip()
                        else:
                            parts.append(chunk)
                            chunk = word
                    if chunk:
                        current = chunk
                    else:
                        current = ""
                else:
                    current = sentence
        if current:
            parts.append(current)
        return parts or [text]

    def generate_voiceover(self, payload: GeminiPayloadSchema, output_dir: Path, workspace_dir: Path, options: RenderOptions, video_duration: float, progress_callback=None, cancel_callback=None) -> dict[str, Any]:
        if options.tts_engine != "vieneu_turbo":
            raise RuntimeError(f"TTS engine chưa hỗ trợ: {options.tts_engine}")
        tts_dir = workspace_dir / "tts"
        raw_dir = tts_dir / "raw"
        fitted_dir = tts_dir / "fitted"
        raw_dir.mkdir(parents=True, exist_ok=True)
        fitted_dir.mkdir(parents=True, exist_ok=True)
        if progress_callback:
            progress_callback({"step": "Generate TTS", "message": "Đang load VieNeu Turbo và tạo voiceover theo SRT...", "progress": 90, "phase": "tts_generate", "phase_progress": 0.0})
        synth = VieneuTurboSynthesizer(options.tts_emotion)
        voice_data = resolve_vieneu_voice(options)
        clone_meta: dict[str, Any] | None = None
        clone_embedding: Path | None = None
        if options.tts_voice_mode == "clone":
            if not options.tts_clone_voice_id:
                raise RuntimeError("Bạn chưa chọn cloned voice.")
            clone_meta = get_cloned_voice(options.tts_clone_voice_id)
            clone_embedding = clone_voice_embedding_path(options.tts_clone_voice_id)
            if not clone_embedding.exists():
                raise RuntimeError("Không tìm thấy embedding của cloned voice.")
        cue_to_segment = self._cue_segment_map(payload)
        required_by_segment: dict[int | None, list[float]] = {}
        generated: list[dict[str, Any]] = []
        total = max(1, len(payload.srt))
        for pos, cue in enumerate(payload.srt, start=1):
            if cancel_callback:
                cancel_callback()
            start = srt_timestamp_to_seconds(cue.start)
            end = srt_timestamp_to_seconds(cue.end)
            slot = max(0.05, end - start)
            segment_id = cue_to_segment.get(cue.index)
            raw_text = normalize_text_for_vietnamese_tts(cue.text)
            sub_texts = self._split_long_cue(raw_text, options.tts_max_chars)
            raw_paths: list[Path] = []
            total_generated_duration = 0.0
            for sub_idx, sub_text in enumerate(sub_texts):
                sub_raw_path = raw_dir / f"cue_{cue.index:04d}_sub_{sub_idx:02d}.wav"
                synth.synthesize_to_file(sub_text, sub_raw_path, options, voice_data, clone_embedding)
                sub_duration = probe_audio_duration(sub_raw_path)
                total_generated_duration += sub_duration
                raw_paths.append(sub_raw_path)
            raw_path = raw_dir / f"cue_{cue.index:04d}.wav"
            if len(raw_paths) == 1:
                if raw_paths[0] != raw_path:
                    raw_paths[0].rename(raw_path)
                else:
                    raw_path = raw_paths[0]
            else:
                concat_list = fitted_dir / f"concat_{cue.index:04d}.txt"
                with open(concat_list, "w", encoding="utf-8") as f:
                    for p in raw_paths:
                        f.write(f"file '{p}'\n")
                _run([settings.ffmpeg_binary, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(raw_path)])
            generated_duration = probe_audio_duration(raw_path) or total_generated_duration
            required_speed = max(1.0, generated_duration / slot) if generated_duration > 0 else 1.0
            required_by_segment.setdefault(segment_id, []).append(required_speed)
            generated.append({"cue": cue, "raw_path": raw_path, "start": start, "end": end, "slot": slot, "segment_id": segment_id, "generated_duration": generated_duration})
            if progress_callback:
                progress_callback({"step": "Generate TTS", "message": f"Đang tạo TTS {pos}/{total}...", "progress": 90 + int((pos / total) * 3), "phase": "tts_generate", "phase_progress": pos / total})
        generated.sort(key=lambda x: x["start"])
        for i in range(len(generated) - 1):
            curr = generated[i]
            next_start = generated[i + 1]["start"]
            curr_end = curr["start"] + curr["slot"]
            overlap = curr_end - next_start
            if overlap > 0.1:
                curr["slot"] = max(0.05, next_start - curr["start"] - 0.01)
        required_by_segment = {}
        for item in generated:
            sid = item["segment_id"]
            req = max(1.0, item["generated_duration"] / item["slot"]) if item["generated_duration"] > 0 else 1.0
            required_by_segment.setdefault(sid, []).append(req)
        segment_speeds = {segment_id: min(max(_percentile(values, 90), 1.0), options.tts_max_speed) for segment_id, values in required_by_segment.items()}
        plans: list[TtsCuePlan] = []
        fitted_paths: list[tuple[Path, float]] = []
        for item in generated:
            if cancel_callback:
                cancel_callback()
            speed = segment_speeds.get(item["segment_id"], 1.0)
            fitted_path = fitted_dir / f"cue_{item['cue'].index:04d}.wav"
            speed_filter = _atempo_filter(speed)
            silence_filter = "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_duration=0.05:start_threshold=-50dB,areverse"
            fit_filters = f"{silence_filter},{speed_filter},asetpts=PTS-STARTPTS"
            _run([settings.ffmpeg_binary, "-y", "-i", str(item["raw_path"]), "-af", fit_filters, "-ar", "48000", "-ac", "2", str(fitted_path)])
            final_duration = probe_audio_duration(fitted_path)
            overflow = final_duration > item["slot"]
            if overflow:
                trim_path = fitted_dir / f"cue_{item['cue'].index:04d}_trim.wav"
                _run([settings.ffmpeg_binary, "-y", "-i", str(fitted_path), "-af", f"atrim=0:{item['slot']:.3f},asetpts=PTS-STARTPTS", "-ar", "48000", "-ac", "2", str(trim_path)])
                os.replace(str(trim_path), str(fitted_path))
                final_duration = probe_audio_duration(fitted_path)
            overflow_final = final_duration > item["slot"]
            warning = "TTS_OVERFLOW: audio vẫn dài hơn slot sau khi ép tốc độ; đã trim để tránh overlap." if overflow_final else ""
            plans.append(TtsCuePlan(index=item["cue"].index, segment_id=item["segment_id"], text=item["cue"].text, start_seconds=item["start"], end_seconds=item["end"], slot_duration=item["slot"], generated_duration=item["generated_duration"], applied_speed=speed, final_duration=final_duration, status="warning" if warning else "ok", warning=warning))
            fitted_paths.append((fitted_path, item["start"]))
        voiceover_path = output_dir / "voiceover.wav"
        self._build_voiceover_track(fitted_paths, voiceover_path, video_duration)
        plan_path = output_dir / "tts_plan.json"
        warnings = [plan.warning for plan in plans if plan.warning]
        plan_payload = {
            "engine": options.tts_engine,
            "language": options.tts_language,
            "persona": options.tts_persona,
            "voice_mode": options.tts_voice_mode,
            "clone_voice": clone_meta,
            "voice": {key: value for key, value in voice_data.items() if key != "vieneu_id"},
            "selected_vieneu_voice": voice_data.get("vieneu_id"),
            "requested_gender": options.tts_voice_gender,
            "emotion": options.tts_emotion,
            "fit_policy": options.tts_fit_policy,
            "max_speed": options.tts_max_speed,
            "temperature": options.tts_temperature,
            "top_k": options.tts_top_k,
            "max_chars": options.tts_max_chars,
            "apply_watermark": options.tts_apply_watermark,
            "segment_speeds": {str(key): value for key, value in segment_speeds.items()},
            "warnings": warnings,
            "cues": [plan.__dict__ for plan in plans],
            "voiceover_path": str(voiceover_path),
        }
        plan_path.write_text(json.dumps(plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"voiceover_path": str(voiceover_path), "tts_plan_path": str(plan_path), "tts_warning_count": str(len(warnings))}

    def mix_voiceover(self, video_path: Path, voiceover_path: Path, output_path: Path, options: RenderOptions) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if options.original_audio_mode == "mute" or not video_has_audio(video_path):
            filter_complex = f"[1:a]volume={options.voiceover_volume:.3f}[a]"
        else:
            filter_complex = f"[0:a]volume={options.original_audio_volume:.3f}[orig];[1:a]volume={options.voiceover_volume:.3f}[vo];[orig][vo]amix=inputs=2:duration=first:normalize=0[a]"
        _run([settings.ffmpeg_binary, "-y", "-i", str(video_path), "-i", str(voiceover_path), "-filter_complex", filter_complex, "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(output_path)])
        return output_path

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


def vieneu_tts_status() -> dict[str, str]:
    try:
        import vieneu  # type: ignore  # noqa: F401
        return {"status": "ready", "engine": "vieneu_turbo", "message": "VieNeu Turbo đã sẵn sàng."}
    except ImportError:
        return {"status": "not_installed", "engine": "vieneu_turbo", "message": "VieNeu Turbo chưa được cài. Chạy scripts/install_tts.ps1 để bật TTS."}


def create_clone_voice(name: str, source_audio_path: Path, options: RenderOptions | None = None) -> dict[str, Any]:
    clone_id = uuid.uuid4().hex
    clone_dir = tts_clones_dir() / clone_id
    clone_dir.mkdir(parents=True, exist_ok=True)
    reference_path = clone_dir / "reference.wav"
    _run([settings.ffmpeg_binary, "-y", "-i", str(source_audio_path), "-t", "60", "-ar", "24000", "-ac", "1", str(reference_path)])
    duration = probe_audio_duration(reference_path)
    synth = VieneuTurboSynthesizer((options or RenderOptions()).tts_emotion)
    synth.encode_reference_to_file(reference_path, clone_dir / "voice.npy")
    metadata = {"id": clone_id, "name": name.strip() or "Cloned voice", "reference_audio_path": str(reference_path), "created_at": time.time(), "duration_seconds": f"{duration:.3f}"}
    (clone_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def preview_builtin_voice(voice_id: str, text: str, options: RenderOptions) -> Path:
    voice_data = next((v for v in VIENEU_TURBO_VOICES if v["id"] == voice_id), None)
    if not voice_data:
        raise ValueError(f"Built-in voice '{voice_id}' không tồn tại.")
    preview_dir = settings.temp_dir / "tts_voice_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    output_path = preview_dir / f"preview_{voice_id}.wav"
    synth = VieneuTurboSynthesizer(options.tts_emotion)
    synth.synthesize_to_file(text.strip() or "Xin chào, đây là giọng đọc thử từ VieNeu Turbo.", output_path, options, voice_data)
    return output_path


def preview_clone_voice(clone_id: str, text: str, options: RenderOptions) -> Path:
    clone_dir = tts_clones_dir() / clone_id
    if not clone_dir.exists():
        raise FileNotFoundError("Clone voice không tồn tại.")
    output_path = clone_dir / "preview.wav"
    synth = VieneuTurboSynthesizer(options.tts_emotion)
    synth.synthesize_to_file(text.strip() or "Xin chào, đây là bản thử giọng clone bằng VieNeu Turbo.", output_path, options, clone_embedding_path=clone_voice_embedding_path(clone_id))
    return output_path
