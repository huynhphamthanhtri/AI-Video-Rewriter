from __future__ import annotations

import logging
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

from app.api.deps import get_preset_service
from app.core.config import settings
from app.core.database import get_db
from app.schemas.common import MessageResponse, UploadCookiesResponse
from app.schemas.preset import PresetCompareRequest, PresetCompareResponse, PresetCreate, PresetRead, PresetUpdate
from app.services.preset_service import validate_preset_conflicts
from app.schemas.prompt import PromptGenerateRequest, PromptGenerateResponse, PromptHealthResponse, PromptPreviewRequest, PromptPreviewResponse, PresetRecommendRequest, PresetRecommendResponse, PromptRunCreate, PromptRunRead, PromptRunStats
from app.services.prompt_telemetry import PromptRunService
from app.schemas.render import BlurDecisionRequest, BlurRenderRequest, BlurRenderResponse, BlurUploadResponse, GeminiPayloadSchema, OpenFolderRequest, RenderJobStartResponse, RenderJobStatusResponse, RenderOptions, RenderPreferencesRequest, RenderPreferencesResponse, RenderRequest, RenderResponse, SavedCookiesResponse, StorageCleanupRequest, StorageCleanupResponse, StorageStatsResponse, TitleLayoutPreviewRequest, TitleLayoutPreviewResponse, TtsClonePreviewRequest, TtsClonePreviewResponse, TtsCloneUploadResponse, TtsVoicePreviewRequest, TtsVoicePreviewResponse, ValidateJsonRequest, ValidateJsonResponse
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
from app.services.video_tools import RenderPipeline, SubtitleBurner, TitleOverlay, VideoCutter, VideoConcatenator, VideoDownloader, cleanup_large_intermediate_artifacts, probe_video_metadata, select_video_encoder
from app.services.tts_tools import TtsVoiceoverService, create_clone_voice, list_cloned_voices, list_vieneu_turbo_voices, preview_builtin_voice, preview_clone_voice, tts_clones_dir, vieneu_tts_status
from app.services.license_service import LicenseError, LicenseService
from app.services.updater_service import UpdaterError, compare_versions, get_local_version, get_remote_manifest, launch_updater
from app.services.gemini_automation import gemini_service, GeminiAutomationService
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


def _license_service() -> LicenseService:
    return LicenseService()


def _require_license(feature: str) -> None:
    try:
        _license_service().require_feature(feature)
    except LicenseError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


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


def _cleanup_root(root: Path, older_than_hours: int, dry_run: bool, protected: set[Path]) -> tuple[int, int, int, list[str]]:
    if not root.exists():
        return 0, 0, 0, []
    cutoff = time.time() - (older_than_hours * 3600)
    matched = 0
    deleted = 0
    freed = 0
    items: list[str] = []
    for item in root.iterdir():
        item_path = item.resolve()
        if item_path in protected:
            continue
        try:
            mtime = item.stat().st_mtime
        except OSError:
            continue
        if mtime > cutoff:
            continue
        size, _ = _dir_size_and_count(item) if item.is_dir() else (item.stat().st_size, 1)
        matched += 1
        freed += size
        if len(items) < 100:
            items.append(str(item))
        if not dry_run:
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)
            deleted += 1
    return matched, deleted, freed, items


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
            if payload.youtube_url or any(source.youtube_url for source in (parsed.sources or [])):
                _require_license("youtube_download")
        except HTTPException as exc:
            _update_render_job(job_id, status="error", step="License", message=str(exc.detail), progress=100, errors=[str(exc.detail)])
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
            render_options=payload.render_options,
            progress_callback=progress_callback,
            cancel_callback=lambda: _raise_if_cancelled(job_id),
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
        _update_render_job(job_id, status="done", step="Export result", message="Render video thành công.", progress=100, completed_segments=len(parsed.video_segments), total_segments=len(parsed.video_segments), result=result, errors=[])
    except RenderJobCancelled:
        _update_render_job(job_id, status="cancelled", step="Cancel", message="Render job đã bị hủy.", progress=100, errors=[])
    except Exception as exc:  # noqa: BLE001
        _update_render_job(job_id, status="error", step="Render", message=str(exc), progress=100, errors=[str(exc)])


