from pathlib import Path

import pytest

from app.schemas.render import RenderOptions
from app.services.subtitle_styler import SubtitleStyler, _parse_srt, _srt_time_to_centiseconds


class TestSrtTimeToCentiseconds:
    def test_converts_properly(self):
        assert _srt_time_to_centiseconds("00:00:01,500") == "0:00:01.50"
        assert _srt_time_to_centiseconds("00:00:00,000") == "0:00:00.00"
        assert _srt_time_to_centiseconds("01:02:03,123") == "1:02:03.12"
        assert _srt_time_to_centiseconds("12:34:56,789") == "12:34:56.78"


class TestParseSrt:
    def test_valid_srt(self, tmp_path: Path):
        srt = tmp_path / "test.srt"
        srt.write_text(
            "1\n00:00:01,000 --> 00:00:04,000\nHello world\n\n"
            "2\n00:00:05,000 --> 00:00:09,500\nDòng thứ hai\ncó hai dòng\n\n"
            "3\n00:00:10,000 --> 00:00:15,000\nLine three",
            encoding="utf-8",
        )
        items = _parse_srt(srt)
        assert len(items) == 3
        assert items[0]["index"] == 1
        assert items[0]["start"] == "0:00:01.00"
        assert items[0]["end"] == "0:00:04.00"
        assert items[0]["text"] == "Hello world"
        assert items[1]["text"] == "Dòng thứ hai\ncó hai dòng"
        assert items[2]["text"] == "Line three"

    def test_with_bom(self, tmp_path: Path):
        srt = tmp_path / "bom.srt"
        srt.write_bytes(b"\xef\xbb\xbf1\n00:00:00,500 --> 00:00:02,000\nBOM test")
        items = _parse_srt(srt)
        assert len(items) == 1
        assert items[0]["text"] == "BOM test"

    def test_empty(self, tmp_path: Path):
        srt = tmp_path / "empty.srt"
        srt.write_text("", encoding="utf-8")
        assert _parse_srt(srt) == []

    def test_no_timeline(self, tmp_path: Path):
        srt = tmp_path / "garbage.srt"
        srt.write_text("just text\nno timestamps", encoding="utf-8")
        assert _parse_srt(srt) == []


