from app.services.prompt_health import score_preset_health


def _health(**overrides):
    defaults = dict(
        rewrite_style="Storytelling",
        target_audience="Đại chúng",
        tone="Thân thiện",
        target_duration="3-5 phút",
        retention_mode="Cao",
        hook_style="Cảnh đắt giá",
        clip_strategy="Giữ đầy đủ ngữ cảnh",
        reuse_level="Trung bình",
        content_density="Trung bình",
        target_language="Tiếng Việt",
        target_market="Việt Nam",
        localization_level="medium",
        rename_characters=True,
        adapt_culture=True,
        adapt_currency=True,
        adapt_units=True,
        adapt_company_names=True,
        adaptation_mode="localized",
        narrator_persona="neutral_narrator",
    )
    defaults.update(overrides)
    return defaults


def test_health_details_excellent():
    result = score_preset_health(_health(
        rewrite_style="Điều tra", target_audience="Chuyên gia", tone="Nghiêm túc",
        retention_mode="Cực cao", hook_style="Cảnh đắt giá",
        narrator_persona="detective",
    ))
    assert "details" in result
    assert len(result["details"]) > 0
    for d in result["details"]:
        assert "factor" in d
        assert "label" in d
        assert "value" in d
        assert "impact" in d
        assert "reason" in d


def test_health_details_impacts_sum_to_score():
    result = score_preset_health(_health(
        rewrite_style="Điều tra", target_audience="Chuyên gia", tone="Nghiêm túc",
        retention_mode="Cực cao", hook_style="Cảnh đắt giá",
        narrator_persona="detective",
    ))
    positive_sum = sum(d["impact"] for d in result["details"] if d["impact"] > 0)
    negative_sum = sum(d["impact"] for d in result["details"] if d["impact"] < 0)
    base = 50
    computed = max(0, min(100, base + positive_sum + negative_sum))
    assert result["score"] == computed


def test_health_details_empty_for_missing_factors():
    result = score_preset_health(_health(
        target_language="", target_market="", localization_level="none",
    ))
    assert "details" in result
