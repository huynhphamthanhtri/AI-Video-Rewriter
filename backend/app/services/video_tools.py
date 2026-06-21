from __future__ import annotations

import json
import hashlib
import logging
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.core.config import settings
from app.schemas.render import GeminiPayloadSchema, RenderOptions, SourceSchema, clip_timestamp_to_seconds
from app.services.title_layout import _title_font_path, compute_title_layout


ProgressCallback = Callable[[dict], None]
CancelCallback = Callable[[], None]

AUDIO_BITRATE = {"fast": "128k", "balanced": "160k", "high": "192k"}
logger = logging.getLogger(__name__)
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
        result = subprocess.run([settings.ffmpeg_binary, "-hide_banner", "-encoders"], check=True, capture_output=True, text=True)
        return result.stdout + result.stderr
    except (OSError, subprocess.CalledProcessError):
        return ""


def _encoder_runtime_works(codec: str) -> bool:
    cmd = [settings.ffmpeg_binary, "-y", "-f", "lavfi", "-i", "testsrc2=s=128x128:r=30:d=1", "-c:v", codec, "-f", "null", "-"]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def select_video_encoder(mode_override: str | None = None) -> EncoderProfile:
    mode = (mode_override or settings.video_encoder).strip().lower()
    if mode in _ENCODER_CACHE:
        return _ENCODER_CACHE[mode]
    if mode == "cpu":
        _ENCODER_CACHE[mode] = CPU_ENCODER
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
        if profile.codec in enabled and _encoder_runtime_works(profile.codec):
            _ENCODER_CACHE[mode] = profile
            return _ENCODER_CACHE[mode]
    _ENCODER_CACHE[mode] = CPU_ENCODER
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
    if profile.hardware:
        return ["-c:v", profile.codec, "-preset", "fast", *GPU_QUALITY[quality], "-pix_fmt", "yuv420p"]
    return ["-c:v", profile.codec, *CPU_QUALITY[quality], "-pix_fmt", "yuv420p"]


def audio_encoder_args(quality: str) -> list[str]:
    return ["-c:a", "aac", "-b:a", AUDIO_BITRATE[quality], "-ar", "48000", "-ac", "2"]


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
        return bool(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip())
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


