from pathlib import Path

from scripts.benchmark_manifest import validate_manifest


def test_benchmark_manifest_has_expected_shape():
    data, errors = validate_manifest(Path(__file__).resolve().parents[1] / "benchmark" / "manifest.json")
    assert errors == []
    assert len(data["sources"]) == 18
    assert sum(1 for source in data["sources"] if source.get("style_pair")) == 3


def test_locked_sources_have_media_and_license():
    data, _ = validate_manifest(Path(__file__).resolve().parents[1] / "benchmark" / "manifest.json")
    locked = [source for source in data["sources"] if source["status"] == "locked"]
    assert locked
    assert all(source.get("media_url") and source.get("license") for source in locked)
