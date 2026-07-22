from scripts.benchmark_qualification import qualify


def test_qualification_requires_auto_style_fidelity_and_prompted_adherence():
    payload = {
        "metadata": {"video_title": "Sintel", "rewrite_style": "Trầm lắng", "tone": "Trang trọng"},
        "rewrite_script": {"full_text": "Sintel tìm chú rồng."},
        "srt": [{"index": index} for index in range(1, 6)],
        "video_segments": [
            {"subtitle_start": index, "subtitle_end": index, "source_start": f"00:00:0{index}.000", "source_end": f"00:00:0{index + 1}.000"}
            for index in range(1, 6)
        ],
    }
    manifest = {
        "quality_thresholds": {"total_score": 82, "source_fidelity": 17, "scene_voice_alignment": 21, "style_adherence_when_prompted": 8},
        "sources": [{
            "id": "sintel", "expected_minutes": 15, "expected_keywords": ["Sintel", "rồng"],
            "style_pair": True, "expected_style_keywords": ["trầm lắng", "trang trọng"],
        }],
    }
    result = {"id": "sintel", "status": "done", "elapsed_seconds": 90, "gemini_json": payload}
    report = qualify([result], [result], manifest)
    assert report["passed"] is True
    assert report["summary"]["renderable_pass_rate"] == 1.0
    assert report["summary"]["prompted_style_passed"] == 1


def test_qualification_accepts_expected_duration_guard():
    manifest = {
        "quality_thresholds": {"total_score": 82, "source_fidelity": 17, "scene_voice_alignment": 21, "style_adherence_when_prompted": 8},
        "sources": [{"id": "long", "expected_minutes": 60, "expected_outcome": "reject_duration"}],
    }
    report = qualify([{"id": "long", "status": "expected_rejection"}], [], manifest)
    assert report["passed"] is True
    assert report["summary"]["auto_passed"] == 1
