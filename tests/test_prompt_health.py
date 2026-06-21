from app.services.prompt_health import score_preset_health


def test_health_score_excellent():
    result = score_preset_health({
        "rewrite_style": "Điều tra", "target_audience": "Chuyên gia", "tone": "Nghiêm túc",
        "target_duration": "5-10 phút", "retention_mode": "Cực cao", "hook_style": "Cảnh đắt giá",
        "clip_strategy": "Giữ đầy đủ ngữ cảnh", "reuse_level": "Trung bình", "content_density": "Cao",
        "target_language": "Tiếng Việt", "target_market": "Việt Nam", "localization_level": "medium",
        "rename_characters": True, "adapt_culture": True, "adapt_currency": True,
        "adapt_units": True, "adapt_company_names": True, "adaptation_mode": "localized",
        "narrator_persona": "detective",
    })
    assert result["score"] >= 85
    assert result["level"] == "excellent"


def test_health_score_good():
    result = score_preset_health({
        "rewrite_style": "Storytelling", "target_audience": "Đại chúng", "tone": "Thân thiện",
        "target_duration": "3-5 phút", "retention_mode": "Cao", "hook_style": "Gây tò mò",
        "clip_strategy": "Ưu tiên dữ kiện", "reuse_level": "Trung bình", "content_density": "Trung bình",
        "target_language": "Tiếng Việt", "target_market": "Việt Nam", "localization_level": "medium",
        "rename_characters": True, "adapt_culture": True, "adapt_currency": True,
        "adapt_units": True, "adapt_company_names": True, "adaptation_mode": "localized",
        "narrator_persona": "neutral_narrator",
    })
    assert result["score"] >= 70
    assert result["level"] in ("good", "excellent")


def test_health_score_risky():
    result = score_preset_health({
        "rewrite_style": "Giữ nguyên phong cách gốc", "target_audience": "Đại chúng", "tone": "Thân thiện",
        "target_duration": "1-3 phút", "retention_mode": "Bình thường", "hook_style": "Kể chuyện",
        "clip_strategy": "Giữ đầy đủ ngữ cảnh", "reuse_level": "Cao", "content_density": "Cao",
        "target_language": "Tiếng Việt", "target_market": "Việt Nam", "localization_level": "none",
        "rename_characters": True, "adapt_culture": True, "adapt_currency": True,
        "adapt_units": True, "adapt_company_names": True, "adaptation_mode": "inspired",
        "narrator_persona": "neutral_narrator",
    })
    assert result["score"] < 70
    assert result["level"] in ("risky", "weak")


def test_health_score_weak():
    result = score_preset_health({
        "rewrite_style": "Giữ nguyên phong cách gốc", "target_audience": "Đại chúng", "tone": "Thân thiện",
        "target_duration": "Tự đề xuất thời lượng phù hợp với kịch bản remake",
        "retention_mode": "Bình thường", "hook_style": "Kể chuyện",
        "clip_strategy": "Giữ đầy đủ ngữ cảnh", "reuse_level": "Trung bình", "content_density": "Trung bình",
        "target_language": "", "target_market": "", "localization_level": "none",
        "rename_characters": True, "adapt_culture": True, "adapt_currency": True,
        "adapt_units": True, "adapt_company_names": True, "adaptation_mode": "localized",
        "narrator_persona": "neutral_narrator",
    })
    assert result["score"] < 50
    assert result["level"] == "weak"


def test_health_score_returns_strengths():
    result = score_preset_health({
        "rewrite_style": "Điều tra", "target_audience": "Chuyên gia", "tone": "Nghiêm túc",
        "target_duration": "5-10 phút", "retention_mode": "Cực cao", "hook_style": "Cảnh đắt giá",
        "clip_strategy": "Giữ đầy đủ ngữ cảnh", "reuse_level": "Trung bình", "content_density": "Cao",
        "target_language": "Tiếng Việt", "target_market": "Việt Nam", "localization_level": "medium",
        "rename_characters": True, "adapt_culture": True, "adapt_currency": True,
        "adapt_units": True, "adapt_company_names": True, "adaptation_mode": "localized",
        "narrator_persona": "detective",
    })
    assert len(result["strengths"]) > 0


def test_health_score_returns_warnings():
    result = score_preset_health({
        "rewrite_style": "Giữ nguyên phong cách gốc", "target_audience": "Đại chúng", "tone": "Thân thiện",
        "target_duration": "Tự đề xuất thời lượng phù hợp với kịch bản remake",
        "retention_mode": "Bình thường", "hook_style": "Kể chuyện",
        "clip_strategy": "Giữ đầy đủ ngữ cảnh", "reuse_level": "Trung bình", "content_density": "Trung bình",
        "target_language": "", "target_market": "", "localization_level": "none",
        "rename_characters": True, "adapt_culture": True, "adapt_currency": True,
        "adapt_units": True, "adapt_company_names": True, "adaptation_mode": "localized",
        "narrator_persona": "neutral_narrator",
    })
    assert len(result["warnings"]) > 0


def test_health_score_clamped():
    result = score_preset_health({
        "rewrite_style": "Giữ nguyên phong cách gốc", "target_audience": "Đại chúng", "tone": "Thân thiện",
        "target_duration": "Tự đề xuất thời lượng phù hợp với kịch bản remake",
        "retention_mode": "Bình thường", "hook_style": "Kể chuyện",
        "clip_strategy": "Giữ đầy đủ ngữ cảnh", "reuse_level": "Thấp", "content_density": "Thấp",
        "target_language": "", "target_market": "", "localization_level": "none",
        "rename_characters": False, "adapt_culture": False, "adapt_currency": False,
        "adapt_units": False, "adapt_company_names": False, "adaptation_mode": "faithful",
        "narrator_persona": "neutral_narrator",
    })
    assert 0 <= result["score"] <= 100
