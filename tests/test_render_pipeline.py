import subprocess
import time
from collections.abc import Callable

import pytest
from pathlib import Path

from app.schemas.render import GeminiPayloadSchema, RenderOptions, RenderRequest
from app.services.video_tools import RenderPipeline, TitleOverlay, VideoDownloader, final_videos_dir, safe_filename_prefix, sanitize_url, analyze_ytdlp_cookie_file


class DummyDownloader:
    def __init__(self):
        self.cookies_file = None
        self.cookies_from_browser = None
        self.user_data_dir = None
        self.downloads = []

    def download(self, url: str, output_path: Path, cookies_file: str | None = None, cookies_from_browser: str | None = None, user_data_dir: str | None = None, cancel_callback: Callable[[], bool] | None = None) -> Path:
        self.cookies_file = cookies_file
        self.cookies_from_browser = cookies_from_browser
        self.user_data_dir = user_data_dir
        self.downloads.append((url, output_path))
        output_path.write_bytes(b"video")
        return output_path


class DummyCutter:
    def __init__(self):
        self.source_paths = None
        self.reencode_segments = None

    def cut(self, source_paths: dict[str, Path], payload: GeminiPayloadSchema, clips_dir: Path, reencode_segments=False, progress_callback=None, render_options=None, cancel_callback=None, segment_plans=None):
        self.source_paths = source_paths
        self.reencode_segments = reencode_segments
        clips_dir.mkdir(parents=True, exist_ok=True)
        total_segments = len(payload.video_segments)
        for index, segment in enumerate(payload.video_segments, start=1):
            (clips_dir / f"segment_{segment.segment_id}.mp4").write_bytes(b"segment")
            if progress_callback:
                progress_callback({"progress": 30 + int((index / total_segments) * 40), "completed_segments": index, "total_segments": total_segments})
        return []


class DummyConcat:
    def concatenate(self, payload: GeminiPayloadSchema, clips_dir: Path, output_path: Path) -> Path:
        output_path.write_bytes(b"final")
        return output_path


class DummyBurner:
    def __init__(self):
        self.video_path = None
        self.srt_path = None
        self.output_path = None

    def burn(self, video_path: Path, srt_path: Path, output_path: Path, render_options=None, progress_callback=None, progress_start=94, progress_end=98, cancel_callback=None) -> Path:
        self.video_path = video_path
        self.srt_path = srt_path
        self.output_path = output_path
        output_path.write_bytes(b"burned")
        return output_path


class DummyTransformer:
    def __init__(self):
        self.options = None
        self.input_path = None
        self.output_path = None

    def needs_transform(self, options: RenderOptions) -> bool:
        return options.vertical_mode != "none" or options.output_resolution != "auto" or options.render_quality != "balanced"

    def transform(self, input_path: Path, output_path: Path, options: RenderOptions, progress_callback=None, progress_start=88, progress_end=94, cancel_callback=None) -> Path:
        self.options = options
        self.input_path = input_path
        self.output_path = output_path
        output_path.write_bytes(input_path.read_bytes() + b" transformed")
        return output_path


def test_render_pipeline(tmp_path: Path, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "temp_dir", tmp_path / "temp")
    monkeypatch.setattr(config.settings, "outputs_dir", tmp_path / "outputs")
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "Rich Man Mocks Mom & Son | @DramatizeMe", "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút", "hashtags": ["#drama", "#remake"]},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })
    pipeline = RenderPipeline(DummyDownloader(), DummyCutter(), DummyConcat(), DummyBurner())
    result = pipeline.render(payload, "https://youtube.com/watch?v=x", None, True, job_id="test-job-1")
    assert "Rich_Man_Mocks_Mom_&_Son_@DramatizeMe" in result["final_video_path"]
    assert result["final_video_path"].endswith("Rich_Man_Mocks_Mom_&_Son_@DramatizeMe_drama_remake.mp4")
    assert Path(result["final_video_path"]).exists()
    assert Path(result["final_video_library_path"]).exists()
    assert Path(result["final_video_library_path"]).parent == final_videos_dir()
    assert Path(result["final_video_library_path"]) == Path(result["final_video_path"])
    assert Path(result["render_plan_path"]).exists()
    assert Path(result["final_subtitle_path"]).exists()
    assert Path(result["source_path"]).exists()
    assert "test_job_1" in result["workspace_dir"]
    assert result["vertical_mode"] == "none"
    assert result["render_quality"] == "balanced"
    assert result["output_resolution"] == "auto"


def test_safe_filename_prefix():
    assert safe_filename_prefix("Rich Man Mocks Mom & Son | @DramatizeMe") == "rich_man_mocks_mom_son_dramatizeme"


def test_storage_cleanup_protects_final_videos_dir(tmp_path: Path, monkeypatch):
    from app.core import config
    from app.api.routes import _cleanup_root

    monkeypatch.setattr(config.settings, "outputs_dir", tmp_path / "outputs")
    library = final_videos_dir()
    old_workspace = config.settings.outputs_dir / "old_workspace"
    library.mkdir(parents=True)
    old_workspace.mkdir(parents=True)
    (library / "final.mp4").write_bytes(b"final")
    (old_workspace / "temp.mp4").write_bytes(b"temp")

    matched, deleted, _, items = _cleanup_root(config.settings.outputs_dir, older_than_hours=0, dry_run=False, protected={library.resolve()})

    assert matched == 1
    assert deleted == 1
    assert str(old_workspace) in items
    assert library.exists()
    assert (library / "final.mp4").exists()
    assert not old_workspace.exists()


def test_storage_cleanup_final_videos_deletes_old_items(tmp_path: Path, monkeypatch):
    from app.core import config
    from app.api.routes import _cleanup_root

    monkeypatch.setattr(config.settings, "outputs_dir", tmp_path / "outputs")
    library = final_videos_dir()
    library.mkdir(parents=True)
    final = library / "old_final.mp4"
    final.write_bytes(b"final")

    matched, deleted, _, items = _cleanup_root(library, older_than_hours=0, dry_run=False, protected=set())

    assert matched == 1
    assert deleted == 1
    assert str(final) in items
    assert not final.exists()


