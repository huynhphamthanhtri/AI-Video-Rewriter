from app.services.gemini_story_plan_validator import looks_like_story_plan_root, validate_story_plan_payload


def _valid_plan() -> dict:
    return {
        "plan_version": 1,
        "story_outline": ["Hook", "Middle", "Payoff"],
        "selected_moments": [
            {
                "source_id": "source_1",
                "analysis_index": 1,
                "timestamp_hint": "00:00:01.000",
                "purpose": "hook",
                "voiceover_point": "Open with the clearest visual beat.",
            }
        ],
        "target_structure": {"opening": "open", "middle": "middle", "climax": "climax", "ending": "ending"},
        "quality_notes": [],
    }


def test_valid_story_plan_passes():
    valid, errors, fixed = validate_story_plan_payload(_valid_plan())
    assert valid
    assert errors == []
    assert fixed is not None


def test_story_plan_rejects_invalid_timestamp():
    plan = _valid_plan()
    plan["selected_moments"][0]["timestamp_hint"] = "00:00:01,000"
    valid, errors, _ = validate_story_plan_payload(plan)
    assert not valid
    assert any("timestamp_hint" in error for error in errors)


def test_looks_like_story_plan_root():
    assert looks_like_story_plan_root(_valid_plan())
    final = _valid_plan()
    final["video_segments"] = []
    assert not looks_like_story_plan_root(final)