def _drain_render_queue():
    global render_worker_running
    with render_jobs_lock:
        if render_worker_running:
            return
        render_worker_running = True
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
            _run_render_job(job_id, payload)
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
            _update_render_job(job_id, status="running", step="TTS voiceover", message="Đang tạo và mix voiceover VieNeu Turbo...", progress=97)
            parsed_payload = GeminiPayloadSchema.model_validate(render_plan_payload)
            video_duration = float(probe_video_metadata(input_for_final).get("duration_seconds") or 0)
            tts_result = TtsVoiceoverService().generate_voiceover(parsed_payload, final_video.parent, Path(result.get("workspace_dir", final_video.parent)), options, video_duration)
            tts_mixed = final_video.parent / f"{input_for_final.stem}_tts_mixed.mp4"
            TtsVoiceoverService().mix_voiceover(input_for_final, Path(tts_result["voiceover_path"]), tts_mixed, options)
            input_for_final = tts_mixed
        title_result = {}
        parsed_payload = GeminiPayloadSchema.model_validate(render_plan_payload)
        if options.title_mode != "none":
            _update_render_job(job_id, status="running", step="Title overlay", message="Đang chèn title lên đầu video...", progress=97)
            titled_path = final_video.parent / f"{input_for_final.stem}_title.mp4"
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
            sped_up_tmp = final_video.parent / f"{final_video.stem}_spedup.mp4"
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
        cleaned_artifacts = cleanup_large_intermediate_artifacts(final_video.parent, keep_paths, enabled=options.artifact_retention == "smart")
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
        _update_render_job(job_id, status="done", step="Export result", message="Render video thành công.", progress=100, result=result, errors=[])
    except Exception as exc:  # noqa: BLE001
        _update_render_job(job_id, status="error", step="Blur/finalize", message=str(exc), progress=100, errors=[str(exc)])


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
        encoder = select_video_encoder("auto")
        encoder_status = {"selected": encoder.name, "label": encoder.label, "codec": encoder.codec, "hardware": encoder.hardware}
    except Exception as exc:  # noqa: BLE001
        encoder_status = {"error": str(exc)}
    node_binary = shutil.which("node")
    node_status = {"available": False, "path": node_binary or ""}
    if node_binary:
        try:
            node_result = subprocess.run([node_binary, "--version"], check=True, capture_output=True, text=True, timeout=10)
            node_status = {"available": True, "path": node_binary, "version": node_result.stdout.strip()}
        except Exception as exc:  # noqa: BLE001
            node_status = {"available": False, "path": node_binary, "error": str(exc)}
    try:
        ytdlp_module_result = subprocess.run(
            [os.sys.executable, "-m", "yt_dlp", "--js-runtimes", settings.ytdlp_js_runtimes or "node", "--remote-components", settings.ytdlp_remote_components or "ejs:github", "--version"],
            capture_output=True,
            text=True,
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
            result = subprocess.run(command, capture_output=True, text=True, timeout=20)
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
        "app_version": "1.0.0-beta-ytdlp-node-runtime-check",
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
        "tts_status": vieneu_tts_status(),
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
    AppSettingsService(db).set(SAVED_COOKIES_KEY, {"cookies_file_path": str(output_path), "uploaded_at": time.time(), "file_size": len(content)})
    return UploadCookiesResponse(message="Upload cookies.txt thành công.", cookies_file_path=str(output_path))


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
            check=True, capture_output=True, text=True, timeout=120)
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
        render_options=payload.render_options,
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
    return vieneu_tts_status()


@router.get("/tts/voices")
def get_tts_voices():
    return {"engine": "vieneu_turbo", "voices": list_vieneu_turbo_voices()}


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
def get_tts_audio(path: str = Query(...)):
    file_path = _safe_path_under(path, tts_clones_dir())
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Audio không tồn tại.")
    return FileResponse(file_path)


@router.post("/render-jobs", response_model=RenderJobStartResponse)
def start_render_job(payload: RenderRequest, background_tasks: BackgroundTasks):
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
    background_tasks.add_task(_drain_render_queue)
    return RenderJobStartResponse(job_id=job_id, status="queued", message="Đã bắt đầu render job.")