def test_sanitize_markdown_url():
    assert sanitize_url("[https://www.youtube.com/watch?v=j9ZJmUUivVI](https://www.youtube.com/watch?v=j9ZJmUUivVI)") == "https://www.youtube.com/watch?v=j9ZJmUUivVI"
    assert sanitize_url("<https://www.youtube.com/watch?v=j9ZJmUUivVI>") == "https://www.youtube.com/watch?v=j9ZJmUUivVI"


def test_sanitize_google_search_url():
    result = sanitize_url("https://www.google.com/search?q=https://youtube.com/watch%3Fv%3Dv3sgoFSqVsw")
    assert result == "https://youtube.com/watch?v=v3sgoFSqVsw"


def test_sanitize_google_redirect_url():
    result = sanitize_url("https://www.google.com/url?q=https%3A%2F%2Fyoutu.be%2Fabc123")
    assert result == "https://youtu.be/abc123"


def test_sanitize_google_url_no_youtube_passthrough():
    result = sanitize_url("https://www.google.com/search?q=cute+cat+videos")
    assert result == "https://www.google.com/search?q=cute+cat+videos"


def test_sanitize_google_url_no_q_passthrough():
    result = sanitize_url("https://www.google.com/")
    assert result == "https://www.google.com/"


class TestPlaceholderUrlValidation:
    def test_rejects_dots_placeholder_single(self):
        assert VideoDownloader._is_placeholder_url("https://www.youtube.com/watch?v=...")

    def test_rejects_dots_placeholder_multi(self):
        assert VideoDownloader._is_placeholder_url("https://www.youtube.com/watch?v=...&t=30")

    def test_rejects_video_id_template(self):
        assert VideoDownloader._is_placeholder_url("https://www.youtube.com/watch?v={VIDEO_ID}")

    def test_rejects_url_encoded_template(self):
        assert VideoDownloader._is_placeholder_url("https://www.youtube.com/watch?v=%7BVIDEO_ID%7D")

    def test_rejects_placeholder_in_path(self):
        assert VideoDownloader._is_placeholder_url("https://www.youtube.com/watch?v=.../extra")

    def test_passes_real_url(self):
        assert not VideoDownloader._is_placeholder_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_passes_real_url_with_params(self):
        assert not VideoDownloader._is_placeholder_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s")

    def test_passes_youtu_be(self):
        assert not VideoDownloader._is_placeholder_url("https://youtu.be/dQw4w9WgXcQ")

    def test_passes_non_youtube_url(self):
        assert not VideoDownloader._is_placeholder_url("https://example.com/video.mp4")


def test_render_pipeline_passes_uploaded_cookies_file(tmp_path: Path, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "temp_dir", tmp_path / "temp")
    monkeypatch.setattr(config.settings, "outputs_dir", tmp_path / "outputs")
    cookies_path = config.settings.temp_dir / "cookies" / "uploaded.txt"
    cookies_path.parent.mkdir(parents=True)
    cookies_path.write_text("cookies", encoding="utf-8")
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "Cookies Test", "rewrite_style": "Drama", "target_audience": "Đại chúng", "tone": "Hài hước", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })
    downloader = DummyDownloader()
    pipeline = RenderPipeline(downloader, DummyCutter(), DummyConcat(), DummyBurner())

    pipeline.render(payload, "https://youtube.com/watch?v=x", None, True, ytdlp_cookies_file=str(cookies_path))

    assert downloader.cookies_file == str(cookies_path.resolve())
    assert downloader.cookies_from_browser is None


def test_render_pipeline_passes_user_data_dir_to_downloader(tmp_path: Path, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "temp_dir", tmp_path / "temp")
    monkeypatch.setattr(config.settings, "outputs_dir", tmp_path / "outputs")
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "Profile Test", "rewrite_style": "Drama", "target_audience": "Đại chúng", "tone": "Hài hước", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })
    downloader = DummyDownloader()
    pipeline = RenderPipeline(downloader, DummyCutter(), DummyConcat(), DummyBurner())

    pipeline.render(payload, "https://youtube.com/watch?v=x", None, True, user_data_dir=str(tmp_path / "profile"))

    assert downloader.user_data_dir == str(tmp_path / "profile")


def _valid_cookie_file(path: Path) -> None:
    path.write_text(
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t4102444800\tLOGIN_INFO\tvalue\n",
        encoding="utf-8",
    )


def test_ytdlp_retries_browser_profile_after_cookie_auth_failure(tmp_path: Path, monkeypatch):
    cookie_file = tmp_path / "cookies.txt"
    _valid_cookie_file(cookie_file)
    profile = tmp_path / "gemini_profile"
    (profile / "Network").mkdir(parents=True)
    (profile / "Network" / "Cookies").write_bytes(b"")
    calls: list[list[str]] = []

    def fake_run(self, cmd, cancel_callback=None):
        calls.append(cmd)
        if "--cookies" in cmd:
            raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(VideoDownloader, "_run_ytdlp_command", fake_run)
    monkeypatch.setattr(VideoDownloader, "_write_ytdlp_preflight", lambda self: None)
    monkeypatch.setattr(VideoDownloader, "_write_ytdlp_command", lambda self, cmd: None)
    monkeypatch.setattr(VideoDownloader, "_write_ytdlp_log", lambda self, cmd, detail: None)
    monkeypatch.setattr(VideoDownloader, "_format_process_error", lambda self, exc, stdout_path=None, stderr_path=None: "HTTP Error 403: Sign in to confirm you're not a bot")

    VideoDownloader().download("https://www.youtube.com/watch?v=test", tmp_path / "out.mp4", cookies_file=str(cookie_file), user_data_dir=str(profile))

    assert len(calls) == 2
    assert "--cookies" in calls[0]
    assert "--cookies-from-browser" in calls[1]
    assert f"chrome:{profile}" in calls[1]


