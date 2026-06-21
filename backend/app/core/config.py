from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]
APP_BRAND = "MrTris_AUTO"


def _default_local_appdata() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) if base else Path.home() / "AppData" / "Local"


def _packaged_appdata() -> Path | None:
    value = os.environ.get("MRTRIS_AUTO_APPDATA")
    if value:
        return Path(value)
    if os.environ.get("MRTRIS_AUTO_PACKAGED") == "1":
        return _default_local_appdata() / APP_BRAND
    return None


def _default_sqlite_url() -> str:
    appdata = _packaged_appdata()
    if appdata:
        return f"sqlite:///{(appdata / 'data' / 'app.db').as_posix()}"
    return f"sqlite:///{(ROOT_DIR / 'backend' / 'app.db').as_posix()}"


def _default_outputs_dir() -> Path:
    value = os.environ.get("MRTRIS_AUTO_OUTPUTS_DIR")
    if value:
        return Path(value)
    if _packaged_appdata():
        return Path.home() / "Videos" / "AutoReview"
    return ROOT_DIR / "outputs"


def _default_temp_dir() -> Path:
    value = os.environ.get("MRTRIS_AUTO_TEMP_DIR")
    if value:
        return Path(value)
    appdata = _packaged_appdata()
    return appdata / "temp" if appdata else ROOT_DIR / "temp"


def _default_logs_dir() -> Path:
    value = os.environ.get("MRTRIS_AUTO_LOGS_DIR")
    if value:
        return Path(value)
    appdata = _packaged_appdata()
    return appdata / "logs" if appdata else ROOT_DIR / "logs"


def _default_local_videos_dir() -> Path:
    value = os.environ.get("MRTRIS_AUTO_LOCAL_VIDEOS_DIR")
    if value:
        return Path(value)
    return _default_temp_dir() / "videos"


def _packaged_binary(relative_path: str) -> str | None:
    if os.environ.get("MRTRIS_AUTO_PACKAGED") != "1":
        return None
    path = ROOT_DIR / relative_path
    return str(path) if path.exists() else None


def _default_ffmpeg_binary() -> str:
    return _packaged_binary("runtime/ffmpeg/ffmpeg.exe") or "ffmpeg"


def _default_ffprobe_binary() -> str:
    return _packaged_binary("runtime/ffmpeg/ffprobe.exe") or "ffprobe"


def _default_ytdlp_binary() -> str:
    return _packaged_binary("runtime/yt-dlp/yt-dlp.exe") or "yt-dlp"


class Settings(BaseSettings):
    app_name: str = APP_BRAND
    api_prefix: str = "/api"
    debug: bool = False
    sqlite_url: str = Field(default_factory=_default_sqlite_url)
    outputs_dir: Path = Field(default_factory=_default_outputs_dir)
    temp_dir: Path = Field(default_factory=_default_temp_dir)
    local_videos_dir: Path = Field(default_factory=_default_local_videos_dir)
    logs_dir: Path = Field(default_factory=_default_logs_dir)
    frontend_dist_dir: Path = ROOT_DIR / "frontend" / "dist"
    ffmpeg_binary: str = Field(default_factory=_default_ffmpeg_binary)
    ffprobe_binary: str = Field(default_factory=_default_ffprobe_binary)
    ytdlp_binary: str = Field(default_factory=_default_ytdlp_binary)
    ytdlp_cookies_file: str | None = None
    ytdlp_cookies_from_browser: str | None = None
    ytdlp_js_runtimes: str | None = None
    ytdlp_remote_components: str | None = None
    ytdlp_prefer_h264: bool = True
    video_encoder: str = "auto"
    segment_fps: int = 60
    render_job_ttl_seconds: int = 24 * 60 * 60
    license_enforcement: bool = False

    gemini_url: str = "https://gemini.google.com/app"
    gemini_session_path: Path = Field(default_factory=lambda: ROOT_DIR / "data" / "gemini_session.json")
    gemini_user_data_dir: str | None = None
    playwright_browsers_path: str | None = None
    playwright_headless: bool = True
    gemini_timeout_seconds: int = 180
    gemini_retry_count: int = 3

    model_config = SettingsConfigDict(env_file=str(ROOT_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")


settings = Settings()


def _repair_packaged_binary(current: str, relative_path: str) -> str:
    if os.environ.get("MRTRIS_AUTO_PACKAGED") != "1":
        return current
    bundled = ROOT_DIR / relative_path
    current_path = Path(current)
    if current_path.exists():
        return current
    if bundled.exists():
        return str(bundled)
    return current


settings.ffmpeg_binary = _repair_packaged_binary(settings.ffmpeg_binary, "runtime/ffmpeg/ffmpeg.exe")
settings.ffprobe_binary = _repair_packaged_binary(settings.ffprobe_binary, "runtime/ffmpeg/ffprobe.exe")
settings.ytdlp_binary = _repair_packaged_binary(settings.ytdlp_binary, "runtime/yt-dlp/yt-dlp.exe")
