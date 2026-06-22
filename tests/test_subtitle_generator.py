from pathlib import Path

from app.schemas.render import GeminiPayloadSchema
from app.services.subtitle_generator import SubtitleGenerator


def test_generate_srt(tmp_path: Path):
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "A", "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "Xin chào"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })
    output = SubtitleGenerator().generate(payload, tmp_path / "output.srt")
    assert output.exists()
    assert "Xin chào" in output.read_text(encoding="utf-8")


def test_generate_srt_uses_adjusted_payload_timestamps(tmp_path: Path):
    payload = GeminiPayloadSchema.model_validate({
        "metadata": {"video_title": "A", "rewrite_style": "Viral", "target_audience": "Đại chúng", "tone": "Năng lượng cao", "target_duration": "1-3 phút"},
        "rewrite_script": {"full_text": "Xin chào"},
        "srt": [{"index": 1, "start": "00:00:02,000", "end": "00:00:06,500", "text": "Đã chỉnh timing"}],
        "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:02.000", "source_end": "00:00:06.500", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "Mở đầu", "importance_score": 95}],
    })

    output = SubtitleGenerator().generate(payload, tmp_path / "adjusted.srt")
    content = output.read_text(encoding="utf-8")

    assert "00:00:02,000 --> 00:00:06,500" in content
    assert "Đã chỉnh timing" in content