def test_ytdlp_prefers_browser_when_cookie_file_has_weak_auth(tmp_path: Path, monkeypatch):
    """Cookie with weak auth (no SAPISID/APISID/LOGIN_INFO) + browser exists → try browser first."""
    far_future = str(int(time.time() + 86400 * 30))
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        f".youtube.com\tTRUE\t/\tTRUE\t{far_future}\t__Secure-3PSID\tval\n",
        encoding="utf-8",
    )
    profile = tmp_path / "profile"
    (profile / "Network").mkdir(parents=True)
    (profile / "Network" / "Cookies").write_bytes(b"")
    calls: list[list[str]] = []

    def fake_run(self, cmd, cancel_callback=None):
        calls.append(cmd)
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(VideoDownloader, "_run_ytdlp_command", fake_run)
    monkeypatch.setattr(VideoDownloader, "_write_ytdlp_preflight", lambda self: None)
    monkeypatch.setattr(VideoDownloader, "_write_ytdlp_command", lambda self, cmd: None)
    monkeypatch.setattr(VideoDownloader, "_write_ytdlp_log", lambda self, cmd, detail: None)
    monkeypatch.setattr(VideoDownloader, "_format_process_error", lambda self, exc, stdout_path=None, stderr_path=None: "HTTP Error 403: Sign in to confirm you're not a bot")

    with pytest.raises(RuntimeError):
        VideoDownloader().download("https://www.youtube.com/watch?v=test", tmp_path / "out.mp4", cookies_file=str(cookie_file), user_data_dir=str(profile))

    assert len(calls) == 2
    # Weak auth → browser should be attempted first
    assert "--cookies-from-browser" in calls[0], f"expected browser first, got: {calls[0]}"
    assert "--cookies" in calls[1]


def test_ytdlp_does_not_retry_non_auth_failure(tmp_path: Path, monkeypatch):
    cookie_file = tmp_path / "cookies.txt"
    _valid_cookie_file(cookie_file)
    profile = tmp_path / "gemini_profile"
    (profile / "Network").mkdir(parents=True)
    (profile / "Network" / "Cookies").write_bytes(b"")
    calls: list[list[str]] = []

    def fake_run(self, cmd, cancel_callback=None):
        calls.append(cmd)
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(VideoDownloader, "_run_ytdlp_command", fake_run)
    monkeypatch.setattr(VideoDownloader, "_write_ytdlp_preflight", lambda self: None)
    monkeypatch.setattr(VideoDownloader, "_write_ytdlp_command", lambda self, cmd: None)
    monkeypatch.setattr(VideoDownloader, "_write_ytdlp_log", lambda self, cmd, detail: None)
    monkeypatch.setattr(VideoDownloader, "_format_process_error", lambda self, exc, stdout_path=None, stderr_path=None: "ERROR: disk full")

    with pytest.raises(RuntimeError):
        VideoDownloader().download("https://www.youtube.com/watch?v=test", tmp_path / "out.mp4", cookies_file=str(cookie_file), user_data_dir=str(profile))

    assert len(calls) == 1
    assert "--cookies" in calls[0]


def test_render_pipeline_rejects_cookies_file_outside_upload_dir(tmp_path: Path, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "temp_dir", tmp_path / "temp")
    monkeypatch.setattr(config.settings, "outputs_dir", tmp_path / "outputs")
    outside_cookies = tmp_path / "cookies.txt"
    outside_cookies.write_text("cookies", encoding="utf-8")
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "Cookies Test", "rewrite_style": "Drama", "target_audience": "Đại chúng", "tone": "Hài hước", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })
    pipeline = RenderPipeline(DummyDownloader(), DummyCutter(), DummyConcat(), DummyBurner())

    with pytest.raises(ValueError, match="File cookies"):
        pipeline.render(payload, "https://youtube.com/watch?v=x", None, True, ytdlp_cookies_file=str(outside_cookies))


def test_render_pipeline_allows_local_video_only_under_configured_dir(tmp_path: Path, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "temp_dir", tmp_path / "temp")
    monkeypatch.setattr(config.settings, "outputs_dir", tmp_path / "outputs")
    monkeypatch.setattr(config.settings, "local_videos_dir", tmp_path / "allowed_videos")
    local_video = config.settings.local_videos_dir / "input.mp4"
    local_video.parent.mkdir(parents=True)
    local_video.write_bytes(b"video")
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "Local Video", "rewrite_style": "Drama", "target_audience": "Đại chúng", "tone": "Hài hước", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })
    pipeline = RenderPipeline(DummyDownloader(), DummyCutter(), DummyConcat(), DummyBurner())

    result = pipeline.render(payload, None, str(local_video), False)

    assert Path(result["final_video_path"]).exists()


def test_render_pipeline_rejects_local_video_outside_configured_dir(tmp_path: Path, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "temp_dir", tmp_path / "temp")
    monkeypatch.setattr(config.settings, "outputs_dir", tmp_path / "outputs")
    monkeypatch.setattr(config.settings, "local_videos_dir", tmp_path / "allowed_videos")
    local_video = tmp_path / "input.mp4"
    local_video.write_bytes(b"video")
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "Local Video", "rewrite_style": "Drama", "target_audience": "Đại chúng", "tone": "Hài hước", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })
    pipeline = RenderPipeline(DummyDownloader(), DummyCutter(), DummyConcat(), DummyBurner())

    with pytest.raises(ValueError, match="Video local"):
        pipeline.render(payload, None, str(local_video), False)


def test_render_pipeline_applies_vertical_blur_fit(tmp_path: Path, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "temp_dir", tmp_path / "temp")
    monkeypatch.setattr(config.settings, "outputs_dir", tmp_path / "outputs")
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "Vertical Test", "rewrite_style": "Drama", "target_audience": "Đại chúng", "tone": "Hài hước", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })
    burner = DummyBurner()
    transformer = DummyTransformer()
    pipeline = RenderPipeline(DummyDownloader(), DummyCutter(), DummyConcat(), burner, transformer)

    result = pipeline.render(payload, "https://youtube.com/watch?v=x", None, True, render_options=RenderOptions(vertical_mode="blur_fit"))

    assert transformer.options is not None
    assert transformer.options.vertical_mode == "blur_fit"
    assert transformer.input_path is not None
    assert transformer.input_path.name == "vertical_test_raw.mp4"
    assert transformer.output_path is not None
    assert transformer.output_path.name == "vertical_test_transformed.mp4"
    assert burner.video_path is not None
    assert burner.video_path.name == "vertical_test_title.mp4"
    assert not burner.video_path.exists()
    assert not transformer.output_path.exists()
    assert burner.output_path == Path(result["final_video_path"])
    assert Path(result["final_video_path"]).exists()
    assert result["vertical_mode"] == "blur_fit"
    assert result["artifact_retention"] == "smart"
    assert result["cleaned_artifact_count"] == "4"


