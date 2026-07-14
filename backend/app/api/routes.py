from __future__ import annotations

import asyncio
import logging
import sys
import uuid
import time
import os
import shutil
import json
import subprocess
from threading import Lock
from pathlib import Path
from urllib.parse import quote

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, WebSocket
from fastapi.responses import FileResponse
from pydantic import BaseModel

import yt_dlp

from app.api.deps import get_preset_service
from app.core.config import ROOT_DIR, settings
from app.core.database import get_db
from app.schemas.common import MessageResponse, UploadCookiesResponse
from app.schemas.batch import BatchAutoSubmitResponse, BatchProgress
from app.schemas.preset import PresetCompareRequest, PresetCompareResponse, PresetCreate, PresetRead, PresetUpdate
from app.services.preset_service import validate_preset_conflicts
from app.schemas.prompt import PromptGenerateRequest, PromptGenerateResponse, PromptHealthResponse, PromptPreviewRequest, PromptPreviewResponse, PresetRecommendRequest, PresetRecommendResponse, PromptRunCreate, PromptRunRead, PromptRunStats
from app.services.prompt_telemetry import PromptRunService
from app.schemas.render import BlurDecisionRequest, BlurRenderRequest, BlurRenderResponse, BlurUploadResponse, GeminiPayloadSchema, OpenFolderRequest, RenderJobStartResponse, RenderJobStatusResponse, RenderOptions, RenderPreferencesRequest, RenderPreferencesResponse, RenderRequest, RenderResponse, SavedCookiesResponse, StorageCleanupRequest, StorageCleanupResponse, StorageStatsResponse, TitleLayoutPreviewRequest, TitleLayoutPreviewResponse, TtsClonePreviewRequest, TtsClonePreviewResponse, TtsCloneUploadResponse, TtsGenerateRequest, TtsGenerateResponse, TtsVoicePreviewRequest, TtsVoicePreviewResponse, ValidateJsonRequest, ValidateJsonResponse
from app.services.blur_tools import BlurService
from app.services.title_layout import compute_title_preview
from app.services.json_validator import JsonValidator
from app.services.preset_service import PresetConflictError, PresetNotFoundError, PresetProtectedError, PresetService
from app.services.app_settings import AppSettingsService
from app.schemas.subtitle import SubtitlePreviewStyleRequest, SubtitlePreviewStyleResponse
from app.services.subtitle_preview import compute_preview
from app.services.preset_recommender import PresetRecommender
from app.services.prompt_generator import PromptGenerator
from app.services.prompt_health import score_preset_health
from app.services.prompt_preview import PromptPreviewService
from app.services.preset_compare import compare_presets
from app.services.video_tools import RenderPipeline, SubtitleBurner, TitleOverlay, VideoCutter, VideoConcatenator, VideoDownloader, cleanup_large_intermediate_artifacts, final_videos_dir, probe_video_metadata, select_video_encoder, ui_safe_error, analyze_ytdlp_cookie_file, video_encoder_diagnostics
from app.services.tts_tools import TtsVoiceoverService, create_clone_voice, generate_standalone_tts, list_cloned_voices, list_edge_tts_voices, preview_builtin_voice, preview_clone_voice, tts_clones_dir, edge_tts_status, TTS_PREVIEWS_DIR, tts_studio_outputs_dir
from app.services.license_service import LicenseError, LicenseService
from app.services.updater_service import UpdaterError, compare_versions, get_local_version, get_remote_manifest, launch_updater
from app.services.gemini_automation import gemini_service, GeminiAutomationService
from app.services.batch_pipeline import batch_service
from app.schemas.prompt import GeminiAutoSubmitRequest, GeminiAutoSubmitResponse, GeminiAutoSubmitStatusResponse
from app.services.prompt_generator import PromptGenerator

router = APIRouter()
RUNTIME_STARTED_AT = time.time()
render_jobs: dict[str, dict] = {}
render_queue: list[tuple[str, RenderRequest]] = []
render_jobs_lock = Lock()
render_worker_running = False
ALLOWED_BLUR_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
ALLOWED_TTS_REF_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
SAVED_COOKIES_KEY = "youtube_cookies"
RENDER_PREFERENCES_KEY = "last_render_preferences"


class RenderJobCancelled(RuntimeError):
    pass


class LicenseActivateRequest(BaseModel):
    license_key: str


class LicenseUnbindRequest(BaseModel):
    license_key: str | None = None


def _license_service() -> LicenseService:
    return LicenseService()


def _require_license(feature: str) -> None:
    if not settings.sv_key_api_url:
        return
    try:
        _license_service().require_feature(feature)
    except LicenseError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _require_tts_ready() -> None:
    status = edge_tts_status()
    if status.get("status") != "ready":
        raise HTTPException(status_code=400, detail=status.get("message", "Edge TTS chưa sẵn sàng."))


def _parse_cookies_from_browser(value: str | None):
    """Parse cookies_from_browser string into yt-dlp tuple or None."""
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if ":" in raw:
        browser, profile = raw.split(":", 1)
        browser = browser.strip()
        profile = profile.strip()
        if browser in {"chrome", "edge", "firefox"} and profile:
            return (browser, profile, None, None)
        return None
    if raw in {"chrome", "edge", "firefox"}:
        return (raw, None, None, None)
    return None


def _resolve_duration_auth(
    cookies_file: str | None,
    cookies_from_browser: str | None,
    user_data_dir: str | None,
) -> tuple[str | None, str | None]:
    """Resolve effective cookies_file and cookies_from_browser.

    Mirror VideoDownloader resolution order plus repo-profile fallback.
    """
    downloader = VideoDownloader()
    effective_cookies_file = cookies_file or settings.ytdlp_cookies_file
    repo_profile = str(ROOT_DIR / "data" / "gemini_profile")
    effective_cookies_from_browser = (
        cookies_from_browser
        or downloader._browser_cookie_source_from_profile(user_data_dir)
        or downloader._browser_cookie_source_from_profile(str(settings.gemini_profile_path))
        or downloader._browser_cookie_source_from_profile(repo_profile)
        or settings.ytdlp_cookies_from_browser
    )
    return effective_cookies_file, effective_cookies_from_browser


def _write_duration_diagnostics(
    url: str,
    attempt: str,
    cookies_file: str | None,
    cookies_from_browser: str | None,
    duration: int | None,
    error: str | None,
    cli_stdout: str | None = None,
    cli_stderr: str | None = None,
    cli_command: str | None = None,
) -> None:
    """Write diagnostic info for duration preflight."""
    try:
        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        diag = {
            "url": url,
            "attempt": attempt,
            "cookies_file": cookies_file,
            "cookies_file_exists": os.path.isfile(cookies_file) if cookies_file else False,
            "cookies_from_browser": cookies_from_browser,
            "timestamp": time.time(),
        }
        if duration is not None:
            diag["duration"] = duration
        if error:
            diag["error"] = error[:3000]
        if cli_stdout:
            diag["cli_stdout"] = cli_stdout[:3000]
        if cli_stderr:
            diag["cli_stderr"] = cli_stderr[:3000]
        if cli_command:
            diag["cli_command"] = cli_command[:3000]

        diag_path = settings.logs_dir / "ytdlp_duration_preflight.json"
        diag_path.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding="utf-8")
        error_path = settings.logs_dir / "ytdlp_duration_error.txt"
        if error:
            error_path.write_text(f"[{attempt}] {url}\n{error}", encoding="utf-8")
        logger.info("Duration preflight %s for %s: cookies_file=%s cookies_from_browser=%s duration=%s",
                     attempt, url, cookies_file, cookies_from_browser, duration)
    except Exception:
        logger.exception("Failed to write duration preflight diagnostics")


def _python_api_duration(
    url: str,
    cookies_file: str | None,
    cookies_from_browser: str | None,
) -> tuple[int | None, str | None]:
    """Extract duration via yt-dlp Python API. Returns (duration, error)."""
    try:
        ydl_opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
            "timeout": 10.0,
        }
        if cookies_file:
            ydl_opts["cookiefile"] = cookies_file
        browser_tuple = _parse_cookies_from_browser(cookies_from_browser)
        if browser_tuple:
            ydl_opts["cookiesfrombrowser"] = browser_tuple
        if settings.ytdlp_js_runtimes:
            ydl_opts["js_runtimes"] = settings.ytdlp_js_runtimes

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get("duration")
            if duration:
                return int(duration), None
            return None, "duration field not found in yt-dlp response"
    except Exception as exc:
        exc_text = str(exc)
        logger.warning("yt-dlp Python API duration extraction failed for %s: %s", url, exc_text[:500])
        return None, exc_text[:3000]