class TestSrtToAss:
    STYLE_ALIGN_IDX = 18
    STYLE_BACK_IDX = 6
    STYLE_FONT_SIZE_IDX = 2
    STYLE_OUTLINE_IDX = 16
    STYLE_SHADOW_IDX = 17
    def test_headers_and_structure(self, tmp_path: Path):
        srt = tmp_path / "input.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nTest", encoding="utf-8")
        ass = tmp_path / "output.ass"
        SubtitleStyler().srt_to_ass(srt, ass, RenderOptions())
        content = ass.read_text(encoding="utf-8")
        assert "[Script Info]" in content
        assert "[V4+ Styles]" in content
        assert "[Events]" in content
        assert "Format: Name, Fontname, Fontsize" in content
        assert "Style: Default," in content
        assert "Dialogue: 0,0:00:01.00,0:00:03.00,Default" in content

    def test_event_text_newline_conversion(self, tmp_path: Path):
        srt = tmp_path / "input.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nLine1\nLine2", encoding="utf-8")
        ass = tmp_path / "output.ass"
        SubtitleStyler().srt_to_ass(srt, ass, RenderOptions())
        content = ass.read_text(encoding="utf-8")
        assert "Line1\\NLine2" in content, "newlines should be converted to \\N"

    def test_font_size_override(self, tmp_path: Path):
        srt = tmp_path / "input.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nTest", encoding="utf-8")
        ass = tmp_path / "output.ass"
        SubtitleStyler().srt_to_ass(srt, ass, RenderOptions(subtitle_font_size="large"))
        content = ass.read_text(encoding="utf-8")
        style_line = [l for l in content.split("\n") if l.startswith("Style:")][0]
        parts = style_line.split(",")
        font_size_index = 2
        assert parts[font_size_index] == "56", f"Expected 56, got {parts[font_size_index]}"

    def test_small_font_size(self, tmp_path: Path):
        srt = tmp_path / "input.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nTest", encoding="utf-8")
        ass = tmp_path / "output.ass"
        SubtitleStyler().srt_to_ass(srt, ass, RenderOptions(subtitle_font_size="small"))
        content = ass.read_text(encoding="utf-8")
        style_line = [l for l in content.split("\n") if l.startswith("Style:")][0]
        assert style_line.split(",")[2] == "36"

    def test_outline_shadow_box_off(self, tmp_path: Path):
        srt = tmp_path / "input.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nTest", encoding="utf-8")
        ass = tmp_path / "output.ass"
        SubtitleStyler().srt_to_ass(
            srt, ass, RenderOptions(subtitle_outline=False, subtitle_shadow=False, subtitle_box=False)
        )
        content = ass.read_text(encoding="utf-8")
        style_line = [l for l in content.split("\n") if l.startswith("Style:")][0]
        parts = style_line.split(",")
        assert parts[self.STYLE_BACK_IDX] == "&H00000000"
        assert parts[15] == "1"
        assert parts[self.STYLE_OUTLINE_IDX] == "0"
        assert parts[self.STYLE_SHADOW_IDX] == "0"

    def test_box_enabled_sets_back_colour(self, tmp_path: Path):
        srt = tmp_path / "input.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nTest", encoding="utf-8")
        ass = tmp_path / "output.ass"
        SubtitleStyler().srt_to_ass(srt, ass, RenderOptions(subtitle_box=True))
        content = ass.read_text(encoding="utf-8")
        style_line = [l for l in content.split("\n") if l.startswith("Style:")][0]
        parts = style_line.split(",")
        assert parts[self.STYLE_BACK_IDX] != "&H00000000"
        assert parts[self.STYLE_BACK_IDX].startswith("&H99")

    def test_position_center_alignment(self, tmp_path: Path):
        srt = tmp_path / "input.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nTest", encoding="utf-8")
        ass = tmp_path / "output.ass"
        SubtitleStyler().srt_to_ass(srt, ass, RenderOptions(subtitle_position="center"))
        content = ass.read_text(encoding="utf-8")
        style_line = [l for l in content.split("\n") if l.startswith("Style:")][0]
        parts = style_line.split(",")
        assert parts[self.STYLE_ALIGN_IDX] == "8", f"Expected 8 for center, got {parts[self.STYLE_ALIGN_IDX]}"

    def test_position_top_alignment(self, tmp_path: Path):
        srt = tmp_path / "input.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nTest", encoding="utf-8")
        ass = tmp_path / "output.ass"
        SubtitleStyler().srt_to_ass(srt, ass, RenderOptions(subtitle_position="top"))
        content = ass.read_text(encoding="utf-8")
        style_line = [l for l in content.split("\n") if l.startswith("Style:")][0]
        assert style_line.split(",")[self.STYLE_ALIGN_IDX] == "5"

    def test_text_align_left_shifts_alignment(self, tmp_path: Path):
        srt = tmp_path / "input.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nTest", encoding="utf-8")
        ass = tmp_path / "output.ass"
        opts = RenderOptions(subtitle_position="bottom", subtitle_text_align="left")
        SubtitleStyler().srt_to_ass(srt, ass, opts)
        content = ass.read_text(encoding="utf-8")
        style_line = [l for l in content.split("\n") if l.startswith("Style:")][0]
        parts = style_line.split(",")[self.STYLE_ALIGN_IDX]
        assert parts == "1", f"Expected 1 (bottom-left), got {parts}"

    def test_news_style(self, tmp_path: Path):
        srt = tmp_path / "input.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nNews test", encoding="utf-8")
        ass = tmp_path / "output.ass"
        SubtitleStyler().srt_to_ass(srt, ass, RenderOptions(subtitle_style="news", subtitle_shadow=True))
        content = ass.read_text(encoding="utf-8")
        style_line = [l for l in content.split("\n") if l.startswith("Style:")][0]
        parts = style_line.split(",")
        assert parts[1] == "Tahoma", f"news: expected Tahoma, got {parts[1]}"
        assert parts[2] == "46", f"news: expected fontsize 46, got {parts[2]}"
        assert parts[self.STYLE_OUTLINE_IDX] == "2"
        assert parts[self.STYLE_SHADOW_IDX] == "1"

    def test_high_contrast_style(self, tmp_path: Path):
        srt = tmp_path / "input.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nHC test", encoding="utf-8")
        ass = tmp_path / "output.ass"
        SubtitleStyler().srt_to_ass(srt, ass, RenderOptions(subtitle_style="high_contrast", subtitle_shadow=True))
        content = ass.read_text(encoding="utf-8")
        style_line = [l for l in content.split("\n") if l.startswith("Style:")][0]
        parts = style_line.split(",")
        assert parts[1] == "Arial", f"high_contrast: expected Arial, got {parts[1]}"
        assert parts[2] == "50", f"high_contrast: expected fontsize 50, got {parts[2]}"
        assert parts[self.STYLE_OUTLINE_IDX] == "5"
        assert parts[self.STYLE_SHADOW_IDX] == "3"

    def test_all_six_styles_produce_valid_ass(self, tmp_path: Path):
        srt = tmp_path / "input.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nTest", encoding="utf-8")
        for style in ("default", "shorts_bold", "documentary", "minimal", "news", "high_contrast"):
            ass = tmp_path / f"{style}.ass"
            SubtitleStyler().srt_to_ass(srt, ass, RenderOptions(subtitle_style=style))
            content = ass.read_text(encoding="utf-8")
            assert "Style: Default," in content
            style_line = [l for l in content.split("\n") if l.startswith("Style:")][0]
            parts = style_line.split(",")
            assert len(parts) >= 19
            assert parts[18]  # Alignment present
