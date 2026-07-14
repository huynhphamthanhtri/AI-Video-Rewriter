import json
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from app.core.config import settings
from app.schemas.render import GeminiPayloadSchema, RenderOptions
from app.services.tts_tools import TtsVoiceoverService, probe_audio_duration
from app.services.video_tools import RenderPipeline, SubtitleBurner, VideoConcatenator, VideoCutter, VideoDownloader, probe_video_metadata


ARTIFACT_ROOT = Path(__file__).resolve().parents[1] / "outputs" / "_step8_voice_duration_e2e"


def _require_ffmpeg() -> None:
    try:
        subprocess.run([settings.ffmpeg_binary, "-version"], check=True, capture_output=True, text=True)
        subprocess.run([settings.ffprobe_binary, "-version"], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        pytest.skip(f"ffmpeg/ffprobe unavailable: {exc}")


def _make_source_video(path: Path, duration: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        settings.ffmpeg_binary,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=320x240:rate=30:duration={duration:.3f}",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-t",
        f"{duration:.3f}",
        "-shortest",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _write_silence(path: Path, duration: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 48000
    channels = 2
    frames = int(round(duration * sample_rate))
    silence_frame = b"\x00\x00" * channels
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(silence_frame * frames)


def _payload(title: str, source_path: Path) -> GeminiPayloadSchema:
    return GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": title, "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút"},
        "sources": [{"source_id": "source_1", "local_video_path": str(source_path)}],
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:04,000", "text": "Câu kiểm thử"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_id": "source_1", "source_start": "00:00:00.000", "source_end": "00:00:04.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })


def _run_case(monkeypatch: pytest.MonkeyPatch, case_name: str, source_duration: float, voice_duration: float) -> dict:
    case_root = ARTIFACT_ROOT / case_name
    outputs_dir = case_root / "outputs"
    temp_dir = case_root / "temp"
    videos_dir = case_root / "videos"
    source_path = videos_dir / f"{case_name}_source.mp4"
    _make_source_video(source_path, source_duration)

    monkeypatch.setattr(settings, "outputs_dir", outputs_dir)
    monkeypatch.setattr(settings, "temp_dir", temp_dir)
    monkeypatch.setattr(settings, "local_videos_dir", videos_dir)

    def fake_generate_natural_tts(self, payload, output_dir, workspace_dir, options, progress_callback=None, cancel_callback=None):
        fitted_dir = workspace_dir / "tts" / "fitted"
        path = fitted_dir / "cue_0001.wav"
        _write_silence(path, voice_duration)
        return {1: voice_duration}, [(path, 0.0, 1)]

    monkeypatch.setattr(TtsVoiceoverService, "generate_natural_tts", fake_generate_natural_tts)

    options = RenderOptions(
        tts_mode="voiceover",
        tts_fit_policy="hybrid",
        video_encoder="cpu",
        render_quality="fast",
        title_mode="none",
        original_audio_mode="mute",
        artifact_retention="keep_all",
    )
    result = RenderPipeline(VideoDownloader(), VideoCutter(), VideoConcatenator(), SubtitleBurner()).render(
        _payload(case_name, source_path),
        youtube_url=None,
        local_video_path=None,
        burn_subtitle=False,
        subtitle_mode="none",
        render_options=options,
    )

    render_plan_path = Path(result["render_plan_path"])
    render_plan = json.loads(render_plan_path.read_text(encoding="utf-8"))
    segment_plan = render_plan["segment_plan"][0]
    video_duration = float(probe_video_metadata(Path(result["final_video_path"])).get("duration_seconds") or 0)
    voiceover_duration = probe_audio_duration(Path(result["voiceover_path"]))

    return {
        "case": case_name,
        "output_video": result["final_video_path"],
        "render_plan": result["render_plan_path"],
        "generated_srt": result["final_subtitle_path"],
        "voiceover_audio": result["voiceover_path"],
        "video_duration": video_duration,
        "voiceover_duration": voiceover_duration,
        "segment_plan": segment_plan,
        "video_segment": render_plan["video_segments"][0],
    }


def test_voice_duration_mocked_e2e_footage_extend_and_freeze(monkeypatch: pytest.MonkeyPatch):
    _require_ffmpeg()
    if ARTIFACT_ROOT.exists():
        shutil.rmtree(ARTIFACT_ROOT)
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)

    footage = _run_case(monkeypatch, "footage_extend", source_duration=8.0, voice_duration=5.0)
    freeze = _run_case(monkeypatch, "freeze_frame", source_duration=4.0, voice_duration=6.0)

    # Both cases now use sync_speed_balance instead of extend/freeze
    footage_plan = footage["segment_plan"]
    v_speed = 0.92  # SAFE_VIDEO_MIN_SOFT
    eff_scene = 4.0 / v_speed  # 4.348
    assert footage_plan["decision"] == "sync_speed_balance"
    assert footage_plan["original_scene_duration"] == pytest.approx(4.0)
    assert footage_plan["final_scene_duration"] == pytest.approx(eff_scene, rel=1e-2)
    assert footage_plan["natural_voice_duration"] == pytest.approx(5.0)
    assert footage_plan["extend_seconds"] == 0.0
    assert footage_plan["video_speed_factor"] == v_speed
    assert footage["video_segment"]["source_end"] == "00:00:04.000"  # no extend
    assert footage["video_duration"] >= footage["voiceover_duration"] - 0.15
    assert footage["video_duration"] == pytest.approx(eff_scene, abs=0.15)

    freeze_plan = freeze["segment_plan"]
    assert freeze_plan["decision"] == "sync_speed_balance"
    assert freeze_plan["original_scene_duration"] == pytest.approx(4.0)
    assert freeze_plan["final_scene_duration"] == pytest.approx(eff_scene, rel=1e-2)
    assert freeze_plan["natural_voice_duration"] == pytest.approx(6.0)
    assert freeze_plan["extend_seconds"] == 0.0
    assert freeze_plan["video_speed_factor"] == v_speed
    assert freeze["video_segment"]["source_end"] == "00:00:04.000"
    assert freeze["video_segment"].get("freeze_frame_duration") is None
    assert freeze["video_duration"] == pytest.approx(eff_scene, abs=0.15)
    assert freeze["video_duration"] >= freeze["voiceover_duration"] - 0.15

    summary_path = ARTIFACT_ROOT / "summary.json"
    summary_path.write_text(json.dumps({"footage_extend": footage, "freeze_frame": freeze}, ensure_ascii=False, indent=2), encoding="utf-8")
