import pytest

from app.schemas.render import RenderOptions
from app.services.title_layout import (
    TitleLayoutResult,
    compute_title_layout,
    compute_title_preview,
    resolve_badge_text,
    resolve_title_text,
)


def test_center_align_expression():
    options = RenderOptions(title_mode="custom", title_text="Test", title_text_align="center")
    layout = compute_title_layout(options, 1920, 1080)
    assert layout.lines[0].x_expr == "(w-text_w)/2"


def test_right_align_expression():
    options = RenderOptions(title_mode="custom", title_text="Test", title_text_align="right")
    layout = compute_title_layout(options, 1920, 1080)
    assert "text_w" in layout.lines[0].x_expr


def test_left_align_expression():
    options = RenderOptions(title_mode="custom", title_text="Test", title_text_align="left")
    layout = compute_title_layout(options, 1920, 1080)
    assert "text_w" not in layout.lines[0].x_expr


def test_multi_line_creates_separate_drawtext_lines():
    options = RenderOptions(
        title_mode="custom", title_text="Hello World Foo Bar",
        title_max_lines=2, title_chars_per_line=16,
    )
    layout = compute_title_layout(options, 1920, 1080)
    assert len(layout.lines) == 2
    assert layout.lines[0].y_expr != layout.lines[1].y_expr


def test_breaking_yellow_header():
    options = RenderOptions(
        title_mode="custom", title_text="Breaking News",
        title_style="breaking_yellow",
    )
    layout = compute_title_layout(options, 1920, 1080)
    assert layout.header_drawbox is not None
    assert len(layout.header_drawbox) > 0


def test_badge_auto_detects_keywords():
    options = RenderOptions(title_mode="auto", title_badge_mode="auto")
    metadata = {"video_title": "Bodycam footage police chase"}
    layout = compute_title_layout(options, 1920, 1080, metadata)
    assert layout.badge is not None
    assert layout.badge.text == "BODYCAM"


def test_badge_custom_text():
    options = RenderOptions(
        title_mode="custom", title_text="Test",
        title_badge_mode="custom", title_badge_text="SPECIAL REPORT",
    )
    layout = compute_title_layout(options, 1920, 1080)
    assert layout.badge is not None
    assert layout.badge.text == "SPECIAL REPORT"


def test_badge_none():
    options = RenderOptions(title_mode="custom", title_text="Test", title_badge_mode="none")
    layout = compute_title_layout(options, 1920, 1080)
    assert layout.badge is None


def test_preview_has_pixel_values():
    options = RenderOptions(title_mode="custom", title_text="Test Title", title_text_align="center")
    preview = compute_title_preview(options, 1920, 1080)
    assert "lines" in preview
    assert len(preview["lines"]) > 0
    line = preview["lines"][0]
    assert isinstance(line["x_px"], int)
    assert isinstance(line["y_px"], int)
    assert isinstance(line["width_px"], int)


def test_font_size_small_medium_large_auto():
    for size, expected in [("small", 38), ("medium", 48), ("large", 60), ("auto", 52)]:
        options = RenderOptions(title_mode="custom", title_text="Test", title_font_size=size)
        layout = compute_title_layout(options, 1920, 1080)
        assert layout.lines[0].font_size == expected


def test_position_top_upper_third_center_bottom():
    options = RenderOptions(title_mode="custom", title_text="Test")
    exprs = {}
    for pos in ["top", "upper_third", "center", "bottom"]:
        o = options.model_copy(update={"title_position": pos})
        layout = compute_title_layout(o, 1920, 1080)
        exprs[pos] = layout.lines[0].y_expr
    assert len(set(exprs.values())) == 4


def test_has_background_for_all_styles():
    styles = ["yellow_highlight", "dark_badge", "clean_white", "breaking_yellow"]
    for style in styles:
        options = RenderOptions(title_mode="custom", title_text="Test", title_style=style)
        layout = compute_title_layout(options, 1920, 1080)
        assert layout.lines[0].has_background is True
        assert layout.lines[0].background_color is not None


def test_empty_title_returns_empty_lines():
    options = RenderOptions(title_mode="custom", title_text="")
    layout = compute_title_layout(options, 1920, 1080)
    assert layout.lines == []


def test_resolve_badge_text_none():
    options = RenderOptions(title_badge_mode="none")
    assert resolve_badge_text(options) == ""


def test_resolve_badge_text_custom():
    options = RenderOptions(title_badge_mode="custom", title_badge_text="ALERT")
    assert resolve_badge_text(options) == "ALERT"


def test_resolve_badge_text_auto_no_metadata():
    options = RenderOptions(title_badge_mode="auto")
    assert resolve_badge_text(options) == ""


def test_resolve_title_text_auto():
    options = RenderOptions(title_mode="auto")
    metadata = {"video_title": "Breaking News Report"}
    text = resolve_title_text(options, metadata)
    assert "Breaking" in text
    assert "News" in text


def test_resolve_title_text_custom():
    options = RenderOptions(title_mode="custom", title_text="My Custom Title")
    text = resolve_title_text(options)
    assert text == "My Custom Title"


def test_preview_badge_pixel_values():
    options = RenderOptions(
        title_mode="custom", title_text="Test",
        title_badge_mode="custom", title_badge_text="BODYCAM",
    )
    preview = compute_title_preview(options, 1920, 1080)
    badge = preview["badge"]
    assert badge is not None
    assert isinstance(badge["x_px"], int)
    assert isinstance(badge["y_px"], int)
    assert isinstance(badge["width_px"], int)
    assert isinstance(badge["height_px"], int)


def test_breaking_yellow_x_expr_with_badge():
    options = RenderOptions(
        title_mode="custom", title_text="Test",
        title_style="breaking_yellow",
        title_badge_mode="custom", title_badge_text="LIVE",
        title_text_align="left",
    )
    layout = compute_title_layout(options, 1920, 1080)
    assert "max(160" in layout.lines[0].x_expr or "w*0.14" in layout.lines[0].x_expr


def test_safe_margin_user_specified():
    options = RenderOptions(
        title_mode="custom", title_text="Test",
        title_safe_margin=60,
    )
    layout = compute_title_layout(options, 1920, 1080)
    assert layout.safe_margin_px == 60


def test_header_height_user_specified():
    options = RenderOptions(
        title_mode="custom", title_text="Test",
        title_header_height=150,
    )
    layout = compute_title_layout(options, 1920, 1080)
    assert layout.header_height_px == 150


def test_pixel_values_scale_with_resolution():
    options = RenderOptions(title_mode="custom", title_text="Hello", title_text_align="center")
    preview_720p = compute_title_preview(options, 1280, 720)
    preview_1080p = compute_title_preview(options, 1920, 1080)
    assert preview_720p["lines"][0]["x_px"] < preview_1080p["lines"][0]["x_px"]
    assert preview_720p["safe_margin_px"] < preview_1080p["safe_margin_px"]