@router.get("/render-jobs", response_model=list[RenderJobStatusResponse])
def list_render_jobs():
    _cleanup_render_jobs()
    with render_jobs_lock:
        items = list(render_jobs.items())
    items.sort(key=lambda item: item[1].get("started_at", 0), reverse=True)
    return [RenderJobStatusResponse(job_id=job_id, **_with_render_job_eta(job)) for job_id, job in items]


@router.get("/render-jobs/{job_id}", response_model=RenderJobStatusResponse)
def get_render_job(job_id: str):
    _cleanup_render_jobs()
    with render_jobs_lock:
        job = render_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Render job không tồn tại.")
    return RenderJobStatusResponse(job_id=job_id, **_with_render_job_eta(job))


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
    protected = _active_workspace_dirs()
    roots = []
    if payload.target in {"temp", "all"}:
        roots.append(settings.temp_dir)
    if payload.target in {"outputs", "all"}:
        roots.append(settings.outputs_dir)
    matched = deleted = freed = 0
    items: list[str] = []
    for root in roots:
        root_matched, root_deleted, root_freed, root_items = _cleanup_root(root, payload.older_than_hours, payload.dry_run, protected)
        matched += root_matched
        deleted += root_deleted
        freed += root_freed
        items.extend(root_items[: max(0, 100 - len(items))])
    return StorageCleanupResponse(target=payload.target, dry_run=payload.dry_run, matched_count=matched, deleted_count=deleted, freed_bytes=freed, items=items)


@router.post("/open-folder", response_model=MessageResponse)
def open_folder(payload: OpenFolderRequest):
    path = _safe_path_under(payload.path, settings.outputs_dir)
    folder = path if path.is_dir() else path.parent
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Thư mục không tồn tại.")
    os.startfile(str(folder))  # type: ignore[attr-defined]
    return MessageResponse(message="Đã mở thư mục output.")


@router.get("/files/download")
def download_file(path: str = Query(...)):
    file_path = _safe_path_under(path, settings.outputs_dir)
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


def _submit_render_from_automation(render_payload: dict) -> str:
    import uuid as _uuid
    import time as _time

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
    render_req = RenderRequest.model_validate(render_payload)
    with render_jobs_lock:
        render_queue.append((job_id, render_req))
    _drain_render_queue()
    return job_id


gemini_service.set_submit_render_fn(_submit_render_from_automation)


@router.post("/gemini/auto-submit", response_model=GeminiAutoSubmitResponse)
async def gemini_auto_submit(payload: GeminiAutoSubmitRequest):
    form_data = payload.form_data
    from app.schemas.prompt import PromptGenerateRequest

    try:
        prompt_req = PromptGenerateRequest.model_validate(form_data)
        prompt = PromptGenerator().generate(prompt_req)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Không thể tạo prompt: {exc}")

    task_id = str(uuid.uuid4())
    render_payload = {
        "youtube_url": form_data.get("youtube_url"),
        "local_video_path": payload.local_video_path,
        "ytdlp_cookies_file": payload.ytdlp_cookies_file,
        "burn_subtitle": payload.subtitle_mode == "burn",
        "subtitle_mode": payload.subtitle_mode,
        "render_options": payload.render_options,
        "gemini_json": {},
    }

    gemini_service.start(task_id, prompt, render_payload, payload.user_data_dir)
    return GeminiAutoSubmitResponse(task_id=task_id, prompt_text=prompt)


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
        msg = (
            "Đang mở Chromium với Chrome profile thật. Bạn đã đăng nhập Google sẵn, hãy đóng trình duyệt sau khi load xong."
            if ud_dir
            else "Đã mở trình duyệt Chromium. Sau khi đăng nhập Gemini, hãy đóng trình duyệt, session sẽ được tự động lưu."
        )
        return {"browser_id": browser_id, "message": msg, "user_data_dir": ud_dir}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Không thể mở trình duyệt: {exc}")


@router.get("/gemini/session-status")
def gemini_session_status():
    return gemini_service.get_session_status()


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
            await websocket.send_json(data)
            if data["status"] in ("done", "error"):
                break

            try:
                await task.wait_for_update(timeout=5.0)
            except Exception:
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