def _cli_duration(
    url: str,
    cookies_file: str | None,
    cookies_from_browser: str | None,
) -> tuple[int | None, str | None, str | None, str | None, str | None]:
    """Extract duration via yt-dlp CLI subprocess.

    Returns (duration, error, stdout, stderr, command_string).
    """
    cmd = [sys.executable, "-m", "yt_dlp",
           "--dump-single-json", "--skip-download", "--no-playlist",
           "--quiet", "--no-warnings"]
    if settings.ytdlp_js_runtimes:
        cmd.extend(["--js-runtimes", settings.ytdlp_js_runtimes])
    if settings.ytdlp_remote_components:
        cmd.extend(["--remote-components", settings.ytdlp_remote_components])
    if cookies_file:
        cmd.extend(["--cookies", cookies_file])
    if cookies_from_browser:
        cmd.extend(["--cookies-from-browser", cookies_from_browser])
    cmd.append(url)

    cmd_str = " ".join(cmd)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30.0,
                                encoding="utf-8", errors="replace")
        if result.returncode == 0 and result.stdout.strip():
            stdout = result.stdout.strip()
            lines = stdout.split("\n")
            for line in reversed(lines):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        info = json.loads(line)
                        duration = info.get("duration")
                        if duration:
                            return int(duration), None, stdout, result.stderr, cmd_str
                    except (json.JSONDecodeError, ValueError):
                        continue
            return None, "No JSON found in CLI stdout", stdout, result.stderr, cmd_str
        error_msg = result.stderr[:3000] if result.stderr else f"Exit code {result.returncode}, no stderr"
        return None, error_msg, result.stdout, result.stderr, cmd_str
    except subprocess.TimeoutExpired:
        return None, "yt-dlp CLI timed out after 30s", None, None, cmd_str
    except Exception as exc:
        return None, str(exc)[:3000], None, None, cmd_str


def _get_youtube_duration_seconds(
    url: str,
    cookies_file: str | None = None,
    cookies_from_browser: str | None = None,
    user_data_dir: str | None = None,
) -> int | None:
    """Get YouTube video duration in seconds.

    Resolution:
      1. Python API with resolved auth
      2. CLI fallback if Python fails
    Diagnostic file written to logs/ytdlp_duration_preflight.json.
    """
    resolved_cookies_file, resolved_cookies_from_browser = _resolve_duration_auth(
        cookies_file, cookies_from_browser, user_data_dir
    )

    # Attempt 1: Python API
    duration, error = _python_api_duration(url, resolved_cookies_file, resolved_cookies_from_browser)
    if duration is not None:
        _write_duration_diagnostics(url, "python_api", resolved_cookies_file, resolved_cookies_from_browser, duration, None)
        return duration

    logger.warning("Python API duration failed, trying CLI fallback for %s: %s", url, (error or "")[:300])

    # Attempt 2: CLI fallback
    cli_duration, cli_error, cli_stdout, cli_stderr, cli_cmd = _cli_duration(
        url, resolved_cookies_file, resolved_cookies_from_browser
    )
    _write_duration_diagnostics(
        url, "cli_fallback", resolved_cookies_file, resolved_cookies_from_browser,
        cli_duration, cli_error, cli_stdout, cli_stderr, cli_cmd
    )
    if cli_duration is not None:
        return cli_duration

    logger.warning("yt-dlp duration extraction failed for %s (Python API + CLI both failed)", url)
    return None


def _update_render_job(job_id: str, **updates):
    with render_jobs_lock:
        now = time.time()
        current = render_jobs.get(job_id, {})
        _update_eta_plan(current, updates, now)
        render_jobs[job_id] = {**current, **updates, "started_at": current.get("started_at", now), "updated_at": now}


def _phase(name: str, estimate: float) -> dict:
    return {"name": name, "estimate_seconds": max(1.0, float(estimate)), "progress": 0.0, "started_at": None, "finished_at": None}


def _build_eta_plan(payload: GeminiPayloadSchema, options: RenderOptions, subtitle_mode: str, source_count: int) -> dict:
    total_segment_duration = sum(max(0.1, segment.duration_seconds) for segment in payload.video_segments)
    output_duration = max(1.0, total_segment_duration)
    phases = [
        _phase("validate", 2),
        _phase("prepare_sources", 3),
        _phase("download_sources", max(3, source_count * 20)),
        _phase("cut_segments", max(5, total_segment_duration * 0.6)),
        _phase("concat", 5),
        _phase("generate_subtitle", 2),
    ]
    needs_transform = options.vertical_mode != "none" or options.output_resolution != "auto" or options.render_quality != "balanced"
    if needs_transform:
        phases.append(_phase("transform", max(3, output_duration * 0.25)))
    if options.tts_mode == "voiceover":
        phases.append(_phase("tts_generate", max(5, len(payload.srt) * 2)))
        phases.append(_phase("tts_mix", max(2, output_duration * 0.05)))
    if subtitle_mode == "burn":
        phases.append(_phase("burn_subtitle", max(3, output_duration * 0.2)))
    if options.video_speed != 1.0:
        phases.append(_phase("speed_up", max(2, output_duration * 0.08)))
    phases.append(_phase("export", 2))
    return {"phases": phases, "paused": False, "paused_started_at": None, "paused_seconds": 0.0}


def _update_eta_plan(job: dict, updates: dict, now: float) -> None:
    plan = job.get("eta_plan")
    if not plan:
        return
    phase_name = updates.get("phase")
    if not phase_name:
        phase_name = _phase_from_progress(int(updates.get("progress") or job.get("progress") or 0), updates.get("step") or job.get("step") or "")
    phase_progress = updates.get("phase_progress")
    if phase_progress is None and "progress" in updates:
        phase_progress = _phase_progress_from_global(phase_name, int(updates.get("progress") or 0))
    phases = plan.get("phases") or []
    for index, phase in enumerate(phases):
        if phase["name"] == phase_name:
            if phase.get("started_at") is None:
                phase["started_at"] = now
            phase["progress"] = max(float(phase.get("progress") or 0), max(0.0, min(1.0, float(phase_progress if phase_progress is not None else 0.05))))
            for previous in phases[:index]:
                previous["progress"] = 1.0
                previous["finished_at"] = previous.get("finished_at") or now
            if phase["progress"] >= 0.999:
                phase["finished_at"] = phase.get("finished_at") or now
            break


def _phase_from_progress(progress: int, step: str) -> str:
    lower = step.lower()
    if "download" in lower or "source" in lower or "copy sources" in lower:
        return "download_sources"
    if "cut" in lower or "segment" in lower:
        return "cut_segments"
    if "concat" in lower:
        return "concat"
    if "subtitle" in lower and "burn" not in lower:
        return "generate_subtitle"
    if "transform" in lower:
        return "transform"
    if "tts" in lower:
        return "tts_generate"
    if "burn" in lower:
        return "burn_subtitle"
    if "speed" in lower:
        return "speed_up"
    if "export" in lower or "copy final" in lower:
        return "export"
    if progress < 10:
        return "validate"
    if progress < 30:
        return "download_sources"
    if progress < 72:
        return "cut_segments"
    if progress < 82:
        return "concat"
    if progress < 88:
        return "generate_subtitle"
    if progress < 94:
        return "transform"
    if progress < 96:
        return "burn_subtitle"
    if progress < 98:
        return "speed_up"
    return "export"


def _phase_progress_from_global(phase: str, progress: int) -> float:
    ranges = {"validate": (0, 10), "download_sources": (10, 30), "cut_segments": (30, 72), "concat": (72, 82), "generate_subtitle": (82, 88), "transform": (88, 94), "tts_generate": (90, 93), "tts_mix": (93, 94), "burn_subtitle": (94, 96), "speed_up": (96, 98), "export": (98, 100)}
    start, end = ranges.get(phase, (0, 100))
    return max(0.0, min(1.0, (progress - start) / max(1, end - start)))


def _eta_from_plan(job: dict, now: float) -> tuple[float | None, float | None, float]:
    plan = job.get("eta_plan")
    started_at = job.get("started_at")
    if not plan or started_at is None:
        return None, None, 0.0
    paused_seconds = float(plan.get("paused_seconds") or 0)
    if plan.get("paused") and plan.get("paused_started_at"):
        paused_seconds += max(0.0, now - float(plan["paused_started_at"]))
    elapsed_processing = max(0.0, now - float(started_at) - paused_seconds)
    if plan.get("paused"):
        return elapsed_processing, None, paused_seconds
    remaining = 0.0
    for phase in plan.get("phases") or []:
        if phase.get("finished_at") or float(phase.get("progress") or 0) >= 0.999:
            continue
        progress = max(0.0, min(0.99, float(phase.get("progress") or 0)))
        estimate = float(phase.get("estimate_seconds") or 1)
        if phase.get("started_at") and progress > 0:
            elapsed_phase = max(0.0, now - float(phase["started_at"]))
            estimate = max(estimate, elapsed_phase / progress)
        remaining += estimate * (1 - progress)
    return elapsed_processing, remaining, paused_seconds


def _with_render_job_eta(job: dict) -> dict:
    now = time.time()
    started_at = job.get("started_at")
    progress = max(0, min(100, int(job.get("progress") or 0)))
    enriched = dict(job)
    if started_at is None:
        enriched.update(elapsed_seconds=None, estimated_total_seconds=None, remaining_seconds=None)
        return enriched

    elapsed_from_plan, remaining_from_plan, _ = _eta_from_plan(job, now)
    elapsed_seconds = elapsed_from_plan if elapsed_from_plan is not None else max(0.0, now - float(started_at))
    estimated_total_seconds = None
    remaining_seconds = None
    if job.get("status") == "done":
        estimated_total_seconds = elapsed_seconds
        remaining_seconds = 0.0
    elif job.get("status") == "waiting_blur":
        estimated_total_seconds = None
        remaining_seconds = None
    elif remaining_from_plan is not None:
        remaining_seconds = max(0.0, remaining_from_plan)
        estimated_total_seconds = elapsed_seconds + remaining_seconds
    elif job.get("status") != "error" and progress > 0:
        estimated_total_seconds = elapsed_seconds / (progress / 100)
        remaining_seconds = max(0.0, estimated_total_seconds - elapsed_seconds)
    enriched.update(
        elapsed_seconds=elapsed_seconds,
        estimated_total_seconds=estimated_total_seconds,
        remaining_seconds=remaining_seconds,
    )
    return enriched