def _run_ffmpeg(cmd: list[str], cwd: str | None = None, progress_callback: ProgressCallback | None = None, duration_seconds: float | None = None, progress_start: int = 0, progress_end: int = 100, cancel_callback: CancelCallback | None = None) -> None:
    if progress_callback is None or not duration_seconds or duration_seconds <= 0:
        if cancel_callback:
            cancel_callback()
        subprocess.run(cmd, check=True, cwd=cwd, capture_output=True, text=True)
        if cancel_callback:
            cancel_callback()
        return
    process = subprocess.Popen(_cmd_with_progress(cmd), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output: list[str] = []
    assert process.stdout is not None
    try:
        for line in process.stdout:
            output.append(line)
            if cancel_callback:
                cancel_callback()
            if line.startswith("out_time_ms="):
                try:
                    out_seconds = int(line.split("=", 1)[1].strip()) / 1_000_000
                except ValueError:
                    continue
                ratio = max(0.0, min(1.0, out_seconds / duration_seconds))
                progress_callback({"progress": progress_start + int(ratio * max(0, progress_end - progress_start)), "phase_progress": ratio})
        returncode = process.wait()
    except Exception:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
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
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
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
    normalized = re.sub(r"[^a-z0-9]+", "_", raw_value)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized[:80] or fallback


def sanitize_url(value: str) -> str:
    cleaned = value.strip().strip("<>").strip("'\"`")
    markdown_match = re.fullmatch(r"\[[^\]]+]\(([^)]+)\)", cleaned)
    if markdown_match:
        cleaned = markdown_match.group(1).strip().strip("<>").strip("'\"`")
    cleaned = cleaned.rstrip(";，,。")
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
    def _base_command(self) -> list[str]:
        return [sys.executable, "-m", "yt_dlp"]

    def download(self, url: str, output_path: Path, cookies_file: str | None = None, cookies_from_browser: str | None = None) -> Path:
        url = sanitize_url(url)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            output_path.unlink()
        format_selector = "bestvideo[vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]/bestvideo[vcodec^=avc1]+bestaudio/best[ext=mp4]/best" if settings.ytdlp_prefer_h264 else "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"
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
        effective_cookies_file = cookies_file or settings.ytdlp_cookies_file
        effective_cookies_from_browser = cookies_from_browser or settings.ytdlp_cookies_from_browser
        if effective_cookies_file:
            cmd.extend(["--cookies", effective_cookies_file])
        elif effective_cookies_from_browser:
            cmd.extend(["--cookies-from-browser", effective_cookies_from_browser])
        cmd.append(url)
        self._write_ytdlp_command(cmd)
        self._write_ytdlp_preflight()
        try:
            stdout_path = settings.logs_dir / "ytdlp_stdout.log"
            stderr_path = settings.logs_dir / "ytdlp_stderr.log"
            settings.logs_dir.mkdir(parents=True, exist_ok=True)
            with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
                subprocess.run(cmd, check=True, stdout=stdout, stderr=stderr, text=True)
        except subprocess.CalledProcessError as exc:
            detail = self._format_process_error(exc, settings.logs_dir / "ytdlp_stdout.log", settings.logs_dir / "ytdlp_stderr.log")
            self._write_ytdlp_log(cmd, detail)
            logger.error("yt-dlp failed. Command: %s\n%s", " ".join(cmd), detail)
            raise RuntimeError(self._friendly_error(detail)) from exc
        return output_path

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
                    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
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

    def _friendly_error(self, detail: str) -> str:
        if "Sign in to confirm" in detail or "not a bot" in detail or "--cookies-from-browser" in detail:
            return (
                "yt-dlp bị YouTube chặn vì cần xác minh đăng nhập/không phải bot. "
                "Hãy cấu hình YTDLP_COOKIES_FROM_BROWSER=chrome/edge hoặc YTDLP_COOKIES_FILE trong .env, "
                "hoặc render bằng local_video_path. Chi tiết: " + detail
            )
        if "No supported JavaScript runtime" in detail:
            return (
                "yt-dlp cảnh báo thiếu JavaScript runtime để giải mã YouTube. "
                "Hãy cài Node.js/Deno và cấu hình YTDLP_JS_RUNTIMES=node/deno nếu cần, "
                "hoặc cấu hình cookies nếu YouTube yêu cầu xác minh. Chi tiết: " + detail
            )
        if "Remote component challenge solver" in detail or "n challenge solving failed" in detail:
            return (
                "yt-dlp cần challenge solver để giải mã YouTube. "
                "Hãy cấu hình YTDLP_REMOTE_COMPONENTS=ejs:github trong .env và restart backend. Chi tiết: " + detail
            )
        return "yt-dlp tải video thất bại. Chi tiết: " + detail


class VideoCutter:
    def cut(self, source_paths: dict[str, Path], payload: GeminiPayloadSchema, clips_dir: Path, reencode_segments: bool = False, progress_callback: ProgressCallback | None = None, render_options: RenderOptions | None = None, cancel_callback: CancelCallback | None = None) -> list[Path]:
        options = render_options or RenderOptions()
        quality = quality_for_stability(options)
        segment_fps = segment_fps_value(options)
        clips_dir.mkdir(parents=True, exist_ok=True)
        results: list[Path] = []
        ordered_segments = sorted(payload.video_segments, key=lambda item: item.order)
        total_segments = len(ordered_segments)
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
            output = clips_dir / f"segment_{segment.segment_id}.mp4"
            source_id = segment.source_id or "source_1"
            source_path = source_paths.get(source_id)
            if source_path is None:
                raise RuntimeError(f"Không tìm thấy video nguồn cho source_id={source_id}.")
            duration = clip_timestamp_to_seconds(segment.source_end) - clip_timestamp_to_seconds(segment.source_start)
            if duration <= 0:
                raise RuntimeError(f"Segment #{segment.segment_id} có duration không hợp lệ.")

            def build_cmd(profile: EncoderProfile) -> list[str]:
                return [
                    settings.ffmpeg_binary,
                    "-y",
                    "-ss",
                    segment.source_start,
                    "-i",
                    str(source_path),
                    "-t",
                    f"{duration:.3f}",
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a?",
                    "-vf",
                    f"fps={segment_fps},setpts=PTS-STARTPTS,setsar=1",
                    "-af",
                    "aresample=async=1:first_pts=0",
                    *video_encoder_args(profile, quality),
                    *audio_encoder_args(quality),
                    "-movflags",
                    "+faststart",
                    str(output),
                ]

            progress_start = 30 + int(((index - 1) / max(total_segments, 1)) * 40)
            progress_end = 30 + int((index / max(total_segments, 1)) * 40)
            run_ffmpeg_with_encoder_fallback(build_cmd, f"FFmpeg cắt segment #{segment.segment_id} thất bại", mode_override=options.video_encoder, progress_callback=progress_callback, duration_seconds=duration, progress_start=progress_start, progress_end=progress_end, cancel_callback=cancel_callback)
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


def normalize_render_sources(payload: GeminiPayloadSchema, youtube_url: str | None, local_video_path: str | None) -> list[SourceSchema]:
    if payload.sources:
        for segment in payload.video_segments:
            if not segment.source_id:
                raise ValueError(f"Segment #{segment.segment_id} thiếu source_id khi JSON có sources[].")
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
        subprocess.run(cmd, check=True, cwd=str(clips_dir), capture_output=True, text=True)
        rough = absolute_output
        rough_fast = output_path.parent / f"{output_path.stem}_faststart.mp4"
        subprocess.run(
            [settings.ffmpeg_binary, "-y", "-i", str(rough),
             "-c", "copy", "-movflags", "+faststart",
             str(rough_fast)],
            check=True, capture_output=True, text=True)
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
                    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:10[bg];[0:v]scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v]",
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
            cmd.extend(["-movflags", "+faststart", str(output_path.resolve())])
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
                    f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:10[bg];[0:v]scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[base];[base]subtitles={relative_ass}[v]",
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
            cmd.extend(["-movflags", "+faststart", str(output_path.resolve())])
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

        font_path = _title_font_path()
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
        render_options: RenderOptions | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: CancelCallback | None = None,
    ) -> dict[str, str]:
        options = render_options or RenderOptions()
        effective_subtitle_mode = subtitle_mode or ("burn" if burn_subtitle else "none")
        selected_encoder = select_video_encoder(options.video_encoder)
        fallback_title = Path(local_video_path).stem if local_video_path else "youtube_video"
        prefix = safe_filename_prefix(payload.metadata.video_title, fallback=fallback_title)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = settings.outputs_dir / f"{prefix}_{timestamp}"
        workspace_name = safe_filename_prefix(job_id, fallback=f"render_{timestamp}")
        workspace_dir = settings.temp_dir / workspace_name

        source = workspace_dir / "source.mp4"
        settings.temp_dir.mkdir(parents=True, exist_ok=True)
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

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
                    self.downloader.download(source_item.youtube_url, source_output, cookies_file=request_cookies_file, cookies_from_browser=ytdlp_cookies_from_browser)
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
        if progress_callback:
            progress_callback({"step": "Prepare sources", "message": "Đã chuẩn bị xong tất cả video nguồn.", "progress": 30, "phase": "download_sources", "phase_progress": 1.0})

        clips_dir = workspace_dir / "segments"
        if cancel_callback:
            cancel_callback()
        self.cutter.cut(source_paths, payload, clips_dir, reencode_segments=True, progress_callback=progress_callback, render_options=options, cancel_callback=cancel_callback)
        rough_video = output_dir / f"{prefix}_raw.mp4"
        if progress_callback:
            progress_callback({"step": "Concatenate", "message": "Đang ghép các segment thành video thô...", "progress": 72, "phase": "concat", "phase_progress": 0.2})
        self.concatenator.concatenate(payload, clips_dir, rough_video)
        from app.services.subtitle_generator import SubtitleGenerator

        if progress_callback:
            progress_callback({"step": "Generate subtitle", "message": "Đang tạo file phụ đề SRT...", "progress": 82, "phase": "generate_subtitle", "phase_progress": 0.2})
        SubtitleGenerator().generate(payload, subtitle_path)

        final_video = output_dir / f"{prefix}_final.mp4"
        needs_transform = self.output_transformer.needs_transform(options)
        subtitle_input_video = rough_video
        final_burned_by_transform = False
        tts_result: dict[str, str] = {}
        title_enabled = self.title_overlay.enabled(options)
        if needs_transform and effective_subtitle_mode == "burn" and options.blur_mode != "review" and options.tts_mode != "voiceover" and not title_enabled and hasattr(self.output_transformer, "transform_and_burn"):
            if progress_callback:
                progress_callback({"step": "Transform + burn subtitle", "message": "Đang áp dụng tỉ lệ/chất lượng và burn subtitle trong một pass...", "progress": 88, "phase": "transform", "phase_progress": 0.05})
            self.output_transformer.transform_and_burn(rough_video, subtitle_path, final_video, options, progress_callback=progress_callback, progress_start=88, progress_end=98, cancel_callback=cancel_callback)  # type: ignore[attr-defined]
            final_burned_by_transform = True
        elif needs_transform:
            transform_output = output_dir / f"{prefix}_pre_blur.mp4" if options.blur_mode == "review" else output_dir / f"{prefix}_transformed.mp4" if effective_subtitle_mode == "burn" else final_video
            if progress_callback:
                progress_callback({"step": "Transform output", "message": "Đang áp dụng tùy chọn tỉ lệ/chất lượng output...", "progress": 88, "phase": "transform", "phase_progress": 0.05})
            self.output_transformer.transform(rough_video, transform_output, options, progress_callback=progress_callback, progress_start=88, progress_end=94, cancel_callback=cancel_callback)
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
                progress_callback({"step": "TTS voiceover", "message": "Đang tạo và mix voiceover VieNeu Turbo...", "progress": 90, "phase": "tts_generate", "phase_progress": 0.0})
            video_duration = float(probe_video_metadata(subtitle_input_video).get("duration_seconds") or 0)
            tts_result = TtsVoiceoverService().generate_voiceover(payload, output_dir, workspace_dir, options, video_duration, progress_callback=progress_callback, cancel_callback=cancel_callback)
            tts_mixed_video = output_dir / f"{prefix}_tts_mixed.mp4"
            TtsVoiceoverService().mix_voiceover(subtitle_input_video, Path(tts_result["voiceover_path"]), tts_mixed_video, options)
            if progress_callback:
                progress_callback({"step": "TTS voiceover", "message": "Đã mix voiceover vào video.", "progress": 94, "phase": "tts_mix", "phase_progress": 1.0})
            subtitle_input_video = tts_mixed_video
            final_burned_by_transform = False

        title_result: dict[str, str] = {}
        if title_enabled:
            if progress_callback:
                progress_callback({"step": "Title overlay", "message": "Đang chèn title lên đầu video...", "progress": 93, "phase": "transform", "phase_progress": 0.9})
            title_video = output_dir / f"{prefix}_title.mp4"
            self.title_overlay.apply(subtitle_input_video, title_video, payload, options, progress_callback=progress_callback, progress_start=93, progress_end=94, cancel_callback=cancel_callback)
            subtitle_input_video = title_video
            final_burned_by_transform = False
            title_result = {"title_overlay": "True", "title_text": self.title_overlay.resolve_title(payload, options), "title_style": options.title_style}

        if effective_subtitle_mode == "burn" and not final_burned_by_transform:
            if progress_callback:
                progress_callback({"step": "Burn subtitle", "message": "Đang ghi subtitle vào video...", "progress": 94, "phase": "burn_subtitle", "phase_progress": 0.05})
            self.subtitle_burner.burn(subtitle_input_video, subtitle_path, final_video, render_options=options, progress_callback=progress_callback, progress_start=94, progress_end=98, cancel_callback=cancel_callback)
        elif subtitle_input_video != final_video:
            if progress_callback:
                progress_callback({"step": "Copy final", "message": "Đang copy video thô thành file cuối...", "progress": 94, "phase": "export", "phase_progress": 0.2})
            shutil.copy2(subtitle_input_video, final_video)

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
                              "-movflags", "+faststart", str(sped_up_tmp.resolve())]

            pre_speed_metadata = probe_video_metadata(final_video)
            run_ffmpeg_with_encoder_fallback(build_speed_cmd, "FFmpeg speed-up thất bại",
                mode_override=options.video_encoder,
                progress_callback=progress_callback, duration_seconds=float(pre_speed_metadata.get("duration_seconds") or 0) / speed,
                progress_start=96, progress_end=98, cancel_callback=cancel_callback)
            final_video.unlink(missing_ok=True)
            shutil.move(str(sped_up_tmp), str(final_video))

        if progress_callback:
            progress_callback({"step": "Export result", "message": "Đang ghi render plan và hoàn tất output...", "progress": 98, "phase": "export", "phase_progress": 0.8})
        render_plan_payload = payload.model_dump()
        render_plan_payload["render_options"] = options.model_dump()
        render_plan_payload["burn_subtitle"] = effective_subtitle_mode == "burn"
        render_plan_payload["subtitle_mode"] = effective_subtitle_mode
        render_plan_payload["source_files"] = {source_id: str(path) for source_id, path in source_paths.items()}
        if tts_result:
            render_plan_payload["tts"] = tts_result
        if title_result:
            render_plan_payload["title_overlay"] = title_result
        source_probe_path = next(iter(source_paths.values()), source)
        source_metadata = probe_video_metadata(source_probe_path)
        output_metadata = probe_video_metadata(final_video)
        render_plan_payload["video_encoder"] = {"mode": options.video_encoder, "selected": selected_encoder.name, "codec": selected_encoder.codec, "label": selected_encoder.label, "hardware": selected_encoder.hardware}
        render_plan_payload["diagnostics"] = {"source": source_metadata, "output": output_metadata, "output_file_size_bytes": final_video.stat().st_size if final_video.exists() else 0}
        render_plan.write_text(json.dumps(render_plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        raw_video_path = str(rough_video)
        keep_paths = {final_video, subtitle_path, render_plan}
        if tts_result.get("voiceover_path"):
            keep_paths.add(Path(tts_result["voiceover_path"]))
        if tts_result.get("tts_plan_path"):
            keep_paths.add(Path(tts_result["tts_plan_path"]))
        cleaned_artifacts = cleanup_large_intermediate_artifacts(output_dir, keep_paths, enabled=options.artifact_retention == "smart")
        render_plan_payload["cleanup"] = {"mode": options.artifact_retention, "deleted_files": cleaned_artifacts}
        render_plan.write_text(json.dumps(render_plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "final_video_path": str(final_video),
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
