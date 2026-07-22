import json

from scripts.baseline_report import build_report, collect_render_plans


def test_baseline_report_collects_render_diagnostics(tmp_path):
    first = tmp_path / "a_render_plan.json"
    second_dir = tmp_path / "nested"
    second_dir.mkdir()
    second = second_dir / "b_render_plan.json"
    first.write_text(json.dumps({
        "diagnostics": {"timing": {"total_seconds": 10, "steps": [{"name": "cut", "duration_seconds": 4}]}},
        "video_segments": [{}, {}], "srt": [{}],
    }), encoding="utf-8")
    second.write_text(json.dumps({
        "diagnostics": {"timing": {"total_seconds": 20, "steps": [{"name": "cut", "duration_seconds": 6}]}},
    }), encoding="utf-8")
    (tmp_path / "invalid_render_plan.json").write_text("not-json", encoding="utf-8")

    report = build_report(collect_render_plans([tmp_path]))
    assert report["sample_count"] == 2
    assert report["render_seconds"]["median"] == 15
    assert report["aggregate_slowest_steps"][0] == {"name": "cut", "duration_seconds": 10.0}
    assert report["samples"][0]["segment_count"] in {0, 2}