def test_render_pipeline_keep_all_preserves_intermediates(tmp_path: Path, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "temp_dir", tmp_path / "temp")
    monkeypatch.setattr(config.settings, "outputs_dir", tmp_path / "outputs")
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "Keep All Test", "rewrite_style": "Drama", "target_audience": "Đại chúng", "tone": "Hài hước", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })
    burner = DummyBurner()
    transformer = DummyTransformer()
    pipeline = RenderPipeline(DummyDownloader(), DummyCutter(), DummyConcat(), burner, transformer)

    result = pipeline.render(payload, "https://youtube.com/watch?v=x", None, True, render_options=RenderOptions(vertical_mode="blur_fit", artifact_retention="keep_all"))

    assert transformer.output_path is not None
    assert transformer.output_path.exists()
    assert burner.video_path is not None
    assert burner.video_path.exists()
    assert Path(result["final_video_path"]).exists()
    assert result["artifact_retention"] == "keep_all"
    assert result["cleaned_artifact_count"] == "0"


def test_render_pipeline_applies_center_crop_without_burn(tmp_path: Path, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "temp_dir", tmp_path / "temp")
    monkeypatch.setattr(config.settings, "outputs_dir", tmp_path / "outputs")
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "Crop Test", "rewrite_style": "Drama", "target_audience": "Đại chúng", "tone": "Hài hước", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })
    burner = DummyBurner()
    transformer = DummyTransformer()
    pipeline = RenderPipeline(DummyDownloader(), DummyCutter(), DummyConcat(), burner, transformer)

    result = pipeline.render(payload, "https://youtube.com/watch?v=x", None, False, render_options=RenderOptions(vertical_mode="center_crop", render_quality="high", output_resolution="1080p"))

    assert transformer.options is not None
    assert transformer.options.vertical_mode == "center_crop"
    assert transformer.options.render_quality == "high"
    assert transformer.input_path is not None
    assert transformer.input_path.name == "crop_test_raw.mp4"
    assert transformer.output_path == Path(result["final_video_path"])
    assert burner.video_path is None
    assert result["burn_subtitle"] == "False"


def test_render_pipeline_applies_video_speed_without_unbound_metadata(tmp_path: Path, monkeypatch):
    from app.core import config
    from app.services import video_tools

    monkeypatch.setattr(config.settings, "temp_dir", tmp_path / "temp")
    monkeypatch.setattr(config.settings, "outputs_dir", tmp_path / "outputs")
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "Speed Test", "rewrite_style": "Drama", "target_audience": "Đại chúng", "tone": "Hài hước", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:04,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:04.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })
    captured: dict[str, float | None] = {}

    def fake_probe_metadata(path: Path) -> dict[str, str]:
        return {"codec": "h264", "fps": "30/1", "resolution": "1920x1080", "duration_seconds": "4.000000"}

    def fake_run_ffmpeg(cmd_builder, message, cwd=None, mode_override=None, progress_callback=None, duration_seconds=None, progress_start=0, progress_end=100, cancel_callback=None):
        captured["duration_seconds"] = duration_seconds
        cmd = cmd_builder(video_tools.CPU_ENCODER)
        output_path = Path(cmd[-1])
        output_path.write_bytes(b"sped up")
        return video_tools.CPU_ENCODER

    monkeypatch.setattr(video_tools, "probe_video_metadata", fake_probe_metadata)
    monkeypatch.setattr(video_tools, "run_ffmpeg_with_encoder_fallback", fake_run_ffmpeg)
    pipeline = RenderPipeline(DummyDownloader(), DummyCutter(), DummyConcat(), DummyBurner())

    result = pipeline.render(payload, "https://youtube.com/watch?v=x", None, False, render_options=RenderOptions(video_speed=1.25))

    assert captured["duration_seconds"] == pytest.approx(3.2)
    assert Path(result["final_video_path"]).read_bytes() == b"sped up"
    assert result["output_duration_seconds"] == "4.000000"


def test_title_overlay_respects_line_options():
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "A very long localized title for preview tuning", "rewrite_style": "Drama", "target_audience": "Đại chúng", "tone": "Hài hước", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })

    title = TitleOverlay().resolve_title(payload, RenderOptions(title_max_lines=1, title_chars_per_line=18))

    assert title.count("\n") == 0
    assert title.endswith("...")


def test_title_overlay_auto_badge_for_cops():
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "Police Bodycam Case", "rewrite_style": "Điều tra", "target_audience": "Đại chúng", "tone": "Nghiêm túc", "target_duration": "1-3 phút", "narrator_persona": "detective"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })

    badge = TitleOverlay().resolve_badge(payload, RenderOptions(title_badge_mode="auto"))

    assert badge == "BODYCAM"


