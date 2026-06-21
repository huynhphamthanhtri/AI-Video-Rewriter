from app.schemas.subtitle import SubtitlePreviewStyleRequest
from app.services.subtitle_preview import compute_preview


class TestComputePreview:
    def test_returns_all_requested_styles(self):
        payload = SubtitlePreviewStyleRequest(
            styles=["default", "minimal", "news"],
        )
        result = compute_preview(payload)
        assert len(result.styles) == 3
        keys = [s.key for s in result.styles]
        assert keys == ["default", "minimal", "news"]

    def test_each_style_has_css_fields(self):
        payload = SubtitlePreviewStyleRequest(styles=["default"])
        result = compute_preview(payload)
        item = result.styles[0]
        assert item.css.font_family
        assert item.css.font_size_px > 0
        assert item.css.outline_width_px >= 0
        assert item.css.shadow_offset_px >= 0
        assert item.css.text_align in ("left", "center", "right")

    def test_outline_disabled_sets_zero_width(self):
        payload = SubtitlePreviewStyleRequest(styles=["default"], subtitle_outline=False)
        result = compute_preview(payload)
        assert result.styles[0].css.outline_width_px == 0

    def test_shadow_disabled_sets_zero_offset(self):
        payload = SubtitlePreviewStyleRequest(styles=["default"], subtitle_shadow=False)
        result = compute_preview(payload)
        assert result.styles[0].css.shadow_offset_px == 0

    def test_shadow_enabled_sets_positive_offset(self):
        payload = SubtitlePreviewStyleRequest(styles=["shorts_bold"], subtitle_shadow=True)
        result = compute_preview(payload)
        assert result.styles[0].css.shadow_offset_px > 0

    def test_box_disabled_sets_transparent_bg(self):
        payload = SubtitlePreviewStyleRequest(styles=["default"], subtitle_box=False)
        result = compute_preview(payload)
        assert result.styles[0].css.background_color == "transparent"

    def test_box_enabled_sets_non_transparent_bg(self):
        payload = SubtitlePreviewStyleRequest(styles=["default"], subtitle_box=True)
        result = compute_preview(payload)
        assert result.styles[0].css.background_color != "transparent"

    def test_font_size_override(self):
        payload = SubtitlePreviewStyleRequest(styles=["default"], subtitle_font_size="large")
        result = compute_preview(payload)
        assert result.styles[0].css.font_size_px == 56

    def test_label_and_description(self):
        payload = SubtitlePreviewStyleRequest(styles=["shorts_bold"])
        result = compute_preview(payload)
        item = result.styles[0]
        assert item.label == "Shorts Bold"
        assert item.description

    def test_all_six_styles_default(self):
        payload = SubtitlePreviewStyleRequest()
        result = compute_preview(payload)
        assert len(result.styles) == 6

    def test_font_family_ends_with_sans_serif(self):
        payload = SubtitlePreviewStyleRequest(styles=["documentary"])
        result = compute_preview(payload)
        assert result.styles[0].css.font_family.endswith(", sans-serif")

    def test_text_align_center_default(self):
        payload = SubtitlePreviewStyleRequest(styles=["default"])
        result = compute_preview(payload)
        assert result.styles[0].css.text_align == "center"
