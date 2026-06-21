from __future__ import annotations

from pydantic import BaseModel, Field


class SubtitleStyleCss(BaseModel):
    font_family: str
    font_size_px: int
    color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width_px: int
    shadow_color: str
    shadow_offset_px: int
    background_color: str
    text_align: str


class SubtitleStylePreviewItem(BaseModel):
    key: str
    label: str
    description: str
    css: SubtitleStyleCss


class SubtitlePreviewStyleRequest(BaseModel):
    styles: list[str] = Field(
        default_factory=lambda: ["default", "shorts_bold", "documentary", "minimal", "news", "high_contrast"]
    )
    subtitle_font_size: str = "auto"
    subtitle_position: str = "bottom"
    subtitle_text_align: str = "center"
    subtitle_outline: bool = True
    subtitle_shadow: bool = False
    subtitle_box: bool = True
    sample_text: str = "Xin chào, đây là phụ đề preview"


class SubtitlePreviewStyleResponse(BaseModel):
    styles: list[SubtitleStylePreviewItem]
