from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import logging
import re
import shutil
import subprocess
import time
import sys
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.core.config import settings
from app.schemas.render import GeminiPayloadSchema, MAX_FREEZE_FRAME_SECONDS, RenderOptions, SourceSchema, SegmentPlanItem, clip_timestamp_to_seconds, seconds_to_clip_timestamp, seconds_to_srt_timestamp, srt_timestamp_to_seconds
from app.services.title_layout import _title_font_path, compute_title_layout


ProgressCallback = Callable[[dict], None]
CancelCallback = Callable[[], None]

AUDIO_BITRATE = {"fast": "128k", "balanced": "160k", "high": "192k"}
logger = logging.getLogger(__name__)

YOUTUBE_COOKIE_DOMAINS = {".youtube.com", "youtube.com", ".google.com", "google.com", ".accounts.google.com"}
YOUTUBE_AUTH_COOKIE_NAMES = {
    "SAPISID", "APISID", "SSID", "SID", "HSID", "LSID", "LOGIN_INFO",
    "__Secure-1PAPISID", "__Secure-3PAPISID",
    "__Secure-1PSAPISID", "__Secure-3PSAPISID",
    "__Secure-1PSID", "__Secure-3PSID",
    "__Secure-1PSIDTS", "__Secure-3PSIDTS",
    "__Secure-1PSIDCC", "__Secure-3PSIDCC",
}
YOUTUBE_STRONG_AUTH_COOKIE_NAMES = {
    "SAPISID", "APISID",
    "__Secure-1PAPISID", "__Secure-3PAPISID",
    "__Secure-1PSAPISID", "__Secure-3PSAPISID",
    "LOGIN_INFO",
}


@dataclass
class CookieHealth:
    valid: bool
    errors: list[str]
    warnings: list[str]
    total_cookies: int
    youtube_cookies: int
    auth_cookies: int
    strong_auth_cookies: int = 0
    has_strong_auth: bool = False
    expired_cookies: int = 0
    nearest_expiry: float | None = None


def analyze_ytdlp_cookie_file(path: Path) -> CookieHealth:
    errors: list[str] = []
    warnings: list[str] = []
    total = 0
    youtube = 0
    auth = 0
    strong_auth = 0
    expired = 0
    nearest_expiry: float | None = None
    now = time.time()

    if not path.exists():
        return CookieHealth(valid=False, errors=["File cookies không tồn tại."], warnings=[], total_cookies=0, youtube_cookies=0, auth_cookies=0, strong_auth_cookies=0, has_strong_auth=False, expired_cookies=0, nearest_expiry=None)

    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return CookieHealth(valid=False, errors=[f"Không thể đọc file cookies: {exc}"], warnings=[], total_cookies=0, youtube_cookies=0, auth_cookies=0, strong_auth_cookies=0, has_strong_auth=False, expired_cookies=0, nearest_expiry=None)

    if not raw.strip():
        return CookieHealth(valid=False, errors=["File cookies rỗng."], warnings=[], total_cookies=0, youtube_cookies=0, auth_cookies=0, strong_auth_cookies=0, has_strong_auth=False, expired_cookies=0, nearest_expiry=None)

    has_netscape_header = raw.strip().startswith("# Netscape HTTP Cookie File") or raw.strip().startswith("# HTTP Cookie File")
    if not has_netscape_header:
        warnings.append("File cookies thiếu header Netscape HTTP Cookie File — yt-dlp vẫn có thể dùng được.")

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        total += 1
        domain = parts[0]
        name = parts[5] if len(parts) > 5 else ""

        if any(domain == d or domain.endswith("." + d.lstrip(".")) for d in YOUTUBE_COOKIE_DOMAINS):
            youtube += 1
            if name in YOUTUBE_AUTH_COOKIE_NAMES:
                auth += 1
                if name in YOUTUBE_STRONG_AUTH_COOKIE_NAMES:
                    strong_auth += 1
            if len(parts) > 4:
                try:
                    expires = float(parts[4])
                    if expires <= 0:
                        pass
                    elif expires < now:
                        expired += 1
                    if expires > 0 and (nearest_expiry is None or expires < nearest_expiry):
                        nearest_expiry = expires
                except ValueError:
                    pass

    has_strong_auth = strong_auth > 0

    if total == 0:
        return CookieHealth(valid=False, errors=["File cookies không có dòng cookie hợp lệ (cần format tab-separated Netscape)."], warnings=[], total_cookies=0, youtube_cookies=0, auth_cookies=0, strong_auth_cookies=0, has_strong_auth=False, expired_cookies=0, nearest_expiry=None)

    if youtube == 0:
        return CookieHealth(valid=False, errors=[f"File cookies không có cookie nào cho domain YouTube/Google. Cần export cookies từ trình duyệt đã đăng nhập YouTube."], warnings=warnings, total_cookies=total, youtube_cookies=youtube, auth_cookies=auth, strong_auth_cookies=strong_auth, has_strong_auth=has_strong_auth, expired_cookies=expired, nearest_expiry=nearest_expiry)

    if auth == 0:
        warnings.append("File cookies thiếu cookie auth (SAPISID, SSID...). yt-dlp có thể bị YouTube chặn.")
    elif not has_strong_auth:
        warnings.append("File cookies có cookie auth yếu (session token), thiếu SAPISID/APISID/LOGIN_INFO — YouTube có thể vẫn yêu cầu đăng nhập.")

    if expired == total:
        return CookieHealth(valid=False, errors=["Tất cả cookie YouTube/Google trong file đã hết hạn. Hãy export cookies mới từ trình duyệt đã đăng nhập YouTube."], warnings=warnings, total_cookies=total, youtube_cookies=youtube, auth_cookies=auth, strong_auth_cookies=strong_auth, has_strong_auth=has_strong_auth, expired_cookies=expired, nearest_expiry=nearest_expiry)

    if expired > 0:
        warnings.append(f"{expired}/{total} cookie YouTube/Google đã hết hạn.")

    return CookieHealth(valid=True, errors=errors, warnings=warnings, total_cookies=total, youtube_cookies=youtube, auth_cookies=auth, strong_auth_cookies=strong_auth, has_strong_auth=has_strong_auth, expired_cookies=expired, nearest_expiry=nearest_expiry)
CPU_QUALITY = {
    "fast": ["-preset", "veryfast", "-crf", "28"],
    "balanced": ["-preset", "veryfast", "-crf", "23"],
    "high": ["-preset", "fast", "-crf", "20"],
}
GPU_QUALITY = {
    "fast": ["-rc", "vbr", "-cq", "26", "-b:v", "5M", "-maxrate", "8M"],
    "balanced": ["-rc", "vbr", "-cq", "23", "-b:v", "8M", "-maxrate", "12M"],
    "high": ["-rc", "vbr", "-cq", "20", "-b:v", "12M", "-maxrate", "18M"],
}
NVENC_PRESETS = {
    "fast": "p1",
    "balanced": "p4",
    "high": "p6",
}


def ui_safe_error(text: str, max_len: int = 500) -> str:
    lines = text.split("\n")
    safe_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("STDERR_FILE:") or stripped.startswith("STDOUT_FILE:"):
            continue
        if stripped == "Traceback (most recent call last):":
            continue
        if stripped.startswith("File \"") or stripped.startswith("  File \""):
            continue
        if stripped.startswith("[debug] Invoking http downloader on "):
            continue
        safe_lines.append(line)
    result = "\n".join(safe_lines).strip()
    if len(result) > max_len:
        result = result[: max_len - 3] + "..."
    return result


def _truncate_for_log(text: str, max_len: int = 500) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


@dataclass(frozen=True)
class EncoderProfile:
    name: str
    label: str
    codec: str
    hardware: bool


CPU_ENCODER = EncoderProfile("cpu", "CPU libx264", "libx264", False)
_ENCODER_CACHE: dict[str, EncoderProfile] = {}