def test_title_overlay_builds_breaking_yellow_filter(tmp_path: Path, monkeypatch):
    from app.services import video_tools

    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "Police Bodycam Case", "rewrite_style": "Điều tra", "target_audience": "Đại chúng", "tone": "Nghiêm túc", "target_duration": "1-3 phút", "narrator_persona": "detective"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    input_path.write_bytes(b"video")
    captured: dict[str, str] = {}

    def fake_probe_metadata(path):
        return {"duration_seconds": 3.0}

    def fake_run_ffmpeg(cmd_builder, *args, **kwargs):
        cmd = cmd_builder(video_tools.CPU_ENCODER)
        captured["filter"] = cmd[cmd.index("-vf") + 1]
        Path(cmd[-1]).write_bytes(b"title")
        return video_tools.CPU_ENCODER

    monkeypatch.setattr(video_tools, "probe_video_metadata", fake_probe_metadata)
    monkeypatch.setattr(video_tools, "run_ffmpeg_with_encoder_fallback", fake_run_ffmpeg)

    TitleOverlay().apply(input_path, output_path, payload, RenderOptions(title_style="breaking_yellow", title_badge_mode="auto", title_text_align="center"))

    assert "drawbox" in captured["filter"]
    assert "0xB91C1C" in captured["filter"]
    assert "0xFFD319" in captured["filter"]
    assert "badge.txt" in captured["filter"]
    assert "x=(w-text_w)/2" in captured["filter"]


def test_render_pipeline_downloads_and_cuts_multiple_sources(tmp_path: Path, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "temp_dir", tmp_path / "temp")
    monkeypatch.setattr(config.settings, "outputs_dir", tmp_path / "outputs")
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "Multi Source", "rewrite_style": "Drama", "target_audience": "Đại chúng", "tone": "Hài hước", "target_duration": "1-3 phút"},
        "sources": [
            {"source_id": "source_1", "youtube_url": "https://youtube.com/watch?v=a", "label": "A"},
            {"source_id": "source_2", "youtube_url": "https://youtube.com/watch?v=b", "label": "B"},
        ],
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [
            {"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"},
            {"index": 2, "start": "00:00:03,000", "end": "00:00:06,000", "text": "Tạm biệt"},
        ],
        "video_segments": [
            {"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "A", "importance_score": 95},
            {"segment_id": 2, "order": 2, "source_id": "source_2", "source_start": "00:00:10.000", "source_end": "00:00:13.000", "subtitle_start": 2, "subtitle_end": 2, "scene_description": "B", "importance_score": 95},
        ],
    })
    downloader = DummyDownloader()
    cutter = DummyCutter()
    pipeline = RenderPipeline(downloader, cutter, DummyConcat(), DummyBurner())

    result = pipeline.render(payload, None, None, True)

    assert len(downloader.downloads) == 2
    assert cutter.source_paths is not None
    assert set(cutter.source_paths) == {"source_1", "source_2"}
    assert cutter.reencode_segments is True
    assert result["source_count"] == "2"


def test_render_pipeline_sanitizes_markdown_source_urls(tmp_path: Path, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "temp_dir", tmp_path / "temp")
    monkeypatch.setattr(config.settings, "outputs_dir", tmp_path / "outputs")
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "Markdown Source", "rewrite_style": "Drama", "target_audience": "Đại chúng", "tone": "Hài hước", "target_duration": "1-3 phút"},
        "sources": [{"source_id": "source_1", "youtube_url": "[https://www.youtube.com/watch?v=j9ZJmUUivVI](https://www.youtube.com/watch?v=j9ZJmUUivVI)", "label": "A"}],
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "A", "importance_score": 95}],
    })
    downloader = DummyDownloader()
    pipeline = RenderPipeline(downloader, DummyCutter(), DummyConcat(), DummyBurner())

    pipeline.render(payload, None, None, True)

    assert downloader.downloads[0][0] == "https://www.youtube.com/watch?v=j9ZJmUUivVI"


def test_render_pipeline_exports_srt_only_without_video_source(tmp_path: Path, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "temp_dir", tmp_path / "temp")
    monkeypatch.setattr(config.settings, "outputs_dir", tmp_path / "outputs")
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "SRT Only", "rewrite_style": "Drama", "target_audience": "Đại chúng", "tone": "Hài hước", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })
    downloader = DummyDownloader()
    cutter = DummyCutter()
    burner = DummyBurner()
    pipeline = RenderPipeline(downloader, cutter, DummyConcat(), burner)

    result = pipeline.render(payload, None, None, False, subtitle_mode="srt_only")

    assert result["final_video_path"] == ""
    assert result["subtitle_mode"] == "srt_only"
    assert Path(result["final_subtitle_path"]).exists()
    assert Path(result["render_plan_path"]).exists()
    assert downloader.downloads == []
    assert cutter.source_paths is None
    assert burner.video_path is None


def test_render_request_allows_srt_only_without_video_source():
    request = RenderRequest.model_validate({
        "gemini_json": {
            "metadata": {"video_title": "SRT Only", "rewrite_style": "Drama", "target_audience": "Đại chúng", "tone": "Hài hước", "target_duration": "1-3 phút"},
            "rewrite_script": {"full_text": "Xin chào"},
            "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
            "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
        },
        "subtitle_mode": "srt_only",
    })

    assert request.effective_subtitle_mode == "srt_only"


# --- ui_safe_error ---


from app.services.video_tools import ui_safe_error


def test_ui_safe_error_passes_short_text():
    assert ui_safe_error("short error") == "short error"


def test_ui_safe_error_strips_stdout_file_block():
    msg = ui_safe_error("something\nSTDOUT_FILE:\nlong stdout data\nSTDERR_FILE:\nlong stderr data\nremaining")
    assert "STDOUT_FILE:" not in msg
    assert "STDERR_FILE:" not in msg
    assert "remaining" in msg


def test_ui_safe_error_strips_traceback():
    msg = ui_safe_error("ERROR: unable to download\nTraceback (most recent call last):\n  File \"C:\\test.py\", line 1\n    raise RuntimeError(\"test\")\nRuntimeError: test\nmessage")
    assert "Traceback" not in msg
    assert "File" not in msg
    assert "RuntimeError: test" in msg
    assert "message" in msg


def test_ui_safe_error_truncates_long_text():
    long_text = "a" * 1000
    msg = ui_safe_error(long_text)
    assert len(msg) <= 500
    assert msg.endswith("...")