def _cleanup_render_jobs() -> None:
    cutoff = time.time() - settings.render_job_ttl_seconds
    with render_jobs_lock:
        expired = [job_id for job_id, job in render_jobs.items() if job.get("updated_at", 0) < cutoff]
        for job_id in expired:
            del render_jobs[job_id]


def _is_cancel_requested(job_id: str) -> bool:
    with render_jobs_lock:
        return bool(render_jobs.get(job_id, {}).get("cancel_requested"))


def _raise_if_cancelled(job_id: str) -> None:
    if _is_cancel_requested(job_id):
        _update_render_job(job_id, status="cancelled", step="Cancel", message="Render job đã bị hủy.", progress=100)
        raise RenderJobCancelled("Render job đã bị hủy.")


def _dir_size_and_count(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    total_size = 0
    total_count = 0
    for item in path.rglob("*"):
        total_count += 1
        if item.is_file():
            try:
                total_size += item.stat().st_size
            except OSError:
                continue
    return total_size, total_count


def _safe_path_under(path_value: str, root: Path) -> Path:
    path = Path(path_value).expanduser().resolve()
    root_path = root.expanduser().resolve()
    try:
        path.relative_to(root_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Path phải nằm trong {root_path}") from exc
    return path


def _safe_custom_path(path_value: str) -> Path | None:
    try:
        p = Path(path_value).expanduser().resolve()
        if not p.is_absolute():
            return None
        if p.parent == p:
            return None
        parent = p.parent
        while parent != parent.parent:
            if parent.name.lower() in ("windows", "program files", "program files (x86)", "programdata"):
                return None
            parent = parent.parent
        return p
    except (RuntimeError, OSError):
        return None


def _safe_path_under_any(path_value: str, roots: list[Path]) -> Path:
    path = Path(path_value).expanduser().resolve()
    for root in roots:
        root_path = root.expanduser().resolve()
        try:
            path.relative_to(root_path)
            return path
        except ValueError:
            continue
    raise HTTPException(status_code=400, detail="Path không nằm trong thư mục cho phép.")


def _blur_uploads_dir() -> Path:
    return settings.temp_dir / "blur_uploads"


def _blur_preview_url(path: Path) -> str:
    return f"/api/blur/preview?path={quote(str(path))}"


def _saved_cookies_path() -> Path:
    return settings.outputs_dir.parent / "data" / "cookies" / "cookies.txt"


def _saved_cookies_metadata(db) -> dict | None:
    metadata = AppSettingsService(db).get(SAVED_COOKIES_KEY)
    if not metadata or not metadata.get("cookies_file_path"):
        return None
    path = Path(metadata["cookies_file_path"])
    if not path.exists():
        AppSettingsService(db).delete(SAVED_COOKIES_KEY)
        return None
    return metadata


def _effective_cookies_file(value: str | None, db) -> str | None:
    if value:
        return value
    metadata = _saved_cookies_metadata(db)
    return metadata.get("cookies_file_path") if metadata else None


def _active_workspace_dirs() -> set[Path]:
    with render_jobs_lock:
        jobs = list(render_jobs.values())
    active = set()
    for job in jobs:
        if job.get("status") in {"queued", "running"}:
            result = job.get("result") or {}
            workspace = result.get("workspace_dir")
            if workspace:
                active.add(Path(workspace).resolve())
    return active


AUTO_CLEANUP_CACHE_DIRS = frozenset({
    "source_cache",
    "gemini_failed_response",
    "tts_voices",
    "tts_clone_uploads",
    "blur_uploads",
})


def _newest_mtime(path: Path) -> float:
    newest = path.stat().st_mtime
    try:
        for p in path.rglob("*"):
            if p.is_dir():
                continue
            try:
                m = p.stat().st_mtime
                if m > newest:
                    newest = m
            except OSError:
                continue
    except (PermissionError, OSError):
        pass
    return newest


def _cleanup_root(root: Path, older_than_hours: int, dry_run: bool, protected: set[Path]) -> tuple[int, int, int, list[str]]:
    if not root.exists():
        return 0, 0, 0, []
    cutoff = time.time() - (older_than_hours * 3600)
    matched = 0
    deleted = 0
    freed = 0
    items: list[str] = []
    for item in root.iterdir():
        try:
            item_path = item.resolve()
        except Exception:
            continue
        if item_path in protected:
            continue

        if item.is_dir() and item.name in AUTO_CLEANUP_CACHE_DIRS:
            for child in item.iterdir():
                try:
                    child_mtime = child.stat().st_mtime
                except OSError:
                    continue
                if child_mtime > cutoff:
                    continue
                child_size = child.stat().st_size if child.is_file() else 0
                matched += 1
                freed += child_size
                if len(items) < 100:
                    items.append(str(child))
                if not dry_run:
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                        deleted += 1
                    else:
                        try:
                            child.unlink(missing_ok=True)
                            deleted += 1
                        except OSError:
                            pass
            continue

        try:
            mtime = item.stat().st_mtime
        except OSError:
            continue

        if item.is_dir():
            if _newest_mtime(item) > cutoff:
                continue
        elif mtime > cutoff:
            continue

        try:
            size, _ = _dir_size_and_count(item) if item.is_dir() else (item.stat().st_size, 1)
            matched += 1
            freed += size
            if len(items) < 100:
                items.append(str(item))
            if not dry_run:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                    deleted += 1
                else:
                    try:
                        item.unlink(missing_ok=True)
                        deleted += 1
                    except OSError:
                        pass
        except Exception:
            logger.exception("Failed to process cleanup item %s", item)
    return matched, deleted, freed, items


def _cleanup_old_temp_files() -> None:
    try:
        _cleanup_root(settings.temp_dir, older_than_hours=6, dry_run=False, protected=_active_workspace_dirs())
    except Exception:
        logger.exception("Automatic temp cleanup failed")
    try:
        extra = Path(settings.temp_dir.parent.parent / "appdata" / "temp")
        if extra.exists():
            _cleanup_root(extra, older_than_hours=6, dry_run=False, protected=set())
    except Exception:
        logger.exception("Cleanup appdata/temp failed")
    try:
        build_dir = Path(settings.temp_dir.parent.parent / "build")
        if build_dir.exists():
            _cleanup_root(build_dir, older_than_hours=6, dry_run=False, protected=set())
    except Exception:
        logger.exception("Cleanup build failed")
    try:
        _cleanup_root(settings.logs_dir, older_than_hours=6, dry_run=False, protected=set())
    except Exception:
        logger.exception("Cleanup logs failed")


_cleanup_task: asyncio.Task | None = None


async def _periodic_cleanup_worker() -> None:
    while True:
        await asyncio.sleep(6 * 3600)
        _cleanup_old_temp_files()


def start_cleanup_scheduler() -> None:
    global _cleanup_task
    if _cleanup_task is None:
        _cleanup_task = asyncio.create_task(_periodic_cleanup_worker())


def _run_render_job(job_id: str, payload: RenderRequest):
    try:
        from app.core.database import SessionLocal

        _raise_if_cancelled(job_id)
        _update_render_job(job_id, status="running", step="Validate EDL", message="Đang validate JSON EDL...", progress=5, completed_segments=0, total_segments=None)
        valid, errors, parsed, _ = JsonValidator().validate_with_auto_fix(payload.gemini_json, render_options=payload.render_options)
        if not valid or parsed is None:
            _update_render_job(job_id, status="error", step="Validate EDL", message="Validation Error", progress=100, errors=errors)
            return
        try:
            if payload.render_options.tts_mode == "voiceover":
                _require_license("tts")
                _require_tts_ready()
            if payload.youtube_url or any(source.youtube_url for source in (parsed.sources or [])):
                _require_license("youtube_download")
        except HTTPException as exc:
            _update_render_job(job_id, status="error", step="Preflight", message=str(exc.detail), progress=100, errors=[str(exc.detail)])
            return
        source_count = len(parsed.sources) if parsed.sources else 1
        _update_render_job(job_id, eta_plan=_build_eta_plan(parsed, payload.render_options, payload.effective_subtitle_mode, source_count))
        _update_render_job(
            job_id,
            status="running",
            step="Prepare render",
            message="Đang chuẩn bị tải video và dựng timeline...",
            progress=10,
            phase="prepare_sources",
            phase_progress=0.1,
            total_segments=len(parsed.video_segments),
            completed_segments=0,
        )
        _raise_if_cancelled(job_id)

        def progress_callback(updates: dict):
            _raise_if_cancelled(job_id)
            _update_render_job(job_id, status="running", **updates)

        with SessionLocal() as db:
            cookies_file = _effective_cookies_file(payload.ytdlp_cookies_file, db)
        pipeline = RenderPipeline(VideoDownloader(), VideoCutter(), VideoConcatenator(), SubtitleBurner())
        result = pipeline.render(
            parsed,
            payload.youtube_url,
            payload.local_video_path,
            payload.burn_subtitle,
            subtitle_mode=payload.effective_subtitle_mode,
            job_id=job_id,
            ytdlp_cookies_file=cookies_file,
            ytdlp_cookies_from_browser=payload.ytdlp_cookies_from_browser,
            user_data_dir=payload.user_data_dir,
            render_options=payload.render_options,
            progress_callback=progress_callback,
            cancel_callback=lambda: _raise_if_cancelled(job_id),
            output_dir_name=payload.output_dir_name,
            output_dir_path=payload.output_dir_path,
        )
        _raise_if_cancelled(job_id)
        if result.get("requires_blur_decision") == "True":
            result["pre_blur_preview_url"] = _blur_preview_url(Path(result["pre_blur_video_path"]))
            with render_jobs_lock:
                plan = render_jobs.get(job_id, {}).get("eta_plan")
                if plan:
                    plan["paused"] = True
                    plan["paused_started_at"] = time.time()
            _update_render_job(job_id, status="waiting_blur", step="Blur review", message="Đang chờ bạn chọn vùng blur hoặc bỏ qua blur.", progress=95, result=result, errors=[])
            return
        _cleanup_old_temp_files()
        _update_render_job(job_id, status="done", step="Export result", message="Render video thành công.", progress=100, completed_segments=len(parsed.video_segments), total_segments=len(parsed.video_segments), result=result, errors=[])
    except RenderJobCancelled:
        _update_render_job(job_id, status="cancelled", step="Cancel", message="Render job đã bị hủy.", progress=100, errors=[])
    except Exception as exc:  # noqa: BLE001
        safe = ui_safe_error(str(exc))
        _update_render_job(job_id, status="error", step="Render", message=safe, progress=100, errors=[safe])


async def _drain_render_queue():
    global render_worker_running
    with render_jobs_lock:
        if render_worker_running:
            return
        render_worker_running = True
    loop = asyncio.get_event_loop()
    try:
        while True:
            with render_jobs_lock:
                next_item = render_queue.pop(0) if render_queue else None
            if next_item is None:
                return
            job_id, payload = next_item
            if _is_cancel_requested(job_id):
                _update_render_job(job_id, status="cancelled", step="Cancel", message="Render job đã bị hủy trước khi chạy.", progress=100, errors=[])
                continue
            await loop.run_in_executor(None, _run_render_job, job_id, payload)
    finally:
        with render_jobs_lock:
            render_worker_running = False


def _finalize_blur_job(job_id: str, regions=None):
    with render_jobs_lock:
        job = render_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Render job không tồn tại.")
    if job.get("status") != "waiting_blur":
        raise HTTPException(status_code=400, detail="Render job không ở trạng thái chờ blur.")
    result = dict(job.get("result") or {})
    pre_blur_path = _safe_path_under(result.get("pre_blur_video_path", ""), settings.outputs_dir)
    final_video = _safe_path_under(result.get("final_video_path", ""), settings.outputs_dir)
    subtitle_path = _safe_path_under(result.get("final_subtitle_path", ""), settings.outputs_dir)
    render_plan_path = _safe_path_under(result.get("render_plan_path", ""), settings.outputs_dir)
    work_dir = _safe_path_under(result.get("output_dir", ""), settings.outputs_dir)
    try:
        render_plan_payload = json.loads(render_plan_path.read_text(encoding="utf-8"))
    except Exception:
        render_plan_payload = {}
    options = RenderOptions.model_validate(render_plan_payload.get("render_options") or {})
    options.video_encoder = result.get("video_encoder", "auto") if result.get("video_encoder") in {"auto", "cpu", "nvenc", "qsv", "amf"} else options.video_encoder

    try:
        with render_jobs_lock:
            plan = render_jobs.get(job_id, {}).get("eta_plan")
            if plan and plan.get("paused"):
                now = time.time()
                plan["paused_seconds"] = float(plan.get("paused_seconds") or 0) + max(0.0, now - float(plan.get("paused_started_at") or now))
                plan["paused"] = False
                plan["paused_started_at"] = None
        _update_render_job(job_id, status="running", step="Apply blur", message="Đang áp dụng blur và hoàn tất output...", progress=96)
        input_for_final = pre_blur_path
        if regions:
            blurred_intermediate = pre_blur_path.parent / f"{pre_blur_path.stem}_blurred.mp4"
            BlurService().apply_blur(pre_blur_path, blurred_intermediate, regions, options)
            input_for_final = blurred_intermediate
        tts_result = {}
        if options.tts_mode == "voiceover":
            _require_license("tts")
            _update_render_job(job_id, status="running", step="TTS voiceover", message="Đang tạo và mix voiceover Edge TTS...", progress=97)
            parsed_payload = GeminiPayloadSchema.model_validate(render_plan_payload)
            video_duration = float(probe_video_metadata(input_for_final).get("duration_seconds") or 0)
            tts_result = TtsVoiceoverService().generate_voiceover(parsed_payload, work_dir, Path(result.get("workspace_dir", work_dir)), options, video_duration)
            tts_mixed = work_dir / f"{input_for_final.stem}_tts_mixed.mp4"
            TtsVoiceoverService().mix_voiceover(input_for_final, Path(tts_result["voiceover_path"]), tts_mixed, options)
            input_for_final = tts_mixed
        title_result = {}
        parsed_payload = GeminiPayloadSchema.model_validate(render_plan_payload)
        if options.title_mode != "none":
            _update_render_job(job_id, status="running", step="Title overlay", message="Đang chèn title lên đầu video...", progress=97)
            titled_path = work_dir / f"{input_for_final.stem}_title.mp4"
            TitleOverlay().apply(input_for_final, titled_path, parsed_payload, options)
            input_for_final = titled_path
            title_result = {"title_overlay": "True", "title_text": TitleOverlay().resolve_title(parsed_payload, options), "title_style": options.title_style}
        if result.get("subtitle_mode") == "burn":
            SubtitleBurner().burn(input_for_final, subtitle_path, final_video, render_options=options)
        else:
            shutil.copy2(input_for_final, final_video)

        if options.video_speed != 1.0 and final_video.exists():
            _update_render_job(job_id, status="running", step="Speed up", message=f"Đang tăng tốc video lên {options.video_speed}x...", progress=97)
            from app.services.video_tools import _probe_has_audio, video_encoder_args, audio_encoder_args, run_ffmpeg_with_encoder_fallback, settings as vt_settings
            sped_up_tmp = work_dir / f"{final_video.stem}_spedup.mp4"
            speed = options.video_speed
            has_audio = _probe_has_audio(final_video)

            def build_blur_speed_cmd(profile: EncoderProfile) -> list[str]:
                cmd = [vt_settings.ffmpeg_binary, "-y", "-i", str(final_video.resolve()),
                       "-vf", f"setpts=PTS/{speed}"]
                if has_audio:
                    cmd += ["-af", f"atempo={speed}"]
                else:
                    cmd += ["-an"]
                return cmd + [*video_encoder_args(profile, options.render_quality),
                             *audio_encoder_args(options.render_quality),
                             "-movflags", "+faststart", str(sped_up_tmp.resolve())]

            run_ffmpeg_with_encoder_fallback(build_blur_speed_cmd, "FFmpeg speed-up thất bại", mode_override=options.video_encoder)
            final_video.unlink(missing_ok=True)
            shutil.move(str(sped_up_tmp), str(final_video))

        output_metadata = probe_video_metadata(final_video)
        keep_paths = {final_video, subtitle_path, render_plan_path}
        if tts_result.get("voiceover_path"):
            keep_paths.add(Path(tts_result["voiceover_path"]))
        if tts_result.get("tts_plan_path"):
            keep_paths.add(Path(tts_result["tts_plan_path"]))
        cleaned_artifacts = cleanup_large_intermediate_artifacts(work_dir, keep_paths, enabled=options.artifact_retention == "smart")
        render_plan_payload["cleanup"] = {"mode": options.artifact_retention, "deleted_files": cleaned_artifacts}
        render_plan_path.write_text(json.dumps(render_plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        result.update(
            requires_blur_decision="False",
            blur_applied=str(bool(regions)),
            final_video_path=str(final_video),
            artifact_retention=options.artifact_retention,
            cleaned_artifact_count=str(len(cleaned_artifacts)),
            cleaned_artifacts="\n".join(cleaned_artifacts),
            output_codec=output_metadata.get("codec", ""),
            output_fps=output_metadata.get("fps", ""),
            output_resolution_actual=output_metadata.get("resolution", ""),
            output_duration_seconds=output_metadata.get("duration_seconds", ""),
            output_file_size_bytes=str(final_video.stat().st_size if final_video.exists() else 0),
            **tts_result,
            **title_result,
        )
        _cleanup_old_temp_files()
        _update_render_job(job_id, status="done", step="Export result", message="Render video thành công.", progress=100, result=result, errors=[])
    except Exception as exc:  # noqa: BLE001
        safe = ui_safe_error(str(exc))
        _update_render_job(job_id, status="error", step="Blur/finalize", message=safe, progress=100, errors=[safe])


@router.get("/presets", response_model=list[PresetRead])
def get_presets(service: PresetService = Depends(get_preset_service)):
    service.seed_builtin_presets()
    return service.list_presets()


@router.get("/presets/sync-status")
def get_preset_sync_status(service: PresetService = Depends(get_preset_service)):
    return service.builtin_sync_status()


@router.post("/presets/sync")
def sync_builtin_presets(service: PresetService = Depends(get_preset_service)):
    return service.sync_builtin_presets()


class PresetValidateConflictsRequest(BaseModel):
    data: dict[str, object]


class PresetValidateConflictsResponse(BaseModel):
    warnings: list[dict[str, str]]


@router.post("/presets/validate-conflicts", response_model=PresetValidateConflictsResponse)
def validate_preset_conflicts_endpoint(payload: PresetValidateConflictsRequest):
    return PresetValidateConflictsResponse(warnings=validate_preset_conflicts(payload.data))


@router.get("/runtime/health")
def get_runtime_health(service: PresetService = Depends(get_preset_service)):
    try:
        encoder_status = video_encoder_diagnostics()
    except Exception as exc:  # noqa: BLE001
        encoder_status = {"error": str(exc)}
    node_binary = shutil.which("node")
    node_status = {"available": False, "path": node_binary or ""}
    if node_binary:
        try:
            node_result = subprocess.run([node_binary, "--version"], check=True, capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace")
            node_status = {"available": True, "path": node_binary, "version": node_result.stdout.strip()}
        except Exception as exc:  # noqa: BLE001
            node_status = {"available": False, "path": node_binary, "error": str(exc)}
    try:
        ytdlp_module_result = subprocess.run(
            [os.sys.executable, "-m", "yt_dlp", "--js-runtimes", settings.ytdlp_js_runtimes or "node", "--remote-components", settings.ytdlp_remote_components or "ejs:github", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        ytdlp_module_status = {
            "available": ytdlp_module_result.returncode == 0,
            "returncode": ytdlp_module_result.returncode,
            "stdout": ytdlp_module_result.stdout.strip(),
            "stderr": ytdlp_module_result.stderr.strip(),
        }
    except Exception as exc:  # noqa: BLE001
        ytdlp_module_status = {"available": False, "error": str(exc)}
    def binary_version_status(command: list[str]) -> dict:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace")
            return {
                "available": result.returncode == 0,
                "returncode": result.returncode,
                "stdout_head": "\n".join(result.stdout.strip().splitlines()[:3]),
                "stderr_head": "\n".join(result.stderr.strip().splitlines()[:3]),
            }
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "error": str(exc)}
    return {
        "pid": os.getpid(),
        "backend_started_at": RUNTIME_STARTED_AT,
        "python_executable": os.sys.executable,
        "app_version": get_local_version().get("version", "0.0.0"),
        "ytdlp_command_mode": "python_module",
        "ytdlp_module_status": ytdlp_module_status,
        "ytdlp_binary": settings.ytdlp_binary,
        "ytdlp_binary_exists": Path(settings.ytdlp_binary).exists(),
        "ytdlp_js_runtimes": settings.ytdlp_js_runtimes,
        "ytdlp_remote_components": settings.ytdlp_remote_components,
        "node_status": node_status,
        "ffmpeg_binary": settings.ffmpeg_binary,
        "ffmpeg_binary_exists": Path(settings.ffmpeg_binary).exists(),
        "ffmpeg_version_status": binary_version_status([settings.ffmpeg_binary, "-version"]),
        "ffprobe_binary": settings.ffprobe_binary,
        "ffprobe_binary_exists": Path(settings.ffprobe_binary).exists(),
        "ffprobe_version_status": binary_version_status([settings.ffprobe_binary, "-version"]),
        "tts_status": edge_tts_status(),
        "video_encoder_auto_result": encoder_status,
        "preset_sync_status": service.builtin_sync_status(),
    }


@router.get("/license/status")
def get_license_status():
    return _license_service().status().as_dict()


@router.post("/license/activate")
def activate_license(payload: LicenseActivateRequest):
    try:
        return _license_service().activate(payload.license_key).as_dict()
    except LicenseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/license/clear", response_model=MessageResponse)
def clear_license():
    _license_service().clear()
    return MessageResponse(message="Đã xóa license local.")


@router.post("/license/unbind", response_model=MessageResponse)
def unbind_license(payload: LicenseUnbindRequest):
    try:
        _license_service().unbind(payload.license_key)
    except LicenseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MessageResponse(message="Đã hủy liên kết thiết bị.")


@router.post("/presets", response_model=PresetRead)
def create_preset(payload: PresetCreate, service: PresetService = Depends(get_preset_service)):
    try:
        return service.create_preset(payload)
    except PresetConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/presets/{preset_id}", response_model=PresetRead)
def update_preset(preset_id: str, payload: PresetUpdate, service: PresetService = Depends(get_preset_service)):
    try:
        return service.update_preset(preset_id, payload)
    except PresetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PresetProtectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PresetConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/presets/{preset_id}", response_model=MessageResponse)
def delete_preset(preset_id: str, service: PresetService = Depends(get_preset_service)):
    try:
        service.delete_preset(preset_id)
        return MessageResponse(message="Xóa preset thành công.")
    except PresetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PresetProtectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/presets/compare", response_model=PresetCompareResponse)
def compare_presets_endpoint(payload: PresetCompareRequest, db: Session = Depends(get_db)):
    try:
        return compare_presets(db, payload.left_preset_id_or_name, payload.right_preset_id_or_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/generate-prompt", response_model=PromptGenerateResponse)
def generate_prompt(payload: PromptGenerateRequest, db: Session = Depends(get_db)):
    t0 = time.time()
    try:
        prompt = PromptGenerator().generate(payload)
        health = score_preset_health(payload.model_dump())
        duration_ms = (time.time() - t0) * 1000
        try:
            PromptRunService(db).record_run(PromptRunCreate(
                prompt_text=prompt,
                form_data=payload.model_dump(),
                health_score=health["score"],
                health_level=health["level"],
                status="success",
                duration_ms=duration_ms,
            ))
        except Exception:
            logger.warning("Telemetry recording failed (non-fatal)", exc_info=True)
        return PromptGenerateResponse(prompt=prompt)
    except Exception as e:
        duration_ms = (time.time() - t0) * 1000
        try:
            PromptRunService(db).record_run(PromptRunCreate(
                prompt_text="",
                form_data=payload.model_dump(),
                status="error",
                error_message=str(e),
                duration_ms=duration_ms,
            ))
        except Exception:
            logger.warning("Telemetry error recording failed (non-fatal)", exc_info=True)
        raise


@router.post("/prompt/health-score", response_model=PromptHealthResponse)
def prompt_health_score(payload: PromptGenerateRequest):
    return PromptHealthResponse(**score_preset_health(payload.model_dump()))


@router.post("/prompt/preview", response_model=PromptPreviewResponse)
def prompt_preview(payload: PromptPreviewRequest):
    service = PromptPreviewService()
    return service.preview(payload)


@router.post("/prompt/recommend", response_model=PresetRecommendResponse)
def recommend_preset(payload: PresetRecommendRequest):
    recommender = PresetRecommender()
    return recommender.recommend(
        video_title=payload.video_title,
        youtube_url=payload.youtube_url,
    )


@router.post("/prompt/runs", response_model=PromptRunRead)
def create_prompt_run(payload: PromptRunCreate, db: Session = Depends(get_db)):
    service = PromptRunService(db)
    result = service.record_run(payload)
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to record prompt run")
    return result


@router.get("/prompt/runs/stats", response_model=PromptRunStats)
def get_prompt_run_stats(since: float | None = None, db: Session = Depends(get_db)):
    service = PromptRunService(db)
    return service.get_stats(since=since)


@router.post("/validate-json", response_model=ValidateJsonResponse)
def validate_json(payload: ValidateJsonRequest):
    validator = JsonValidator()
    valid, errors, _, fixed_payload = validator.validate_with_auto_fix(payload.payload)
    warnings = [error for error in errors if error.startswith("AUTO FIX")]
    warnings.extend(validator.alignment_warnings(fixed_payload or payload.payload))
    visible_errors = [] if valid else errors
    return ValidateJsonResponse(valid=valid, errors=visible_errors, warnings=warnings, fixed_payload=fixed_payload if warnings else None)


def _strict_gemini_validate(data: object) -> tuple[bool, list[str]]:
    """Validate Gemini payload rejecting extra fields via Pydantic extra=forbid."""
    import pydantic

    class StrictGemini(GeminiPayloadSchema):
        model_config = {"extra": "forbid"}

    try:
        StrictGemini.model_validate(data)
        return True, []
    except Exception as e:
        return False, [str(e)]


@router.post("/validate-json/strict", response_model=ValidateJsonResponse)
def validate_json_strict(payload: ValidateJsonRequest):
    """Strict validation: rejects extra fields not in the schema."""
    valid, errors = _strict_gemini_validate(payload.payload)
    return ValidateJsonResponse(valid=valid, errors=errors)


@router.post("/upload-cookies", response_model=UploadCookiesResponse)
async def upload_cookies(file: UploadFile = File(...), db=Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ upload file cookies.txt.")
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File cookies.txt vượt quá 2MB.")
    cookies_dir = _saved_cookies_path().parent
    cookies_dir.mkdir(parents=True, exist_ok=True)
    output_path = _saved_cookies_path()
    output_path.write_bytes(content)
    health = analyze_ytdlp_cookie_file(output_path)
    if not health.valid:
        raise HTTPException(status_code=400, detail="; ".join(health.errors))
    health_meta = {"valid": health.valid, "total_cookies": health.total_cookies, "youtube_cookies": health.youtube_cookies, "auth_cookies": health.auth_cookies, "expired_cookies": health.expired_cookies}
    AppSettingsService(db).set(SAVED_COOKIES_KEY, {"cookies_file_path": str(output_path), "uploaded_at": time.time(), "file_size": len(content), "cookie_health": health_meta})
    msg = "Upload cookies.txt thành công."
    if health.warnings:
        msg += " Cảnh báo: " + "; ".join(health.warnings)
    return UploadCookiesResponse(message=msg, cookies_file_path=str(output_path))


@router.post("/blur/upload-video", response_model=BlurUploadResponse)
async def upload_blur_video(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_BLUR_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ video .mp4, .mov, .mkv, .webm.")
    upload_dir = _blur_uploads_dir() / uuid.uuid4().hex
    upload_dir.mkdir(parents=True, exist_ok=True)
    output_path = upload_dir / f"input{suffix}"
    size = 0
    with output_path.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > 2 * 1024 * 1024 * 1024:
                output_path.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="Video upload vượt quá 2GB.")
            handle.write(chunk)
    try:
        fast_path = upload_dir / "input_faststart.mp4"
        subprocess.run(
            [settings.ffmpeg_binary, "-y", "-i", str(output_path),
             "-c", "copy", "-movflags", "+faststart",
             str(fast_path)],
            check=True, capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        output_path.unlink(missing_ok=True)
        fast_path.rename(output_path)
    except Exception:
        pass
    metadata = probe_video_metadata(output_path)
    width = height = None
    if metadata.get("resolution"):
        try:
            width_text, height_text = metadata["resolution"].split("x")
            width, height = int(width_text), int(height_text)
        except ValueError:
            pass
    return BlurUploadResponse(message="Upload video thành công.", video_path=str(output_path), preview_url=_blur_preview_url(output_path), width=width, height=height, duration_seconds=metadata.get("duration_seconds"))


@router.get("/blur/preview")
def preview_blur_video(path: str = Query(...)):
    file_path = _safe_path_under_any(path, [_blur_uploads_dir(), settings.outputs_dir])
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Video không tồn tại.")
    return FileResponse(file_path)


@router.post("/blur/render", response_model=BlurRenderResponse)
def render_blur_video(payload: BlurRenderRequest):
    _require_license("blur")
    video_path = _safe_path_under(payload.video_path, _blur_uploads_dir())
    output_path = BlurService().output_path_for(video_path)
    final_path, metadata = BlurService().apply_blur(video_path, output_path, payload.regions)
    return BlurRenderResponse(
        message="Blur video thành công.",
        final_video_path=str(final_path),
        output_dir=str(final_path.parent),
        video_encoder=metadata.get("video_encoder"),
        video_encoder_label=metadata.get("video_encoder_label"),
        video_encoder_codec=metadata.get("video_encoder_codec"),
        output_codec=metadata.get("codec", ""),
        output_fps=metadata.get("fps", ""),
        output_resolution_actual=metadata.get("resolution", ""),
        output_duration_seconds=metadata.get("duration_seconds", ""),
        output_file_size_bytes=str(final_path.stat().st_size if final_path.exists() else 0),
    )


@router.post("/render", response_model=RenderResponse)
def render_video(payload: RenderRequest, db=Depends(get_db)):
    _require_license("render")
    valid, errors, parsed, _ = JsonValidator().validate_with_auto_fix(payload.gemini_json, render_options=payload.render_options)
    if not valid or parsed is None:
        raise HTTPException(status_code=400, detail=errors)
    if payload.render_options.tts_mode == "voiceover":
        _require_license("tts")
    if payload.youtube_url or any(source.youtube_url for source in (parsed.sources or [])):
        _require_license("youtube_download")
    pipeline = RenderPipeline(VideoDownloader(), VideoCutter(), VideoConcatenator(), SubtitleBurner())
    result = pipeline.render(
        parsed,
        payload.youtube_url,
        payload.local_video_path,
        payload.burn_subtitle,
        subtitle_mode=payload.effective_subtitle_mode,
        ytdlp_cookies_file=_effective_cookies_file(payload.ytdlp_cookies_file, db),
        ytdlp_cookies_from_browser=payload.ytdlp_cookies_from_browser,
        user_data_dir=payload.user_data_dir,
        render_options=payload.render_options,
        output_dir_name=payload.output_dir_name,
        output_dir_path=payload.output_dir_path,
    )
    return RenderResponse(message="Render video thành công.", **result)


@router.get("/app-settings/cookies", response_model=SavedCookiesResponse)
def get_saved_cookies(db=Depends(get_db)):
    metadata = _saved_cookies_metadata(db)
    if not metadata:
        return SavedCookiesResponse(available=False)
    return SavedCookiesResponse(available=True, **metadata)


@router.delete("/app-settings/cookies", response_model=MessageResponse)
def delete_saved_cookies(db=Depends(get_db)):
    metadata = _saved_cookies_metadata(db)
    if metadata and metadata.get("cookies_file_path"):
        Path(metadata["cookies_file_path"]).unlink(missing_ok=True)
    AppSettingsService(db).delete(SAVED_COOKIES_KEY)
    return MessageResponse(message="Đã xóa cookies đã lưu.")


@router.get("/app-settings/render-preferences", response_model=RenderPreferencesResponse)
def get_render_preferences(db=Depends(get_db)):
    value = AppSettingsService(db).get(RENDER_PREFERENCES_KEY)
    if not value:
        return RenderPreferencesResponse()
    return RenderPreferencesResponse(**value)


@router.put("/app-settings/render-preferences", response_model=RenderPreferencesResponse)
def save_render_preferences(payload: RenderPreferencesRequest, db=Depends(get_db)):
    value = payload.model_dump()
    value["updated_at"] = time.time()
    AppSettingsService(db).set(RENDER_PREFERENCES_KEY, value)
    return RenderPreferencesResponse(**value)


@router.get("/tts/status")
def get_tts_status():
    return edge_tts_status()


@router.get("/tts/voices")
def get_tts_voices():
    return {"engine": "edge_tts", "voices": list_edge_tts_voices()}


@router.post("/tts/voices/{voice_id}/preview", response_model=TtsVoicePreviewResponse)
def preview_tts_voice(voice_id: str, payload: TtsVoicePreviewRequest):
    _require_license("tts")
    try:
        path = preview_builtin_voice(voice_id, payload.text, RenderOptions())
        return TtsVoicePreviewResponse(message="Tạo preview voice thành công.", preview_audio_path=str(path))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/tts/clones")
def get_tts_clones():
    return {"voices": list_cloned_voices()}


@router.post("/tts/clone/upload", response_model=TtsCloneUploadResponse)
async def upload_tts_clone(file: UploadFile = File(...), name: str = "Cloned voice"):
    _require_license("voice_clone")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_TTS_REF_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ audio .wav, .mp3, .m4a, .aac, .flac, .ogg.")
    upload_dir = settings.temp_dir / "tts_clone_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    temp_path = upload_dir / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    with temp_path.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > 50 * 1024 * 1024:
                temp_path.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="Reference audio vượt quá 50MB.")
            handle.write(chunk)
    try:
        voice = create_clone_voice(name, temp_path)
        return TtsCloneUploadResponse(message="Clone giọng thành công.", voice=voice)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)


@router.post("/tts/clones/{clone_id}/preview", response_model=TtsClonePreviewResponse)
def preview_tts_clone(clone_id: str, payload: TtsClonePreviewRequest):
    _require_license("voice_clone")
    try:
        path = preview_clone_voice(clone_id, payload.text, payload.render_options)
        return TtsClonePreviewResponse(message="Tạo preview clone voice thành công.", preview_audio_path=str(path))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/tts/clones/{clone_id}", response_model=MessageResponse)
def delete_tts_clone(clone_id: str):
    clone_path = _safe_path_under(str(tts_clones_dir() / clone_id), tts_clones_dir())
    if not clone_path.exists():
        raise HTTPException(status_code=404, detail="Clone voice không tồn tại.")
    shutil.rmtree(clone_path, ignore_errors=True)
    return MessageResponse(message="Đã xóa cloned voice.")


@router.get("/tts/audio")
def get_tts_audio(path: str = Query(...), download: bool = Query(False)):
    file_path = _safe_path_under_any(path, [tts_clones_dir(), settings.temp_dir / "tts_voice_previews", tts_studio_outputs_dir()])
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Audio không tồn tại.")
    if download:
        return FileResponse(file_path, filename=file_path.name, media_type="application/octet-stream")
    return FileResponse(file_path)


@router.get("/tts/prebuilt-preview/{voice_id}")
def serve_prebuilt_preview(voice_id: str):
    safe_ids = {voice["id"] for voice in list_edge_tts_voices()}
    if voice_id not in safe_ids:
        raise HTTPException(status_code=404, detail="Voice không tồn tại.")
    file_path = TTS_PREVIEWS_DIR / f"preview_{voice_id}.wav"
    if not file_path.is_file():
        file_path = preview_builtin_voice(voice_id, "Xin chào, đây là giọng đọc thử từ Edge TTS.", RenderOptions())
    return FileResponse(file_path, media_type="audio/wav")


@router.post("/tts/generate", response_model=TtsGenerateResponse)
def generate_tts_audio(payload: TtsGenerateRequest):
    _require_tts_ready()
    try:
        path = generate_standalone_tts(payload.voice_id, payload.text, payload.format)
        return TtsGenerateResponse(
            message="Tạo audio TTS thành công.",
            audio_path=str(path),
            audio_url=f"/api/tts/audio?path={quote(str(path))}",
            filename=path.name,
            output_dir=str(path.parent),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/render-jobs", response_model=RenderJobStartResponse)
async def start_render_job(payload: RenderRequest):
    _require_license("render")
    _cleanup_render_jobs()
    job_id = str(uuid.uuid4())
    with render_jobs_lock:
        render_jobs[job_id] = {
            "status": "queued",
            "step": "Render request",
            "message": "Đã nhận yêu cầu render, đang xếp hàng...",
            "progress": 0,
            "total_segments": None,
            "completed_segments": 0,
            "result": None,
            "errors": [],
            "cancel_requested": False,
            "started_at": time.time(),
            "updated_at": time.time(),
        }
        render_queue.append((job_id, payload))
    asyncio.create_task(_drain_render_queue())
    return RenderJobStartResponse(job_id=job_id, status="queued", message="Đã bắt đầu render job.")


@router.get("/render-jobs", response_model=list[RenderJobStatusResponse])
def list_render_jobs():
    _cleanup_render_jobs()
    with render_jobs_lock:
        items = list(render_jobs.items())
    items.sort(key=lambda item: item[1].get("started_at", 0), reverse=True)
    result = []
    for job_id, job in items:
        safe_job = dict(job)
        safe_job["message"] = ui_safe_error(job.get("message", ""))
        safe_job["errors"] = [ui_safe_error(e) for e in job.get("errors", [])]
        result.append(RenderJobStatusResponse(job_id=job_id, **_with_render_job_eta(safe_job)))
    return result


@router.get("/render-jobs/{job_id}", response_model=RenderJobStatusResponse)
def get_render_job(job_id: str):
    _cleanup_render_jobs()
    with render_jobs_lock:
        job = render_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Render job không tồn tại.")
    safe_job = dict(job)
    safe_job["message"] = ui_safe_error(job.get("message", ""))
    safe_job["errors"] = [ui_safe_error(e) for e in job.get("errors", [])]
    return RenderJobStatusResponse(job_id=job_id, **_with_render_job_eta(safe_job))


@router.post("/render-jobs/{job_id}/cancel", response_model=MessageResponse)
def cancel_render_job(job_id: str):
    with render_jobs_lock:
        job = render_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Render job không tồn tại.")
        if job.get("status") in {"done", "error", "cancelled"}:
            return MessageResponse(message="Render job đã kết thúc, không cần hủy.")
        job["cancel_requested"] = True
        job["updated_at"] = time.time()
        if job.get("status") == "queued":
            job.update(status="cancelled", step="Cancel", message="Render job đã bị hủy trước khi chạy.", progress=100, errors=[])
    return MessageResponse(message="Đã gửi yêu cầu hủy render job.")


@router.post("/render-jobs/{job_id}/blur/skip", response_model=MessageResponse)
def skip_render_job_blur(job_id: str, background_tasks: BackgroundTasks):
    _require_license("blur")
    background_tasks.add_task(_finalize_blur_job, job_id, [])
    return MessageResponse(message="Đã bỏ qua blur và tiếp tục xuất final.")


@router.post("/render-jobs/{job_id}/blur/apply", response_model=MessageResponse)
def apply_render_job_blur(job_id: str, payload: BlurDecisionRequest, background_tasks: BackgroundTasks):
    _require_license("blur")
    if not payload.regions:
        raise HTTPException(status_code=400, detail="Cần ít nhất một vùng blur hoặc chọn bỏ qua blur.")
    background_tasks.add_task(_finalize_blur_job, job_id, payload.regions)
    return MessageResponse(message="Đã áp dụng blur và tiếp tục xuất final.")


@router.get("/storage/stats", response_model=StorageStatsResponse)
def storage_stats():
    outputs_size, outputs_count = _dir_size_and_count(settings.outputs_dir)
    temp_size, temp_count = _dir_size_and_count(settings.temp_dir)
    return StorageStatsResponse(outputs_size_bytes=outputs_size, temp_size_bytes=temp_size, outputs_count=outputs_count, temp_count=temp_count)


@router.post("/storage/cleanup", response_model=StorageCleanupResponse)
def storage_cleanup(payload: StorageCleanupRequest):
    try:
        protected = _active_workspace_dirs()
        protected.add(final_videos_dir().resolve())
        roots = []
        if payload.target in {"temp", "all"}:
            roots.append(settings.temp_dir)
        if payload.target in {"outputs", "all"}:
            roots.append(settings.outputs_dir)
        if payload.target == "all":
            extra = Path(settings.temp_dir.parent.parent / "appdata" / "temp")
            if extra.exists():
                roots.append(extra)
            build_dir = Path(settings.temp_dir.parent.parent / "build")
            if build_dir.exists():
                roots.append(build_dir)
            roots.append(settings.logs_dir)
        matched = deleted = freed = 0
        items: list[str] = []
        for root in roots:
            try:
                root_matched, root_deleted, root_freed, root_items = _cleanup_root(root, payload.older_than_hours, payload.dry_run, protected)
                matched += root_matched
                deleted += root_deleted
                freed += root_freed
                items.extend(root_items[: max(0, 100 - len(items))])
            except Exception:
                logger.exception("Cleanup failed for %s", root)
        return StorageCleanupResponse(target=payload.target, dry_run=payload.dry_run, matched_count=matched, deleted_count=deleted, freed_bytes=freed, items=items)
    except Exception:
        logger.exception("Storage cleanup failed")
        return StorageCleanupResponse(target=payload.target, dry_run=payload.dry_run, matched_count=0, deleted_count=0, freed_bytes=0, items=[])


@router.post("/storage/cleanup-final-videos", response_model=StorageCleanupResponse)
def storage_cleanup_final_videos(payload: StorageCleanupRequest):
    target_dir = final_videos_dir()
    matched, deleted, freed, items = _cleanup_root(target_dir, payload.older_than_hours, payload.dry_run, protected=set())
    return StorageCleanupResponse(target="outputs", dry_run=payload.dry_run, matched_count=matched, deleted_count=deleted, freed_bytes=freed, items=items)


@router.post("/open-folder", response_model=MessageResponse)
def open_folder(payload: OpenFolderRequest):
    try:
        path = _safe_path_under(payload.path, settings.outputs_dir)
    except HTTPException:
        path = _safe_custom_path(payload.path)
        if not path:
            raise HTTPException(status_code=403, detail="Đường dẫn nằm ngoài thư mục cho phép.")
    folder = path if path.is_dir() else path.parent
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Thư mục không tồn tại.")
    os.startfile(str(folder))  # type: ignore[attr-defined]
    return MessageResponse(message="Đã mở thư mục output.")


@router.get("/outputs/final-videos-path", response_model=dict)
def get_outputs_final_videos_path():
    path = final_videos_dir()
    path.mkdir(parents=True, exist_ok=True)
    return {"path": str(path)}


@router.get("/files/download")
def download_file(path: str = Query(...)):
    try:
        file_path = _safe_path_under(path, settings.outputs_dir)
    except HTTPException:
        file_path = _safe_custom_path(path)
        if not file_path:
            raise HTTPException(status_code=403, detail="Đường dẫn nằm ngoài thư mục cho phép.")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File không tồn tại.")
    return FileResponse(file_path, filename=file_path.name)


@router.post("/subtitle/preview-style", response_model=SubtitlePreviewStyleResponse)
def subtitle_preview_style(request: SubtitlePreviewStyleRequest):
    return compute_preview(request)


@router.post("/title/layout-preview", response_model=TitleLayoutPreviewResponse)
def get_title_layout_preview(request: TitleLayoutPreviewRequest):
    preview = compute_title_preview(
        request.render_options,
        request.video_width,
        request.video_height,
        request.metadata,
    )
    return TitleLayoutPreviewResponse(**preview)


@router.get("/update/check")
def check_update():
    try:
        local = get_local_version()
        remote = get_remote_manifest()
        return compare_versions(local, remote)
    except UpdaterError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in /update/check")
        raise HTTPException(status_code=500, detail="Lỗi không mong đợi khi kiểm tra cập nhật.")


@router.post("/update/launch")
def launch_update():
    try:
        return launch_updater(from_ui=True, restart_after_update=True)
    except UpdaterError as exc:
        detail = str(exc)
        if "không tìm thấy" in detail.lower():
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=503, detail=detail)
    except Exception as exc:
        logger.exception("Unexpected error in /update/launch")
        raise HTTPException(status_code=500, detail="Lỗi không mong đợi khi mở trình cập nhật.")


async def _submit_render_from_automation(render_payload: dict, task_id: str | None = None) -> str:
    import uuid as _uuid
    import time as _time

    if task_id:
        t = gemini_service.get_task(task_id)
        if t is None or t.status != "running":
            raise RuntimeError(f"Task {task_id} is not running (status={t.status if t else 'not found'}), refusing to submit render job.")

    render_req = RenderRequest.model_validate(render_payload)

    if task_id:
        t = gemini_service.get_task(task_id)
        if t is None or t.status != "running":
            raise RuntimeError(f"Task {task_id} stopped before render enqueue (status={t.status if t else 'not found'}).")

    job_id = str(_uuid.uuid4())
    with render_jobs_lock:
        render_jobs[job_id] = {
            "status": "queued",
            "step": "Auto pipeline render",
            "message": "Đã nhận yêu cầu render từ auto pipeline...",
            "progress": 0,
            "total_segments": None,
            "completed_segments": 0,
            "result": None,
            "errors": [],
            "cancel_requested": False,
            "started_at": _time.time(),
            "updated_at": _time.time(),
        }
    with render_jobs_lock:
        render_queue.append((job_id, render_req))
    asyncio.create_task(_drain_render_queue())
    return job_id


def _cancel_render_job_immediately(job_id: str) -> None:
    with render_jobs_lock:
        job = render_jobs.get(job_id)
        if job is None:
            return
        job["cancel_requested"] = True
        if job.get("status") in {"queued", "running"}:
            job["status"] = "cancelled"
            job["step"] = "Cancel"
            job["message"] = "Render job đã bị hủy do auto pipeline lỗi."
            job["progress"] = 100
            job["updated_at"] = time.time()


gemini_service.set_submit_render_fn(_submit_render_from_automation)
gemini_service.set_cancel_render_fn(_cancel_render_job_immediately)


def _get_render_status_for_batch(job_id: str) -> dict | None:
    with render_jobs_lock:
        job = render_jobs.get(job_id)
        if job is None:
            return None
        return _with_render_job_eta(dict(job))


batch_service.set_render_status_getter(_get_render_status_for_batch)
batch_service.set_cancel_render_fn(_cancel_render_job_immediately)


@router.post("/gemini/auto-submit", response_model=GeminiAutoSubmitResponse)
async def gemini_auto_submit(payload: GeminiAutoSubmitRequest):
    form_data = payload.form_data
    from app.schemas.prompt import PromptGenerateRequest

    try:
        prompt_req = PromptGenerateRequest.model_validate(form_data)
        prompt = PromptGenerator().generate(prompt_req)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Không thể tạo prompt: {exc}")

    if payload.render_options.get("tts_mode") == "voiceover" and not payload.gemini_dry_run:
        _require_tts_ready()

    from app.core.database import SessionLocal
    with SessionLocal() as db:
        cookies_file = _effective_cookies_file(payload.ytdlp_cookies_file, db)

    youtube_url = form_data.get("youtube_url")
    if youtube_url:
        duration = _get_youtube_duration_seconds(
            youtube_url,
            cookies_file=cookies_file,
            cookies_from_browser=payload.ytdlp_cookies_from_browser,
            user_data_dir=payload.user_data_dir,
        )
        max_duration = settings.gemini_max_video_duration_seconds
        if duration is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "video_duration_unknown",
                    "message": 'Không lấy được thời lượng video. YouTube có thể đang yêu cầu xác minh cookie/profile. Hãy bấm "Mở trình duyệt Gemini", đăng nhập YouTube/Gemini nếu cần, đóng trình duyệt rồi chạy lại.',
                    "max_duration_seconds": max_duration,
                },
            )
        if duration > max_duration:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "video_duration_exceeds_gemini_limit",
                    "duration_seconds": duration,
                    "max_duration_seconds": max_duration,
                    "message": f"Video dài hơn {max_duration // 60} phút, không chạy Gemini để tránh timeout.",
                },
            )

    task_id = str(uuid.uuid4())
    render_payload = {
        "youtube_url": youtube_url,
        "local_video_path": payload.local_video_path,
        "ytdlp_cookies_file": cookies_file,
        "ytdlp_cookies_from_browser": payload.ytdlp_cookies_from_browser,
        "user_data_dir": payload.user_data_dir,
        "burn_subtitle": payload.subtitle_mode == "burn",
        "subtitle_mode": payload.subtitle_mode,
        "render_options": payload.render_options,
        "gemini_json": {},
        "output_dir_name": form_data.get("output_dir_name") or payload.output_dir_name,
        "output_dir_path": form_data.get("output_dir_path") or payload.output_dir_path,
    }

    gemini_service.start(task_id, prompt, render_payload, payload.user_data_dir, headless=payload.headless,
                         thinking_mode=payload.gemini_thinking_mode,
                         analysis_mode=payload.gemini_analysis_mode,
                         form_data=form_data,
                         dry_run=payload.gemini_dry_run)
    return GeminiAutoSubmitResponse(task_id=task_id, prompt_text=prompt)


@router.post("/gemini/batch-auto-submit", response_model=BatchAutoSubmitResponse)
async def gemini_batch_auto_submit(payload: GeminiAutoSubmitRequest):
    if payload.render_options.get("tts_mode") == "voiceover":
        _require_tts_ready()

    from app.core.database import SessionLocal
    with SessionLocal() as db:
        cookies_file = _effective_cookies_file(payload.ytdlp_cookies_file, db)

    raw_urls = payload.form_data.get("youtube_urls") or []
    batch_urls = [str(u).strip() for u in raw_urls if str(u).strip()]
    if not batch_urls and payload.form_data.get("youtube_url"):
        batch_urls = [str(payload.form_data["youtube_url"]).strip()]
    max_duration = settings.gemini_max_video_duration_seconds
    for url in batch_urls:
        duration = _get_youtube_duration_seconds(
            url,
            cookies_file=cookies_file,
            cookies_from_browser=payload.ytdlp_cookies_from_browser,
            user_data_dir=payload.user_data_dir,
        )
        if duration is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "video_duration_unknown",
                    "url": url,
                    "message": f'Không lấy được thời lượng video, bỏ qua: {url}. YouTube có thể đang yêu cầu xác minh cookie/profile. Hãy bấm "Mở trình duyệt Gemini", đăng nhập YouTube/Gemini nếu cần, đóng trình duyệt rồi chạy lại.',
                    "max_duration_seconds": max_duration,
                },
            )
        if duration > max_duration:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "video_duration_exceeds_gemini_limit",
                    "url": url,
                    "duration_seconds": duration,
                    "max_duration_seconds": max_duration,
                    "message": f"Video {url} dài {duration // 60} phút, vượt giới hạn {max_duration // 60} phút.",
                },
            )

    try:
        batch = batch_service.start(
            form_data=payload.form_data,
            render_options=payload.render_options,
            subtitle_mode=payload.subtitle_mode,
            ytdlp_cookies_file=cookies_file,
            ytdlp_cookies_from_browser=payload.ytdlp_cookies_from_browser,
            local_video_path=payload.local_video_path,
            user_data_dir=payload.user_data_dir,
            headless=payload.headless,
            gemini_thinking_mode=payload.gemini_thinking_mode,
            gemini_analysis_mode=payload.gemini_analysis_mode,
        )
        return BatchAutoSubmitResponse(**batch.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/gemini/batch/{batch_id}", response_model=BatchProgress)
def gemini_batch_progress(batch_id: str):
    batch = batch_service.get(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch không tồn tại.")
    return batch


@router.post("/gemini/batch/{batch_id}/cancel", response_model=MessageResponse)
def gemini_batch_cancel(batch_id: str):
    ok = batch_service.cancel(batch_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Batch không tồn tại hoặc đã kết thúc.")
    return MessageResponse(message="Đã gửi yêu cầu hủy batch.")


@router.post("/gemini/auto-submit/cancel/{task_id}")
def gemini_auto_submit_cancel(task_id: str):
    ok = gemini_service.cancel(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task không tồn tại hoặc đã kết thúc.")
    return {"message": "Đã gửi yêu cầu hủy auto pipeline."}


class OpenBrowserRequest(BaseModel):
    user_data_dir: str | None = None


@router.post("/gemini/open-browser")
async def gemini_open_browser(payload: OpenBrowserRequest | None = None):
    try:
        ud_dir = payload.user_data_dir if payload else None
        browser_id = await gemini_service.open_standalone_browser(ud_dir)
        resolved_user_data_dir = ud_dir or str(settings.gemini_profile_path)
        msg = (
            "Đang mở Chromium với Chrome profile thật. Bạn đã đăng nhập Google sẵn, hãy đóng trình duyệt sau khi load xong."
            if ud_dir
            else "Đã mở trình duyệt Chromium. Sau khi đăng nhập Gemini, hãy đóng trình duyệt, session sẽ được tự động lưu."
        )
        return {"browser_id": browser_id, "message": msg, "user_data_dir": resolved_user_data_dir}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Không thể mở trình duyệt: {exc}")


@router.get("/gemini/session-status")
def gemini_session_status():
    return gemini_service.get_session_status()


@router.get("/gemini/status/{task_id}")
def gemini_status_http(task_id: str):
    task = gemini_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task không tồn tại.")
    return task.to_dict()


@router.websocket("/gemini/status/{task_id}")
async def gemini_status_ws(websocket: WebSocket, task_id: str):
    from fastapi.websockets import WebSocket, WebSocketDisconnect

    await websocket.accept()
    task = gemini_service.get_task(task_id)
    if not task:
        await websocket.send_json({"error": "Task không tồn tại."})
        await websocket.close()
        return

    try:
        while True:
            data = task.to_dict()
            logger.debug("WS send: step=%s status=%s", data.get("step"), data.get("status"))
            await websocket.send_json(data)
            if data["status"] in ("done", "error"):
                break

            try:
                await task.wait_for_update(timeout=5.0)
            except (Exception, asyncio.CancelledError):
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
