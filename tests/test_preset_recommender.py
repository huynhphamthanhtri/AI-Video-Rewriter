from __future__ import annotations

import pytest
from app.services.preset_recommender import PresetRecommender, TitleNormalizer, PRESET_RULES


def test_provided_title_preferred_over_url():
    """When video_title is provided, it is used even if youtube_url is also provided."""
    r = PresetRecommender()
    result = r.recommend(video_title="iPhone 16 Pro Review", youtube_url="https://youtube.com/watch?v=xyz")
    assert result["title"] == "iPhone 16 Pro Review"
    assert result["title_source"] == "provided"


def test_empty_title_falls_back_to_url(monkeypatch):
    """When video_title is empty, extracts from youtube_url."""
    def mock_extract(self, url):
        return "Inside the Bodycam: Police Chase"
    monkeypatch.setattr(PresetRecommender, "_extract_title_from_url", mock_extract)

    r = PresetRecommender()
    result = r.recommend(video_title="", youtube_url="https://youtube.com/watch?v=xyz")
    assert result["title"] == "Inside the Bodycam: Police Chase"
    assert result["title_source"] == "extracted"


def test_both_empty_returns_empty():
    """When both title and url are empty, no recommendations."""
    r = PresetRecommender()
    result = r.recommend(video_title="", youtube_url="")
    assert result["title"] is None
    assert result["recommendations"] == []
    assert result["title_source"] == "none"


def test_extraction_failure_with_provided_title_still_recommends():
    """Provided title is used directly, no yt-dlp call needed."""
    r = PresetRecommender()
    result = r.recommend(video_title="Công Nghệ Mới 2024", youtube_url="")
    assert result["title"] == "Công Nghệ Mới 2024"
    assert len(result["recommendations"]) > 0


def test_extraction_failure_with_url_only(monkeypatch):
    """When yt-dlp fails and no title provided, returns empty."""
    def mock_extract(self, url):
        return None
    monkeypatch.setattr(PresetRecommender, "_extract_title_from_url", mock_extract)

    r = PresetRecommender()
    result = r.recommend(video_title="", youtube_url="https://youtube.com/watch?v=xyz")
    assert result["title"] is None
    assert result["recommendations"] == []


def test_sports_keywords_map_to_youtube_shorts_not_us_cops():
    """Sports keywords should recommend YouTube Shorts Review, not US COPS Documentary."""
    r = PresetRecommender()
    result = r.recommend(video_title="NBA Finals 2024 Highlights")
    rec_names = [rec["preset_name"] for rec in result["recommendations"]]
    assert "US COPS Documentary" not in rec_names
    assert "YouTube Shorts Review" in rec_names


def test_multiple_matches_sorted_by_confidence():
    """Recommendations returned sorted by confidence descending."""
    r = PresetRecommender()
    result = r.recommend(video_title="Bodycam: Police Chase Investigation Documentary")
    confidences = [rec["confidence"] for rec in result["recommendations"]]
    assert confidences == sorted(confidences, reverse=True)


def test_low_confidence_filtered_out():
    """Recommendations with confidence < 0.15 are excluded."""
    r = PresetRecommender()
    result = r.recommend(video_title="Random Video With No Keywords Whatsoever")
    for rec in result["recommendations"]:
        assert rec["confidence"] >= 0.15


def test_vietnamese_diacritic_normalization():
    """Vietnamese text with diacritics matches normalized keywords."""
    r = PresetRecommender()
    result = r.recommend(video_title="Review Công Nghệ Mới Nhất 2024")
    rec_names = [rec["preset_name"] for rec in result["recommendations"]]
    assert "Review Công Nghệ" in rec_names


def test_title_normalizer_strip_diacritics():
    assert TitleNormalizer.strip_diacritics("Công Nghệ") == "Cong Nghe"


def test_title_normalizer_lowercase():
    assert TitleNormalizer.normalize("iPhone 16 PRO") == "iphone 16 pro"


def test_title_normalizer_punctuation_removed():
    assert TitleNormalizer.normalize("Hello, World!") == "hello world"


def test_confidence_strong():
    """Many keyword matches + exact name bonus -> high confidence."""
    r = PresetRecommender()
    result = r.recommend(video_title="US COPS Documentary: Bodycam Police Chase")
    for rec in result["recommendations"]:
        if rec["preset_name"] == "US COPS Documentary":
            assert rec["confidence"] >= 0.70
            assert rec["confidence_label"] == "strong"


def test_confidence_medium():
    """Moderate keyword matches -> medium confidence."""
    r = PresetRecommender()
    result = r.recommend(video_title="App Review and Gadget Unboxing Technology")
    for rec in result["recommendations"]:
        if rec["preset_name"] == "Review Công Nghệ":
            assert rec["confidence"] >= 0.30
            assert rec["confidence_label"] in ("medium", "weak")


def test_exact_preset_name_bonus():
    """Title containing the exact preset name gets a confidence boost."""
    r = PresetRecommender()
    result = r.recommend(video_title="Tin Tức Nhanh: Hôm Nay Có Gì?")
    for rec in result["recommendations"]:
        if rec["preset_name"] == "Tin Tức Nhanh":
            assert rec["confidence"] >= 0.40


def test_preset_rules_cover_all_builtin_presets():
    """Every builtin preset should have at least one keyword rule."""
    builtin_names = [
        "Mặc Định", "TikTok Viral 60s", "YouTube Shorts Review", "Review Công Nghệ",
        "Podcast Tóm Tắt", "Documentary Mini", "Tin Tức Nhanh", "US COPS Documentary",
        "Reaction Hài Hước", "Drama Kể Chuyện", "Phân Tích Chuyên Gia",
        "Content Giáo Dục", "Nhà Đầu Tư", "Marketing Case Study",
        "Tranh Luận/Góc Nhìn Trái Chiều",
    ]
    rule_presets = {rule.preset_name for rule in PRESET_RULES}
    for name in builtin_names:
        if name != "Mặc Định":
            assert name in rule_presets, f"Missing rule for {name}"


def test_title_source_provided():
    r = PresetRecommender()
    result = r.recommend(video_title="Test Video")
    assert result["title_source"] == "provided"


def test_title_source_extracted(monkeypatch):
    def mock_extract(self, url):
        return "Extracted Title"
    monkeypatch.setattr(PresetRecommender, "_extract_title_from_url", mock_extract)
    r = PresetRecommender()
    result = r.recommend(video_title="", youtube_url="https://youtube.com/watch?v=xyz")
    assert result["title_source"] == "extracted"


def test_ytdlp_failure_graceful(monkeypatch):
    """yt-dlp failure should not crash, returns empty gracefully."""
    def mock_extract(self, url):
        return None
    monkeypatch.setattr(PresetRecommender, "_extract_title_from_url", mock_extract)
    r = PresetRecommender()
    result = r.recommend(video_title="", youtube_url="https://youtube.com/watch?v=xyz")
    assert result["title"] is None
    assert result["recommendations"] == []