def test_ui_safe_error_handles_403_detail():
    text = (
        "ERROR: unable to download video data: HTTP Error 403: Forbidden\n"
        "Traceback (most recent call last):\n  File \"C:\\test.py\", line 1\n"
        "STDERR_FILE:\ndebug: format 137\n[download] 1.3% of 738.35MiB\nHTTP Error 403"
    )
    msg = ui_safe_error(text)
    assert "STDERR_FILE:" not in msg
    assert "Traceback" not in msg
    assert "HTTP Error 403" in msg


def test_require_tts_ready_raises_when_not_installed(monkeypatch):
    from app.api.routes import _require_tts_ready
    from fastapi import HTTPException

    monkeypatch.setattr("app.api.routes.edge_tts_status", lambda: {"status": "not_installed", "engine": "edge_tts", "message": "Edge TTS chưa được cài."})

    with pytest.raises(HTTPException) as exc_info:
        _require_tts_ready()
    assert exc_info.value.status_code == 400
    assert "Edge TTS" in str(exc_info.value.detail)


def test_require_tts_ready_passes_when_installed(monkeypatch):
    from app.api.routes import _require_tts_ready

    monkeypatch.setattr("app.api.routes.edge_tts_status", lambda: {"status": "ready", "engine": "edge_tts", "message": "Sẵn sàng."})

    _require_tts_ready()


import json


