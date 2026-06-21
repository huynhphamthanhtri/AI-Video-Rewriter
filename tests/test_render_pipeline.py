from pathlib import Path

import pytest

from app.schemas.render import GeminiPayloadSchema, RenderOptions, RenderRequest
from app.services.video_tools import RenderPipeline, TitleOverlay, safe_filename_prefix, sanitize_url


class DummyDownloader:
    def __init__(self):
        self.cookies_file = None
        self.cookies_from_browser = None
        self.downloads = []

    def download(self, url: str, output_path: Path, cookies_file: str | None = None, cookies_from_browser: str | None = None) -> Path:
        self.cookies_file = cookies_file
        self.cookies_from_browser = cookies_from_browser
        self.downloads.append((url, output_path))
        output_path.write_bytes(b"video")
        return output_path


class DummyCutter:
    def __init__(self):
        self.source_paths = None
        self.reencode_segments = None

    def cut(self, source_paths: dict[str, Path], payload: GeminiPayloadSchema, clips_dir: Path, reencode_segments=False, progress_callback=None, render_options=None, cancel_callback=None):
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
        "metadata": {"video_title": "Rich Man Mocks Mom & Son | @DramatizeMe", "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })
    pipeline = RenderPipeline(DummyDownloader(), DummyCutter(), DummyConcat(), DummyBurner())
    result = pipeline.render(payload, "https://youtube.com/watch?v=x", None, True, job_id="test-job-1")
    assert "rich_man_mocks_mom_son_dramatizeme" in result["final_video_path"]
    assert result["final_video_path"].endswith("rich_man_mocks_mom_son_dramatizeme_final.mp4")
    assert Path(result["final_video_path"]).exists()
    assert Path(result["render_plan_path"]).exists()
    assert Path(result["final_subtitle_path"]).exists()
    assert Path(result["source_path"]).exists()
    assert "test_job_1" in result["workspace_dir"]
    assert result["vertical_mode"] == "none"
    assert result["render_quality"] == "balanced"
    assert result["output_resolution"] == "auto"


def test_safe_filename_prefix():
    assert safe_filename_prefix("Rich Man Mocks Mom & Son | @DramatizeMe") == "rich_man_mocks_mom_son_dramatizeme"


def test_sanitize_markdown_url():
    assert sanitize_url("[https://www.youtube.com/watch?v=j9ZJmUUivVI](https://www.youtube.com/watch?v=j9ZJmUUivVI)") == "https://www.youtube.com/watch?v=j9ZJmUUivVI"
    assert sanitize_url("<https://www.youtube.com/watch?v=j9ZJmUUivVI>") == "https://www.youtube.com/watch?v=j9ZJmUUivVI"


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
