import os

import pytest

from scripts.live_benchmark import acquire_lock, run_case, score_payload


def test_score_payload_rewards_valid_scene_voice_mapping():
    payload = {
        "metadata": {"video_title": "Title", "rewrite_style": "Auto", "tone": "Warm"},
        "rewrite_script": {"full_text": "Narration"},
        "srt": [{"index": index} for index in range(1, 6)],
        "video_segments": [
            {
                "subtitle_start": index,
                "subtitle_end": index,
                "source_start": f"00:00:0{index}.000",
                "source_end": f"00:00:0{index + 1}.000",
            }
            for index in range(1, 6)
        ],
    }
    score = score_payload(payload)
    assert score == {
        "deterministic_score": 100,
        "source_fidelity": 20,
        "fidelity_hits": [],
        "style_adherence": 10,
        "style_hits": [],
        "srt_count": 5,
        "video_segment_count": 5,
        "alignment_ratio": 1.0,
    }


def test_score_payload_rejects_reversed_subtitle_mapping():
    payload = {
        "metadata": {"video_title": "Title", "rewrite_style": "Auto", "tone": "Warm"},
        "rewrite_script": {"full_text": "Narration"},
        "srt": [{"index": 1}, {"index": 2}],
        "video_segments": [{"subtitle_start": 2, "subtitle_end": 1, "source_start": "00:00:01.000", "source_end": "00:00:02.000"}],
    }
    score = score_payload(payload)
    assert score["alignment_ratio"] == 0
    assert score["deterministic_score"] < 82


def test_score_payload_fails_source_fidelity_when_expected_topic_is_missing():
    payload = {
        "metadata": {"video_title": "Blender Tutorial", "rewrite_style": "Educational", "tone": "Upbeat"},
        "rewrite_script": {"full_text": "A tutorial about creating 3D graphics."},
        "srt": [{"index": index} for index in range(1, 6)],
        "video_segments": [
            {"subtitle_start": index, "subtitle_end": index, "source_start": f"00:00:0{index}.000", "source_end": f"00:00:0{index + 1}.000"}
            for index in range(1, 6)
        ],
    }
    score = score_payload(payload, ["dragon", "rồng", "Sintel"])
    assert score["source_fidelity"] == 0
    assert score["deterministic_score"] == 80


def test_score_payload_checks_prompted_style_metadata():
    payload = {
        "metadata": {"video_title": "Title", "rewrite_style": "Trầm lắng", "tone": "Trang trọng, giàu cảm xúc"},
        "rewrite_script": {"full_text": "Sintel và chú rồng."},
        "srt": [{"index": index} for index in range(1, 6)],
        "video_segments": [
            {"subtitle_start": index, "subtitle_end": index, "source_start": f"00:00:0{index}.000", "source_end": f"00:00:0{index + 1}.000"}
            for index in range(1, 6)
        ],
    }
    score = score_payload(payload, ["Sintel"], ["trầm lắng", "trang trọng"])
    assert score["style_adherence"] == 10
    assert set(score["style_hits"]) == {"trầm lắng", "trang trọng"}


def test_live_benchmark_lock_rejects_active_owner(tmp_path):
    lock_path = tmp_path / "benchmark.lock"
    lock_path.write_text(str(os.getpid()), encoding="ascii")
    with pytest.raises(RuntimeError, match="already running"):
        acquire_lock(lock_path)


def test_live_benchmark_accepts_expected_duration_rejection(monkeypatch):
    monkeypatch.setattr(
        "scripts.live_benchmark._request_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError('HTTP 422: {"code":"video_duration_exceeds_gemini_limit"}')
        ),
    )
    result = run_case(
        "http://127.0.0.1:8007",
        {
            "id": "long",
            "category": "long_form",
            "media_url": "https://example.test/long",
            "expected_outcome": "reject_duration",
        },
        30,
    )
    assert result["status"] == "expected_rejection"
    assert result["quality"] == {"duration_guard": "passed"}