def _ffmpeg_encoders() -> str:
    try:
        result = subprocess.run([settings.ffmpeg_binary, "-hide_banner", "-encoders"], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return result.stdout + result.stderr
    except (OSError, subprocess.CalledProcessError):
        return ""


def _encoder_runtime_works(codec: str) -> bool:
    cmd = [settings.ffmpeg_binary, "-y", "-f", "lavfi", "-i", "testsrc2=s=128x128:r=30:d=1", "-c:v", codec, "-f", "null", "-"]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def video_encoder_diagnostics() -> dict:
    candidates = {
        "nvenc": EncoderProfile("nvenc", "NVIDIA NVENC", "h264_nvenc", True),
        "qsv": EncoderProfile("qsv", "Intel Quick Sync", "h264_qsv", True),
        "amf": EncoderProfile("amf", "AMD AMF", "h264_amf", True),
    }
    enabled = _ffmpeg_encoders()
    candidate_rows = []
    for profile in candidates.values():
        available = profile.codec in enabled
        runtime_ok = _encoder_runtime_works(profile.codec) if available else False
        candidate_rows.append({
            "name": profile.name,
            "label": profile.label,
            "codec": profile.codec,
            "available": available,
            "runtime_ok": runtime_ok,
        })
    selected = select_video_encoder("auto")
    return {
        "selected": selected.name,
        "label": selected.label,
        "codec": selected.codec,
        "hardware": selected.hardware,
        "checked_at": time.time(),
        "ffmpeg_binary": settings.ffmpeg_binary,
        "hardware_candidates": candidate_rows,
    }


def select_video_encoder(mode_override: str | None = None) -> EncoderProfile:
    mode = (mode_override or settings.video_encoder).strip().lower()
    if mode in _ENCODER_CACHE:
        return _ENCODER_CACHE[mode]
    if mode == "cpu":
        _ENCODER_CACHE[mode] = CPU_ENCODER
        logger.info("Video encoder selected: %s (%s), mode=%s", CPU_ENCODER.label, CPU_ENCODER.codec, mode)
        return _ENCODER_CACHE[mode]

    candidates = {
        "nvenc": EncoderProfile("nvenc", "NVIDIA NVENC", "h264_nvenc", True),
        "qsv": EncoderProfile("qsv", "Intel Quick Sync", "h264_qsv", True),
        "amf": EncoderProfile("amf", "AMD AMF", "h264_amf", True),
    }
    enabled = _ffmpeg_encoders()
    order = [mode] if mode in candidates else ["nvenc", "qsv", "amf"]
    for key in order:
        profile = candidates[key]
        if profile.codec not in enabled:
            logger.warning("Video encoder candidate unavailable: %s (%s)", profile.label, profile.codec)
            continue
        if _encoder_runtime_works(profile.codec):
            _ENCODER_CACHE[mode] = profile
            logger.info("Video encoder selected: %s (%s), mode=%s", profile.label, profile.codec, mode)
            return _ENCODER_CACHE[mode]
        logger.warning("Video encoder candidate failed runtime test: %s (%s)", profile.label, profile.codec)
    _ENCODER_CACHE[mode] = CPU_ENCODER
    logger.info("Video encoder selected: %s (%s), mode=%s", CPU_ENCODER.label, CPU_ENCODER.codec, mode)
    return _ENCODER_CACHE[mode]


def quality_for_stability(options: RenderOptions) -> str:
    if options.render_stability == "fast":
        return "fast"
    if options.render_stability == "max_quality":
        return "high"
    return options.render_quality


def segment_fps_value(options: RenderOptions) -> int:
    if options.segment_fps == "30":
        return 30
    if options.segment_fps == "60":
        return 60
    return settings.segment_fps


def video_encoder_args(profile: EncoderProfile, quality: str) -> list[str]:
    if profile.codec == "h264_nvenc":
        return ["-c:v", profile.codec, "-preset", NVENC_PRESETS.get(quality, "p4"), *GPU_QUALITY[quality], "-pix_fmt", "yuv420p"]
    if profile.hardware:
        return ["-c:v", profile.codec, "-preset", "fast", *GPU_QUALITY[quality], "-pix_fmt", "yuv420p"]
    return ["-c:v", profile.codec, *CPU_QUALITY[quality], "-pix_fmt", "yuv420p"]


def audio_encoder_args(quality: str) -> list[str]:
    return ["-c:a", "aac", "-b:a", AUDIO_BITRATE[quality], "-ar", "48000", "-ac", "2"]


def render_parallelism_diagnostics(
    encoder: EncoderProfile,
    options: RenderOptions,
    segment_count: int,
    max_workers: int | None = None,
    ffmpeg_threads: int | None = None,
) -> dict:
    return {
        "cpu_count": os.cpu_count() or 1,
        "encoder_name": encoder.name,
        "encoder_label": encoder.label,
        "encoder_codec": encoder.codec,
        "encoder_hardware": encoder.hardware,
        "segment_count": segment_count,
        "segment_fps": segment_fps_value(options),
        "max_parallel_workers": max_workers,
        "ffmpeg_threads": ffmpeg_threads,
    }


def calculate_segment_parallelism(
    encoder: EncoderProfile,
    segment_count: int,
) -> tuple[int, int]:
    cpu_count = os.cpu_count() or 4

    if segment_count <= 3:
        return 1, 0

    if encoder.codec == "h264_nvenc":
        return min(segment_count, 3, cpu_count), 1

    if encoder.codec in {"h264_qsv", "h264_amf"}:
        return min(segment_count, 2, cpu_count), 1

    if cpu_count <= 4:
        workers = 1
    elif cpu_count <= 8:
        workers = 2
    else:
        workers = min(3, max(2, cpu_count // 4))

    workers = min(workers, segment_count)
    ffmpeg_threads = max(1, min(4, max(1, cpu_count // max(1, workers))))
    return workers, ffmpeg_threads


def ffmpeg_thread_args(thread_count: int | None) -> list[str]:
    if thread_count and thread_count > 0:
        return ["-threads", str(thread_count)]
    return []


def _ffmpeg_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _wrap_title(value: str, max_lines: int = 2, chars_per_line: int = 34) -> str:
    words = value.strip().split()
    if not words:
        return ""
    lines: list[str] = []
    current = ""
    max_lines = max(1, min(3, int(max_lines)))
    max_chars = max(16, min(60, int(chars_per_line)))
    for word in words:
        next_line = f"{current} {word}".strip()
        if len(next_line) > max_chars and current:
            lines.append(current)
            current = word
            if len(lines) == max_lines:
                break
        else:
            current = next_line
    if current and len(lines) < max_lines:
        lines.append(current)
    text = "\n".join(lines[:max_lines])
    original = " ".join(words)
    if len(text.replace("\n", " ")) < len(original) and not text.endswith("..."):
        text = text[: max(0, len(text) - 3)].rstrip() + "..."
    return text


SMART_CLEANUP_PATTERNS = (
    "*_raw.mp4",
    "*_transformed.mp4",
    "*_pre_blur.mp4",
    "*_raw_blurred.mp4",
    "*_blurred.mp4",
    "*_tts_mixed.mp4",
    "*_title.mp4",
    "*_title.txt",
    "*_spedup.mp4",
)


def _probe_has_audio(path: Path) -> bool:
    cmd = [settings.ffprobe_binary, "-v", "error", "-select_streams", "a:0",
           "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)]
    try:
        return bool(subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8", errors="replace").stdout.strip())
    except Exception:
        return True


def cleanup_large_intermediate_artifacts(output_dir: Path, keep_paths: set[Path], enabled: bool = True) -> list[str]:
    if not enabled or not output_dir.exists():
        return []
    output_root = output_dir.resolve()
    protected = {path.resolve() for path in keep_paths if path}
    deleted: list[str] = []
    for pattern in SMART_CLEANUP_PATTERNS:
        for candidate in output_dir.glob(pattern):
            try:
                resolved = candidate.resolve()
                resolved.relative_to(output_root)
            except (OSError, ValueError):
                continue
            if resolved in protected or not candidate.is_file():
                continue
            try:
                candidate.unlink()
            except OSError:
                continue
            deleted.append(str(candidate))
    return deleted


def _cmd_with_progress(cmd: list[str]) -> list[str]:
    if not cmd or "-progress" in cmd:
        return cmd
    return [cmd[0], "-progress", "pipe:1", "-nostats", *cmd[1:]]


def _kill_ffmpeg_tree(pid: int) -> None:
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10)
    except Exception:
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
        except Exception:
            pass


def _run_ffmpeg(cmd: list[str], cwd: str | None = None, progress_callback: ProgressCallback | None = None, duration_seconds: float | None = None, progress_start: int = 0, progress_end: int = 100, cancel_callback: CancelCallback | None = None) -> None:
    is_progress_mode = progress_callback is not None and duration_seconds and duration_seconds > 0
    if not cancel_callback and not is_progress_mode:
        if cancel_callback:
            cancel_callback()
        subprocess.run(cmd, check=True, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if cancel_callback:
            cancel_callback()
        return
    actual_cmd = _cmd_with_progress(cmd) if is_progress_mode else cmd
    process = subprocess.Popen(actual_cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    output: list[str] = []
    assert process.stdout is not None
    try:
        for line in process.stdout:
            output.append(line)
            if cancel_callback:
                cancel_callback()
            if is_progress_mode and line.startswith("out_time_ms="):
                try:
                    out_seconds = int(line.split("=", 1)[1].strip()) / 1_000_000
                except ValueError:
                    continue
                ratio = max(0.0, min(1.0, out_seconds / duration_seconds))
                progress_callback({"progress": progress_start + int(ratio * max(0, progress_end - progress_start)), "phase_progress": ratio})
        returncode = process.wait()
    except Exception:
        _kill_ffmpeg_tree(process.pid)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        raise
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, cmd, output="".join(output), stderr="".join(output))


def run_ffmpeg_with_encoder_fallback(cmd_builder: Callable[[EncoderProfile], list[str]], message: str, cwd: str | None = None, mode_override: str | None = None, progress_callback: ProgressCallback | None = None, duration_seconds: float | None = None, progress_start: int = 0, progress_end: int = 100, cancel_callback: CancelCallback | None = None) -> EncoderProfile:
    profile = select_video_encoder(mode_override)
    try:
        _run_ffmpeg(cmd_builder(profile), cwd=cwd, progress_callback=progress_callback, duration_seconds=duration_seconds, progress_start=progress_start, progress_end=progress_end, cancel_callback=cancel_callback)
        return profile
    except subprocess.CalledProcessError as exc:
        if not profile.hardware:
            detail = exc.stderr or exc.stdout or str(exc)
            raise RuntimeError(f"{message}: {detail}") from exc
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        logger.warning("Hardware encoder %s failed during %s. Falling back to CPU libx264. Detail: %s", profile.codec, message, _truncate_for_log(detail, 500))
        try:
            _run_ffmpeg(cmd_builder(CPU_ENCODER), cwd=cwd, progress_callback=progress_callback, duration_seconds=duration_seconds, progress_start=progress_start, progress_end=progress_end, cancel_callback=cancel_callback)
            return CPU_ENCODER
        except subprocess.CalledProcessError as fallback_exc:
            detail = fallback_exc.stderr or fallback_exc.stdout or exc.stderr or exc.stdout or str(fallback_exc)
            raise RuntimeError(f"{message}: {detail}") from fallback_exc


def probe_video_metadata(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    cmd = [settings.ffprobe_binary, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height,avg_frame_rate,duration,bit_rate", "-of", "json", str(path)]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        payload = json.loads(result.stdout)
        stream = (payload.get("streams") or [{}])[0]
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError, IndexError):
        return {}
    width = stream.get("width")
    height = stream.get("height")
    return {
        "codec": str(stream.get("codec_name") or ""),
        "fps": str(stream.get("avg_frame_rate") or ""),
        "resolution": f"{width}x{height}" if width and height else "",
        "duration_seconds": str(stream.get("duration") or ""),
        "bit_rate": str(stream.get("bit_rate") or ""),
    }


def safe_filename_prefix(value: str | None, fallback: str = "render") -> str:
    raw_value = (value or fallback).strip().lower()
    normalized = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw_value)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized[:80] or fallback


def safe_filename_pretty(value: str, fallback: str = "video") -> str:
    raw = (value or fallback).strip().replace(" ", "_")
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized[:120] or fallback


def safe_output_dir_name(name: str | None) -> str | None:
    if not name or not name.strip():
        return None
    val = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in name.strip())
    val = re.sub(r"_+", "_", val).strip("_")
    return val[:120] or None


def safe_output_dir_path(path: str | None) -> Path | None:
    if not path or not path.strip():
        return None
    p = Path(path).resolve()
    if not p.is_absolute():
        return None
    parent = p.parent
    while parent != parent.parent:
        if parent.name.lower() in ("windows", "program files", "program files (x86)", "programdata"):
            return None
        parent = parent.parent
    if p.parent == p:
        return None
    return p


def final_video_stem(payload: GeminiPayloadSchema, options: RenderOptions) -> str:
    title = payload.metadata.video_title
    hashtags = payload.metadata.hashtags or []
    if not hashtags:
        badge_text = TitleOverlay().resolve_badge(payload, options)
        if badge_text:
            hashtags.append(badge_text)
    if hashtags:
        ht_part = "_".join(safe_filename_prefix(h) for h in hashtags)
        stem = safe_filename_pretty(f"{title}_{ht_part}")
    else:
        stem = safe_filename_pretty(title)
    return stem[:120] or "video"


def final_videos_dir() -> Path:
    return settings.outputs_dir / "final_videos"


def copy_final_video_to_library(final_video: Path) -> Path | None:
    if not final_video.exists() or not final_video.is_file():
        return None
    library_dir = final_videos_dir()
    library_dir.mkdir(parents=True, exist_ok=True)
    library_path = _unique_path(library_dir / final_video.name)
    shutil.copy2(final_video, library_path)
    return library_path


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.parent / f"{path.stem}_{counter}{path.suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def sanitize_url(value: str) -> str:
    cleaned = value.strip().strip("<>").strip("'\"`")
    markdown_match = re.fullmatch(r"\[[^\]]+]\(([^)]+)\)", cleaned)
    if markdown_match:
        cleaned = markdown_match.group(1).strip().strip("<>").strip("'\"`")
    cleaned = cleaned.rstrip(";，,。")
    try:
        parsed = urllib.parse.urlparse(cleaned)
        if parsed.netloc in {"google.com", "www.google.com"}:
            qs = urllib.parse.parse_qs(parsed.query)
            q = qs.get("q")
            if q:
                inner = urllib.parse.unquote(q[0])
                inner_parsed = urllib.parse.urlparse(inner)
                if inner_parsed.netloc in {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}:
                    return sanitize_url(inner)
    except Exception:
        pass
    return cleaned


def source_cache_path(url: str) -> Path:
    key = hashlib.sha1(sanitize_url(url).encode("utf-8")).hexdigest()
    return settings.temp_dir / "source_cache" / f"{key}.mp4"


def _resolve_path(value: str) -> Path:
    try:
        return Path(value).expanduser().resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"Đường dẫn không hợp lệ hoặc không tồn tại: {value}") from exc


def _ensure_path_under(path: Path, root: Path, label: str) -> Path:
    root_path = root.expanduser().resolve()
    try:
        path.relative_to(root_path)
    except ValueError as exc:
        raise ValueError(f"{label} phải nằm trong thư mục cho phép: {root_path}") from exc
    return path


def _segment_plan_to_dict(plan: SegmentPlanItem) -> dict[str, object]:
    d = plan.model_dump()
    d["original_scene_duration"] = d.pop("scene_duration")
    d["final_scene_duration"] = d.pop("required_duration")
    return d


def _apply_segment_plan_to_payload(payload: GeminiPayloadSchema, segment_plans: list[SegmentPlanItem], srt_shifts: dict[int, float] | None = None) -> None:
    """Modifies payload SRT timestamps and segment metadata according to the plan.

    Handles:
    - source_end extension for footage_extend
    - freeze_frame_duration assignment
    - SRT cue internal scaling when video_speed_factor != 1.0
    - Last-cue end extension when extend_seconds > 0
    """
    plan_by_seg = {p.segment_id: p for p in segment_plans}

    # Apply source_end extensions and freeze_duration
    for seg in payload.video_segments:
        p = plan_by_seg.get(seg.segment_id)
        if p and p.extend_seconds > 0:
            if p.decision == "footage_extend":
                current_end = clip_timestamp_to_seconds(seg.source_end)
                seg.source_end = seconds_to_clip_timestamp(current_end + p.extend_seconds)
            if p.freeze_duration:
                seg.freeze_frame_duration = p.freeze_duration

    # Build srt_by_index lookup
    srt_by_index = {item.index: item for item in payload.srt}

    # ── Per-segment SRT timing adjustment ──
    segments = sorted(payload.video_segments, key=lambda s: s.order)
    accum = 0.0  # cumulative delta from previous segments
    for seg in segments:
        p = plan_by_seg.get(seg.segment_id)
        if not p:
            accum += 0.0
            continue

        orig_dur = seg.duration_seconds
        extend = p.extend_seconds
        video_speed = p.video_speed_factor
        final_dur = p.required_duration
        delta = p.duration_delta_seconds

        first_cue = srt_by_index.get(seg.subtitle_start)
        if not first_cue:
            accum += delta
            continue

        # Compute scale for internal cue timing (compression/expansion)
        if p.decision == "sync_video_hard_trim":
            # Hard trim: total compression = required_duration / orig_dur
            # (video_speed alone is insufficient: e.g. speed=1.15 + trim from 10→4.75)
            internal_scale = final_dur / max(orig_dur, 0.001)
        elif video_speed != 1.0:
            internal_scale = 1.0 / video_speed
        else:
            internal_scale = 1.0
        seg_start_orig = srt_timestamp_to_seconds(first_cue.start)
        seg_start_final = seg_start_orig + accum

        for idx in range(seg.subtitle_start, seg.subtitle_end + 1):
            cue = srt_by_index.get(idx)
            if not cue:
                continue

            orig_start = srt_timestamp_to_seconds(cue.start)
            orig_end = srt_timestamp_to_seconds(cue.end)

            local_start = orig_start - seg_start_orig
            local_end = orig_end - seg_start_orig
            new_start = seg_start_final + local_start * internal_scale
            new_end = seg_start_final + local_end * internal_scale

            # For the last cue, add extend_seconds (scaled by video_speed)
            if idx == seg.subtitle_end and extend > 0:
                new_end = new_end + (extend / video_speed)

            new_start = max(0.0, new_start)
            new_end = max(new_start + 0.05, new_end)

            cue.start = seconds_to_srt_timestamp(new_start)
            cue.end = seconds_to_srt_timestamp(new_end)

        accum += delta


def validate_request_cookies_file(value: str | None) -> str | None:
    if not value:
        return None
    path = _resolve_path(value)
    if path.suffix.lower() != ".txt":
        raise ValueError("File cookies phải có đuôi .txt.")
    try:
        return str(_ensure_path_under(path, settings.temp_dir / "cookies", "File cookies"))
    except ValueError:
        return str(_ensure_path_under(path, settings.outputs_dir.parent / "data" / "cookies", "File cookies"))


def validate_request_local_video_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = _resolve_path(value)
    return _ensure_path_under(path, settings.local_videos_dir, "Video local")


class VideoDownloader:
    @staticmethod
    def _is_placeholder_url(url: str) -> bool:
        placeholder_patterns = ["...", "{VIDEO_ID}", "{video_id}", "<VIDEO_ID>", "<video_id>", "{%s}", "%7BVIDEO_ID%7D"]
        if any(p in url for p in placeholder_patterns):
            return True
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.netloc in {"youtu.be"}:
                path_id = parsed.path.strip("/")
                if path_id in {"", "...", "{VIDEO_ID}"}:
                    return True
                if path_id:
                    return False
            if parsed.netloc in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
                qs = urllib.parse.parse_qs(parsed.query)
                v = qs.get("v", [None])[0] or ""
                if v in {"", "...", "{VIDEO_ID}", "%7BVIDEO_ID%7D"}:
                    return True
        except Exception:
            pass
        return False

    def _base_command(self) -> list[str]:
        return [sys.executable, "-m", "yt_dlp"]

    def download(
        self,
        url: str,
        output_path: Path,
        cookies_file: str | None = None,
        cookies_from_browser: str | None = None,
        user_data_dir: str | None = None,
        cancel_callback: CancelCallback | None = None,
    ) -> Path:
        url = sanitize_url(url)
        if self._is_placeholder_url(url):
            raise ValueError(
                "URL YouTube không hợp lệ — chứa placeholder (..., {VIDEO_ID}). "
                "Hãy dùng URL YouTube thật, ví dụ: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            )
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.netloc in {"google.com", "www.google.com"}:
                raise ValueError(
                    "URL nguồn là Google Search/redirect, không phải link YouTube trực tiếp. "
                    "Hãy dùng URL youtube.com/watch hoặc youtu.be."
                )
        except ValueError:
            raise
        except Exception:
            pass
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            output_path.unlink()
        format_selector = "bestvideo[vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]/bestvideo[vcodec^=avc1]+bestaudio/best[ext=mp4]/best" if settings.ytdlp_prefer_h264 else "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"
        effective_cookies_file = cookies_file or settings.ytdlp_cookies_file
        effective_cookies_from_browser = cookies_from_browser or self._browser_cookie_source_from_profile(user_data_dir) or settings.ytdlp_cookies_from_browser
        auth_candidates: list[tuple[str, str | None]] = []
        cookie_file_has_strong_auth = False
        health: CookieHealth | None = None
        if effective_cookies_file:
            health = analyze_ytdlp_cookie_file(Path(effective_cookies_file))
            logger.info("Cookie file health: valid=%s total=%d youtube=%d auth=%d strong_auth=%s expired=%d",
                        health.valid, health.total_cookies, health.youtube_cookies, health.auth_cookies, health.has_strong_auth, health.expired_cookies)
            if health.warnings:
                for w in health.warnings:
                    logger.warning("Cookie warning: %s", w)
            if not health.valid:
                raise ValueError("File cookies không hợp lệ: " + "; ".join(health.errors))
            cookie_file_has_strong_auth = health.has_strong_auth
            if effective_cookies_from_browser and not cookie_file_has_strong_auth:
                # Weak cookies → try browser first (more likely up-to-date)
                auth_candidates.append(("cookies_from_browser", effective_cookies_from_browser))
                auth_candidates.append(("cookies_file", effective_cookies_file))
            else:
                auth_candidates.append(("cookies_file", effective_cookies_file))
                if effective_cookies_from_browser:
                    auth_candidates.append(("cookies_from_browser", effective_cookies_from_browser))
        elif effective_cookies_from_browser:
            auth_candidates.append(("cookies_from_browser", effective_cookies_from_browser))
        if not auth_candidates:
            auth_candidates.append(("none", None))
        self._write_ytdlp_preflight()
        last_detail = ""
        last_exc: subprocess.CalledProcessError | None = None
        attempted: list[str] = []
        for index, (auth_kind, auth_value) in enumerate(auth_candidates):
            cmd = self._build_download_command(url, output_path, format_selector, auth_kind, auth_value)
            attempted.append(f"{auth_kind}:{auth_value or ''}")
            self._write_ytdlp_command(cmd)
            try:
                self._run_ytdlp_command(cmd, cancel_callback=cancel_callback)
                return output_path
            except subprocess.CalledProcessError as exc:
                detail = self._format_process_error(exc, settings.logs_dir / "ytdlp_stdout.log", settings.logs_dir / "ytdlp_stderr.log")
                self._write_ytdlp_log(cmd, detail)
                logger.error("yt-dlp failed. Command: %s\n%s", " ".join(cmd), detail)
                last_detail = detail
                last_exc = exc
                if index == len(auth_candidates) - 1 or not self._is_auth_retryable_error(detail):
                    break
                logger.warning("yt-dlp auth failed with %s, retrying next auth candidate", auth_kind)
        if last_exc:
            detail_with_attempts = last_detail + "\n\nAUTH_ATTEMPTS:\n" + "\n".join(attempted)
            raise RuntimeError(self._friendly_error(detail_with_attempts, health)) from last_exc
        return output_path

    def _build_download_command(self, url: str, output_path: Path, format_selector: str, auth_kind: str, auth_value: str | None) -> list[str]:
        cmd = self._base_command() + [
            "--verbose",
            "--force-overwrites",
            "--no-continue",
            "--merge-output-format",
            "mp4",
            "--remux-video",
            "mp4",
            "-f",
            format_selector,
            "-o",
            str(output_path),
        ]
        if settings.ytdlp_js_runtimes:
            cmd.extend(["--js-runtimes", settings.ytdlp_js_runtimes])
        if settings.ytdlp_remote_components:
            cmd.extend(["--remote-components", settings.ytdlp_remote_components])
        if auth_kind == "cookies_file" and auth_value:
            cmd.extend(["--cookies", auth_value])
        elif auth_kind == "cookies_from_browser" and auth_value:
            cmd.extend(["--cookies-from-browser", auth_value])
        cmd.append(url)
        return cmd

    def _run_ytdlp_command(self, cmd: list[str], cancel_callback: CancelCallback | None = None) -> None:
        stdout_path = settings.logs_dir / "ytdlp_stdout.log"
        stderr_path = settings.logs_dir / "ytdlp_stderr.log"
        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        if cancel_callback:
            cancel_callback()
            with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
                proc = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, text=True, encoding="utf-8", errors="replace")
                while proc.poll() is None:
                    if cancel_callback:
                        cancel_callback()
                    time.sleep(2)
                if proc.returncode != 0:
                    raise subprocess.CalledProcessError(proc.returncode, cmd)
        else:
            with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
                subprocess.run(cmd, check=True, stdout=stdout, stderr=stderr, text=True, encoding="utf-8", errors="replace")

    def _browser_cookie_source_from_profile(self, user_data_dir: str | None) -> str | None:
        candidates = [user_data_dir, str(settings.gemini_profile_path) if settings.gemini_profile_path else None]
        for value in candidates:
            if not value:
                continue
            profile = Path(value)
            if not profile.is_dir():
                continue
            # Chromium standard: user_data_dir/Default/Network/Cookies
            if (profile / "Default" / "Network" / "Cookies").is_file():
                return f"chrome:{profile}"
            # Chromium named-profile: user_data_dir/Profile N/Network/Cookies
            for child in profile.iterdir():
                if child.is_dir() and child.name.startswith("Profile "):
                    if (child / "Network" / "Cookies").is_file():
                        return f"chrome:{profile}"
                    break  # one scan enough, found a profile dir
            # Direct profile dir: {profile}/Network/Cookies or legacy {profile}/Cookies
            if (profile / "Network" / "Cookies").is_file() or (profile / "Cookies").is_file():
                return f"chrome:{profile}"
        return None

    def _is_auth_retryable_error(self, detail: str) -> bool:
        markers = ["HTTP Error 403", "403 Forbidden", "Sign in to confirm", "not a bot", "cookies", "cookie", "LOGIN_REQUIRED"]
        return any(marker.lower() in detail.lower() for marker in markers)

    def _write_ytdlp_command(self, cmd: list[str]) -> None:
        try:
            settings.logs_dir.mkdir(parents=True, exist_ok=True)
            (settings.logs_dir / "ytdlp_last_command.txt").write_text(" ".join(cmd) + "\n", encoding="utf-8")
        except Exception:
            logger.exception("Không ghi được ytdlp_last_command.txt")

    def _write_ytdlp_preflight(self) -> None:
        try:
            settings.logs_dir.mkdir(parents=True, exist_ok=True)
            lines = []
            node = shutil.which("node")
            checks = []
            if node:
                checks.append([node, "--version"])
            else:
                lines.append("node=not_found_in_PATH")
            checks.append([sys.executable, "-m", "yt_dlp", "--js-runtimes", settings.ytdlp_js_runtimes or "node", "--remote-components", settings.ytdlp_remote_components or "ejs:github", "--version"])
            checks.append([settings.ytdlp_binary, "--js-runtimes", settings.ytdlp_js_runtimes or "node", "--remote-components", settings.ytdlp_remote_components or "ejs:github", "--version"])
            for command in checks:
                try:
                    result = subprocess.run(command, capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace")
                    lines.append(f"$ {' '.join(command)}")
                    lines.append(f"exit={result.returncode}")
                    lines.append("STDOUT")
                    lines.append(result.stdout.strip())
                    lines.append("STDERR")
                    lines.append(result.stderr.strip())
                    lines.append("")
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"$ {' '.join(command)}")
                    lines.append(f"ERROR: {exc}")
            (settings.logs_dir / "ytdlp_preflight.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            logger.exception("Không ghi được ytdlp_preflight.log")

    def _write_ytdlp_log(self, cmd: list[str], detail: str) -> None:
        try:
            settings.logs_dir.mkdir(parents=True, exist_ok=True)
            path = settings.logs_dir / "ytdlp.log"
            with path.open("a", encoding="utf-8") as handle:
                handle.write("\n=== yt-dlp failure ===\n")
                handle.write("COMMAND:\n" + " ".join(cmd) + "\n\n")
                handle.write(detail + "\n")
        except Exception:
            logger.exception("Không ghi được ytdlp.log")

    def _format_process_error(self, exc: subprocess.CalledProcessError, stdout_path: Path | None = None, stderr_path: Path | None = None) -> str:
        parts = [f"returncode={exc.returncode}"]
        if exc.stderr:
            parts.append("STDERR:\n" + exc.stderr.strip())
        if exc.stdout:
            parts.append("STDOUT:\n" + exc.stdout.strip())
        if stderr_path and stderr_path.exists():
            stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace").strip()
            if stderr_text:
                parts.append("STDERR_FILE:\n" + stderr_text[-12000:])
        if stdout_path and stdout_path.exists():
            stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace").strip()
            if stdout_text:
                parts.append("STDOUT_FILE:\n" + stdout_text[-12000:])
        if len(parts) == 1:
            parts.append(str(exc))
        return "\n\n".join(parts)

    def _friendly_error(self, detail: str, health: CookieHealth | None = None) -> str:
        detail_stripped = ui_safe_error(detail)
        had_cookies = "--cookies" in detail or "cookies.txt" in detail or "COOKIES_FILE" in detail
        had_browser_profile = "cookies_from_browser" in detail or "--cookies-from-browser" in detail or "chrome:" in detail
        if "HTTP Error 403" in detail or "403 Forbidden" in detail:
            base = (
                "YouTube chặn tải video vì thiếu cookies đăng nhập (HTTP 403). "
                "Hãy cấu hình YTDLP_COOKIES_FILE hoặc YTDLP_COOKIES_FROM_BROWSER=chrome/edge."
            )
            if had_cookies:
                base = (
                    "YouTube trả về HTTP 403 dù đã nạp cookie. "
                    "Cookie có thể đã hết hạn hoặc bị YouTube thu hồi. "
                    "Hãy export cookies mới từ trình duyệt đã đăng nhập YouTube, hoặc thử YTDLP_COOKIES_FROM_BROWSER=chrome/edge."
                )
            if had_browser_profile:
                base += " Tool đã thử dùng Chrome/Gemini profile hiện tại nếu profile có cookies."
            return base + " Chi tiết kỹ thuật: " + detail_stripped
        if "Sign in to confirm" in detail or "not a bot" in detail or "--cookies-from-browser" in detail:
            base = (
                "yt-dlp bị YouTube chặn vì cần xác minh đăng nhập/không phải bot. "
                "Hãy cấu hình YTDLP_COOKIES_FILE hoặc YTDLP_COOKIES_FROM_BROWSER=chrome/edge."
            )
            if had_cookies:
                base = (
                    "YouTube chặn yt-dlp dù đã nạp file cookie. "
                    "Cookie hiện tại có thể đã hết hạn hoặc YouTube cần re-verify. "
                    "Hãy export lại cookies mới từ trình duyệt đã đăng nhập YouTube, hoặc dùng YTDLP_COOKIES_FROM_BROWSER=chrome/edge."
                )
                if health is not None and not health.has_strong_auth:
                    base += " Cookie file hiện tại thiếu cookie đăng nhập mạnh (SAPISID/APISID/LOGIN_INFO) — export cookies từ tab youtube.com đang đăng nhập để có đủ auth token."
            if had_browser_profile:
                base += " Tool đã thử dùng Chrome/Gemini profile hiện tại nếu profile có cookies."
            if "older than" in detail:
                base += " Phiên bản yt-dlp đã cũ, có thể bị YouTube chặn. Hãy update yt-dlp."
            if "PO Token Providers: none" in detail:
                base += " yt-dlp chưa có PO token provider; nếu vẫn bị chặn sau khi refresh cookies, cần cấu hình PO token."
            return base + " Chi tiết kỹ thuật: " + detail_stripped
        if "No supported JavaScript runtime" in detail:
            return (
                "yt-dlp thiếu JavaScript runtime. "
                "Hãy cài Node.js/Deno và cấu hình YTDLP_JS_RUNTIMES=node/deno. "
                "Chi tiết kỹ thuật: " + detail_stripped
            )
        if "Remote component challenge solver" in detail or "n challenge solving failed" in detail:
            return (
                "yt-dlp cần challenge solver. "
                "Hãy cấu hình YTDLP_REMOTE_COMPONENTS=ejs:github và restart backend. "
                "Chi tiết kỹ thuật: " + detail_stripped
            )
        return "yt-dlp tải video thất bại. " + detail_stripped


class VideoCutter:
    def cut(self, source_paths: dict[str, Path], payload: GeminiPayloadSchema, clips_dir: Path, reencode_segments: bool = False, progress_callback: ProgressCallback | None = None, render_options: RenderOptions | None = None, cancel_callback: CancelCallback | None = None, segment_plans: list[SegmentPlanItem] | None = None) -> list[Path]:
        options = render_options or RenderOptions()
        quality = quality_for_stability(options)
        segment_fps = segment_fps_value(options)
        clips_dir.mkdir(parents=True, exist_ok=True)
        plan_by_seg = {p.segment_id: p for p in (segment_plans or [])}
        ordered_segments = sorted(payload.video_segments, key=lambda item: item.order)
        total_segments = len(ordered_segments)

        selected_encoder = select_video_encoder(options.video_encoder)
        max_workers, ffmpeg_threads = calculate_segment_parallelism(selected_encoder, total_segments)
        thread_args = ffmpeg_thread_args(ffmpeg_threads)

        def _cut_one(index: int, segment: object) -> Path:
            output = clips_dir / f"segment_{segment.segment_id}.mp4"
            source_id = segment.source_id or "source_1"
            source_path = source_paths.get(source_id)
            if source_path is None:
                raise RuntimeError(f"Không tìm thấy video nguồn cho source_id={source_id}.")
            duration = clip_timestamp_to_seconds(segment.source_end) - clip_timestamp_to_seconds(segment.source_start)
            if duration <= 0:
                raise RuntimeError(f"Segment #{segment.segment_id} có duration không hợp lệ.")

            p = plan_by_seg.get(segment.segment_id)
            video_speed = p.video_speed_factor if p else 1.0

            if p and p.decision == "sync_video_hard_trim":
                trim_input = p.required_duration * p.video_speed_factor
                duration = min(duration, trim_input)

            freeze_dur = segment.freeze_frame_duration or 0.0
            vf_parts = [f"fps={segment_fps}", "setsar=1"]
            if video_speed != 1.0:
                vf_parts.insert(0, f"setpts=PTS-STARTPTS/{video_speed:.6f}")
            else:
                vf_parts.insert(0, "setpts=PTS-STARTPTS")
            if freeze_dur > 0:
                vf_parts.insert(0, f"tpad=stop_mode=clone:stop_duration={freeze_dur:.3f}")

            def build_cmd(profile: EncoderProfile) -> list[str]:
                cmd = [
                    settings.ffmpeg_binary,
                    "-y",
                    "-ss",
                    segment.source_start,
                ]
                if freeze_dur > 0:
                    cmd.extend(["-t", f"{duration:.3f}"])
                cmd.extend(["-i", str(source_path)])
                if freeze_dur <= 0:
                    cmd.extend(["-t", f"{duration:.3f}"])
                af_parts = []
                if video_speed != 1.0:
                    af_parts.append(f"atempo={video_speed:.6f}")
                af_parts.append("aresample=async=1:first_pts=0")
                return [
                    *cmd,
                    "-map", "0:v:0",
                    "-map", "0:a?",
                    "-vf", ",".join(vf_parts),
                    "-af", ",".join(af_parts),
                    *thread_args,
                    *video_encoder_args(profile, quality),
                    *audio_encoder_args(quality),
                    str(output),
                ]

            per_seg_callback = None if max_workers > 1 else progress_callback
            run_ffmpeg_with_encoder_fallback(
                build_cmd,
                f"FFmpeg cắt segment #{segment.segment_id} thất bại",
                mode_override=options.video_encoder,
                progress_callback=per_seg_callback,
                duration_seconds=duration,
                progress_start=0,
                progress_end=0,
                cancel_callback=cancel_callback,
            )
            return output

        if max_workers <= 1:
            results: list[Path] = []
            for index, segment in enumerate(ordered_segments, start=1):
                if progress_callback:
                    progress_callback({
                        "step": "Cut segments",
                        "message": f"Đang cắt segment {index}/{total_segments}...",
                        "progress": 30 + int(((index - 1) / max(total_segments, 1)) * 40),
                        "total_segments": total_segments,
                        "completed_segments": index - 1,
                        "phase": "cut_segments",
                        "phase_progress": (index - 1) / max(total_segments, 1),
                    })
                output = _cut_one(index, segment)
                results.append(output)
                if progress_callback:
                    progress_callback({
                        "step": "Cut segments",
                        "message": f"Đã cắt xong segment {index}/{total_segments}.",
                        "progress": 30 + int((index / max(total_segments, 1)) * 40),
                        "total_segments": total_segments,
                        "completed_segments": index,
                        "phase": "cut_segments",
                        "phase_progress": index / max(total_segments, 1),
                    })
            return results

        parallel_results: list[Path | None] = [None] * total_segments
        completed = 0

        if cancel_callback:
            cancel_callback()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_cut_one, index, segment): index
                for index, segment in enumerate(ordered_segments, start=1)
            }

            for future in as_completed(future_map):
                index = future_map[future]
                try:
                    output = future.result()
                except Exception as exc:
                    for f in future_map:
                        f.cancel()
                    raise RuntimeError(f"Cắt segment #{index} thất bại: {exc}") from exc

                parallel_results[index - 1] = output
                completed += 1
                if progress_callback:
                    progress_callback({
                        "step": "Cut segments",
                        "message": f"Đang cắt segment {completed}/{total_segments}...",
                        "progress": 30 + int((completed / max(total_segments, 1)) * 40),
                        "total_segments": total_segments,
                        "completed_segments": completed,
                        "phase": "cut_segments",
                        "phase_progress": completed / max(total_segments, 1),
                    })

        for i, path in enumerate(parallel_results):
            if path is None:
                raise RuntimeError(f"Parallel cut failed: segment #{i + 1} was not completed.")
        return [path for path in parallel_results if path is not None]


def normalize_render_sources(payload: GeminiPayloadSchema, youtube_url: str | None, local_video_path: str | None) -> list[SourceSchema]:
    if payload.sources:
        for segment in payload.video_segments:
            if not segment.source_id:
                raise ValueError(f"Segment #{segment.segment_id} thiếu source_id khi JSON có sources[].")
        for source in payload.sources:
            if source.youtube_url:
                source.youtube_url = sanitize_url(source.youtube_url)
        return payload.sources
    fallback = SourceSchema(source_id="source_1", youtube_url=sanitize_url(youtube_url) if youtube_url else None, local_video_path=local_video_path, label="Video nguồn chính")
    payload.sources = [fallback]
    for segment in payload.video_segments:
        segment.source_id = "source_1"
    return payload.sources


class VideoConcatenator:
    def concatenate(self, payload: GeminiPayloadSchema, clips_dir: Path, output_path: Path) -> Path:
        manifest = clips_dir / "concat.txt"
        ordered = sorted(payload.video_segments, key=lambda item: item.order)
        lines = [f"file 'segment_{item.segment_id}.mp4'" for item in ordered]
        manifest.write_text("\n".join(lines), encoding="utf-8")
        absolute_output = output_path.resolve()
        cmd = [settings.ffmpeg_binary, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest.name), "-c", "copy", str(absolute_output)]
        subprocess.run(cmd, check=True, cwd=str(clips_dir), capture_output=True, text=True, encoding="utf-8", errors="replace")
        rough = absolute_output
        rough_fast = output_path.parent / f"{output_path.stem}_faststart.mp4"
        subprocess.run(
            [settings.ffmpeg_binary, "-y", "-i", str(rough),
             "-c", "copy", "-movflags", "+faststart",
             str(rough_fast)],
            check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        rough.unlink()
        rough_fast.rename(rough)
        return absolute_output


class SubtitleBurner:
    def burn(self, video_path: Path, srt_path: Path, output_path: Path, render_options: RenderOptions | None = None, progress_callback: ProgressCallback | None = None, progress_start: int = 94, progress_end: int = 98, cancel_callback: CancelCallback | None = None) -> Path:
        options = render_options or RenderOptions()
        quality = quality_for_stability(options)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ass_path = output_path.parent / f"{output_path.stem}_styled.ass"
        from app.services.subtitle_styler import SubtitleStyler
        SubtitleStyler().srt_to_ass(srt_path, ass_path, options)
        relative_ass = ass_path.name

        def build_cmd(profile: EncoderProfile) -> list[str]:
            return [
                settings.ffmpeg_binary,
                "-y",
                "-i",
                str(video_path.resolve()),
                "-vf",
                f"subtitles={relative_ass}",
                *video_encoder_args(profile, quality),
                *audio_encoder_args(quality),
                "-r", "30",
                "-movflags",
                "+faststart",
                str(output_path.resolve()),
            ]

        duration = float(probe_video_metadata(video_path).get("duration_seconds") or 0)
        run_ffmpeg_with_encoder_fallback(build_cmd, "FFmpeg burn subtitle thất bại", cwd=str(ass_path.parent), mode_override=options.video_encoder, progress_callback=progress_callback, duration_seconds=duration, progress_start=progress_start, progress_end=progress_end, cancel_callback=cancel_callback)
        return output_path


class OutputTransformer:
    def needs_transform(self, options: RenderOptions) -> bool:
        return options.vertical_mode != "none" or options.output_resolution != "auto" or options.render_quality != "balanced"

    def transform(self, input_path: Path, output_path: Path, options: RenderOptions, progress_callback: ProgressCallback | None = None, progress_start: int = 88, progress_end: int = 94, cancel_callback: CancelCallback | None = None) -> Path:
        quality = quality_for_stability(options)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        def build_cmd(profile: EncoderProfile) -> list[str]:
            cmd = [settings.ffmpeg_binary, "-y", "-i", str(input_path.resolve())]
            if options.vertical_mode == "blur_fit":
                cmd.extend([
                    "-filter_complex",
                    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=10:1[bg];[0:v]scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30[v]",
                    "-map",
                    "[v]",
                    "-map",
                    "0:a?",
                ])
            else:
                filter_value = self._build_simple_filter(options)
                if filter_value:
                    cmd.extend(["-vf", filter_value])
            cmd.extend(video_encoder_args(profile, quality))
            cmd.extend(audio_encoder_args(quality))
            cmd.extend(["-r", "30", "-movflags", "+faststart", str(output_path.resolve())])
            return cmd

        duration = float(probe_video_metadata(input_path).get("duration_seconds") or 0)
        run_ffmpeg_with_encoder_fallback(build_cmd, "FFmpeg chuyển đổi output thất bại", mode_override=options.video_encoder, progress_callback=progress_callback, duration_seconds=duration, progress_start=progress_start, progress_end=progress_end, cancel_callback=cancel_callback)
        return output_path

    def transform_and_burn(self, input_path: Path, srt_path: Path, output_path: Path, options: RenderOptions, progress_callback: ProgressCallback | None = None, progress_start: int = 88, progress_end: int = 98, cancel_callback: CancelCallback | None = None) -> Path:
        quality = quality_for_stability(options)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ass_path = output_path.parent / f"{output_path.stem}_styled.ass"
        from app.services.subtitle_styler import SubtitleStyler
        SubtitleStyler().srt_to_ass(srt_path, ass_path, options)
        relative_ass = ass_path.name

        def build_cmd(profile: EncoderProfile) -> list[str]:
            cmd = [settings.ffmpeg_binary, "-y", "-i", str(input_path.resolve())]
            if options.vertical_mode == "blur_fit":
                cmd.extend([
                    "-filter_complex",
                    f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=10:1[bg];[0:v]scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[base];[base]subtitles={relative_ass},fps=30[v]",
                    "-map",
                    "[v]",
                    "-map",
                    "0:a?",
                ])
            else:
                base_filter = self._build_simple_filter(options)
                subtitle_filter = f"subtitles={relative_ass}"
                cmd.extend(["-vf", f"{base_filter},{subtitle_filter}" if base_filter else subtitle_filter])
            cmd.extend(video_encoder_args(profile, quality))
            cmd.extend(audio_encoder_args(quality))
            cmd.extend(["-r", "30", "-movflags", "+faststart", str(output_path.resolve())])
            return cmd

        duration = float(probe_video_metadata(input_path).get("duration_seconds") or 0)
        run_ffmpeg_with_encoder_fallback(build_cmd, "FFmpeg transform + burn subtitle thất bại", cwd=str(ass_path.parent), mode_override=options.video_encoder, progress_callback=progress_callback, duration_seconds=duration, progress_start=progress_start, progress_end=progress_end, cancel_callback=cancel_callback)
        return output_path

    def _build_simple_filter(self, options: RenderOptions) -> str | None:
        if options.vertical_mode == "center_crop":
            return "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        if options.output_resolution == "720p":
            return "scale=-2:720"
        if options.output_resolution == "1080p":
            return "scale=-2:1080"
        return None


class TitleOverlay:
    def enabled(self, options: RenderOptions) -> bool:
        return options.title_mode != "none"

    def resolve_title(self, payload: GeminiPayloadSchema, options: RenderOptions) -> str:
        raw = options.title_text if options.title_mode == "custom" else payload.metadata.video_title
        return _wrap_title(raw, options.title_max_lines, options.title_chars_per_line)

    def resolve_badge(self, payload: GeminiPayloadSchema, options: RenderOptions) -> str:
        if options.title_badge_mode == "none":
            return ""
        if options.title_badge_mode == "custom":
            return options.title_badge_text.strip().upper()[:32]
        haystack = " ".join([
            payload.metadata.video_title,
            payload.metadata.rewrite_style,
            payload.metadata.tone,
            payload.metadata.narrator_persona,
        ]).lower()
        if any(token in haystack for token in ["bodycam", "police", "cops", "cop", "officer"]):
            return "BODYCAM"
        if any(token in haystack for token in ["case", "crime", "documentary", "detective"]):
            return "CASE FILE"
        return "TRUE CRIME"

    def _title_enable_expr(self, options: RenderOptions) -> str:
        if options.title_show_duration == "intro_only":
            return f":enable='between(t\\,0\\,{options.title_intro_seconds:.2f})'"
        return ""

    def apply(self, input_path: Path, output_path: Path, payload: GeminiPayloadSchema, options: RenderOptions, progress_callback: ProgressCallback | None = None, progress_start: int = 93, progress_end: int = 94, cancel_callback: CancelCallback | None = None) -> Path:
        metadata = {
            "video_title": payload.metadata.video_title,
            "rewrite_style": payload.metadata.rewrite_style,
            "tone": payload.metadata.tone,
            "narrator_persona": payload.metadata.narrator_persona,
        }
        meta = probe_video_metadata(input_path)
        res = meta.get("resolution", "")
        if res and "x" in res:
            parts = res.split("x")
            video_width = int(parts[0])
            video_height = int(parts[1])
        else:
            video_width, video_height = 1920, 1080

        layout = compute_title_layout(options, video_width, video_height, metadata)
        if not layout.lines:
            shutil.copy2(input_path, output_path)
            return output_path

        quality = quality_for_stability(options)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        title_text = "\n".join(line.text for line in layout.lines)
        title_file = output_path.parent / f"{output_path.stem}_title.txt"
        title_file.write_text(title_text, encoding="utf-8")
        badge_file = output_path.parent / f"{output_path.stem}_badge.txt"
        if layout.badge:
            badge_file.write_text(layout.badge.text, encoding="utf-8")

        font_probe_text = title_text
        if layout.badge:
            font_probe_text = f"{font_probe_text}\n{layout.badge.text}"
        font_path = _title_font_path(font_probe_text)
        font_part = f":fontfile='{_ffmpeg_filter_path(font_path)}'" if font_path else ""
        enable_part = self._title_enable_expr(options)
        shadow_part = ":shadowcolor=black@0.8:shadowx=2:shadowy=2"
        filters: list[str] = []

        if layout.header_drawbox:
            filters.extend(layout.header_drawbox)

        if layout.badge:
            badge_font_size = max(24, layout.badge.font_size - 18)
            filters.append(
                f"drawtext=textfile='{badge_file.name}'{font_part}:x={layout.badge.x_expr}:y={layout.badge.y_expr}:fontsize={badge_font_size}:"
                f"fontcolor={layout.badge.font_color}:box=1:boxcolor=0xB91C1C@0.95:boxborderw=12:shadowcolor=black@0.85:shadowx=1:shadowy=1{enable_part}"
            )

        for i, line in enumerate(layout.lines):
            line_file = output_path.parent / f"{output_path.stem}_title_{i}.txt"
            line_file.write_text(line.text, encoding="utf-8")
            box_part = f"box=1:boxcolor={line.background_color}" if line.has_background and line.background_color else "box=0"
            filters.append(
                f"drawtext=textfile='{line_file.name}'{font_part}:"
                f"x={line.x_expr}:y={line.y_expr}:fontsize={line.font_size}:fontcolor={line.font_color}:"
                f"{box_part}{shadow_part}{enable_part}"
            )

        duration = float(probe_video_metadata(input_path).get("duration_seconds") or 0)
        if duration <= 0:
            shutil.copy2(input_path, output_path)
            return output_path

        def build_cmd(profile: EncoderProfile) -> list[str]:
            return [
                settings.ffmpeg_binary,
                "-y",
                "-i",
                str(input_path.resolve()),
                "-vf",
                ",".join(filters),
                *video_encoder_args(profile, quality),
                *audio_encoder_args(quality),
                "-r", "30",
                "-movflags",
                "+faststart",
                str(output_path.resolve()),
            ]

        run_ffmpeg_with_encoder_fallback(build_cmd, "FFmpeg chèn title thất bại", cwd=str(title_file.parent), mode_override=options.video_encoder, progress_callback=progress_callback, duration_seconds=duration, progress_start=progress_start, progress_end=progress_end, cancel_callback=cancel_callback)
        return output_path


class RenderPipeline:
    def __init__(self, downloader: VideoDownloader, cutter: VideoCutter, concatenator: VideoConcatenator, subtitle_burner: SubtitleBurner, output_transformer: OutputTransformer | None = None, title_overlay: TitleOverlay | None = None):
        self.downloader = downloader
        self.cutter = cutter
        self.concatenator = concatenator
        self.subtitle_burner = subtitle_burner
        self.output_transformer = output_transformer or OutputTransformer()
        self.title_overlay = title_overlay or TitleOverlay()

    def render(
        self,
        payload: GeminiPayloadSchema,
        youtube_url: str | None,
        local_video_path: str | None,
        burn_subtitle: bool,
        subtitle_mode: str | None = None,
        job_id: str | None = None,
        ytdlp_cookies_file: str | None = None,
        ytdlp_cookies_from_browser: str | None = None,
        user_data_dir: str | None = None,
        render_options: RenderOptions | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: CancelCallback | None = None,
        output_dir_name: str | None = None,
        output_dir_path: str | None = None,
    ) -> dict[str, str]:
        options = render_options or RenderOptions()
        effective_subtitle_mode = subtitle_mode or ("burn" if burn_subtitle else "none")
        render_started_at = time.perf_counter()
        timings: list[dict] = []
        encoder_events: list[dict] = []

        def mark_timing(name: str, started_at: float, extra: dict | None = None) -> None:
            timings.append({"name": name, "duration_seconds": round(time.perf_counter() - started_at, 3), "extra": extra or {}})

        def timing_payload() -> dict:
            total = round(time.perf_counter() - render_started_at, 3)
            slowest = sorted(timings, key=lambda item: item.get("duration_seconds", 0), reverse=True)[:5]
            return {"total_seconds": total, "steps": timings, "slowest_steps": slowest}

        def record_encoder_step(step: str, requested: EncoderProfile, used: EncoderProfile) -> None:
            encoder_events.append({
                "step": step,
                "requested": requested.name,
                "used": used.name,
                "codec": used.codec,
                "hardware": used.hardware,
                "fallback_used": requested.hardware and used.name != requested.name,
                "fallback_from": requested.codec if requested.hardware and used.name != requested.name else "",
            })

        selected_encoder = select_video_encoder(options.video_encoder)
        fallback_title = Path(local_video_path).stem if local_video_path else "youtube_video"
        prefix = safe_filename_prefix(payload.metadata.video_title, fallback=fallback_title)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        custom_path = safe_output_dir_path(output_dir_path)
        safe_folder = safe_output_dir_name(output_dir_name)
        if custom_path:
            output_dir = custom_path
        elif safe_folder:
            output_dir = settings.outputs_dir / safe_folder
        else:
            output_dir = settings.outputs_dir / f"{prefix}_{timestamp}"
        workspace_name = safe_filename_prefix(job_id, fallback=f"render_{timestamp}")
        workspace_dir = settings.temp_dir / workspace_name

        source = workspace_dir / "source.mp4"
        step_started = time.perf_counter()
        settings.temp_dir.mkdir(parents=True, exist_ok=True)
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        mark_timing("prepare_workspace", step_started)

        stem = final_video_stem(payload, options)
        if safe_folder:
            subtitle_path = _unique_path(output_dir / f"{stem}.srt")
            render_plan = _unique_path(output_dir / f"{stem}_plan.json")
        else:
            subtitle_path = output_dir / f"{prefix}_subtitle.srt"
            render_plan = output_dir / f"{prefix}_render_plan.json"

        if effective_subtitle_mode == "srt_only":
            from app.services.subtitle_generator import SubtitleGenerator

            if progress_callback:
                progress_callback({"step": "Generate subtitle", "message": "Đang tạo file phụ đề SRT...", "progress": 82, "phase": "generate_subtitle", "phase_progress": 0.1})
            SubtitleGenerator().generate(payload, subtitle_path)
            if progress_callback:
                progress_callback({"step": "Export result", "message": "Đang ghi render plan và hoàn tất output SRT...", "progress": 98, "phase": "export", "phase_progress": 0.5})
            render_plan_payload = payload.model_dump()
            render_plan_payload["render_options"] = options.model_dump()
            render_plan_payload["burn_subtitle"] = False
            render_plan_payload["subtitle_mode"] = effective_subtitle_mode
            render_plan_payload["source_files"] = {}
            render_plan_payload["video_encoder"] = {"mode": options.video_encoder, "selected": selected_encoder.name, "codec": selected_encoder.codec, "label": selected_encoder.label, "hardware": selected_encoder.hardware}
            render_plan_payload["diagnostics"] = {"timing": timing_payload(), "encoder": {"requested": options.video_encoder, "selected": selected_encoder.name, "codec": selected_encoder.codec, "label": selected_encoder.label, "hardware": selected_encoder.hardware, "events": encoder_events}, "parallelism": render_parallelism_diagnostics(selected_encoder, options, len(payload.video_segments))}
            render_plan.write_text(json.dumps(render_plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return {
                "final_video_path": "",
                "final_subtitle_path": str(subtitle_path),
                "render_plan_path": str(render_plan),
                "output_dir": str(output_dir),
                "source_path": "",
                "workspace_dir": str(workspace_dir),
                "deleted_raw_video_path": "",
                "source_count": "0",
                "vertical_mode": options.vertical_mode,
                "render_quality": options.render_quality,
                "output_resolution": options.output_resolution,
                "burn_subtitle": "False",
                "subtitle_mode": effective_subtitle_mode,
                "video_encoder": selected_encoder.name,
                "video_encoder_label": selected_encoder.label,
                "video_encoder_codec": selected_encoder.codec,
            }

        if progress_callback:
            progress_callback({"step": "Prepare workspace", "message": "Đang chuẩn bị thư mục render...", "progress": 12, "phase": "prepare_sources", "phase_progress": 0.3})

        request_cookies_file = validate_request_cookies_file(ytdlp_cookies_file)
        sources = normalize_render_sources(payload, youtube_url, local_video_path)
        sources_dir = workspace_dir / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)
        source_paths: dict[str, Path] = {}
        step_started = time.perf_counter()
        for index, source_item in enumerate(sources, start=1):
            source_output = source if len(sources) == 1 else sources_dir / f"{safe_filename_prefix(source_item.source_id)}.mp4"
            if source_item.youtube_url:
                source_item.youtube_url = sanitize_url(source_item.youtube_url)
                if progress_callback:
                    progress_callback({"step": "Download sources", "message": f"Đang tải nguồn {index}/{len(sources)} ({source_item.source_id})...", "progress": 15 + int(((index - 1) / max(len(sources), 1)) * 15), "phase": "download_sources", "phase_progress": (index - 1) / max(len(sources), 1)})
                cached_source = source_cache_path(source_item.youtube_url)
                if cached_source.exists():
                    if progress_callback:
                        progress_callback({"step": "Reuse cached source", "message": f"Đang dùng lại source cache {index}/{len(sources)} ({source_item.source_id})...", "progress": 15 + int(((index - 1) / max(len(sources), 1)) * 15), "phase": "download_sources", "phase_progress": (index - 1) / max(len(sources), 1)})
                    shutil.copy2(cached_source, source_output)
                else:
                    self.downloader.download(source_item.youtube_url, source_output, cookies_file=request_cookies_file, cookies_from_browser=ytdlp_cookies_from_browser, user_data_dir=user_data_dir, cancel_callback=cancel_callback)
                    cached_source.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_output, cached_source)
            elif source_item.local_video_path:
                if progress_callback:
                    progress_callback({"step": "Copy sources", "message": f"Đang copy nguồn {index}/{len(sources)} ({source_item.source_id})...", "progress": 15 + int(((index - 1) / max(len(sources), 1)) * 15), "phase": "download_sources", "phase_progress": (index - 1) / max(len(sources), 1)})
                request_local_source = validate_request_local_video_path(source_item.local_video_path)
                if source_output.exists():
                    source_output.unlink()
                shutil.copy2(request_local_source, source_output)
            else:
                raise ValueError(f"Source {source_item.source_id} thiếu youtube_url hoặc local_video_path.")
            source_paths[source_item.source_id] = source_output
        mark_timing("download_sources", step_started, {"source_count": len(sources)})
        if progress_callback:
            progress_callback({"step": "Prepare sources", "message": "Đã chuẩn bị xong tất cả video nguồn.", "progress": 30, "phase": "download_sources", "phase_progress": 1.0})

        # ── TTS pre-processing: generate natural TTS, SegmentPlanner, update payload ──
        tts_segment_plans: list[SegmentPlanItem] = []
        segment_speeds: dict[int | None, float] = {}
        srt_shifts: dict[int, float] = {}
        if options.tts_mode == "voiceover":
            from app.services.tts_tools import TtsVoiceoverService
            from app.services.segment_planner import SegmentPlanner

            if progress_callback:
                progress_callback({"step": "Generate TTS", "message": "Đang tạo TTS tự nhiên (không speed)...", "progress": 30, "phase": "tts_natural", "phase_progress": 0.0})
            step_started = time.perf_counter()
            natural_durations, _ = TtsVoiceoverService().generate_natural_tts(
                payload, output_dir, workspace_dir, options,
                progress_callback=progress_callback, cancel_callback=cancel_callback,
            )
            mark_timing("tts_generate_natural", step_started, {"cue_count": len(payload.srt)})

            step_started = time.perf_counter()
            source_durations: dict[str, float] = {}
            for sid, spath in source_paths.items():
                meta = probe_video_metadata(spath)
                source_durations[sid] = float(meta.get("duration_seconds") or 0.0)

            planner = SegmentPlanner()
            tts_segment_plans = planner.plan(payload, options, natural_durations, source_durations)
            srt_shifts = planner.compute_srt_shifts(tts_segment_plans, payload)
            segment_speeds = {p.segment_id: p.speed_factor for p in tts_segment_plans}

            _apply_segment_plan_to_payload(payload, tts_segment_plans, srt_shifts)

            # ── TTS timeline reconciliation ──
            if progress_callback:
                progress_callback({"step": "TTS reconcile", "message": "Đang cân chỉnh timeline voiceover...", "progress": 31, "phase": "tts_reconcile", "phase_progress": 0.0})
            tts_service = TtsVoiceoverService()
            reconcile_plans, _, _ = tts_service.prepare_voiceover_plans(
                payload, output_dir, workspace_dir, options,
                segment_speeds=segment_speeds,
                progress_callback=progress_callback, cancel_callback=cancel_callback,
            )
            tts_service.reconcile_payload_tts_timeline(payload, reconcile_plans, output_dir)
            mark_timing("segment_plan", step_started, {"segment_count": len(tts_segment_plans)})

        clips_dir = workspace_dir / "segments"
        if cancel_callback:
            cancel_callback()
        step_started = time.perf_counter()
        self.cutter.cut(source_paths, payload, clips_dir, reencode_segments=True, progress_callback=progress_callback, render_options=options, cancel_callback=cancel_callback, segment_plans=tts_segment_plans if tts_segment_plans else None)
        mark_timing("cut_segments", step_started, {"segment_count": len(payload.video_segments)})
        record_encoder_step("cut_segments", selected_encoder, selected_encoder)
        rough_video = output_dir / f"{prefix}_raw.mp4"
        if progress_callback:
            progress_callback({"step": "Concatenate", "message": "Đang ghép các segment thành video thô...", "progress": 72, "phase": "concat", "phase_progress": 0.2})
        step_started = time.perf_counter()
        self.concatenator.concatenate(payload, clips_dir, rough_video)
        mark_timing("concat_segments", step_started)

        # ── Extend video with freeze-frame padding for TTS overrun ──
        if options.tts_mode == "voiceover" and tts_segment_plans:
            total_overrun = max(0.0, sum(p.overrun_seconds for p in tts_segment_plans))
            if total_overrun > 0.5:
                step_started = time.perf_counter()
                dur = float(probe_video_metadata(rough_video).get("duration_seconds") or 0)
                if dur > 1.0:
                    extended = output_dir / f"{prefix}_raw_extended.mp4"
                    vf = f"tpad=stop_mode=clone:stop_duration={total_overrun:.3f}"
                    def build_extend_cmd(profile: EncoderProfile) -> list[str]:
                        return [
                            settings.ffmpeg_binary, "-y", "-i", str(rough_video),
                            "-map", "0:v:0",
                            "-map", "0:a?",
                            "-vf", vf,
                            "-af", f"apad=pad_dur={total_overrun:.3f}",
                            *video_encoder_args(profile, options.render_quality),
                            "-c:a", "aac", "-b:a", "192k",
                            "-movflags", "+faststart",
                            str(extended),
                        ]
                    used_encoder = run_ffmpeg_with_encoder_fallback(build_extend_cmd, "FFmpeg TTS overrun extension thất bại", mode_override=options.video_encoder, duration_seconds=dur + total_overrun, cancel_callback=cancel_callback)
                    record_encoder_step("tts_overrun_extend", selected_encoder, used_encoder)
                    rough_video.unlink(missing_ok=True)
                    extended.rename(rough_video)
                mark_timing("tts_overrun_extend", step_started, {"overrun_seconds": round(total_overrun, 3)})

        from app.services.subtitle_generator import SubtitleGenerator

        if progress_callback:
            progress_callback({"step": "Generate subtitle", "message": "Đang tạo file phụ đề SRT...", "progress": 82, "phase": "generate_subtitle", "phase_progress": 0.2})
        step_started = time.perf_counter()
        SubtitleGenerator().generate(payload, subtitle_path)
        mark_timing("generate_subtitle", step_started)

        final_video = _unique_path(final_videos_dir() / f"{stem}.mp4")
        final_videos_dir().mkdir(parents=True, exist_ok=True)
        needs_transform = self.output_transformer.needs_transform(options)
        subtitle_input_video = rough_video
        final_burned_by_transform = False
        tts_result: dict[str, str] = {}
        title_enabled = self.title_overlay.enabled(options)
        if needs_transform and effective_subtitle_mode == "burn" and options.blur_mode != "review" and options.tts_mode != "voiceover" and not title_enabled and hasattr(self.output_transformer, "transform_and_burn"):
            if progress_callback:
                progress_callback({"step": "Transform + burn subtitle", "message": "Đang áp dụng tỉ lệ/chất lượng và burn subtitle trong một pass...", "progress": 88, "phase": "transform", "phase_progress": 0.05})
            step_started = time.perf_counter()
            self.output_transformer.transform_and_burn(rough_video, subtitle_path, final_video, options, progress_callback=progress_callback, progress_start=88, progress_end=98, cancel_callback=cancel_callback)  # type: ignore[attr-defined]
            mark_timing("transform_and_burn", step_started)
            final_burned_by_transform = True
        elif needs_transform:
            transform_output = output_dir / f"{prefix}_pre_blur.mp4" if options.blur_mode == "review" else output_dir / f"{prefix}_transformed.mp4" if effective_subtitle_mode == "burn" else final_video
            if progress_callback:
                progress_callback({"step": "Transform output", "message": "Đang áp dụng tùy chọn tỉ lệ/chất lượng output...", "progress": 88, "phase": "transform", "phase_progress": 0.05})
            step_started = time.perf_counter()
            self.output_transformer.transform(rough_video, transform_output, options, progress_callback=progress_callback, progress_start=88, progress_end=94, cancel_callback=cancel_callback)
            mark_timing("transform", step_started)
            subtitle_input_video = transform_output

        if options.blur_mode == "review":
            if progress_callback:
                progress_callback({"step": "Blur review", "message": "Đang chờ bạn chọn vùng blur hoặc bỏ qua blur...", "progress": 95, "phase": "burn_subtitle", "phase_progress": 0.0})
            render_plan_payload = payload.model_dump()
            render_plan_payload["render_options"] = options.model_dump()
            render_plan_payload["burn_subtitle"] = effective_subtitle_mode == "burn"
            render_plan_payload["subtitle_mode"] = effective_subtitle_mode
            render_plan_payload["source_files"] = {source_id: str(path) for source_id, path in source_paths.items()}
            render_plan_payload["pending_blur_review"] = True
            if tts_segment_plans:
                render_plan_payload["segment_plan"] = [_segment_plan_to_dict(p) for p in tts_segment_plans]
            render_plan_payload["video_encoder"] = {"mode": options.video_encoder, "selected": selected_encoder.name, "codec": selected_encoder.codec, "label": selected_encoder.label, "hardware": selected_encoder.hardware}
            render_plan_payload["diagnostics"] = {"timing": timing_payload(), "encoder": {"requested": options.video_encoder, "selected": selected_encoder.name, "codec": selected_encoder.codec, "label": selected_encoder.label, "hardware": selected_encoder.hardware, "events": encoder_events}, "parallelism": render_parallelism_diagnostics(selected_encoder, options, len(payload.video_segments))}
            render_plan.write_text(json.dumps(render_plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return {
                "requires_blur_decision": "True",
                "pre_blur_video_path": str(subtitle_input_video),
                "final_video_path": str(final_video),
                "final_subtitle_path": str(subtitle_path),
                "render_plan_path": str(render_plan),
                "output_dir": str(output_dir),
                "source_path": str(source),
                "workspace_dir": str(workspace_dir),
                "source_count": str(len(source_paths)),
                "vertical_mode": options.vertical_mode,
                "render_quality": options.render_quality,
                "output_resolution": options.output_resolution,
                "burn_subtitle": str(effective_subtitle_mode == "burn"),
                "subtitle_mode": effective_subtitle_mode,
                "video_encoder": selected_encoder.name,
                "video_encoder_label": selected_encoder.label,
                "video_encoder_codec": selected_encoder.codec,
            }

        if options.tts_mode == "voiceover":
            from app.services.tts_tools import TtsVoiceoverService

            if progress_callback:
                progress_callback({"step": "TTS voiceover", "message": "Đang hoàn thiện voiceover (áp dụng speed)...", "progress": 90, "phase": "tts_build", "phase_progress": 0.0})
            video_duration = float(probe_video_metadata(subtitle_input_video).get("duration_seconds") or 0)
            if payload.srt:
                video_duration = max(video_duration, max(srt_timestamp_to_seconds(cue.end) for cue in payload.srt))
            step_started = time.perf_counter()
            tts_result = TtsVoiceoverService().generate_voiceover(
                payload, output_dir, workspace_dir, options, video_duration,
                progress_callback=progress_callback, cancel_callback=cancel_callback,
                segment_speeds=segment_speeds if segment_speeds else None,
            )
            mark_timing("tts_generate_voiceover", step_started, {"cue_count": len(payload.srt)})
            tts_mixed_video = output_dir / f"{prefix}_tts_mixed.mp4"
            step_started = time.perf_counter()
            TtsVoiceoverService().mix_voiceover(subtitle_input_video, Path(tts_result["voiceover_path"]), tts_mixed_video, options, encoder_profile=selected_encoder)
            mark_timing("tts_mix_voiceover", step_started)
            if progress_callback:
                progress_callback({"step": "TTS voiceover", "message": "Đã mix voiceover vào video.", "progress": 94, "phase": "tts_mix", "phase_progress": 1.0})
            subtitle_input_video = tts_mixed_video
            final_burned_by_transform = False

        title_result: dict[str, str] = {}
        if title_enabled:
            if progress_callback:
                progress_callback({"step": "Title overlay", "message": "Đang chèn title lên đầu video...", "progress": 93, "phase": "transform", "phase_progress": 0.9})
            title_video = output_dir / f"{prefix}_title.mp4"
            step_started = time.perf_counter()
            self.title_overlay.apply(subtitle_input_video, title_video, payload, options, progress_callback=progress_callback, progress_start=93, progress_end=94, cancel_callback=cancel_callback)
            mark_timing("title_overlay", step_started)
            subtitle_input_video = title_video
            final_burned_by_transform = False
            title_result = {"title_overlay": "True", "title_text": self.title_overlay.resolve_title(payload, options), "title_style": options.title_style}

        if effective_subtitle_mode == "burn" and not final_burned_by_transform:
            if progress_callback:
                progress_callback({"step": "Burn subtitle", "message": "Đang ghi subtitle vào video...", "progress": 94, "phase": "burn_subtitle", "phase_progress": 0.05})
            step_started = time.perf_counter()
            self.subtitle_burner.burn(subtitle_input_video, subtitle_path, final_video, render_options=options, progress_callback=progress_callback, progress_start=94, progress_end=98, cancel_callback=cancel_callback)
            mark_timing("burn_subtitle", step_started)
        elif subtitle_input_video != final_video:
            if progress_callback:
                progress_callback({"step": "Copy final", "message": "Đang copy video thô thành file cuối...", "progress": 94, "phase": "export", "phase_progress": 0.2})
            step_started = time.perf_counter()
            shutil.copy2(subtitle_input_video, final_video)
            mark_timing("copy_final", step_started)

        if options.video_speed != 1.0 and final_video.exists():
            if progress_callback:
                progress_callback({"step": "Speed up", "message": f"Đang tăng tốc video lên {options.video_speed}x...", "progress": 96, "phase": "speed_up", "phase_progress": 0.05})
            sped_up_tmp = output_dir / f"{prefix}_spedup.mp4"
            speed = options.video_speed
            has_audio = _probe_has_audio(final_video)

            def build_speed_cmd(profile: EncoderProfile) -> list[str]:
                cmd = [settings.ffmpeg_binary, "-y", "-i", str(final_video.resolve()),
                       "-vf", f"setpts=PTS/{speed}"]
                if has_audio:
                    cmd += ["-af", f"atempo={speed}"]
                else:
                    cmd += ["-an"]
                return cmd + [*video_encoder_args(profile, options.render_quality),
                              *audio_encoder_args(options.render_quality),
                              "-r", "30", "-movflags", "+faststart", str(sped_up_tmp.resolve())]

            pre_speed_metadata = probe_video_metadata(final_video)
            step_started = time.perf_counter()
            used_encoder = run_ffmpeg_with_encoder_fallback(build_speed_cmd, "FFmpeg speed-up thất bại",
                mode_override=options.video_encoder,
                progress_callback=progress_callback, duration_seconds=float(pre_speed_metadata.get("duration_seconds") or 0) / speed,
                progress_start=96, progress_end=98, cancel_callback=cancel_callback)
            record_encoder_step("speed_up", selected_encoder, used_encoder)
            final_video.unlink(missing_ok=True)
            shutil.move(str(sped_up_tmp), str(final_video))
            mark_timing("speed_up", step_started, {"speed": speed})

        if progress_callback:
            progress_callback({"step": "Export result", "message": "Đang ghi render plan và hoàn tất output...", "progress": 98, "phase": "export", "phase_progress": 0.8})
        step_started = time.perf_counter()
        render_plan_payload = payload.model_dump()
        render_plan_payload["render_options"] = options.model_dump()
        render_plan_payload["burn_subtitle"] = effective_subtitle_mode == "burn"
        render_plan_payload["subtitle_mode"] = effective_subtitle_mode
        render_plan_payload["source_files"] = {source_id: str(path) for source_id, path in source_paths.items()}
        if tts_result:
            render_plan_payload["tts"] = tts_result
        if title_result:
            render_plan_payload["title_overlay"] = title_result
        if tts_segment_plans:
            render_plan_payload["segment_plan"] = [_segment_plan_to_dict(p) for p in tts_segment_plans]
        source_probe_path = next(iter(source_paths.values()), source)
        source_metadata = probe_video_metadata(source_probe_path)
        output_metadata = probe_video_metadata(final_video)
        render_plan_payload["video_encoder"] = {"mode": options.video_encoder, "selected": selected_encoder.name, "codec": selected_encoder.codec, "label": selected_encoder.label, "hardware": selected_encoder.hardware}
        render_plan_payload["diagnostics"] = {
            "source": source_metadata,
            "output": output_metadata,
            "output_file_size_bytes": final_video.stat().st_size if final_video.exists() else 0,
            "timing": timing_payload(),
            "encoder": {"requested": options.video_encoder, "selected": selected_encoder.name, "codec": selected_encoder.codec, "label": selected_encoder.label, "hardware": selected_encoder.hardware, "events": encoder_events},
            "parallelism": render_parallelism_diagnostics(selected_encoder, options, len(payload.video_segments)),
        }
        render_plan.write_text(json.dumps(render_plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        library_video = final_video
        render_plan_payload["final_video_library_path"] = str(library_video)
        render_plan_payload["final_video_library_dir"] = str(library_video.parent)

        raw_video_path = str(rough_video)
        keep_paths = {final_video, subtitle_path, render_plan}
        if tts_result.get("voiceover_path"):
            keep_paths.add(Path(tts_result["voiceover_path"]))
        if tts_result.get("tts_plan_path"):
            keep_paths.add(Path(tts_result["tts_plan_path"]))
        cleaned_artifacts = cleanup_large_intermediate_artifacts(output_dir, keep_paths, enabled=options.artifact_retention == "smart")
        mark_timing("export_cleanup", step_started, {"cleaned_artifact_count": len(cleaned_artifacts)})
        render_plan_payload["cleanup"] = {"mode": options.artifact_retention, "deleted_files": cleaned_artifacts}
        render_plan_payload["diagnostics"]["timing"] = timing_payload()
        render_plan_payload["diagnostics"]["encoder"] = {"requested": options.video_encoder, "selected": selected_encoder.name, "codec": selected_encoder.codec, "label": selected_encoder.label, "hardware": selected_encoder.hardware, "events": encoder_events}
        render_plan.write_text(json.dumps(render_plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "final_video_path": str(final_video),
            "final_video_library_path": str(library_video),
            "final_video_library_dir": str(library_video.parent),
            "final_subtitle_path": str(subtitle_path),
            "render_plan_path": str(render_plan),
            "output_dir": str(output_dir),
            "source_path": str(source),
            "workspace_dir": str(workspace_dir),
            "deleted_raw_video_path": raw_video_path,
            "artifact_retention": options.artifact_retention,
            "cleaned_artifact_count": str(len(cleaned_artifacts)),
            "cleaned_artifacts": "\n".join(cleaned_artifacts),
            "source_count": str(len(source_paths)),
            "vertical_mode": options.vertical_mode,
            "render_quality": options.render_quality,
            "output_resolution": options.output_resolution,
            "burn_subtitle": str(effective_subtitle_mode == "burn"),
            "subtitle_mode": effective_subtitle_mode,
            "video_encoder": selected_encoder.name,
            "video_encoder_label": selected_encoder.label,
            "video_encoder_codec": selected_encoder.codec,
            **tts_result,
            **title_result,
            "source_codec": source_metadata.get("codec", ""),
            "source_fps": source_metadata.get("fps", ""),
            "source_resolution": source_metadata.get("resolution", ""),
            "output_codec": output_metadata.get("codec", ""),
            "output_fps": output_metadata.get("fps", ""),
            "output_resolution_actual": output_metadata.get("resolution", ""),
            "output_duration_seconds": output_metadata.get("duration_seconds", ""),
            "output_file_size_bytes": str(final_video.stat().st_size if final_video.exists() else 0),
        }