class TestCookieAnalyzer:
    NETSARAP_HEADER = "# Netscape HTTP Cookie File\n"

    def _make_cookie_file(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "cookies.txt"
        p.write_text(content, encoding="utf-8")
        return p

    def test_empty_file_is_invalid(self, tmp_path: Path):
        p = self._make_cookie_file(tmp_path, "")
        h = analyze_ytdlp_cookie_file(p)
        assert not h.valid
        assert any("rỗng" in e for e in h.errors)

    def test_no_yt_cookies_is_invalid(self, tmp_path: Path):
        content = self.NETSARAP_HEADER + "\t".join([
            ".example.com", "TRUE", "/", "FALSE", "1893456000", "test_cookie", "value"
        ]) + "\n"
        p = self._make_cookie_file(tmp_path, content)
        h = analyze_ytdlp_cookie_file(p)
        assert not h.valid
        assert any("YouTube" in e for e in h.errors)

    def test_all_expired_is_invalid(self, tmp_path: Path):
        rows = [
            self.NETSARAP_HEADER.rstrip("\n"),
            "\t".join([".youtube.com", "TRUE", "/", "FALSE", "1000000000", "test_cookie", "value"]),
            "\t".join([".youtube.com", "TRUE", "/", "FALSE", "1500000000", "SAPISID", "value"]),
        ]
        p = self._make_cookie_file(tmp_path, "\n".join(rows) + "\n")
        h = analyze_ytdlp_cookie_file(p)
        assert not h.valid, f"expected invalid but got {h}"
        assert any("hết hạn" in e for e in h.errors)

    def test_valid_youtube_cookies(self, tmp_path: Path):
        far_future = str(int(time.time() + 86400 * 30))
        rows = [
            self.NETSARAP_HEADER.rstrip("\n"),
            "\t".join([".youtube.com", "TRUE", "/", "FALSE", far_future, "SAPISID", "value123"]),
            "\t".join([".google.com", "TRUE", "/", "FALSE", far_future, "SSID", "value456"]),
        ]
        p = self._make_cookie_file(tmp_path, "\n".join(rows) + "\n")
        h = analyze_ytdlp_cookie_file(p)
        assert h.valid, h.errors
        assert h.youtube_cookies >= 2, f"got {h.youtube_cookies}"
        assert h.auth_cookies >= 1

    def test_missing_auth_cookies_warns(self, tmp_path: Path):
        far_future = str(int(time.time() + 86400 * 30))
        lines = [self.NETSARAP_HEADER]
        lines.append("\t".join([".youtube.com", "TRUE", "/", "FALSE", far_future, "VISITOR_INFO1_LIVE", "val"]))
        p = self._make_cookie_file(tmp_path, "".join(lines))
        h = analyze_ytdlp_cookie_file(p)
        assert h.valid
        assert len(h.warnings) > 0
        assert any("thiếu cookie auth" in w for w in h.warnings)

    def test_partially_expired_warns(self, tmp_path: Path):
        distant = str(int(time.time() + 86400 * 30))
        expired = str(1000000000)
        rows = [
            self.NETSARAP_HEADER.rstrip("\n"),
            "\t".join([".youtube.com", "TRUE", "/", "FALSE", expired, "VISITOR_INFO1_LIVE", "v1"]),
            "\t".join([".youtube.com", "TRUE", "/", "FALSE", distant, "SAPISID", "v2"]),
        ]
        p = self._make_cookie_file(tmp_path, "\n".join(rows) + "\n")
        h = analyze_ytdlp_cookie_file(p)
        assert h.valid, h.errors
        assert h.expired_cookies > 0

    def test_nonexistent_file(self, tmp_path: Path):
        h = analyze_ytdlp_cookie_file(tmp_path / "nope.txt")
        assert not h.valid
        assert any("không tồn tại" in e for e in h.errors)

    def test_no_parseable_rows(self, tmp_path: Path):
        content = "# just a comment\n# another comment\n\n"
        p = self._make_cookie_file(tmp_path, content)
        h = analyze_ytdlp_cookie_file(p)
        assert not h.valid
        assert any("không có dòng cookie" in e for e in h.errors)

    def test_modern_secure_auth_detected(self, tmp_path):
        far_future = str(int(time.time() + 86400 * 30))
        rows = [
            self.NETSARAP_HEADER.rstrip("\n"),
            "\t".join([".youtube.com", "TRUE", "/", "FALSE", far_future, "__Secure-3PAPISID", "val"]),
        ]
        p = self._make_cookie_file(tmp_path, "\n".join(rows) + "\n")
        h = analyze_ytdlp_cookie_file(p)
        assert h.valid, h.errors
        assert h.auth_cookies == 1
        assert h.has_strong_auth, "Secure-3PAPISID should be strong auth"

    def test_strong_auth_present(self, tmp_path):
        far_future = str(int(time.time() + 86400 * 30))
        rows = [
            self.NETSARAP_HEADER.rstrip("\n"),
            "\t".join([".youtube.com", "TRUE", "/", "FALSE", far_future, "SAPISID", "val"]),
        ]
        p = self._make_cookie_file(tmp_path, "\n".join(rows) + "\n")
        h = analyze_ytdlp_cookie_file(p)
        assert h.valid, h.errors
        assert h.auth_cookies == 1
        assert h.has_strong_auth

    def test_weak_session_no_strong_auth(self, tmp_path):
        far_future = str(int(time.time() + 86400 * 30))
        rows = [
            self.NETSARAP_HEADER.rstrip("\n"),
            "\t".join([".youtube.com", "TRUE", "/", "FALSE", far_future, "__Secure-3PSID", "val"]),
        ]
        p = self._make_cookie_file(tmp_path, "\n".join(rows) + "\n")
        h = analyze_ytdlp_cookie_file(p)
        assert h.valid, h.errors
        assert h.auth_cookies == 1  # still counted as auth
        assert not h.has_strong_auth  # but not strong

    def test_weak_auth_warns_about_missing_strong(self, tmp_path):
        far_future = str(int(time.time() + 86400 * 30))
        rows = [
            self.NETSARAP_HEADER.rstrip("\n"),
            "\t".join([".youtube.com", "TRUE", "/", "FALSE", far_future, "__Secure-3PSID", "val"]),
            "\t".join([".youtube.com", "TRUE", "/", "FALSE", far_future, "__Secure-3PSIDCC", "val"]),
        ]
        p = self._make_cookie_file(tmp_path, "\n".join(rows) + "\n")
        h = analyze_ytdlp_cookie_file(p)
        assert h.valid, h.errors
        assert h.auth_cookies >= 2
        assert not h.has_strong_auth
        assert any("thiếu" in w and "SAPISID" in w for w in h.warnings)


@pytest.mark.asyncio
async def test_validate_and_render_reports_invalid_json_without_fake_retry():
    from app.services.gemini_automation import GeminiAutomationService, GeminiAutomationTask

    svc = GeminiAutomationService()
    task = GeminiAutomationTask("test-validate-task")

    invalid_json = json.dumps({"metadata": {"video_title": "test"}})
    render_payload = {"render_options": {"tts_mode": "none"}}

    await svc._validate_and_render(task, invalid_json, render_payload)

    assert task.status == "error"
    assert "không hợp lệ" in task.error.lower()
    assert "3 lần thử" not in task.error


@pytest.mark.asyncio
async def test_validate_without_render_marks_done_and_does_not_submit_render():
    from app.services.gemini_automation import GeminiAutomationService, GeminiAutomationTask

    svc = GeminiAutomationService()
    called = False

    async def submit_render(_payload, _task_id):
        nonlocal called
        called = True
        return "job-1"

    svc.set_submit_render_fn(submit_render)
    task = GeminiAutomationTask("test-dry-run-task")
    payload = {
        "metadata": {"video_title": "A", "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    }

    await svc._validate_without_render(task, json.dumps(payload), {"render_options": {"tts_mode": "none"}})

    assert task.status == "done"
    assert task.result["dry_run"] is True
    assert task.result["render_submitted"] is False
    assert task.result["json_valid"] is True
    assert called is False


class TestJsonRepair:
    """Tests for loads_json_with_repair and _repair_unescaped_quotes."""

    def test_repair_unescaped_quotes_in_full_text(self):
        raw = '{"metadata": {"video_title": "Test"}, "sources": [{"source_id": "source_1", "youtube_url": "https://youtube.com/watch?v=abc123", "label": "Test"}], "rewrite_script": {"full_text": "Hãy gặp "Edward Wilson", tự xưng là hỗ trợ McAfee."}}'
        from app.services.json_validator import loads_json_with_repair
        parsed = loads_json_with_repair(raw)
        assert isinstance(parsed, dict)
        full_text = parsed["rewrite_script"]["full_text"]
        assert '"Edward Wilson"' in full_text
        assert 'tự xưng là hỗ trợ McAfee' in full_text

    def test_repair_unescaped_quotes_in_srt_text(self):
        raw = '{"metadata": {"video_title": "Test"}, "sources": [{"source_id": "source_1", "youtube_url": "https://youtube.com/watch?v=abc123", "label": "Test"}], "rewrite_script": {"full_text": "Hello"}, "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:05,000", "text": "Hắn nói "Tôi đến đây" và bỏ chạy."}]}'
        from app.services.json_validator import loads_json_with_repair
        parsed = loads_json_with_repair(raw)
        assert isinstance(parsed, dict)
        text = parsed["srt"][0]["text"]
        assert '"Tôi đến đây"' in text
        assert 'và bỏ chạy' in text

    def test_repair_preserves_existing_valid_escapes(self):
        raw = '{"metadata": {"video_title": "Test"}, "sources": [{"source_id": "source_1", "youtube_url": "https://youtube.com/watch?v=abc123", "label": "Test"}], "rewrite_script": {"full_text": "Anh ấy nói \\"Xin chào\\" và cười."}}'
        from app.services.json_validator import loads_json_with_repair
        parsed = loads_json_with_repair(raw)
        assert isinstance(parsed, dict)
        full_text = parsed["rewrite_script"]["full_text"]
        assert '"Xin chào"' in full_text or '\\"Xin chào\\"' in full_text
        assert 'và cười' in full_text

    def test_repair_does_not_modify_valid_json(self):
        raw = '{"metadata": {"video_title": "Test"}, "sources": [{"source_id": "source_1", "youtube_url": "https://youtube.com/watch?v=abc123", "label": "Test"}], "rewrite_script": {"full_text": "Nội dung bình thường không có quote."}}'
        from app.services.json_validator import loads_json_with_repair
        parsed = loads_json_with_repair(raw)
        assert isinstance(parsed, dict)
        assert parsed["rewrite_script"]["full_text"] == "Nội dung bình thường không có quote."

    def test_repair_handles_broken_json_gracefully(self):
        raw = '{"metadata": {"video_title": "Test", "sources": [broken completely}'
        from app.services.json_validator import loads_json_with_repair
        with pytest.raises(ValueError, match="JSON không hợp lệ"):
            loads_json_with_repair(raw)

    def test_repair_handles_markdown_url_in_sources(self):
        raw = '{"metadata": {"video_title": "Test"}, "sources": [{"source_id": "source_1", "youtube_url": "[https://www.youtube.com/watch?v=abc123](https://www.youtube.com/watch?v=abc123)", "label": "Test"}], "rewrite_script": {"full_text": "No quotes here."}}'
        from app.services.json_validator import JsonValidator
        validator = JsonValidator()
        # normalize_payload handles URL sanitization (loads_json_with_repair only parses)
        parsed = validator.normalize_payload(raw)
        url = parsed["sources"][0]["youtube_url"]
        assert url == "https://www.youtube.com/watch?v=abc123"

    def test_normalize_payload_with_unescaped_quotes(self):
        from app.services.json_validator import JsonValidator
        validator = JsonValidator()
        raw = '{"metadata": {"video_title": "Test"}, "sources": [{"source_id": "source_1", "youtube_url": "https://youtube.com/watch?v=abc123", "label": "Test"}], "rewrite_script": {"full_text": "Hắn tự xưng "CEO" và bỏ chạy."}}'
        parsed = validator.normalize_payload(raw)
        assert isinstance(parsed, dict)
        assert '"CEO"' in parsed["rewrite_script"]["full_text"]

    def test_repair_adjacent_quotes_in_scene_description(self):
        raw = '{"metadata": {"video_title": "Test"}, "sources": [{"source_id": "source_1", "youtube_url": "https://youtube.com/watch?v=abc123", "label": "Test"}], "rewrite_script": {"full_text": "OK"}, "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:05,000", "text": "OK"}], "video_segments": [{"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:05.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Cảnh "mở đầu""}]}'
        from app.services.json_validator import loads_json_with_repair
        parsed = loads_json_with_repair(raw)
        assert isinstance(parsed, dict)
        desc = parsed["video_segments"][0]["scene_description"]
        assert desc == 'Cảnh "mở đầu"', f"Got: {desc}"

    def test_extract_json_with_unescaped_quotes(self):
        from app.services.gemini_automation import GeminiAutomationService
        svc = GeminiAutomationService()
        response = (
            'Đây là JSON của bạn:\n'
            '{\n'
            '  "metadata": {"video_title": "Test"},\n'
            '  "sources": [{"source_id": "source_1", "youtube_url": "https://youtube.com/watch?v=abc123", "label": "Test"}],\n'
            '  "rewrite_script": {"full_text": "Tên hắn là "Edward Wilson". Không thể tin được!"},\n'
            '  "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:05,000", "text": "Hắn nói "Xin chào" với tôi."}],\n'
            '  "video_segments": [{"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:05.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Cảnh mở đầu"}]'
            '\n}'
        )
        result = svc._extract_json(response)
        assert result, "Should extract JSON despite unescaped quotes"
        import json as _json
        parsed = _json.loads(result)
        assert "Edward Wilson" in parsed["rewrite_script"]["full_text"]
        assert "Xin chào" in parsed["srt"][0]["text"]


def test_browser_cookie_source_default_network_cookies(tmp_path: Path):
    """Chromium user_data_dir/Default/Network/Cookies is detected."""
    profile = tmp_path / "chrome_profile"
    cookie = profile / "Default" / "Network" / "Cookies"
    cookie.parent.mkdir(parents=True, exist_ok=True)
    cookie.write_bytes(b"")
    downloader = VideoDownloader()
    result = downloader._browser_cookie_source_from_profile(str(profile))
    assert result == f"chrome:{profile}"


def test_browser_cookie_source_legacy_network_cookies(tmp_path: Path):
    """Direct profile dir with Network/Cookies (legacy path)."""
    profile = tmp_path / "legacy_profile"
    cookie = profile / "Network" / "Cookies"
    cookie.parent.mkdir(parents=True, exist_ok=True)
    cookie.write_bytes(b"")
    downloader = VideoDownloader()
    result = downloader._browser_cookie_source_from_profile(str(profile))
    assert result == f"chrome:{profile}"


def test_browser_cookie_source_legacy_cookies(tmp_path: Path):
    """Very old Chromium with {profile}/Cookies."""
    profile = tmp_path / "old_profile"
    cookie = profile / "Cookies"
    cookie.parent.mkdir(parents=True, exist_ok=True)
    cookie.write_bytes(b"")
    downloader = VideoDownloader()
    result = downloader._browser_cookie_source_from_profile(str(profile))
    assert result == f"chrome:{profile}"


def test_browser_cookie_source_no_cookies(tmp_path: Path, monkeypatch):
    """Profile dir without any Cookies file returns None."""
    from app.core.config import settings as cfg
    monkeypatch.setattr(cfg, "gemini_profile_path", tmp_path / "nonexistent_gemini")
    profile = tmp_path / "empty_profile"
    profile.mkdir(parents=True, exist_ok=True)
    downloader = VideoDownloader()
    result = downloader._browser_cookie_source_from_profile(str(profile))
    assert result is None


def test_browser_cookie_source_none_input(monkeypatch):
    """None input returns None when no real profile exists."""
    from app.core.config import settings as cfg
    # Point gemini_profile_path to non-existent dir so it doesn't
    # accidentally pick up the real dev profile.
    monkeypatch.setattr(cfg, "gemini_profile_path", Path("Z:\\__nonexistent__"))
    downloader = VideoDownloader()
    result = downloader._browser_cookie_source_from_profile(None)
    assert result is None


def test_browser_cookie_source_named_profile(tmp_path: Path):
    """Named profile (Profile 1) with Default/Network/Cookies still detected."""
    profile = tmp_path / "named_profile"
    named = profile / "Profile 1" / "Network" / "Cookies"
    named.parent.mkdir(parents=True, exist_ok=True)
    named.write_bytes(b"")
    downloader = VideoDownloader()
    result = downloader._browser_cookie_source_from_profile(str(profile))
    assert result == f"chrome:{profile}"
