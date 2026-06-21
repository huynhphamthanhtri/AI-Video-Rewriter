from __future__ import annotations

from app.schemas.render import RenderOptions
from app.schemas.subtitle import SubtitlePreviewStyleRequest, SubtitlePreviewStyleResponse, SubtitleStyleCss, SubtitleStylePreviewItem
from app.services.subtitle_styler import SubtitleStyler


def _back_colour_to_rgba(ass_color: str) -> str:
    if not ass_color.startswith("&H"):
        return ass_color
    hex_part = ass_color[2:]
    if len(hex_part) < 8:
        return "transparent"
    alpha_hex = hex_part[:2]
    blue = int(hex_part[2:4], 16)
    green = int(hex_part[4:6], 16)
    red = int(hex_part[6:8], 16)
    alpha = int(alpha_hex, 16)
    if alpha == 0:
        return "transparent"
    return f"rgba({red},{green},{blue},{round(1.0 - alpha / 255.0, 3)})"


def compute_preview(payload: SubtitlePreviewStyleRequest) -> SubtitlePreviewStyleResponse:
    styler = SubtitleStyler()
    items: list[SubtitleStylePreviewItem] = []

    for style_key in payload.styles:
        ro = RenderOptions(
            subtitle_style=style_key,
            subtitle_font_size=payload.subtitle_font_size,
            subtitle_position=payload.subtitle_position,
            subtitle_text_align=payload.subtitle_text_align,
            subtitle_outline=payload.subtitle_outline,
            subtitle_shadow=payload.subtitle_shadow,
            subtitle_box=payload.subtitle_box,
        )
        resolved = styler._resolve_style(ro)
        metadata = SubtitleStyler.STYLE_METADATA.get(style_key, {})

        fontsize = int(resolved.get("Fontsize", 48))
        outline = int(resolved.get("Outline", 0))
        shadow = int(resolved.get("Shadow", 0))
        align_idx = int(resolved.get("Alignment", 2))

        text_align_map = {1: "left", 2: "center", 3: "right", 4: "left", 5: "center", 6: "right", 7: "left", 8: "center", 9: "right"}
        text_align = text_align_map.get(align_idx, "center")
        back_colour = str(resolved.get("BackColour", "&H00000000"))

        bg = _back_colour_to_rgba(back_colour) if payload.subtitle_box else "transparent"
        shadow_color = "rgba(0,0,0,0.6)" if shadow > 0 else "transparent"

        items.append(SubtitleStylePreviewItem(
            key=style_key,
            label=metadata.get("label", style_key),
            description=metadata.get("description", ""),
            css=SubtitleStyleCss(
                font_family=str(resolved.get("Fontname", "Arial, sans-serif")) + ", sans-serif",
                font_size_px=fontsize,
                outline_width_px=outline if payload.subtitle_outline else 0,
                shadow_offset_px=shadow if payload.subtitle_shadow else 0,
                shadow_color=shadow_color,
                background_color=bg,
                text_align=text_align,
            ),
        ))

    return SubtitlePreviewStyleResponse(styles=items)
